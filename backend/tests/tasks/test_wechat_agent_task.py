from unittest.mock import AsyncMock, Mock
from uuid import uuid4


from app.tasks import wechat_agent


class Query:
    def __init__(self, values=()):
        self.values = list(values)

    def order_by(self, *_args):
        return self

    def limit(self, *_args):
        return self

    async def values_list(self, *_args, **_kwargs):
        return self.values

    def filter(self, *_args, **_kwargs):
        return self

    def __await__(self):
        async def resolve():
            return self.values

        return resolve().__await__()


def run_task(monkeypatch, task):
    import asyncio

    monkeypatch.setattr(wechat_agent, "_run_async", asyncio.run)
    return task.run()


def test_recovery_does_not_inspect_queue_when_agent_chat_disabled(monkeypatch):
    from app.models import wechat_agent as models

    feature_check = AsyncMock(return_value={"knowledge_collection"})
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

    assert run_task(monkeypatch, wechat_agent.recover_bindings_task) == {"queued": 0}
    feature_check.assert_awaited_once_with("wechat")


def test_recovery_queues_unique_bindings_for_pending_receipts_and_deliveries(
    monkeypatch,
):
    from app.models import wechat_agent as models

    binding_id = uuid4()
    receipt_filter = Mock(side_effect=[Query([binding_id]), Query([binding_id])])
    monkeypatch.setattr(models.WeChatAgentReceipt, "filter", receipt_filter)
    monkeypatch.setattr(
        models.WeChatAgentDelivery, "filter", Mock(return_value=Query([uuid4()]))
    )
    monkeypatch.setattr(
        wechat_agent, "enabled_features", AsyncMock(return_value={"agent_chat"})
    )
    dispatch = Mock()
    monkeypatch.setattr(wechat_agent.process_binding_task, "delay", dispatch)

    assert run_task(monkeypatch, wechat_agent.recover_bindings_task) == {"queued": 1}
    dispatch.assert_called_once_with(str(binding_id))


def test_recovery_skips_delivery_receipt_lookup_when_none_are_pending(monkeypatch):
    from app.models import wechat_agent as models

    binding_id = uuid4()
    receipt_filter = Mock(return_value=Query([binding_id]))
    monkeypatch.setattr(models.WeChatAgentReceipt, "filter", receipt_filter)
    monkeypatch.setattr(
        models.WeChatAgentDelivery, "filter", Mock(return_value=Query())
    )
    monkeypatch.setattr(
        wechat_agent, "enabled_features", AsyncMock(return_value={"agent_chat"})
    )
    dispatch = Mock()
    monkeypatch.setattr(wechat_agent.process_binding_task, "delay", dispatch)

    assert run_task(monkeypatch, wechat_agent.recover_bindings_task) == {"queued": 1}
    dispatch.assert_called_once_with(str(binding_id))
    assert receipt_filter.call_count == 1
