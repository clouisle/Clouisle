"""Behavioral tests for tool connections against a real SQLite ORM schema.

Covers ownership/team isolation, explicit grants and revocation, secret
encryption at rest, field filtering and default selection. No mocks for the
storage layer: every assertion runs through Tortoise and the real models.
"""

from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from tortoise.context import TortoiseContext

from app.models.api_key import APIKey
from app.models.tool_connection import (
    ToolConnection,
    ToolConnectionScope,
)
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_connection import (
    ToolConnectionCreate,
    ToolConnectionUpdate,
)
from app.services.tool_connections import ToolConnectionService


@pytest.fixture
def run_orm(tmp_path):
    """Run one scenario against a fresh file-backed SQLite schema."""
    runner = asyncio.Runner()
    database_url = f"sqlite://{tmp_path / 'tool-connections.sqlite3'}"

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


async def _make_user(name: str, *, superuser: bool = False) -> User:
    return await User.create(
        id=uuid4(),
        username=name,
        email=f"{name}@example.com",
        hashed_password="not-used",
        is_superuser=superuser,
    )


async def _make_team(name: str, owner: User) -> Team:
    return await Team.create(id=uuid4(), name=name, owner_id=owner.id)


async def _join(team: Team, user: User, role: str = "member") -> TeamMember:
    return await TeamMember.create(
        id=uuid4(), team_id=team.id, user_id=user.id, role=role
    )


async def _make_api_key(owner: User, name: str = "entrypoint-key") -> APIKey:
    return await APIKey.create(
        id=uuid4(),
        name=name,
        key_prefix="clou_test",
        key_hash="hashed",
        user_id=owner.id,
    )


def _personal_payload(
    team_id: UUID,
    config: dict[str, str],
    *,
    name: str = "Personal search",
    is_default: bool = False,
) -> ToolConnectionCreate:
    return ToolConnectionCreate(
        team_id=team_id,
        builtin_tool_key="web_search",
        scope=ToolConnectionScope.USER,
        name=name,
        account_label="alice@example.com",
        config=config,
        is_default=is_default,
    )


def _expect_error(code: ResponseCode):
    return _ErrorExpectation(code)


class _ErrorExpectation:
    def __init__(self, code: ResponseCode):
        self._code = code
        self._context = None

    def __enter__(self):
        self._context = pytest.raises(BusinessError)
        return self._context.__enter__()

    def __exit__(self, exc_type, exc, tb):
        handled = self._context.__exit__(exc_type, exc, tb)
        if exc is not None and isinstance(exc, BusinessError):
            assert int(exc.code) == int(self._code), (exc.code, exc.msg_key)
        return handled


def test_personal_connection_is_owner_team_scoped_and_encrypted(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        bob = await _make_user("bob")
        team = await _make_team("team-one", alice)
        other_team = await _make_team("team-two", alice)
        await _join(team, alice, "owner")
        await _join(team, bob, "member")
        await _join(other_team, alice, "owner")

        created = await ToolConnectionService.create_connection(
            actor=alice,
            payload=_personal_payload(
                team.id, {"api_key": "tvly-super-secret"}, is_default=True
            ),
        )
        stored = await ToolConnection.get(id=created.id)
        assert stored.encrypted_config
        assert "tvly-super-secret" not in stored.encrypted_config
        assert stored.secret_fields == ["api_key"]
        assert stored.scope == ToolConnectionScope.USER
        assert stored.owner_user_id == alice.id
        assert stored.secret_version == 1

        dumped = created.model_dump()
        serialized = json.dumps(dumped, default=str)
        assert "tvly-super-secret" not in serialized
        assert "encrypted_config" not in dumped
        assert "config" not in dumped
        assert dumped["secret_fields"] == ["api_key"]
        assert dumped["account_label"] == "alice@example.com"

        resolved = await ToolConnectionService.resolve_connection(
            team_id=team.id, actor=alice, connection_id=created.id
        )
        assert resolved.secrets == {"api_key": "tvly-super-secret"}
        assert resolved.effective_user_id == alice.id
        assert resolved.owner_user_id == alice.id
        assert resolved.secret_version == 1

        with _expect_error(ResponseCode.TOOL_CONNECTION_ACCESS_DENIED):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=bob,
                connection_id=created.id,
                binding_trusted=False,
            )
        # When the connection was bound in trusted definition, bob can execute:
        trusted = await ToolConnectionService.resolve_connection(
            team_id=team.id, actor=bob, connection_id=created.id, binding_trusted=True
        )
        assert trusted.connection_id == created.id

        with _expect_error(ResponseCode.TOOL_CONNECTION_NOT_FOUND):
            await ToolConnectionService.resolve_connection(
                team_id=other_team.id, actor=alice, connection_id=created.id
            )

        with _expect_error(ResponseCode.TOOL_CONNECTION_NOT_FOUND):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=alice,
                connection_id=created.id,
                builtin_tool_key="calculator",
            )

        with _expect_error(ResponseCode.TOOL_CONNECTION_ACCESS_DENIED):
            await ToolConnectionService.get_connection(
                actor=bob, connection_id=created.id
            )
        with _expect_error(ResponseCode.TOOL_CONNECTION_ACCESS_DENIED):
            await ToolConnectionService.update_connection(
                actor=bob,
                connection_id=created.id,
                payload=ToolConnectionUpdate(name="hijacked"),
            )
        with _expect_error(ResponseCode.TOOL_CONNECTION_ACCESS_DENIED):
            await ToolConnectionService.revoke_connection(
                actor=bob, connection_id=created.id
            )

        default = await ToolConnectionService.get_default_connection(
            actor=alice,
            team_id=team.id,
            scope=ToolConnectionScope.USER,
            builtin_tool_key="web_search",
        )
        assert default.id == created.id

    run_orm(scenario)


def test_personal_binding_and_revocation(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        bob = await _make_user("bob")
        team = await _make_team("team-one", alice)
        other_team = await _make_team("team-two", alice)
        await _join(team, alice, "owner")
        await _join(team, bob, "member")
        await _join(other_team, alice, "owner")

        connection = await ToolConnectionService.create_connection(
            actor=alice,
            payload=_personal_payload(team.id, {"api_key": "delegated-secret"}),
        )

        # Untrusted client request of someone else's personal connection fails:
        with _expect_error(ResponseCode.TOOL_CONNECTION_ACCESS_DENIED):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=bob,
                connection_id=connection.id,
                binding_trusted=False,
            )
        # Server-bound trusted execution succeeds for team member:
        trusted = await ToolConnectionService.resolve_connection(
            team_id=team.id,
            actor=bob,
            connection_id=connection.id,
            binding_trusted=True,
        )
        assert trusted.secrets == {"api_key": "delegated-secret"}

        # Assert binding allowed checks:
        allowed = await ToolConnectionService.assert_binding_allowed(
            actor=alice,
            team_id=team.id,
            connection_id=connection.id,
            builtin_tool_key="web_search",
        )
        assert allowed.id == connection.id
        # Bob cannot bind Alice's personal connection:
        with _expect_error(ResponseCode.TOOL_CONNECTION_ACCESS_DENIED):
            await ToolConnectionService.assert_binding_allowed(
                actor=bob,
                team_id=team.id,
                connection_id=connection.id,
                builtin_tool_key="web_search",
            )
        with _expect_error(ResponseCode.TOOL_CONNECTION_INVALID):
            await ToolConnectionService.assert_tools_config_bindings_allowed(
                actor=alice,
                team_id=team.id,
                tools_config=[
                    {"type": "builtin", "name": "web_search", "connection_id": "bad"}
                ],
            )
        with _expect_error(ResponseCode.TOOL_CONNECTION_ACCESS_DENIED):
            await ToolConnectionService.assert_definition_bindings_allowed(
                actor=bob,
                team_id=team.id,
                definition={
                    "nodes": [
                        {
                            "type": "tool",
                            "data": {
                                "config": {
                                    "connectionId": str(connection.id),
                                    "toolType": "builtin",
                                    "toolName": "web_search",
                                }
                            },
                        }
                    ]
                },
            )
        # Revoking the connection invalidates resolution.
        await ToolConnectionService.revoke_connection(
            actor=alice, connection_id=connection.id
        )
        with _expect_error(ResponseCode.TOOL_CONNECTION_INACTIVE):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=bob,
                connection_id=connection.id,
                binding_trusted=True,
            )

    run_orm(scenario)


def test_field_filtering_defaults_team_and_site_scope(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        bob = await _make_user("bob")
        superuser = await _make_user("root", superuser=True)
        team = await _make_team("team-one", alice)
        other_team = await _make_team("team-two", alice)
        await _join(team, alice, "owner")
        await _join(team, bob, "member")
        await _join(other_team, alice, "owner")

        first = await ToolConnectionService.create_connection(
            actor=alice,
            payload=_personal_payload(
                team.id, {"api_key": "one", "region": "us"}, is_default=True
            ),
        )
        second = await ToolConnectionService.create_connection(
            actor=alice,
            payload=_personal_payload(
                team.id, {"api_key": "two", "region": "eu"}, is_default=True
            ),
        )

        first_reloaded = await ToolConnection.get(id=first.id)
        assert first_reloaded.is_default is False
        assert first_reloaded.default_slot is None
        second_reloaded = await ToolConnection.get(id=second.id)
        assert second_reloaded.is_default is True

        default = await ToolConnectionService.get_default_connection(
            actor=alice,
            team_id=team.id,
            scope=ToolConnectionScope.USER,
            builtin_tool_key="web_search",
        )
        assert default.id == second.id

        resolved = await ToolConnectionService.resolve_connection(
            team_id=team.id,
            actor=alice,
            use_default=True,
            scope=ToolConnectionScope.USER,
            builtin_tool_key="web_search",
            allowed_secret_fields={"api_key"},
        )
        assert resolved.connection_id == second.id
        assert resolved.secrets == {"api_key": "two"}

        with _expect_error(ResponseCode.TOOL_CONNECTION_INACTIVE):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=alice,
                connection_id=second.id,
                allowed_secret_fields={"api_key"},
                required_secret_fields={"api_key", "region"},
            )

        # Secret rotation bumps the version; name-only edits do not.
        rotated = await ToolConnectionService.update_connection(
            actor=alice,
            connection_id=second.id,
            payload=ToolConnectionUpdate(config_set={"api_key": "rotated"}),
        )
        assert rotated.secret_version == 2
        renamed = await ToolConnectionService.update_connection(
            actor=alice,
            connection_id=second.id,
            payload=ToolConnectionUpdate(name="Renamed"),
        )
        assert renamed.secret_version == 2

        with _expect_error(ResponseCode.TOOL_CONNECTION_INVALID):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=alice,
                connection_id=second.id,
                expected_secret_version=1,
            )

        removed = await ToolConnectionService.update_connection(
            actor=alice,
            connection_id=second.id,
            payload=ToolConnectionUpdate(config_remove=["api_key"]),
        )
        assert removed.secret_fields == ["region"]
        with _expect_error(ResponseCode.TOOL_CONNECTION_INACTIVE):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=alice,
                connection_id=second.id,
                required_secret_fields={"api_key"},
            )

        # Team-scoped connections need no grant, but stay team-bound.
        team_connection = await ToolConnectionService.create_connection(
            actor=alice,
            payload=ToolConnectionCreate(
                team_id=team.id,
                builtin_tool_key="web_search",
                scope=ToolConnectionScope.TEAM,
                name="Team account",
                config={"token": "team-secret"},
                is_default=True,
            ),
        )
        stored = await ToolConnection.get(id=team_connection.id)
        assert "team-secret" not in stored.encrypted_config
        member_resolved = await ToolConnectionService.resolve_connection(
            team_id=team.id, actor=bob, connection_id=team_connection.id
        )
        assert member_resolved.secrets == {"token": "team-secret"}
        assert member_resolved.owner_user_id is None
        assert member_resolved.effective_user_id is None

        with _expect_error(ResponseCode.TOOL_CONNECTION_NOT_FOUND):
            await ToolConnectionService.resolve_connection(
                team_id=other_team.id,
                actor=alice,
                connection_id=team_connection.id,
            )
        with _expect_error(ResponseCode.TEAM_ADMIN_REQUIRED):
            await ToolConnectionService.create_connection(
                actor=bob,
                payload=ToolConnectionCreate(
                    team_id=team.id,
                    builtin_tool_key="web_search",
                    scope=ToolConnectionScope.TEAM,
                    name="Not allowed",
                    config={"token": "nope"},
                ),
            )

        # Site connections are global and superuser-only to create.
        with _expect_error(ResponseCode.PERMISSION_DENIED):
            await ToolConnectionService.create_connection(
                actor=alice,
                payload=ToolConnectionCreate(
                    builtin_tool_key="web_search",
                    scope=ToolConnectionScope.SITE,
                    name="Site account",
                    config={"api_key": "site-secret"},
                ),
            )
        site_connection = await ToolConnectionService.create_connection(
            actor=superuser,
            payload=ToolConnectionCreate(
                builtin_tool_key="web_search",
                scope=ToolConnectionScope.SITE,
                name="Site account",
                config={"api_key": "site-secret"},
                is_default=True,
            ),
        )
        site_resolved = await ToolConnectionService.resolve_connection(
            team_id=team.id, actor=bob, connection_id=site_connection.id
        )
        assert site_resolved.secrets == {"api_key": "site-secret"}
        site_stored = await ToolConnection.get(id=site_connection.id)
        assert site_stored.team_id is None
        assert site_stored.default_slot == "site:builtin:web_search"

        # List filtering: members see team/site metadata but never another
        # user's personal connections.
        member_list = await ToolConnectionService.list_connections(
            actor=bob, team_id=team.id
        )
        member_ids = {item.id for item in member_list}
        assert first.id not in member_ids
        assert second.id not in member_ids
        assert team_connection.id in member_ids
        assert site_connection.id in member_ids
        owner_list = await ToolConnectionService.list_connections(
            actor=alice, team_id=team.id
        )
        owner_ids = {item.id for item in owner_list}
        assert {first.id, second.id} <= owner_ids

    run_orm(scenario)


def test_personal_default_and_sole_connection_selection_rules(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        team = await _make_team("team-one", alice)
        await _join(team, alice, "owner")

        sole = await ToolConnectionService.create_connection(
            actor=alice,
            payload=_personal_payload(team.id, {"api_key": "alice-sole"}),
        )
        # A sole personal connection is selected without an explicit default.
        selected = await ToolConnectionService.get_default_connection(
            actor=alice,
            team_id=team.id,
            scope=ToolConnectionScope.USER,
            builtin_tool_key="web_search",
        )
        assert selected.id == sole.id
        resolved = await ToolConnectionService.resolve_connection(
            team_id=team.id,
            actor=alice,
            use_default=True,
            scope=ToolConnectionScope.USER,
            builtin_tool_key="web_search",
            allowed_secret_fields={"api_key"},
        )
        assert resolved.connection_id == sole.id
        assert resolved.secrets == {"api_key": "alice-sole"}

        # Adding a second connection makes automatic selection ambiguous until
        # one of them becomes the default.
        second = await ToolConnectionService.create_connection(
            actor=alice,
            payload=_personal_payload(
                team.id, {"api_key": "alice-second"}, name="Second"
            ),
        )
        with pytest.raises(BusinessError) as ambiguous:
            await ToolConnectionService.get_default_connection(
                actor=alice,
                team_id=team.id,
                scope=ToolConnectionScope.USER,
                builtin_tool_key="web_search",
            )
        assert int(ambiguous.value.code) == int(
            ResponseCode.TOOL_CONNECTION_DEFAULT_REQUIRED
        )
        assert ambiguous.value.msg_key == "tool_connection_default_required"
        with _expect_error(ResponseCode.TOOL_CONNECTION_DEFAULT_REQUIRED):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=alice,
                use_default=True,
                scope=ToolConnectionScope.USER,
                builtin_tool_key="web_search",
            )

        # An explicit connection still works while automatic selection is
        # ambiguous.
        chosen = await ToolConnectionService.resolve_connection(
            team_id=team.id,
            actor=alice,
            connection_id=second.id,
            allowed_secret_fields={"api_key"},
        )
        assert chosen.secrets == {"api_key": "alice-second"}

        await ToolConnectionService.update_connection(
            actor=alice,
            connection_id=second.id,
            payload=ToolConnectionUpdate(is_default=True),
        )
        selected = await ToolConnectionService.get_default_connection(
            actor=alice,
            team_id=team.id,
            scope=ToolConnectionScope.USER,
            builtin_tool_key="web_search",
        )
        assert selected.id == second.id

        # An inactive default surfaces the inactive error instead of falling
        # back to the other personal account.
        await ToolConnectionService.update_connection(
            actor=alice,
            connection_id=second.id,
            payload=ToolConnectionUpdate(status="reauth_required"),
        )
        with _expect_error(ResponseCode.TOOL_CONNECTION_INACTIVE):
            await ToolConnectionService.get_default_connection(
                actor=alice,
                team_id=team.id,
                scope=ToolConnectionScope.USER,
                builtin_tool_key="web_search",
            )
        with _expect_error(ResponseCode.TOOL_CONNECTION_INACTIVE):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=alice,
                use_default=True,
                scope=ToolConnectionScope.USER,
                builtin_tool_key="web_search",
            )

    run_orm(scenario)


def test_automatic_personal_selection_never_crosses_identity(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        bob = await _make_user("bob")
        carol = await _make_user("carol")
        dave = await _make_user("dave")
        eve = await _make_user("eve")
        team = await _make_team("team-one", alice)
        other_team = await _make_team("team-two", alice)
        await _join(team, alice, "owner")
        for user in (bob, carol, dave, eve):
            await _join(team, user, "member")
        await _join(other_team, carol, "member")

        alice_connection = await ToolConnectionService.create_connection(
            actor=alice,
            payload=_personal_payload(team.id, {"api_key": "alice"}),
        )
        await ToolConnectionService.create_connection(
            actor=alice,
            payload=ToolConnectionCreate(
                team_id=team.id,
                builtin_tool_key="web_search",
                scope=ToolConnectionScope.TEAM,
                name="Team account",
                config={"api_key": "team"},
                is_default=True,
            ),
        )

        # Bob has no personal connection: neither another user's account nor
        # the team account is an acceptable fallback.
        with _expect_error(ResponseCode.TOOL_CONNECTION_REQUIRED):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=bob,
                use_default=True,
                scope=ToolConnectionScope.USER,
                builtin_tool_key="web_search",
            )
        with _expect_error(ResponseCode.TOOL_CONNECTION_REQUIRED):
            await ToolConnectionService.get_default_connection(
                actor=bob,
                team_id=team.id,
                scope=ToolConnectionScope.USER,
                builtin_tool_key="web_search",
            )

        # A personal account in another team is never selected.
        await ToolConnectionService.create_connection(
            actor=carol,
            payload=_personal_payload(
                other_team.id, {"api_key": "carol-other"}, name="Carol other team"
            ),
        )
        with _expect_error(ResponseCode.TOOL_CONNECTION_REQUIRED):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=carol,
                use_default=True,
                scope=ToolConnectionScope.USER,
                builtin_tool_key="web_search",
            )
        carol_connection = await ToolConnectionService.create_connection(
            actor=carol,
            payload=_personal_payload(team.id, {"api_key": "carol-team"}),
        )
        carol_resolved = await ToolConnectionService.resolve_connection(
            team_id=team.id,
            actor=carol,
            use_default=True,
            scope=ToolConnectionScope.USER,
            builtin_tool_key="web_search",
            allowed_secret_fields={"api_key"},
        )
        assert carol_resolved.connection_id == carol_connection.id
        assert carol_resolved.secrets == {"api_key": "carol-team"}
        alice_default = await ToolConnectionService.get_default_connection(
            actor=alice,
            team_id=team.id,
            scope=ToolConnectionScope.USER,
            builtin_tool_key="web_search",
        )
        assert alice_default.id == alice_connection.id
        with _expect_error(ResponseCode.TOOL_CONNECTION_REQUIRED):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=bob,
                use_default=True,
                scope=ToolConnectionScope.USER,
                builtin_tool_key="web_search",
            )

        # A connection for another service is not selected.
        await ToolConnectionService.create_connection(
            actor=dave,
            payload=ToolConnectionCreate(
                team_id=team.id,
                builtin_tool_key="calculator",
                scope=ToolConnectionScope.USER,
                name="Calculator",
                config={"api_key": "dave-calculator"},
            ),
        )
        with _expect_error(ResponseCode.TOOL_CONNECTION_REQUIRED):
            await ToolConnectionService.get_default_connection(
                actor=dave,
                team_id=team.id,
                scope=ToolConnectionScope.USER,
                builtin_tool_key="web_search",
            )

        # Revoked connections are excluded from the sole fallback.
        await ToolConnectionService.revoke_connection(
            actor=carol, connection_id=carol_connection.id
        )
        with _expect_error(ResponseCode.TOOL_CONNECTION_REQUIRED):
            await ToolConnectionService.get_default_connection(
                actor=carol,
                team_id=team.id,
                scope=ToolConnectionScope.USER,
                builtin_tool_key="web_search",
            )

        # A sole re-authentication-required connection reports the inactive
        # error rather than being silently skipped.
        eve_connection = await ToolConnectionService.create_connection(
            actor=eve,
            payload=_personal_payload(team.id, {"api_key": "eve"}),
        )
        await ToolConnectionService.update_connection(
            actor=eve,
            connection_id=eve_connection.id,
            payload=ToolConnectionUpdate(status="reauth_required"),
        )
        with _expect_error(ResponseCode.TOOL_CONNECTION_INACTIVE):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=eve,
                use_default=True,
                scope=ToolConnectionScope.USER,
                builtin_tool_key="web_search",
            )

    run_orm(scenario)


def test_scope_owner_team_invariants_reject_ambiguous_rows(run_orm):
    async def scenario():
        user = await _make_user("alice")
        team = await _make_team("team-one", user)

        with pytest.raises(ValueError):
            ToolConnection(
                id=uuid4(),
                scope=ToolConnectionScope.USER,
                team_id=team.id,
                builtin_tool_key="web_search",
            ).validate_invariants()

        with pytest.raises(ValueError):
            ToolConnection(
                id=uuid4(),
                scope=ToolConnectionScope.TEAM,
                team_id=team.id,
                owner_user_id=user.id,
                builtin_tool_key="web_search",
            ).validate_invariants()

        with pytest.raises(ValueError):
            ToolConnection(
                id=uuid4(),
                scope=ToolConnectionScope.SITE,
                team_id=team.id,
                builtin_tool_key="web_search",
            ).validate_invariants()

        with pytest.raises(ValueError):
            ToolConnection(
                id=uuid4(),
                scope=ToolConnectionScope.TEAM,
                team_id=team.id,
                tool_id=uuid4(),
                builtin_tool_key="web_search",
            ).validate_invariants()

        with pytest.raises(ValueError):
            ToolConnection(
                id=uuid4(),
                scope=ToolConnectionScope.TEAM,
                team_id=team.id,
                builtin_tool_key="web_search",
                is_default=True,
            ).validate_invariants()

    run_orm(scenario)
