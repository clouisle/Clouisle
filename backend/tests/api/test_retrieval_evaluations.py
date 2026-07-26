import inspect
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.endpoints import retrieval_evaluations as api
from app.core import i18n
from app.schemas.response import BusinessError
from app.schemas.retrieval_evaluation import (
    EvaluationCaseInput,
    EvaluationDatasetCreate,
    EvaluationDatasetUpdate,
    EvaluationRunCreate,
)
from app.services.retrieval_evaluation_store import parse_cases


class _Rows:
    """Mimics ``filter(...).order_by(...)`` resolving to an awaitable queryset."""

    def __init__(self, rows):
        self.rows = rows

    def order_by(self, *_fields):
        return self

    def __await__(self):
        async def resolve():
            return self.rows

        return resolve().__await__()


@pytest.mark.anyio
async def test_evaluate_permission_uses_admin_route_isolation():
    user = SimpleNamespace(is_superuser=False, roles=[])
    request = SimpleNamespace(
        url=SimpleNamespace(path="/api/v1/admin/knowledge-bases/x/evaluation-datasets")
    )
    with pytest.raises(BusinessError) as error:
        await api.require_kb_evaluate(request, user)
    assert error.value.kwargs["permission"] == "admin:knowledge-base:evaluate"


@pytest.mark.anyio
async def test_cancel_run_marks_finished_and_revokes_task():
    now = datetime.now(timezone.utc)
    dataset = SimpleNamespace(id=uuid4())
    run = SimpleNamespace(
        id=uuid4(),
        dataset_id=dataset.id,
        created_by_id=uuid4(),
        status="running",
        config_snapshot={},
        version_snapshot={},
        summary_metrics=None,
        error_message=None,
        metric_k=None,
        created_at=now,
        started_at=now,
        finished_at=None,
        task_id="task-1",
        sweep_id=None,
        stage=None,
        candidate_key=None,
        label=None,
        dataset_revision=None,
        dataset_snapshot_hash=None,
        save=AsyncMock(),
        case_results=MagicMock(),
    )

    class Results:
        def __await__(self):
            async def resolve():
                return []

            return resolve().__await__()

    run.case_results.all.return_value.order_by.return_value = Results()
    query = MagicMock(first=AsyncMock(return_value=run))
    celery = MagicMock()
    with (
        patch.object(api, "_dataset", AsyncMock(return_value=dataset)),
        patch.object(api.EvaluationRun, "filter", return_value=query),
        patch("app.core.celery.celery_app", celery),
    ):
        response = await api.cancel_run(uuid4(), dataset.id, run.id, SimpleNamespace())

    assert response["data"]["status"] == "canceled"
    assert run.finished_at is not None
    celery.control.revoke.assert_called_once_with("task-1", terminate=False)


@pytest.mark.anyio
async def test_dataset_lookup_is_scoped_to_kb():
    query = MagicMock(first=AsyncMock(return_value=None))
    with (
        patch.object(api, "check_kb_access", AsyncMock()),
        patch.object(api.EvaluationDataset, "filter", return_value=query) as filtered,
    ):
        with pytest.raises(BusinessError) as error:
            await api._dataset(uuid4(), uuid4(), SimpleNamespace())
    assert error.value.status_code == 404
    assert "knowledge_base_id" in filtered.call_args.kwargs


@pytest.mark.anyio
@pytest.mark.parametrize("active", [False, True])
async def test_active_run_guard(active):
    query = MagicMock(exists=AsyncMock(return_value=active))
    with patch.object(api.EvaluationRun, "filter", return_value=query):
        if active:
            with pytest.raises(BusinessError) as error:
                await api._ensure_no_active_runs(uuid4())
            assert error.value.msg_key == "evaluation_dataset_has_active_runs"
        else:
            await api._ensure_no_active_runs(uuid4())


@pytest.mark.anyio
async def test_case_update_is_blocked_by_active_run_but_metadata_update_is_allowed():
    dataset = SimpleNamespace(
        id=uuid4(), name="old", description=None, save=AsyncMock()
    )
    user = SimpleNamespace(id=uuid4())
    replace_mock = AsyncMock(
        side_effect=BusinessError(msg_key="evaluation_dataset_has_active_runs")
    )
    with (
        patch.object(api, "_dataset", AsyncMock(return_value=dataset)),
        patch.object(api, "replace_cases", replace_mock) as replace,
        patch.object(api, "_dataset_data", AsyncMock(return_value={})),
    ):
        with pytest.raises(BusinessError):
            await api.update_dataset(
                uuid4(), dataset.id, EvaluationDatasetUpdate(cases=[]), user
            )
        await api.update_dataset(
            uuid4(), dataset.id, EvaluationDatasetUpdate(description="new"), user
        )
    replace.assert_awaited_once_with(dataset, [])
    assert dataset.description == "new"


@pytest.mark.anyio
async def test_case_crud_preserves_case_id_and_returns_case_payloads():
    dataset = SimpleNamespace(id=uuid4())
    case_id = uuid4()
    stored = SimpleNamespace(
        id=case_id,
        query="whats our refund policy",
        query_fingerprint="whats our refund policy",
        chunk_relevance={},
        document_relevance={},
        expected_empty=False,
        labeling_metadata=None,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )
    edit = EvaluationCaseInput(query="What is our refund policy?")
    edited = SimpleNamespace(
        id=case_id,
        query=edit.query,
        query_fingerprint="What is our refund policy?",
        chunk_relevance={},
        document_relevance={},
        expected_empty=False,
        labeling_metadata=None,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )
    with (
        patch.object(api, "_dataset", AsyncMock(return_value=dataset)),
        patch.object(api, "_ensure_no_active_runs", AsyncMock()),
        patch.object(api, "create_case", AsyncMock(return_value=stored)) as create,
        patch.object(api, "_case", AsyncMock(return_value=stored)) as lookup,
        patch.object(api, "update_case", AsyncMock(return_value=edited)) as update,
        patch.object(api, "delete_case", AsyncMock()) as delete,
    ):
        created = await api.create_dataset_case(
            uuid4(), dataset.id, edit, SimpleNamespace()
        )
        updated = await api.update_dataset_case(
            uuid4(), dataset.id, case_id, edit, SimpleNamespace()
        )
        deleted = await api.delete_dataset_case(
            uuid4(), dataset.id, case_id, SimpleNamespace()
        )

    create.assert_awaited_once_with(dataset, edit)
    update.assert_awaited_once_with(dataset, stored, edit)
    delete.assert_awaited_once_with(dataset, stored)
    assert lookup.await_count == 2
    assert all(call.args == (dataset.id, case_id) for call in lookup.await_args_list)
    assert created["data"]["id"] == case_id
    assert updated["data"] == {
        "id": case_id,
        "query": edit.query,
        "query_fingerprint": "What is our refund policy?",
        "chunk_relevance": {},
        "document_relevance": {},
        "expected_empty": False,
        "labeling_metadata": None,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    assert deleted["data"] is None


@pytest.mark.anyio
async def test_case_lookup_is_scoped_to_dataset():
    query = MagicMock(first=AsyncMock(return_value=None))
    with patch.object(api.EvaluationCase, "filter", return_value=query) as filtered:
        with pytest.raises(BusinessError) as error:
            await api._case(uuid4(), uuid4())
    assert error.value.status_code == 404
    assert error.value.msg_key == "evaluation_case_not_found"
    assert "dataset_id" in filtered.call_args.kwargs


@pytest.mark.anyio
async def test_case_mutations_are_blocked_while_a_run_is_active():
    dataset = SimpleNamespace(id=uuid4())
    case = EvaluationCaseInput(query="q")
    error_response = BusinessError(msg_key="evaluation_dataset_has_active_runs")
    create_mock = AsyncMock(side_effect=error_response)
    update_mock = AsyncMock(side_effect=error_response)
    delete_mock = AsyncMock(side_effect=error_response)
    with (
        patch.object(api, "_dataset", AsyncMock(return_value=dataset)),
        patch.object(api, "create_case", create_mock) as create,
        patch.object(api, "update_case", update_mock) as update,
        patch.object(api, "delete_case", delete_mock) as delete,
        patch.object(api, "_case", AsyncMock()) as lookup,
    ):
        calls = (
            lambda: api.create_dataset_case(
                uuid4(), dataset.id, case, SimpleNamespace()
            ),
            lambda: api.update_dataset_case(
                uuid4(), dataset.id, uuid4(), case, SimpleNamespace()
            ),
            lambda: api.delete_dataset_case(
                uuid4(), dataset.id, uuid4(), SimpleNamespace()
            ),
        )
        for call in calls:
            with pytest.raises(BusinessError) as error:
                await call()
            assert error.value.msg_key == "evaluation_dataset_has_active_runs"

    create.assert_awaited_once()
    update.assert_awaited_once()
    delete.assert_awaited_once()
    assert lookup.await_count == 2  # update and delete both lookup first


@pytest.mark.parametrize(
    "payload",
    [
        {"chunk_relevance": {uuid4(): 4}},
        {"document_relevance": {uuid4(): -1}},
        {"chunk_relevance": {uuid4(): 1.5}},
        {"expected_empty": True, "chunk_relevance": {uuid4(): 3}},
    ],
)
def test_single_case_endpoints_reject_invalid_grades_and_expected_empty(payload):
    for endpoint in (api.create_dataset_case, api.update_dataset_case):
        annotation = inspect.signature(endpoint).parameters["data"].annotation
        assert annotation is EvaluationCaseInput
    with pytest.raises(ValidationError):
        EvaluationCaseInput(query="q", **payload)


@pytest.mark.anyio
@pytest.mark.parametrize("export_format", ["json", "csv"])
async def test_export_round_trips_through_the_import_parser(export_format):
    dataset = SimpleNamespace(id=uuid4())
    chunk_id, document_id = uuid4(), uuid4()
    cases = [
        EvaluationCaseInput(
            query='"Quoted", comma\nand a newline',
            chunk_relevance={chunk_id: 3},
            document_relevance={document_id: 2},
        ),
        EvaluationCaseInput(query="退款政策在哪里？", expected_empty=True),
    ]
    rows = [
        SimpleNamespace(
            query=case.query,
            chunk_relevance={
                str(key): value for key, value in case.chunk_relevance.items()
            },
            document_relevance={
                str(key): value for key, value in case.document_relevance.items()
            },
            expected_empty=case.expected_empty,
        )
        for case in cases
    ]
    with (
        patch.object(api, "_dataset", AsyncMock(return_value=dataset)),
        patch.object(api.EvaluationCase, "filter", return_value=_Rows(rows)),
    ):
        response = await api.export_dataset(
            uuid4(), dataset.id, export_format, SimpleNamespace()
        )

    assert response["data"]["format"] == export_format
    reimported = parse_cases(
        response["data"]["content"].encode(), f"cases.{export_format}"
    )
    assert reimported == cases


@pytest.mark.anyio
async def test_export_defaults_to_json_and_rejects_unknown_formats():
    dataset = SimpleNamespace(id=uuid4())
    rows = [
        SimpleNamespace(
            query="q", chunk_relevance={}, document_relevance={}, expected_empty=False
        )
    ]
    assert inspect.signature(api.export_dataset).parameters["format"].default == "json"
    with (
        patch.object(api, "_dataset", AsyncMock(return_value=dataset)),
        patch.object(api.EvaluationCase, "filter", return_value=_Rows(rows)),
    ):
        default = await api.export_dataset(
            uuid4(), dataset.id, current_user=SimpleNamespace()
        )
        with pytest.raises(BusinessError) as error:
            await api.export_dataset(uuid4(), dataset.id, "xml", SimpleNamespace())

    assert default["data"]["format"] == "json"
    assert parse_cases(default["data"]["content"].encode(), "cases.json") == [
        EvaluationCaseInput(query="q")
    ]
    assert error.value.msg_key == "evaluation_export_format_invalid"


@pytest.mark.parametrize("language", ["en", "zh"])
def test_new_case_and_export_messages_are_translated(language):
    for key in (
        "evaluation_case_not_found",
        "evaluation_case_created",
        "evaluation_case_updated",
        "evaluation_case_deleted",
        "evaluation_dataset_case_limit",
        "evaluation_export_format_invalid",
    ):
        assert i18n.t(key, lang=language) != key


@pytest.mark.anyio
async def test_import_is_blocked_before_read_when_run_is_active():
    dataset = SimpleNamespace(id=uuid4())
    file = SimpleNamespace(filename="cases.json", read=AsyncMock(return_value=b"[]"))
    replace_mock = AsyncMock(
        side_effect=BusinessError(msg_key="evaluation_dataset_has_active_runs")
    )
    with (
        patch.object(api, "_dataset", AsyncMock(return_value=dataset)),
        patch.object(api, "parse_cases", return_value=[]),
        patch.object(api, "replace_cases", replace_mock) as replace,
    ):
        with pytest.raises(BusinessError):
            await api.import_dataset(uuid4(), dataset.id, file, SimpleNamespace())
    file.read.assert_awaited_once()
    replace.assert_awaited_once()


@pytest.mark.anyio
async def test_create_dataset_duplicate_and_success_branches():
    kb_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    duplicate = MagicMock(exists=AsyncMock(return_value=True))
    with (
        patch.object(api, "check_kb_access", AsyncMock()),
        patch.object(api.EvaluationDataset, "filter", return_value=duplicate),
    ):
        with pytest.raises(BusinessError) as error:
            await api.create_dataset(
                kb_id, EvaluationDatasetCreate(name="duplicate"), user
            )
    assert error.value.msg_key == "evaluation_dataset_name_exists"

    dataset = SimpleNamespace(id=uuid4())
    unique = MagicMock(exists=AsyncMock(return_value=False))
    with (
        patch.object(api, "check_kb_access", AsyncMock()),
        patch.object(api.EvaluationDataset, "filter", return_value=unique),
        patch.object(api.EvaluationDataset, "create", AsyncMock(return_value=dataset)),
        patch.object(api, "replace_cases", AsyncMock()) as replace,
        patch.object(api, "_dataset_data", AsyncMock(return_value={"id": dataset.id})),
    ):
        response = await api.create_dataset(
            kb_id, EvaluationDatasetCreate(name="new"), user
        )
    replace.assert_awaited_once_with(dataset, [])
    assert response["data"]["id"] == dataset.id


@pytest.mark.anyio
async def test_update_dataset_name_and_cases_branches():
    dataset = SimpleNamespace(
        id=uuid4(), name="old", description=None, save=AsyncMock()
    )
    duplicate = MagicMock()
    duplicate.exclude.return_value.exists = AsyncMock(return_value=True)
    with (
        patch.object(api, "_dataset", AsyncMock(return_value=dataset)),
        patch.object(api.EvaluationDataset, "filter", return_value=duplicate),
    ):
        with pytest.raises(BusinessError) as error:
            await api.update_dataset(
                uuid4(),
                dataset.id,
                EvaluationDatasetUpdate(name="taken"),
                SimpleNamespace(),
            )
    assert error.value.msg_key == "evaluation_dataset_name_exists"

    duplicate.exclude.return_value.exists = AsyncMock(return_value=False)
    with (
        patch.object(api, "_dataset", AsyncMock(return_value=dataset)),
        patch.object(api.EvaluationDataset, "filter", return_value=duplicate),
        patch.object(api, "replace_cases", AsyncMock()) as replace,
        patch.object(api, "_dataset_data", AsyncMock(return_value={})),
    ):
        await api.update_dataset(
            uuid4(),
            dataset.id,
            EvaluationDatasetUpdate(name="new", description=None, cases=[]),
            SimpleNamespace(),
        )
    assert dataset.name == "new"
    assert dataset.description is None
    replace.assert_awaited_once_with(dataset, [])


@pytest.mark.anyio
async def test_delete_and_start_run_guards():
    dataset = SimpleNamespace(id=uuid4(), delete=AsyncMock())
    with (
        patch.object(api, "_dataset", AsyncMock(return_value=dataset)),
        patch.object(
            api,
            "_ensure_no_active_runs",
            AsyncMock(
                side_effect=BusinessError(msg_key="evaluation_dataset_has_active_runs")
            ),
        ),
    ):
        with pytest.raises(BusinessError):
            await api.delete_dataset(uuid4(), dataset.id, SimpleNamespace())
    dataset.delete.assert_not_awaited()

    no_cases = MagicMock(exists=AsyncMock(return_value=False))
    with (
        patch.object(api, "_dataset", AsyncMock(return_value=dataset)),
        patch.object(api.EvaluationCase, "filter", return_value=no_cases),
    ):
        with pytest.raises(BusinessError) as error:
            await api.start_run(
                uuid4(), dataset.id, EvaluationRunCreate(), SimpleNamespace()
            )
    assert error.value.msg_key == "evaluation_dataset_empty"


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", [api.get_run, api.cancel_run])
async def test_run_lookup_not_found(endpoint):
    dataset = SimpleNamespace(id=uuid4())
    query = MagicMock(first=AsyncMock(return_value=None))
    with (
        patch.object(api, "_dataset", AsyncMock(return_value=dataset)),
        patch.object(api.EvaluationRun, "filter", return_value=query),
    ):
        with pytest.raises(BusinessError) as error:
            await endpoint(uuid4(), dataset.id, uuid4(), SimpleNamespace())
    assert error.value.status_code == 404


@pytest.mark.anyio
async def test_cancel_rejects_terminal_run_and_skips_revoke_without_task():
    dataset = SimpleNamespace(id=uuid4())
    terminal = SimpleNamespace(status="completed")
    query = MagicMock(first=AsyncMock(return_value=terminal))
    with (
        patch.object(api, "_dataset", AsyncMock(return_value=dataset)),
        patch.object(api.EvaluationRun, "filter", return_value=query),
    ):
        with pytest.raises(BusinessError) as error:
            await api.cancel_run(uuid4(), dataset.id, uuid4(), SimpleNamespace())
    assert error.value.msg_key == "evaluation_run_not_cancelable"

    run = SimpleNamespace(
        status="pending", task_id=None, finished_at=None, save=AsyncMock()
    )
    query = MagicMock(first=AsyncMock(return_value=run))
    with (
        patch.object(api, "_dataset", AsyncMock(return_value=dataset)),
        patch.object(api.EvaluationRun, "filter", return_value=query),
        patch.object(api, "_run_data", AsyncMock(return_value={})),
    ):
        await api.cancel_run(uuid4(), dataset.id, uuid4(), SimpleNamespace())
    assert run.status == "canceled"
