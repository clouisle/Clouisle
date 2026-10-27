"""Package-import behavior against a real SQLite schema.

These scenarios exercise what a consumer observes after importing a
``.clouisle`` package: permission enforcement, legacy database-tool mapping,
builtin-tool reference rewriting for agents and workflows, and the declared
connection-field contract stored on the created tool.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from tortoise.context import TortoiseContext

from app.models.agent import Agent
from app.models.tool import CustomToolType, Tool, ToolType
from app.models.user import Permission, Role, Team, TeamMember, User
from app.models.workflow import Workflow
from app.schemas.clouisle_package import ClouisleImportInstallRequest
from app.schemas.response import BusinessError
from app.services.clouisle_package_resources import (
    AgentPackageAdapter,
    ToolPackageAdapter,
    WorkflowPackageAdapter,
)


@pytest.fixture
def run_orm(tmp_path):
    """Run one scenario against a fresh file-backed SQLite schema."""
    runner = asyncio.Runner()
    database_url = f"sqlite://{tmp_path / 'package-import.sqlite3'}"

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


async def _user(label: str) -> User:
    suffix = uuid4().hex[:8]
    return await User.create(
        id=uuid4(),
        username=f"{label}_{suffix}",
        email=f"{label}_{suffix}@package-import.test",
        hashed_password="not-used",
    )


async def _team(owner: User) -> Team:
    team = await Team.create(id=uuid4(), name=f"team_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    return team


async def _join(team: Team, user: User, role: str) -> None:
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=user.id, role=role)


async def _grant(user: User, code: str) -> None:
    existing = await Permission.filter(code=code).first()
    permission = existing or await Permission.create(
        id=uuid4(), scope=code.split(":")[0], code=code, description=None
    )
    role = await Role.create(id=uuid4(), name=f"role_{uuid4().hex[:8]}")
    await role.permissions.add(permission)
    await user.roles.add(role)
    await user.fetch_related("roles__permissions")


async def _tool(
    team: Team,
    name: str,
    tool_type: ToolType = ToolType.CUSTOM,
    **values,
) -> Tool:
    if tool_type == ToolType.CUSTOM:
        values.setdefault("custom_type", CustomToolType.HTTP)
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=name,
        display_name=name,
        description="",
        type=tool_type,
        **values,
    )


def test_permission_gate_enforces_membership_and_global_grant(run_orm):
    async def scenario():
        owner = await _user("perm-owner")
        team = await _team(owner)

        member = await _user("perm-member")
        await _join(team, member, "member")
        await _grant(member, "tool:create")
        assert (
            await ToolPackageAdapter().ensure_import_permission(member, team.id) is None
        )
        # Without an explicit team scope the global grant alone decides.
        assert await ToolPackageAdapter().ensure_import_permission(member) is None

        ungranted = await _user("perm-ungranted")
        await _join(team, ungranted, "member")
        await ungranted.fetch_related("roles__permissions")
        with pytest.raises(BusinessError) as denied:
            await ToolPackageAdapter().ensure_import_permission(ungranted, team.id)
        assert denied.value.msg_key == "operation_not_permitted"
        with pytest.raises(BusinessError) as global_denied:
            await ToolPackageAdapter().ensure_import_permission(ungranted)
        assert global_denied.value.msg_key == "operation_not_permitted"

        viewer = await _user("perm-viewer")
        await _join(team, viewer, "viewer")
        await _grant(viewer, "tool:create")
        with pytest.raises(BusinessError) as viewer_denied:
            await ToolPackageAdapter().ensure_import_permission(viewer, team.id)
        assert viewer_denied.value.msg_key == "operation_not_permitted"

        outsider = await _user("perm-outsider")
        await _grant(outsider, "tool:create")
        with pytest.raises(BusinessError) as outsider_denied:
            await ToolPackageAdapter().ensure_import_permission(outsider, team.id)
        assert outsider_denied.value.msg_key == "not_team_member"

    run_orm(scenario)


def test_legacy_database_import_updates_builtin_and_never_clobbers_custom(run_orm):
    async def scenario():
        owner = await _user("legacy-owner")
        team = await _team(owner)
        definition = await _tool(
            team,
            "postgresql_query",
            ToolType.BUILTIN,
            approval_policy={"default_decision": "allow"},
            definition_version=3,
            is_enabled=True,
        )
        payload = {
            "name": "Legacy Postgres",
            "type": "custom",
            "custom_type": "database",
            "database_config": {"db_type": "PostgreSQL"},
            "approval_policy": {"default_decision": "require_approval"},
            "is_enabled": False,
        }

        result = await ToolPackageAdapter().install(
            manifest=None,
            resource_payload=payload,
            team=team,
            user=owner,
            install_in=ClouisleImportInstallRequest(),
        )

        assert result.updated == definition.id
        assert result.installed is None
        assert result.warnings == ["clouisle_database_connection_required"]
        refreshed = await Tool.get(id=definition.id)
        assert refreshed.definition_version == 4
        assert refreshed.is_enabled is False
        assert refreshed.approval_policy["default_decision"] == "require_approval"

        # A user-owned custom tool that happens to share the legacy builtin
        # name is a real conflict; the import must not take it over.
        collision = await _tool(team, "mysql_query", ToolType.CUSTOM)
        with pytest.raises(BusinessError) as conflict:
            await ToolPackageAdapter().install(
                manifest=None,
                resource_payload={
                    "name": "Legacy MySQL",
                    "type": "custom",
                    "custom_type": "database",
                    "database_config": {"db_type": "mysql"},
                },
                team=team,
                user=owner,
                install_in=ClouisleImportInstallRequest(),
            )
        assert conflict.value.msg_key == "tool_name_exists"
        preserved = await Tool.get(id=collision.id)
        assert preserved.type == ToolType.CUSTOM

    run_orm(scenario)


def test_agent_install_rewrites_legacy_tool_ids_to_builtin_names(run_orm):
    async def scenario():
        owner = await _user("agent-owner")
        team = await _team(owner)
        builtin = await _tool(team, "postgresql_query", ToolType.BUILTIN)
        custom = await _tool(team, "custom-http", ToolType.CUSTOM)
        unknown_id = str(uuid4())
        payload = {
            "name": "tool-agent",
            "tools_config": [
                {
                    "type": "builtin",
                    "name": "web_search",
                    "config": {"engine": "unknown"},
                },
                {"type": "custom", "tool_id": unknown_id},
                {"type": "custom", "tool_id": str(custom.id)},
                {
                    "type": "mcp",
                    "server_id": str(builtin.id),
                    "config": {"mode": "team"},
                },
            ],
        }

        result = await AgentPackageAdapter().install(
            manifest=None,
            resource_payload=payload,
            team=team,
            user=owner,
            install_in=ClouisleImportInstallRequest(),
        )

        agent = await Agent.get(id=result.installed)
        assert agent.tools_config == [
            {"type": "builtin", "name": "web_search", "config": {"engine": "auto"}},
            {"type": "custom", "tool_id": unknown_id},
            {"type": "custom", "tool_id": str(custom.id)},
            {"type": "builtin", "name": "postgresql_query", "config": {"mode": "team"}},
        ]

        duplicate_payload = {
            "name": "duplicate-agent",
            "tools_config": [
                {"type": "custom", "tool_id": str(builtin.id)},
                {"type": "builtin", "name": "postgresql_query"},
            ],
        }
        with pytest.raises(BusinessError) as duplicate:
            await AgentPackageAdapter().install(
                manifest=None,
                resource_payload=duplicate_payload,
                team=team,
                user=owner,
                install_in=ClouisleImportInstallRequest(),
            )
        assert duplicate.value.msg_key == "clouisle_builtin_tool_duplicate"
        assert duplicate.value.kwargs["fields"] == "postgresql_query"
        assert (
            await Agent.filter(team_id=team.id, name="duplicate-agent").exists()
            is False
        )

    run_orm(scenario)


def test_workflow_install_rewrites_builtin_tool_nodes(run_orm):
    async def scenario():
        owner = await _user("workflow-owner")
        team = await _team(owner)
        postgres = await _tool(team, "postgresql_query", ToolType.BUILTIN)
        mysql = await _tool(team, "mysql_query", ToolType.BUILTIN)
        custom = await _tool(team, "custom-http", ToolType.CUSTOM)
        definition = {
            "nodes": [
                "invalid-node",
                {"data": {}},
                {
                    "data": {
                        "config": {
                            "toolType": "custom",
                            "toolId": str(postgres.id),
                            "toolName": "old-name",
                        }
                    }
                },
                {"data": {"toolConfig": {"toolType": "mcp", "tool_id": str(mysql.id)}}},
                {
                    "data": {
                        "toolConfig": {
                            "toolType": "custom",
                            "tool_id": str(custom.id),
                        }
                    }
                },
                {"data": {"toolConfig": {"toolType": "builtin", "toolName": "keep"}}},
                {"data": {"config": {"toolType": "custom"}}},
                {"data": {"toolConfig": "not-a-dict", "config": "not-a-dict"}},
            ]
        }

        result = await WorkflowPackageAdapter().install(
            manifest=None,
            resource_payload={"name": "builtin-flow", "definition": definition},
            team=team,
            user=owner,
            install_in=ClouisleImportInstallRequest(),
        )

        workflow = await Workflow.get(id=result.installed)
        nodes = workflow.definition["nodes"]
        assert nodes[0] == "invalid-node"
        assert nodes[1] == {"data": {}}
        assert nodes[2]["data"]["config"] == {
            "toolType": "builtin",
            "toolName": "postgresql_query",
        }
        assert nodes[3]["data"]["toolConfig"] == {
            "toolType": "builtin",
            "toolName": "mysql_query",
        }
        assert nodes[4]["data"]["toolConfig"] == {
            "toolType": "custom",
            "tool_id": str(custom.id),
        }
        assert nodes[5]["data"]["toolConfig"] == {
            "toolType": "builtin",
            "toolName": "keep",
        }
        assert nodes[6]["data"]["config"] == {"toolType": "custom"}
        assert nodes[7]["data"] == {
            "toolConfig": "not-a-dict",
            "config": "not-a-dict",
        }

    run_orm(scenario)


def test_tool_install_normalizes_declared_fields_and_rejects_inline_secrets(run_orm):
    async def scenario():
        owner = await _user("tool-owner")
        team = await _team(owner)
        payload = {
            "name": "declared-api",
            "type": "custom",
            "custom_type": "http",
            "http_config": {
                "url": "https://api.example.test/v1",
                "headers": {"X-Api-Key": "{{api_key}}"},
            },
            "connection_fields": [
                None,
                "api_key",
                {"name": "   "},
                {
                    "name": " api_key ",
                    "label": "",
                    "required": False,
                    "label_key": "tool.api_key",
                },
            ],
        }

        result = await ToolPackageAdapter().install(
            manifest=None,
            resource_payload=payload,
            team=team,
            user=owner,
            install_in=ClouisleImportInstallRequest(),
        )

        tool = await Tool.get(id=result.installed)
        assert tool.connection_fields == [
            {
                "name": "api_key",
                "label": "api_key",
                "required": False,
                "secret": True,
                "label_key": "tool.api_key",
            }
        ]
        assert tool.credentials == {}
        assert tool.is_enabled is False

        with pytest.raises(BusinessError) as leak:
            await ToolPackageAdapter().install(
                manifest=None,
                resource_payload={
                    "name": "leaky-api",
                    "type": "custom",
                    "custom_type": "http",
                    "http_config": {
                        "url": "https://api.example.test/v1",
                        "headers": {"Authorization": "Bearer live"},
                    },
                },
                team=team,
                user=owner,
                install_in=ClouisleImportInstallRequest(),
            )
        assert leak.value.msg_key == "tool_secret_inline_not_allowed"
        assert await Tool.filter(team_id=team.id, name="leaky-api").exists() is False

    run_orm(scenario)
