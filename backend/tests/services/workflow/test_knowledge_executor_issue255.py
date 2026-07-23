from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.knowledge_base import KnowledgeBase
from app.models.workflow import Workflow
from app.services.workflow.executors.knowledge import KnowledgeRetrievalNodeExecutor

retrieval = import_module("app.services.retrieval")


class _Query:
    def __init__(self, result):
        self.result = result

    def only(self, *_fields):
        return self

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

    workflow_id, team_id, unknown_kb_id = uuid4(), uuid4(), uuid4()
    monkeypatch.setattr(
        Workflow,
        "filter",
        MagicMock(return_value=_Query(SimpleNamespace(team_id=team_id))),
    )
    kb_filter = MagicMock(return_value=_Query(None))
    monkeypatch.setattr(KnowledgeBase, "filter", kb_filter)
    missing_kb = await executor.execute(
        _node(
            knowledgeBaseId=str(unknown_kb_id),
            querySource="constant",
            queryConstantValue="q",
        ),
        context,
        SimpleNamespace(workflow_id=workflow_id),
    )

    kb_filter.assert_called_once_with(id=str(unknown_kb_id), team_id=team_id)
    assert missing_kb_id.error == "validation_error"
    assert missing_query.error == "query_parameter_required"
    assert missing_kb.error == "not_found"
    context.resolve_variable_ref.assert_awaited_once_with("start.query")


@pytest.mark.asyncio
@pytest.mark.parametrize("query_source", ["variable", "constant"])
async def test_retrieval_formats_results_and_forwards_config(monkeypatch, query_source):
    kb_id, team_id, embedding_id, rerank_id = (uuid4() for _ in range(4))
    document_id, chunk_id = uuid4(), uuid4()
    workflow_id = uuid4()
    kb = SimpleNamespace(
        id=kb_id,
        name="Docs",
        status="active",
        embedding_model_id=embedding_id,
        rerank_model_id=rerank_id,
        team_id=team_id,
    )
    retrieve = AsyncMock(
        return_value=SimpleNamespace(
            results=(
                {
                    "content": "first",
                    "score": 0.8,
                    "metadata": {"page": 1},
                    "document_id": document_id,
                    "chunk_id": chunk_id,
                },
                {"content": "second"},
            )
        )
    )
    monkeypatch.setattr(
        Workflow,
        "filter",
        MagicMock(return_value=_Query(SimpleNamespace(team_id=team_id))),
    )
    kb_filter = MagicMock(return_value=_Query(kb))
    monkeypatch.setattr(KnowledgeBase, "filter", kb_filter)
    monkeypatch.setattr(retrieval, "retrieve", retrieve)
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
        _node(**config), context, SimpleNamespace(workflow_id=workflow_id)
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
    kb_filter.assert_called_once_with(id=str(kb_id), team_id=team_id)
    request = retrieve.await_args.args[0]
    assert request.query == expected_query
    assert request.search_mode == "vector"
    assert request.top_k == 3
    assert request.score_threshold == 0.4
    assert request.targets[0].kb_id == kb_id
    assert request.targets[0].rerank_model_id == rerank_id


@pytest.mark.asyncio
async def test_retrieval_translates_search_failures(monkeypatch):
    workflow_id, kb_id, team_id = uuid4(), uuid4(), uuid4()
    kb = SimpleNamespace(
        id=kb_id,
        name="Docs",
        status="active",
        embedding_model_id=None,
        rerank_model_id=None,
        team_id=team_id,
    )
    monkeypatch.setattr(
        Workflow,
        "filter",
        MagicMock(return_value=_Query(SimpleNamespace(team_id=team_id))),
    )
    monkeypatch.setattr(KnowledgeBase, "filter", MagicMock(return_value=_Query(kb)))
    monkeypatch.setattr(retrieval, "retrieve", AsyncMock(side_effect=RuntimeError()))

    result = await KnowledgeRetrievalNodeExecutor().execute(
        _node(
            knowledgeBaseId=str(kb_id),
            querySource="constant",
            queryConstantValue="q",
        ),
        SimpleNamespace(resolve_variable_ref=AsyncMock()),
        SimpleNamespace(workflow_id=workflow_id),
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
