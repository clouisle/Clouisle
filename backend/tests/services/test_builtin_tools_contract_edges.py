"""Descriptor and persistence edges of builtin definition materialization.

``get_builtin_definition`` is the only place a model-facing builtin becomes a
real ``Tool`` row. Its input contract decides whether a dynamic skill/descriptor
can be persisted and what happens when two callers materialize the same
definition concurrently.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from tortoise.context import TortoiseContext
from tortoise.exceptions import IntegrityError

from app.llm.tools import tool_registry
from app.llm.tools.registry import ToolInfo, ToolParameter
from app.models.tool import Tool, ToolType
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.services.builtin_tools import get_builtin_definition


@pytest.fixture
def run_orm(tmp_path):
    runner = asyncio.Runner()
    database_url = f"sqlite://{tmp_path / 'builtin-tools-contract.sqlite3'}"

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


async def _team():
    user = await User.create(
        id=uuid4(),
        username="builtin-contract-owner",
        email="builtin-contract@example.com",
        hashed_password="x",
    )
    team = await Team.create(
        id=uuid4(),
        name=f"builtin-contract-{uuid4()}",
        owner_id=user.id,
    )
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=user.id, role="owner")
    return user, team


def test_malformed_descriptors_are_rejected_before_any_row_exists(run_orm):
    async def scenario():
        _user, team = await _team()
        name = "skill_malformed_descriptor"
        malformed = [
            object(),
            {"name": "different_name", "description": "wrong name"},
            {"name": name, "description": ""},
            {"name": name, "description": "missing params type", "parameters": "nope"},
            {
                "name": name,
                "description": "bad parameter item",
                "parameters": [{"name": "q"}, "not-a-dict"],
            },
            {"name": name, "description": "bad version", "definition_version": 0},
            {
                "name": name,
                "description": "bad version type",
                "definition_version": "1",
            },
        ]

        for descriptor in malformed:
            with pytest.raises(BusinessError) as exc:
                await get_builtin_definition(team.id, name, descriptor=descriptor)
            assert exc.value.code == ResponseCode.BAD_REQUEST
            assert exc.value.msg_key == "tool_connection_invalid"

        assert not await Tool.filter(team_id=team.id, name=name).exists()

    run_orm(scenario)


def test_toolinfo_descriptor_materializes_a_persisted_builtin(run_orm):
    async def scenario():
        _user, team = await _team()
        info = ToolInfo(
            name="skill_research_pack",
            description="Research skill",
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="Search query",
                    required=True,
                )
            ],
        )

        definition = await get_builtin_definition(team.id, info.name, descriptor=info)

        stored = await Tool.filter(id=definition.id).first()
        assert stored is not None
        assert stored.type == ToolType.BUILTIN
        assert definition.approval_policy["default_decision"] == "allow"

    run_orm(scenario)


def test_registry_refresh_upgrades_legacy_identity_in_place(run_orm):
    async def scenario():
        _user, team = await _team()
        legacy = await Tool.create(
            id=uuid4(),
            team_id=team.id,
            name="postgresql_query",
            display_name="postgresql_query",
            description="legacy",
            type=ToolType.BUILTIN,
            identity_policy="none",
            connection_fields=[
                {
                    "name": "url",
                    "label": "Legacy URL",
                    "label_key": "fields.url",
                    "required": True,
                    "secret": True,
                },
                {
                    "name": "custom",
                    "label": "Keep me",
                    "required": True,
                    "secret": False,
                },
            ],
        )

        refreshed = await get_builtin_definition(team.id, "postgresql_query")

        assert refreshed.id == legacy.id
        assert refreshed.identity_policy == "selectable"
        # Operator-added fields survive the identity upgrade.
        assert "custom" in {field["name"] for field in refreshed.connection_fields}
        assert await Tool.filter(team_id=team.id, name="postgresql_query").count() == 1

        again = await get_builtin_definition(team.id, "postgresql_query")
        assert again.id == legacy.id
        assert again.identity_policy == "selectable"

    run_orm(scenario)


def test_concurrent_materialization_adopts_the_existing_builtin(run_orm, monkeypatch):
    registry_name = "fake_adoption_tool"
    tool_registry.register_tool(
        ToolInfo(
            name=registry_name, description="registered description", parameters=[]
        )
    )

    original_save = Tool.save
    winners: dict[str, Tool] = {}

    async def racing_save(definition, *args, **kwargs):
        if definition.name not in winners:
            winner = Tool(
                id=uuid4(),
                team_id=definition.team_id,
                name=definition.name,
                display_name=definition.name,
                description="winner description",
                type=ToolType.BUILTIN,
                approval_policy={},
            )
            winners[definition.name] = winner
            await original_save(winner)
            raise IntegrityError("duplicate key value violates unique constraint")
        return await original_save(definition, *args, **kwargs)

    monkeypatch.setattr(Tool, "save", racing_save)

    async def scenario():
        _user, team = await _team()

        synthetic = await get_builtin_definition(team.id, "list_assets")
        assert synthetic.id == winners["list_assets"].id
        assert synthetic.approval_policy["default_decision"] == "allow"

        registry_defined = await get_builtin_definition(team.id, registry_name)
        assert registry_defined.id == winners[registry_name].id

        assert await Tool.filter(team_id=team.id, name=registry_name).count() == 1
        # The winner keeps its admin policy; adoption never duplicates a row.
        stored = await Tool.filter(team_id=team.id, name="list_assets").first()
        assert stored.id == winners["list_assets"].id
        assert stored.approval_policy["default_decision"] == "allow"

    try:
        run_orm(scenario)
    finally:
        tool_registry.unregister(registry_name)
