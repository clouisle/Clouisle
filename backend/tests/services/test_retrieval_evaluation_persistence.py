from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.response import BusinessError
from app.schemas.retrieval_evaluation import EvaluationCaseInput, EvaluationRunCreate
from app.services import retrieval_evaluation_store as store


@pytest.mark.anyio
async def test_replace_cases_validates_and_replaces_inside_transaction():
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4())
    case = EvaluationCaseInput(query="q")
    events = []

    @asynccontextmanager
    async def transaction():
        events.append("begin")
        yield
        events.append("commit")

    delete = AsyncMock(side_effect=lambda: events.append("delete"))
    query = MagicMock(delete=delete)
    validate = AsyncMock(side_effect=lambda *_: events.append("validate"))
    bulk_create = AsyncMock(side_effect=lambda *_: events.append("create"))
    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(store, "validate_case_labels", validate),
        patch.object(store.EvaluationCase, "filter", return_value=query),
        patch.object(store.EvaluationCase, "bulk_create", bulk_create),
    ):
        await store.replace_cases(dataset, [case])

    assert events == ["begin", "validate", "delete", "create", "commit"]


@pytest.mark.anyio
async def test_update_case_keeps_case_id_while_replace_cases_rebuilds_it():
    """Regression: editing one case must not reset case ids, because historical
    ``EvaluationCaseResult.case_id`` links are nulled when rows are recreated."""
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4())
    case_id = uuid4()
    row = SimpleNamespace(
        id=case_id,
        query="whats our refund policy",
        chunk_relevance={},
        document_relevance={},
        expected_empty=False,
        save=AsyncMock(),
    )
    edit = EvaluationCaseInput(query="What is our refund policy?")

    @asynccontextmanager
    async def transaction():
        yield

    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(store, "validate_case_labels", AsyncMock()),
    ):
        updated = await store.update_case(dataset, row, edit)

    assert updated.id == case_id
    assert updated.query == "What is our refund policy?"
    row.save.assert_awaited_once_with(
        update_fields=[
            "query",
            "chunk_relevance",
            "document_relevance",
            "expected_empty",
        ]
    )

    delete = AsyncMock()
    bulk_create = AsyncMock()
    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(store, "validate_case_labels", AsyncMock()),
        patch.object(
            store.EvaluationCase, "filter", return_value=MagicMock(delete=delete)
        ),
        patch.object(store.EvaluationCase, "bulk_create", bulk_create),
    ):
        await store.replace_cases(dataset, [edit])

    delete.assert_awaited_once()
    rebuilt = bulk_create.await_args.args[0]
    assert [item.id for item in rebuilt] != [case_id]


@pytest.mark.anyio
async def test_create_run_marks_dispatch_failure_finished_without_raw_error():
    run = SimpleNamespace(
        id=uuid4(),
        status="pending",
        error_message=None,
        finished_at=None,
        save=AsyncMock(),
    )
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4())
    user = SimpleNamespace(id=uuid4())
    kb = SimpleNamespace(
        embedding_model_id=None, rerank_model_id=None, embedding_dimension=None
    )

    @asynccontextmanager
    async def transaction():
        yield

    with (
        patch.object(store.KnowledgeBase, "get", AsyncMock(return_value=kb)),
        patch.object(store.EvaluationRun, "create", AsyncMock(return_value=run)),
        patch.object(store, "in_transaction", transaction),
        patch(
            "app.tasks.retrieval_evaluation.execute_evaluation_run_task.delay",
            side_effect=RuntimeError("broker secret"),
        ),
    ):
        with pytest.raises(BusinessError) as error:
            await store.create_run(dataset, user, EvaluationRunCreate())

    assert error.value.msg_key == "evaluation_dispatch_failed"
    assert run.status == "failed"
    assert run.error_message == "evaluation_dispatch_failed"
    assert isinstance(run.finished_at, datetime)
    assert "broker secret" not in run.error_message
