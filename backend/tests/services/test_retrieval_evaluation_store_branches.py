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
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4(), revision=1, save=AsyncMock())
    delete = AsyncMock()

    @asynccontextmanager
    async def transaction():
        yield

    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(store.EvaluationDataset, "select_for_update", return_value=MagicMock(get=AsyncMock(return_value=dataset))),
        patch.object(store.EvaluationRun, "filter", return_value=MagicMock(exists=AsyncMock(return_value=False))),
        patch.object(store, "validate_case_labels", AsyncMock()),
        patch.object(
            store.EvaluationCase, "filter", return_value=MagicMock(delete=delete)
        ),
        patch.object(store.EvaluationCase, "bulk_create", AsyncMock()) as create,
    ):
        await store.replace_cases(dataset, [])
    delete.assert_awaited_once()
    create.assert_not_awaited()
    assert dataset.revision == 2


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
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4(), revision=2, save=AsyncMock())
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
        patch.object(store.EvaluationDataset, "select_for_update", return_value=MagicMock(get=AsyncMock(return_value=dataset))),
        patch.object(store.EvaluationRun, "filter", return_value=MagicMock(exists=AsyncMock(return_value=False))),
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
    assert dataset.revision == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("case_count", "expected"), [(store.MAX_CASES - 1, True), (store.MAX_CASES, False)]
)
async def test_create_case_enforces_dataset_case_ceiling(case_count, expected):
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4(), revision=5, save=AsyncMock())
    chunk_id = uuid4()
    case = EvaluationCaseInput(query="q", chunk_relevance={chunk_id: 3})
    create = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    validate = AsyncMock()

    @asynccontextmanager
    async def transaction():
        yield

    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(store.EvaluationDataset, "select_for_update", return_value=MagicMock(get=AsyncMock(return_value=dataset))),
        patch.object(store.EvaluationRun, "filter", return_value=MagicMock(exists=AsyncMock(return_value=False))),
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
        assert dataset.revision == 6
    else:
        create.assert_not_awaited()
        validate.assert_not_awaited()
        assert dataset.revision == 5


def test_serialize_cases_rejects_unknown_format():
    with pytest.raises(BusinessError) as error:
        store.serialize_cases([], "xml")
    assert error.value.msg_key == "evaluation_export_format_invalid"


@pytest.mark.anyio
async def test_query_fingerprint_normalization():
    """Test query normalization and fingerprint generation."""
    # Unicode normalization, trim, and whitespace collapse
    assert store.normalize_query("  hello　world  ") == "hello world"
    assert store.normalize_query("café") == "café"
    # Different queries produce different fingerprints
    fp1 = store.compute_query_fingerprint("test query")
    fp2 = store.compute_query_fingerprint("test query ")  # trailing space
    fp3 = store.compute_query_fingerprint("different")
    assert fp1 == fp2  # normalized to same
    assert fp1 != fp3
    assert len(fp1) == 64  # SHA-256 hex


@pytest.mark.anyio
async def test_create_case_increments_revision():
    """Test that create_case increments dataset revision."""
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4(), revision=5, save=AsyncMock())
    case = EvaluationCaseInput(query="test")

    @asynccontextmanager
    async def transaction():
        yield

    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(store.EvaluationDataset, "select_for_update", return_value=MagicMock(get=AsyncMock(return_value=dataset))),
        patch.object(store.EvaluationRun, "filter", return_value=MagicMock(exists=AsyncMock(return_value=False))),
        patch.object(store, "validate_case_labels", AsyncMock()),
        patch.object(store.EvaluationCase, "filter", return_value=MagicMock(count=AsyncMock(return_value=0))),
        patch.object(store.EvaluationCase, "create", AsyncMock(return_value=SimpleNamespace(id=uuid4()))),
    ):
        await store.create_case(dataset, case)

    assert dataset.revision == 6
    dataset.save.assert_awaited_once()


@pytest.mark.anyio
async def test_update_case_increments_revision():
    """Test that update_case increments dataset revision."""
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4(), revision=3, save=AsyncMock())
    existing = SimpleNamespace(id=uuid4(), query="old", save=AsyncMock())
    case = EvaluationCaseInput(query="new")

    @asynccontextmanager
    async def transaction():
        yield

    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(store.EvaluationDataset, "select_for_update", return_value=MagicMock(get=AsyncMock(return_value=dataset))),
        patch.object(store.EvaluationRun, "filter", return_value=MagicMock(exists=AsyncMock(return_value=False))),
        patch.object(store, "validate_case_labels", AsyncMock()),
    ):
        await store.update_case(dataset, existing, case)

    assert dataset.revision == 4
    dataset.save.assert_awaited_once()


@pytest.mark.anyio
async def test_delete_case_increments_revision():
    """Test that delete_case increments dataset revision."""
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4(), revision=2, save=AsyncMock())
    case_to_delete = SimpleNamespace(id=uuid4(), delete=AsyncMock())

    @asynccontextmanager
    async def transaction():
        yield

    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(store.EvaluationDataset, "select_for_update", return_value=MagicMock(get=AsyncMock(return_value=dataset))),
        patch.object(store.EvaluationRun, "filter", return_value=MagicMock(exists=AsyncMock(return_value=False))),
    ):
        await store.delete_case(dataset, case_to_delete)

    assert dataset.revision == 3
    dataset.save.assert_awaited_once()
    case_to_delete.delete.assert_awaited_once()


@pytest.mark.anyio
async def test_replace_cases_increments_revision():
    """Test that replace_cases increments dataset revision."""
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4(), revision=1, save=AsyncMock())

    @asynccontextmanager
    async def transaction():
        yield

    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(store.EvaluationDataset, "select_for_update", return_value=MagicMock(get=AsyncMock(return_value=dataset))),
        patch.object(store.EvaluationRun, "filter", return_value=MagicMock(exists=AsyncMock(return_value=False))),
        patch.object(store, "validate_case_labels", AsyncMock()),
        patch.object(store.EvaluationCase, "filter", return_value=MagicMock(delete=AsyncMock())),
        patch.object(store.EvaluationCase, "bulk_create", AsyncMock()),
    ):
        await store.replace_cases(dataset, [EvaluationCaseInput(query="q1")])

    assert dataset.revision == 2
    dataset.save.assert_awaited_once()


@pytest.mark.anyio
async def test_upsert_case_creates_when_no_match():
    """Test upsert creates a new case when no matching query fingerprint exists."""
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4(), revision=0, save=AsyncMock())
    case = EvaluationCaseInput(query="new query")
    created_case = SimpleNamespace(id=uuid4())

    @asynccontextmanager
    async def transaction():
        yield

    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(store.EvaluationDataset, "select_for_update", return_value=MagicMock(get=AsyncMock(return_value=dataset))),
        patch.object(store.EvaluationRun, "filter", return_value=MagicMock(exists=AsyncMock(return_value=False))),
        patch.object(store, "validate_case_labels", AsyncMock()),
        patch.object(store.EvaluationCase, "filter", return_value=MagicMock(count=AsyncMock(return_value=0), all=AsyncMock(return_value=[]))),
        patch.object(store.EvaluationCase, "create", AsyncMock(return_value=created_case)),
    ):
        result, created = await store.upsert_case(dataset, case, expected_revision=None)

    assert result == created_case
    assert created is True
    assert dataset.revision == 1


@pytest.mark.anyio
async def test_upsert_case_updates_when_unique_match():
    """Test upsert updates existing case when exactly one matching query fingerprint exists."""
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4(), revision=10, save=AsyncMock())
    existing = SimpleNamespace(id=uuid4(), query="old", save=AsyncMock())
    case = EvaluationCaseInput(query="updated query")

    @asynccontextmanager
    async def transaction():
        yield

    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(store.EvaluationDataset, "select_for_update", return_value=MagicMock(get=AsyncMock(return_value=dataset))),
        patch.object(store.EvaluationRun, "filter", return_value=MagicMock(exists=AsyncMock(return_value=False))),
        patch.object(store, "validate_case_labels", AsyncMock()),
        patch.object(store.EvaluationCase, "filter", return_value=MagicMock(all=AsyncMock(return_value=[existing]))),
    ):
        result, created = await store.upsert_case(dataset, case, expected_revision=None)

    assert result == existing
    assert created is False
    assert existing.query == "updated query"
    assert dataset.revision == 11


@pytest.mark.anyio
async def test_upsert_case_rejects_duplicate_query():
    """Test upsert raises 409 when multiple cases have the same query fingerprint."""
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4(), revision=5, save=AsyncMock())
    case = EvaluationCaseInput(query="duplicate")
    existing1 = SimpleNamespace(id=uuid4())
    existing2 = SimpleNamespace(id=uuid4())

    @asynccontextmanager
    async def transaction():
        yield

    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(store.EvaluationDataset, "select_for_update", return_value=MagicMock(get=AsyncMock(return_value=dataset))),
        patch.object(store.EvaluationRun, "filter", return_value=MagicMock(exists=AsyncMock(return_value=False))),
        patch.object(store, "validate_case_labels", AsyncMock()),
        patch.object(store.EvaluationCase, "filter", return_value=MagicMock(all=AsyncMock(return_value=[existing1, existing2]))),
    ):
        with pytest.raises(BusinessError) as error:
            await store.upsert_case(dataset, case, expected_revision=None)

    assert error.value.msg_key == "evaluation_dataset_duplicate_query"
    assert error.value.status_code == 409
    assert dataset.revision == 5  # unchanged


@pytest.mark.anyio
async def test_mutation_rejects_stale_revision():
    """Test mutations reject when expected_revision doesn't match current."""
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4(), revision=10, save=AsyncMock())
    case = EvaluationCaseInput(query="test")

    @asynccontextmanager
    async def transaction():
        yield

    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(store.EvaluationDataset, "select_for_update", return_value=MagicMock(get=AsyncMock(return_value=dataset))),
    ):
        with pytest.raises(BusinessError) as error:
            await store.create_case(dataset, case, expected_revision=9)

    assert error.value.msg_key == "evaluation_dataset_revision_conflict"
    assert error.value.status_code == 409
    assert dataset.revision == 10  # unchanged


@pytest.mark.anyio
async def test_mutation_blocks_when_active_runs_exist():
    """Test mutations block when active runs exist."""
    dataset = SimpleNamespace(id=uuid4(), knowledge_base_id=uuid4(), revision=5, save=AsyncMock())
    case = EvaluationCaseInput(query="test")

    @asynccontextmanager
    async def transaction():
        yield

    with (
        patch.object(store, "in_transaction", transaction),
        patch.object(store.EvaluationDataset, "select_for_update", return_value=MagicMock(get=AsyncMock(return_value=dataset))),
        patch.object(store.EvaluationRun, "filter", return_value=MagicMock(exists=AsyncMock(return_value=True))),
    ):
        with pytest.raises(BusinessError) as error:
            await store.create_case(dataset, case, expected_revision=None)

    assert error.value.msg_key == "evaluation_dataset_has_active_runs"
    assert dataset.revision == 5  # unchanged

