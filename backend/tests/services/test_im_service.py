from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.schemas.response import BusinessError
from app.models.im import (
    ImConversation,
    ImConversationType,
    ImMessage,
)
from app.services import im_service


def test_sort_user_pair() -> None:
    u1 = uuid4()
    u2 = uuid4()
    p1, p2 = im_service._sort_user_pair(u1, u2)
    assert str(p1) < str(p2)
    # 反向传入也得到相同顺序
    p1_rev, p2_rev = im_service._sort_user_pair(u2, u1)
    assert p1 == p1_rev
    assert p2 == p2_rev


@pytest.mark.asyncio
async def test_check_users_in_same_team_forbidden() -> None:
    team_id = uuid4()
    u1 = uuid4()
    u2 = uuid4()

    fake_query = AsyncMock()
    fake_query.values_list = AsyncMock(return_value=[u1])  # 只有 u1 在团队中

    with patch("app.models.user.TeamMember.filter", return_value=fake_query):
        with pytest.raises(BusinessError) as exc_info:
            await im_service.check_users_in_same_team(team_id, u1, u2)
        assert exc_info.value.status_code == 403
        assert exc_info.value.msg_key == "team_access_denied"


@pytest.mark.asyncio
async def test_cannot_chat_with_self() -> None:
    team_id = uuid4()
    u1 = uuid4()
    with pytest.raises(BusinessError) as exc_info:
        await im_service.get_or_create_direct_conversation(team_id, u1, u1)
    assert exc_info.value.status_code == 400
    assert exc_info.value.msg_key == "cannot_chat_with_self"


@pytest.mark.asyncio
async def test_send_direct_message_access_denied() -> None:
    conv_id = uuid4()
    sender_id = uuid4()
    stranger_id = uuid4()
    user2_id = uuid4()

    conv = ImConversation(
        id=conv_id,
        team_id=uuid4(),
        type=ImConversationType.DIRECT,
    )
    conv.user1_id = sender_id
    conv.user2_id = user2_id

    fake_query = AsyncMock()
    fake_query.first = AsyncMock(return_value=conv)

    with patch("app.models.im.ImConversation.filter", return_value=fake_query):
        with pytest.raises(BusinessError) as exc_info:
            await im_service.send_direct_message(
                conversation_id=conv_id,
                sender_id=stranger_id,
                content="hello",
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.msg_key == "conversation_access_denied"


@pytest.mark.asyncio
async def test_send_direct_message_idempotent() -> None:
    conv_id = uuid4()
    sender_id = uuid4()
    user2_id = uuid4()
    client_msg_id = "test-client-msg-123"

    conv = ImConversation(
        id=conv_id,
        team_id=uuid4(),
        type=ImConversationType.DIRECT,
    )
    conv.user1_id = sender_id
    conv.user2_id = user2_id

    existing_msg = ImMessage(
        id=uuid4(),
        conversation_id=conv_id,
        sender_id=sender_id,
        client_msg_id=client_msg_id,
        seq=1,
        content="existing",
    )

    fake_conv_query = AsyncMock()
    fake_conv_query.first = AsyncMock(return_value=conv)

    with (
        patch("app.models.im.ImConversation.filter", return_value=fake_conv_query),
        patch(
            "app.services.im_redis.get_cached_message_result",
            return_value={"id": str(existing_msg.id)},
        ),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=existing_msg)),
        ),
    ):
        result = await im_service.send_direct_message(
            conversation_id=conv_id,
            sender_id=sender_id,
            content="existing",
            client_msg_id=client_msg_id,
        )
        assert result.id == existing_msg.id


@pytest.mark.asyncio
async def test_search_messages_empty_query() -> None:
    res = await im_service.search_messages(uuid4(), uuid4(), "   ")
    assert res == []
