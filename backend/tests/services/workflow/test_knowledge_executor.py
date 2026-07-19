"""Behavioral tests for the knowledge retrieval workflow executor."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.workflow.executors.knowledge import KnowledgeRetrievalNodeExecutor


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "expected_error"),
    [
        ({}, "validation_error"),
        (
            {
                "knowledgeBaseId": "kb-1",
                "querySource": "constant",
                "queryConstantValue": "",
            },
            "query_parameter_required",
        ),
    ],
)
async def test_knowledge_retrieval_validates_required_configuration(
    config, expected_error
):
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock(return_value=None)

    result = await KnowledgeRetrievalNodeExecutor().execute(
        {"data": {"knowledgeRetrievalConfig": config}}, context, MagicMock()
    )

    assert result.error == expected_error


@pytest.mark.asyncio
async def test_knowledge_retrieval_formats_search_results():
    knowledge_base = SimpleNamespace(
        embedding_model_id=uuid4(), rerank_model_id=uuid4(), team_id=uuid4()
    )
    query = MagicMock()
    query.first = AsyncMock(return_value=knowledge_base)
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock(return_value="relevant question")
    document_id, chunk_id = uuid4(), uuid4()
    vector_store = MagicMock()
    vector_store.search = AsyncMock(
        return_value=[
            {
                "content": "First passage",
                "score": 0.9,
                "metadata": {"source": "guide"},
                "document_id": document_id,
                "chunk_id": chunk_id,
            },
            {"content": "Second passage"},
        ]
    )

    with (
        patch("app.models.knowledge_base.KnowledgeBase.filter", return_value=query),
        patch(
            "app.services.vector_store.VectorStore", return_value=vector_store
        ) as store,
    ):
        result = await KnowledgeRetrievalNodeExecutor().execute(
            {
                "data": {
                    "knowledgeRetrievalConfig": {
                        "knowledgeBaseId": "kb-1",
                        "queryVariableRef": "{{start.query}}",
                        "searchMode": "vector",
                        "topK": 2,
                        "threshold": 0.5,
                        "outputVariable": "matches",
                    }
                }
            },
            context,
            MagicMock(),
        )

    assert result.outputs == {
        "matches": [
            {
                "content": "First passage",
                "score": 0.9,
                "metadata": {"source": "guide"},
                "documentId": str(document_id),
                "chunkId": str(chunk_id),
            },
            {
                "content": "Second passage",
                "score": 0,
                "metadata": {},
                "documentId": None,
                "chunkId": None,
            },
        ],
        "context": "First passage\n\n---\n\nSecond passage",
        "totalFound": 2,
    }
    store.assert_called_once_with(
        embedding_model_id=str(knowledge_base.embedding_model_id),
        rerank_model_id=str(knowledge_base.rerank_model_id),
        team_id=str(knowledge_base.team_id),
    )
    vector_store.search.assert_awaited_once_with(
        kb_id="kb-1",
        query="relevant question",
        search_mode="vector",
        top_k=2,
        score_threshold=0.5,
    )


@pytest.mark.asyncio
async def test_knowledge_retrieval_translates_search_errors():
    knowledge_base = SimpleNamespace(
        embedding_model_id=None, rerank_model_id=None, team_id=None
    )
    query = MagicMock()
    query.first = AsyncMock(return_value=knowledge_base)
    vector_store = MagicMock()
    vector_store.search = AsyncMock(side_effect=RuntimeError("search unavailable"))

    with (
        patch("app.models.knowledge_base.KnowledgeBase.filter", return_value=query),
        patch("app.services.vector_store.VectorStore", return_value=vector_store),
        patch(
            "app.services.workflow.executors.knowledge.translate_public_workflow_error",
            return_value="retrieval_error",
        ) as translate_error,
    ):
        result = await KnowledgeRetrievalNodeExecutor().execute(
            {
                "data": {
                    "knowledgeRetrievalConfig": {
                        "knowledgeBaseId": "kb-1",
                        "querySource": "constant",
                        "queryConstantValue": "question",
                    }
                }
            },
            MagicMock(),
            MagicMock(),
        )

    assert result.error == "retrieval_error"
    translate_error.assert_called_once()
