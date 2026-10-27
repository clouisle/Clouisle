"""Authorization, identity and lifecycle edge paths for tool connections.

Complements ``test_tool_connections.py``: these scenarios target the branches
that decide *who* may read, manage, revoke or resolve a connection, plus the
fail-closed handling of malformed rows and secret containers. Every assertion
runs against real Tortoise models on a fresh SQLite schema; no storage mocks.
"""

from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from tortoise.context import TortoiseContext

from app.core.tool_secrets import encrypt_tool_secret
from app.models.tool_connection import (
    ToolConnection,
    ToolConnectionScope,
    ToolConnectionStatus,
)
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_connection import (
    ToolConnectionCreate,
    ToolConnectionUpdate,
)
from app.services.tool_connections import (
    ConnectionBinding,
    ResolvedConnection,
    ToolConnectionService,
)


@pytest.fixture
def run_orm(tmp_path):
    runner = asyncio.Runner()
    database_url = f"sqlite://{tmp_path / 'tool-connection-paths.sqlite3'}"

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


async def _personal(team: Team, owner: User, *, config=None) -> ToolConnection:
    created = await ToolConnectionService.create_connection(
        actor=owner,
        payload=_personal_payload(team.id, config or {"api_key": "owner-secret"}),
    )
    return await ToolConnection.get(id=created.id)


def test_actor_resolution_and_missing_team_fail_closed(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        team = await _make_team("team-one", alice)

        assert (await ToolConnectionService._resolve_actor(alice.id)).id == alice.id
        assert (await ToolConnectionService._resolve_actor(str(alice.id))).id == (
            alice.id
        )
        with _expect_error(ResponseCode.UNAUTHORIZED):
            await ToolConnectionService._resolve_actor(uuid4())
        with pytest.raises(TypeError):
            await ToolConnectionService._resolve_actor(42)

        with _expect_error(ResponseCode.TEAM_NOT_FOUND):
            await ToolConnectionService.list_connections(actor=alice, team_id=uuid4())
        # Owning a Team row is not membership.
        with _expect_error(ResponseCode.NOT_TEAM_MEMBER):
            await ToolConnectionService.list_connections(actor=alice, team_id=team.id)

        await _join(team, alice)
        with _expect_error(ResponseCode.NOT_FOUND):
            await ToolConnectionService.create_connection(
                actor=alice,
                payload=ToolConnectionCreate(
                    team_id=team.id,
                    tool_id=uuid4(),
                    scope=ToolConnectionScope.USER,
                    name="Missing tool",
                ),
            )

    run_orm(scenario)


def test_config_guards_reject_schema_bypassing_callers(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        team = await _make_team("team-one", alice)
        await _join(team, alice, "owner")

        def bypass(config, *, builtin_tool_key="web_search"):
            return ToolConnectionCreate.model_construct(
                team_id=team.id,
                scope=ToolConnectionScope.USER,
                name="Bypass",
                account_label=None,
                config=config,
                is_default=False,
                tool_id=None,
                builtin_tool_key=builtin_tool_key,
            )

        too_many = {f"field_{index}": "v" for index in range(51)}
        for config in (
            too_many,
            {"api_key": 123},
            {"api_key": ""},
            {"": "value"},
            {" ": "value"},
            {"api_key": "x" * 8193},
        ):
            with _expect_error(ResponseCode.TOOL_CONNECTION_INVALID):
                await ToolConnectionService.create_connection(
                    actor=alice, payload=bypass(config)
                )

        with _expect_error(ResponseCode.TOOL_CONNECTION_INVALID):
            await ToolConnectionService.create_connection(
                actor=alice, payload=bypass({}, builtin_tool_key=None)
            )

        # The same guards protect an unreadable stored payload.
        created = await _personal(team, alice)
        await ToolConnection.filter(id=created.id).update(encrypted_config="junk")
        with _expect_error(ResponseCode.TOOL_CONNECTION_SECRET_UNREADABLE):
            await ToolConnectionService.resolve_connection(
                team_id=team.id, actor=alice, connection_id=created.id
            )

        await ToolConnection.filter(id=created.id).update(
            encrypted_config=encrypt_tool_secret(json.dumps(["not", "a", "map"]))
        )
        with _expect_error(ResponseCode.TOOL_CONNECTION_SECRET_UNREADABLE):
            await ToolConnectionService.resolve_connection(
                team_id=team.id, actor=alice, connection_id=created.id
            )

    run_orm(scenario)


def test_declared_field_contracts_apply_on_create_and_update(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        team = await _make_team("team-one", alice)
        await _join(team, alice, "owner")

        with _expect_error(ResponseCode.TOOL_CONNECTION_INVALID):
            await ToolConnectionService.create_connection(
                actor=alice,
                payload=_personal_payload(team.id, {"other": "value"}),
                declared_secret_fields={"api_key"},
            )
        with _expect_error(ResponseCode.TOOL_CONNECTION_INVALID):
            await ToolConnectionService.create_connection(
                actor=alice,
                payload=_personal_payload(team.id, {"other": "value"}),
                required_secret_fields={"api_key"},
            )

        created = await ToolConnectionService.create_connection(
            actor=alice,
            payload=_personal_payload(team.id, {"api_key": "one", "region": "us"}),
            declared_secret_fields={"api_key", "region"},
            required_secret_fields={"api_key"},
        )

        with _expect_error(ResponseCode.TOOL_CONNECTION_INVALID):
            await ToolConnectionService.update_connection(
                actor=alice,
                connection_id=created.id,
                payload=ToolConnectionUpdate(config_set={"undeclared": "x"}),
                declared_secret_fields={"api_key", "region"},
                required_secret_fields={"api_key"},
            )
        with _expect_error(ResponseCode.TOOL_CONNECTION_INVALID):
            await ToolConnectionService.update_connection(
                actor=alice,
                connection_id=created.id,
                payload=ToolConnectionUpdate(config_remove=["api_key"]),
                declared_secret_fields={"api_key", "region"},
                required_secret_fields={"api_key"},
            )

        # A cleared error leaves the stored secret untouched.
        stored = await ToolConnection.get(id=created.id)
        assert stored.secret_version == 1
        assert "api_key" in ToolConnectionService._decrypt_config(stored)

    run_orm(scenario)


def test_update_version_status_and_account_label_rules(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        team = await _make_team("team-one", alice)
        await _join(team, alice, "owner")
        created = await _personal(team, alice)

        with _expect_error(ResponseCode.TOOL_CONNECTION_INVALID):
            await ToolConnectionService.update_connection(
                actor=alice,
                connection_id=created.id,
                payload=ToolConnectionUpdate(expected_secret_version=7),
            )

        # Account label is identity material: changing it bumps the version.
        relabelled = await ToolConnectionService.update_connection(
            actor=alice,
            connection_id=created.id,
            payload=ToolConnectionUpdate(account_label="alice+new@example.com"),
        )
        assert relabelled.secret_version == 2
        unchanged = await ToolConnectionService.update_connection(
            actor=alice,
            connection_id=created.id,
            payload=ToolConnectionUpdate(account_label="alice+new@example.com"),
        )
        assert unchanged.secret_version == 2

        # Re-setting the same secret material does not bump again.
        same = await ToolConnectionService.update_connection(
            actor=alice,
            connection_id=created.id,
            payload=ToolConnectionUpdate(config_set={"api_key": "owner-secret"}),
        )
        assert same.secret_version == 2

        inactive = await ToolConnectionService.update_connection(
            actor=alice,
            connection_id=created.id,
            payload=ToolConnectionUpdate(status=ToolConnectionStatus.REAUTH_REQUIRED),
        )
        assert inactive.status == "reauth_required"
        assert inactive.secret_version == 2
        with _expect_error(ResponseCode.TOOL_CONNECTION_INACTIVE):
            await ToolConnectionService.resolve_connection(
                team_id=team.id, actor=alice, connection_id=created.id
            )

        await ToolConnectionService.revoke_connection(
            actor=alice, connection_id=created.id
        )
        with _expect_error(ResponseCode.TOOL_CONNECTION_INACTIVE):
            await ToolConnectionService.update_connection(
                actor=alice,
                connection_id=created.id,
                payload=ToolConnectionUpdate(name="Too late"),
            )

    run_orm(scenario)


def test_read_authorization_matrix(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        bob = await _make_user("bob")
        outsider = await _make_user("outsider")
        root = await _make_user("root", superuser=True)
        team = await _make_team("team-one", alice)
        await _join(team, alice, "owner")
        await _join(team, bob, "member")

        personal = await _personal(team, alice)
        team_connection = await ToolConnectionService.create_connection(
            actor=alice,
            payload=ToolConnectionCreate(
                team_id=team.id,
                builtin_tool_key="web_search",
                scope=ToolConnectionScope.TEAM,
                name="Shared",
                config={"token": "team"},
            ),
        )
        site_connection = await ToolConnectionService.create_connection(
            actor=root,
            payload=ToolConnectionCreate(
                builtin_tool_key="web_search",
                scope=ToolConnectionScope.SITE,
                name="Site",
                config={"token": "site"},
            ),
        )

        # Team connections are readable by every member, not outsiders.
        assert (
            await ToolConnectionService.get_connection(
                actor=bob, connection_id=team_connection.id
            )
        ).id == team_connection.id
        with _expect_error(ResponseCode.NOT_TEAM_MEMBER):
            await ToolConnectionService.get_connection(
                actor=outsider, connection_id=team_connection.id
            )

        # Site connections need an explicit team context for non-superusers.
        with _expect_error(ResponseCode.TOOL_CONNECTION_ACCESS_DENIED):
            await ToolConnectionService.get_connection(
                actor=bob, connection_id=site_connection.id
            )
        assert (
            await ToolConnectionService.get_connection(
                actor=bob, connection_id=site_connection.id, team_id=team.id
            )
        ).id == site_connection.id
        with _expect_error(ResponseCode.NOT_TEAM_MEMBER):
            await ToolConnectionService.get_connection(
                actor=outsider,
                connection_id=site_connection.id,
                team_id=team.id,
            )
        assert (
            await ToolConnectionService.get_connection(
                actor=root, connection_id=site_connection.id
            )
        ).id == site_connection.id

        # A personal owner who left the team loses read access fail-closed.
        await TeamMember.filter(team_id=team.id, user_id=alice.id).delete()
        with _expect_error(ResponseCode.NOT_TEAM_MEMBER):
            await ToolConnectionService.get_connection(
                actor=alice, connection_id=personal.id
            )

        with _expect_error(ResponseCode.TOOL_CONNECTION_NOT_FOUND):
            await ToolConnectionService.get_connection(
                actor=root, connection_id=uuid4()
            )

    run_orm(scenario)


def test_manage_access_never_impersonates_a_personal_owner(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        bob = await _make_user("bob")
        root = await _make_user("root", superuser=True)
        team = await _make_team("team-one", alice)
        await _join(team, alice, "owner")
        await _join(team, bob, "member")

        personal = await _personal(team, alice)
        team_connection = await ToolConnectionService.create_connection(
            actor=alice,
            payload=ToolConnectionCreate(
                team_id=team.id,
                builtin_tool_key="web_search",
                scope=ToolConnectionScope.TEAM,
                name="Shared",
                config={"token": "team"},
            ),
        )
        site_connection = await ToolConnectionService.create_connection(
            actor=root,
            payload=ToolConnectionCreate(
                builtin_tool_key="web_search",
                scope=ToolConnectionScope.SITE,
                name="Site",
                config={"token": "site"},
            ),
        )

        with _expect_error(ResponseCode.TOOL_CONNECTION_ACCESS_DENIED):
            await ToolConnectionService.assert_manage_access(
                actor=bob, connection_id=personal.id
            )
        with _expect_error(ResponseCode.TOOL_CONNECTION_ACCESS_DENIED):
            await ToolConnectionService.assert_manage_access(
                actor=root, connection_id=personal.id
            )

        with _expect_error(ResponseCode.TEAM_ADMIN_REQUIRED):
            await ToolConnectionService.assert_manage_access(
                actor=bob, connection_id=team_connection.id
            )
        with _expect_error(ResponseCode.TEAM_ADMIN_REQUIRED):
            await ToolConnectionService.assert_manage_access(
                actor=bob,
                connection_id=team_connection.id,
                allow_superuser_override=True,
            )
        # Superusers bypass membership/admin checks for shared connections.
        assert (
            await ToolConnectionService.assert_manage_access(
                actor=root, connection_id=team_connection.id
            )
        ).id == team_connection.id

        with _expect_error(ResponseCode.PERMISSION_DENIED):
            await ToolConnectionService.assert_manage_access(
                actor=bob, connection_id=site_connection.id
            )
        assert (
            await ToolConnectionService.assert_manage_access(
                actor=root, connection_id=site_connection.id
            )
        ).id == site_connection.id

    run_orm(scenario)


def test_resolution_rejects_conflicting_identity_requests(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        bob = await _make_user("bob")
        other_team = await _make_team("team-two", alice)
        team = await _make_team("team-one", alice)
        await _join(team, alice)
        await _join(team, bob)
        await _join(other_team, alice)
        personal = await _personal(team, alice)

        with _expect_error(ResponseCode.TOOL_CONNECTION_INVALID):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=alice,
                connection_id=personal.id,
                use_default=True,
            )
        with _expect_error(ResponseCode.TOOL_CONNECTION_REQUIRED):
            await ToolConnectionService.resolve_connection(team_id=team.id, actor=alice)
        with _expect_error(ResponseCode.TOOL_CONNECTION_REQUIRED):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=alice,
                use_default=True,
                builtin_tool_key="web_search",
            )
        with _expect_error(ResponseCode.TOOL_CONNECTION_ACCESS_DENIED):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=alice,
                connection_id=personal.id,
                allowed_scopes={ToolConnectionScope.TEAM},
            )
        with _expect_error(ResponseCode.TOOL_CONNECTION_ACCESS_DENIED):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=alice,
                connection_id=personal.id,
                scope=ToolConnectionScope.TEAM,
            )
        with _expect_error(ResponseCode.TOOL_CONNECTION_INVALID):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=alice,
                connection_id=personal.id,
                expected_secret_version=9,
            )
        with _expect_error(ResponseCode.TOOL_CONNECTION_NOT_FOUND):
            await ToolConnectionService.resolve_connection(
                team_id=other_team.id,
                actor=alice,
                connection_id=personal.id,
            )
        with _expect_error(ResponseCode.TOOL_CONNECTION_NOT_FOUND):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=alice,
                connection_id=personal.id,
                builtin_tool_key="calculator",
            )

        # A malformed site row that carries a team is never silently used.
        corrupted = await ToolConnection.create(
            id=uuid4(),
            team_id=team.id,
            builtin_tool_key="web_search",
            scope=ToolConnectionScope.SITE,
            name="Corrupt site",
            status=ToolConnectionStatus.ACTIVE,
        )
        with _expect_error(ResponseCode.TOOL_CONNECTION_NOT_FOUND):
            await ToolConnectionService.resolve_connection(
                team_id=team.id, actor=alice, connection_id=corrupted.id
            )

    run_orm(scenario)


def test_trusted_binding_uses_owner_identity(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        bob = await _make_user("bob")
        team = await _make_team("team-one", alice)
        await _join(team, alice, "owner")
        await _join(team, bob, "member")
        personal = await _personal(team, alice)

        with _expect_error(ResponseCode.TOOL_CONNECTION_ACCESS_DENIED):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=bob,
                connection_id=personal.id,
                binding_trusted=False,
            )
        trusted = await ToolConnectionService.resolve_connection(
            team_id=team.id,
            actor=bob,
            connection_id=personal.id,
            binding_trusted=True,
        )
        assert trusted.effective_user_id == alice.id

        # Resolution binds the effective identity to the personal owner, never
        # to the caller executing the tool.
        assert trusted.owner_user_id == alice.id
        assert trusted.secrets == {"api_key": "owner-secret"}

        # Once the owner leaves the team, a previously trusted server binding
        # must stop impersonating that external identity for every other member.
        await TeamMember.filter(team_id=team.id, user_id=alice.id).delete()
        with _expect_error(ResponseCode.TOOL_CONNECTION_ACCESS_DENIED):
            await ToolConnectionService.resolve_connection(
                team_id=team.id,
                actor=bob,
                connection_id=personal.id,
                binding_trusted=True,
            )
        with _expect_error(ResponseCode.TOOL_CONNECTION_ACCESS_DENIED):
            await ToolConnectionService.get_binding_snapshot(
                team_id=team.id,
                actor=bob,
                connection_id=personal.id,
                binding_trusted=True,
            )

    run_orm(scenario)


def test_definition_binding_scans_skip_unrelated_nodes(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        bob = await _make_user("bob")
        team = await _make_team("team-one", alice)
        await _join(team, alice, "owner")
        await _join(team, bob, "member")
        personal = await _personal(team, alice)

        await ToolConnectionService.assert_tools_config_bindings_allowed(
            actor=alice, team_id=team.id, tools_config=None
        )
        await ToolConnectionService.assert_tools_config_bindings_allowed(
            actor=alice,
            team_id=team.id,
            tools_config=[None, "not-a-dict", {}, {"connection_id": ""}],
        )

        with _expect_error(ResponseCode.TOOL_CONNECTION_INVALID):
            await ToolConnectionService.assert_tools_config_bindings_allowed(
                actor=alice,
                team_id=team.id,
                tools_config=[
                    {"connection_id": str(personal.id), "tool_id": "not-a-uuid"}
                ],
            )

        await ToolConnectionService.assert_definition_bindings_allowed(
            actor=alice, team_id=team.id, definition=None
        )
        await ToolConnectionService.assert_definition_bindings_allowed(
            actor=alice,
            team_id=team.id,
            definition={
                "nodes": [
                    None,
                    {"type": "agent", "data": {"config": {"connectionId": "x"}}},
                    {"type": "tool", "data": {"config": "not-a-dict"}},
                    {"type": "tool", "data": {"config": {}}},
                ]
            },
        )

        # Snake_case workflow keys resolve the same authority as camelCase.
        await ToolConnectionService.assert_definition_bindings_allowed(
            actor=alice,
            team_id=team.id,
            definition={
                "nodes": [
                    {
                        "type": "tool",
                        "data": {
                            "config": {
                                "connection_id": str(personal.id),
                                "toolType": "builtin",
                                "tool_name": "web_search",
                            }
                        },
                    }
                ]
            },
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
                                    "connection_id": str(personal.id),
                                    "toolType": "builtin",
                                    "tool_name": "web_search",
                                }
                            },
                        }
                    ]
                },
            )

        revoked = await _personal(team, alice, config={"api_key": "revoked"})
        await ToolConnectionService.revoke_connection(
            actor=alice, connection_id=revoked.id
        )
        with _expect_error(ResponseCode.TOOL_CONNECTION_INACTIVE):
            await ToolConnectionService.assert_binding_allowed(
                actor=alice,
                team_id=team.id,
                connection_id=revoked.id,
                builtin_tool_key="web_search",
            )

    run_orm(scenario)


def test_binding_snapshots_are_secret_free_and_status_aware(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        team = await _make_team("team-one", alice)
        await _join(team, alice)
        personal = await _personal(team, alice, config={"api_key": "top-secret"})

        snapshot = await ToolConnectionService.get_binding_snapshot(
            team_id=team.id, actor=alice, connection_id=personal.id
        )
        assert isinstance(snapshot, ConnectionBinding)
        assert snapshot.connection_id == personal.id
        assert snapshot.effective_user_id == alice.id
        assert snapshot.is_active is True
        assert not hasattr(snapshot, "secrets")
        assert "top-secret" not in repr(snapshot)

        resolved = await ToolConnectionService.resolve_connection(
            team_id=team.id, actor=alice, connection_id=personal.id
        )
        assert isinstance(resolved, ResolvedConnection)
        degraded = ToolConnectionService.binding_from_resolved(
            ResolvedConnection(
                connection_id=resolved.connection_id,
                team_id=resolved.team_id,
                scope=resolved.scope,
                owner_user_id=resolved.owner_user_id,
                effective_user_id=resolved.effective_user_id,
                tool_id=resolved.tool_id,
                builtin_tool_key=resolved.builtin_tool_key,
                account_label=resolved.account_label,
                status=ToolConnectionStatus.REAUTH_REQUIRED,
                secret_version=resolved.secret_version,
                secrets={"api_key": "top-secret"},
            )
        )
        assert degraded.is_active is False
        assert "top-secret" not in repr(degraded)

        await ToolConnectionService.revoke_connection(
            actor=alice, connection_id=personal.id
        )
        with _expect_error(ResponseCode.TOOL_CONNECTION_INACTIVE):
            await ToolConnectionService.get_binding_snapshot(
                team_id=team.id, actor=alice, connection_id=personal.id
            )

    run_orm(scenario)


def test_listing_and_default_selection_scope_filters(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        bob = await _make_user("bob")
        outsider = await _make_user("outsider")
        root = await _make_user("root", superuser=True)
        team = await _make_team("team-one", alice)
        await _join(team, alice, "owner")
        await _join(team, bob, "member")

        personal = await _personal(team, alice, config={"api_key": "alice"})
        revoked = await _personal(team, alice, config={"api_key": "old"})
        await ToolConnectionService.revoke_connection(
            actor=alice, connection_id=revoked.id
        )
        team_connection = await ToolConnectionService.create_connection(
            actor=alice,
            payload=ToolConnectionCreate(
                team_id=team.id,
                builtin_tool_key="web_search",
                scope=ToolConnectionScope.TEAM,
                name="Shared",
                config={"token": "team"},
                is_default=True,
            ),
        )
        site_connection = await ToolConnectionService.create_connection(
            actor=root,
            payload=ToolConnectionCreate(
                builtin_tool_key="web_search",
                scope=ToolConnectionScope.SITE,
                name="Site",
                config={"token": "site"},
                is_default=True,
            ),
        )

        visible = await ToolConnectionService.list_connections(
            actor=alice, team_id=team.id
        )
        visible_ids = {item.id for item in visible}
        assert personal.id in visible_ids
        assert revoked.id not in visible_ids
        assert {team_connection.id, site_connection.id} <= visible_ids

        with_revoked = await ToolConnectionService.list_connections(
            actor=alice, team_id=team.id, include_revoked=True
        )
        assert revoked.id in {item.id for item in with_revoked}

        without_site = await ToolConnectionService.list_connections(
            actor=alice, team_id=team.id, include_site=False
        )
        assert site_connection.id not in {item.id for item in without_site}

        filtered = await ToolConnectionService.list_connections(
            actor=alice, team_id=team.id, builtin_tool_key="calculator"
        )
        assert filtered == []

        # Team default is usable by members but not outsiders.
        team_default = await ToolConnectionService.get_default_connection(
            actor=bob,
            team_id=team.id,
            scope=ToolConnectionScope.TEAM,
            builtin_tool_key="web_search",
        )
        assert team_default.id == team_connection.id
        with _expect_error(ResponseCode.NOT_TEAM_MEMBER):
            await ToolConnectionService.get_default_connection(
                actor=outsider,
                team_id=team.id,
                scope=ToolConnectionScope.TEAM,
                builtin_tool_key="web_search",
            )

        site_default = await ToolConnectionService.get_default_connection(
            actor=bob,
            team_id=team.id,
            scope=ToolConnectionScope.SITE,
            builtin_tool_key="web_search",
        )
        assert site_default.id == site_connection.id

        with _expect_error(ResponseCode.TOOL_CONNECTION_INVALID):
            await ToolConnectionService.get_default_connection(
                actor=bob,
                team_id=team.id,
                scope=ToolConnectionScope.USER,
            )

        # The materialized-tool identity is tried before the builtin key, but a
        # connection stored under the builtin key is still found.
        fallback = await ToolConnectionService.get_default_connection(
            actor=bob,
            team_id=team.id,
            scope=ToolConnectionScope.TEAM,
            tool_id=uuid4(),
            builtin_tool_key="web_search",
        )
        assert fallback.id == team_connection.id

    run_orm(scenario)


def test_revocation_is_idempotent_and_scope_specific(run_orm):
    async def scenario():
        alice = await _make_user("alice")
        root = await _make_user("root", superuser=True)
        team = await _make_team("team-one", alice)
        await _join(team, alice, "owner")
        personal = await _personal(team, alice)
        await ToolConnectionService.update_connection(
            actor=alice,
            connection_id=personal.id,
            payload=ToolConnectionUpdate(is_default=True),
        )

        # Superusers cannot revoke another user's personal delegation.
        with _expect_error(ResponseCode.TOOL_CONNECTION_ACCESS_DENIED):
            await ToolConnectionService.revoke_connection(
                actor=root, connection_id=personal.id
            )

        first = await ToolConnectionService.revoke_connection(
            actor=alice, connection_id=personal.id, reason="user request"
        )
        assert first.status == "revoked"
        stored = await ToolConnection.get(id=personal.id)
        assert stored.is_default is False
        assert stored.default_slot is None

        second = await ToolConnectionService.revoke_connection(
            actor=alice, connection_id=personal.id
        )
        assert second.status == "revoked"

        team_connection = await ToolConnectionService.create_connection(
            actor=alice,
            payload=ToolConnectionCreate(
                team_id=team.id,
                builtin_tool_key="web_search",
                scope=ToolConnectionScope.TEAM,
                name="Shared",
                config={"token": "team"},
            ),
        )
        # Superuser override applies to shared (team) connections.
        revoked = await ToolConnectionService.revoke_connection(
            actor=root, connection_id=team_connection.id
        )
        assert revoked.status == "revoked"

        with _expect_error(ResponseCode.TOOL_CONNECTION_NOT_FOUND):
            await ToolConnectionService.revoke_connection(
                actor=root, connection_id=uuid4()
            )

    run_orm(scenario)
