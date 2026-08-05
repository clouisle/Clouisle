import pytest
from types import SimpleNamespace
from uuid import uuid4

import app.llm as llm_package
from app.api.v1.endpoints import chat as chat_endpoint
from app.llm.types import (
    ChatResponse as LLMChatResponse,
    ChatStreamChunk,
    ChatStreamDelta,
    FinishReason,
    FunctionCall,
    Message as LLMMessage,
    ToolCall,
    Usage,
)
from app.schemas.agent import ChatRequest


class Query:
    async def update(self, **kwargs):
        self.updated = kwargs


class FakeModel:
    @classmethod
    def filter(cls, **kwargs):
        return Query()


class SavedMessage(SimpleNamespace):
    async def save(self, *args, **kwargs):
        self.saved = True

    async def delete(self):
        self.deleted = True


class FakeMessage:
    created = []

    @classmethod
    async def create(cls, **kwargs):
        msg = SavedMessage(id=uuid4(), **kwargs)
        cls.created.append(msg)
        return msg


class Request:
    def __init__(self, disconnects=None):
        self.disconnects = iter(disconnects or [])

    async def is_disconnected(self):
        return next(self.disconnects, False)


async def stream(chunks):
    for chunk in chunks:
        yield chunk


@pytest.fixture
def patched_chat_stream(monkeypatch):
    FakeMessage.created = []
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        team=SimpleNamespace(id=uuid4()),
        rag_mode="off",
        enable_attachments=False,
        max_iterations=2,
        context_compression_config=None,
    )
    user = SimpleNamespace(id=uuid4(), is_active=True, locale="en")
    conversation = SimpleNamespace(id=uuid4(), title=None)
    model = SimpleNamespace(
        id=uuid4(),
        is_enabled=True,
        provider="test",
        model_id="model",
        context_length=4096,
        max_output_tokens=256,
        capabilities={},
    )
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
    prepared = SimpleNamespace(
        messages=[LLMMessage(role="user", content="hello")],
        compression=None,
    )

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(chat_endpoint.deps, "check_api_key_agent_access", noop)
    monkeypatch.setattr(chat_endpoint, "check_agent_chat_access", AsyncReturn(agent))
    monkeypatch.setattr(
        chat_endpoint, "get_or_create_conversation", AsyncReturn(conversation)
    )
    monkeypatch.setattr(
        chat_endpoint,
        "get_streaming_config",
        lambda agent: {
            "global_timeout": 30,
            "heartbeat_interval": 999,
            "idle_timeout": 30,
            "tool_timeouts": {},
        },
    )
    from app.services.sandbox.gateway import sandbox_gateway

    monkeypatch.setattr(sandbox_gateway, "create_session", AsyncReturn("session-1"))
    monkeypatch.setattr(
        chat_endpoint, "build_file_content_for_context", AsyncReturn(("", None))
    )
    monkeypatch.setattr(
        chat_endpoint,
        "resolve_agent_chat_model",
        AsyncReturn(model_resolution),
    )
    monkeypatch.setattr(
        chat_endpoint, "get_visible_conversation_messages", AsyncReturn([])
    )
    monkeypatch.setattr(
        chat_endpoint, "collect_conversation_images", lambda *a, **k: ([], [])
    )
    monkeypatch.setattr(
        chat_endpoint,
        "append_conversation_image_inventory",
        lambda message, inventory: message,
    )
    monkeypatch.setattr(
        chat_endpoint,
        "get_agent_tools",
        AsyncReturn(
            [
                {
                    "function": {
                        "name": "lookup",
                        "description": "Lookup",
                        "parameters": {},
                    }
                }
            ]
        ),
    )
    monkeypatch.setattr(
        chat_endpoint, "get_tool_display_names", AsyncReturn({"lookup": "Lookup"})
    )
    monkeypatch.setattr(
        chat_endpoint, "send_heartbeat_if_needed", AsyncReturn((True, 0))
    )
    monkeypatch.setattr(chat_endpoint, "prepare_model_context", AsyncReturn(prepared))
    monkeypatch.setattr(
        chat_endpoint, "build_compression_events", lambda **kwargs: (None, None)
    )
    monkeypatch.setattr(
        chat_endpoint, "iter_with_idle_timeout", lambda source, **kwargs: source
    )
    monkeypatch.setattr(
        chat_endpoint, "get_next_user_branch_parent_id", AsyncReturn(None)
    )
    monkeypatch.setattr(chat_endpoint, "get_prefix_path_before", AsyncReturn([]))
    monkeypatch.setattr(chat_endpoint, "activate_conversation_branch", noop)

    monkeypatch.setattr(
        chat_endpoint, "enqueue_session_memory_extraction", lambda *a, **k: None
    )
    monkeypatch.setattr(chat_endpoint, "Message", FakeMessage)
    monkeypatch.setattr(chat_endpoint, "Conversation", FakeModel)
    monkeypatch.setattr(chat_endpoint, "Agent", FakeModel)
    monkeypatch.setattr(chat_endpoint, "Team", FakeModel)
    return SimpleNamespace(user=user, agent=agent)


class AsyncReturn:
    def __init__(self, value):
        self.value = value
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.value


def chunk(**delta):
    return ChatStreamChunk(
        id="chunk-1",
        model="test/model",
        delta=ChatStreamDelta(**delta),
    )


async def collect_events(response):
    return [part async for part in response.body_iterator]


@pytest.mark.anyio
async def test_stream_empty_chunks_fallback_emits_reasoning_and_content(
    patched_chat_stream, monkeypatch
):
    manager = SimpleNamespace(
        team_chat_stream=lambda **kwargs: stream([]),
        team_chat=AsyncReturn(
            LLMChatResponse(
                id="fallback-1",
                model="test/model",
                content="fallback answer",
                reasoning_content="fallback thought",
                finish_reason=FinishReason.STOP,
                usage=Usage(prompt_tokens=4, completion_tokens=8, total_tokens=12),
            )
        ),
        record_stream_usage=AsyncReturn(None),
    )
    monkeypatch.setattr(llm_package, "model_manager", manager)

    response = await chat_endpoint.chat_stream(
        patched_chat_stream.agent.id,
        ChatRequest(message="hello"),
        Request(),
        (patched_chat_stream.user, None),
    )
    events = "".join(await collect_events(response))

    assert "event: reasoning_start" in events
    assert "fallback thought" in events
    assert "fallback answer" in events
    assert "event: message_end" in events
    assert manager.team_chat.calls


@pytest.mark.anyio
async def test_stream_skips_empty_tool_name_and_parses_bad_arguments_to_empty_dict(
    patched_chat_stream, monkeypatch
):
    tool_calls = [
        ToolCall(id="blank", function=FunctionCall(name="", arguments="{")),
        ToolCall(id="valid", function=FunctionCall(name="lookup", arguments="{")),
    ]
    manager = SimpleNamespace(
        team_chat_stream=lambda **kwargs: stream(
            [
                chunk(tool_calls=tool_calls),
                ChatStreamChunk(
                    id="chunk-2",
                    model="test/model",
                    delta=ChatStreamDelta(),
                    finish_reason=FinishReason.TOOL_CALLS,
                ),
                chunk(content="done"),
            ]
        ),
        team_chat=AsyncReturn(None),
        record_stream_usage=AsyncReturn(None),
    )
    monkeypatch.setattr(llm_package, "model_manager", manager)
    monkeypatch.setattr(
        chat_endpoint,
        "execute_tool_call",
        AsyncReturn(
            {
                "kind": "media.image",
                "success": True,
                "images": [{"image": {"url": "/generated.png"}}],
            }
        ),
    )

    response = await chat_endpoint.chat_stream(
        patched_chat_stream.agent.id,
        ChatRequest(message="hello"),
        Request(),
        (patched_chat_stream.user, None),
    )
    events = "".join(await collect_events(response))

    assert '"tool_call_id": "valid"' in events
    assert '"arguments": {}' in events
    assert '"tool_call_id": "blank"' not in events
    assert "event: media_result" in events
    assert "event: message_end" in events
