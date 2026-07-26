"""Knowledge-base isolated retrieval evaluation APIs."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile

from app.api.v1.endpoints.knowledge_bases import (
    check_kb_access,
    require_kb_permission,
    _require_kb_action,
)
from app.api import deps
from app.models.retrieval_evaluation import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationRun,
    EvaluationRunStatus,
)
from app.models.user import User
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.schemas.retrieval_evaluation import (
    EvaluationCaseInput,
    EvaluationDatasetCreate,
    EvaluationDatasetUpdate,
    EvaluationRunCreate,
)
from app.services.retrieval_evaluation_store import (
    MAX_IMPORT_BYTES,
    create_case,
    create_run,
    parse_cases,
    replace_cases,
    serialize_cases,
    update_case,
)

router = APIRouter()


async def require_kb_evaluate(
    request: Request, current_user: User = Depends(deps.get_current_active_user)
) -> User:
    user = await require_kb_permission(request, current_user)
    _require_kb_action(user, "evaluate")
    return user


async def _dataset(kb_id: UUID, dataset_id: UUID, user: User) -> EvaluationDataset:
    await check_kb_access(kb_id, user)
    dataset = await EvaluationDataset.filter(
        id=dataset_id, knowledge_base_id=kb_id
    ).first()
    if not dataset:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="evaluation_dataset_not_found",
            status_code=404,
        )
    return dataset


async def _ensure_no_active_runs(dataset_id: UUID) -> None:
    if await EvaluationRun.filter(
        dataset_id=dataset_id, status__in=["pending", "running"]
    ).exists():
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="evaluation_dataset_has_active_runs"
        )


async def _case(dataset_id: UUID, case_id: UUID) -> EvaluationCase:
    case = await EvaluationCase.filter(id=case_id, dataset_id=dataset_id).first()
    if not case:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="evaluation_case_not_found",
            status_code=404,
        )
    return case


def _case_data(case: EvaluationCase) -> dict[str, Any]:
    return {
        "id": case.id,
        "query": case.query,
        "chunk_relevance": case.chunk_relevance,
        "document_relevance": case.document_relevance,
        "expected_empty": case.expected_empty,
    }


async def _dataset_data(dataset: EvaluationDataset) -> dict[str, Any]:
    cases = await EvaluationCase.filter(dataset_id=dataset.id).order_by(
        "created_at", "id"
    )
    return {
        "id": dataset.id,
        "knowledge_base_id": dataset.knowledge_base_id,
        "name": dataset.name,
        "description": dataset.description,
        "created_by_id": dataset.created_by_id,
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
        "cases": [_case_data(case) for case in cases],
    }


async def _run_data(run: EvaluationRun) -> dict[str, Any]:
    results = await run.case_results.all().order_by("created_at", "id")
    return {
        "id": run.id,
        "dataset_id": run.dataset_id,
        "created_by_id": run.created_by_id,
        "status": run.status,
        "config_snapshot": run.config_snapshot,
        "version_snapshot": run.version_snapshot,
        "summary_metrics": run.summary_metrics,
        "error_message": run.error_message,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "case_results": [
            {
                "id": result.id,
                "case_id": result.case_id or result.case_snapshot.get("id"),
                "case_snapshot": result.case_snapshot,
                "candidates": result.candidates,
                "metrics": result.metrics,
                "latency_ms": result.latency_ms,
                "error_message": result.error_message,
            }
            for result in results
        ],
    }


@router.get("/{kb_id}/evaluation-datasets", response_model=Response[list[dict]])
async def list_datasets(
    kb_id: UUID, current_user: User = Depends(require_kb_evaluate)
) -> Any:
    await check_kb_access(kb_id, current_user)
    datasets = await EvaluationDataset.filter(knowledge_base_id=kb_id).order_by(
        "-created_at"
    )
    return success(data=[await _dataset_data(dataset) for dataset in datasets])


@router.post("/{kb_id}/evaluation-datasets", response_model=Response[dict])
async def create_dataset(
    kb_id: UUID,
    data: EvaluationDatasetCreate,
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    await check_kb_access(kb_id, current_user)
    if await EvaluationDataset.filter(knowledge_base_id=kb_id, name=data.name).exists():
        raise BusinessError(
            code=ResponseCode.DUPLICATE_NAME, msg_key="evaluation_dataset_name_exists"
        )
    dataset = await EvaluationDataset.create(
        knowledge_base_id=kb_id,
        created_by_id=current_user.id,
        name=data.name,
        description=data.description,
    )
    await replace_cases(dataset, data.cases)
    return success(
        data=await _dataset_data(dataset), msg_key="evaluation_dataset_created"
    )


@router.get("/{kb_id}/evaluation-datasets/{dataset_id}", response_model=Response[dict])
async def get_dataset(
    kb_id: UUID, dataset_id: UUID, current_user: User = Depends(require_kb_evaluate)
) -> Any:
    return success(
        data=await _dataset_data(await _dataset(kb_id, dataset_id, current_user))
    )


@router.put("/{kb_id}/evaluation-datasets/{dataset_id}", response_model=Response[dict])
async def update_dataset(
    kb_id: UUID,
    dataset_id: UUID,
    data: EvaluationDatasetUpdate,
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    dataset = await _dataset(kb_id, dataset_id, current_user)
    if data.name is not None:
        duplicate = (
            await EvaluationDataset.filter(knowledge_base_id=kb_id, name=data.name)
            .exclude(id=dataset.id)
            .exists()
        )
        if duplicate:
            raise BusinessError(
                code=ResponseCode.DUPLICATE_NAME,
                msg_key="evaluation_dataset_name_exists",
            )
        dataset.name = data.name
    if "description" in data.model_fields_set:
        dataset.description = data.description
    await dataset.save()
    if data.cases is not None:
        await _ensure_no_active_runs(dataset.id)
        await replace_cases(dataset, data.cases)
    return success(
        data=await _dataset_data(dataset), msg_key="evaluation_dataset_updated"
    )


@router.delete(
    "/{kb_id}/evaluation-datasets/{dataset_id}", response_model=Response[None]
)
async def delete_dataset(
    kb_id: UUID, dataset_id: UUID, current_user: User = Depends(require_kb_evaluate)
) -> Any:
    dataset = await _dataset(kb_id, dataset_id, current_user)
    await _ensure_no_active_runs(dataset.id)
    await dataset.delete()
    return success(msg_key="evaluation_dataset_deleted")


@router.post(
    "/{kb_id}/evaluation-datasets/{dataset_id}/import", response_model=Response[dict]
)
async def import_dataset(
    kb_id: UUID,
    dataset_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    dataset = await _dataset(kb_id, dataset_id, current_user)
    await _ensure_no_active_runs(dataset.id)
    content = await file.read(MAX_IMPORT_BYTES + 1)
    cases = parse_cases(content, file.filename or "")
    await replace_cases(dataset, cases)
    return success(
        data=await _dataset_data(dataset), msg_key="evaluation_dataset_imported"
    )


@router.get(
    "/{kb_id}/evaluation-datasets/{dataset_id}/export", response_model=Response[dict]
)
async def export_dataset(
    kb_id: UUID,
    dataset_id: UUID,
    format: str = "json",
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    """Export cases in an import-compatible shape; unknown formats are rejected."""
    dataset = await _dataset(kb_id, dataset_id, current_user)
    cases = await EvaluationCase.filter(dataset_id=dataset.id).order_by(
        "created_at", "id"
    )
    return success(data={"format": format, "content": serialize_cases(cases, format)})


@router.post(
    "/{kb_id}/evaluation-datasets/{dataset_id}/cases", response_model=Response[dict]
)
async def create_dataset_case(
    kb_id: UUID,
    dataset_id: UUID,
    data: EvaluationCaseInput,
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    dataset = await _dataset(kb_id, dataset_id, current_user)
    await _ensure_no_active_runs(dataset.id)
    case = await create_case(dataset, data)
    return success(data=_case_data(case), msg_key="evaluation_case_created")


@router.put(
    "/{kb_id}/evaluation-datasets/{dataset_id}/cases/{case_id}",
    response_model=Response[dict],
)
async def update_dataset_case(
    kb_id: UUID,
    dataset_id: UUID,
    case_id: UUID,
    data: EvaluationCaseInput,
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    dataset = await _dataset(kb_id, dataset_id, current_user)
    await _ensure_no_active_runs(dataset.id)
    existing = await _case(dataset.id, case_id)
    case = await update_case(dataset, existing, data)
    return success(data=_case_data(case), msg_key="evaluation_case_updated")


@router.delete(
    "/{kb_id}/evaluation-datasets/{dataset_id}/cases/{case_id}",
    response_model=Response[None],
)
async def delete_dataset_case(
    kb_id: UUID,
    dataset_id: UUID,
    case_id: UUID,
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    dataset = await _dataset(kb_id, dataset_id, current_user)
    await _ensure_no_active_runs(dataset.id)
    case = await _case(dataset.id, case_id)
    await case.delete()
    return success(msg_key="evaluation_case_deleted")


@router.post(
    "/{kb_id}/evaluation-datasets/{dataset_id}/runs", response_model=Response[dict]
)
async def start_run(
    kb_id: UUID,
    dataset_id: UUID,
    config: EvaluationRunCreate,
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    dataset = await _dataset(kb_id, dataset_id, current_user)
    if not await EvaluationCase.filter(dataset_id=dataset.id).exists():
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="evaluation_dataset_empty"
        )
    return success(
        data=await _run_data(await create_run(dataset, current_user, config)),
        msg_key="evaluation_run_created",
    )


@router.get(
    "/{kb_id}/evaluation-datasets/{dataset_id}/runs",
    response_model=Response[list[dict]],
)
async def list_runs(
    kb_id: UUID, dataset_id: UUID, current_user: User = Depends(require_kb_evaluate)
) -> Any:
    dataset = await _dataset(kb_id, dataset_id, current_user)
    runs = await EvaluationRun.filter(dataset_id=dataset.id).order_by("-created_at")
    return success(data=[await _run_data(run) for run in runs])


@router.get(
    "/{kb_id}/evaluation-datasets/{dataset_id}/runs/{run_id}",
    response_model=Response[dict],
)
async def get_run(
    kb_id: UUID,
    dataset_id: UUID,
    run_id: UUID,
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    dataset = await _dataset(kb_id, dataset_id, current_user)
    run = await EvaluationRun.filter(id=run_id, dataset_id=dataset.id).first()
    if not run:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="evaluation_run_not_found",
            status_code=404,
        )
    return success(data=await _run_data(run))


@router.post(
    "/{kb_id}/evaluation-datasets/{dataset_id}/runs/{run_id}/cancel",
    response_model=Response[dict],
)
async def cancel_run(
    kb_id: UUID,
    dataset_id: UUID,
    run_id: UUID,
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    dataset = await _dataset(kb_id, dataset_id, current_user)
    run = await EvaluationRun.filter(id=run_id, dataset_id=dataset.id).first()
    if not run:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="evaluation_run_not_found",
            status_code=404,
        )
    if run.status not in {
        EvaluationRunStatus.PENDING.value,
        EvaluationRunStatus.RUNNING.value,
    }:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="evaluation_run_not_cancelable"
        )
    run.status = EvaluationRunStatus.CANCELED.value
    run.finished_at = datetime.now(timezone.utc)
    await run.save(update_fields=["status", "finished_at"])
    if run.task_id:
        from app.core.celery import celery_app

        celery_app.control.revoke(run.task_id, terminate=False)
    return success(data=await _run_data(run), msg_key="evaluation_run_canceled")
