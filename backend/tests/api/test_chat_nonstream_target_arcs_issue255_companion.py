from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.llm.errors import ContextLengthError
from app.llm.types import ChatResponse, FunctionCall, Message, ToolCall, Usage
from app.models.agent import RAGMode
from app.schemas.agent import ChatRequest
from app.schemas.response import BusinessError


def _fake_chat_resolution():
    """Return a SimpleNamespace mimicking ChatModelResolution for tests."""
    from types import SimpleNamespace
    from uuid import uuid4

    return SimpleNamespace(
        model=SimpleNamespace(id=uuid4()),
        team_model=SimpleNamespace(),
        model_id=str(uuid4()),
        tokenizer_model_id="stub-model",
        provider="stub",
        context_length=8192,
        max_output_tokens=1024,
        supports_vision=False,
    )


class UpdateQuery:
    def __init__(self):
        self.update = AsyncMock(return_value=1)


class ChangingToolCalls:
    def __init__(self, calls):
        self.calls = calls
        self.checks = iter((False, True))

    def __bool__(self):
        return next(self.checks)

    def __iter__(self):
        return iter(self.calls)


class StoredMessage(SimpleNamespace):
    pass


def response(*, tool_calls=None, usage=True, content="answer"):
    values = {
        "id": str(uuid4()),
        "model": "stub/model",
        "content": content,
        "reasoning_content": None,
        "tool_calls": tool_calls,
        "finish_reason": "tool_calls" if tool_calls else "stop",
        "usage": Usage(prompt_tokens=2, completion_tokens=3, total_tokens=5),
    }
    if not usage:
        values["usage"] = None
    return ChatResponse(**values) if usage else SimpleNamespace(**values)


async def setup_chat(monkeypatch, *, max_iterations=2, history_override=None):
    user = SimpleNamespace(id=uuid4(), is_active=True, locale="en")
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        rag_mode=RAGMode.OFF,
        max_iterations=max_iterations,
        enable_attachments=False,
        enable_user_input_request=False,
    )
    conversation = SimpleNamespace(id=uuid4(), title="existing")
    created = []

    async def create_message(**values):
        defaults = {
            "id": uuid4(),
            "conversation_id": values["conversation"].id,
            "created_at": datetime.now(UTC),
            "images": None,
            "file_urls": None,
            "tool_calls": None,
            "tool_call_id": None,
            "tool_name": None,
            "reasoning_content": None,
            "model_used": None,
            "token_usage": None,
            "duration_ms": None,
            "first_token_ms": None,
            "is_manually_stopped": False,
            "rag_context": None,
            "round_id": None,
            "round_index": 0,
            "round_role": None,
            "is_round_canonical": False,
            "iteration_index": None,
            "round_status": None,
            "parent_id": None,
            "branch_parent_id": None,
            "is_active": True,
            "version_number": 1,
            "save": AsyncMock(),
        }
        defaults.update(values)
        defaults.pop("conversation")
        message = StoredMessage(**defaults)
        created.append(message)
        return message

    prepared = SimpleNamespace(messages=[Message(role="user", content="prepared")])
    monkeypatch.setattr(chat.deps, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(chat, "check_agent_chat_access", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        chat, "get_or_create_conversation", AsyncMock(return_value=conversation)
    )
    monkeypatch.setattr(
        chat, "get_next_user_branch_parent_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(chat.Message, "create", AsyncMock(side_effect=create_message))
    monkeypatch.setattr(chat, "update_message_stats", AsyncMock())
    monkeypatch.setattr(
        chat,
        "resolve_agent_chat_model",
        AsyncMock(return_value=_fake_chat_resolution()),
    )
    monkeypatch.setattr(
        chat, "get_streaming_config", lambda _agent: {"tool_timeouts": {}}
    )
    monkeypatch.setattr(
        "app.services.sandbox.gateway.sandbox_gateway.create_session",
        AsyncMock(return_value="session"),
    )
    monkeypatch.setattr(
        chat, "build_file_content_for_context", AsyncMock(return_value=("", None))
    )
    monkeypatch.setattr(
        chat, "get_visible_conversation_messages", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(chat, "collect_conversation_images", lambda *_a, **_k: ([], []))
    monkeypatch.setattr(
        chat, "append_conversation_image_inventory", lambda text, _images: text
    )
    monkeypatch.setattr(chat, "get_agent_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "get_tool_display_names", AsyncMock(return_value={}))
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(return_value=prepared))
    monkeypatch.setattr(chat.Conversation, "filter", Mock(return_value=UpdateQuery()))
    monkeypatch.setattr(chat.Agent, "filter", Mock(return_value=UpdateQuery()))
    monkeypatch.setattr(chat, "get_prefix_path_before", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "activate_conversation_branch", AsyncMock())

    monkeypatch.setattr(chat, "enqueue_session_memory_extraction", Mock())

    request = ChatRequest(message="hello", history_override=history_override)
    return SimpleNamespace(user=user, agent=agent, request=request, created=created)


async def run_chat(state):
    return await chat.chat(state.agent.id, state.request, (state.user, None))


@pytest.mark.anyio
async def test_nonstream_skips_empty_iteration_range(monkeypatch):
    state = await setup_chat(monkeypatch, max_iterations=-1)

    with pytest.raises(UnboundLocalError):
        await run_chat(state)


@pytest.mark.anyio
@pytest.mark.parametrize("error_source", ["prepare", "model"])
async def test_nonstream_does_not_retry_context_error(monkeypatch, error_source):
    state = await setup_chat(monkeypatch)
    monkeypatch.setattr(chat, "should_retry_context_length", lambda _agent: False)
    if error_source == "prepare":
        chat.prepare_model_context.side_effect = ContextLengthError()
    else:
        monkeypatch.setattr(
            "app.llm.model_manager.team_chat",
            AsyncMock(side_effect=ContextLengthError()),
        )

    with pytest.raises(BusinessError):
        await run_chat(state)


@pytest.mark.anyio
async def test_nonstream_retried_prepare_does_not_retry_model_error(monkeypatch):
    state = await setup_chat(monkeypatch)
    chat.prepare_model_context.side_effect = ContextLengthError()
    monkeypatch.setattr(chat, "should_retry_context_length", lambda _agent: True)
    monkeypatch.setattr(
        chat,
        "retry_prepare_model_context",
        AsyncMock(
            return_value=SimpleNamespace(messages=[Message(role="user", content="x")])
        ),
    )
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat",
        AsyncMock(side_effect=ContextLengthError()),
    )

    with pytest.raises(BusinessError):
        await run_chat(state)


@pytest.mark.anyio
async def test_nonstream_accepts_response_without_usage(monkeypatch):
    state = await setup_chat(monkeypatch)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat",
        AsyncMock(return_value=response(usage=False)),
    )

    result = await run_chat(state)

    assert result["data"].usage["total_tokens"] == 0


@pytest.mark.anyio
async def test_nonstream_safe_parser_accepts_mapping_arguments(monkeypatch):
    state = await setup_chat(monkeypatch, max_iterations=1)
    call = ToolCall(id="call", function=FunctionCall(name="lookup", arguments="{}"))
    call.function.arguments = {"query": "x"}
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat",
        AsyncMock(return_value=response(tool_calls=[call])),
    )

    with pytest.raises(TypeError):
        await run_chat(state)

    assert state.created[1].tool_calls[0]["arguments"] == {"query": "x"}


@pytest.mark.anyio
async def test_nonstream_preserves_existing_history_override(monkeypatch):
    state = await setup_chat(
        monkeypatch,
        history_override=[{"role": "user", "content": "prior"}],
    )
    call = ToolCall(id="call", function=FunctionCall(name="lookup", arguments="{}"))
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat",
        AsyncMock(side_effect=[response(tool_calls=[call]), response()]),
    )
    monkeypatch.setattr(chat, "execute_tool_call", AsyncMock(return_value="result"))
    monkeypatch.setattr(
        chat, "get_tool_execution_payloads", lambda value: (value, value)
    )

    await run_chat(state)

    second_context = chat.prepare_model_context.await_args_list[1].kwargs
    assert [item["role"] for item in second_context["history_override"]] == [
        "user",
        "assistant",
        "tool",
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("final_calls", [[], None])
async def test_nonstream_final_tool_call_iteration_edges(monkeypatch, final_calls):
    state = await setup_chat(monkeypatch)
    setup_call = ToolCall(
        id="setup", function=FunctionCall(name="lookup", arguments="{}")
    )
    final_call = ToolCall(
        id="final", function=FunctionCall(name="lookup", arguments='{"q": 1}')
    )
    changing = ChangingToolCalls([final_call] if final_calls is None else final_calls)
    final = response()
    final.tool_calls = changing
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat",
        AsyncMock(side_effect=[response(tool_calls=[setup_call]), final]),
    )
    monkeypatch.setattr(chat, "execute_tool_call", AsyncMock(return_value="result"))
    monkeypatch.setattr(
        chat, "get_tool_execution_payloads", lambda value: (value, value)
    )

    await run_chat(state)

    assert state.created[-1].tool_calls == (
        []
        if final_calls == []
        else [
            {
                "id": "final",
                "name": "lookup",
                "display_name": "lookup",
                "arguments": {"q": 1},
            }
        ]
    )
