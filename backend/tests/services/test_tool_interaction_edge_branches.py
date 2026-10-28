"""Edge-case branches for durable interaction validation and races.

The main behavior suite already covers the happy paths. These checks pin the
fail-closed validation corners (credential fields, unsupported schema shapes,
absolute deadlines) and the two outcomes of losing a concurrent response race,
which the durable store must resolve without ever reviving a terminal row.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tortoise.context import TortoiseContext

from app.core.timezone import now_utc
from app.models.tool_interaction import (
    InteractionKind,
    InteractionOutcome,
    InteractionRequest,
    InteractionStatus,
)
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.services import tool_interactions


@pytest.fixture
def run_orm(tmp_path):
    runner = asyncio.Runner()
    database_url = f"sqlite://{tmp_path / 'interaction-edges.sqlite3'}"

    def run(scenario):
        async def _wrapped():
            async with TortoiseContext() as context:
                await context.init(
                    db_url=database_url, modules={"models": ["app.models"]}
                )
                await context.generate_schemas()
                return await scenario()

        return runner.run(_wrapped())

    try:
        yield run
    finally:
        runner.close()


async def _user(label: str, *, active: bool = True) -> User:
    suffix = uuid4().hex[:8]
    return await User.create(
        id=uuid4(),
        username=f"{label}_{suffix}",
        email=f"{label}_{suffix}@interaction-edges.test",
        hashed_password="x",
        is_active=active,
    )


async def _team(owner: User) -> Team:
    team = await Team.create(id=uuid4(), name=f"team_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    return team


async def _form_interaction(
    owner: User, team: Team, *, schema: dict | None = None, **kwargs
) -> InteractionRequest:
    return await tool_interactions.create_interaction(
        kind=InteractionKind.ELICITATION,
        actor=owner,
        team_id=team.id,
        payload={
            "mode": "form",
            "message": "Name?",
            "requested_schema": schema
            or {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
        audience={"user_ids": [str(owner.id)]},
        ttl_seconds=60,
        **kwargs,
    )


def test_schema_request_detection_covers_mapping_shapes():
    assert tool_interactions.schema_requests_secrets(None) is False
    assert tool_interactions.schema_requests_secrets("not-a-schema") is False
    assert tool_interactions.schema_requests_secrets({"properties": []}) is False
    assert (
        tool_interactions.schema_requests_secrets(
            {"properties": {"name": {"type": "string"}}}
        )
        is False
    )
    # Credential markers are detected in the field name, title, description
    # and format, so a benign-looking name cannot hide a password prompt.
    assert tool_interactions.schema_requests_secrets(
        {"properties": {"auth": {"description": "Enter your API token"}}}
    )
    assert tool_interactions.schema_requests_secrets(
        {"properties": {"code": {"title": "Password"}}}
    )
    assert tool_interactions.schema_requests_secrets(
        {"properties": {"value": {"format": "secret"}}}
    )


def test_form_validation_rejects_secret_and_unsupported_shapes():
    cases = [
        (
            {
                "type": "object",
                "properties": {"password": {"type": "string"}},
            },
            {"password": "hunter2"},
            ResponseCode.TOOL_INTERACTION_SECRET_FIELD_REJECTED,
        ),
        (
            {
                "type": "object",
                "properties": {"value": {"type": "string", "format": "password"}},
            },
            {"value": "hunter2"},
            ResponseCode.TOOL_INTERACTION_SECRET_FIELD_REJECTED,
        ),
        (
            {"type": "object", "properties": {"value": "string"}},
            {"value": "x"},
            ResponseCode.TOOL_INTERACTION_SCHEMA_INVALID,
        ),
        (
            {"type": "object", "properties": {"value": {"type": "object"}}},
            {"value": {"nested": 1}},
            ResponseCode.TOOL_INTERACTION_SCHEMA_INVALID,
        ),
        (
            {
                "type": "object",
                "properties": {"tags": {"type": "array", "items": {"type": "integer"}}},
            },
            {"tags": ["one"]},
            ResponseCode.TOOL_INTERACTION_SCHEMA_INVALID,
        ),
        (
            {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": "value",
            },
            {"value": "x"},
            ResponseCode.TOOL_INTERACTION_SCHEMA_INVALID,
        ),
    ]
    for schema, content, expected in cases:
        with pytest.raises(BusinessError) as exc:
            tool_interactions.validate_form_content(schema, content)
        assert exc.value.code == expected
        if expected == ResponseCode.TOOL_INTERACTION_SECRET_FIELD_REJECTED:
            assert exc.value.msg_key == "run_interaction_secret_field_rejected"


def test_audience_rejects_inactive_users_and_malformed_audience():
    user = SimpleNamespace(id=uuid4(), is_active=False)
    interaction = SimpleNamespace(
        audience={"user_ids": [str(user.id)], "roles": []},
        team_id=uuid4(),
    )
    # An inactive user loses access even when explicitly named.
    assert tool_interactions.audience_matches(interaction, user, {}) is False

    active = SimpleNamespace(id=uuid4(), is_active=True)
    malformed = SimpleNamespace(audience=["not", "a", "mapping"], team_id=None)
    assert tool_interactions.audience_matches(malformed, active, {}) is False


def test_utc_normalisation_treats_naive_values_as_utc(run_orm):
    assert tool_interactions._as_utc(None) is None
    naive = datetime(2026, 1, 2, 3, 4, 5)
    normalized = tool_interactions._as_utc(naive)
    assert normalized is not None and normalized.tzinfo is not None
    assert normalized.hour == 3

    # A pending row whose stored deadline already passed is expired by the
    # waiter without ever reporting it as answerable.
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        row = await _form_interaction(owner, team)
        await InteractionRequest.filter(id=row.id).update(
            expires_at=now_utc() - timedelta(seconds=1)
        )
        waited = await tool_interactions.wait_for_response(row.id, deadline_seconds=60)
        assert waited.status == InteractionStatus.EXPIRED

    run_orm(scenario)


def test_url_and_sampling_responses_reject_content(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        url_row = await tool_interactions.create_interaction(
            kind=InteractionKind.ELICITATION,
            actor=owner,
            team_id=team.id,
            payload={
                "mode": "url",
                "message": "Sign in",
                "url": "https://auth.example.com/start",
            },
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
        )
        with pytest.raises(BusinessError) as exc:
            await tool_interactions.respond_to_interaction(
                url_row.id,
                owner,
                action="accept",
                content={"name": "Ada"},
                idempotency_key="url-content1",
            )
        assert exc.value.code == ResponseCode.TOOL_INTERACTION_INVALID_RESPONSE

        # The key must be a string; numeric keys are rejected, not coerced.
        with pytest.raises(BusinessError) as key_exc:
            await tool_interactions.respond_to_interaction(
                url_row.id,
                owner,
                action="accept",
                idempotency_key=12345678,
            )
        assert key_exc.value.code == ResponseCode.TOOL_INTERACTION_INVALID_RESPONSE

        accepted = await tool_interactions.respond_to_interaction(
            url_row.id,
            owner,
            action="accept",
            idempotency_key="url-accept1",
        )
        assert accepted.status == InteractionStatus.RESPONDED
        assert tool_interactions.load_response_content(accepted) is None

    run_orm(scenario)


def test_response_to_expired_row_reports_expiry(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        row = await _form_interaction(owner, team)
        await InteractionRequest.filter(id=row.id).update(
            expires_at=now_utc() - timedelta(seconds=1)
        )

        with pytest.raises(BusinessError) as exc:
            await tool_interactions.respond_to_interaction(
                row.id,
                owner,
                action="accept",
                content={"name": "Ada"},
                idempotency_key="expired-key1",
            )
        assert exc.value.code == ResponseCode.TOOL_INTERACTION_EXPIRED
        assert (await InteractionRequest.get(id=row.id)).status == (
            InteractionStatus.EXPIRED
        )

    run_orm(scenario)


class _RacingUpdate:
    """Return 0 from the conditional update after a competing decision."""

    def __init__(self, queryset, *, row_id, key, digest, respond_with_user):
        self._queryset = queryset
        self._row_id = row_id
        self._key = key
        self._digest = digest
        self._user = respond_with_user

    def __getattr__(self, name):
        return getattr(self._queryset, name)

    async def update(self, **_kwargs):
        await InteractionRequest.filter(id=self._row_id).update(
            status=InteractionStatus.RESPONDED,
            outcome=InteractionOutcome.ACCEPT,
            responded_by_id=self._user.id,
            response_idempotency_key=self._key,
            response_digest=self._digest,
        )
        return 0


def _race_filter(real_filter, *, row_id, key, digest, user):
    def racing_filter(*args, **kwargs):
        queryset = real_filter(*args, **kwargs)
        if kwargs.get("status") == InteractionStatus.PENDING:
            return _RacingUpdate(
                queryset,
                row_id=row_id,
                key=key,
                digest=digest,
                respond_with_user=user,
            )
        return queryset

    return racing_filter


def test_losing_response_race_returns_identical_replay(run_orm, monkeypatch):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        row = await _form_interaction(owner, team)
        real_filter = InteractionRequest.filter
        monkeypatch.setattr(
            InteractionRequest,
            "filter",
            _race_filter(
                real_filter,
                row_id=row.id,
                key="race-key01",
                digest=tool_interactions._response_digest(
                    InteractionOutcome.ACCEPT, {"name": "Ada"}
                ),
                user=owner,
            ),
        )
        replayed = await tool_interactions.respond_to_interaction(
            row.id,
            owner,
            action="accept",
            content={"name": "Ada"},
            idempotency_key="race-key01",
        )
        assert replayed.status == InteractionStatus.RESPONDED
        assert replayed.response_idempotency_key == "race-key01"

    run_orm(scenario)


def test_losing_response_race_with_different_decision_is_not_pending(
    run_orm, monkeypatch
):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        row = await _form_interaction(owner, team)
        real_filter = InteractionRequest.filter
        monkeypatch.setattr(
            InteractionRequest,
            "filter",
            _race_filter(
                real_filter,
                row_id=row.id,
                key="someone-else",
                digest="different-digest",
                user=owner,
            ),
        )

        with pytest.raises(BusinessError) as exc:
            await tool_interactions.respond_to_interaction(
                row.id,
                owner,
                action="accept",
                content={"name": "Ada"},
                idempotency_key="race-key02",
            )
        assert exc.value.code == ResponseCode.TOOL_INTERACTION_NOT_PENDING

    run_orm(scenario)


def test_close_helpers_reject_pending_status_and_filter_by_run(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        run_id = uuid4()
        row = await _form_interaction(owner, team, run_kind="agent", run_id=run_id)

        with pytest.raises(ValueError):
            await tool_interactions.close_pending_for_session(
                "session-key", status=InteractionStatus.PENDING
            )
        with pytest.raises(ValueError):
            await tool_interactions.close_interaction(
                row.id, status=InteractionStatus.PENDING
            )

        closed = await tool_interactions.close_pending_for_run("agent", run_id)
        assert closed == 1

        rows, total = await tool_interactions.list_interactions_for_user(
            owner, status=InteractionStatus.CANCELLED, run_id=run_id
        )
        assert total == 1 and rows[0].id == row.id

    run_orm(scenario)
