from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import agents
from app.models.agent import AgentStatus, AgentVisibility, RAGMode
from app.schemas.agent import AgentCreate, AgentUpdate
from app.schemas.response import BusinessError, ResponseCode


class _Query:
    def __init__(self, result=None, *, count=0, values=None):
        self.result = result
        self.total = count
        self.values = values or []
        self.calls = []

    def filter(self, *args, **kwargs):
        self.calls.append(("filter", args, kwargs))
        return self

    def exclude(self, *args, **kwargs):
        self.calls.append(("exclude", args, kwargs))
        return self

    def prefetch_related(self, *args):
        self.calls.append(("prefetch_related", args, {}))
        return self

    def order_by(self, *args):
        self.calls.append(("order_by", args, {}))
        return self

    def offset(self, value):
        self.calls.append(("offset", (value,), {}))
        return self

    def limit(self, value):
        self.calls.append(("limit", (value,), {}))
        return self

    def values_list(self, *args, **kwargs):
        self.calls.append(("values_list", args, kwargs))
        return _Query(self.values)

    async def first(self):
        return self.result

    async def count(self):
        return self.total

    async def delete(self):
        self.calls.append(("delete", (), {}))

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def _agent(**overrides):
    values = {
        "id": uuid4(),
        "name": "Agent",
        "description": "Description",
        "icon": None,
        "avatar_url": None,
        "team_id": uuid4(),
        "model_id": None,
        "system_prompt": "Helpful",
        "max_iterations": 5,
        "hide_tool_calls": False,
        "hide_message_actions": False,
        "hide_reasoning": False,
        "tools_config": [],
        "enable_attachments": False,
        "enable_user_input_request": False,
        "attachment_config": {},
        "enable_memory": False,
        "memory_config": {},
        "context_compression_config": {},
        "enable_image_generation": False,
        "image_generation_config": {"allow_model_override": True, "width": 1},
        "enable_video_generation": False,
        "video_generation_config": {"allow_model_override": True, "duration": 1},
        "rag_mode": RAGMode.AGENTIC,
        "variables": [],
        "opening_message": None,
        "suggested_questions": [],
        "powered_by_text": None,
        "embed_config": {},
        "visibility": AgentVisibility.TEAM,
        "status": AgentStatus.DRAFT,
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def admin():
    return SimpleNamespace(id=uuid4(), username="admin")


@pytest.mark.anyio
async def test_list_and_filter_options_cover_all_filters_and_model_mapping(admin):
    item = _agent(model_id=uuid4())
    query = _Query([item], count=1)
    model = SimpleNamespace(name="Model", provider="provider", model_id="remote")
    team_model = SimpleNamespace(id=item.model_id, model=model)
    team = SimpleNamespace(id=uuid4(), name="Team")

    with (
        patch.object(agents.Agent, "all", return_value=query),
        patch.object(agents.TeamModel, "filter", return_value=_Query([team_model])),
        patch.object(
            agents, "build_agent_list_out", AsyncMock(return_value={"id": item.id})
        ),
    ):
        response = await agents.list_agents(
            page=2,
            page_size=5,
            search="agent",
            status=[AgentStatus.DRAFT],
            visibility=[AgentVisibility.TEAM],
            team_id=[item.team_id],
            creator=["owner"],
            current_user=admin,
        )

    assert response["data"]["items"] == [{"id": item.id}]
    assert response["data"]["page"] == 2
    assert sum(call[0] == "filter" for call in query.calls) == 5
    assert ("offset", (5,), {}) in query.calls

    with (
        patch.object(agents.Team, "all", return_value=_Query([team])),
        patch.object(
            agents.Agent,
            "filter",
            return_value=_Query(values=["zoe", "", "amy", "zoe"]),
        ),
    ):
        options = await agents.get_agent_filter_options(current_user=admin)

    assert options["data"]["teams"] == [{"value": str(team.id), "label": "Team"}]
    assert options["data"]["creators"] == [
        {"value": "amy", "label": "amy"},
        {"value": "zoe", "label": "zoe"},
    ]
    assert await agents._get_model_info_map([_agent()]) == {}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("stage", "expected_code"),
    [
        ("team", ResponseCode.NOT_FOUND),
        ("duplicate", ResponseCode.DUPLICATE_NAME),
        ("model", ResponseCode.MODEL_NOT_AUTHORIZED),
        ("kb", ResponseCode.KB_NOT_FOUND),
    ],
)
async def test_create_agent_rejects_invalid_boundaries(admin, stage, expected_code):
    team_id = uuid4()
    model_id = uuid4()
    kb_config = SimpleNamespace(knowledge_base_id=uuid4())
    agent_in = AgentCreate.model_construct(
        team_id=team_id,
        name="Agent",
        model_id=model_id,
        knowledge_base_configs=[kb_config],
    )
    team = SimpleNamespace(id=team_id)
    responses = {
        "team": [None],
        "duplicate": [team, _agent()],
        "model": [team, None, None],
        "kb": [team, None, SimpleNamespace(id=model_id), None],
    }[stage]

    with (
        patch.object(agents.Team, "filter", side_effect=[_Query(responses[0])]),
        patch.object(
            agents.Agent,
            "filter",
            side_effect=[_Query(responses[1])] if len(responses) > 1 else [],
        ),
        patch.object(
            agents.TeamModel,
            "filter",
            side_effect=[_Query(responses[2])] if len(responses) > 2 else [],
        ),
        patch.object(
            agents.KnowledgeBase,
            "filter",
            side_effect=[_Query(responses[3])] if len(responses) > 3 else [],
        ),
        pytest.raises(BusinessError) as exc,
    ):
        await agents.create_agent(MagicMock(), agent_in, current_user=admin)

    assert exc.value.code == expected_code


@pytest.mark.anyio
async def test_update_agent_applies_optional_fields_and_replaces_knowledge_bases(admin):
    item = _agent()
    model_id = uuid4()
    kb_config = SimpleNamespace(
        knowledge_base_id=uuid4(),
        retrieval_top_k=7,
        score_threshold=0.5,
        search_mode="hybrid",
    )
    update = AgentUpdate.model_construct(
        name="Renamed",
        description="New",
        icon="icon",
        avatar_url="avatar",
        system_prompt="Prompt",
        max_iterations=9,
        hide_tool_calls=True,
        hide_message_actions=False,
        hide_reasoning=False,
        opening_message="Hello",
        suggested_questions=["Why?"],
        visibility="private",
        model_id=model_id,
        tools_config=[SimpleNamespace(model_dump=lambda: {"type": "builtin"})],
        enable_attachments=True,
        enable_user_input_request=True,
        attachment_config={"parser": None},
        enable_memory=True,
        memory_config=SimpleNamespace(model_dump=lambda: {"auto_extract": True}),
        context_compression_config=SimpleNamespace(
            model_dump=lambda: {"enabled": True}
        ),
        enable_image_generation=True,
        image_generation_config=SimpleNamespace(model_dump=lambda: {"max_images": 2}),
        enable_video_generation=True,
        video_generation_config=SimpleNamespace(model_dump=lambda: {"max_duration": 5}),
        rag_mode="off",
        variables=[SimpleNamespace(model_dump=lambda: {"name": "topic"})],
        embed_config={"theme": "dark"},
        knowledge_base_configs=[kb_config],
    )
    refreshed = _agent(
        id=item.id,
        team_id=item.team_id,
        name="Renamed",
        visibility=AgentVisibility.PRIVATE,
    )
    delete_query = _Query([])

    with (
        patch.object(agents, "_get_agent", AsyncMock(return_value=item)),
        patch.object(agents.Agent, "filter", return_value=_Query(None)),
        patch.object(
            agents.TeamModel, "filter", return_value=_Query(SimpleNamespace())
        ),
        patch(
            "app.services.skill.SkillService.validate_agent_skill_configs", AsyncMock()
        ),
        patch.object(
            agents.KnowledgeBase, "filter", return_value=_Query(SimpleNamespace())
        ),
        patch.object(agents.AgentKnowledgeBase, "filter", return_value=delete_query),
        patch.object(agents.AgentKnowledgeBase, "create", AsyncMock()) as create_kb,
        patch.object(agents.Agent, "get", return_value=_Query(refreshed)),
        patch.object(agents.AuditLogService, "log", AsyncMock()) as audit,
        patch.object(
            agents, "build_agent_out", AsyncMock(return_value={"id": item.id})
        ),
    ):
        response = await agents.update_agent(
            MagicMock(), item.id, update, current_user=admin
        )

    assert response["data"] == {"id": item.id}
    assert item.attachment_config == {"parser": None}
    assert item.rag_mode == RAGMode.OFF
    assert item.variables == [{"name": "topic"}]
    assert item.enable_user_input_request is True
    assert item.embed_config == {"theme": "dark"}
    item.save.assert_awaited_once()
    create_kb.assert_awaited_once()
    assert len(audit.await_args.kwargs["metadata"]["fields_updated"]) == 28
    assert audit.await_args.kwargs["changes"]["before"]["knowledge_bases"] == []
    assert audit.await_args.kwargs["changes"]["after"]["knowledge_bases"] == [
        {
            "knowledge_base_id": str(kb_config.knowledge_base_id),
            "retrieval_top_k": 7,
            "score_threshold": 0.5,
            "search_mode": "hybrid",
        }
    ]


@pytest.mark.anyio
async def test_update_agent_records_kb_configuration_only_changes(admin):
    item = _agent()
    kb_id = uuid4()
    old_row = SimpleNamespace(
        knowledge_base_id=kb_id,
        retrieval_top_k=3,
        score_threshold=0.3,
        search_mode="dense",
    )
    kb_config = SimpleNamespace(
        knowledge_base_id=kb_id,
        retrieval_top_k=7,
        score_threshold=0.5,
        search_mode="hybrid",
    )
    delete_query = _Query([])
    update = AgentUpdate.model_construct(knowledge_base_configs=[kb_config])
    refreshed = _agent(id=item.id, team_id=item.team_id)

    with (
        patch.object(agents, "_get_agent", AsyncMock(return_value=item)),
        patch.object(
            agents.AgentKnowledgeBase,
            "filter",
            side_effect=[_Query([old_row]), delete_query],
        ),
        patch.object(agents.AgentKnowledgeBase, "create", AsyncMock()),
        patch.object(
            agents.KnowledgeBase, "filter", return_value=_Query(SimpleNamespace())
        ),
        patch.object(agents.Agent, "get", return_value=_Query(refreshed)),
        patch.object(agents.AuditLogService, "log", AsyncMock()) as audit,
        patch.object(
            agents, "build_agent_out", AsyncMock(return_value={"id": item.id})
        ),
    ):
        response = await agents.update_agent(
            MagicMock(), item.id, update, current_user=admin
        )

    assert response["data"] == {"id": item.id}
    before = audit.await_args.kwargs["changes"]["before"]["knowledge_bases"]
    after = audit.await_args.kwargs["changes"]["after"]["knowledge_bases"]
    assert before == [
        {
            "knowledge_base_id": str(kb_id),
            "retrieval_top_k": 3,
            "score_threshold": 0.3,
            "search_mode": "dense",
        }
    ]
    assert after == [
        {
            "knowledge_base_id": str(kb_id),
            "retrieval_top_k": 7,
            "score_threshold": 0.5,
            "search_mode": "hybrid",
        }
    ]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("missing", ResponseCode.AGENT_NOT_FOUND),
        ("duplicate", ResponseCode.DUPLICATE_NAME),
        ("model", ResponseCode.MODEL_NOT_AUTHORIZED),
        ("kb", ResponseCode.KB_NOT_FOUND),
    ],
)
async def test_lookup_and_update_rejection_matrix(admin, case, expected_code):
    item = _agent()
    agent_id = item.id

    if case == "missing":
        with (
            patch.object(agents.Agent, "filter", return_value=_Query(None)),
            pytest.raises(BusinessError) as exc,
        ):
            await agents._get_agent(agent_id, detail=True)
    else:
        update = {
            "duplicate": AgentUpdate(name="Other"),
            "model": AgentUpdate(model_id=uuid4()),
            "kb": AgentUpdate(knowledge_base_configs=[{"knowledge_base_id": uuid4()}]),
        }[case]
        with (
            patch.object(agents, "_get_agent", AsyncMock(return_value=item)),
            patch.object(
                agents.Agent,
                "filter",
                return_value=_Query(_agent()) if case == "duplicate" else _Query(None),
            ),
            patch.object(agents.TeamModel, "filter", return_value=_Query(None)),
            patch.object(agents.KnowledgeBase, "filter", return_value=_Query(None)),
            pytest.raises(BusinessError) as exc,
        ):
            await agents.update_agent(MagicMock(), agent_id, update, current_user=admin)

    assert exc.value.code == expected_code


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("function", "status", "notification_type"),
    [
        (
            agents.publish_agent,
            AgentStatus.PUBLISHED,
            agents.AutoNotificationType.AGENT_PUBLISHED,
        ),
        (
            agents.unpublish_agent,
            AgentStatus.DRAFT,
            agents.AutoNotificationType.AGENT_UNPUBLISHED,
        ),
    ],
)
async def test_publish_transitions_with_and_without_team(
    admin, function, status, notification_type
):
    send = AsyncMock()
    build = AsyncMock(return_value={"status": status.value})

    for team_id in (uuid4(), None):
        item = _agent(
            team_id=team_id,
            status=AgentStatus.DRAFT
            if status == AgentStatus.PUBLISHED
            else AgentStatus.PUBLISHED,
        )
        with (
            patch.object(agents, "_get_agent", AsyncMock(return_value=item)),
            patch.object(agents.AuditLogService, "log", AsyncMock()),
            patch.object(agents.AutoNotificationService, "send_to_team", send),
            patch.object(agents, "build_agent_out", build),
            patch.object(agents, "t", return_value="translated"),
        ):
            await function(MagicMock(), item.id, current_user=admin)
        assert item.status == status

    assert send.await_count == 1
    assert send.await_args.kwargs["notification_type"] == notification_type


@pytest.mark.anyio
async def test_duplicate_and_delete_copy_safe_fields_and_audit(admin):
    source = _agent()
    created = _agent(name="Agent (Copy)")
    association = SimpleNamespace(
        knowledge_base_id=uuid4(),
        retrieval_top_k=4,
        score_threshold=0.2,
        search_mode="vector",
    )
    create = AsyncMock(return_value=created)

    with (
        patch.object(agents, "_get_agent", AsyncMock(return_value=source)),
        patch.object(agents.Agent, "create", create),
        patch.object(
            agents.AgentKnowledgeBase, "filter", return_value=_Query([association])
        ),
        patch.object(agents.AgentKnowledgeBase, "create", AsyncMock()) as create_kb,
        patch.object(agents.Agent, "get", return_value=_Query(created)),
        patch.object(agents.AuditLogService, "log", AsyncMock()),
        patch.object(
            agents, "build_agent_out", AsyncMock(return_value={"id": created.id})
        ),
    ):
        response = await agents.duplicate_agent(
            MagicMock(), source.id, current_user=admin
        )

    assert response["data"] == {"id": created.id}
    assert create.await_args.kwargs["image_generation_config"] == {"width": 1}
    assert create.await_args.kwargs["video_generation_config"] == {"duration": 1}
    assert create.await_args.kwargs["enable_user_input_request"] is False
    create_kb.assert_awaited_once()

    with (
        patch.object(agents, "_get_agent", AsyncMock(return_value=source)),
        patch.object(agents.AuditLogService, "log", AsyncMock()),
    ):
        deleted = await agents.delete_agent(MagicMock(), source.id, current_user=admin)

    source.delete.assert_awaited_once()
    assert deleted["data"] == {"id": str(source.id)}
