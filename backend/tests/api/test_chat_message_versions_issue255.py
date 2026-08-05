from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.schemas.agent import SwitchVersionRequest


class _Query:
    def __init__(self, *, first=None, all=None, count=0):
        self._first = first
        self._all = all or []
        self._count = count
        self.filter_calls = []

    def filter(self, *_args, **_kwargs):
        self.filter_calls.append((_args, _kwargs))
        return self

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self._first

    async def all(self):
        return self._all

    async def count(self):
        return self._count


def _message(*, parent_id=None, version_number=1, is_active=True, content="text"):
    return SimpleNamespace(
        id=uuid4(),
        conversation_id=uuid4(),
        parent_id=parent_id,
        version_number=version_number,
        is_active=is_active,
        content=content,
        created_at=datetime.now(UTC),
    )


@pytest.mark.anyio
async def test_get_message_versions_returns_root_and_children_in_version_order():
    root = _message(version_number=1, content="original")
    third = _message(parent_id=root.id, version_number=3, content="third")
    second = _message(parent_id=root.id, version_number=2, content="second")
    child_query = _Query(all=[third, second])
    message_model = MagicMock()
    message_model.filter.side_effect = [
        _Query(all=[root]),
        child_query,
    ]

    with patch.object(chat, "Message", message_model):
        versions = await chat.get_message_versions(second)

    assert [version.id for version in versions] == [root.id, second.id, third.id]
    assert [version.content for version in versions] == ["original", "second", "third"]
    message_model.filter.assert_any_call(id=root.id)
    message_model.filter.assert_any_call(parent_id=root.id)
    assert len(child_query.filter_calls) == 1


@pytest.mark.anyio
async def test_message_version_list_rejects_missing_message():
    message_model = MagicMock()
    message_model.filter.return_value = _Query(first=None)

    with (
        patch.object(chat, "Message", message_model),
        pytest.raises(chat.BusinessError) as error,
    ):
        await chat.get_message_version_list(uuid4(), uuid4(), SimpleNamespace())

    assert error.value.msg_key == "message_not_found"
    assert error.value.status_code == 404


@pytest.mark.anyio
async def test_message_version_list_requires_conversation_ownership():
    message = _message()
    message_model = MagicMock()
    message_model.filter.return_value = _Query(first=message)
    conversation_model = MagicMock()
    conversation_model.filter.return_value = _Query(first=None)

    with (
        patch.object(chat, "Message", message_model),
        patch.object(chat, "Conversation", conversation_model),
        pytest.raises(chat.BusinessError) as error,
    ):
        await chat.get_message_version_list(uuid4(), message.id, SimpleNamespace())

    assert error.value.msg_key == "access_denied"
    assert error.value.status_code == 403


@pytest.mark.anyio
async def test_message_version_list_returns_owned_version_group():
    user = SimpleNamespace(id=uuid4())
    root = _message(version_number=1)
    child = _message(parent_id=root.id, version_number=2)
    message_model = MagicMock()
    message_model.filter.side_effect = [
        _Query(first=child),
        _Query(all=[root]),
        _Query(all=[child]),
    ]
    conversation_model = MagicMock()
    conversation_model.filter.return_value = _Query(
        first=SimpleNamespace(id=root.conversation_id)
    )

    with (
        patch.object(chat, "Message", message_model),
        patch.object(chat, "Conversation", conversation_model),
    ):
        response = await chat.get_message_version_list(uuid4(), child.id, user)

    assert response["code"] == 0
    assert [version.id for version in response["data"]] == [root.id, child.id]
    conversation_model.filter.assert_called_once_with(
        id=child.conversation_id, user=user
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("current", "conversation", "target", "msg_key", "status_code"),
    [
        (None, None, None, "message_not_found", 404),
        (_message(), None, None, "access_denied", 403),
        (_message(), SimpleNamespace(), None, "version_not_found", 404),
    ],
)
async def test_switch_message_version_rejects_missing_or_inaccessible_resources(
    current, conversation, target, msg_key, status_code
):
    message_model = MagicMock()
    message_model.filter.side_effect = [_Query(first=current), _Query(first=target)]
    conversation_model = MagicMock()
    conversation_model.filter.return_value = _Query(first=conversation)

    with (
        patch.object(chat, "Message", message_model),
        patch.object(chat, "Conversation", conversation_model),
        pytest.raises(chat.BusinessError) as error,
    ):
        await chat.switch_message_version(
            uuid4(),
            uuid4(),
            SwitchVersionRequest(version_id=uuid4()),
            SimpleNamespace(),
        )

    assert error.value.msg_key == msg_key
    assert error.value.status_code == status_code


@pytest.mark.anyio
async def test_switch_message_version_rejects_version_from_another_group():
    user = SimpleNamespace(id=uuid4())
    current = _message()
    target = _message()
    message_model = MagicMock()
    message_model.filter.side_effect = [_Query(first=current), _Query(first=target)]
    conversation_model = MagicMock()
    conversation_model.filter.return_value = _Query(first=SimpleNamespace())

    with (
        patch.object(chat, "Message", message_model),
        patch.object(chat, "Conversation", conversation_model),
        pytest.raises(chat.BusinessError) as error,
    ):
        await chat.switch_message_version(
            uuid4(),
            current.id,
            SwitchVersionRequest(version_id=target.id),
            user,
        )

    assert error.value.msg_key == "version_not_in_group"
    assert error.value.status_code == 400


@pytest.mark.anyio
async def test_switch_message_version_activates_target_branch_and_stales_memory():
    user = SimpleNamespace(id=uuid4())
    root = _message()
    target = _message(parent_id=root.id, version_number=2)
    later = _message()
    message_model = MagicMock()
    message_model.filter.side_effect = [_Query(first=root), _Query(first=target)]
    conversation_model = MagicMock()
    conversation_model.filter.return_value = _Query(first=SimpleNamespace())
    output = SimpleNamespace(id=target.id, versions=[target])

    with (
        patch.object(chat, "Message", message_model),
        patch.object(chat, "Conversation", conversation_model),
        patch.object(
            chat, "get_prefix_path_before", AsyncMock(return_value=[root])
        ) as prefix,
        patch.object(
            chat, "find_descendant_branch_from", AsyncMock(return_value=[later])
        ) as descendants,
        patch.object(chat, "activate_conversation_branch", AsyncMock()) as activate,
        patch.object(
            chat,
            "stale_session_memory_if_source_outside_active_branch",
            AsyncMock(),
        ) as stale_memory,
        patch.object(
            chat,
            "build_message_out_with_versions",
            AsyncMock(return_value=output),
        ) as build_output,
    ):
        response = await chat.switch_message_version(
            uuid4(),
            root.id,
            SwitchVersionRequest(version_id=target.id),
            user,
        )

    prefix.assert_awaited_once_with(target)
    descendants.assert_awaited_once_with(target)
    activate.assert_awaited_once_with(root.conversation_id, [root, later])
    stale_memory.assert_awaited_once_with(root.conversation_id)
    build_output.assert_awaited_once_with(target, include_versions=True)
    assert response["data"] is output
