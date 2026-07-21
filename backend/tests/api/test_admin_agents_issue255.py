from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import agents
from app.models.agent import AgentStatus, AgentVisibility
from app.schemas.response import BusinessError


class Query:
    def __init__(self, result=None, *, count=0):
        self.result = result
        self.total = count
        self.calls = []

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return self

    def filter(self, *args, **kwargs):
        return self._record("filter", *args, **kwargs)

    def exclude(self, *args, **kwargs):
        return self._record("exclude", *args, **kwargs)

    def prefetch_related(self, *args):
        return self._record("prefetch_related", *args)

    def order_by(self, *args):
        return self._record("order_by", *args)

    def offset(self, value):
        return self._record("offset", value)

    def limit(self, value):
        return self._record("limit", value)

    def values_list(self, *args, **kwargs):
        return self._record("values_list", *args, **kwargs)

    async def first(self):
        if isinstance(self.result, list):
            return self.result[0] if self.result else None
        return self.result

    async def count(self):
        return self.total

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def agent(**overrides):
    values = {
        "id": uuid4(),
        "name": "Coverage Agent",
        "description": "Description",
        "icon": None,
        "avatar_url": None,
        "team_id": uuid4(),
        "model_id": None,
        "system_prompt": "Help",
        "max_iterations": 5,
        "hide_tool_calls": False,
        "tools_config": [],
        "enable_vision": False,
        "enable_file_upload": False,
        "file_upload_config": {},
        "enable_user_input_request": False,
        "enable_memory": False,
        "memory_config": {},
        "context_compression_config": {},
        "enable_image_generation": False,
        "image_generation_config": {"allow_model_override": True, "size": "1:1"},
        "enable_video_generation": False,
        "video_generation_config": {"allow_model_override": True, "duration": 5},
        "rag_mode": "agentic",
        "variables": [],
        "opening_message": None,
        "suggested_questions": [],
        "visibility": AgentVisibility.TEAM,
        "status": AgentStatus.DRAFT,
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_agent_lookup_and_model_map_boundaries(monkeypatch):
    query = Query(None)
    monkeypatch.setattr(agents.Agent, "filter", lambda **kwargs: query)

    with pytest.raises(BusinessError) as exc:
        await agents._get_agent(uuid4(), detail=True)
    assert exc.value.status_code == 404
    assert any(call[0] == "prefetch_related" for call in query.calls)
    assert await agents._get_model_info_map([agent()]) == {}

    model_id = uuid4()
    team_model = SimpleNamespace(
        id=model_id,
        model=SimpleNamespace(name="Model", provider="openai", model_id="gpt-test"),
    )
    monkeypatch.setattr(
        agents.TeamModel,
        "filter",
        lambda **kwargs: Query([team_model]),
    )
    info = await agents._get_model_info_map([agent(model_id=model_id)])
    assert info[str(model_id)].name == "Model"


@pytest.mark.anyio
async def test_list_agents_applies_all_filters_and_serializes(monkeypatch):
    item = agent()
    query = Query([item], count=1)
    monkeypatch.setattr(agents.Agent, "all", lambda: query)
    monkeypatch.setattr(agents, "_get_model_info_map", AsyncMock(return_value={}))
    monkeypatch.setattr(
        agents, "build_agent_list_out", AsyncMock(return_value={"id": str(item.id)})
    )

    result = await agents.list_agents(
        page=2,
        page_size=10,
        search="coverage",
        status=[AgentStatus.DRAFT],
        visibility=[AgentVisibility.TEAM],
        team_id=[item.team_id],
        creator=["owner"],
        current_user=SimpleNamespace(),
    )

    assert result["data"]["total"] == 1
    assert result["data"]["page"] == 2
    assert len([call for call in query.calls if call[0] == "filter"]) == 5
    assert ("offset", (10,), {}) in query.calls


@pytest.mark.anyio
async def test_filter_options_are_sorted_and_deduplicated(monkeypatch):
    teams = [
        SimpleNamespace(id=uuid4(), name="Beta"),
        SimpleNamespace(id=uuid4(), name="Alpha"),
    ]
    monkeypatch.setattr(agents.Team, "all", lambda: Query(teams))
    monkeypatch.setattr(
        agents.Agent,
        "filter",
        lambda **kwargs: Query(["zoe", None, "amy", "zoe"]),
    )

    result = await agents.get_agent_filter_options(current_user=SimpleNamespace())

    assert [item["label"] for item in result["data"]["teams"]] == ["Beta", "Alpha"]
    assert result["data"]["creators"] == [
        {"value": "amy", "label": "amy"},
        {"value": "zoe", "label": "zoe"},
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("function", "start_status", "expected_status", "notification_type"),
    [
        (
            agents.publish_agent,
            AgentStatus.DRAFT,
            AgentStatus.PUBLISHED,
            "agent.published",
        ),
        (
            agents.unpublish_agent,
            AgentStatus.PUBLISHED,
            AgentStatus.DRAFT,
            "agent.unpublished",
        ),
    ],
)
async def test_publish_transitions_audit_and_notify(
    monkeypatch, function, start_status, expected_status, notification_type
):
    item = agent(status=start_status)
    monkeypatch.setattr(agents, "_get_agent", AsyncMock(return_value=item))
    monkeypatch.setattr(
        agents, "build_agent_out", AsyncMock(return_value={"id": item.id})
    )
    audit = AsyncMock()
    notify = AsyncMock()
    monkeypatch.setattr(agents.AuditLogService, "log", audit)
    monkeypatch.setattr(agents.AutoNotificationService, "send_to_team", notify)

    result = await function(MagicMock(), item.id, current_user=SimpleNamespace())

    assert item.status is expected_status
    item.save.assert_awaited_once()
    audit.assert_awaited_once()
    notify.assert_awaited_once()
    assert notify.await_args.kwargs["notification_type"].value == notification_type
    assert result["data"]["id"] == item.id


@pytest.mark.anyio
async def test_duplicate_copies_safe_configuration_and_knowledge(monkeypatch):
    source = agent()
    duplicate = agent(name="Coverage Agent (Copy)")
    association = SimpleNamespace(
        knowledge_base_id=uuid4(),
        retrieval_top_k=4,
        score_threshold=0.7,
        search_mode="hybrid",
    )
    create_agent = AsyncMock(return_value=duplicate)
    create_association = AsyncMock()
    monkeypatch.setattr(agents, "_get_agent", AsyncMock(return_value=source))
    monkeypatch.setattr(agents.Agent, "create", create_agent)
    monkeypatch.setattr(agents.Agent, "get", lambda **kwargs: Query(duplicate))
    monkeypatch.setattr(
        agents.AgentKnowledgeBase, "filter", lambda **kwargs: Query([association])
    )
    monkeypatch.setattr(agents.AgentKnowledgeBase, "create", create_association)
    monkeypatch.setattr(agents.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        agents, "build_agent_out", AsyncMock(return_value={"id": duplicate.id})
    )

    result = await agents.duplicate_agent(
        MagicMock(), source.id, current_user=SimpleNamespace(id=uuid4())
    )

    assert create_agent.await_args.kwargs["visibility"] is AgentVisibility.PRIVATE
    assert (
        "allow_model_override"
        not in create_agent.await_args.kwargs["image_generation_config"]
    )
    assert (
        "allow_model_override"
        not in create_agent.await_args.kwargs["video_generation_config"]
    )
    create_association.assert_awaited_once()
    assert result["data"]["id"] == duplicate.id


@pytest.mark.anyio
async def test_delete_audits_before_removing_agent(monkeypatch):
    item = agent()
    audit = AsyncMock()
    monkeypatch.setattr(agents, "_get_agent", AsyncMock(return_value=item))
    monkeypatch.setattr(agents.AuditLogService, "log", audit)

    result = await agents.delete_agent(
        MagicMock(), item.id, current_user=SimpleNamespace(id=uuid4())
    )

    audit.assert_awaited_once()
    item.delete.assert_awaited_once()
    assert result["data"] == {"id": str(item.id)}
