from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import retrieval_evaluations as api
from app.schemas.response import BusinessError
from app.schemas.retrieval_evaluation import (
    EvaluationDatasetCreate,
    EvaluationDatasetUpdate,
    EvaluationRunCreate,
)


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
        created_at=now,
        started_at=now,
        finished_at=None,
        task_id="task-1",
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
    with (
        patch.object(api, "_dataset", AsyncMock(return_value=dataset)),
        patch.object(
            api,
            "_ensure_no_active_runs",
            AsyncMock(
                side_effect=BusinessError(msg_key="evaluation_dataset_has_active_runs")
            ),
        ) as guard,
        patch.object(api, "replace_cases", AsyncMock()) as replace,
        patch.object(api, "_dataset_data", AsyncMock(return_value={})),
    ):
        with pytest.raises(BusinessError):
            await api.update_dataset(
                uuid4(), dataset.id, EvaluationDatasetUpdate(cases=[]), user
            )
        await api.update_dataset(
            uuid4(), dataset.id, EvaluationDatasetUpdate(description="new"), user
        )
    guard.assert_awaited_once_with(dataset.id)
    replace.assert_not_awaited()
    assert dataset.description == "new"


@pytest.mark.anyio
async def test_import_is_blocked_before_read_when_run_is_active():
    dataset = SimpleNamespace(id=uuid4())
    file = SimpleNamespace(filename="cases.json", read=AsyncMock())
    with (
        patch.object(api, "_dataset", AsyncMock(return_value=dataset)),
        patch.object(
            api,
            "_ensure_no_active_runs",
            AsyncMock(
                side_effect=BusinessError(msg_key="evaluation_dataset_has_active_runs")
            ),
        ),
        patch.object(api, "replace_cases", AsyncMock()) as replace,
    ):
        with pytest.raises(BusinessError):
            await api.import_dataset(uuid4(), dataset.id, file, SimpleNamespace())
    file.read.assert_not_awaited()
    replace.assert_not_awaited()


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
        patch.object(api, "_ensure_no_active_runs", AsyncMock()) as guard,
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
    guard.assert_awaited_once_with(dataset.id)
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
