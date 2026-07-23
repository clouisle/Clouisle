from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.retrieval_evaluation import EvaluationRunStatus
from app.services.retrieval import RetrievalResponse
from app.tasks import retrieval_evaluation as task


class Query:
    def __init__(self, result):
        self.result = result

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.result


class Cases:
    def __init__(self, cases):
        self.cases = cases

    def all(self):
        return self

    def order_by(self, *_args):
        return self

    def __await__(self):
        async def resolve():
            return self.cases

        return resolve().__await__()


@pytest.mark.anyio
async def test_task_happy_path_persists_snapshot_without_content():
    chunk_id, document_id = uuid4(), uuid4()
    case = SimpleNamespace(
        id=uuid4(),
        query="secret query",
        chunk_relevance={str(chunk_id): 3},
        document_relevance={str(document_id): 2},
        expected_empty=False,
    )
    dataset = SimpleNamespace(knowledge_base_id=uuid4(), cases=Cases([case]))
    run = SimpleNamespace(
        id=uuid4(),
        dataset=dataset,
        status="pending",
        started_at=None,
        config_snapshot={
            "search_mode": "hybrid",
            "top_k": 10,
            "score_threshold": 0,
            "dense_weight": 1,
            "lexical_weight": 1,
            "rrf_k": 60,
            "rerank_enabled": False,
            "rerank_candidate_k": 20,
            "rerank_fail_open": True,
            "rerank_score_threshold": None,
        },
        save=AsyncMock(),
        refresh_from_db=AsyncMock(),
        summary_metrics=None,
        finished_at=None,
        error_message=None,
    )
    kb = SimpleNamespace(
        id=dataset.knowledge_base_id,
        name="kb",
        team_id=uuid4(),
        status="active",
        embedding_model_id=None,
        rerank_model_id=None,
        embedding_dimension=None,
    )
    update = AsyncMock()
    count_query = MagicMock(count=AsyncMock(return_value=0))
    result = {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "score": 0.8,
        "content": "must not persist",
    }
    with (
        patch.object(task.EvaluationRun, "filter", return_value=Query(run)),
        patch.object(task.KnowledgeBase, "get", AsyncMock(return_value=kb)),
        patch.object(
            task, "retrieve", AsyncMock(return_value=RetrievalResponse((result,), ()))
        ),
        patch.object(task.EvaluationCaseResult, "update_or_create", update),
        patch.object(task.EvaluationCaseResult, "filter", return_value=count_query),
    ):
        response = await task.execute_evaluation_run(run.id)

    defaults = update.await_args.kwargs["defaults"]
    assert response["status"] == "completed"
    assert run.status == EvaluationRunStatus.COMPLETED.value
    assert defaults["case_snapshot"]["query"] == "secret query"
    assert "content" not in defaults["candidates"][0]


@pytest.mark.anyio
async def test_task_does_not_overwrite_terminal_cancellation():
    case = SimpleNamespace(
        id=uuid4(),
        query="q",
        chunk_relevance={},
        document_relevance={},
        expected_empty=True,
    )
    dataset = SimpleNamespace(knowledge_base_id=uuid4(), cases=Cases([case]))
    refresh_count = 0

    async def refresh(*, fields):
        nonlocal refresh_count
        refresh_count += 1
        if refresh_count == 2:
            run.status = EvaluationRunStatus.CANCELED.value

    run = SimpleNamespace(
        id=uuid4(),
        dataset=dataset,
        status="pending",
        started_at=None,
        config_snapshot={
            "search_mode": "fulltext",
            "top_k": 10,
            "score_threshold": 0,
            "dense_weight": 1,
            "lexical_weight": 1,
            "rrf_k": 60,
            "rerank_enabled": False,
            "rerank_candidate_k": 20,
            "rerank_fail_open": True,
            "rerank_score_threshold": None,
        },
        save=AsyncMock(),
        refresh_from_db=AsyncMock(side_effect=refresh),
        summary_metrics=None,
        finished_at=None,
        error_message=None,
    )
    kb = SimpleNamespace(
        id=dataset.knowledge_base_id,
        name="kb",
        team_id=uuid4(),
        status="active",
        embedding_model_id=None,
        rerank_model_id=None,
        embedding_dimension=None,
    )
    with (
        patch.object(task.EvaluationRun, "filter", return_value=Query(run)),
        patch.object(task.KnowledgeBase, "get", AsyncMock(return_value=kb)),
        patch.object(
            task, "retrieve", AsyncMock(return_value=RetrievalResponse((), ()))
        ),
        patch.object(task.EvaluationCaseResult, "update_or_create", AsyncMock()),
        patch.object(
            task.EvaluationCaseResult,
            "filter",
            return_value=MagicMock(count=AsyncMock(return_value=0)),
        ),
    ):
        response = await task.execute_evaluation_run(run.id)

    assert response["status"] == "canceled"
    assert run.status == EvaluationRunStatus.CANCELED.value
    assert not any(
        "summary_metrics" in call.kwargs.get("update_fields", [])
        for call in run.save.await_args_list
    )


@pytest.mark.anyio
async def test_task_handles_missing_canceled_redelivery_and_stable_failure():
    run_id = uuid4()
    with patch.object(task.EvaluationRun, "filter", return_value=Query(None)):
        assert (await task.execute_evaluation_run(run_id))["status"] == "missing"

    canceled = SimpleNamespace(status="canceled")
    with patch.object(task.EvaluationRun, "filter", return_value=Query(canceled)):
        assert (await task.execute_evaluation_run(run_id))["status"] == "canceled"

    completed = SimpleNamespace(status="completed")
    with patch.object(task.EvaluationRun, "filter", return_value=Query(completed)):
        assert (await task.execute_evaluation_run(run_id))["status"] == "completed"

    dataset = SimpleNamespace(knowledge_base_id=uuid4())
    failed = SimpleNamespace(
        id=run_id,
        dataset=dataset,
        status="pending",
        started_at=None,
        config_snapshot={},
        save=AsyncMock(),
        error_message=None,
        finished_at=None,
    )
    with (
        patch.object(task.EvaluationRun, "filter", return_value=Query(failed)),
        patch.object(
            task.KnowledgeBase,
            "get",
            AsyncMock(side_effect=RuntimeError("database password")),
        ),
    ):
        response = await task.execute_evaluation_run(run_id)

    assert response["status"] == "failed"
    assert failed.error_message == "RuntimeError"
