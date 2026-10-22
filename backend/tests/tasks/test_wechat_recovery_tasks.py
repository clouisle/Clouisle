import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
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

    async def values_list(self, *_args, **_kwargs):
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


def test_recover_bindings_returns_idle_when_agent_feature_disabled(
    monkeypatch, run_async
):
    from tortoise import Tortoise

    feature_check = AsyncMock(return_value={"knowledge_collection"})
    monkeypatch.setattr(wechat_agent, "enabled_features", feature_check)
    connection = Mock()
    monkeypatch.setattr(Tortoise, "get_connection", Mock(return_value=connection))

    assert wechat_agent.recover_bindings_task() == {"queued": 0}
    feature_check.assert_awaited_once_with("wechat")
    connection.execute_query_dict.assert_not_called()


def test_recover_knowledge_receipts_disabled_feature_still_expires_logins(
    monkeypatch, run_async
):
    from app.models import wechat_knowledge as models

    deleted = AsyncMock()
    monkeypatch.setattr(
        models.WeChatKnowledgeLogin,
        "filter",
        lambda **_kwargs: SimpleNamespace(delete=deleted),
    )
    monkeypatch.setattr(
        wechat_knowledge, "enabled_features", AsyncMock(return_value={"agent_chat"})
    )
    dispatch = Mock()
    monkeypatch.setattr(wechat_knowledge.process_receipt_task, "delay", dispatch)

    assert wechat_knowledge.recover_receipts_task() == {"queued": 0}
    deleted.assert_awaited_once()
    dispatch.assert_not_called()


def test_recover_knowledge_receipts_queues_each_eligible_row(monkeypatch, run_async):
    from app.models import wechat_knowledge as models

    row_ids = [uuid4(), uuid4()]
    rows = Query([SimpleNamespace(id=row_id) for row_id in row_ids])
    monkeypatch.setattr(
        models.WeChatKnowledgeLogin,
        "filter",
        lambda **_kwargs: SimpleNamespace(delete=AsyncMock()),
    )
    monkeypatch.setattr(
        models.WeChatKnowledgeReceipt, "filter", lambda *_args, **_kwargs: rows
    )
    monkeypatch.setattr(
        wechat_knowledge,
        "enabled_features",
        AsyncMock(return_value={"knowledge_collection"}),
    )
    dispatch = Mock()
    monkeypatch.setattr(wechat_knowledge.process_receipt_task, "delay", dispatch)

    assert wechat_knowledge.recover_receipts_task() == {"queued": 2}
    assert dispatch.call_args_list == [
        ((str(row_ids[0]),),),
        ((str(row_ids[1]),),),
    ]
