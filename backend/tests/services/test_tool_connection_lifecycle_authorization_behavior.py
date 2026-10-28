"""Lifecycle and authorization behavior for tool connections on real ORM rows.

Complements the existing connection suites with consumer-visible transitions
they do not exercise: schema-bypassing callers, corrupt scope/owner rows,
clearing the default slot, required-secret resolution and foreign personal
bindings. Tortoise models and the service layer run unmodified; only the
external world is absent.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.models.tool_connection import (
    ToolConnection,
    ToolConnectionScope,
    ToolConnectionStatus,
)
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_connection import ToolConnectionCreate, ToolConnectionUpdate
from app.services.tool_connections import ToolConnectionService

pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def _database():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        yield
    finally:
        await Tortoise.close_connections()


async def _user(label: str) -> User:
    suffix = uuid4().hex[:8]
    return await User.create(
        id=uuid4(),
        username=f"{label}_{suffix}",
        email=f"{label}_{suffix}@connection.test",
        hashed_password="x",
    )


async def _team(owner: User, *, members: tuple[User, ...] = ()) -> Team:
    team = await Team.create(
        id=uuid4(), name=f"team_{uuid4().hex[:8]}", owner_id=owner.id
    )
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    for member in members:
        await TeamMember.create(
            id=uuid4(), team_id=team.id, user_id=member.id, role="member"
        )
    return team


def _expect_business_error(
    exc_info: pytest.ExceptionInfo[BusinessError],
    code: ResponseCode,
    msg_key: str,
    status_code: int,
) -> None:
    error = exc_info.value
    assert int(error.code) == int(code), (error.code, error.msg_key)
    assert error.msg_key == msg_key
    assert error.status_code == status_code


async def _personal(
    team: Team,
    owner: User,
    *,
    config: dict[str, str] | None = None,
    is_default: bool = False,
):
    return await ToolConnectionService.create_connection(
        actor=owner,
        payload=ToolConnectionCreate(
            team_id=team.id,
            builtin_tool_key="web_search",
            scope=ToolConnectionScope.USER,
            name=f"Personal {uuid4().hex[:6]}",
            account_label="owner@example.test",
            config=config if config is not None else {"api_key": "secret"},
            is_default=is_default,
        ),
    )


async def test_update_clears_default_and_rejects_status_revoke_bypass():
    async with _database():
        alice = await _user("alice")
        team = await _team(alice)
        created = await _personal(team, alice, is_default=True)

        stored = await ToolConnection.get(id=created.id)
        assert stored.is_default is True
        assert stored.default_slot == (f"user:{team.id}:{alice.id}:builtin:web_search")

        cleared = await ToolConnectionService.update_connection(
            actor=alice,
            connection_id=created.id,
            payload=ToolConnectionUpdate(is_default=False),
        )
        assert cleared.is_default is False
        stored = await ToolConnection.get(id=created.id)
        assert stored.default_slot is None

        # Callers that bypass the update schema must still use revoke_connection
        # instead of flipping an existing row into a terminal state.
        bypass = ToolConnectionUpdate.model_construct(
            status=ToolConnectionStatus.REVOKED
        )
        with pytest.raises(BusinessError) as rejected:
            await ToolConnectionService.update_connection(
                actor=alice, connection_id=created.id, payload=bypass
            )
        _expect_business_error(
            rejected,
            ResponseCode.TOOL_CONNECTION_INVALID,
            "tool_connection_invalid",
            400,
        )
        stored = await ToolConnection.get(id=created.id)
        assert stored.status == ToolConnectionStatus.ACTIVE
        assert stored.is_default is False


async def test_resolution_enforces_declared_secret_fields():
    async with _database():
        alice = await _user("alice")
        team = await _team(alice)
        created = await _personal(team, alice, config={"api_key": "present"})

        resolved = await ToolConnectionService.resolve_connection(
            team_id=team.id,
            actor=alice,
            connection_id=created.id,
            required_secret_fields={"api_key"},
        )
        assert resolved.connection_id == created.id
        assert resolved.secrets == {"api_key": "present"}

        with pytest.raises(BusinessError) as unreadable:
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=alice,
                connection_id=created.id,
                required_secret_fields={"api_key", "region"},
            )
        _expect_business_error(
            unreadable,
            ResponseCode.TOOL_CONNECTION_INACTIVE,
            "tool_connection_secret_unreadable",
            409,
        )


async def test_binding_allows_shared_connection_but_rejects_foreign_personal():
    async with _database():
        alice = await _user("alice")
        bob = await _user("bob")
        team = await _team(alice, members=(bob,))

        shared = await ToolConnectionService.create_connection(
            actor=alice,
            payload=ToolConnectionCreate(
                team_id=team.id,
                builtin_tool_key="web_search",
                scope=ToolConnectionScope.TEAM,
                name="Shared search",
                config={"token": "team"},
            ),
        )
        bound = await ToolConnectionService.assert_binding_allowed(
            actor=bob, team_id=team.id, connection_id=shared.id
        )
        assert bound.id == shared.id

        personal = await _personal(team, alice)
        with pytest.raises(BusinessError) as foreign:
            await ToolConnectionService.assert_binding_allowed(
                actor=bob, team_id=team.id, connection_id=personal.id
            )
        _expect_business_error(
            foreign,
            ResponseCode.TOOL_CONNECTION_ACCESS_DENIED,
            "tool_connection_access_denied",
            403,
        )

        await ToolConnectionService.revoke_connection(
            actor=alice, connection_id=shared.id
        )
        with pytest.raises(BusinessError) as revoked:
            await ToolConnectionService.assert_binding_allowed(
                actor=bob, team_id=team.id, connection_id=shared.id
            )
        _expect_business_error(
            revoked,
            ResponseCode.TOOL_CONNECTION_INACTIVE,
            "tool_connection_inactive",
            409,
        )


async def test_corrupt_scope_rows_fail_closed_and_stay_owner_only():
    async with _database():
        alice = await _user("alice")
        await _team(alice)

        # Legacy rows written before scope invariants existed may carry a
        # team-scoped identity without a team. Shared rows must fail closed.
        orphan_shared = await ToolConnection.create(
            id=uuid4(),
            team_id=None,
            scope=ToolConnectionScope.TEAM,
            builtin_tool_key="web_search",
            owner_user_id=None,
            name="Legacy shared without team",
            status=ToolConnectionStatus.ACTIVE,
        )
        for operation in (
            ToolConnectionService.assert_manage_access,
            ToolConnectionService.get_connection,
        ):
            with pytest.raises(BusinessError) as invalid:
                await operation(actor=alice, connection_id=orphan_shared.id)
            _expect_business_error(
                invalid,
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_invalid",
                400,
            )

        # A personal row without a team has no membership to re-check; it must
        # still be reachable only by its owner.
        orphan_personal = await ToolConnection.create(
            id=uuid4(),
            team_id=None,
            scope=ToolConnectionScope.USER,
            builtin_tool_key="web_search",
            owner_user_id=alice.id,
            name="Legacy personal without team",
            status=ToolConnectionStatus.ACTIVE,
        )
        managed = await ToolConnectionService.assert_manage_access(
            actor=alice, connection_id=orphan_personal.id
        )
        assert managed.id == orphan_personal.id
        read = await ToolConnectionService.get_connection(
            actor=alice, connection_id=orphan_personal.id
        )
        assert read.id == orphan_personal.id


async def test_trusted_binding_of_ownerless_personal_row_fails_closed():
    async with _database():
        alice = await _user("alice")
        bob = await _user("bob")
        team = await _team(alice, members=(bob,))

        ownerless = await ToolConnection.create(
            id=uuid4(),
            team_id=team.id,
            scope=ToolConnectionScope.USER,
            builtin_tool_key="web_search",
            owner_user_id=None,
            name="Ownerless personal row",
            status=ToolConnectionStatus.ACTIVE,
        )

        with pytest.raises(BusinessError) as orphaned:
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=bob,
                connection_id=ownerless.id,
                binding_trusted=True,
            )
        _expect_business_error(
            orphaned,
            ResponseCode.TOOL_CONNECTION_ACCESS_DENIED,
            "tool_connection_access_denied",
            403,
        )


async def test_default_selection_requires_shared_default_and_unions_personal():
    async with _database():
        alice = await _user("alice")
        team = await _team(alice)

        # Shared scopes have no sole-account fallback: an unconfigured team
        # default is an explicit configuration error.
        with pytest.raises(BusinessError) as missing_team_default:
            await ToolConnectionService.get_default_connection(
                actor=alice,
                team_id=team.id,
                scope=ToolConnectionScope.TEAM,
                builtin_tool_key="web_search",
            )
        _expect_business_error(
            missing_team_default,
            ResponseCode.TOOL_CONNECTION_REQUIRED,
            "tool_connection_required",
            409,
        )

        # Personal selection accepts either identity for a materialized tool:
        # the row may be stored under tool_id or the builtin key.
        personal = await _personal(team, alice)
        selected = await ToolConnectionService.get_default_connection(
            actor=alice,
            team_id=team.id,
            scope=ToolConnectionScope.USER,
            tool_id=uuid4(),
            builtin_tool_key="web_search",
        )
        assert selected.id == personal.id


async def test_schema_bypassing_create_requires_team_and_mapping_config():
    async with _database():
        alice = await _user("alice")
        team = await _team(alice)

        for scope in (ToolConnectionScope.TEAM, ToolConnectionScope.USER):
            payload = ToolConnectionCreate.model_construct(
                team_id=None,
                scope=scope,
                name="Bypassed team",
                account_label=None,
                config={},
                is_default=False,
                tool_id=None,
                builtin_tool_key="web_search",
            )
            with pytest.raises(BusinessError) as missing_team:
                await ToolConnectionService.create_connection(
                    actor=alice, payload=payload
                )
            _expect_business_error(
                missing_team,
                ResponseCode.TOOL_CONNECTION_INVALID,
                "tool_connection_invalid",
                400,
            )

        non_mapping = ToolConnectionCreate.model_construct(
            team_id=team.id,
            scope=ToolConnectionScope.USER,
            name="Bypassed config",
            account_label=None,
            config=["api_key"],
            is_default=False,
            tool_id=None,
            builtin_tool_key="web_search",
        )
        with pytest.raises(BusinessError) as invalid_config:
            await ToolConnectionService.create_connection(
                actor=alice, payload=non_mapping
            )
        _expect_business_error(
            invalid_config,
            ResponseCode.TOOL_CONNECTION_INVALID,
            "tool_connection_invalid",
            400,
        )
        assert await ToolConnection.filter(name__startswith="Bypassed").count() == 0
