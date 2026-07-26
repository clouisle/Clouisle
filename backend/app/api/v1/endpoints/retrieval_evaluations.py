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
    EvaluationSweep,
    EvaluationSweepStatus,
)
from app.models.user import User
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.schemas.retrieval_evaluation import (
    EvaluationCaseInput,
    EvaluationCaseUpsert,
    EvaluationDatasetCreate,
    EvaluationDatasetUpdate,
    EvaluationRunCreate,
    EvaluationSweepCreate,
    EvaluationSweepResponse,
    RunComparisonResponse,
)
from app.services.retrieval_evaluation_store import (
    MAX_IMPORT_BYTES,
    create_case,
    create_run,
    delete_case,
    parse_cases,
    replace_cases,
    serialize_cases,
    update_case,
    upsert_case,
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
        "query_fingerprint": case.query_fingerprint,
        "chunk_relevance": case.chunk_relevance,
        "document_relevance": case.document_relevance,
        "expected_empty": case.expected_empty,
        "labeling_metadata": case.labeling_metadata,
        "created_at": case.created_at,
        "updated_at": case.updated_at,
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
        "revision": dataset.revision,
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
        "metric_k": run.metric_k,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "sweep_id": run.sweep_id,
        "stage": run.stage,
        "candidate_key": run.candidate_key,
        "label": run.label,
        "dataset_revision": run.dataset_revision,
        "dataset_snapshot_hash": run.dataset_snapshot_hash,
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
    case = await _case(dataset.id, case_id)
    await delete_case(dataset, case)
    return success(msg_key="evaluation_case_deleted")


@router.post(
    "/{kb_id}/evaluation-datasets/{dataset_id}/upsert-case",
    response_model=Response[dict],
)
async def upsert_dataset_case(
    kb_id: UUID,
    dataset_id: UUID,
    data: EvaluationCaseUpsert,
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    """Create or update a case by query fingerprint.

    If expected_revision is provided, validates dataset revision and returns 409
    on mismatch or duplicate query fingerprint. Returns (case, created) where
    created=True for new cases.
    """
    dataset = await _dataset(kb_id, dataset_id, current_user)
    case_input = EvaluationCaseInput(
        query=data.query,
        chunk_relevance=data.chunk_relevance,
        document_relevance=data.document_relevance,
        expected_empty=data.expected_empty,
    )
    case, created = await upsert_case(dataset, case_input, data.expected_revision)
    # Update labeling_metadata after upsert
    if data.labeling_metadata:
        case.labeling_metadata = data.labeling_metadata
        await case.save(update_fields=["labeling_metadata"])

    return success(
        data={**_case_data(case), "created": created},
        msg_key="evaluation_case_created" if created else "evaluation_case_updated",
    )


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
    kb_id: UUID,
    dataset_id: UUID,
    sweep_id: UUID | None = None,
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    """List evaluation runs for a dataset, optionally filtered by sweep."""
    dataset = await _dataset(kb_id, dataset_id, current_user)
    query = EvaluationRun.filter(dataset_id=dataset.id)
    if sweep_id is not None:
        query = query.filter(sweep_id=sweep_id)
    runs = await query.order_by("-created_at")
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


@router.post(
    "/{kb_id}/evaluation-datasets/{dataset_id}/compare-runs",
    response_model=Response[RunComparisonResponse],
)
async def compare_runs(
    kb_id: UUID,
    dataset_id: UUID,
    baseline_run_id: UUID,
    candidate_run_id: UUID,
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    """Compare two evaluation runs from the same dataset.

    Returns metric deltas, per-case outcomes, and config diff.
    Comparability checks ensure dataset revision/hash and metric_k match.
    """
    dataset = await _dataset(kb_id, dataset_id, current_user)

    # Fetch both runs with case results
    baseline_run = await EvaluationRun.filter(
        id=baseline_run_id, dataset_id=dataset.id
    ).first()
    candidate_run = await EvaluationRun.filter(
        id=candidate_run_id, dataset_id=dataset.id
    ).first()

    if not baseline_run:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="evaluation_run_not_found",
            status_code=404,
        )
    if not candidate_run:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="evaluation_run_not_found",
            status_code=404,
        )

    # Both must be completed
    if baseline_run.status != EvaluationRunStatus.COMPLETED.value:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="evaluation_run_not_completed",
        )
    if candidate_run.status != EvaluationRunStatus.COMPLETED.value:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="evaluation_run_not_completed",
        )

    # Load case results
    from app.models.retrieval_evaluation import EvaluationCaseResult

    baseline_cases = await EvaluationCaseResult.filter(run_id=baseline_run.id).all()
    candidate_cases = await EvaluationCaseResult.filter(run_id=candidate_run.id).all()

    # Convert to dict format for comparison service
    baseline_dict = {
        "id": baseline_run.id,
        "dataset_id": baseline_run.dataset_id,
        "config_snapshot": baseline_run.config_snapshot,
        "version_snapshot": baseline_run.version_snapshot,
        "summary_metrics": baseline_run.summary_metrics,
        "metric_k": getattr(baseline_run, "metric_k", None),
        "case_results": [
            {
                "id": cr.id,
                "case_id": cr.case_id,
                "case_snapshot": cr.case_snapshot,
                "candidates": cr.candidates,
                "metrics": cr.metrics,
                "latency_ms": cr.latency_ms,
                "error_message": cr.error_message,
            }
            for cr in baseline_cases
        ],
    }

    candidate_dict = {
        "id": candidate_run.id,
        "dataset_id": candidate_run.dataset_id,
        "config_snapshot": candidate_run.config_snapshot,
        "version_snapshot": candidate_run.version_snapshot,
        "summary_metrics": candidate_run.summary_metrics,
        "metric_k": getattr(candidate_run, "metric_k", None),
        "case_results": [
            {
                "id": cr.id,
                "case_id": cr.case_id,
                "case_snapshot": cr.case_snapshot,
                "candidates": cr.candidates,
                "metrics": cr.metrics,
                "latency_ms": cr.latency_ms,
                "error_message": cr.error_message,
            }
            for cr in candidate_cases
        ],
    }

    # Compare using service
    from app.services.retrieval_evaluation_comparison import (
        compare_runs as compare_runs_service,
    )

    result = compare_runs_service(baseline_dict, candidate_dict)

    response = RunComparisonResponse(
        baseline_id=result.baseline_id,
        candidate_id=result.candidate_id,
        comparable=result.comparable,
        incompatibility_reason=result.incompatibility_reason,
        metric_deltas=result.metric_deltas,
        improved_cases=result.improved_cases,
        unchanged_cases=result.unchanged_cases,
        regressed_cases=result.regressed_cases,
        unpaired_cases=result.unpaired_cases,
        case_deltas=result.case_deltas,
        config_diff=result.config_diff,
    )

    return success(data=response)


# ==================== Sweep APIs ====================


async def _sweep(
    kb_id: UUID, dataset_id: UUID, sweep_id: UUID, user: User
) -> EvaluationSweep:
    """Get sweep and verify access."""
    await check_kb_access(kb_id, user)
    sweep = await EvaluationSweep.filter(
        id=sweep_id,
        dataset_id=dataset_id,
    ).first()
    if not sweep:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="evaluation_sweep_not_found",
            status_code=404,
        )
    # Verify dataset belongs to kb
    dataset = await EvaluationDataset.filter(
        id=dataset_id,
        knowledge_base_id=kb_id,
    ).first()
    if not dataset:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="evaluation_dataset_not_found",
            status_code=404,
        )
    return sweep


def _sweep_data(sweep: EvaluationSweep) -> dict[str, Any]:
    """Convert sweep model to response dict."""
    return {
        "id": sweep.id,
        "dataset_id": sweep.dataset_id,
        "created_by_id": sweep.created_by_id,
        "status": sweep.status,
        "objective": sweep.objective,
        "metric_k": sweep.metric_k,
        "serving_top_k": sweep.serving_top_k,
        "space": sweep.space,
        "guards": sweep.guards,
        "baseline_config": sweep.baseline_config,
        "recommendation": sweep.recommendation,
        "best_run_id": sweep.best_run_id,
        "verification_run_id": sweep.verification_run_id,
        "stage": sweep.stage,
        "progress": sweep.progress,
        "task_id": sweep.task_id,
        "heartbeat_at": sweep.heartbeat_at,
        "applied": sweep.applied,
        "applied_at": sweep.applied_at,
        "applied_by_id": sweep.applied_by_id,
        "applied_diff": sweep.applied_diff,
        "error_message": sweep.error_message,
        "dataset_revision": sweep.dataset_revision,
        "dataset_snapshot_hash": sweep.dataset_snapshot_hash,
        "version_snapshot": sweep.version_snapshot,
        "created_at": sweep.created_at,
        "started_at": sweep.started_at,
        "finished_at": sweep.finished_at,
    }


@router.post(
    "/{kb_id}/evaluation-datasets/{dataset_id}/sweeps",
    response_model=Response[EvaluationSweepResponse],
)
async def create_sweep(
    kb_id: UUID,
    dataset_id: UUID,
    payload: EvaluationSweepCreate,
    request: Request,
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    """Create a new parameter sweep for a dataset.

    Validates dataset exists, loads baseline config, and queues the sweep task.
    """
    dataset = await _dataset(kb_id, dataset_id, current_user)

    # Load baseline config from payload or use defaults
    if payload.baseline_config:
        baseline_config = payload.baseline_config
    else:
        # Use default baseline config
        baseline_config = {
            "search_mode": "hybrid",
            "top_k": payload.serving_top_k,
            "score_threshold": 0,
            "dense_weight": 1.0,
            "lexical_weight": 1.0,
            "rrf_k": 60,
            "rerank_enabled": False,
            "rerank_candidate_k": 20,
            "rerank_score_threshold": None,
        }

    # Snapshot dataset
    cases = await EvaluationCase.filter(dataset_id=dataset_id).order_by(
        "created_at", "id"
    )
    from app.tasks.retrieval_tuning import dataset_snapshot_hash

    case_data = [
        {
            "id": str(case.id),
            "query": case.query,
            "chunk_relevance": case.chunk_relevance,
            "document_relevance": case.document_relevance,
            "expected_empty": case.expected_empty,
        }
        for case in cases
    ]
    snapshot_hash = dataset_snapshot_hash(case_data)

    # Load KB for version snapshot
    from app.models.knowledge_base import KnowledgeBase

    kb = await KnowledgeBase.get(id=kb_id)

    # Create sweep
    sweep = await EvaluationSweep.create(
        dataset_id=dataset_id,
        created_by_id=current_user.id,
        status=EvaluationSweepStatus.PENDING.value,
        objective=payload.objective,
        metric_k=payload.metric_k,
        serving_top_k=payload.serving_top_k,
        space=payload.space,
        guards=payload.guards,
        baseline_config=baseline_config,
        dataset_revision=dataset.revision,
        dataset_snapshot_hash=snapshot_hash,
        version_snapshot={
            "embedding_model_id": kb.embedding_model_id,
            "rerank_model_id": kb.rerank_model_id,
        },
    )

    # Queue sweep task
    from app.tasks.retrieval_tuning import orchestrate_sweep

    orchestrate_sweep.delay(str(sweep.id))

    return success(data=EvaluationSweepResponse(**_sweep_data(sweep)))


@router.get(
    "/{kb_id}/evaluation-datasets/{dataset_id}/sweeps/{sweep_id}",
    response_model=Response[EvaluationSweepResponse],
)
async def get_sweep(
    kb_id: UUID,
    dataset_id: UUID,
    sweep_id: UUID,
    request: Request,
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    """Get sweep status and progress."""
    sweep = await _sweep(kb_id, dataset_id, sweep_id, current_user)
    return success(data=EvaluationSweepResponse(**_sweep_data(sweep)))


@router.post(
    "/{kb_id}/evaluation-datasets/{dataset_id}/sweeps/{sweep_id}/cancel",
    response_model=Response[dict],
)
async def cancel_sweep_endpoint(
    kb_id: UUID,
    dataset_id: UUID,
    sweep_id: UUID,
    request: Request,
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    """Cancel a running sweep."""
    sweep = await _sweep(kb_id, dataset_id, sweep_id, current_user)

    # Only cancel if not already terminal
    if sweep.status in (
        EvaluationSweepStatus.COMPLETED.value,
        EvaluationSweepStatus.FAILED.value,
        EvaluationSweepStatus.CANCELED.value,
    ):
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="evaluation_sweep_already_terminal",
        )

    from app.tasks.retrieval_tuning import cancel_sweep

    result = await cancel_sweep(str(sweep_id))
    return success(data=result)


@router.post(
    "/{kb_id}/evaluation-datasets/{dataset_id}/sweeps/{sweep_id}/apply",
    response_model=Response[dict],
)
async def apply_sweep_recommendation(
    kb_id: UUID,
    dataset_id: UUID,
    sweep_id: UUID,
    request: Request,
    current_user: User = Depends(require_kb_evaluate),
) -> Any:
    """Mark sweep recommendation as applied.

    Records that the recommendation was applied by the user.
    Actual KB config changes should be done by the user through KB settings UI.
    """
    sweep = await _sweep(kb_id, dataset_id, sweep_id, current_user)

    # Verify sweep is completed with recommendation
    if sweep.status != EvaluationSweepStatus.COMPLETED.value:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="evaluation_sweep_not_completed",
        )

    if not sweep.recommendation:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="evaluation_sweep_no_recommendation",
        )

    if sweep.applied:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="evaluation_sweep_already_applied",
        )

    # Mark sweep as applied (user acknowledges they applied the recommendation)
    sweep.applied = True
    sweep.applied_at = datetime.now(timezone.utc)
    sweep.applied_by_id = current_user.id
    sweep.applied_diff = {
        "baseline": sweep.baseline_config,
        "recommended": sweep.recommendation["config"],
    }
    await sweep.save()

    return success(
        data={
            "applied": True,
            "recommendation": sweep.recommendation,
            "baseline_config": sweep.baseline_config,
        }
    )
