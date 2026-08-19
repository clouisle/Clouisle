from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat as chat_endpoint
from app.llm.types import ChatStreamChunk, ChatStreamDelta, FinishReason
from app.schemas.agent import ChatRequest
from app.schemas.response import BusinessError, ResponseCode


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


class _AsyncStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        item = self._chunks.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _Msg(SimpleNamespace):
    async def save(self, *args, **kwargs):
        return None

    async def delete(self):
        return None


class _ModelMessage(SimpleNamespace):
    def model_dump(self, **kwargs):
        return {"role": "user", "content": "hello"}


class _Request:
    def __init__(self, disconnected=False):
        self.disconnected = disconnected

    async def is_disconnected(self):
        return self.disconnected


class _Query:
    async def update(self, **kwargs):
        self.updated = kwargs
        return None


@pytest.fixture
def chat_env(monkeypatch):
    agent_id = uuid4()
    team_id = uuid4()
    user = SimpleNamespace(id=uuid4(), is_active=True, locale="en")
    agent = SimpleNamespace(
        id=agent_id,
        team_id=team_id,
        team=SimpleNamespace(id=team_id),
        rag_mode="manual",
        enable_attachments=False,
        max_iterations=1,
        enable_user_input_request=False,
    )
    conversation = SimpleNamespace(id=uuid4(), title="Existing")
    created = []

    async def create_message(**kwargs):
        kwargs.setdefault("file_urls", None)
        msg = _Msg(id=uuid4(), **kwargs)
        created.append(msg)
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
    monkeypatch.setattr(chat_endpoint.Message, "create", create_message)
    monkeypatch.setattr(chat_endpoint, "update_message_stats", AsyncMock())
    monkeypatch.setattr(
        chat_endpoint,
        "resolve_agent_chat_model",
        AsyncMock(return_value=_fake_chat_resolution()),
    )
    monkeypatch.setattr(
        chat_endpoint,
        "get_streaming_config",
        lambda agent: {
            "global_timeout": 30,
            "heartbeat_interval": 60,
            "idle_timeout": 30,
            "tool_timeouts": {},
        },
    )
    monkeypatch.setattr(
        "app.services.sandbox.gateway.sandbox_gateway.create_session",
        AsyncMock(return_value="sandbox-1"),
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
        chat_endpoint, "collect_conversation_images", lambda *a, **k: ([], [])
    )
    monkeypatch.setattr(
        chat_endpoint, "append_conversation_image_inventory", lambda msg, inv: msg
    )
    monkeypatch.setattr(chat_endpoint, "get_agent_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        chat_endpoint, "get_tool_display_names", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        chat_endpoint,
        "prepare_model_context",
        AsyncMock(
            return_value=SimpleNamespace(messages=[_ModelMessage()], compression=None)
        ),
    )
    monkeypatch.setattr(
        chat_endpoint, "build_compression_events", lambda **kwargs: (None, None)
    )
    monkeypatch.setattr(
        chat_endpoint, "get_prefix_path_before", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(chat_endpoint, "activate_conversation_branch", AsyncMock())

    monkeypatch.setattr(
        chat_endpoint, "enqueue_session_memory_extraction", lambda *args: None
    )
    monkeypatch.setattr(chat_endpoint.Conversation, "filter", lambda **kwargs: _Query())
    monkeypatch.setattr(chat_endpoint.Agent, "filter", lambda **kwargs: _Query())
    monkeypatch.setattr(chat_endpoint.Team, "filter", lambda **kwargs: _Query())

    return SimpleNamespace(
        agent_id=agent_id,
        user=user,
        agent=agent,
        conversation=conversation,
        created=created,
    )


class AsyncMock:
    def __init__(self, return_value=None, side_effect=None):
        self.return_value = return_value
        self.side_effect = side_effect
        self.await_count = 0
        self.await_args_list = []

    async def __call__(self, *args, **kwargs):
        self.await_count += 1
        self.await_args_list.append((args, kwargs))
        if self.side_effect:
            if isinstance(self.side_effect, list):
                value = self.side_effect.pop(0)
                if isinstance(value, Exception):
                    raise value
                return value
            raise self.side_effect
        return self.return_value


@pytest.mark.anyio
async def test_inactive_user_short_circuits_before_api_key_access(monkeypatch):
    api_key_check = AsyncMock()
    monkeypatch.setattr(chat_endpoint.deps, "check_api_key_agent_access", api_key_check)
    inactive = SimpleNamespace(is_active=False)

    with pytest.raises(BusinessError) as exc:
        await chat_endpoint.chat(
            uuid4(), ChatRequest(message="hello"), (inactive, None)
        )

    assert exc.value.code == ResponseCode.INACTIVE_USER
    assert api_key_check.await_count == 0


@pytest.mark.anyio
async def test_stream_finish_length_emits_truncation_and_records_zero_usage(
    monkeypatch, chat_env
):
    record_usage = AsyncMock()
    monkeypatch.setattr(
        chat_endpoint,
        "send_heartbeat_if_needed",
        AsyncMock(return_value=(True, 0.0)),
    )
    monkeypatch.setattr(
        chat_endpoint, "iter_with_idle_timeout", lambda stream, **kwargs: stream
    )
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream",
        lambda **kwargs: _AsyncStream(
            [
                ChatStreamChunk(
                    id="chunk-1",
                    model="fake",
                    delta=ChatStreamDelta(),
                    finish_reason=FinishReason.LENGTH,
                )
            ]
        ),
    )
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat",
        AsyncMock(return_value=SimpleNamespace(reasoning_content=None, content=None)),
    )
    monkeypatch.setattr("app.llm.model_manager.record_stream_usage", record_usage)

    response = await chat_endpoint.chat_stream(
        chat_env.agent_id,
        ChatRequest(message="hello"),
        _Request(),
        (chat_env.user, None),
    )
    body = "".join([chunk async for chunk in response.body_iterator])

    assert "event: output_truncated" in body
    assert "event: message_end" in body
    assert record_usage.await_count == 0
    assert chat_env.created[1].token_usage == {
        "prompt": 8,
        "completion": 0,
        "cache_read": 0,
        "cache_creation": 0,
        "total_input": 8,
    }
    assert chat_env.created[1].is_manually_stopped is False


@pytest.mark.anyio
async def test_stream_initial_heartbeat_disconnect_persists_stopped_message(
    monkeypatch, chat_env
):
    monkeypatch.setattr(
        chat_endpoint,
        "send_heartbeat_if_needed",
        AsyncMock(return_value=(False, 0.0)),
    )

    response = await chat_endpoint.chat_stream(
        chat_env.agent_id,
        ChatRequest(message="hello"),
        _Request(disconnected=True),
        (chat_env.user, None),
    )
    body = "".join([chunk async for chunk in response.body_iterator])

    assert "event: message_start" in body
    assert "event: message_end" not in body
    assert chat_env.created[1].is_manually_stopped is True
    assert (
        chat_env.created[1].round_status
        == chat_endpoint.MessageRoundStatus.MANUALLY_STOPPED
    )


@pytest.mark.anyio
@pytest.mark.parametrize("field", ["asset_id", "asset_ref"])
async def test_stream_does_not_persist_message_for_invalid_attachment(
    monkeypatch, chat_env, field
):
    chat_env.agent.enable_attachments = True
    resolver = "get_authorized" if field == "asset_id" else "resolve_ref"
    monkeypatch.setattr(
        chat_endpoint.asset_service,
        resolver,
        AsyncMock(
            side_effect=BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="file_not_found",
                status_code=404,
            )
        ),
    )
    attachment = {
        "url": "current.png",
        field: str(uuid4()) if field == "asset_id" else "a1b2",
    }

    response = await chat_endpoint.chat_stream(
        chat_env.agent_id,
        ChatRequest(message="invalid attachment", images=[attachment]),
        _Request(),
        (chat_env.user, None),
    )
    body = "".join([chunk async for chunk in response.body_iterator])

    assert "event: error" in body
    assert chat_env.created == []
