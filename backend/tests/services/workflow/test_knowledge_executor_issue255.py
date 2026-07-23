from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.knowledge_base import KnowledgeBase
from app.services.workflow.executors.knowledge import KnowledgeRetrievalNodeExecutor

vector_store = import_module("app.services.vector_store")


class _Query:
    def __init__(self, result):
        self.result = result

    async def first(self):
        return self.result


def _node(**config):
    return {"data": {"knowledgeRetrievalConfig": config}}


@pytest.mark.asyncio
async def test_retrieval_validates_required_inputs_and_missing_kb(monkeypatch):
    executor = KnowledgeRetrievalNodeExecutor()
    context = SimpleNamespace(resolve_variable_ref=AsyncMock(return_value=""))

    missing_kb_id = await executor.execute(_node(), context, MagicMock())
    missing_query = await executor.execute(
        _node(knowledgeBaseId=str(uuid4()), queryVariableRef="start.query"),
        context,
        MagicMock(),
    )

    monkeypatch.setattr(KnowledgeBase, "filter", MagicMock(return_value=_Query(None)))
    missing_kb = await executor.execute(
        _node(
            knowledgeBaseId=str(uuid4()), querySource="constant", queryConstantValue="q"
        ),
        context,
        MagicMock(),
    )

    assert missing_kb_id.error == "validation_error"
    assert missing_query.error == "query_parameter_required"
    assert missing_kb.error == "not_found"
    context.resolve_variable_ref.assert_awaited_once_with("start.query")


@pytest.mark.asyncio
@pytest.mark.parametrize("query_source", ["variable", "constant"])
async def test_retrieval_formats_results_and_forwards_config(monkeypatch, query_source):
    kb_id, team_id, embedding_id, rerank_id = (uuid4() for _ in range(4))
    document_id, chunk_id = uuid4(), uuid4()
    kb = SimpleNamespace(
        embedding_model_id=embedding_id,
        rerank_model_id=rerank_id,
        team_id=team_id,
    )
    search = AsyncMock(
        return_value=[
            {
                "content": "first",
                "score": 0.8,
                "metadata": {"page": 1},
                "document_id": document_id,
                "chunk_id": chunk_id,
            },
            {"content": "second"},
        ]
    )
    store = MagicMock()
    store.search = search
    store_factory = MagicMock(return_value=store)
    monkeypatch.setattr(KnowledgeBase, "filter", MagicMock(return_value=_Query(kb)))
    monkeypatch.setattr(vector_store, "VectorStore", store_factory)
    context = SimpleNamespace(resolve_variable_ref=AsyncMock(return_value="resolved"))
    config = {
        "knowledgeBaseId": str(kb_id),
        "querySource": query_source,
        "queryVariableRef": "start.query",
        "queryConstantValue": "constant",
        "searchMode": "vector",
        "topK": 3,
        "threshold": 0.4,
        "outputVariable": "matches",
    }

    result = await KnowledgeRetrievalNodeExecutor().execute(
        _node(**config), context, MagicMock()
    )

    expected_query = "resolved" if query_source == "variable" else "constant"
    assert result.success is True
    assert result.outputs == {
        "matches": [
            {
                "content": "first",
                "score": 0.8,
                "metadata": {"page": 1},
                "documentId": str(document_id),
                "chunkId": str(chunk_id),
            },
            {
                "content": "second",
                "score": 0,
                "metadata": {},
                "documentId": None,
                "chunkId": None,
            },
        ],
        "context": "first\n\n---\n\nsecond",
        "totalFound": 2,
    }
    store_factory.assert_called_once_with(
        embedding_model_id=str(embedding_id),
        rerank_model_id=str(rerank_id),
        team_id=str(team_id),
    )
    search.assert_awaited_once_with(
        kb_id=str(kb_id),
        query=expected_query,
        search_mode="vector",
        top_k=3,
        score_threshold=0.4,
    )


@pytest.mark.asyncio
async def test_retrieval_translates_search_failures(monkeypatch):
    kb = SimpleNamespace(embedding_model_id=None, rerank_model_id=None, team_id=None)
    store = MagicMock()
    store.search = AsyncMock(side_effect=RuntimeError())
    monkeypatch.setattr(KnowledgeBase, "filter", MagicMock(return_value=_Query(kb)))
    monkeypatch.setattr(vector_store, "VectorStore", MagicMock(return_value=store))

    result = await KnowledgeRetrievalNodeExecutor().execute(
        _node(
            knowledgeBaseId=str(uuid4()),
            querySource="constant",
            queryConstantValue="q",
        ),
        SimpleNamespace(resolve_variable_ref=AsyncMock()),
        MagicMock(),
    )

    assert result.success is False
    assert result.error == "Workflow execution error"


def test_retrieval_declares_outputs():
    executor = KnowledgeRetrievalNodeExecutor()

    assert executor.get_output_variables({}) == [
        {"name": "results", "type": "array"},
        {"name": "context", "type": "string"},
        {"name": "totalFound", "type": "number"},
    ]
    assert [(item.name, item.type.kind) for item in executor.get_output_specs({})] == [
        ("results", "array"),
        ("context", "string"),
        ("totalFound", "number"),
    ]
