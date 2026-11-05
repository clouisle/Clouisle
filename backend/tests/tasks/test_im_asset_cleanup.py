from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from tortoise.expressions import Subquery

from app.tasks import im as im_tasks


def _candidate_query(rows: list[tuple[object, str]]) -> MagicMock:
    query = MagicMock()
    query.exclude = MagicMock(return_value=query)
    query.order_by = MagicMock(return_value=query)
    query.limit = MagicMock(return_value=query)
    query.values_list = AsyncMock(return_value=rows)
    return query


def _asset_filter_factory(candidate_query: MagicMock, delete_query: MagicMock):
    calls: list[dict] = []

    def factory(**kwargs):
        calls.append(kwargs)
        if "created_at__lt" in kwargs:
            return candidate_query
        return delete_query

    factory.calls = calls  # type: ignore[attr-defined]
    return factory


@pytest.mark.asyncio
async def test_cleanup_deletes_only_unreferenced_assets() -> None:
    orphan_id, referenced_id, rechecked_id = uuid4(), uuid4(), uuid4()
    candidate_query = _candidate_query(
        [
            (orphan_id, "im/2026/11/orphan.png"),
            (referenced_id, "im/2026/11/referenced.png"),
            (rechecked_id, "im/2026/11/rechecked.png"),
        ]
    )
    delete_query = MagicMock()
    delete_query.delete = AsyncMock(return_value=1)
    asset_filter = _asset_filter_factory(candidate_query, delete_query)
    message_filter = MagicMock(
        side_effect=lambda **kwargs: (
            SimpleNamespace(values_list=MagicMock(return_value=[]))
            if kwargs.get("asset_id__isnull") is False
            else SimpleNamespace(
                values_list=AsyncMock(return_value=[referenced_id]),
            )
            if "asset_id__in" in kwargs
            else SimpleNamespace(
                exists=AsyncMock(return_value=kwargs.get("asset_id") == rechecked_id)
            )
        )
    )
    storage = SimpleNamespace(delete=AsyncMock())
    scope_query = SimpleNamespace(values_list=MagicMock(return_value=[]))

    with (
        patch.object(im_tasks.Asset, "filter", side_effect=asset_filter),
        patch.object(im_tasks.ImMessage, "filter", message_filter),
        patch.object(
            im_tasks.AssetScopeRef, "filter", return_value=scope_query
        ) as scope_filter,
        patch(
            "app.services.upload_storage.get_upload_storage_backend",
            new_callable=AsyncMock,
            return_value=storage,
        ),
    ):
        result = await im_tasks._cleanup_orphan_im_assets()

    scope_filter.assert_called_once()
    assert (
        scope_filter.call_args.kwargs["scope_type"]
        == im_tasks.AssetScopeType.IM_CONVERSATION
    )
    # Referenced assets are excluded in SQL before the batch limit, so a large
    # set of long-lived referenced assets cannot starve the cleanup.
    exclude_kwargs = candidate_query.exclude.call_args.kwargs
    assert set(exclude_kwargs) == {"id__in"}
    assert isinstance(exclude_kwargs["id__in"], Subquery)
    assert {"asset_id__isnull": False} in [
        call.kwargs for call in message_filter.call_args_list
    ]
    storage.delete.assert_awaited_once_with("im/2026/11/orphan.png")
    delete_query.delete.assert_awaited_once()
    [delete_call] = [c for c in asset_filter.calls if "id" in c]  # type: ignore[attr-defined]
    assert delete_call["id"] == orphan_id
    assert result["scanned"] == 3
    assert result["referenced"] == 1
    assert result["deleted"] == 1
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_cleanup_keeps_row_when_storage_delete_fails() -> None:
    asset_id = uuid4()
    candidate_query = _candidate_query([(asset_id, "im/2026/11/locked.png")])
    delete_query = MagicMock()
    delete_query.delete = AsyncMock(return_value=1)
    asset_filter = _asset_filter_factory(candidate_query, delete_query)
    storage = SimpleNamespace(delete=AsyncMock(side_effect=OSError("storage offline")))

    with (
        patch.object(im_tasks.Asset, "filter", side_effect=asset_filter),
        patch.object(
            im_tasks.ImMessage,
            "filter",
            side_effect=lambda **kwargs: (
                SimpleNamespace(values_list=MagicMock(return_value=[]))
                if "asset_id__isnull" in kwargs
                else SimpleNamespace(
                    values_list=AsyncMock(return_value=[]),
                    exists=AsyncMock(return_value=False),
                )
            ),
        ),
        patch.object(
            im_tasks.AssetScopeRef,
            "filter",
            return_value=SimpleNamespace(values_list=MagicMock(return_value=[])),
        ),
        patch(
            "app.services.upload_storage.get_upload_storage_backend",
            new_callable=AsyncMock,
            return_value=storage,
        ),
    ):
        result = await im_tasks._cleanup_orphan_im_assets()

    storage.delete.assert_awaited_once()
    delete_query.delete.assert_not_awaited()
    assert result["deleted"] == 0
    assert result["failed"] == 1


@pytest.mark.asyncio
async def test_cleanup_short_circuits_without_candidates() -> None:
    with (
        patch.object(im_tasks.Asset, "filter", return_value=_candidate_query([])),
        patch.object(
            im_tasks.ImMessage,
            "filter",
            return_value=SimpleNamespace(values_list=MagicMock(return_value=[])),
        ),
        patch.object(
            im_tasks.AssetScopeRef,
            "filter",
            return_value=SimpleNamespace(values_list=MagicMock(return_value=[])),
        ),
        patch(
            "app.services.upload_storage.get_upload_storage_backend",
            new_callable=AsyncMock,
        ) as storage_factory,
    ):
        result = await im_tasks._cleanup_orphan_im_assets()

    storage_factory.assert_not_awaited()
    assert result["scanned"] == 0
    assert result["deleted"] == 0


@pytest.mark.asyncio
async def test_cleanup_applies_ttl_and_batch_overrides() -> None:
    now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
    candidate_query = _candidate_query([])
    asset_filter = MagicMock(return_value=candidate_query)

    with (
        patch.object(im_tasks, "now_utc", return_value=now),
        patch.object(im_tasks.Asset, "filter", side_effect=asset_filter),
        patch.object(
            im_tasks.ImMessage,
            "filter",
            return_value=SimpleNamespace(values_list=MagicMock(return_value=[])),
        ),
        patch.object(
            im_tasks.AssetScopeRef,
            "filter",
            return_value=SimpleNamespace(values_list=MagicMock(return_value=[])),
        ),
    ):
        await im_tasks._cleanup_orphan_im_assets(ttl_hours=6, batch_size=7)

    kwargs = asset_filter.call_args.kwargs
    assert kwargs["created_at__lt"] == datetime(2026, 11, 5, 6, tzinfo=timezone.utc)
    candidate_query.exclude.assert_called_once()
    candidate_query.limit.assert_called_once_with(7)


def test_task_wrapper_runs_cleanup_on_worker_loop() -> None:
    def _run(coro):
        coro.close()
        return {"status": "success"}

    loop = MagicMock()
    loop.run_until_complete = MagicMock(side_effect=_run)
    with patch.object(im_tasks, "_get_event_loop", return_value=loop):
        result = im_tasks.cleanup_orphan_im_assets_task()

    assert result == {"status": "success"}
    loop.run_until_complete.assert_called_once()


def test_get_event_loop_replaces_closed_loop() -> None:
    closed_loop = MagicMock()
    closed_loop.is_closed.return_value = True
    new_loop = MagicMock()

    with (
        patch("asyncio.get_event_loop", return_value=closed_loop),
        patch("asyncio.new_event_loop", return_value=new_loop),
        patch("asyncio.set_event_loop") as set_event_loop,
    ):
        assert im_tasks._get_event_loop() is new_loop

    set_event_loop.assert_called_once_with(new_loop)


def test_get_event_loop_recovers_when_no_loop_is_set() -> None:
    new_loop = MagicMock()

    with (
        patch("asyncio.get_event_loop", side_effect=RuntimeError("no loop")),
        patch("asyncio.new_event_loop", return_value=new_loop),
        patch("asyncio.set_event_loop") as set_event_loop,
    ):
        assert im_tasks._get_event_loop() is new_loop

    set_event_loop.assert_called_once_with(new_loop)


def test_get_event_loop_reuses_an_open_loop() -> None:
    open_loop = MagicMock()
    open_loop.is_closed.return_value = False

    with (
        patch("asyncio.get_event_loop", return_value=open_loop),
        patch("asyncio.set_event_loop") as set_event_loop,
    ):
        assert im_tasks._get_event_loop() is open_loop

    set_event_loop.assert_not_called()


def test_task_wrapper_reraises_cleanup_failures() -> None:
    def _raise(coro):
        coro.close()
        raise RuntimeError("boom")

    loop = MagicMock()
    loop.run_until_complete = MagicMock(side_effect=_raise)
    with (
        patch.object(im_tasks, "_get_event_loop", return_value=loop),
        pytest.raises(RuntimeError, match="boom"),
    ):
        im_tasks.cleanup_orphan_im_assets_task()
