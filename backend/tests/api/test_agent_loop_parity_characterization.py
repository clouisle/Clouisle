"""
Characterization tests for the four Agent Chat execution paths.

These tests freeze the current visible contracts BEFORE centralizing the four
duplicated tool loops into a single AgentLoop state machine: event order,
branch activation, and persisted round structure must not change during the
extraction.

These tests use fake model streams and fake tools only; they do not modify
production behavior. They are expected to pass against the current chat.py and
to fail if the extraction accidentally changes:

 SSE event ordering (message_start -> tool_call -> tool_result -> content ->
  message_end, compression events at their actual loop position)
 branch activation (edit creates a new user version and activates the edited
  path; regenerate creates a new assistant version)
 persisted round structure (canonical user input, non-canonical assistant
  step with tool_calls, non-canonical tool results, canonical final assistant)
 manual-stop persistence (disconnect saves partial content with
  MANUALLY_STOPPED and does not emit message_end)
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat as chat_api
from app.llm.types import (
    ChatResponse as LLMChatResponse,
    ChatStreamChunk,
    ChatStreamDelta,
    FinishReason,
    FunctionCall,
    Message as LLMMessage,
    MessageRole as LLMMessageRole,
    ToolCall,
    Usage,
)
from app.models.agent import MessageRole, MessageRoundStatus, RAGMode
from app.schemas.agent import ChatRequest, EditMessageRequest


class StoredMessage:
    """Fake persisted message capturing every round-structure field."""

    def __init__(self, **values):
        self.id = uuid4()
        self.conversation_id = values["conversation"].id
        self.created_at = datetime.now(UTC)
        self.parent_id = None
        self.is_active = True
        self.version_number = 1
        self.save = AsyncMock()
        self.delete = AsyncMock()
        for name, default in {
            "content": "",
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
            "branch_parent_id": None,
        }.items():
            setattr(self, name, values.get(name, default))
        self.role = values["role"]


class UpdateQuery:
    def __init__(self):
        self.update = AsyncMock(return_value=1)

    def filter(self, *_args, **_kwargs):
        return self


def _model_resolution():
    model_uuid = uuid4()
    model = SimpleNamespace(
        id=model_uuid,
        is_enabled=True,
        capabilities={},
        provider="stub",
        model_id="unit-model",
        context_length=8192,
        max_output_tokens=1024,
    )
    return SimpleNamespace(
        model=model,
        team_model=SimpleNamespace(model=model, is_enabled=True),
        model_id=str(model_uuid),
        tokenizer_model_id=model.model_id,
        provider=model.provider,
        context_length=model.context_length,
        max_output_tokens=model.max_output_tokens,
        supports_vision=False,
    )


def _streaming_config(_agent=None):
    return {
        "global_timeout": 10,
        "heartbeat_interval": 1,
        "tool_timeouts": {},
        "idle_timeout": 3,
    }


def _prepared_context():
    compression = SimpleNamespace(
        stage="none",
        actions=None,
        before_tokens=0,
        after_tokens=0,
        pressure_level="normal",
        summary_source_tokens=0,
        summary_result_tokens=0,
        summary_saved_tokens=0,
    )
    return SimpleNamespace(
        messages=[
            LLMMessage(role=LLMMessageRole.USER, content="hello"),
            LLMMessage(role=LLMMessageRole.ASSISTANT, content="ok"),
        ],
        compression=compression,
        token_budget=None,
        protected_indexes=set(),
    )


def _context_plan():
    """Fake build_context_plan result: no summarization, finalize returns the
    prepared provider context."""
    return SimpleNamespace(
        will_summarize=False,
        compression=SimpleNamespace(stage="none"),
        finalize=AsyncMock(return_value=_prepared_context()),
    )


def _tool_call(call_id: str, name: str = "get_current_time") -> ToolCall:
    return ToolCall(
        id=call_id,
        function=FunctionCall(name=name, arguments="{}"),
    )


def _tool_turn_stream(
    tool_call_id: str, final_content: str, tool_name: str = "get_current_time"
):
    """Provider that returns the tool-call turn on the first invocation and
    the final answer on the second, mirroring one model turn per loop
    iteration (a stateful model, not a replayed script)."""

    async def tool_turn(**_kwargs):
        yield ChatStreamChunk(
            id="c1",
            model="unit-model",
            delta=ChatStreamDelta(tool_calls=[_tool_call(tool_call_id, tool_name)]),
            finish_reason=FinishReason.TOOL_CALLS,
            usage=Usage(prompt_tokens=7, completion_tokens=1, total_tokens=8),
        )

    async def final_turn(**_kwargs):
        yield ChatStreamChunk(
            id="c2",
            model="unit-model",
            delta=ChatStreamDelta(content=final_content),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=7, completion_tokens=3, total_tokens=10),
        )

    invocations = {"count": 0}

    def team_stream(**_kwargs):
        invocations["count"] += 1
        return tool_turn() if invocations["count"] == 1 else final_turn()

    return team_stream


@pytest.fixture
def chat_mocks(monkeypatch):
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        team=SimpleNamespace(id=uuid4()),
        rag_mode=RAGMode.AGENTIC,
        enable_attachments=False,
        enable_user_input_request=False,
        max_iterations=2,
        context_compression_config={"emit_sse_events": True},
    )
    conversation = SimpleNamespace(id=uuid4(), title=None)
    user = SimpleNamespace(id=uuid4(), is_active=True, locale="en")
    created: list[StoredMessage] = []

    async def create_message(**values):
        message = StoredMessage(**values)
        created.append(message)
        return message

    monkeypatch.setattr(chat_api.deps, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(
        chat_api, "check_agent_chat_access", AsyncMock(return_value=agent)
    )
    monkeypatch.setattr(
        chat_api, "get_or_create_conversation", AsyncMock(return_value=conversation)
    )
    monkeypatch.setattr(
        chat_api, "get_next_user_branch_parent_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(chat_api.Message, "create", create_message)
    monkeypatch.setattr(chat_api, "update_message_stats", AsyncMock())
    monkeypatch.setattr(
        chat_api,
        "resolve_agent_chat_model",
        AsyncMock(return_value=_model_resolution()),
    )
    monkeypatch.setattr(chat_api, "get_streaming_config", _streaming_config)
    monkeypatch.setattr(
        chat_api, "build_file_content_for_context", AsyncMock(return_value=("", None))
    )
    monkeypatch.setattr(
        chat_api, "get_visible_conversation_messages", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(chat_api, "get_agent_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat_api, "get_tool_display_names", AsyncMock(return_value={}))
    monkeypatch.setattr(
        chat_api, "build_context_plan", AsyncMock(return_value=_context_plan())
    )
    monkeypatch.setattr(
        chat_api, "build_compression_start_event", Mock(return_value=None)
    )
    monkeypatch.setattr(
        chat_api, "build_compression_events", Mock(return_value=(None, None))
    )
    monkeypatch.setattr(chat_api, "get_compression_trigger", Mock(return_value=None))
    monkeypatch.setattr(
        chat_api, "collect_conversation_images", lambda *_args, **_kwargs: ([], [])
    )
    monkeypatch.setattr(
        chat_api, "append_conversation_image_inventory", lambda text, _inv: text
    )
    monkeypatch.setattr(chat_api, "append_generated_images", Mock())
    monkeypatch.setattr(
        chat_api, "send_heartbeat_if_needed", AsyncMock(return_value=(True, 0))
    )
    monkeypatch.setattr(chat_api, "get_prefix_path_before", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat_api, "activate_conversation_branch", AsyncMock())
    monkeypatch.setattr(chat_api, "t", lambda key, **_kwargs: key)
    monkeypatch.setattr(
        chat_api, "_append_asset_manifest", AsyncMock(side_effect=lambda s, **_k: s)
    )
    monkeypatch.setattr(chat_api, "_resolve_message_assets", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat_api, "_attach_message_assets", AsyncMock())
    monkeypatch.setattr(
        chat_api, "_calculate_model_usage", Mock(return_value=(7, 3, 0, 0, 7))
    )
    monkeypatch.setattr(
        chat_api.Conversation, "filter", lambda **_kwargs: UpdateQuery()
    )
    monkeypatch.setattr(chat_api.Agent, "filter", lambda **_kwargs: UpdateQuery())
    monkeypatch.setattr(chat_api.Team, "filter", lambda **_kwargs: UpdateQuery())

    from app.services.sandbox.gateway import sandbox_gateway
    from app.llm import model_manager as mm_module

    monkeypatch.setattr(
        sandbox_gateway, "create_session", AsyncMock(return_value="session")
    )
    monkeypatch.setattr(mm_module, "team_chat", AsyncMock())
    monkeypatch.setattr(mm_module, "team_chat_stream", AsyncMock())
    monkeypatch.setattr(mm_module, "record_stream_usage", AsyncMock())

    return SimpleNamespace(
        agent=agent,
        conversation=conversation,
        user=user,
        created=created,
        model_manager=mm_module,
    )


async def _collect_stream(response):
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    return "".join(chunks)


def _event_names(body: str) -> list[str]:
    return [
        line.split(": ", 1)[1]
        for line in body.splitlines()
        if line.startswith("event: ")
    ]


# ---------- Stream: normal tool round ----------


@pytest.mark.asyncio
async def test_stream_tool_round_event_order_and_round_structure(
    chat_mocks, monkeypatch
):
    """Model -> tool call -> tool result -> final answer keeps event order and
    persists one canonical round: user input, assistant step with tool_calls,
    tool result, canonical final assistant."""
    tool_call_id = "call_1"
    monkeypatch.setattr(
        chat_mocks.model_manager,
        "team_chat_stream",
        _tool_turn_stream(tool_call_id, "the answer"),
    )
    monkeypatch.setattr(
        chat_api, "execute_tool_call", AsyncMock(return_value={"result": "ok"})
    )
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))

    response = await chat_api.chat_stream(
        chat_mocks.agent.id,
        ChatRequest(message="hello"),
        request,
        (chat_mocks.user, None),
    )
    body = await _collect_stream(response)
    events = _event_names(body)

    assert events[0] == "message_start"
    assert events[1] == "tool_call"
    assert events[2] == "tool_result"
    assert events[3] == "content_delta"
    assert events[-1] == "message_end"
    assert "iteration_cap_reached" not in events

    user_msg = chat_mocks.created[0]
    assistant_final = next(
        m
        for m in chat_mocks.created
        if getattr(m.round_role, "value", None) == "assistant_final"
    )
    steps = [m for m in chat_mocks.created if m.round_role is not None]
    assert user_msg.role == MessageRole.USER
    assert user_msg.is_round_canonical is True
    assert user_msg.round_role.value == "user_input"

    assistant_step = next(m for m in steps if m.round_role.value == "assistant_step")
    assert assistant_step.tool_calls == [
        {
            "id": tool_call_id,
            "name": "get_current_time",
            "display_name": "get_current_time",
            "arguments": {},
        }
    ]
    assert assistant_step.is_round_canonical is False

    tool_msgs = [m for m in steps if m.round_role.value == "tool_result"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].tool_call_id == tool_call_id
    assert tool_msgs[0].content == '{"result": "ok"}'
    assert tool_msgs[0].is_round_canonical is False

    assert assistant_final.role == MessageRole.ASSISTANT
    assert assistant_final.content == "the answer"
    assert assistant_final.is_round_canonical is True
    assert assistant_final.round_role.value == "assistant_final"
    assert assistant_final.round_status == MessageRoundStatus.COMPLETED
    assert assistant_final.branch_parent_id == user_msg.id

    # Round indices must be strictly increasing in order of appearance.
    round_ids = {m.round_id for m in chat_mocks.created}
    assert len(round_ids) == 1
    indices = [m.round_index for m in chat_mocks.created]
    assert indices == sorted(indices)

    chat_api.activate_conversation_branch.assert_awaited_once()


# ---------- Stream: tool error result ----------


@pytest.mark.asyncio
async def test_stream_tool_error_result_keeps_round_and_finishes(
    chat_mocks, monkeypatch
):
    """A tool returning an error payload is persisted as the tool result and
    the same round continues to the final answer."""
    tool_call_id = "call_err"
    monkeypatch.setattr(
        chat_mocks.model_manager,
        "team_chat_stream",
        _tool_turn_stream(tool_call_id, "recovered", tool_name="explode"),
    )
    monkeypatch.setattr(
        chat_api, "execute_tool_call", AsyncMock(return_value={"error": "boom"})
    )
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))

    response = await chat_api.chat_stream(
        chat_mocks.agent.id,
        ChatRequest(message="hello"),
        request,
        (chat_mocks.user, None),
    )
    body = await _collect_stream(response)
    events = _event_names(body)

    assert events[-1] == "message_end"
    tool_msgs = [
        m
        for m in chat_mocks.created
        if getattr(m.round_role, "value", None) == "tool_result"
    ]
    assert len(tool_msgs) == 1
    assert "boom" in tool_msgs[0].content
    assistant_final = next(
        m
        for m in chat_mocks.created
        if getattr(m.round_role, "value", None) == "assistant_final"
    )
    assert assistant_final.round_status == MessageRoundStatus.COMPLETED


# ---------- Stream: manual stop via disconnect ----------


@pytest.mark.asyncio
async def test_stream_disconnect_persists_manually_stopped_partial(
    chat_mocks, monkeypatch
):
    """Disconnect mid-stream persists partial content as MANUALLY_STOPPED and
    never emits message_end; the server does not finalize the branch."""

    async def stream(**_kwargs):
        yield ChatStreamChunk(
            id="c1",
            model="unit-model",
            delta=ChatStreamDelta(content="partial"),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=7, completion_tokens=2, total_tokens=9),
        )

    monkeypatch.setattr(chat_mocks.model_manager, "team_chat_stream", stream)
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=True))

    response = await chat_api.chat_stream(
        chat_mocks.agent.id,
        ChatRequest(message="hello"),
        request,
        (chat_mocks.user, None),
    )
    body = await _collect_stream(response)
    events = _event_names(body)

    assert events[0] == "message_start"
    assert "message_end" not in events
    assistant = chat_mocks.created[-1]
    assert assistant.is_manually_stopped is True
    assert assistant.round_status == MessageRoundStatus.MANUALLY_STOPPED
    chat_api.activate_conversation_branch.assert_not_awaited()


# ---------- Non-stream: same round contract ----------


@pytest.mark.asyncio
async def test_nonstream_tool_round_persists_same_round_structure(
    chat_mocks, monkeypatch
):
    """The non-stream path persists the same canonical round structure through
    its own loop."""
    tool_call_id = "ncall_1"
    first = LLMChatResponse(
        id="r1",
        model="unit-model",
        content="planning",
        finish_reason=FinishReason.TOOL_CALLS,
        tool_calls=[_tool_call(tool_call_id)],
        usage=Usage(prompt_tokens=7, completion_tokens=2, total_tokens=9),
    )
    final = LLMChatResponse(
        id="r2",
        model="unit-model",
        content="final answer",
        finish_reason=FinishReason.STOP,
        usage=Usage(prompt_tokens=7, completion_tokens=5, total_tokens=12),
    )
    calls = iter([first, final])

    monkeypatch.setattr(
        chat_mocks.model_manager,
        "team_chat",
        AsyncMock(side_effect=lambda **_kwargs: next(calls)),
    )
    monkeypatch.setattr(
        chat_api, "execute_tool_call", AsyncMock(return_value={"result": "ok"})
    )
    monkeypatch.setattr(
        chat_api, "prepare_model_context", AsyncMock(return_value=_prepared_context())
    )

    result = await chat_api.chat(
        chat_mocks.agent.id,
        ChatRequest(message="hello"),
        (chat_mocks.user, None),
    )

    assert result["data"].message.content == "final answer"
    user_msg = chat_mocks.created[0]
    steps = [
        m
        for m in chat_mocks.created
        if getattr(m.round_role, "value", None) in {"assistant_step", "tool_result"}
    ]
    assert len(steps) == 2
    assert steps[0].round_role.value == "assistant_step"
    assert steps[0].tool_calls[0]["id"] == tool_call_id
    assert steps[1].round_role.value == "tool_result"
    assert steps[1].tool_call_id == tool_call_id
    assistant_final = chat_mocks.created[-1]
    assert assistant_final.round_role.value == "assistant_final"
    assert assistant_final.branch_parent_id == user_msg.id
    assert assistant_final.round_status == MessageRoundStatus.COMPLETED
    chat_api.activate_conversation_branch.assert_awaited_once()


# ---------- Edit: branch version activation ----------


class _Query:
    """Chainable fake Tortoise queryset for the edit/regenerate entry lookup."""

    def __init__(self, result=None, *, count=0, exists=True):
        self.result = result
        self.count_result = count
        self.exists_result = exists
        self.update = AsyncMock(return_value=1)
        self.delete = AsyncMock(return_value=1)
        self.waits = []

    def filter(self, *_args, **_kwargs):
        return self

    def prefetch_related(self, *_args, **_kwargs):
        return self

    def using_db(self, *_args, **_kwargs):
        return self

    def select_for_update(self):
        return self

    async def first(self):
        return self.result

    async def all(self):
        return []

    async def count(self):
        return self.count_result

    async def exists(self):
        return self.exists_result


def _edit_env(monkeypatch):
    """Mock environment for the edit endpoint: new user version created and
    activated; the edited path is the only branch activation."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def transaction():
        yield object()

    user = SimpleNamespace(id=uuid4(), locale="en")
    team_id = uuid4()
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=team_id,
        team=SimpleNamespace(id=team_id),
        rag_mode=RAGMode.OFF,
        max_iterations=1,
        context_compression_config={"emit_sse_events": True},
    )
    conversation = SimpleNamespace(id=uuid4(), agent_id=agent.id)
    original = SimpleNamespace(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content="original question",
        branch_parent_id=None,
        images=[],
        file_urls=[],
    )
    prefix_message = SimpleNamespace(id=uuid4())
    original_reply = SimpleNamespace(id=uuid4())
    edited = SimpleNamespace(id=uuid4())
    assistant = SimpleNamespace(id=uuid4(), save=AsyncMock())
    created = iter([edited, assistant])
    version_query = _Query(count=2)
    active_query = _Query(exists=True)
    cleanup_query = _Query()

    def message_filter(*_args, **kwargs):
        if kwargs == {"id": original.id}:
            return _Query(original)
        if "is_active" in kwargs:
            return active_query
        if "id" in kwargs and len(kwargs) == 1:
            return cleanup_query
        return version_query

    monkeypatch.setattr(chat_api.Message, "filter", message_filter)
    monkeypatch.setattr(
        chat_api.Conversation, "filter", lambda **_kwargs: _Query(conversation)
    )
    monkeypatch.setattr(chat_api.Agent, "filter", lambda **_kwargs: _Query(agent))
    monkeypatch.setattr(chat_api.Team, "filter", lambda **_kwargs: _Query())
    monkeypatch.setattr(chat_api, "in_transaction", transaction)
    monkeypatch.setattr(chat_api, "get_version_root_id", lambda _m: original.id)
    monkeypatch.setattr(
        chat_api,
        "get_prefix_path_before",
        AsyncMock(return_value=[prefix_message]),
    )
    monkeypatch.setattr(
        chat_api,
        "find_descendant_branch_from",
        AsyncMock(return_value=[original, original_reply]),
    )

    async def create_message(**values):
        item = next(created)
        for key, value in values.items():
            setattr(item, key, value)
        if "conversation" in values and not hasattr(item, "conversation_id"):
            item.conversation_id = values["conversation"].id
        return item

    monkeypatch.setattr(
        chat_api.Message, "create", AsyncMock(side_effect=create_message)
    )
    monkeypatch.setattr(chat_api, "get_streaming_config", _streaming_config)
    monkeypatch.setattr(
        chat_api,
        "resolve_agent_chat_model",
        AsyncMock(return_value=_model_resolution()),
    )
    monkeypatch.setattr(chat_api, "get_agent_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat_api, "get_tool_display_names", AsyncMock(return_value={}))
    monkeypatch.setattr(
        chat_api, "build_context_plan", AsyncMock(return_value=_context_plan())
    )
    monkeypatch.setattr(
        chat_api, "build_compression_start_event", Mock(return_value=None)
    )
    monkeypatch.setattr(
        chat_api, "build_compression_events", Mock(return_value=(None, None))
    )
    monkeypatch.setattr(chat_api, "get_compression_trigger", Mock(return_value=None))
    monkeypatch.setattr(
        chat_api, "collect_conversation_images", lambda *_args, **_kwargs: ([], [])
    )
    monkeypatch.setattr(
        chat_api, "append_conversation_image_inventory", lambda text, _inv: text
    )
    monkeypatch.setattr(chat_api, "append_generated_images", Mock())
    monkeypatch.setattr(
        chat_api, "send_heartbeat_if_needed", AsyncMock(return_value=(True, 0))
    )
    monkeypatch.setattr(chat_api, "activate_conversation_branch", AsyncMock())
    monkeypatch.setattr(chat_api, "t", lambda key, **_kwargs: key)
    monkeypatch.setattr(
        chat_api, "_append_asset_manifest", AsyncMock(side_effect=lambda s, **_k: s)
    )
    monkeypatch.setattr(
        chat_api, "_calculate_model_usage", Mock(return_value=(7, 3, 0, 0, 7))
    )
    monkeypatch.setattr(chat_api.AuditLogService, "log", AsyncMock())

    from app.services.sandbox.gateway import sandbox_gateway
    from app.llm import model_manager as mm_module

    monkeypatch.setattr(
        sandbox_gateway, "create_session", AsyncMock(return_value="sandbox-session")
    )
    monkeypatch.setattr(mm_module, "record_stream_usage", AsyncMock())

    return SimpleNamespace(
        agent=agent,
        conversation=conversation,
        user=user,
        original=original,
        edited=edited,
        assistant=assistant,
        model_manager=mm_module,
    )


@pytest.mark.asyncio
async def test_edit_stream_creates_user_version_and_activates_edited_path(
    monkeypatch,
):
    """Edit bumps the user message version, creates a fresh assistant, and
    activates the edited path exactly once."""
    env = _edit_env(monkeypatch)

    async def stream(**_kwargs):
        yield ChatStreamChunk(
            id="c1",
            model="unit-model",
            delta=ChatStreamDelta(content="edited answer"),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=7, completion_tokens=3, total_tokens=10),
        )

    monkeypatch.setattr(env.model_manager, "team_chat_stream", stream)
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))

    response = await chat_api.edit_user_message_stream(
        env.agent.id,
        env.original.id,
        EditMessageRequest(content="edited question"),
        request,
        env.user,
    )
    body = await _collect_stream(response)
    events = _event_names(body)

    assert events[0] == "message_start"
    # The start event carries the edited version identity.
    start_payload = next(
        line
        for line in body.splitlines()
        if line.startswith('data: {"conversation_id"')
    )
    assert '"edited_message_id": "%s"' % env.edited.id in start_payload
    assert '"edited_version_number": 3' in start_payload
    assert events[-1] == "message_end"

    # The edited user message is version 3, parented to the original root,
    # and the assistant is a fresh canonical final.
    assert env.edited.version_number == 3
    assert env.edited.parent_id == env.original.id
    assert env.edited.round_role.value == "user_input"
    assert env.edited.is_round_canonical is True
    assert env.assistant.content == "edited answer"
    assert env.assistant.round_status == MessageRoundStatus.COMPLETED
    assert env.assistant.branch_parent_id == env.edited.id

    # The edited path is activated; restore never runs.
    # First activation commits the new user version; the final activation
    # appends the assistant (edited path). Restore never runs.
    assert chat_api.activate_conversation_branch.await_count == 2
    called_args = chat_api.activate_conversation_branch.await_args.args
    assert called_args[1][-1].id == env.assistant.id


@pytest.mark.asyncio
async def test_edit_stream_model_error_preserves_edited_path_with_error_round(
    monkeypatch,
):
    """A model failure before content preserves the edited user version and its
    assistant under the edited path, marking the round ERROR (the current
    contract; nothing is discarded when fallback content can be stored)."""
    from app.llm.errors import LLMError

    env = _edit_env(monkeypatch)

    async def failing_stream(**_kwargs):
        raise LLMError("boom")
        yield  # pragma: no cover

    monkeypatch.setattr(env.model_manager, "team_chat_stream", failing_stream)
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))

    response = await chat_api.edit_user_message_stream(
        env.agent.id,
        env.original.id,
        EditMessageRequest(content="edited question"),
        request,
        env.user,
    )
    body = await _collect_stream(response)

    # Error event is emitted; the edited user message stays, its assistant is
    # an ERROR round, and the edited path is activated (initial version
    # activation + final edited-path activation).
    assert "event: error" in body
    assert env.edited.version_number == 3
    assert env.assistant.round_status == MessageRoundStatus.ERROR
    assert env.assistant.content  # fallback error content preserved
    assert chat_api.activate_conversation_branch.await_count == 2
    final_call = chat_api.activate_conversation_branch.await_args_list[-1]
    assert final_call.args[1][-1].id == env.assistant.id


# ---------- Regenerate: new assistant version activation ----------


def _regen_env(monkeypatch):
    """Mock environment for regenerate: creates a new assistant version and
    activates the regenerated path."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def transaction():
        yield object()

    user = SimpleNamespace(id=uuid4(), locale="en")
    team_id = uuid4()
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=team_id,
        team=SimpleNamespace(id=team_id),
        rag_mode=RAGMode.OFF,
        max_iterations=1,
        context_compression_config={"emit_sse_events": True},
    )
    conversation = SimpleNamespace(id=uuid4(), agent_id=agent.id)
    user_message = SimpleNamespace(
        id=uuid4(),
        content="question",
        created_at=None,
        role=MessageRole.USER,
    )
    old_assistant = SimpleNamespace(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="old answer",
        branch_parent_id=user_message.id,
        round_status=MessageRoundStatus.COMPLETED,
        version_number=1,
        round_id=None,
        round_index=0,
        round_role=None,
        is_round_canonical=True,
        save=AsyncMock(),
    )
    new_message = SimpleNamespace(id=uuid4(), save=AsyncMock())
    created = iter([new_message])

    def message_filter(*_args, **kwargs):
        if kwargs == {"id": old_assistant.id}:
            return _Query(old_assistant)
        return _Query()

    monkeypatch.setattr(chat_api.Message, "filter", message_filter)
    monkeypatch.setattr(
        chat_api.Conversation, "filter", lambda **_kwargs: _Query(conversation)
    )
    monkeypatch.setattr(chat_api.Agent, "filter", lambda **_kwargs: _Query(agent))
    monkeypatch.setattr(chat_api.Team, "filter", lambda **_kwargs: _Query())
    monkeypatch.setattr(chat_api, "in_transaction", transaction)
    monkeypatch.setattr(chat_api, "get_version_root_id", lambda _m: old_assistant.id)
    monkeypatch.setattr(
        chat_api,
        "get_prefix_path_before",
        AsyncMock(return_value=[user_message]),
    )
    monkeypatch.setattr(
        chat_api,
        "find_descendant_branch_from",
        AsyncMock(return_value=[user_message, old_assistant]),
    )
    monkeypatch.setattr(chat_api, "get_branch_version_count", AsyncMock(return_value=1))

    async def create_message(**values):
        item = next(created)
        for key, value in values.items():
            setattr(item, key, value)
        if "conversation" in values and not hasattr(item, "conversation_id"):
            item.conversation_id = values["conversation"].id
        return item

    monkeypatch.setattr(
        chat_api.Message, "create", AsyncMock(side_effect=create_message)
    )
    monkeypatch.setattr(chat_api, "get_streaming_config", _streaming_config)
    monkeypatch.setattr(
        chat_api,
        "resolve_agent_chat_model",
        AsyncMock(return_value=_model_resolution()),
    )
    monkeypatch.setattr(chat_api, "get_agent_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat_api, "get_tool_display_names", AsyncMock(return_value={}))
    monkeypatch.setattr(
        chat_api, "build_context_plan", AsyncMock(return_value=_context_plan())
    )
    monkeypatch.setattr(
        chat_api, "build_compression_start_event", Mock(return_value=None)
    )
    monkeypatch.setattr(
        chat_api, "build_compression_events", Mock(return_value=(None, None))
    )
    monkeypatch.setattr(chat_api, "get_compression_trigger", Mock(return_value=None))
    monkeypatch.setattr(
        chat_api, "collect_conversation_images", lambda *_args, **_kwargs: ([], [])
    )
    monkeypatch.setattr(
        chat_api, "append_conversation_image_inventory", lambda text, _inv: text
    )
    monkeypatch.setattr(chat_api, "append_generated_images", Mock())
    monkeypatch.setattr(
        chat_api, "send_heartbeat_if_needed", AsyncMock(return_value=(True, 0))
    )
    monkeypatch.setattr(chat_api, "activate_conversation_branch", AsyncMock())
    monkeypatch.setattr(chat_api, "t", lambda key, **_kwargs: key)
    monkeypatch.setattr(
        chat_api, "_append_asset_manifest", AsyncMock(side_effect=lambda s, **_k: s)
    )
    monkeypatch.setattr(
        chat_api, "_calculate_model_usage", Mock(return_value=(7, 3, 0, 0, 7))
    )

    from app.services.sandbox.gateway import sandbox_gateway
    from app.llm import model_manager as mm_module

    monkeypatch.setattr(
        sandbox_gateway, "create_session", AsyncMock(return_value="sandbox-session")
    )
    monkeypatch.setattr(mm_module, "record_stream_usage", AsyncMock())

    return SimpleNamespace(
        agent=agent,
        conversation=conversation,
        user=user,
        old_assistant=old_assistant,
        user_message=user_message,
        new_message=new_message,
        model_manager=mm_module,
    )


@pytest.mark.asyncio
async def test_regenerate_creates_new_assistant_version_and_activates_path(
    monkeypatch,
):
    """Regenerate bumps the assistant version, streams a fresh answer, and
    activates the regenerated path."""
    env = _regen_env(monkeypatch)

    async def stream(**_kwargs):
        yield ChatStreamChunk(
            id="c1",
            model="unit-model",
            delta=ChatStreamDelta(content="regenerated answer"),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=7, completion_tokens=4, total_tokens=11),
        )

    monkeypatch.setattr(env.model_manager, "team_chat_stream", stream)
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))

    response = await chat_api.regenerate_message(
        env.agent.id,
        env.old_assistant.id,
        SimpleNamespace(),
        request,
        env.user,
    )
    body = await _collect_stream(response)
    events = _event_names(body)

    assert events[0] == "message_start"
    start_payload = next(
        line
        for line in body.splitlines()
        if line.startswith('data: {"conversation_id"')
    )
    assert '"message_id": "%s"' % env.new_message.id in start_payload
    assert '"version_number": 2' in start_payload
    assert '"parent_id": "%s"' % env.old_assistant.id in start_payload
    assert events[-1] == "message_end"

    assert env.new_message.version_number == 2
    assert env.new_message.parent_id == env.old_assistant.id
    assert env.new_message.content == "regenerated answer"
    assert env.new_message.branch_parent_id == env.user_message.id
    assert env.new_message.round_status == MessageRoundStatus.COMPLETED

    chat_api.activate_conversation_branch.assert_awaited_once()
    called_args = chat_api.activate_conversation_branch.await_args.args
    assert called_args[1][-1].id == env.new_message.id


# ---------- Compression: ordering at the loop position ----------


@pytest.mark.asyncio
async def test_stream_compression_events_precede_content_at_loop_position(
    chat_mocks, monkeypatch
):
    """compression_start is emitted when the plan summarizes and appears before
    the first content_delta; compression_end follows finalize."""
    compression = SimpleNamespace(
        stage="macro",
        actions=["context_summary"],
        before_tokens=1000,
        after_tokens=200,
        pressure_level="auto_compact",
        summary_source_tokens=800,
        summary_result_tokens=100,
        summary_saved_tokens=700,
        context_limit=4096,
        output_reserve=400,
        safety_margin=100,
    )
    plan = SimpleNamespace(
        will_summarize=True,
        compression=compression,
        finalize=AsyncMock(
            return_value=SimpleNamespace(
                messages=[
                    LLMMessage(role=LLMMessageRole.USER, content="hello"),
                    LLMMessage(
                        role=LLMMessageRole.USER,
                        content="Earlier conversation summary...",
                    ),
                ],
                compression=compression,
                token_budget=None,
                protected_indexes=set(),
            )
        ),
    )
    monkeypatch.setattr(chat_api, "build_context_plan", AsyncMock(return_value=plan))

    start_event = (
        "event: compression_start\n"
        'data: {"stage": "macro", "trigger": "preflight_summary"}\n\n'
    )
    end_event = (
        "event: compression_end\n"
        'data: {"stage": "macro", "trigger": "preflight_summary", '
        '"summary_source_tokens": 800}\n\n'
    )
    monkeypatch.setattr(
        chat_api, "build_compression_start_event", Mock(return_value=start_event)
    )
    monkeypatch.setattr(
        chat_api, "build_compression_events", Mock(return_value=(None, end_event))
    )
    monkeypatch.setattr(
        chat_api, "get_compression_trigger", Mock(return_value="preflight_summary")
    )

    async def stream(**_kwargs):
        yield ChatStreamChunk(
            id="c1",
            model="unit-model",
            delta=ChatStreamDelta(content="answer with summary"),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=7, completion_tokens=3, total_tokens=10),
        )

    monkeypatch.setattr(chat_mocks.model_manager, "team_chat_stream", stream)
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))

    response = await chat_api.chat_stream(
        chat_mocks.agent.id,
        ChatRequest(message="hello"),
        request,
        (chat_mocks.user, None),
    )
    body = await _collect_stream(response)

    start_idx = body.index("event: compression_start")
    end_idx = body.index("event: compression_end")
    content_idx = body.index("event: content_delta")
    assert start_idx < end_idx < content_idx
    assert body.index("event: message_start") < start_idx
