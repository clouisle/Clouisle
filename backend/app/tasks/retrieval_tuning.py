"""Celery tasks for retrieval parameter tuning orchestration."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal, cast
from uuid import UUID

from tortoise.transactions import in_transaction

from app.core.celery_app import celery_app
from app.models import EvaluationDataset, EvaluationRun, EvaluationSweep
from app.models.retrieval_evaluation import EvaluationRunStatus, EvaluationSweepStatus
from app.services.retrieval_tuning import (
    ObjectiveMetric,
    expand_space,
    normalize_space,
    score_run,
    select_recommendation,
)
from app.tasks.retrieval_evaluation import execute_evaluation_run


def dataset_snapshot_hash(cases: list[dict]) -> str:
    """Generate stable hash for dataset snapshot."""
    canonical = json.dumps(cases, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


@celery_app.task(bind=True, name="retrieval_tuning.orchestrate_sweep")
async def orchestrate_sweep(self, sweep_id: str) -> dict:
    """Orchestrate parameter sweep with staged coordinate search.

    Returns:
        Summary dict with status, recommendation, best_run_id, error_message.
    """
    sweep_uuid = UUID(sweep_id)

    try:
        async with in_transaction() as conn:
            sweep = await EvaluationSweep.get(id=sweep_uuid)

            # Check if already terminal
            if sweep.status in (
                EvaluationSweepStatus.COMPLETED.value,
                EvaluationSweepStatus.FAILED.value,
                EvaluationSweepStatus.CANCELED.value,
            ):
                return {
                    "status": sweep.status,
                    "recommendation": sweep.recommendation,
                    "best_run_id": str(sweep.best_run_id) if sweep.best_run_id else None,
                    "error_message": sweep.error_message,
                }

            # Mark as running
            sweep.status = EvaluationSweepStatus.RUNNING.value
            sweep.started_at = datetime.now(timezone.utc)
            sweep.heartbeat_at = datetime.now(timezone.utc)
            sweep.task_id = self.request.id
            await sweep.save()

            # Load dataset and freeze snapshot
            dataset = await EvaluationDataset.get(id=sweep.dataset_id).prefetch_related("cases")
            cases = [
                {
                    "id": str(case.id),
                    "query": case.query,
                    "chunk_relevance": case.chunk_relevance,
                    "document_relevance": case.document_relevance,
                    "expected_empty": case.expected_empty,
                }
                for case in dataset.cases
            ]

            snapshot_hash = dataset_snapshot_hash(cases)

            # Verify dataset revision and snapshot haven't drifted
            if sweep.dataset_revision != dataset.revision or sweep.dataset_snapshot_hash != snapshot_hash:
                sweep.status = EvaluationSweepStatus.FAILED.value
                sweep.error_message = "Dataset has changed since sweep was created"
                sweep.finished_at = datetime.now(timezone.utc)
                await sweep.save()
                return {
                    "status": sweep.status,
                    "error_message": sweep.error_message,
                }

        # Expand parameter space
        baseline_config = sweep.baseline_config.copy()
        baseline_config["search_mode"] = baseline_config.get("search_mode", "hybrid")

        space = normalize_space(sweep.space, baseline_config)
        all_candidates = expand_space(space, baseline_config, sweep.metric_k, sweep.serving_top_k)

        # Check budget
        case_count = len(cases)
        run_count = len(all_candidates)
        if run_count > 32:
            async with in_transaction() as conn:
                sweep = await EvaluationSweep.get(id=sweep_uuid)
                sweep.status = EvaluationSweepStatus.FAILED.value
                sweep.error_message = f"Parameter space too large: {run_count} runs exceeds limit of 32"
                sweep.finished_at = datetime.now(timezone.utc)
                await sweep.save()

                return {
                    "status": sweep.status,
                    "error_message": sweep.error_message,
                }

        if case_count * run_count > 5000:
            async with in_transaction() as conn:
                sweep = await EvaluationSweep.get(id=sweep_uuid)
                sweep.status = EvaluationSweepStatus.FAILED.value
                sweep.error_message = f"Total workload {case_count} cases × {run_count} runs = {case_count * run_count} exceeds limit of 5000"
                sweep.finished_at = datetime.now(timezone.utc)
                await sweep.save()

                return {
                    "status": sweep.status,
                    "error_message": sweep.error_message,
                }

        # Execute all child runs serially by stage
        stages: dict[str, list[tuple[str, dict, dict]]] = {}

        for stage_name, candidate_key, label, config in all_candidates:
            # Check if canceled
            async with in_transaction() as conn:
                sweep = await EvaluationSweep.get(id=sweep_uuid)
                if sweep.status == EvaluationSweepStatus.CANCELED.value:
                    return {
                        "status": sweep.status,
                        "error_message": "Sweep was canceled",
                    }

                # Update heartbeat and stage
                sweep.stage = stage_name
                sweep.heartbeat_at = datetime.now(timezone.utc)
                if stage_name not in sweep.progress:
                    sweep.progress[stage_name] = {"total": 0, "completed": 0}
                sweep.progress[stage_name]["total"] += 1
                await sweep.save()

            # Check if child run already exists (idempotent redelivery)
            existing_run = await EvaluationRun.filter(
                sweep_id=sweep_uuid,
                candidate_key=candidate_key,
            ).first()

            if existing_run and existing_run.status == EvaluationRunStatus.COMPLETED.value:
                # Already completed, skip
                async with in_transaction() as conn:
                    sweep = await EvaluationSweep.get(id=sweep_uuid)
                    sweep.progress[stage_name]["completed"] += 1
                    await sweep.save()
                continue

            # Create or reuse child run
            if existing_run:
                run_id = existing_run.id
            else:
                run = await EvaluationRun.create(
                    dataset_id=sweep.dataset_id,
                    created_by_id=sweep.created_by_id,
                    status=EvaluationRunStatus.PENDING.value,
                    config_snapshot=config,
                    version_snapshot=sweep.version_snapshot,
                    sweep_id=sweep_uuid,
                    stage=stage_name,
                    candidate_key=candidate_key,
                    label=label,
                    metric_k=sweep.metric_k,
                    dataset_revision=sweep.dataset_revision,
                    dataset_snapshot_hash=snapshot_hash,
                )
                run_id = run.id

            # Execute child run synchronously
            try:
                await execute_evaluation_run(run_id)
            except Exception as e:
                # Child run failed, mark sweep as failed
                async with in_transaction() as conn:
                    sweep = await EvaluationSweep.get(id=sweep_uuid)
                    sweep.status = EvaluationSweepStatus.FAILED.value
                    sweep.error_message = f"Child run {candidate_key} failed: {str(e)}"
                    sweep.finished_at = datetime.now(timezone.utc)
                    await sweep.save()

                return {
                    "status": sweep.status,
                    "error_message": sweep.error_message,
                }

            # Update progress
            async with in_transaction() as conn:
                sweep = await EvaluationSweep.get(id=sweep_uuid)
                sweep.progress[stage_name]["completed"] += 1
                await sweep.save()

            # Collect stage results for recommendation
            if stage_name not in stages:
                stages[stage_name] = []

            run = await EvaluationRun.get(id=run_id)
            stages[stage_name].append((candidate_key, config, run.summary_metrics or {}))

        # Select recommendation from all completed runs
        all_run_tuples = []
        for stage_runs in stages.values():
            all_run_tuples.extend(stage_runs)

        recommendation = select_recommendation(
            all_run_tuples,
            "baseline",
            cast(ObjectiveMetric, sweep.objective),
            sweep.metric_k,
            sweep.guards,
        )

        # Create verification run if recommendation exists
        verification_run_id = None
        if recommendation:
            # Check if verification run already exists
            existing_verification = await EvaluationRun.filter(
                sweep_id=sweep_uuid,
                candidate_key=f"verification:{recommendation['candidate_key']}",
            ).first()

            if existing_verification and existing_verification.status == EvaluationRunStatus.COMPLETED.value:
                verification_run_id = existing_verification.id
            else:
                # Create verification run
                if existing_verification:
                    verification_run_id = existing_verification.id
                else:
                    verification_run = await EvaluationRun.create(
                        dataset_id=sweep.dataset_id,
                        created_by_id=sweep.created_by_id,
                        status=EvaluationRunStatus.PENDING.value,
                        config_snapshot=recommendation["config"],
                        version_snapshot=sweep.version_snapshot,
                        sweep_id=sweep_uuid,
                        stage="verification",
                        candidate_key=f"verification:{recommendation['candidate_key']}",
                        label="verification",
                        metric_k=sweep.metric_k,
                        dataset_revision=sweep.dataset_revision,
                        dataset_snapshot_hash=snapshot_hash,
                    )
                    verification_run_id = verification_run.id

                # Execute verification run
                try:
                    await execute_evaluation_run(verification_run_id)
                except Exception as e:
                    async with in_transaction() as conn:
                        sweep = await EvaluationSweep.get(id=sweep_uuid)
                        sweep.status = EvaluationSweepStatus.FAILED.value
                        sweep.error_message = f"Verification run failed: {str(e)}"
                        sweep.finished_at = datetime.now(timezone.utc)
                        await sweep.save()

                    return {
                        "status": sweep.status,
                        "error_message": sweep.error_message,
                    }

            # Check verification against guards
            verification_run = await EvaluationRun.get(id=verification_run_id)
            verification_score = score_run(
                verification_run.summary_metrics or {},
                cast(ObjectiveMetric, sweep.objective),
                sweep.metric_k,
            )

            if verification_score < 0:
                recommendation = None  # Verification failed to produce valid score
            else:
                # Check if verification delta is within tolerance
                verification_delta = verification_score - recommendation["baseline_value"]
                if abs(verification_delta - recommendation["delta"]) > 0.02:
                    recommendation = None  # Verification diverged too much

                # Re-check guards on verification run
                guards = sweep.guards
                if verification_run.summary_metrics:
                    error_count = verification_run.summary_metrics.get("error_count", 0)
                    p95_latency = verification_run.summary_metrics.get("latency_p95_ms", 0)

                    if error_count > guards.get("max_error_count", 0):
                        recommendation = None
                    if p95_latency > guards.get("max_p95_latency_ms", 5000):
                        recommendation = None

        # Mark sweep as completed
        async with in_transaction() as conn:
            sweep = await EvaluationSweep.get(id=sweep_uuid)
            sweep.status = EvaluationSweepStatus.COMPLETED.value
            sweep.recommendation = recommendation
            sweep.best_run_id = (
                UUID(recommendation["candidate_key"].split(":", 1)[1])
                if recommendation and ":" in recommendation["candidate_key"]
                else None
            )
            sweep.verification_run_id = verification_run_id
            sweep.finished_at = datetime.now(timezone.utc)
            await sweep.save()

        return {
            "status": sweep.status,
            "recommendation": recommendation,
            "best_run_id": str(sweep.best_run_id) if sweep.best_run_id else None,
            "verification_run_id": str(verification_run_id) if verification_run_id else None,
        }

    except Exception as e:
        # Unexpected error
        async with in_transaction() as conn:
            sweep = await EvaluationSweep.get(id=sweep_uuid)
            if sweep.status not in (
                EvaluationSweepStatus.COMPLETED.value,
                EvaluationSweepStatus.FAILED.value,
                EvaluationSweepStatus.CANCELED.value,
            ):
                sweep.status = EvaluationSweepStatus.FAILED.value
                sweep.error_message = str(e)
                sweep.finished_at = datetime.now(timezone.utc)
                await sweep.save()

        raise
