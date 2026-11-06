from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import im as im_endpoints
from app.models.im import ImMessageType
from app.models.user import User
from app.schemas.im import MarkReadRequest, SendMessageRequest


@pytest.fixture
def fake_user() -> User:
    user = User(
        id=uuid4(),
        username="alice",
        email="alice@example.com",
        is_active=True,
    )
    return user


@pytest.mark.asyncio
async def test_list_conversations_endpoint(fake_user: User) -> None:
    team_id = uuid4()
    mock_items = [
        {
            "id": str(uuid4()),
            "type": "system",
            "team_id": str(team_id),
            "is_pinned": True,
            "is_muted": False,
            "last_read_seq": 0,
            "latest_seq": 1,
            "unread_count": 1,
            "last_message_content": "Notice",
            "last_message_at": None,
            "peer": None,
            "created_at": "2026-11-04T00:00:00Z",
            "updated_at": "2026-11-04T00:00:00Z",
        }
    ]

    with (
        patch("app.api.v1.endpoints.im.check_team_access", return_value=None),
        patch("app.services.im_service.list_conversations", return_value=mock_items),
    ):
        resp = await im_endpoints.list_conversations(
            team_id=team_id, current_user=fake_user
        )
        assert resp["code"] == 0
        assert len(resp["data"]) == 1
        assert resp["data"][0]["type"] == "system"


@pytest.mark.asyncio
async def test_send_message_endpoint(fake_user: User) -> None:
    conv_id = uuid4()
    fake_msg = AsyncMock()
    fake_msg.id = uuid4()
    fake_msg.conversation_id = conv_id
    fake_msg.sender_id = fake_user.id
    fake_msg.client_msg_id = "client-uuid"
    fake_msg.seq = 10
    fake_msg.msg_type = ImMessageType.TEXT
    fake_msg.content = "hello world"
    fake_msg.payload = None
    fake_msg.status = AsyncMock(value="normal")
    fake_msg.created_at = AsyncMock(isoformat=lambda: "2026-11-04T00:00:00Z")
    fake_msg.asset_id = None

    payload = SendMessageRequest(
        content="hello world",
        client_msg_id="client-uuid",
    )

    with patch("app.services.im_service.send_direct_message", return_value=fake_msg):
        resp = await im_endpoints.send_message(
            conversation_id=conv_id,
            payload=payload,
            current_user=fake_user,
        )
        assert resp["code"] == 0
        assert resp["data"].content == "hello world"
        assert resp["data"].seq == 10


@pytest.mark.asyncio
async def test_mark_read_endpoint(fake_user: User) -> None:
    conv_id = uuid4()
    with patch("app.services.im_service.mark_conversation_read", return_value=3):
        resp = await im_endpoints.mark_read(
            conversation_id=conv_id,
            payload=MarkReadRequest(up_to_seq=5),
            current_user=fake_user,
        )
        assert resp["code"] == 0
        assert resp["data"] == {"cleared": 3}


@pytest.mark.asyncio
async def test_get_unread_count_endpoint(fake_user: User) -> None:
    with patch("app.services.im_service.get_global_unread_count", return_value=8):
        resp = await im_endpoints.get_unread_count(current_user=fake_user)
        assert resp["code"] == 0
        assert resp["data"].total == 8


@pytest.mark.asyncio
async def test_list_team_chat_candidates_endpoint(fake_user: User) -> None:
    team_id = uuid4()
    other_user = User(
        id=uuid4(),
        username="bob",
        email="bob@example.com",
        is_active=True,
    )
    fake_member = AsyncMock()
    fake_member.user = other_user
    fake_member.role = "member"

    fake_query = MagicMock()
    fake_query.exclude = MagicMock(return_value=fake_query)
    fake_query.prefetch_related = MagicMock(return_value=fake_query)
    fake_query.all = AsyncMock(return_value=[fake_member])

    with (
        patch("app.api.v1.endpoints.im.check_team_access", return_value=None),
        patch("app.models.user.TeamMember.filter", return_value=fake_query),
    ):
        resp = await im_endpoints.list_team_chat_candidates(
            team_id=team_id, current_user=fake_user
        )
        assert resp["code"] == 0
        assert len(resp["data"]) == 1
        assert resp["data"][0]["username"] == "bob"
        assert resp["data"][0]["full_name"] == "bob"


@pytest.mark.asyncio
async def test_stream_im_events_endpoint(fake_user: User) -> None:
    fake_request = AsyncMock()
    fake_request.is_disconnected = AsyncMock(side_effect=[False, True])

    fake_pubsub = AsyncMock()
    fake_pubsub.subscribe = AsyncMock()
    fake_pubsub.unsubscribe = AsyncMock()
    fake_pubsub.close = AsyncMock()
    fake_pubsub.get_message = AsyncMock(
        return_value={
            "type": "message",
            "data": b'{"type": "new_message", "data": {"content": "hi"}}',
        }
    )

    fake_redis = AsyncMock()
    fake_redis.pubsub = MagicMock(return_value=fake_pubsub)

    with patch("app.core.redis.get_redis", return_value=fake_redis):
        response = await im_endpoints.stream_im_events(
            request=fake_request, current_user=fake_user
        )
        assert response.media_type == "text/event-stream"
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        assert any("connected" in c for c in chunks)
        assert any("new_message" in c for c in chunks)


@pytest.mark.asyncio
async def test_search_messages_endpoint(fake_user: User) -> None:
    team_id = uuid4()
    mock_results = [
        {
            "message_id": str(uuid4()),
            "conversation_id": str(uuid4()),
            "seq": 10,
            "content": "found target text",
            "msg_type": "text",
            "conversation_type": "direct",
            "created_at": "2026-11-04T00:00:00Z",
            "peer": None,
        }
    ]
    with (
        patch("app.api.v1.endpoints.im.check_team_access", return_value=None),
        patch("app.services.im_service.search_messages", return_value=mock_results),
    ):
        resp = await im_endpoints.search_messages(
            team_id=team_id, q="target", limit=20, current_user=fake_user
        )
        assert resp["code"] == 0
        assert len(resp["data"]) == 1
        assert resp["data"][0]["content"] == "found target text"


@pytest.mark.asyncio
async def test_create_or_get_direct_conversation_endpoint(fake_user: User) -> None:
    team_id = uuid4()
    target_user_id = uuid4()
    mock_conv = MagicMock(
        id=uuid4(),
        type=MagicMock(value="direct"),
        team_id=team_id,
        user1_id=fake_user.id,
        user2_id=target_user_id,
        latest_seq=0,
        last_message_content=None,
        last_message_at=None,
        created_at=MagicMock(isoformat=lambda: "2026-11-04T00:00:00Z"),
        updated_at=MagicMock(isoformat=lambda: "2026-11-04T00:00:00Z"),
    )
    mock_peer_user = MagicMock(
        id=target_user_id,
        username="bob",
        full_name="Bob Builder",
        avatar_url=None,
    )
    with (
        patch("app.api.v1.endpoints.im.check_team_access", return_value=None),
        patch(
            "app.services.im_service.get_or_create_direct_conversation",
            return_value=mock_conv,
        ),
        patch(
            "app.models.user.User.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=mock_peer_user)),
        ),
    ):
        from app.schemas.im import DirectConversationCreate

        payload = DirectConversationCreate(
            team_id=team_id, target_user_id=target_user_id
        )
        resp = await im_endpoints.create_or_get_direct_conversation(
            payload, current_user=fake_user
        )
        assert resp["code"] == 0
        assert resp["data"].type == "direct"
        assert resp["data"].peer.username == "bob"


@pytest.mark.asyncio
async def test_get_messages_endpoint(fake_user: User) -> None:
    conv_id = uuid4()
    msg = MagicMock(
        id=uuid4(),
        conversation_id=conv_id,
        sender_id=fake_user.id,
        client_msg_id="uuid",
        seq=1,
        msg_type=MagicMock(value="text"),
        content="hi",
        payload=None,
        status=MagicMock(value="normal"),
        created_at=MagicMock(isoformat=lambda: "2026-11-04T00:00:00Z"),
        asset_id=None,
    )
    with patch("app.services.im_service.get_messages", return_value=([msg], False)):
        resp = await im_endpoints.get_messages(
            conversation_id=conv_id,
            around_seq=1,
            current_user=fake_user,
        )
        assert resp["code"] == 0
        assert len(resp["data"].messages) == 1
        assert resp["data"].has_more is False
