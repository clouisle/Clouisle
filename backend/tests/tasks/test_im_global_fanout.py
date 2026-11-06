from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.tasks import im as im_tasks


def _user_query(users: list[list[SimpleNamespace]]) -> MagicMock:
    query = MagicMock()
    query.filter = MagicMock(return_value=query)
    query.order_by = MagicMock(return_value=query)
    query.limit = MagicMock(return_value=query)
    query.all = AsyncMock(side_effect=users)
    return query


@pytest.mark.asyncio
async def test_fanout_sends_once_per_user_with_team_and_skips_unresolved() -> None:
    notification = MagicMock(
        id=uuid4(),
        scope="global",
        type="notice",
        title="Title",
        content="Body",
        level=MagicMock(value="low"),
        data={},
        link_url=None,
    )
    first, second = SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())
    query = _user_query([[first, second], []])

    with (
        patch(
            "app.models.notification.Notification.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=notification)),
        ),
        patch("app.models.user.User.filter", return_value=query),
        patch(
            "app.services.im_system_bridge._resolve_notification_team_id",
            new_callable=AsyncMock,
            side_effect=["team-1", None],
        ),
        patch(
            "app.services.im_service.send_system_message", new_callable=AsyncMock
        ) as send,
    ):
        result = await im_tasks._fanout_global_notification(notification.id)

    assert result == {"sent": 1, "skipped": 1}
    send.assert_awaited_once()
    kwargs = send.await_args.kwargs
    assert kwargs["team_id"] == "team-1"
    assert kwargs["recipient_user_id"] == first.id
    from app.services.im_system_bridge import _bridge_client_msg_id

    assert kwargs["client_msg_id"] == _bridge_client_msg_id(notification.id, first.id)
    assert len(kwargs["client_msg_id"]) <= 64


@pytest.mark.asyncio
async def test_fanout_returns_early_when_notification_disappeared() -> None:
    with patch(
        "app.models.notification.Notification.filter",
        return_value=AsyncMock(first=AsyncMock(return_value=None)),
    ):
        result = await im_tasks._fanout_global_notification(uuid4())
    assert result == {"sent": 0, "skipped": 0}


def test_fanout_task_wrapper_runs_on_worker_loop() -> None:
    def _run(coro):
        coro.close()
        return {"sent": 0, "skipped": 0}

    loop = MagicMock()
    loop.run_until_complete = MagicMock(side_effect=_run)
    with patch.object(im_tasks, "_get_event_loop", return_value=loop):
        assert im_tasks.fanout_global_notification_task(str(uuid4())) == {
            "sent": 0,
            "skipped": 0,
        }
