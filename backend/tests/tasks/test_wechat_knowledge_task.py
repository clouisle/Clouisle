from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4


from app.tasks import wechat_knowledge


class Query:
    def __init__(self, values=()):
        self.values = list(values)

    def order_by(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def __await__(self):
        async def resolve():
            return self.values

        return resolve().__await__()


def run_task(monkeypatch):
    import asyncio

    monkeypatch.setattr(wechat_knowledge, "_run_async", asyncio.run)
    return wechat_knowledge.recover_receipts_task.run()


def test_recovery_expires_old_logins_but_does_not_query_receipts_when_disabled(
    monkeypatch,
):
    from app.models import wechat_knowledge as models

    delete = AsyncMock()
    monkeypatch.setattr(
        models.WeChatKnowledgeLogin,
        "filter",
        lambda **_kwargs: SimpleNamespace(delete=delete),
    )
    monkeypatch.setattr(
        wechat_knowledge, "enabled_features", AsyncMock(return_value={"agent_chat"})
    )
    receipt_filter = Mock(
        side_effect=AssertionError("disabled recovery must not inspect receipts")
    )
    monkeypatch.setattr(models.WeChatKnowledgeReceipt, "filter", receipt_filter)
    dispatch = Mock()
    monkeypatch.setattr(wechat_knowledge.process_receipt_task, "delay", dispatch)

    assert run_task(monkeypatch) == {"queued": 0}
    delete.assert_awaited_once()
    receipt_filter.assert_not_called()
    dispatch.assert_not_called()


def test_recovery_queues_eligible_connected_receipts(monkeypatch):
    from app.models import wechat_knowledge as models

    receipt_ids = [uuid4(), uuid4()]
    rows = Query([SimpleNamespace(id=value) for value in receipt_ids])
    monkeypatch.setattr(
        models.WeChatKnowledgeLogin,
        "filter",
        lambda **_kwargs: SimpleNamespace(delete=AsyncMock()),
    )
    receipt_filter = Mock(return_value=rows)
    monkeypatch.setattr(models.WeChatKnowledgeReceipt, "filter", receipt_filter)
    monkeypatch.setattr(
        wechat_knowledge,
        "enabled_features",
        AsyncMock(return_value={"knowledge_collection"}),
    )
    dispatch = Mock()
    monkeypatch.setattr(wechat_knowledge.process_receipt_task, "delay", dispatch)

    assert run_task(monkeypatch) == {"queued": 2}
    assert [call.args for call in dispatch.call_args_list] == [
        (str(receipt_ids[0]),),
        (str(receipt_ids[1]),),
    ]
    assert receipt_filter.called
