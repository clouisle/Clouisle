from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.api.v1.endpoints import agents
from app.models.agent import AgentStatus, AgentVisibility
from app.schemas.agent import AgentCreate, AgentKnowledgeBaseConfig, AgentUpdate
from app.schemas.response import BusinessError


class Query:
    def __init__(self, value=None, *, count=0):
        self.value = value
        self.count_value = count
        self.calls = []

    def _chain(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return self

    def filter(self, *args, **kwargs):
        return self._chain("filter", *args, **kwargs)

    def exclude(self, *args, **kwargs):
        return self._chain("exclude", *args, **kwargs)

    def prefetch_related(self, *args):
        return self._chain("prefetch_related", *args)

    def offset(self, value):
        return self._chain("offset", value)

    def limit(self, value):
        return self._chain("limit", value)

    def order_by(self, value):
        return self._chain("order_by", value)

    def annotate(self, **kwargs):
        return self._chain("annotate", **kwargs)

    def group_by(self, *args):
        return self._chain("group_by", *args)

    def values(self, *args):
        return self._chain("values", *args)

    async def first(self):
        return self.value

    async def count(self):
        return self.count_value

    async def delete(self):
        self.calls.append(("delete", (), {}))
        return 1

    async def update(self, **kwargs):
        self.calls.append(("update", (), kwargs))
        return 1

    def __await__(self):
        async def resolve():
            return self.value

        return resolve().__await__()


def request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/agents",
            "headers": [],
            "query_string": b"",
        }
    )


def user(*, superuser=False):
    return SimpleNamespace(id=uuid4(), is_superuser=superuser, username="tester")


def agent(**overrides):
    now = datetime.now(UTC)
    owner = overrides.pop("created_by", user())
    team = overrides.pop(
        "team", SimpleNamespace(id=uuid4(), name="Team", avatar_url=None)
    )
    values = {
        "id": uuid4(),
        "name": "Agent",
        "description": "Description",
        "icon": None,
        "avatar_url": None,
        "team": team,
        "team_id": team.id,
        "model_id": None,
        "system_prompt": "Be useful",
        "max_iterations": 5,
        "hide_tool_calls": False,
        "hide_message_actions": False,
        "hide_reasoning": False,
        "tools_config": [],
        "enable_attachments": False,
        "attachment_config": {},
        "enable_user_input_request": False,
        "enable_memory": False,
        "memory_config": {},
        "context_compression_config": {},
        "enable_image_generation": False,
        "image_generation_config": {},
        "enable_video_generation": False,
        "video_generation_config": {},
        "rag_mode": "agentic",
        "variables": [],
        "opening_message": None,
        "suggested_questions": [],
        "powered_by_text": None,
        "embed_config": {},
        "status": AgentStatus.DRAFT,
        "visibility": AgentVisibility.TEAM,
        "conversation_count": 0,
        "message_count": 0,
        "created_by": owner,
        "created_at": now,
        "updated_at": now,
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def conversation(**overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "agent_id": uuid4(),
        "agent": SimpleNamespace(name="Agent", icon=None),
        "user_id": uuid4(),
        "title": "Chat",
        "variables": {},
        "message_count": 2,
        "token_usage": 5,
        "created_at": now,
        "updated_at": now,
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_check_agent_access_boundaries(monkeypatch):
    current_user = user()
    owner_agent = agent(created_by=current_user, visibility=AgentVisibility.PRIVATE)
    query = Query(owner_agent)
    monkeypatch.setattr(agents.Agent, "filter", lambda **_kwargs: query)

    assert (
        await agents.check_agent_access(owner_agent.id, current_user, True)
        is owner_agent
    )

    owner_agent.created_by = user()
    with pytest.raises(BusinessError) as error:
        await agents.check_agent_access(owner_agent.id, current_user)
    assert error.value.msg_key == "agent_access_denied"

    query.value = None
    with pytest.raises(BusinessError) as error:
        await agents.check_agent_access(uuid4(), current_user)
    assert error.value.status_code == 404


@pytest.mark.anyio
async def test_check_agent_access_team_and_superuser(monkeypatch):
    current_user = user()
    team_agent = agent(created_by=None, visibility=AgentVisibility.PRIVATE)
    query = Query(team_agent)
    check_team = AsyncMock()
    monkeypatch.setattr(agents.Agent, "filter", lambda **_kwargs: query)
    monkeypatch.setattr(agents, "check_team_access", check_team)

    assert (
        await agents.check_agent_access(team_agent.id, current_user, True) is team_agent
    )
    check_team.assert_any_await(team_agent.team.id, current_user)
    check_team.assert_any_await(team_agent.team.id, current_user, require_admin=True)

    check_team.reset_mock()
    assert (
        await agents.check_agent_access(team_agent.id, user(superuser=True))
        is team_agent
    )
    check_team.assert_not_awaited()


@pytest.mark.anyio
async def test_build_agent_outputs_relations_and_sanitizes_media(monkeypatch):
    item = agent(
        model_id=uuid4(),
        image_generation_config={"allow_model_override": True, "max_images": 2},
        video_generation_config={"allow_model_override": True},
        visibility=AgentVisibility.PUBLIC,
    )
    model = SimpleNamespace(name="Model", provider="dummy", model_id="dummy-model")
    team_model = SimpleNamespace(id=item.model_id, model=model)
    kb = SimpleNamespace(
        id=uuid4(), name="KB", description=None, icon=None, document_count=3
    )
    association = SimpleNamespace(
        id=uuid4(),
        knowledge_base=kb,
        retrieval_top_k=4,
        score_threshold=0.5,
        search_mode="hybrid",
    )
    monkeypatch.setattr(agents.TeamModel, "filter", lambda **_kwargs: Query(team_model))
    monkeypatch.setattr(
        agents.AgentKnowledgeBase, "filter", lambda **_kwargs: Query([association])
    )

    output = await agents.build_agent_out(item)
    listing = await agents.build_agent_list_out(
        item,
        {
            str(item.model_id): agents.ModelInfo(
                id=item.model_id,
                name="Model",
                provider="dummy",
                model_id="dummy-model",
            )
        },
    )

    assert output["knowledge_bases"][0]["knowledge_base"]["name"] == "KB"
    assert output["image_generation_config"] == {"max_images": 2}
    assert output["video_generation_config"] is None
    assert output["visibility"] == AgentVisibility.TEAM
    assert listing["model"]["provider"] == "dummy"


@pytest.mark.anyio
async def test_list_agents_applies_scope_filters_and_batches_models(monkeypatch):
    current_user = user()
    item = agent(model_id=uuid4())
    query = Query([item], count=1)
    memberships = Query([item.team_id])
    team_model = SimpleNamespace(
        id=item.model_id,
        model=SimpleNamespace(
            name="M",
            provider="dummy",
            provider_display_name="Acme Gateway",
            model_id="m",
        ),
    )
    monkeypatch.setattr(agents.Agent, "all", lambda: query)
    monkeypatch.setattr(agents.TeamMember, "filter", lambda **_kwargs: memberships)
    memberships.values_list = lambda *_args, **_kwargs: memberships
    monkeypatch.setattr(
        agents.TeamModel, "filter", lambda **_kwargs: Query([team_model])
    )

    result = await agents.list_agents(
        status="draft",
        visibility="team",
        keyword="agent",
        own_only=True,
        page=2,
        page_size=1,
        current_user=current_user,
    )

    assert result["data"]["total"] == 1
    assert result["data"]["items"][0]["model"]["name"] == "M"
    assert (
        result["data"]["items"][0]["model"]["provider_display_name"] == "Acme Gateway"
    )
    assert any(call[0] == "offset" and call[1] == (1,) for call in query.calls)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("existing", "model", "kb", "msg_key"),
    [
        (object(), object(), object(), "agent_name_exists"),
        (None, None, object(), "model_not_authorized"),
        (None, object(), None, "kb_not_found"),
    ],
)
async def test_create_agent_rejects_invalid_bindings(
    monkeypatch, existing, model, kb, msg_key
):
    team_id = uuid4()
    payload = AgentCreate(
        name="Agent",
        team_id=team_id,
        model_id=uuid4(),
        knowledge_base_configs=[{"knowledge_base_id": uuid4()}],
    )
    monkeypatch.setattr(agents.deps, "check_scoped_permission", AsyncMock())
    monkeypatch.setattr(
        agents, "check_team_access", AsyncMock(return_value=SimpleNamespace(id=team_id))
    )
    monkeypatch.setattr(agents.Agent, "filter", lambda **_kwargs: Query(existing))
    monkeypatch.setattr(agents.TeamModel, "filter", lambda **_kwargs: Query(model))
    monkeypatch.setattr(agents.KnowledgeBase, "filter", lambda **_kwargs: Query(kb))

    with pytest.raises(BusinessError) as error:
        await agents.create_agent(
            request=request(), agent_in=payload, current_user=user()
        )
    assert error.value.msg_key == msg_key


@pytest.mark.anyio
async def test_create_agent_persists_config_and_knowledge_binding(monkeypatch):
    team_id = uuid4()
    kb_id = uuid4()
    current_user = user()
    team = SimpleNamespace(id=team_id, name="Team")
    created = agent(team=SimpleNamespace(id=team_id, name="Team", avatar_url=None))
    payload = AgentCreate(
        name="Agent",
        team_id=team_id,
        tools_config=[{"type": "builtin", "name": "clock"}],
        knowledge_base_configs=[
            {
                "knowledge_base_id": kb_id,
                "retrieval_top_k": 7,
                "score_threshold": 0.4,
                "search_mode": "vector",
            }
        ],
        enable_memory=True,
        memory_config={"max_memories_per_retrieval": 6},
        enable_video_generation=True,
        video_generation_config={"default_model_ref": "dummy/model"},
    )
    monkeypatch.setattr(agents.deps, "check_scoped_permission", AsyncMock())
    monkeypatch.setattr(agents, "check_team_access", AsyncMock(return_value=team))
    monkeypatch.setattr(agents.Agent, "filter", lambda **_kwargs: Query(None))
    monkeypatch.setattr(
        agents.KnowledgeBase, "filter", lambda **_kwargs: Query(object())
    )
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(agents.Agent, "create", create)
    monkeypatch.setattr(agents.Agent, "get", lambda **_kwargs: Query(created))
    binding_create = AsyncMock()
    monkeypatch.setattr(agents.AgentKnowledgeBase, "create", binding_create)
    monkeypatch.setattr(
        agents.AgentKnowledgeBase, "filter", lambda **_kwargs: Query([])
    )
    monkeypatch.setattr(agents.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        "app.services.skill.SkillService.validate_agent_skill_configs", AsyncMock()
    )

    result = await agents.create_agent(
        request=request(), agent_in=payload, current_user=current_user
    )

    assert result["msg"]
    assert create.await_args.kwargs["tools_config"][0]["name"] == "clock"
    assert create.await_args.kwargs["memory_config"]["max_memories_per_retrieval"] == 6
    binding_create.assert_awaited_once()
    agents.AuditLogService.log.assert_awaited_once()


@pytest.mark.anyio
async def test_update_agent_updates_config_tools_and_kb(monkeypatch):
    item = agent()
    payload = AgentUpdate(
        name="Updated",
        description="New",
        max_iterations=8,
        tools_config=[{"type": "builtin", "name": "clock"}],
        enable_attachments=True,
        attachment_config={"max_files": 2},
        enable_memory=True,
        memory_config={"max_memories_per_retrieval": 4},
        enable_image_generation=True,
        image_generation_config={"max_images": 2},
        rag_mode="auto",
        variables=[{"name": "topic"}],
        embed_config={"allowed_domains": ["example.test"]},
        knowledge_base_configs=[{"knowledge_base_id": uuid4()}],
    )
    monkeypatch.setattr(agents, "check_agent_access", AsyncMock(return_value=item))
    monkeypatch.setattr(agents.deps, "check_scoped_permission", AsyncMock())
    monkeypatch.setattr(agents.Agent, "filter", lambda **_kwargs: Query(None))
    kb_query = Query([])
    monkeypatch.setattr(agents.AgentKnowledgeBase, "filter", lambda **_kwargs: kb_query)
    monkeypatch.setattr(
        agents.KnowledgeBase, "filter", lambda **_kwargs: Query(object())
    )
    monkeypatch.setattr(agents.AgentKnowledgeBase, "create", AsyncMock())
    monkeypatch.setattr(agents.Agent, "get", lambda **_kwargs: Query(item))
    monkeypatch.setattr(agents.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        "app.services.skill.SkillService.validate_agent_skill_configs", AsyncMock()
    )

    result = await agents.update_agent(
        request=request(), agent_id=item.id, agent_in=payload, current_user=user()
    )

    assert result["data"]["name"] == "Updated"
    assert item.tools_config[0]["name"] == "clock"
    assert item.embed_config == {"allowed_domains": ["example.test"]}
    assert any(call[0] == "delete" for call in kb_query.calls)
    item.save.assert_awaited_once()


@pytest.mark.anyio
async def test_update_agent_stops_after_persistence_error(monkeypatch):
    item = agent()
    item.save.side_effect = RuntimeError("database unavailable")
    audit = AsyncMock()
    monkeypatch.setattr(agents, "check_agent_access", AsyncMock(return_value=item))
    monkeypatch.setattr(agents.deps, "check_scoped_permission", AsyncMock())
    monkeypatch.setattr(agents.AuditLogService, "log", audit)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await agents.update_agent(
            request=request(),
            agent_id=item.id,
            agent_in=AgentUpdate(description="changed"),
            current_user=user(),
        )

    audit.assert_not_awaited()


@pytest.mark.anyio
async def test_delete_publish_and_unpublish(monkeypatch):
    item = agent()
    monkeypatch.setattr(agents, "check_agent_access", AsyncMock(return_value=item))
    monkeypatch.setattr(agents.AuditLogService, "log", AsyncMock())
    notify = AsyncMock()
    monkeypatch.setattr(agents.AutoNotificationService, "send_to_team", notify)
    monkeypatch.setattr(
        agents, "build_agent_out", AsyncMock(return_value={"id": item.id})
    )

    deleted = await agents.delete_agent(request(), item.id, user())
    published = await agents.publish_agent(request(), item.id, user())
    unpublished = await agents.unpublish_agent(request(), item.id, user())

    assert deleted["data"]["id"] == str(item.id)
    item.delete.assert_awaited_once()
    assert published["data"]["id"] == item.id
    assert unpublished["data"]["id"] == item.id
    assert item.status == AgentStatus.DRAFT
    assert notify.await_count == 2


@pytest.mark.anyio
async def test_duplicate_copies_bindings_and_strips_internal_media_config(monkeypatch):
    source = agent(
        image_generation_config={"allow_model_override": True, "max_images": 3},
        video_generation_config={"allow_model_override": True, "poll_timeout_s": 30},
    )
    duplicate = agent(name="Agent (Copy)")
    association = SimpleNamespace(
        knowledge_base_id=uuid4(),
        retrieval_top_k=5,
        score_threshold=0.3,
        search_mode="hybrid",
    )
    monkeypatch.setattr(agents, "check_agent_access", AsyncMock(return_value=source))
    monkeypatch.setattr(agents.deps, "check_scoped_permission", AsyncMock())
    create = AsyncMock(return_value=duplicate)
    monkeypatch.setattr(agents.Agent, "create", create)
    monkeypatch.setattr(agents.Agent, "get", lambda **_kwargs: Query(duplicate))
    monkeypatch.setattr(
        agents.AgentKnowledgeBase, "filter", lambda **_kwargs: Query([association])
    )
    binding_create = AsyncMock()
    monkeypatch.setattr(agents.AgentKnowledgeBase, "create", binding_create)
    monkeypatch.setattr(agents.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(agents, "build_agent_out", AsyncMock(return_value={"ok": True}))

    result = await agents.duplicate_agent(source.id, request(), user())

    assert result["data"] == {"ok": True}
    assert create.await_args.kwargs["visibility"] == AgentVisibility.PRIVATE
    assert create.await_args.kwargs["image_generation_config"] == {"max_images": 3}
    assert create.await_args.kwargs["video_generation_config"] == {"poll_timeout_s": 30}
    binding_create.assert_awaited_once()


@pytest.mark.anyio
async def test_video_status_boundaries(monkeypatch):
    item = agent(enable_video_generation=False)
    monkeypatch.setattr(agents, "check_agent_access", AsyncMock(return_value=item))

    with pytest.raises(BusinessError) as error:
        await agents.get_agent_video_generation_status(item.id, "task", user())
    assert error.value.status_code == 400

    item.enable_video_generation = True
    item.video_generation_config = {
        "default_model_ref": "dummy/model",
        "poll_interval_ms": 500,
        "poll_timeout_s": 5,
    }
    response = {"status": "succeeded", "url": "https://example.test/video.mp4"}
    get_status = AsyncMock(return_value=response)
    build_result = MagicMock(return_value={"status": "succeeded"})
    monkeypatch.setattr("app.llm.model_manager.get_video_status", get_status)
    monkeypatch.setattr(
        "app.llm.tools.builtin.media.build_video_tool_result", build_result
    )

    result = await agents.get_agent_video_generation_status(item.id, "task", user())

    assert result["data"] == {"status": "succeeded"}
    get_status.assert_awaited_once_with("task", model_id="dummy/model")
    build_result.assert_called_once_with(
        "",
        response,
        model_ref="dummy/model",
        poll_interval_ms=500,
        poll_timeout_s=5,
    )


@pytest.mark.anyio
async def test_conversation_list_filters_and_invalid_sort(monkeypatch):
    item = agent()
    conv = conversation()
    query = Query([conv], count=1)
    monkeypatch.setattr(agents, "check_agent_access", AsyncMock(return_value=item))
    monkeypatch.setattr(agents.Conversation, "filter", lambda **_kwargs: query)

    result = await agents.list_agent_conversations(
        item.id,
        search=" chat ",
        created_after=datetime.now(UTC),
        created_before=datetime.now(UTC),
        sort_by="invalid",
        page=1,
        page_size=20,
        current_user=user(),
    )

    assert result["data"]["items"][0]["agent_name"] == item.name
    assert any(
        call[0] == "order_by" and call[1] == ("-updated_at",) for call in query.calls
    )


@pytest.mark.anyio
async def test_conversation_crud_and_missing_paths(monkeypatch):
    current_user = user()
    conv = conversation(user_id=current_user.id)
    query = Query(conv)
    agent_query = Query()
    monkeypatch.setattr(agents.Conversation, "filter", lambda **_kwargs: query)
    monkeypatch.setattr(agents.Agent, "filter", lambda **_kwargs: agent_query)

    renamed = await agents.update_conversation(
        conversation_id=conv.id,
        conv_in=agents.ConversationUpdate(title="Renamed"),
        current_user=current_user,
    )
    deleted = await agents.delete_conversation(conv.id, current_user)

    assert renamed["data"]["title"] == "Renamed"
    conv.save.assert_awaited_once()
    assert deleted["data"]["id"] == str(conv.id)
    conv.delete.assert_awaited_once()

    query.value = None
    with pytest.raises(BusinessError) as error:
        await agents.update_conversation(
            conversation_id=uuid4(),
            conv_in=agents.ConversationUpdate(title="Missing"),
            current_user=current_user,
        )
    assert error.value.msg_key == "conversation_not_found"


@pytest.mark.anyio
async def test_delete_message_updates_token_totals(monkeypatch):
    current_user = user()
    conv = conversation(user_id=current_user.id)
    message = SimpleNamespace(
        id=uuid4(),
        token_usage={"prompt": 3, "completion": 4},
        delete=AsyncMock(),
    )
    conv_query = Query(conv)
    message_query = Query(message)
    monkeypatch.setattr(agents.Conversation, "filter", lambda **_kwargs: conv_query)
    monkeypatch.setattr(agents.Message, "filter", lambda **_kwargs: message_query)

    result = await agents.delete_message(conv.id, message.id, current_user)

    assert result["data"]["id"] == str(message.id)
    update = next(call for call in conv_query.calls if call[0] == "update")
    assert "token_usage" in update[2]
    assert "updated_at" in update[2]
    message.delete.assert_awaited_once()

    message_query.value = None
    with pytest.raises(BusinessError) as error:
        await agents.delete_message(conv.id, uuid4(), current_user)
    assert error.value.msg_key == "message_not_found"


@pytest.mark.anyio
async def test_get_agent_and_list_my_conversations(monkeypatch):
    item = agent()
    conv = conversation(agent=item)
    current_user = user()
    monkeypatch.setattr(agents, "check_agent_access", AsyncMock(return_value=item))
    monkeypatch.setattr(
        agents, "build_agent_out", AsyncMock(return_value={"id": item.id})
    )
    query = Query([conv], count=1)
    monkeypatch.setattr(agents.Conversation, "filter", lambda **_kwargs: query)

    fetched = await agents.get_agent(item.id, current_user)
    listed = await agents.list_my_conversations(
        agent_id=item.id, page=1, page_size=10, current_user=current_user
    )

    assert fetched["data"]["id"] == item.id
    assert listed["data"]["items"][0]["agent_name"] == item.name
    assert any(call[0] == "filter" for call in query.calls)


@pytest.mark.anyio
async def test_get_conversation_missing(monkeypatch):
    monkeypatch.setattr(agents.Conversation, "filter", lambda **_kwargs: Query(None))

    with pytest.raises(BusinessError) as error:
        await agents.get_conversation(uuid4(), user())

    assert error.value.msg_key == "conversation_not_found"


@pytest.mark.anyio
async def test_model_helpers_and_shared_agent_write_access(monkeypatch):
    assert await agents.get_model_info(None) is None
    monkeypatch.setattr(agents.Model, "filter", lambda **_kwargs: Query(None))
    assert await agents.get_model_info(SimpleNamespace(model_id=uuid4())) is None

    model = SimpleNamespace(
        name="Model",
        provider="dummy",
        provider_display_name="Acme Gateway",
        model_id="model",
    )
    monkeypatch.setattr(agents.Model, "filter", lambda **_kwargs: Query(model))
    team_model = SimpleNamespace(id=uuid4(), model_id=uuid4())
    model_info = await agents.get_model_info(team_model)
    assert model_info.name == "Model"
    assert model_info.provider_display_name == "Acme Gateway"

    current_user = user()
    item = agent(created_by=user(), visibility=AgentVisibility.TEAM)
    check_team = AsyncMock()
    monkeypatch.setattr(agents.Agent, "filter", lambda **_kwargs: Query(item))
    monkeypatch.setattr(agents, "check_team_access", check_team)

    assert await agents.check_agent_access(item.id, current_user, True) is item
    check_team.assert_any_await(item.team.id, current_user)
    check_team.assert_any_await(item.team.id, current_user, require_admin=True)


@pytest.mark.anyio
async def test_agent_list_fallback_model_and_team_scopes(monkeypatch):
    team_id = uuid4()
    item = agent(model_id=uuid4())
    query = Query([item], count=1)
    team_model = SimpleNamespace(
        id=item.model_id,
        model=SimpleNamespace(
            name="Fallback",
            provider="dummy",
            provider_display_name="Acme Gateway",
            model_id="fallback",
        ),
    )
    monkeypatch.setattr(agents.Agent, "all", lambda: query)
    monkeypatch.setattr(
        agents.TeamModel,
        "filter",
        lambda **kwargs: Query([team_model] if "id__in" in kwargs else team_model),
    )
    monkeypatch.setattr(agents, "check_team_access", AsyncMock())

    listing = await agents.build_agent_list_out(item)
    result = await agents.list_agents(
        team_id=team_id, current_user=user(superuser=True)
    )

    assert listing["model"]["name"] == "Fallback"
    assert listing["model"]["provider_display_name"] == "Acme Gateway"
    assert result["data"]["total"] == 1
    assert any(
        call[0] == "filter" and call[2] == {"team_id": team_id} for call in query.calls
    )

    query.calls.clear()
    await agents.list_agents(team_id=team_id, current_user=user())
    assert len([call for call in query.calls if call[0] == "filter"]) == 2


@pytest.mark.anyio
async def test_update_agent_rejects_duplicate_model_and_kb(monkeypatch):
    item = agent()
    monkeypatch.setattr(agents, "check_agent_access", AsyncMock(return_value=item))
    monkeypatch.setattr(agents.deps, "check_scoped_permission", AsyncMock())

    monkeypatch.setattr(agents.Agent, "filter", lambda **_kwargs: Query(object()))
    with pytest.raises(BusinessError) as error:
        await agents.update_agent(
            request=request(),
            agent_id=item.id,
            agent_in=AgentUpdate(name="Duplicate"),
            current_user=user(),
        )
    assert error.value.msg_key == "agent_name_exists"

    monkeypatch.setattr(agents.Agent, "filter", lambda **_kwargs: Query(None))
    monkeypatch.setattr(agents.TeamModel, "filter", lambda **_kwargs: Query(None))
    with pytest.raises(BusinessError) as error:
        await agents.update_agent(
            request=request(),
            agent_id=item.id,
            agent_in=AgentUpdate(model_id=uuid4()),
            current_user=user(),
        )
    assert error.value.msg_key == "model_not_authorized"

    monkeypatch.setattr(
        agents.AgentKnowledgeBase, "filter", lambda **_kwargs: Query([])
    )
    monkeypatch.setattr(agents.KnowledgeBase, "filter", lambda **_kwargs: Query(None))
    with pytest.raises(BusinessError) as error:
        await agents.update_agent(
            request=request(),
            agent_id=item.id,
            agent_in=AgentUpdate(
                knowledge_base_configs=[{"knowledge_base_id": uuid4()}]
            ),
            current_user=user(),
        )
    assert error.value.msg_key == "kb_not_found"


@pytest.mark.anyio
async def test_update_agent_persists_remaining_fields(monkeypatch):
    item = agent()
    model_id = uuid4()
    payload = AgentUpdate(
        icon="bot",
        avatar_url="https://example.test/avatar.png",
        system_prompt="Updated prompt",
        hide_tool_calls=True,
        hide_message_actions=False,
        hide_reasoning=False,
        opening_message="Hello",
        suggested_questions=["Help?"],
        powered_by_text="Acme Inc",
        visibility="public",
        model_id=model_id,
        enable_attachments=True,
        enable_user_input_request=True,
        context_compression_config={"enabled": True},
        enable_video_generation=True,
        video_generation_config={"default_model_ref": "dummy/model"},
    )
    monkeypatch.setattr(agents, "check_agent_access", AsyncMock(return_value=item))
    monkeypatch.setattr(agents.deps, "check_scoped_permission", AsyncMock())
    monkeypatch.setattr(agents.Agent, "filter", lambda **_kwargs: Query(None))
    team_model = SimpleNamespace(
        id=model_id,
        model=SimpleNamespace(name="Model", provider="dummy", model_id="model"),
    )
    monkeypatch.setattr(agents.TeamModel, "filter", lambda **_kwargs: Query(team_model))
    monkeypatch.setattr(agents.Agent, "get", lambda **_kwargs: Query(item))
    monkeypatch.setattr(
        agents.AgentKnowledgeBase, "filter", lambda **_kwargs: Query([])
    )
    monkeypatch.setattr(agents.AuditLogService, "log", AsyncMock())

    result = await agents.update_agent(
        request=request(), agent_id=item.id, agent_in=payload, current_user=user()
    )

    assert result["data"]["visibility"] == AgentVisibility.TEAM
    assert item.model_id == model_id
    assert item.enable_attachments is True
    assert item.enable_user_input_request is True
    assert item.video_generation_config["default_model_ref"] == "dummy/model"
    assert item.powered_by_text == "Acme Inc"
    fields = agents.AuditLogService.log.await_args.kwargs["metadata"]["fields_updated"]
    assert {
        "icon",
        "avatar_url",
        "system_prompt",
        "model_id",
        "powered_by_text",
    } <= set(fields)


@pytest.mark.anyio
async def test_publish_without_team_skips_provider_notification(monkeypatch):
    item = agent(team_id=None)
    monkeypatch.setattr(agents, "check_agent_access", AsyncMock(return_value=item))
    monkeypatch.setattr(agents.AuditLogService, "log", AsyncMock())
    notify = AsyncMock()
    monkeypatch.setattr(agents.AutoNotificationService, "send_to_team", notify)
    monkeypatch.setattr(agents, "build_agent_out", AsyncMock(return_value={}))

    await agents.publish_agent(request(), item.id, user())
    await agents.unpublish_agent(request(), item.id, user())

    notify.assert_not_awaited()


@pytest.mark.anyio
async def test_get_conversation_builds_versions_and_agent_details(monkeypatch):
    current_user = user()
    conv = conversation(user_id=current_user.id)
    root_id = uuid4()
    child_id = uuid4()
    messages = [
        SimpleNamespace(
            id=root_id, parent_id=None, round_id=None, is_round_canonical=True
        ),
        SimpleNamespace(
            id=child_id, parent_id=root_id, round_id=None, is_round_canonical=True
        ),
    ]
    monkeypatch.setattr(agents.Conversation, "filter", lambda **_kwargs: Query(conv))
    monkeypatch.setattr(
        agents, "get_visible_conversation_messages", AsyncMock(return_value=messages)
    )
    monkeypatch.setattr(
        agents.Message,
        "filter",
        lambda **_kwargs: Query([{"parent_id": root_id, "count": 1}]),
    )
    monkeypatch.setattr(
        agents,
        "build_message_round_payloads",
        AsyncMock(return_value=[{"id": root_id}, {"id": child_id}]),
    )

    result = await agents.get_conversation(conv.id, current_user)

    assert result["data"]["agent_name"] == conv.agent.name
    assert [message["version_count"] for message in result["data"]["messages"]] == [
        2,
        2,
    ]


@pytest.mark.anyio
async def test_conversation_optional_and_not_found_branches(monkeypatch):
    current_user = user()
    conv = conversation(agent=None, user_id=current_user.id)
    list_query = Query([conv], count=1)
    detail_query = Query(conv)
    monkeypatch.setattr(
        agents.Conversation,
        "filter",
        lambda **_kwargs: list_query if list_query.calls == [] else detail_query,
    )

    listed = await agents.list_my_conversations(current_user=current_user)
    unchanged = await agents.update_conversation(
        conversation_id=conv.id,
        conv_in=agents.ConversationUpdate(),
        current_user=current_user,
    )
    assert listed["data"]["items"][0]["agent_name"] is None
    assert unchanged["data"]["agent_name"] is None
    conv.save.assert_not_awaited()

    detail_query.value = None
    with pytest.raises(BusinessError) as error:
        await agents.delete_conversation(uuid4(), current_user)
    assert error.value.msg_key == "conversation_not_found"

    with pytest.raises(BusinessError) as error:
        await agents.delete_message(uuid4(), uuid4(), current_user)
    assert error.value.msg_key == "conversation_not_found"


@pytest.mark.anyio
async def test_delete_message_without_usage_updates_count(monkeypatch):
    current_user = user()
    conv = conversation(user_id=current_user.id)
    message = SimpleNamespace(id=uuid4(), token_usage=None, delete=AsyncMock())
    conv_query = Query(conv)
    monkeypatch.setattr(agents.Conversation, "filter", lambda **_kwargs: conv_query)
    monkeypatch.setattr(agents.Message, "filter", lambda **_kwargs: Query(message))

    await agents.delete_message(conv.id, message.id, current_user)

    assert any(call[0] == "update" for call in conv_query.calls)
    message.delete.assert_awaited_once()


def test_agent_request_validation_boundaries():
    with pytest.raises(ValidationError):
        AgentCreate(name="", team_id=uuid4())
    with pytest.raises(ValidationError):
        AgentCreate(name="Agent", team_id=uuid4(), max_iterations=201)
    with pytest.raises(ValidationError):
        AgentKnowledgeBaseConfig(knowledge_base_id=uuid4(), score_threshold=1.1)
    with pytest.raises(ValidationError):
        AgentKnowledgeBaseConfig(knowledge_base_id=uuid4(), search_mode="unknown")
