import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_rag import (
    aggregate_rag_contexts,
    build_rag_prompt,
    perform_rag_retrieval,
)


@pytest.mark.asyncio
async def test_perform_rag_retrieval_supports_lexical_only_and_isolates_failures():
    agent = SimpleNamespace(id=uuid4())
    lexical_kb = SimpleNamespace(
        id=uuid4(),
        name="Lexical",
        status="active",
        embedding_model_id=None,
        rerank_model_id=None,
        team_id=uuid4(),
    )
    successful_kb = SimpleNamespace(
        id=uuid4(),
        name="Handbook",
        embedding_model_id=uuid4(),
        rerank_model_id=uuid4(),
        team_id=uuid4(),
        status="active",
    )
    failed_kb = SimpleNamespace(
        id=uuid4(),
        name="Broken",
        embedding_model_id=uuid4(),
        rerank_model_id=None,
        team_id=uuid4(),
        status="active",
    )
    associations = [
        SimpleNamespace(
            knowledge_base=lexical_kb,
            search_mode="fulltext",
            retrieval_top_k=2,
            score_threshold=0.9,
        ),
        SimpleNamespace(
            knowledge_base=successful_kb,
            search_mode="hybrid",
            retrieval_top_k=3,
            score_threshold=0.4,
        ),
        SimpleNamespace(
            knowledge_base=failed_kb,
            search_mode="vector",
            retrieval_top_k=5,
            score_threshold=0.2,
        ),
    ]
    query = MagicMock()
    query.prefetch_related = AsyncMock(return_value=associations)
    lexical_store = SimpleNamespace(search=AsyncMock(return_value=[]))
    successful_store = SimpleNamespace(
        search=AsyncMock(
            return_value=[
                {
                    "document_id": uuid4(),
                    "document_name": "Guide",
                    "content": "Answer",
                    "score": 0.9,
                }
            ]
        )
    )
    failed_store = SimpleNamespace(search=AsyncMock(side_effect=RuntimeError("down")))

    with (
        patch(
            "app.models.agent.AgentKnowledgeBase.filter", return_value=query
        ) as filter_mock,
        patch(
            "app.services.vector_store.VectorStore",
            side_effect=[lexical_store, successful_store, failed_store],
        ) as store_mock,
    ):
        results = await perform_rag_retrieval(agent, "question")

    filter_mock.assert_called_once_with(agent_id=agent.id)
    query.prefetch_related.assert_awaited_once_with("knowledge_base")
    assert store_mock.call_args_list[0].kwargs == {
        "embedding_model_id": None,
        "rerank_model_id": None,
        "team_id": str(lexical_kb.team_id),
    }
    lexical_store.search.assert_awaited_once_with(
        kb_id=lexical_kb.id,
        query="question",
        search_mode="fulltext",
        top_k=2,
        score_threshold=0.9,
    )
    assert store_mock.call_args_list[1].kwargs == {
        "embedding_model_id": str(successful_kb.embedding_model_id),
        "rerank_model_id": str(successful_kb.rerank_model_id),
        "team_id": str(successful_kb.team_id),
    }
    assert store_mock.call_args_list[2].kwargs["rerank_model_id"] is None
    successful_store.search.assert_awaited_once_with(
        kb_id=successful_kb.id,
        query="question",
        search_mode="hybrid",
        top_k=3,
        score_threshold=0.4,
    )
    assert results == [
        {
            "kb_id": str(successful_kb.id),
            "kb_name": "Handbook",
            "document_id": str(successful_store.search.return_value[0]["document_id"]),
            "document_name": "Guide",
            "content": "Answer",
            "score": 0.9,
        }
    ]


def test_aggregate_rag_contexts_merges_documents_and_keeps_best_numeric_score():
    contexts = [
        {
            "kb_id": "kb-1",
            "kb_name": "KB",
            "document_id": "doc-1",
            "document_name": "Guide",
            "content": "first",
            "score": None,
        },
        {
            "kb_id": "kb-1",
            "document_id": "doc-1",
            "content": "second",
            "score": 0.8,
        },
        {
            "kb_id": "kb-1",
            "document_name": "Fallback",
            "content": None,
            "score": "unknown",
        },
    ]

    assert aggregate_rag_contexts(contexts) == [
        {
            "kb_id": "kb-1",
            "kb_name": "KB",
            "document_id": "doc-1",
            "document_name": "Guide",
            "score": 0.8,
            "content": "first\n\nsecond",
        },
        {
            "kb_id": "kb-1",
            "kb_name": None,
            "document_id": None,
            "document_name": "Fallback",
            "score": "unknown",
            "content": "",
        },
    ]


def test_build_rag_prompt_returns_plain_message_without_context():
    assert aggregate_rag_contexts([]) == []
    assert build_rag_prompt([], "plain question") == "plain question"


def test_build_rag_prompt_numbers_aggregated_references():
    prompt = build_rag_prompt(
        [
            {
                "kb_id": "kb-1",
                "kb_name": "Policies",
                "document_id": "doc-1",
                "document_name": "Leave",
                "content": "part one",
                "score": 0.4,
            },
            {
                "kb_id": "kb-1",
                "kb_name": "Policies",
                "document_id": "doc-1",
                "document_name": "Leave",
                "content": "part two",
                "score": 0.7,
            },
        ],
        "How much leave?",
    )

    assert "[[ref:1]] Policies - Leave:\npart one\n\npart two" in prompt
    assert "[[ref:2]]" not in prompt
    assert "Use ONLY [[cite:N]]" in prompt
    assert "User question: How much leave?" in prompt


@pytest.mark.asyncio
async def test_perform_rag_retrieval_is_bounded_skips_inactive_and_truncates_globally():
    agent = SimpleNamespace(id=uuid4())
    active_kbs = [
        SimpleNamespace(
            id=uuid4(),
            name=f"KB {index}",
            status="active",
            embedding_model_id=uuid4(),
            rerank_model_id=None,
            team_id=uuid4(),
        )
        for index in range(10)
    ]
    inactive_kb = SimpleNamespace(
        id=uuid4(),
        name="Archived",
        status="archived",
        embedding_model_id=uuid4(),
        rerank_model_id=None,
        team_id=uuid4(),
    )
    associations = [
        SimpleNamespace(
            knowledge_base=kb,
            search_mode="vector",
            retrieval_top_k=2,
            score_threshold=0.0,
        )
        for kb in [*active_kbs, inactive_kb]
    ]
    query = MagicMock()
    query.prefetch_related = AsyncMock(return_value=associations)
    active_searches = 0
    max_active_searches = 0

    def make_store(**_kwargs):
        async def search(**kwargs):
            nonlocal active_searches, max_active_searches
            active_searches += 1
            max_active_searches = max(max_active_searches, active_searches)
            await asyncio.sleep(0.01)
            active_searches -= 1
            index = next(
                index for index, kb in enumerate(active_kbs) if kb.id == kwargs["kb_id"]
            )
            return [
                {
                    "document_id": f"doc-{index}",
                    "document_name": f"Doc {index}",
                    "content": f"Result {index}",
                    "score": index / 10,
                }
            ]

        return SimpleNamespace(search=search)

    with (
        patch("app.models.agent.AgentKnowledgeBase.filter", return_value=query),
        patch(
            "app.services.vector_store.VectorStore", side_effect=make_store
        ) as store_mock,
    ):
        results = await perform_rag_retrieval(agent, "question")

    assert max_active_searches == 8
    assert store_mock.call_count == 10
    assert [result["content"] for result in results] == ["Result 9", "Result 8"]
