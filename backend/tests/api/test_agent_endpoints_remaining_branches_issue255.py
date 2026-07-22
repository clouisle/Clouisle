from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import agents as admin_agents
from app.api.v1.endpoints import agents as user_agents
from app.models.agent import AgentStatus, AgentVisibility
from app.schemas.agent import AgentCreate, AgentKnowledgeBaseConfig
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, result=None, count=0):
        self.result = result
        self.total = count
        self.filters = []

    def filter(self, *args, **kwargs):
        self.filters.append((args, kwargs))
        return self

    def prefetch_related(self, *args):
        return self

    def order_by(self, *args):
        return self

    def offset(self, value):
        return self

    def limit(self, value):
        return self

    async def first(self):
        return self.result

    async def count(self):
        return self.total

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def user(**overrides):
    values = {"id": uuid4(), "is_superuser": False}
    values.update(overrides)
    return SimpleNamespace(**values)


def agent(**overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "name": "Agent",
        "description": None,
        "icon": None,
        "avatar_url": None,
        "model_id": None,
        "team": SimpleNamespace(id=uuid4(), name="Team"),
        "created_by": None,
        "status": AgentStatus.DRAFT,
        "visibility": AgentVisibility.TEAM,
        "conversation_count": 0,
        "message_count": 0,
        "system_prompt": None,
        "max_iterations": 5,
        "hide_tool_calls": False,
        "tools_config": [],
        "enable_vision": False,
        "enable_file_upload": False,
        "file_upload_config": None,
        "enable_user_input_request": False,
        "enable_memory": False,
        "memory_config": None,
        "context_compression_config": None,
        "enable_image_generation": False,
        "image_generation_config": None,
        "enable_video_generation": False,
        "video_generation_config": None,
        "rag_mode": "agentic",
        "variables": [],
        "opening_message": None,
        "suggested_questions": [],
        "embed_config": {},
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_private_unowned_agent_requires_team_admin_for_write(monkeypatch):
    target = agent(visibility=AgentVisibility.PRIVATE)
    query = Query(target)
    access = AsyncMock()
    monkeypatch.setattr(user_agents.Agent, "filter", Mock(return_value=query))
    monkeypatch.setattr(user_agents, "check_team_access", access)

    assert (
        await user_agents.check_agent_access(target.id, user(), require_write=True)
        is target
    )
    assert access.await_args_list[0].args == (
        target.team.id,
        access.await_args_list[0].args[1],
    )
    assert access.await_args_list[1].kwargs == {"require_admin": True}


@pytest.mark.asyncio
async def test_team_agent_write_skips_admin_check_for_owner(monkeypatch):
    owner = user()
    target = agent(created_by=owner)
    access = AsyncMock()
    monkeypatch.setattr(user_agents.Agent, "filter", Mock(return_value=Query(target)))
    monkeypatch.setattr(user_agents, "check_team_access", access)

    assert (
        await user_agents.check_agent_access(target.id, owner, require_write=True)
        is target
    )
    access.assert_awaited_once_with(target.team.id, owner)


@pytest.mark.asyncio
async def test_agent_builders_return_no_model_when_relations_are_missing(monkeypatch):
    monkeypatch.setattr(user_agents.Model, "filter", Mock(return_value=Query(None)))
    assert await user_agents.get_model_info(SimpleNamespace(model_id=uuid4())) is None

    target = agent(model_id=uuid4())
    monkeypatch.setattr(user_agents.TeamModel, "filter", Mock(return_value=Query(None)))
    built_list = await user_agents.build_agent_list_out(target, {})
    monkeypatch.setattr(
        user_agents.AgentKnowledgeBase, "filter", Mock(return_value=Query([]))
    )
    built_detail = await user_agents.build_agent_out(target)

    assert built_list["model"] is None
    assert built_detail["model"] is None


@pytest.mark.asyncio
async def test_user_agent_list_superuser_without_filters_skips_model_batch(monkeypatch):
    current_user = user(is_superuser=True)
    target = agent()
    query = Query([target], count=1)
    build = AsyncMock(return_value={"id": target.id})
    model_filter = Mock()
    monkeypatch.setattr(user_agents.Agent, "all", Mock(return_value=query))
    monkeypatch.setattr(user_agents.TeamModel, "filter", model_filter)
    monkeypatch.setattr(user_agents, "build_agent_list_out", build)

    result = await user_agents.list_agents(current_user=current_user)

    assert result["data"]["total"] == 1
    assert query.filters == []
    model_filter.assert_not_called()
    build.assert_awaited_once_with(target, {})


@pytest.mark.asyncio
async def test_agent_conversation_list_skips_empty_optional_filters(monkeypatch):
    current_user = user()
    target = agent()
    query = Query([], count=0)
    monkeypatch.setattr(
        user_agents, "check_agent_access", AsyncMock(return_value=target)
    )
    monkeypatch.setattr(user_agents.Conversation, "filter", Mock(return_value=query))

    await user_agents.list_agent_conversations(
        target.id,
        search="   ",
        created_after=None,
        created_before=None,
        sort_by="invalid",
        page=1,
        page_size=20,
        current_user=current_user,
    )

    assert query.filters == []


@pytest.mark.asyncio
async def test_get_conversation_defaults_version_count_for_childless_root(monkeypatch):
    current_user = user()
    conversation = SimpleNamespace(id=uuid4(), agent=None)
    message = SimpleNamespace(
        id=uuid4(), parent_id=None, round_id=None, is_round_canonical=True
    )
    monkeypatch.setattr(
        user_agents.Conversation, "filter", Mock(return_value=Query(conversation))
    )
    monkeypatch.setattr(
        user_agents,
        "get_visible_conversation_messages",
        AsyncMock(return_value=[message]),
    )
    child_query = Query([])
    child_query.annotate = Mock(return_value=child_query)
    child_query.group_by = Mock(return_value=child_query)
    child_query.values = AsyncMock(return_value=[])
    monkeypatch.setattr(user_agents.Message, "filter", Mock(return_value=child_query))
    monkeypatch.setattr(
        user_agents, "build_message_round_payloads", AsyncMock(return_value=[{}])
    )
    monkeypatch.setattr(
        user_agents.ConversationOut,
        "model_validate",
        Mock(return_value=SimpleNamespace(model_dump=lambda: {})),
    )

    result = await user_agents.get_conversation(conversation.id, current_user)
    assert result["data"]["messages"][0]["version_count"] == 1


@pytest.mark.asyncio
async def test_admin_get_agent_prefetches_detail_and_rejects_missing(monkeypatch):
    target = agent()
    detailed = Query(target)
    monkeypatch.setattr(admin_agents.Agent, "filter", Mock(return_value=detailed))
    assert await admin_agents._get_agent(target.id, detail=True) is target

    monkeypatch.setattr(admin_agents.Agent, "filter", Mock(return_value=Query(None)))
    with pytest.raises(BusinessError) as error:
        await admin_agents._get_agent(uuid4())
    assert error.value.code == ResponseCode.AGENT_NOT_FOUND


@pytest.mark.asyncio
async def test_admin_agent_list_skips_all_optional_filters(monkeypatch):
    query = Query([], count=0)
    monkeypatch.setattr(admin_agents.Agent, "all", Mock(return_value=query))
    monkeypatch.setattr(admin_agents, "_get_model_info_map", AsyncMock(return_value={}))

    await admin_agents.list_agents(
        page=1,
        page_size=20,
        search=None,
        status=None,
        visibility=None,
        team_id=None,
        creator=None,
        current_user=user(),
    )

    assert query.filters == []


@pytest.mark.asyncio
async def test_admin_create_rejects_unauthorized_model(monkeypatch):
    team_id = uuid4()
    data = AgentCreate(name="Agent", team_id=team_id, model_id=uuid4())
    monkeypatch.setattr(
        admin_agents.Team,
        "filter",
        Mock(return_value=Query(SimpleNamespace(id=team_id))),
    )
    monkeypatch.setattr(admin_agents.Agent, "filter", Mock(return_value=Query(None)))
    monkeypatch.setattr(
        admin_agents.TeamModel, "filter", Mock(return_value=Query(None))
    )

    with pytest.raises(BusinessError) as error:
        await admin_agents.create_agent(Mock(), data, user())
    assert error.value.code == ResponseCode.MODEL_NOT_AUTHORIZED


@pytest.mark.asyncio
async def test_admin_create_rejects_missing_knowledge_base(monkeypatch):
    team_id = uuid4()
    config = AgentKnowledgeBaseConfig(knowledge_base_id=uuid4())
    data = AgentCreate(name="Agent", team_id=team_id, knowledge_base_configs=[config])
    monkeypatch.setattr(
        admin_agents.Team,
        "filter",
        Mock(return_value=Query(SimpleNamespace(id=team_id))),
    )
    monkeypatch.setattr(admin_agents.Agent, "filter", Mock(return_value=Query(None)))
    monkeypatch.setattr(
        admin_agents.KnowledgeBase, "filter", Mock(return_value=Query(None))
    )

    with pytest.raises(BusinessError) as error:
        await admin_agents.create_agent(Mock(), data, user())
    assert error.value.code == ResponseCode.KB_NOT_FOUND


@pytest.mark.asyncio
async def test_admin_create_persists_each_knowledge_base_and_audits(monkeypatch):
    team = SimpleNamespace(id=uuid4(), name="Team")
    configs = [
        AgentKnowledgeBaseConfig(knowledge_base_id=uuid4()),
        AgentKnowledgeBaseConfig(knowledge_base_id=uuid4(), search_mode="vector"),
    ]
    data = AgentCreate(name="Agent", team_id=team.id, knowledge_base_configs=configs)
    created = agent(team=team, status=AgentStatus.DRAFT)
    monkeypatch.setattr(admin_agents.Team, "filter", Mock(return_value=Query(team)))
    monkeypatch.setattr(admin_agents.Agent, "filter", Mock(return_value=Query(None)))
    monkeypatch.setattr(
        admin_agents.KnowledgeBase,
        "filter",
        Mock(return_value=Query(SimpleNamespace())),
    )
    monkeypatch.setattr(admin_agents.Agent, "create", AsyncMock(return_value=created))
    monkeypatch.setattr(admin_agents.Agent, "get", Mock(return_value=Query(created)))
    kb_create = AsyncMock()
    monkeypatch.setattr(admin_agents.AgentKnowledgeBase, "create", kb_create)
    monkeypatch.setattr(admin_agents.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        admin_agents, "build_agent_out", AsyncMock(return_value={"id": created.id})
    )
    from app.services.skill import SkillService

    monkeypatch.setattr(SkillService, "validate_agent_skill_configs", AsyncMock())

    result = await admin_agents.create_agent(Mock(), data, user())

    assert result["data"]["id"] == created.id
    assert kb_create.await_count == 2
    admin_agents.AuditLogService.log.assert_awaited_once()
