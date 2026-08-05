from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat as chat_endpoint
from app.llm.types import ChatResponse as LLMChatResponse
from app.llm.types import FinishReason, FunctionCall, ToolCall, Usage
from app.models.agent import MessageRoundStatus, RAGMode
from app.schemas.agent import ChatRequest


class _AsyncUpdateQuery:
    def __init__(self):
        self.calls = []

    def update(self, **kwargs):
        self.calls.append(kwargs)
        return self

    def __await__(self):
        async def _done():
            return 1

        return _done().__await__()


class _FakeMessage:
    created = []

    def __init__(self, **kwargs):
        self.id = uuid4()
        self.conversation_id = kwargs["conversation"].id
        self.created_at = chat_endpoint.now_utc()
        self.is_active = True
        self.version_number = 1
        self.version_count = 1
        self.parent_id = None
        self.steps = None
        self.versions = None
        self.__dict__.update(kwargs)
        self.role = kwargs["role"].value
        self.round_role = kwargs.get("round_role")
        if hasattr(self.round_role, "value"):
            self.round_role = self.round_role.value
        self.round_status = kwargs.get("round_status")
        if hasattr(self.round_status, "value"):
            self.round_status = self.round_status.value
        self.images = kwargs.get("images")
        self.file_urls = kwargs.get("file_urls")
        self.tool_calls = kwargs.get("tool_calls")
        self.tool_call_id = kwargs.get("tool_call_id")
        self.tool_name = kwargs.get("tool_name")
        self.reasoning_content = kwargs.get("reasoning_content")
        self.model_used = kwargs.get("model_used")
        self.token_usage = kwargs.get("token_usage")
        self.duration_ms = kwargs.get("duration_ms")
        self.first_token_ms = kwargs.get("first_token_ms")
        self.rag_context = kwargs.get("rag_context")
        self.round_id = kwargs.get("round_id")
        self.round_index = kwargs.get("round_index", 0)
        self.is_round_canonical = kwargs.get("is_round_canonical", False)
        self.iteration_index = kwargs.get("iteration_index")
        self.branch_parent_id = kwargs.get("branch_parent_id")

    @classmethod
    async def create(cls, **kwargs):
        message = cls(**kwargs)
        cls.created.append(message)
        return message

    async def save(self, update_fields=None):
        return None


@pytest.mark.asyncio
async def test_chat_tool_loop_terminal_message_when_max_iterations_reached(monkeypatch):
    _FakeMessage.created = []
    agent_id = uuid4()
    user = SimpleNamespace(id=uuid4(), is_active=True, locale="en")
    agent = SimpleNamespace(
        id=agent_id,
        team_id=uuid4(),
        rag_mode=RAGMode.OFF,
        enable_attachments=False,
        max_iterations=1,
        enable_user_input_request=False,
    )
    conversation = SimpleNamespace(id=uuid4(), title="Existing")
    model = SimpleNamespace(
        id=uuid4(),
        is_enabled=True,
        provider="openai",
        model_id="gpt-test",
        capabilities={},
        context_length=4096,
        max_output_tokens=512,
    )
    prepared_context = SimpleNamespace(messages=[])
    model_resolution = SimpleNamespace(
        model=model,
        team_model=SimpleNamespace(model=model, is_enabled=True),
        model_id=str(model.id),
        tokenizer_model_id=model.model_id,
        provider=model.provider,
        context_length=model.context_length,
        max_output_tokens=model.max_output_tokens,
        supports_vision=False,
    )
    response = LLMChatResponse(
        id="resp-1",
        model="openai/gpt-test",
        content="need tool",
        tool_calls=[
            ToolCall(
                id="call-1",
                type="function",
                function=FunctionCall(name="lookup", arguments="not-json"),
            )
        ],
        finish_reason=FinishReason.TOOL_CALLS,
        usage=Usage(prompt_tokens=3, completion_tokens=4, total_tokens=7),
    )
    conversation_updates = _AsyncUpdateQuery()
    agent_updates = _AsyncUpdateQuery()

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(chat_endpoint.deps, "check_api_key_agent_access", _noop)
    monkeypatch.setattr(chat_endpoint, "check_agent_chat_access", _noop)
    monkeypatch.setattr(chat_endpoint, "get_or_create_conversation", _noop)
    monkeypatch.setattr(chat_endpoint, "perform_rag_retrieval", _noop)
    monkeypatch.setattr(chat_endpoint, "Message", _FakeMessage)
    monkeypatch.setattr(chat_endpoint, "update_message_stats", _noop)
    monkeypatch.setattr(
        chat_endpoint,
        "resolve_agent_chat_model",
        lambda agent: _awaitable(model_resolution),
    )
    monkeypatch.setattr(
        chat_endpoint,
        "get_streaming_config",
        lambda agent: {"tool_timeouts": {}},
    )
    monkeypatch.setattr(
        "app.services.sandbox.gateway.sandbox_gateway.create_session",
        lambda **kwargs: _awaitable("sandbox-session"),
    )
    monkeypatch.setattr(
        chat_endpoint,
        "build_file_content_for_context",
        lambda **kwargs: _awaitable(("", None)),
    )
    monkeypatch.setattr(
        chat_endpoint,
        "get_visible_conversation_messages",
        lambda conversation_id: _awaitable([]),
    )
    monkeypatch.setattr(
        chat_endpoint, "collect_conversation_images", lambda *a, **k: ([], [])
    )
    monkeypatch.setattr(
        chat_endpoint, "append_conversation_image_inventory", lambda m, i: m
    )
    monkeypatch.setattr(chat_endpoint, "get_agent_tools", lambda agent: _awaitable([]))
    monkeypatch.setattr(
        chat_endpoint, "get_tool_display_names", lambda *a: _awaitable({})
    )
    monkeypatch.setattr(
        chat_endpoint, "prepare_model_context", lambda **k: _awaitable(prepared_context)
    )
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat", lambda **k: _awaitable(response)
    )
    monkeypatch.setattr(
        chat_endpoint,
        "execute_tool_call",
        lambda *a, **k: _awaitable({"ok": True}),
    )
    monkeypatch.setattr(
        chat_endpoint, "get_tool_execution_payloads", lambda r: (r, "tool-ok")
    )
    monkeypatch.setattr(chat_endpoint, "append_generated_images", lambda *a, **k: None)
    monkeypatch.setattr(
        chat_endpoint.Conversation, "filter", lambda **k: conversation_updates
    )
    monkeypatch.setattr(chat_endpoint.Agent, "filter", lambda **k: agent_updates)
    monkeypatch.setattr(
        chat_endpoint, "get_prefix_path_before", lambda message: _awaitable([])
    )
    monkeypatch.setattr(chat_endpoint, "activate_conversation_branch", _noop)

    monkeypatch.setattr(
        chat_endpoint, "enqueue_session_memory_extraction", lambda *a: None
    )
    monkeypatch.setattr(
        chat_endpoint,
        "build_max_iterations_terminal_content",
        lambda locale: "limit hit",
    )
    monkeypatch.setattr(
        chat_endpoint,
        "get_next_user_branch_parent_id",
        lambda conversation: _awaitable(None),
    )
    monkeypatch.setattr(
        chat_endpoint, "check_agent_chat_access", lambda *a: _awaitable(agent)
    )
    monkeypatch.setattr(
        chat_endpoint, "get_or_create_conversation", lambda *a: _awaitable(conversation)
    )

    result = await chat_endpoint.chat(
        agent_id,
        ChatRequest(message="run tool"),
        auth_result=(user, None),
    )

    final_message = _FakeMessage.created[-1]
    assert result["data"].message.content == "limit hit"
    assert final_message.round_status == MessageRoundStatus.MAX_ITERATIONS_REACHED.value
    assert final_message.reasoning_content is None
    assert result["data"].usage == {
        "prompt_tokens": 3,
        "completion_tokens": 4,
        "total_tokens": 7,
    }


def _awaitable(value):
    async def _inner():
        return value

    return _inner()
