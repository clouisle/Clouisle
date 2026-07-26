import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.vector_store import VectorStore

vector_store = importlib.import_module("app.services.vector_store")


@pytest.mark.asyncio
async def test_rerank_config_applies_all_overrides(monkeypatch):
    kb = SimpleNamespace(
        settings={
            "rerank_candidate_k": 20,
            "rerank_score_threshold": "0.4",
        },
        rerank_model_id=uuid4(),
    )
    monkeypatch.setattr(
        vector_store.KnowledgeBase, "get_or_none", AsyncMock(return_value=kb)
    )

    config = await VectorStore()._resolve_rerank_config(
        uuid4(),
        {
            "rerank_enabled": False,
            "rerank_candidate_k": 5,
            "rerank_fail_open": False,
            "rerank_score_threshold": None,
        },
    )

    assert config == {
        "model_id": str(kb.rerank_model_id),
        "enabled": False,
        "candidate_k": 5,
        "score_threshold": None,
    }


@pytest.mark.asyncio
async def test_rerank_config_ignores_null_candidate_override(monkeypatch):
    monkeypatch.setattr(
        vector_store.KnowledgeBase, "get_or_none", AsyncMock(return_value=None)
    )

    config = await VectorStore(rerank_model_id="reranker")._resolve_rerank_config(
        uuid4(), {"rerank_candidate_k": None, "rerank_score_threshold": "0.8"}
    )

    assert config == {
        "model_id": "reranker",
        "enabled": True,
        "candidate_k": 10,
        "score_threshold": 0.8,
    }


@pytest.mark.asyncio
async def test_rerank_failure_propagates(monkeypatch):
    manager = SimpleNamespace(rerank=AsyncMock(side_effect=RuntimeError("offline")))
    monkeypatch.setattr(vector_store, "_get_model_manager", lambda: manager)
    results = [{"content": "first", "score": 0.5}]
    store = VectorStore()

    assert await store._rerank_results("query", [], "reranker", None) == []
    with pytest.raises(RuntimeError, match="offline"):
        await store._rerank_results("query", results, "reranker", None)
