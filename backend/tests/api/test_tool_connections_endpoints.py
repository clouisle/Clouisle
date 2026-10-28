"""Authorization and lifecycle tests for the tool-connection HTTP surface.

These tests call the route handlers against a real SQLite schema. They focus
on the consumer-visible security contract of the endpoint layer: which team
may use which tool definition, who may see or change a connection, and how
secret-field declarations gate writes. The service layer is deliberately not
mocked, so the declared-field plumbing is verified end to end.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tortoise.context import TortoiseContext

from app.api.v1.endpoints import tool_connections
from app.models.tool import (
    Tool,
    ToolShare,
    ToolSharePermission,
    ToolType,
    ToolVisibility,
)
from app.models.tool_connection import ToolConnectionScope, ToolConnectionStatus
from app.models.user import Permission, Role, Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_connection import (
    ToolConnectionCreate,
    ToolConnectionForToolCreate,
    ToolConnectionUpdate,
)


@pytest.fixture
def conn_orm(tmp_path):
    runner = asyncio.Runner()
    database_url = f"sqlite://{tmp_path / 'tool-connections-api.sqlite3'}"

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


async def _user(label: str, *, superuser: bool = False) -> User:
    suffix = uuid4().hex[:8]
    return await User.create(
        id=uuid4(),
        username=f"{label}_{suffix}",
        email=f"{label}_{suffix}@tool-connections-api.test",
        hashed_password="x",
        is_superuser=superuser,
    )


async def _team(label: str) -> Team:
    return await Team.create(id=uuid4(), name=f"{label}_{uuid4().hex[:8]}")


async def _member(team: Team, user: User, role: str = "member") -> None:
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=user.id, role=role)


async def _grant_team_read(user: User) -> User:
    permission = await Permission.create(id=uuid4(), scope="team", code="team:read")
    role = await Role.create(id=uuid4(), name=f"reader_{uuid4().hex[:8]}")
    await role.permissions.add(permission)
    await user.roles.add(role)
    return await User.filter(id=user.id).prefetch_related("roles__permissions").first()


async def _tool(
    team: Team,
    creator: User,
    *,
    visibility: ToolVisibility = ToolVisibility.TEAM,
    connection_fields: list | None = None,
) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"tool_{uuid4().hex[:8]}",
        display_name="Connection tool",
        description="tool connection endpoint test",
        type=ToolType.MCP,
        visibility=visibility,
        created_by_id=creator.id,
        connection_fields=connection_fields or [],
        mcp_config={"transport": "sse", "url": "https://mcp.example/sse"},
    )


async def _share(tool: Tool, team: Team, actor: User) -> None:
    await ToolShare.create(
        id=uuid4(),
        tool_id=tool.id,
        shared_with_team_id=team.id,
        permission=ToolSharePermission.READ_EXECUTE,
        shared_by_id=actor.id,
    )


def test_tool_scoped_listing_enforces_creator_only_private_tools(conn_orm):
    async def scenario():
        owner = await _user("owner")
        member = await _grant_team_read(await _user("member"))
        team = await _team("same")
        await _member(team, owner, "owner")
        await _member(team, member)

        team_tool = await _tool(team, owner)
        listed = await tool_connections.list_tool_connections(
            team_tool.id, team.id, True, False, current_user=member
        )
        assert listed["code"] == ResponseCode.SUCCESS
        assert listed["data"] == []

        private_tool = await _tool(team, owner, visibility=ToolVisibility.PRIVATE)
        # Team membership and team:read are not enough for a private tool.
        with pytest.raises(BusinessError) as denied:
            await tool_connections.list_tool_connections(
                private_tool.id, team.id, True, False, current_user=member
            )
        assert denied.value.msg_key == "tool_access_denied"
        assert denied.value.status_code == 403

        allowed = await tool_connections.list_tool_connections(
            private_tool.id, team.id, True, False, current_user=owner
        )
        assert allowed["data"] == []

        with pytest.raises(BusinessError) as missing:
            await tool_connections.list_tool_connections(
                uuid4(), team.id, True, False, current_user=owner
            )
        assert missing.value.code == ResponseCode.NOT_FOUND
        assert missing.value.msg_key == "tool_not_found"

    conn_orm(scenario)


def test_cross_team_access_requires_membership_private_block_and_share(conn_orm):
    async def scenario():
        owner = await _user("owner")
        consumer = await _grant_team_read(await _user("consumer"))
        outsider = await _user("outsider")
        owning_team = await _team("owning")
        consuming_team = await _team("consuming")
        await _member(owning_team, owner, "owner")
        await _member(consuming_team, consumer)
        await _member(owning_team, outsider, "owner")

        shared_tool = await _tool(owning_team, owner)
        private_tool = await _tool(
            owning_team, owner, visibility=ToolVisibility.PRIVATE
        )

        # The consuming team must be one the caller actually belongs to.
        with pytest.raises(BusinessError) as not_member:
            await tool_connections.list_tool_connections(
                shared_tool.id, consuming_team.id, True, False, current_user=outsider
            )
        assert not_member.value.msg_key == "not_team_member"

        # Membership alone does not grant access to another team's definition.
        with pytest.raises(BusinessError) as unshared:
            await tool_connections.list_tool_connections(
                shared_tool.id, consuming_team.id, True, False, current_user=consumer
            )
        assert unshared.value.msg_key == "tool_access_denied"

        await _share(shared_tool, consuming_team, owner)
        granted = await tool_connections.list_tool_connections(
            shared_tool.id, consuming_team.id, True, False, current_user=consumer
        )
        assert granted["data"] == []

        # A PRIVATE definition is never usable cross-team, even with a share.
        await _share(private_tool, consuming_team, owner)
        with pytest.raises(BusinessError) as private_denied:
            await tool_connections.list_tool_connections(
                private_tool.id, consuming_team.id, True, False, current_user=consumer
            )
        assert private_denied.value.msg_key == "tool_access_denied"

    conn_orm(scenario)


def test_generic_listing_validates_tool_and_builtin_identity(conn_orm):
    async def scenario():
        actor = await _user("actor", superuser=True)
        team = await _team("generic")
        tool = await _tool(team, actor)

        by_tool = await tool_connections.list_connections(
            team.id,
            tool_id=tool.id,
            builtin_tool_key=None,
            current_user=actor,
        )
        assert by_tool["data"] == []

        by_builtin = await tool_connections.list_connections(
            team.id, builtin_tool_key="calculate", current_user=actor
        )
        assert by_builtin["data"] == []

        with pytest.raises(BusinessError) as unknown_tool:
            await tool_connections.list_connections(
                team.id,
                tool_id=uuid4(),
                builtin_tool_key=None,
                current_user=actor,
            )
        assert unknown_tool.value.msg_key == "tool_not_found"

        # Unknown builtin keys run registration once, then still fail closed.
        with pytest.raises(BusinessError) as unknown_builtin:
            await tool_connections.list_connections(
                team.id, builtin_tool_key="not_a_real_builtin", current_user=actor
            )
        assert unknown_builtin.value.msg_key == "tool_not_found"
        assert unknown_builtin.value.status_code == 404

    conn_orm(scenario)


def test_tool_scoped_create_enforces_site_superuser_and_declared_fields(conn_orm):
    async def scenario():
        owner = await _grant_team_read(await _user("owner"))
        admin = await _user("site-admin", superuser=True)
        team = await _team("create")
        await _member(team, owner, "owner")

        tool = await _tool(
            team,
            owner,
            connection_fields=[
                {"name": "token", "label": "Token", "required": True, "secret": True},
                {"label": "missing name"},
                "not-a-mapping",
            ],
        )

        with pytest.raises(BusinessError) as missing_required:
            await tool_connections.create_tool_connection(
                tool.id,
                ToolConnectionForToolCreate(
                    team_id=team.id,
                    scope=ToolConnectionScope.TEAM,
                    name="team account",
                    config={},
                ),
                current_user=owner,
            )
        assert missing_required.value.msg_key == "tool_connection_invalid"

        with pytest.raises(BusinessError) as undeclared:
            await tool_connections.create_tool_connection(
                tool.id,
                ToolConnectionForToolCreate(
                    team_id=team.id,
                    scope=ToolConnectionScope.TEAM,
                    name="team account",
                    config={"token": "secret", "extra": "nope"},
                ),
                current_user=owner,
            )
        assert undeclared.value.msg_key == "tool_connection_invalid"

        created = await tool_connections.create_tool_connection(
            tool.id,
            ToolConnectionForToolCreate(
                team_id=team.id,
                scope=ToolConnectionScope.TEAM,
                name="team account",
                config={"token": "super-secret"},
                is_default=True,
            ),
            current_user=owner,
        )
        assert created["data"].secret_fields == ["token"]
        assert created["data"].is_default is True
        assert "super-secret" not in str(created["data"].model_dump())

        with pytest.raises(BusinessError) as site_denied:
            await tool_connections.create_tool_connection(
                tool.id,
                ToolConnectionForToolCreate(
                    scope=ToolConnectionScope.SITE,
                    name="site account",
                    config={"token": "super-secret"},
                ),
                current_user=owner,
            )
        assert site_denied.value.msg_key == "permission_denied"
        assert site_denied.value.status_code == 403

        site_created = await tool_connections.create_tool_connection(
            tool.id,
            ToolConnectionForToolCreate(
                scope=ToolConnectionScope.SITE,
                name="site account",
                config={"token": "site-secret"},
            ),
            current_user=admin,
        )
        assert site_created["data"].team_id is None
        assert site_created["data"].scope == ToolConnectionScope.SITE

        # A declaration list with no usable names allows no credential fields.
        unresolved = await _tool(
            team,
            owner,
            connection_fields=[None, {"label": "anonymous"}, {"name": ""}],
        )
        with pytest.raises(BusinessError) as undeclared_all:
            await tool_connections.create_tool_connection(
                unresolved.id,
                ToolConnectionForToolCreate(
                    team_id=team.id,
                    scope=ToolConnectionScope.TEAM,
                    name="nothing declared",
                    config={"token": "x"},
                ),
                current_user=owner,
            )
        assert undeclared_all.value.msg_key == "tool_connection_invalid"

    conn_orm(scenario)


def test_generic_create_authorizes_tool_and_builtin_paths(conn_orm):
    async def scenario():
        owner = await _user("owner")
        other = await _user("other")
        admin = await _user("admin", superuser=True)
        team = await _team("create-generic")
        other_team = await _team("other-team")
        await _member(team, owner, "owner")
        await _member(other_team, other, "owner")

        private_tool = await _tool(team, owner, visibility=ToolVisibility.PRIVATE)

        with pytest.raises(BusinessError) as access_denied:
            await tool_connections.create_connection(
                ToolConnectionCreate(
                    team_id=team.id,
                    scope=ToolConnectionScope.TEAM,
                    name="not mine",
                    tool_id=private_tool.id,
                ),
                current_user=other,
            )
        assert access_denied.value.msg_key == "tool_access_denied"

        # A site connection without a team is reserved for site admins.
        with pytest.raises(BusinessError) as site_denied:
            await tool_connections.create_connection(
                ToolConnectionCreate(
                    scope=ToolConnectionScope.SITE,
                    name="site without admin",
                    tool_id=private_tool.id,
                ),
                current_user=owner,
            )
        assert site_denied.value.msg_key == "permission_denied"

        by_builtin = await tool_connections.create_connection(
            ToolConnectionCreate(
                team_id=team.id,
                scope=ToolConnectionScope.TEAM,
                name="builtin team account",
                builtin_tool_key="calculate",
            ),
            current_user=owner,
        )
        assert by_builtin["data"].builtin_tool_key == "calculate"

        with pytest.raises(BusinessError) as unknown_builtin:
            await tool_connections.create_connection(
                ToolConnectionCreate(
                    team_id=team.id,
                    scope=ToolConnectionScope.TEAM,
                    name="unknown builtin",
                    builtin_tool_key="no_such_builtin",
                ),
                current_user=owner,
            )
        assert unknown_builtin.value.msg_key == "tool_not_found"

        personal = await tool_connections.create_connection(
            ToolConnectionCreate(
                team_id=team.id,
                scope=ToolConnectionScope.USER,
                name="personal",
                tool_id=private_tool.id,
            ),
            current_user=admin,
        )
        assert personal["data"].scope == ToolConnectionScope.USER
        assert personal["data"].team_id == team.id

    conn_orm(scenario)


def test_connection_reads_enforce_personal_ownership_and_site_team_context(conn_orm):
    async def scenario():
        owner = await _user("owner")
        peer = await _user("peer")
        admin = await _user("admin", superuser=True)
        team = await _team("reads")
        await _member(team, owner, "owner")
        await _member(team, peer, "owner")

        personal = await tool_connections.create_connection(
            ToolConnectionCreate(
                team_id=team.id,
                scope=ToolConnectionScope.USER,
                name="owner personal",
                config={"token": "personal-secret"},
                builtin_tool_key="calculate",
            ),
            current_user=owner,
        )
        connection_id = personal["data"].id

        mine = await tool_connections.get_connection(
            connection_id, team_id=None, current_user=owner
        )
        assert mine["data"].id == connection_id

        for denied_user in (peer, admin):
            with pytest.raises(BusinessError) as denied:
                await tool_connections.get_connection(
                    connection_id, team_id=None, current_user=denied_user
                )
            assert denied.value.msg_key == "tool_connection_access_denied"

        site = await tool_connections.create_connection(
            ToolConnectionCreate(
                scope=ToolConnectionScope.SITE,
                name="site identity",
                builtin_tool_key="calculate",
            ),
            current_user=admin,
        )
        site_id = site["data"].id

        with pytest.raises(BusinessError) as site_needs_context:
            await tool_connections.get_connection(
                site_id, team_id=None, current_user=peer
            )
        assert site_needs_context.value.msg_key == "tool_connection_access_denied"

        with pytest.raises(BusinessError) as site_wrong_team:
            await tool_connections.get_connection(
                site_id, team_id=uuid4(), current_user=peer
            )
        assert site_wrong_team.value.msg_key == "team_not_found"

        with pytest.raises(BusinessError) as site_not_member:
            await tool_connections.get_connection(
                site_id, team_id=(await _team("stranger")).id, current_user=peer
            )
        assert site_not_member.value.msg_key == "not_team_member"

        site_read = await tool_connections.get_connection(
            site_id, team_id=team.id, current_user=peer
        )
        assert site_read["data"].scope == ToolConnectionScope.SITE

        with pytest.raises(BusinessError) as missing:
            await tool_connections.get_connection(
                uuid4(), team_id=None, current_user=owner
            )
        assert missing.value.msg_key == "tool_connection_not_found"

    conn_orm(scenario)


def test_updates_revalidate_declared_fields_and_revoked_state(conn_orm):
    async def scenario():
        owner = await _grant_team_read(await _user("owner"))
        peer = await _user("peer")
        admin = await _user("admin", superuser=True)
        team = await _team("updates")
        await _member(team, owner, "owner")
        await _member(team, peer)

        tool = await _tool(
            team,
            owner,
            connection_fields=[
                {"name": "token", "required": True},
                {"name": "region"},
            ],
        )
        created = await tool_connections.create_tool_connection(
            tool.id,
            ToolConnectionForToolCreate(
                team_id=team.id,
                scope=ToolConnectionScope.TEAM,
                name="team account",
                config={"token": "first", "region": "eu"},
            ),
            current_user=owner,
        )
        connection_id = created["data"].id

        # Removing a required field is rejected before the service write.
        with pytest.raises(BusinessError) as required:
            await tool_connections.update_connection(
                connection_id,
                ToolConnectionUpdate(config_remove=["token"]),
                current_user=owner,
            )
        assert required.value.msg_key == "tool_connection_invalid"

        rotated = await tool_connections.update_connection(
            connection_id,
            ToolConnectionUpdate(
                config_set={"token": "second"}, config_remove=["region"]
            ),
            current_user=owner,
        )
        assert rotated["data"].secret_version == 2
        assert rotated["data"].secret_fields == ["token"]

        # Team-scope management requires an admin, not just membership.
        with pytest.raises(BusinessError) as team_admin:
            await tool_connections.update_connection(
                connection_id,
                ToolConnectionUpdate(name="peer rename"),
                current_user=peer,
            )
        assert team_admin.value.msg_key == "team_admin_required"

        # Personal connections are owner-only even for site admins.
        personal = await tool_connections.create_connection(
            ToolConnectionCreate(
                team_id=team.id,
                scope=ToolConnectionScope.USER,
                name="personal",
                builtin_tool_key="calculate",
            ),
            current_user=owner,
        )
        with pytest.raises(BusinessError) as impersonation:
            await tool_connections.update_connection(
                personal["data"].id,
                ToolConnectionUpdate(name="admin rename"),
                current_user=admin,
            )
        assert impersonation.value.msg_key == "tool_connection_access_denied"

        # Builtin (tool_id=None) updates skip tool lookup and declared fields.
        builtin_update = await tool_connections.update_connection(
            personal["data"].id,
            ToolConnectionUpdate(config_set={"token": "any"}),
            current_user=owner,
        )
        assert builtin_update["data"].secret_fields == ["token"]

        revoked = await tool_connections.revoke_connection(
            connection_id, reason="leaked", current_user=owner
        )
        assert revoked["data"].status == ToolConnectionStatus.REVOKED
        assert revoked["data"].is_default is False

        with pytest.raises(BusinessError) as inactive:
            await tool_connections.update_connection(
                connection_id,
                ToolConnectionUpdate(name="after revoke"),
                current_user=owner,
            )
        assert inactive.value.msg_key == "tool_connection_inactive"
        assert inactive.value.status_code == 409

        with pytest.raises(BusinessError) as missing:
            await tool_connections.update_connection(
                uuid4(), ToolConnectionUpdate(name="ghost"), current_user=owner
            )
        assert missing.value.msg_key == "tool_connection_not_found"

    conn_orm(scenario)


def test_revoke_requires_management_and_is_idempotent(conn_orm):
    async def scenario():
        owner = await _user("owner")
        member = await _user("member")
        admin = await _user("admin", superuser=True)
        team = await _team("revoke")
        await _member(team, owner, "owner")
        await _member(team, member)

        connection = await tool_connections.create_connection(
            ToolConnectionCreate(
                team_id=team.id,
                scope=ToolConnectionScope.TEAM,
                name="default team account",
                builtin_tool_key="calculate",
                is_default=True,
            ),
            current_user=owner,
        )
        connection_id = connection["data"].id

        with pytest.raises(BusinessError) as team_admin:
            await tool_connections.revoke_connection(
                connection_id, reason=None, current_user=member
            )
        assert team_admin.value.msg_key == "team_admin_required"

        first = await tool_connections.revoke_connection(
            connection_id, reason="rotated", current_user=owner
        )
        assert first["data"].status == ToolConnectionStatus.REVOKED

        # Revoking an already-revoked row stays terminal and readable.
        second = await tool_connections.revoke_connection(
            connection_id, reason=None, current_user=admin
        )
        assert second["data"].status == ToolConnectionStatus.REVOKED

        site = await tool_connections.create_connection(
            ToolConnectionCreate(
                scope=ToolConnectionScope.SITE,
                name="site account",
                builtin_tool_key="calculate",
            ),
            current_user=admin,
        )
        with pytest.raises(BusinessError) as site_denied:
            await tool_connections.revoke_connection(
                site["data"].id, reason=None, current_user=owner
            )
        assert site_denied.value.msg_key == "permission_denied"

        with pytest.raises(BusinessError) as missing:
            await tool_connections.revoke_connection(
                uuid4(), reason=None, current_user=owner
            )
        assert missing.value.msg_key == "tool_connection_not_found"

    conn_orm(scenario)


def test_tool_visibility_helper_accepts_raw_string_values():
    assert (
        tool_connections._tool_visibility(
            SimpleNamespace(visibility=ToolVisibility.TEAM)
        )
        == "team"
    )
    assert tool_connections._tool_visibility(SimpleNamespace(visibility="private")) == (
        "private"
    )
