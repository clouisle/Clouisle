from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.response import BusinessError
from app.models.im import (
    ImConversation,
    ImConversationType,
    ImMessage,
)
from app.services import im_service

# Captured before the autouse fixture stubs the module attribute.
_REAL_ENSURE_ACTIVE_TEAM_MEMBER = im_service._ensure_active_team_member


@pytest.fixture(autouse=True)
def _stub_team_membership_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Other branches are under test here; the live guard has its own coverage."""

    async def _allow(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(im_service, "_ensure_active_team_member", _allow)


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
        type=ImConversationType.DIRECT,
    )
    conv.team_id = uuid4()
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
        type=ImConversationType.DIRECT,
    )
    conv.team_id = uuid4()
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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("plain text", "plain text"),
        ("**bold** and __strong__", "bold and strong"),
        ("*italic* _emphasis_ ~~gone~~", "italic emphasis gone"),
        ("**unclosed", "unclosed"),
        ("***", "*"),
        ("a\n**b\nc**", "a b c"),
        ("```py\ncode\n```", ""),
        ("```unclosed", "```unclosed"),
        ("`code`", "code"),
        ("`unclosed", "`unclosed"),
        ("``", "``"),
        ("[text](https://x.test/a)", "text"),
        ("![img](https://x.test/a)", "img"),
        ("[text]", "[text]"),
        ("[text] (url)", "[text] (url)"),
        ("[](x)", "[](x)"),
        ("[a](b", "[a](b"),
        ("![](x)", ""),
        ("# Heading\n> quote", "Heading quote"),
        ("  multiple   spaces  ", "multiple spaces"),
        ("**[link](u)**", "link"),
        ("**a **b**", "a b"),
        ("*a *b*", "a b*"),
    ],
)
def test_strip_markdown_summary_shapes(text: str, expected: str) -> None:
    assert im_service._strip_markdown_summary(text) == expected


def test_strip_markdown_summary_truncates_to_limit() -> None:
    assert im_service._strip_markdown_summary("x" * 250) == "x" * 200
    assert im_service._strip_markdown_summary("y" * 50, max_length=10) == "y" * 10


def test_ensure_same_asset_rejects_swapped_attachment() -> None:
    existing = MagicMock(asset_id=uuid4())
    with pytest.raises(BusinessError) as exc:
        im_service._ensure_same_asset(existing, uuid4())
    assert exc.value.msg_key == "im_attachment_mismatch"
    im_service._ensure_same_asset(MagicMock(asset_id=None), None)


@pytest.mark.asyncio
async def test_ensure_active_team_member_allows_active_member() -> None:
    query = MagicMock()
    query.exists = AsyncMock(return_value=True)
    with patch("app.services.im_service.TeamMember.filter", return_value=query):
        await _REAL_ENSURE_ACTIVE_TEAM_MEMBER(uuid4(), uuid4())
    query.exists.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_active_team_member_rejects_removed_or_inactive_member() -> None:
    query = MagicMock()
    query.exists = AsyncMock(return_value=False)
    with patch("app.services.im_service.TeamMember.filter", return_value=query):
        with pytest.raises(BusinessError) as exc:
            await _REAL_ENSURE_ACTIVE_TEAM_MEMBER(uuid4(), uuid4())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_check_users_in_same_team_allows_both_members() -> None:
    user_a, user_b = uuid4(), uuid4()
    query = MagicMock()
    query.values_list = AsyncMock(return_value=[user_a, user_b])
    with patch("app.services.im_service.TeamMember.filter", return_value=query):
        await im_service.check_users_in_same_team(uuid4(), user_a, user_b)


@pytest.mark.asyncio
async def test_get_messages_missing_conversation_returns_404() -> None:
    with patch(
        "app.models.im.ImConversation.filter",
        return_value=AsyncMock(first=AsyncMock(return_value=None)),
    ):
        with pytest.raises(BusinessError) as exc:
            await im_service.get_messages(uuid4(), uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_mark_conversation_read_missing_conversation_returns_404() -> None:
    with patch(
        "app.models.im.ImConversation.filter",
        return_value=AsyncMock(first=AsyncMock(return_value=None)),
    ):
        with pytest.raises(BusinessError) as exc:
            await im_service.mark_conversation_read(uuid4(), uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_rebuild_unread_cache_from_db_aggregates_conversations() -> None:
    user_id = uuid4()
    conv_a, conv_b = MagicMock(id=uuid4()), MagicMock(id=uuid4())
    participant_a = MagicMock(conversation=conv_a, last_read_seq=1)
    participant_b = MagicMock(conversation=conv_b, last_read_seq=0)
    query = MagicMock()
    query.prefetch_related = MagicMock(
        return_value=AsyncMock(
            all=AsyncMock(return_value=[participant_a, participant_b])
        )
    )

    with (
        patch(
            "app.services.im_service.ImConversationParticipant.filter",
            return_value=query,
        ),
        patch(
            "app.services.im_service._count_unread_messages",
            new_callable=AsyncMock,
            side_effect=[3, 0],
        ),
        patch(
            "app.services.im_redis.rebuild_unread_cache", new_callable=AsyncMock
        ) as rebuild,
    ):
        result = await im_service._rebuild_unread_cache_from_db(user_id)

    assert result == {str(conv_a.id): 3, str(conv_b.id): 0}
    rebuild.assert_awaited_once_with(user_id, 3, result)
