from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.models.agent import MessageRole, MessageRoundStatus
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, result=None, items=None, count=0):
        self.result = result
        self.items = items or []
        self.total = count

    def filter(self, *_args, **_kwargs):
        return self

    def prefetch_related(self, *_relations):
        return self

    async def first(self):
        return self.result

    async def all(self):
        return self.items

    async def count(self):
        return self.total


def message(**overrides):
    values = {
        "id": uuid4(),
        "conversation_id": uuid4(),
        "role": MessageRole.USER,
        "content": "hello",
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
        "created_at": datetime.now(UTC),
        "round_id": None,
        "round_index": 0,
        "round_role": None,
        "is_round_canonical": True,
        "iteration_index": None,
        "round_status": MessageRoundStatus.COMPLETED,
        "branch_parent_id": None,
        "parent_id": None,
        "is_active": True,
        "version_number": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_message_version_helpers_sort_count_and_build_output(monkeypatch):
    root = message(version_number=1)
    child = message(parent_id=root.id, version_number=2, content="edited")
    filter_mock = MagicMock(
        side_effect=[Query(items=[root]), Query(items=[child]), Query(count=1)]
    )
    monkeypatch.setattr(chat.Message, "filter", filter_mock)

    versions = await chat.get_message_versions(child)
    count = await chat.get_version_count(child)

    assert [item.id for item in versions] == [root.id, child.id]
    assert [item.content for item in versions] == ["hello", "edited"]
    assert count == 2
    assert filter_mock.call_args_list[0].kwargs == {"id": root.id}
    assert filter_mock.call_args_list[1].kwargs == {"parent_id": root.id}

    monkeypatch.setattr(chat, "get_version_count", AsyncMock(return_value=2))
    get_versions = AsyncMock(return_value=versions)
    monkeypatch.setattr(chat, "get_message_versions", get_versions)

    without_versions = await chat.build_message_out_with_versions(child)
    with_versions = await chat.build_message_out_with_versions(
        child, include_versions=True
    )

    assert without_versions.version_count == 2
    assert without_versions.versions is None
    assert with_versions.versions == versions
    assert with_versions.round_status == MessageRoundStatus.COMPLETED.value
    get_versions.assert_awaited_once_with(child)


@pytest.mark.asyncio
async def test_get_message_version_list_error_and_success_branches(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    message_id = uuid4()
    agent_id = uuid4()

    monkeypatch.setattr(chat.Message, "filter", MagicMock(return_value=Query()))
    with pytest.raises(BusinessError) as caught:
        await chat.get_message_version_list(agent_id, message_id, user)
    assert caught.value.code == ResponseCode.NOT_FOUND

    current = message(id=message_id)
    monkeypatch.setattr(chat.Message, "filter", MagicMock(return_value=Query(current)))
    monkeypatch.setattr(chat.Conversation, "filter", MagicMock(return_value=Query()))
    with pytest.raises(BusinessError) as caught:
        await chat.get_message_version_list(agent_id, message_id, user)
    assert caught.value.code == ResponseCode.FORBIDDEN

    expected = [SimpleNamespace(id=current.id)]
    monkeypatch.setattr(
        chat.Conversation, "filter", MagicMock(return_value=Query(object()))
    )
    get_versions = AsyncMock(return_value=expected)
    monkeypatch.setattr(chat, "get_message_versions", get_versions)

    result = await chat.get_message_version_list(agent_id, message_id, user)

    assert result["data"] == expected
    get_versions.assert_awaited_once_with(current)


@pytest.mark.asyncio
async def test_switch_message_version_rejects_invalid_requests(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    agent_id = uuid4()
    message_id = uuid4()
    version_id = uuid4()
    request = SimpleNamespace(version_id=version_id)

    monkeypatch.setattr(chat.Message, "filter", MagicMock(return_value=Query()))
    with pytest.raises(BusinessError) as caught:
        await chat.switch_message_version(agent_id, message_id, request, user)
    assert caught.value.msg_key == "message_not_found"

    current = message(id=message_id)
    monkeypatch.setattr(chat.Message, "filter", MagicMock(return_value=Query(current)))
    monkeypatch.setattr(chat.Conversation, "filter", MagicMock(return_value=Query()))
    with pytest.raises(BusinessError) as caught:
        await chat.switch_message_version(agent_id, message_id, request, user)
    assert caught.value.msg_key == "access_denied"

    monkeypatch.setattr(
        chat.Conversation, "filter", MagicMock(return_value=Query(object()))
    )
    monkeypatch.setattr(
        chat.Message,
        "filter",
        MagicMock(side_effect=[Query(current), Query()]),
    )
    with pytest.raises(BusinessError) as caught:
        await chat.switch_message_version(agent_id, message_id, request, user)
    assert caught.value.msg_key == "version_not_found"

    other = message(id=version_id)
    monkeypatch.setattr(
        chat.Message,
        "filter",
        MagicMock(side_effect=[Query(current), Query(other)]),
    )
    monkeypatch.setattr(
        chat, "get_version_root_id", MagicMock(side_effect=[uuid4(), uuid4()])
    )
    with pytest.raises(BusinessError) as caught:
        await chat.switch_message_version(agent_id, message_id, request, user)
    assert caught.value.msg_key == "version_not_in_group"


@pytest.mark.asyncio
async def test_switch_message_version_activates_target_branch(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    current = message()
    target = message(parent_id=current.id, version_number=2)
    monkeypatch.setattr(
        chat.Message,
        "filter",
        MagicMock(side_effect=[Query(current), Query(target), Query(current)]),
    )
    monkeypatch.setattr(
        chat.Conversation, "filter", MagicMock(return_value=Query(object()))
    )
    monkeypatch.setattr(chat, "get_version_root_id", MagicMock(return_value=current.id))
    prefix = [message()]
    descendant = [message()]
    monkeypatch.setattr(chat, "get_prefix_path_before", AsyncMock(return_value=prefix))
    monkeypatch.setattr(
        chat, "find_descendant_branch_from", AsyncMock(return_value=descendant)
    )
    activate = AsyncMock()
    monkeypatch.setattr(chat, "activate_conversation_branch", activate)
    output = message()
    build = AsyncMock(return_value=output)
    monkeypatch.setattr(chat, "build_message_out_with_versions", build)

    result = await chat.switch_message_version(
        uuid4(), current.id, SimpleNamespace(version_id=target.id), user
    )

    assert result["data"] is output
    activate.assert_awaited_once_with(current.conversation_id, [*prefix, *descendant])
    build.assert_awaited_once_with(target, include_versions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("current", "content", "conversation", "agent", "msg_key"),
    [
        (None, "edited", None, None, "message_not_found"),
        (
            message(role=MessageRole.ASSISTANT),
            "edited",
            None,
            None,
            "can_only_edit_user_message",
        ),
        (message(), "   ", None, None, "message_content_required"),
        (message(), "edited", None, None, "access_denied"),
        (message(), "edited", object(), None, "agent_not_found"),
    ],
)
async def test_edit_user_message_stream_validation_branches(
    monkeypatch, current, content, conversation, agent, msg_key
):
    monkeypatch.setattr(chat.Message, "filter", MagicMock(return_value=Query(current)))
    monkeypatch.setattr(
        chat.Conversation, "filter", MagicMock(return_value=Query(conversation))
    )
    monkeypatch.setattr(chat.Agent, "filter", MagicMock(return_value=Query(agent)))

    with pytest.raises(BusinessError) as caught:
        await chat.edit_user_message_stream(
            uuid4(),
            uuid4(),
            SimpleNamespace(content=content),
            SimpleNamespace(),
            SimpleNamespace(id=uuid4()),
        )

    assert caught.value.msg_key == msg_key
