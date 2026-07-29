from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_rag import (
    _bounded_rewrite_history,
    aggregate_rag_contexts,
    build_rag_prompt,
    contextualize_retrieval_query,
    perform_rag_retrieval,
    should_contextualize_query,
)


def test_contextualization_trigger_is_conservative():
    assert should_contextualize_query("What about its retention period?")
    assert should_contextualize_query("它的保留期限呢？")
    assert not should_contextualize_query("Annual leave retention period")
    assert not should_contextualize_query("  ")


def test_contextualization_history_has_message_and_token_bounds(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_rag.count_tokens", lambda _content: 1_000
    )
    history = [
        SimpleNamespace(role="user", content=f"message-{index}") for index in range(6)
    ]

    assert [item["content"] for item in _bounded_rewrite_history(history)] == [
        "message-4",
        "message-5",
    ]


@pytest.mark.asyncio
async def test_contextualization_disabled_and_standalone_skip_model(monkeypatch):
    agent = SimpleNamespace(team_id=uuid4(), model_id=uuid4())
    history = [SimpleNamespace(role="user", content="annual leave")]
    team_chat = AsyncMock()
    with patch("app.llm.model_manager.team_chat", team_chat):
        disabled = await contextualize_retrieval_query(agent, "What about it?", history)
        monkeypatch.setattr(
            "app.api.v1.endpoints.chat_rag.settings.RAG_QUERY_CONTEXTUALIZATION_ENABLED",
            True,
        )
        standalone = await contextualize_retrieval_query(
            agent, "Annual leave retention period", history
        )

    assert disabled.status == "disabled"
    assert standalone.status == "not_needed"
    team_chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_contextualize_retrieval_query_uses_agent_model_and_branch_history(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_rag.settings.RAG_QUERY_CONTEXTUALIZATION_ENABLED",
        True,
    )
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4(), model_id=uuid4())
    history = [
        SimpleNamespace(role="user", content="Tell me about the leave policy"),
        SimpleNamespace(role="assistant", content="It covers annual leave."),
        SimpleNamespace(role="tool", content="ignored"),
    ]
    response = SimpleNamespace(
        content='{"query":"annual leave What about its limit?",'
        '"evidence":"annual leave"}'
    )
    model_id = uuid4()
    team_model_query = MagicMock()
    team_model_query.prefetch_related.return_value = team_model_query
    team_model_query.first = AsyncMock(
        return_value=SimpleNamespace(model=SimpleNamespace(id=model_id))
    )

    with (
        patch("app.models.model.TeamModel.filter", return_value=team_model_query),
        patch(
            "app.llm.model_manager.team_chat", AsyncMock(return_value=response)
        ) as team_chat,
    ):
        result = await contextualize_retrieval_query(
            agent, "What about its limit?", history
        )

    assert result.query == "annual leave What about its limit?"
    assert result.status == "rewritten"
    call = team_chat.await_args.kwargs
    assert call["team_id"] == str(agent.team_id)
    assert call["model_id"] == str(model_id)
    assert call["messages"][-1] == {
        "role": "user",
        "content": "What about its limit?",
    }
    assert {message["role"] for message in call["messages"]} == {
        "system",
        "user",
        "assistant",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [None, "   "])
async def test_contextualize_retrieval_query_falls_back_on_empty_response(
    content, monkeypatch
):
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_rag.settings.RAG_QUERY_CONTEXTUALIZATION_ENABLED",
        True,
    )
    agent = SimpleNamespace(team_id=uuid4(), model_id=uuid4())
    history = [SimpleNamespace(role="user", content="Tell me about policy A")]
    team_model_query = MagicMock()
    team_model_query.prefetch_related.return_value = team_model_query
    team_model_query.first = AsyncMock(
        return_value=SimpleNamespace(model=SimpleNamespace(id=uuid4()))
    )
    with (
        patch("app.models.model.TeamModel.filter", return_value=team_model_query),
        patch(
            "app.llm.model_manager.team_chat",
            AsyncMock(return_value=SimpleNamespace(content=content)),
        ),
    ):
        assert (
            await contextualize_retrieval_query(agent, "And its limit?", history)
        ).query == "And its limit?"


@pytest.mark.asyncio
async def test_contextualize_retrieval_query_rejects_unsupported_additions(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_rag.settings.RAG_QUERY_CONTEXTUALIZATION_ENABLED",
        True,
    )
    agent = SimpleNamespace(team_id=uuid4(), model_id=uuid4())
    history = [SimpleNamespace(role="user", content="Tell me about policy A")]
    team_model_query = MagicMock()
    team_model_query.prefetch_related.return_value = team_model_query
    team_model_query.first = AsyncMock(
        return_value=SimpleNamespace(model=SimpleNamespace(id=uuid4()))
    )
    response = SimpleNamespace(
        content='{"query":"policy A has a 30-day limit", "evidence":"policy A"}'
    )
    with (
        patch("app.models.model.TeamModel.filter", return_value=team_model_query),
        patch("app.llm.model_manager.team_chat", AsyncMock(return_value=response)),
    ):
        result = await contextualize_retrieval_query(
            agent, "What about its limit?", history
        )

    assert result.query == "What about its limit?"
    assert result.status == "fallback"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError("provider"), TimeoutError()])
async def test_contextualize_retrieval_query_falls_back_on_model_failure(
    failure, monkeypatch
):
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_rag.settings.RAG_QUERY_CONTEXTUALIZATION_ENABLED",
        True,
    )
    agent = SimpleNamespace(team_id=uuid4(), model_id=uuid4())
    history = [SimpleNamespace(role="user", content="Tell me about policy A")]
    team_model_query = MagicMock()
    team_model_query.prefetch_related.return_value = team_model_query
    team_model_query.first = AsyncMock(
        return_value=SimpleNamespace(model=SimpleNamespace(id=uuid4()))
    )
    with (
        patch("app.models.model.TeamModel.filter", return_value=team_model_query),
        patch("app.llm.model_manager.team_chat", AsyncMock(side_effect=failure)),
    ):
        result = await contextualize_retrieval_query(agent, "And its limit?", history)

    assert result.query == "And its limit?"
    assert result.status == "fallback"


@pytest.mark.asyncio
async def test_contextualize_retrieval_query_handles_unusable_context_and_model(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_rag.settings.RAG_QUERY_CONTEXTUALIZATION_ENABLED",
        True,
    )
    query = "What about it?"
    assert (
        await contextualize_retrieval_query(
            SimpleNamespace(team_id=None, model_id=None), query, []
        )
    ).status == "not_needed"
    assert (
        await contextualize_retrieval_query(
            SimpleNamespace(team_id=None, model_id=None),
            query,
            [SimpleNamespace(role="user", content="policy")],
        )
    ).status == "fallback"
    assert (
        await contextualize_retrieval_query(
            SimpleNamespace(team_id=uuid4(), model_id=uuid4()),
            query,
            [SimpleNamespace(role="tool", content="ignored")],
        )
    ).status == "not_needed"

    team_model_query = MagicMock()
    team_model_query.prefetch_related.return_value = team_model_query
    team_model_query.first = AsyncMock(return_value=None)
    with patch("app.models.model.TeamModel.filter", return_value=team_model_query):
        result = await contextualize_retrieval_query(
            SimpleNamespace(team_id=uuid4(), model_id=uuid4()),
            query,
            [SimpleNamespace(role="user", content="policy")],
        )
    assert result.status == "fallback"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        '{"query":"policy What about it?","evidence":"missing"}',
        '{"query":"policy What about it?","evidence":"policy","extra":"x"}',
        '{"query":1,"evidence":"policy"}',
    ],
)
async def test_contextualize_retrieval_query_rejects_malformed_output(
    content, monkeypatch
):
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_rag.settings.RAG_QUERY_CONTEXTUALIZATION_ENABLED",
        True,
    )
    team_model_query = MagicMock()
    team_model_query.prefetch_related.return_value = team_model_query
    team_model_query.first = AsyncMock(
        return_value=SimpleNamespace(model=SimpleNamespace(id=uuid4()))
    )
    with (
        patch("app.models.model.TeamModel.filter", return_value=team_model_query),
        patch(
            "app.llm.model_manager.team_chat",
            AsyncMock(return_value=SimpleNamespace(content=content)),
        ),
    ):
        result = await contextualize_retrieval_query(
            SimpleNamespace(team_id=uuid4(), model_id=uuid4()),
            "What about it?",
            [SimpleNamespace(role="user", content="policy")],
        )
    assert result.status == "fallback"


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
        settings=None,
    )
    successful_kb = SimpleNamespace(
        id=uuid4(),
        name="Handbook",
        embedding_model_id=uuid4(),
        rerank_model_id=uuid4(),
        team_id=uuid4(),
        status="active",
        settings=None,
    )
    failed_kb = SimpleNamespace(
        id=uuid4(),
        name="Broken",
        embedding_model_id=uuid4(),
        rerank_model_id=None,
        team_id=uuid4(),
        status="active",
        settings=None,
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
    document_id = uuid4()
    retrieve = AsyncMock(
        return_value=SimpleNamespace(
            results=(
                {
                    "kb_id": str(successful_kb.id),
                    "kb_name": "Handbook",
                    "document_id": document_id,
                    "document_name": "Guide",
                    "content": "Answer",
                    "score": 0.9,
                },
            )
        )
    )

    with (
        patch(
            "app.models.agent.AgentKnowledgeBase.filter", return_value=query
        ) as filter_mock,
        patch("app.api.v1.endpoints.chat_rag.retrieve", retrieve),
    ):
        results = await perform_rag_retrieval(agent, "question")

    filter_mock.assert_called_once_with(agent_id=agent.id)
    query.prefetch_related.assert_awaited_once_with("knowledge_base")
    request = retrieve.await_args.args[0]
    assert request.query == "question"
    assert request.top_k == 5
    assert [target.kb_id for target in request.targets] == [
        lexical_kb.id,
        successful_kb.id,
        failed_kb.id,
    ]
    assert request.targets[0].search_mode == "fulltext"
    assert request.targets[0].embedding_model_id is None
    assert request.targets[1].rerank_model_id == successful_kb.rerank_model_id
    assert request.targets[2].score_threshold == 0.2
    assert results == [
        {
            "kb_id": str(successful_kb.id),
            "kb_name": "Handbook",
            "document_id": str(document_id),
            "document_name": "Guide",
            "content": "Answer",
            "score": 0.9,
            "metadata": {},
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
            settings=None,
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
        settings=None,
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
    retrieve = AsyncMock(
        return_value=SimpleNamespace(
            results=(
                {
                    "kb_id": str(active_kbs[9].id),
                    "kb_name": "KB 9",
                    "document_id": "doc-9",
                    "document_name": "Doc 9",
                    "content": "Result 9",
                    "score": 0.9,
                },
                {
                    "kb_id": str(active_kbs[8].id),
                    "kb_name": "KB 8",
                    "document_id": "doc-8",
                    "document_name": "Doc 8",
                    "content": "Result 8",
                    "score": 0.8,
                },
            )
        )
    )

    with (
        patch("app.models.agent.AgentKnowledgeBase.filter", return_value=query),
        patch("app.api.v1.endpoints.chat_rag.retrieve", retrieve),
    ):
        results = await perform_rag_retrieval(agent, "question")

    request = retrieve.await_args.args[0]
    assert len(request.targets) == 11
    assert request.targets[-1].status == "archived"
    assert request.top_k == 2
    assert [result["content"] for result in results] == ["Result 9", "Result 8"]
