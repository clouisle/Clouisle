from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat as chat_endpoint
from app.llm.types import (
    ChatResponse as LLMChatResponse,
    FinishReason,
    FunctionCall,
    Message as LLMMessage,
    ToolCall,
    Usage,
)
from app.models.agent import RAGMode
from app.schemas.agent import ChatRequest
from app.schemas.response import BusinessError, ResponseCode


class _Filter:
    def __init__(self):
        self.update = AsyncMock()


class _PreparedContext:
    messages = [LLMMessage(role="user", content="prepared")]


@pytest.fixture
def ids():
    return SimpleNamespace(
        user_id=uuid4(), agent_id=uuid4(), team_id=uuid4(), conversation_id=uuid4()
    )


def _agent(ids, **overrides):
    values = {
        "id": ids.agent_id,
        "team_id": ids.team_id,
        "rag_mode": RAGMode.OFF,
        "enable_vision": False,
        "enable_user_input_request": False,
        "max_iterations": 5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _team_model():
    model = SimpleNamespace(
        id=uuid4(),
        is_enabled=True,
        provider="openai",
        model_id="gpt-4o-mini",
        capabilities={},
        context_length=8192,
        max_output_tokens=1024,
    )
    return SimpleNamespace(model=model)


def _message(ids, content="assistant"):
    return SimpleNamespace(
        id=uuid4(),
        conversation_id=ids.conversation_id,
        role="assistant",
        content=content,
        images=None,
        file_urls=None,
        tool_calls=None,
        tool_call_id=None,
        tool_name=None,
        reasoning_content=None,
        model_used="openai/gpt-4o-mini",
        token_usage=None,
        duration_ms=None,
        first_token_ms=None,
        is_manually_stopped=False,
        rag_context=None,
        created_at=chat_endpoint.now_utc(),
        round_id=None,
        round_index=0,
        round_role=None,
        is_round_canonical=True,
        iteration_index=None,
        round_status=None,
        parent_id=None,
        branch_parent_id=None,
        is_active=True,
        version_number=1,
        version_count=1,
        versions=None,
        save=AsyncMock(),
    )


def _llm_response(content="done", tool_calls=None, prompt=3, completion=4):
    return LLMChatResponse(
        id="resp-1",
        model="openai/gpt-4o-mini",
        content=content,
        reasoning_content="why",
        tool_calls=tool_calls,
        finish_reason=FinishReason.TOOL_CALLS if tool_calls else FinishReason.STOP,
        usage=Usage(prompt_tokens=prompt, completion_tokens=completion),
    )


def _patch_common(monkeypatch, ids, agent=None, conversation=None):
    user = SimpleNamespace(
        id=ids.user_id, is_active=True, locale="en", is_superuser=False
    )
    agent = agent or _agent(ids)
    conversation = conversation or SimpleNamespace(
        id=ids.conversation_id, title="existing"
    )
    user_msg = _message(ids, "user")
    assistant_msg = _message(ids)
    created_messages = []

    async def create_message(**kwargs):
        msg = (
            user_msg
            if kwargs["role"] == chat_endpoint.MessageRole.USER
            else _message(ids)
        )
        if kwargs.get("round_role") == chat_endpoint.MessageRoundRole.ASSISTANT_FINAL:
            msg = assistant_msg
        for key, value in kwargs.items():
            setattr(msg, key, value)
        created_messages.append(msg)
        return msg

    monkeypatch.setattr(chat_endpoint.deps, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(
        chat_endpoint, "check_agent_chat_access", AsyncMock(return_value=agent)
    )
    monkeypatch.setattr(
        chat_endpoint,
        "get_or_create_conversation",
        AsyncMock(return_value=conversation),
    )
    monkeypatch.setattr(
        chat_endpoint, "get_next_user_branch_parent_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        chat_endpoint.Message, "create", AsyncMock(side_effect=create_message)
    )
    monkeypatch.setattr(chat_endpoint, "update_message_stats", AsyncMock())
    monkeypatch.setattr(
        chat_endpoint, "get_agent_chat_model", AsyncMock(return_value=_team_model())
    )
    monkeypatch.setattr(
        chat_endpoint, "get_streaming_config", lambda _agent: {"tool_timeouts": {}}
    )

    import app.services.sandbox.gateway as gateway_module

    monkeypatch.setattr(
        gateway_module,
        "sandbox_gateway",
        SimpleNamespace(create_session=AsyncMock(return_value="session-1")),
    )
    monkeypatch.setattr(
        chat_endpoint,
        "build_file_content_for_context",
        AsyncMock(return_value=("", None)),
    )
    monkeypatch.setattr(
        chat_endpoint, "get_visible_conversation_messages", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        chat_endpoint, "collect_conversation_images", lambda *_, **__: ([], [])
    )
    monkeypatch.setattr(
        chat_endpoint, "append_conversation_image_inventory", lambda message, _: message
    )
    monkeypatch.setattr(chat_endpoint, "get_agent_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        chat_endpoint, "get_tool_display_names", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        chat_endpoint,
        "prepare_model_context",
        AsyncMock(return_value=_PreparedContext()),
    )
    monkeypatch.setattr(
        chat_endpoint, "get_prefix_path_before", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(chat_endpoint, "activate_conversation_branch", AsyncMock())

    monkeypatch.setattr(
        chat_endpoint, "enqueue_session_memory_extraction", lambda *_, **__: None
    )
    conversation_filter = _Filter()
    agent_filter = _Filter()
    monkeypatch.setattr(
        chat_endpoint.Conversation, "filter", lambda **_: conversation_filter
    )
    monkeypatch.setattr(chat_endpoint.Agent, "filter", lambda **_: agent_filter)
    return SimpleNamespace(
        user=user,
        agent=agent,
        conversation=conversation,
        user_msg=user_msg,
        created_messages=created_messages,
        conversation_update=conversation_filter.update,
        agent_update=agent_filter.update,
    )


@pytest.mark.asyncio
async def test_chat_updates_file_urls_parses_user_input_and_titles_empty_conversation(
    monkeypatch, ids
):
    ctx = _patch_common(
        monkeypatch,
        ids,
        agent=_agent(ids, enable_user_input_request=True),
        conversation=SimpleNamespace(id=ids.conversation_id, title=""),
    )
    updated_urls = [{"url": "https://files.example/parsed.txt"}]
    monkeypatch.setattr(
        chat_endpoint,
        "build_file_content_for_context",
        AsyncMock(return_value=("file text", updated_urls)),
    )
    monkeypatch.setattr(
        chat_endpoint,
        "parse_user_input_request",
        lambda content: (None, content.replace("[[need-input]]", "")),
    )

    from app.llm import model_manager

    monkeypatch.setattr(
        model_manager,
        "team_chat",
        AsyncMock(
            return_value=_llm_response("answer [[need-input]]", prompt=0, completion=9)
        ),
    )

    result = await chat_endpoint.chat(
        ids.agent_id,
        ChatRequest(message="x" * 60, history_override=[]),
        (ctx.user, None),
    )

    assert result["code"] == ResponseCode.SUCCESS
    assert ctx.user_msg.file_urls == updated_urls
    ctx.user_msg.save.assert_awaited_once_with(update_fields=["file_urls"])
    final_msg = ctx.created_messages[-1]
    assert final_msg.content == "answer "
    ctx.conversation_update.assert_awaited_once()
    assert ctx.conversation_update.await_args.kwargs["title"] == "x" * 50 + "..."


@pytest.mark.asyncio
async def test_chat_caps_tool_iterations_with_invalid_arguments_and_display_fallback(
    monkeypatch, ids
):
    ctx = _patch_common(monkeypatch, ids, agent=_agent(ids, max_iterations=1))
    monkeypatch.setattr(
        chat_endpoint,
        "get_agent_tools",
        AsyncMock(
            return_value=[
                {
                    "function": {
                        "name": "lookup",
                        "description": "Lookup",
                        "parameters": {"type": "object"},
                    }
                }
            ]
        ),
    )
    monkeypatch.setattr(
        chat_endpoint, "get_tool_display_names", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        chat_endpoint,
        "execute_tool_call",
        AsyncMock(return_value={"ok": True}),
    )
    monkeypatch.setattr(
        chat_endpoint,
        "get_tool_execution_payloads",
        lambda result: ("display", "llm"),
    )
    monkeypatch.setattr(chat_endpoint, "append_generated_images", lambda *_, **__: None)
    tool_call = ToolCall(
        id="call-1",
        function=FunctionCall(name="lookup", arguments="not-json"),
    )

    from app.llm import model_manager

    monkeypatch.setattr(
        model_manager,
        "team_chat",
        AsyncMock(return_value=_llm_response("", [tool_call], prompt=2, completion=5)),
    )

    result = await chat_endpoint.chat(
        ids.agent_id,
        ChatRequest(message="hello"),
        (ctx.user, None),
    )

    assert result["code"] == ResponseCode.SUCCESS
    assistant_step = ctx.created_messages[1]
    assert assistant_step.tool_calls[0]["display_name"] == "lookup"
    assert assistant_step.tool_calls[0]["arguments"] == {}
    chat_endpoint.execute_tool_call.assert_awaited_once()
    assert chat_endpoint.execute_tool_call.await_args.args[1] == {}
    final_msg = ctx.created_messages[-1]
    assert final_msg.reasoning_content is None
    assert final_msg.tool_calls is None
    assert final_msg.token_usage == {"prompt": 2, "completion": 5}


@pytest.mark.asyncio
async def test_chat_maps_insufficient_quota_to_business_error(monkeypatch, ids):
    ctx = _patch_common(monkeypatch, ids)

    from app.llm import model_manager
    from app.llm.errors import InsufficientQuotaError

    monkeypatch.setattr(
        model_manager,
        "team_chat",
        AsyncMock(side_effect=InsufficientQuotaError("out", quota_type="tokens")),
    )

    with pytest.raises(BusinessError) as exc_info:
        await chat_endpoint.chat(
            ids.agent_id,
            ChatRequest(message="hello"),
            (ctx.user, None),
        )

    assert exc_info.value.code == ResponseCode.MODEL_QUOTA_EXCEEDED
    assert exc_info.value.status_code == 429
    assert exc_info.value.data == {"quota_type": "tokens"}
