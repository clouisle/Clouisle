import asyncio
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.tasks import wechat_agent, wechat_knowledge


class Query:
    def __init__(self, values=()):
        self.values = list(values)

    def order_by(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def values_list(self, *_args, **_kwargs):
        return self.values

    def filter(self, *_args, **_kwargs):
        return self

    async def delete(self):
        return len(self.values)

    def __await__(self):
        async def resolve():
            return self.values

        return resolve().__await__()


@pytest.fixture
def run_async(monkeypatch):
    monkeypatch.setattr(wechat_agent, "_run_async", asyncio.run)
    monkeypatch.setattr(wechat_knowledge, "_run_async", asyncio.run)


@pytest.mark.asyncio
async def test_recover_bindings_returns_idle_when_agent_feature_disabled(
    monkeypatch, run_async
):
    from app.models import wechat_agent as models

    feature_check = Mock(return_value={"knowledge_collection"})
    monkeypatch.setattr(wechat_agent, "enabled_features", feature_check)
    monkeypatch.setattr(
        models.WeChatAgentReceipt,
        "filter",
        Mock(side_effect=AssertionError("disabled recovery must not inspect receipts")),
    )
    monkeypatch.setattr(
        models.WeChatAgentDelivery,
        "filter",
        Mock(
            side_effect=AssertionError("disabled recovery must not inspect deliveries")
        ),
    )

    assert wechat_agent.recover_bindings_task() == {"queued": 0}
    feature_check.assert_called_once_with("wechat")


@pytest.mark.asyncio
async def test_recover_bindings_queues_receipt_and_delivery_work(
    monkeypatch, run_async
):
    from app.models import wechat_agent as models

    receipt_id = uuid4()
    binding_id = uuid4()
    pending_receipts = Query([binding_id])
    pending_deliveries = Query([receipt_id])
    delivery_receipts = Query([binding_id])
    receipt_filters = Mock(side_effect=[pending_receipts, delivery_receipts])
    monkeypatch.setattr(models.WeChatAgentReceipt, "filter", receipt_filters)
    monkeypatch.setattr(
        models.WeChatAgentDelivery, "filter", Mock(return_value=pending_deliveries)
    )
    monkeypatch.setattr(
        wechat_agent, "enabled_features", Mock(return_value={"agent_chat"})
    )
    dispatch = Mock()
    monkeypatch.setattr(wechat_agent.process_binding_task, "delay", dispatch)

    assert wechat_agent.recover_bindings_task() == {"queued": 1}
    dispatch.assert_called_once_with(str(binding_id))
    assert receipt_filters.call_count == 2


@pytest.mark.asyncio
async def test_recover_bindings_with_no_delivery_rows_only_queues_receipts(
    monkeypatch, run_async
):
    from app.models import wechat_agent as models

    binding_id = uuid4()
    receipt_filters = Mock(return_value=Query([binding_id]))
    monkeypatch.setattr(models.WeChatAgentReceipt, "filter", receipt_filters)
    monkeypatch.setattr(
        models.WeChatAgentDelivery, "filter", Mock(return_value=Query())
    )
    monkeypatch.setattr(
        wechat_agent, "enabled_features", Mock(return_value={"agent_chat"})
    )
    dispatch = Mock()
    monkeypatch.setattr(wechat_agent.process_binding_task, "delay", dispatch)

    assert wechat_agent.recover_bindings_task() == {"queued": 1}
    dispatch.assert_called_once_with(str(binding_id))
    assert receipt_filters.call_count == 1


@pytest.mark.asyncio
async def test_recover_bindings_deduplicates_binding_with_receipt_and_delivery(
    monkeypatch, run_async
):
    from app.models import wechat_agent as models

    binding_id = uuid4()
    receipt_filters = Mock(side_effect=[Query([binding_id]), Query([binding_id])])
    monkeypatch.setattr(models.WeChatAgentReceipt, "filter", receipt_filters)
    monkeypatch.setattr(
        models.WeChatAgentDelivery, "filter", Mock(return_value=Query([uuid4()]))
    )
    monkeypatch.setattr(
        wechat_agent, "enabled_features", Mock(return_value={"agent_chat"})
    )
    dispatch = Mock()
    monkeypatch.setattr(wechat_agent.process_binding_task, "delay", dispatch)

    assert wechat_agent.recover_bindings_task() == {"queued": 1}
    dispatch.assert_called_once_with(str(binding_id))


@pytest.mark.asyncio
async def test_recover_knowledge_receipts_disabled_feature_still_expires_logins(
    monkeypatch, run_async
):
    from app.models import wechat_knowledge as models

    deleted = Mock()
    monkeypatch.setattr(
        models.WeChatKnowledgeLogin,
        "filter",
        lambda **_kwargs: SimpleNamespace(delete=deleted),
    )
    monkeypatch.setattr(
        wechat_knowledge, "enabled_features", Mock(return_value={"agent_chat"})
    )
    dispatch = Mock()
    monkeypatch.setattr(wechat_knowledge.process_receipt_task, "delay", dispatch)

    assert wechat_knowledge.recover_receipts_task() == {"queued": 0}
    deleted.assert_awaited_once()
    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_recover_knowledge_receipts_queues_each_eligible_row(
    monkeypatch, run_async
):
    from app.models import wechat_knowledge as models

    row_ids = [uuid4(), uuid4()]
    rows = Query([SimpleNamespace(id=row_id) for row_id in row_ids])
    monkeypatch.setattr(
        models.WeChatKnowledgeLogin,
        "filter",
        lambda **_kwargs: SimpleNamespace(delete=Mock()),
    )
    monkeypatch.setattr(
        models.WeChatKnowledgeReceipt, "filter", lambda *_args, **_kwargs: rows
    )
    monkeypatch.setattr(
        wechat_knowledge,
        "enabled_features",
        Mock(return_value={"knowledge_collection"}),
    )
    dispatch = Mock()
    monkeypatch.setattr(wechat_knowledge.process_receipt_task, "delay", dispatch)

    assert wechat_knowledge.recover_receipts_task() == {"queued": 2}
    assert dispatch.call_args_list == [
        ((str(row_ids[0]),),),
        ((str(row_ids[1]),),),
    ]
