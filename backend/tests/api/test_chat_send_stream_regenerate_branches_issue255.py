from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.models.agent import MessageRole
from app.schemas.agent import ChatRequest, RegenerateRequest


class Query:
    def __init__(self, result=None):
        self.result = result

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.result


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", [chat.chat, chat.chat_stream])
async def test_send_and_stream_check_api_key_before_agent_lookup(monkeypatch, endpoint):
    agent_id = uuid4()
    api_key = SimpleNamespace(id=uuid4())
    current_user = SimpleNamespace(is_active=True)
    access_check = AsyncMock()
    agent_lookup = AsyncMock(side_effect=RuntimeError("stop after preflight"))
    monkeypatch.setattr(chat.deps, "check_api_key_agent_access", access_check)
    monkeypatch.setattr(chat, "check_agent_chat_access", agent_lookup)

    args = [agent_id, ChatRequest(message="hello")]
    if endpoint is chat.chat_stream:
        args.append(SimpleNamespace())
    args.append((current_user, api_key))

    with pytest.raises(RuntimeError, match="stop after preflight"):
        await endpoint(*args)

    access_check.assert_awaited_once_with(api_key, agent_id)
    agent_lookup.assert_awaited_once_with(agent_id, current_user)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("message", "conversation", "agent", "prefix", "msg_key", "status_code"),
    [
        (None, None, None, [], "message_not_found", 404),
        (
            SimpleNamespace(role=MessageRole.USER),
            None,
            None,
            [],
            "can_only_regenerate_assistant",
            400,
        ),
        (
            SimpleNamespace(role=MessageRole.ASSISTANT, conversation_id=uuid4()),
            None,
            None,
            [],
            "access_denied",
            403,
        ),
        (
            SimpleNamespace(role=MessageRole.ASSISTANT, conversation_id=uuid4()),
            SimpleNamespace(agent_id=uuid4()),
            None,
            [],
            "agent_not_found",
            404,
        ),
        (
            SimpleNamespace(role=MessageRole.ASSISTANT, conversation_id=uuid4()),
            SimpleNamespace(agent_id=uuid4()),
            SimpleNamespace(),
            [],
            "no_user_message_found",
            400,
        ),
    ],
)
async def test_regenerate_rejects_invalid_message_context(
    monkeypatch, message, conversation, agent, prefix, msg_key, status_code
):
    current_user = SimpleNamespace(id=uuid4())
    message_filter = MagicMock(return_value=Query(message))
    conversation_filter = MagicMock(return_value=Query(conversation))
    agent_filter = MagicMock(return_value=Query(agent))
    prefix_lookup = AsyncMock(return_value=prefix)
    monkeypatch.setattr(chat.Message, "filter", message_filter)
    monkeypatch.setattr(chat.Conversation, "filter", conversation_filter)
    monkeypatch.setattr(chat.Agent, "filter", agent_filter)
    monkeypatch.setattr(chat, "get_prefix_path_before", prefix_lookup)

    with pytest.raises(chat.BusinessError) as error:
        await chat.regenerate_message(
            uuid4(),
            uuid4(),
            RegenerateRequest(),
            SimpleNamespace(),
            current_user,
        )

    assert error.value.msg_key == msg_key
    assert error.value.status_code == status_code
