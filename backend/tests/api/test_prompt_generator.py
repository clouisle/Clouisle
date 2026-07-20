import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.endpoints import prompt_generator
from app.schemas.response import ResponseCode


async def collect_events(response):
    return "".join([chunk async for chunk in response.body_iterator])


def mock_default_model(monkeypatch, model=None):
    query = MagicMock()
    query.first = AsyncMock(return_value=model)
    monkeypatch.setattr(prompt_generator.Model, "filter", MagicMock(return_value=query))
    return query


class FakeChatModel:
    def __init__(self, *contents, error=None):
        self.contents = contents
        self.error = error
        self.messages = None

    async def astream(self, messages):
        self.messages = messages
        if self.error:
            raise self.error
        for content in self.contents:
            yield SimpleNamespace(content=content)


@pytest.fixture
def audit_log(monkeypatch):
    log = AsyncMock()
    monkeypatch.setattr(prompt_generator.AuditLogService, "log", log)
    return log


def test_context_and_style_helpers_cover_empty_and_populated_boundaries():
    assert prompt_generator.build_context_string(None, "zh") == "无额外上下文"
    assert (
        prompt_generator.build_context_string(
            prompt_generator.PromptGenerateContext(), "en"
        )
        == "No additional context"
    )

    context = prompt_generator.PromptGenerateContext(
        agent_name="Researcher",
        agent_description="Find facts",
        rag_mode="hybrid",
        capabilities={
            "enable_vision": True,
            "enable_memory": True,
            "memory_config": {"window": 3},
        },
        tools=[
            {
                "display_name": "Search",
                "type": "builtin",
                "description": "Search the web",
                "config": {"safe": True},
            },
            {},
        ],
        knowledge_bases=[
            {"name": "Docs", "description": "Manuals", "config": {"top_k": 4}}
        ],
        variables=[
            {
                "name": "query",
                "type": "text",
                "required": False,
                "label": "Question",
                "default": "",
                "options": ["a", "b"],
            }
        ],
    )

    rendered = prompt_generator.build_context_string(context, "en")

    assert "Agent Name: Researcher" in rendered
    assert "Enabled Capabilities: Vision, Memory" in rendered
    assert 'Capability Configs: {"memory_config":{"window":3}}' in rendered
    assert 'Search(builtin): Search the web config={"safe":true}' in rendered
    assert "unknown(unknown)" in rendered
    assert 'Docs: Manuals config={"top_k":4}' in rendered
    assert (
        'query(type=text, required=False, label=Question, options=["a","b"])'
        in rendered
    )
    assert (
        prompt_generator.get_tone_description("missing", "en")
        == "Professional and formal"
    )
    assert prompt_generator.get_focus_description("missing", "zh") == "任务与对话平衡"
    assert prompt_generator.build_style_requirements(None, "en") == ""
    assert (
        prompt_generator.build_style_requirements(
            prompt_generator.PromptStyle(include_cot=True, include_constraints=False),
            "en",
        )
        == "- Include Chain-of-Thought guidance for showing reasoning process"
    )


@pytest.mark.asyncio
async def test_generate_prompt_streams_content_and_audits(monkeypatch, audit_log):
    model = SimpleNamespace(name="default-chat")
    mock_default_model(monkeypatch, model)
    chat_model = FakeChatModel("First", "", " second")
    monkeypatch.setattr(
        "app.llm.adapters.chat.factory.create_chat_model",
        MagicMock(return_value=chat_model),
    )
    body = prompt_generator.PromptGenerateRequest(
        description="Answer questions",
        language="en",
        context=prompt_generator.PromptGenerateContext(agent_name="Helper"),
        style=prompt_generator.PromptStyle(tone="friendly", focus="task-oriented"),
    )
    request = MagicMock()
    user = MagicMock()

    events = await collect_events(
        await prompt_generator.generate_prompt(request, body, user)
    )

    assert "event: start" in events
    assert '"delta": "First"' in events
    assert '"delta": " second"' in events
    assert '"total_length": 12' in events
    generated_prompt = chat_model.messages[0].content
    assert "Answer questions" in generated_prompt
    assert "Agent Name: Helper" in generated_prompt
    assert "Friendly and approachable" in generated_prompt
    audit_log.assert_awaited_once_with(
        user=user,
        action="generate_prompt",
        resource_type="prompt",
        resource_id=None,
        resource_name=None,
        operation="create",
        status="success",
        request=request,
        metadata={"language": "en", "has_context": True},
    )


@pytest.mark.asyncio
async def test_generate_prompt_reports_missing_model(monkeypatch, audit_log):
    query = mock_default_model(monkeypatch)
    body = prompt_generator.PromptGenerateRequest(description="Help", language="")

    events = await collect_events(
        await prompt_generator.generate_prompt(MagicMock(), body, MagicMock())
    )

    payload = json.loads(events.split("data: ", 1)[1])
    assert payload["code"] == ResponseCode.MODEL_NOT_FOUND
    query.first.assert_awaited_once_with()
    audit_log.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_prompt_normalizes_provider_error(monkeypatch, audit_log):
    mock_default_model(monkeypatch, SimpleNamespace(name="broken"))
    monkeypatch.setattr(
        "app.llm.adapters.chat.factory.create_chat_model",
        MagicMock(return_value=FakeChatModel(error=RuntimeError("secret"))),
    )

    events = await collect_events(
        await prompt_generator.generate_prompt(
            MagicMock(),
            prompt_generator.PromptGenerateRequest(description="Help"),
            MagicMock(),
        )
    )

    assert "event: start" in events
    assert f'"code": {ResponseCode.UNKNOWN_ERROR}' in events
    assert "secret" not in events


@pytest.mark.asyncio
async def test_optimize_prompt_streams_content_and_audits(monkeypatch, audit_log):
    mock_default_model(monkeypatch, SimpleNamespace(name="optimizer"))
    chat_model = FakeChatModel("Better")
    monkeypatch.setattr(
        "app.llm.adapters.chat.factory.create_chat_model",
        MagicMock(return_value=chat_model),
    )
    request = MagicMock()
    user = MagicMock()

    events = await collect_events(
        await prompt_generator.optimize_prompt(
            request, "Old prompt", "Be clearer", user
        )
    )

    assert '"delta": "Better"' in events
    assert '"total_length": 6' in events
    assert "Old prompt" in chat_model.messages[0].content
    assert "Be clearer" in chat_model.messages[0].content
    audit_log.assert_awaited_once_with(
        user=user,
        action="optimize_prompt",
        resource_type="prompt",
        resource_id=None,
        resource_name=None,
        operation="update",
        status="success",
        request=request,
        metadata={"prompt_length": 10, "feedback_length": 10},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("model,error_code", [(None, ResponseCode.MODEL_NOT_FOUND)])
async def test_optimize_prompt_reports_missing_model(
    monkeypatch, audit_log, model, error_code
):
    mock_default_model(monkeypatch, model)

    events = await collect_events(
        await prompt_generator.optimize_prompt(
            MagicMock(), "Current", "Feedback", MagicMock()
        )
    )

    assert f'"code": {error_code}' in events
    audit_log.assert_awaited_once()


@pytest.mark.asyncio
async def test_optimize_prompt_normalizes_provider_error(monkeypatch, audit_log):
    mock_default_model(monkeypatch, SimpleNamespace(name="broken"))
    monkeypatch.setattr(
        "app.llm.adapters.chat.factory.create_chat_model",
        MagicMock(side_effect=RuntimeError("secret")),
    )

    events = await collect_events(
        await prompt_generator.optimize_prompt(
            MagicMock(), "Current", "Feedback", MagicMock()
        )
    )

    assert "event: start" in events
    assert f'"code": {ResponseCode.UNKNOWN_ERROR}' in events
    assert "secret" not in events
