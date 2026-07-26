from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.response import BusinessError
from app.schemas.retrieval_evaluation import EvaluationCaseInput, EvaluationRunCreate
from app.services import retrieval_evaluation_store as store


class Values:
    def __init__(self, values):
        self.values = values

    async def values_list(self, *_args, **_kwargs):
        return self.values


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["chunk", "document"])
async def test_validate_case_labels_accepts_owned_and_rejects_foreign(kind):
    item_id, kb_id = uuid4(), uuid4()
    case = EvaluationCaseInput(
        query="q",
        chunk_relevance={item_id: 1} if kind == "chunk" else {},
        document_relevance={item_id: 1} if kind == "document" else {},
    )
    model = store.DocumentChunk if kind == "chunk" else store.Document
    with patch.object(model, "filter", return_value=Values([item_id])):
        await store.validate_case_labels(kb_id, [case])
    with patch.object(model, "filter", return_value=Values([])):
        with pytest.raises(BusinessError) as error:
            await store.validate_case_labels(kb_id, [case])
    assert error.value.msg_key == "evaluation_label_outside_kb"


@pytest.mark.anyio
async def test_replace_cases_empty_only_deletes():
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4())
    delete = AsyncMock()

    @asynccontextmanager
    async def transaction():
        yield

    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(store, "validate_case_labels", AsyncMock()),
        patch.object(
            store.EvaluationCase, "filter", return_value=MagicMock(delete=delete)
        ),
        patch.object(store.EvaluationCase, "bulk_create", AsyncMock()) as create,
    ):
        await store.replace_cases(dataset, [])
    delete.assert_awaited_once()
    create.assert_not_awaited()


@pytest.mark.anyio
async def test_create_run_success_snapshots_model_ids_and_task():
    model_id, rerank_id = uuid4(), uuid4()
    kb = SimpleNamespace(
        embedding_model_id=model_id, rerank_model_id=rerank_id, embedding_dimension=1536
    )
    run = SimpleNamespace(id=uuid4(), task_id=None, save=AsyncMock())
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4())

    @asynccontextmanager
    async def transaction():
        yield

    create = AsyncMock(return_value=run)
    with (
        patch.object(store.KnowledgeBase, "get", AsyncMock(return_value=kb)),
        patch.object(store.EvaluationRun, "create", create),
        patch.object(store, "in_transaction", transaction),
        patch(
            "app.tasks.retrieval_evaluation.execute_evaluation_run_task.delay",
            return_value=SimpleNamespace(id="task"),
        ),
    ):
        result = await store.create_run(
            dataset, SimpleNamespace(id=uuid4()), EvaluationRunCreate()
        )
    snapshot = create.await_args.kwargs["version_snapshot"]
    assert result.task_id == "task"
    assert snapshot["embedding_model_id"] == str(model_id)
    assert snapshot["rerank_model_id"] == str(rerank_id)


def test_schema_validation_branches():
    with pytest.raises(ValidationError):
        EvaluationCaseInput(query="q", chunk_relevance={uuid4(): 4})
    with pytest.raises(ValidationError):
        EvaluationRunCreate(search_mode="hybrid", dense_weight=0, lexical_weight=0)


def test_run_config_drops_retired_rerank_fail_open():
    assert "rerank_fail_open" not in EvaluationRunCreate().model_dump()


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["chunk", "document"])
async def test_single_case_writes_reject_labels_outside_kb(kind):
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4())
    item_id = uuid4()
    case = EvaluationCaseInput(
        query="q",
        chunk_relevance={item_id: 3} if kind == "chunk" else {},
        document_relevance={item_id: 3} if kind == "document" else {},
    )
    model = store.DocumentChunk if kind == "chunk" else store.Document
    existing = SimpleNamespace(query="old", save=AsyncMock())
    create = AsyncMock()

    @asynccontextmanager
    async def transaction():
        yield

    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(model, "filter", return_value=Values([])),
        patch.object(
            store.EvaluationCase,
            "filter",
            return_value=MagicMock(count=AsyncMock(return_value=0)),
        ),
        patch.object(store.EvaluationCase, "create", create),
    ):
        with pytest.raises(BusinessError) as created:
            await store.create_case(dataset, case)
        with pytest.raises(BusinessError) as updated:
            await store.update_case(dataset, existing, case)

    assert created.value.msg_key == "evaluation_label_outside_kb"
    assert updated.value.msg_key == "evaluation_label_outside_kb"
    create.assert_not_awaited()
    existing.save.assert_not_awaited()
    assert existing.query == "old"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("case_count", "expected"), [(store.MAX_CASES - 1, True), (store.MAX_CASES, False)]
)
async def test_create_case_enforces_dataset_case_ceiling(case_count, expected):
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4())
    chunk_id = uuid4()
    case = EvaluationCaseInput(query="q", chunk_relevance={chunk_id: 3})
    create = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    validate = AsyncMock()

    @asynccontextmanager
    async def transaction():
        yield

    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(store, "validate_case_labels", validate),
        patch.object(
            store.EvaluationCase,
            "filter",
            return_value=MagicMock(count=AsyncMock(return_value=case_count)),
        ),
        patch.object(store.EvaluationCase, "create", create),
    ):
        if expected:
            await store.create_case(dataset, case)
        else:
            with pytest.raises(BusinessError) as error:
                await store.create_case(dataset, case)
            assert error.value.msg_key == "evaluation_dataset_case_limit"

    if expected:
        assert create.await_args.kwargs["chunk_relevance"] == {str(chunk_id): 3}
    else:
        create.assert_not_awaited()
        validate.assert_not_awaited()


def test_serialize_cases_rejects_unknown_format():
    with pytest.raises(BusinessError) as error:
        store.serialize_cases([], "xml")
    assert error.value.msg_key == "evaluation_export_format_invalid"
