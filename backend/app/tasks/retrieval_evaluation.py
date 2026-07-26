"""Celery execution for persistent retrieval evaluation runs."""

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from uuid import UUID

from celery import shared_task

from app.models.knowledge_base import KnowledgeBase
from app.models.retrieval_evaluation import (
    EvaluationCaseResult,
    EvaluationRun,
    EvaluationRunStatus,
)
from app.services.retrieval import RetrievalRequest, RetrievalTarget, retrieve
from app.services.retrieval_evaluation import EvaluationCase as MetricCase
from app.services.retrieval_evaluation import (
    evaluate_case,
    expected_empty_accuracy,
    latency_percentiles,
    ranking_means,
)


def _candidate(result: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "chunk_id": str(result.get("chunk_id")) if result.get("chunk_id") else None,
            "document_id": str(result.get("document_id"))
            if result.get("document_id")
            else None,
            "rank": rank,
            "score": result.get("score"),
            "dense_rank": result.get("dense_rank"),
            "dense_score": result.get("dense_score"),
            "lexical_rank": result.get("lexical_rank"),
            "lexical_score": result.get("lexical_score"),
            "fusion_rank": result.get("fusion_rank"),
            "fusion_score": result.get("fusion_score"),
            "rerank_rank": result.get("rerank_rank"),
            "rerank_score": result.get("rerank_score"),
        }.items()
        if value is not None
    }


async def execute_evaluation_run(run_id: UUID) -> dict[str, Any]:
    """Execute a single evaluation run.

    Idempotent: safe to call multiple times. Returns early if already terminal.
    Checks for cancellation before starting and periodically during execution.

    Args:
        run_id: UUID of the evaluation run to execute.

    Returns:
        Status dict with status, run_id, and optional summary_metrics.
    """
    run = await EvaluationRun.filter(id=run_id).prefetch_related("dataset").first()
    if not run:
        return {"status": "missing", "run_id": str(run_id)}

    # Terminal state protection: don't re-execute completed/failed/canceled runs
    if run.status in (
        EvaluationRunStatus.COMPLETED.value,
        EvaluationRunStatus.FAILED.value,
        EvaluationRunStatus.CANCELED.value,
    ):
        return {
            "status": run.status,
            "run_id": str(run_id),
            "summary_metrics": run.summary_metrics,
        }

    # Idempotent transition to RUNNING
    if run.status == EvaluationRunStatus.PENDING.value:
        run.status = EvaluationRunStatus.RUNNING.value
        run.started_at = datetime.now(timezone.utc)
        await run.save(update_fields=["status", "started_at"])
    elif run.status == EvaluationRunStatus.RUNNING.value:
        # Already running (redelivery or recovery) - continue from where we left off
        pass
    else:
        # Unknown status
        return {"status": run.status, "run_id": str(run_id)}
    config = run.config_snapshot
    dataset = run.dataset
    try:
        kb = await KnowledgeBase.get(id=dataset.knowledge_base_id)
        cases = await dataset.cases.all().order_by("created_at", "id")
    except Exception as exc:
        run.status = EvaluationRunStatus.FAILED.value
        run.error_message = type(exc).__name__
        run.finished_at = datetime.now(timezone.utc)
        await run.save(update_fields=["status", "error_message", "finished_at"])
        return {"status": "failed", "run_id": str(run.id)}
    evaluations = []
    latencies: list[float] = []

    try:
        for case in cases:
            await run.refresh_from_db(fields=["status"])
            if run.status == EvaluationRunStatus.CANCELED.value:
                return {"status": "canceled", "run_id": str(run.id)}
            started = perf_counter()
            error = None
            candidates: list[dict[str, Any]] = []
            try:
                response = await retrieve(
                    RetrievalRequest(
                        query=case.query,
                        targets=(
                            RetrievalTarget(
                                kb_id=kb.id,
                                kb_name=kb.name,
                                team_id=UUID(str(kb.team_id)),
                                status=kb.status,
                                embedding_model_id=kb.embedding_model_id,
                                rerank_model_id=kb.rerank_model_id,
                                embedding_dimension=kb.embedding_dimension,
                            ),
                        ),
                        search_mode=config["search_mode"],
                        top_k=config["top_k"],
                        score_threshold=config["score_threshold"],
                        dense_weight=config["dense_weight"],
                        lexical_weight=config["lexical_weight"],
                        rrf_k=config["rrf_k"],
                        rerank_overrides={
                            "rerank_enabled": config["rerank_enabled"],
                            "rerank_candidate_k": config["rerank_candidate_k"],
                            "rerank_score_threshold": config["rerank_score_threshold"],
                        },
                    )
                )
                candidates = [
                    _candidate(result, rank)
                    for rank, result in enumerate(response.results, 1)
                ]
            except Exception as exc:
                error = type(exc).__name__
            latency_ms = (perf_counter() - started) * 1000
            evaluation = evaluate_case(
                MetricCase(
                    case_id=str(case.id),
                    query=case.query,
                    chunk_relevance=case.chunk_relevance,
                    document_relevance=case.document_relevance,
                    expected_empty=case.expected_empty,
                ),
                [
                    candidate["chunk_id"]
                    for candidate in candidates
                    if candidate.get("chunk_id")
                ],
                [
                    candidate["document_id"]
                    for candidate in candidates
                    if candidate.get("document_id")
                ],
                config["top_k"],
            )
            evaluations.append(evaluation)
            latencies.append(latency_ms)
            await EvaluationCaseResult.update_or_create(
                run_id=run.id,
                case_id=case.id,
                defaults={
                    "case_snapshot": {
                        "id": str(case.id),
                        "query": case.query,
                        "chunk_relevance": case.chunk_relevance,
                        "document_relevance": case.document_relevance,
                        "expected_empty": case.expected_empty,
                    },
                    "candidates": candidates,
                    "metrics": {
                        "chunk": asdict(evaluation.chunk),
                        "document": asdict(evaluation.document),
                        "expected_empty_correct": evaluation.expected_empty_correct,
                    },
                    "latency_ms": latency_ms,
                    "error_message": error,
                },
            )

        # Cases without positive labels carry no ranking signal, so averaging them in
        # would let expected-empty or single-family cases drag the means to zero.
        graded_chunks = [item.chunk for item in evaluations if item.chunk_graded]
        graded_documents = [
            item.document for item in evaluations if item.document_graded
        ]
        summary = {
            "case_count": len(evaluations),
            "error_count": await EvaluationCaseResult.filter(
                run_id=run.id, error_message__not_isnull=True
            ).count(),
            "graded_chunk_case_count": len(graded_chunks),
            "graded_document_case_count": len(graded_documents),
            "expected_empty_count": sum(
                item.expected_empty_correct is not None for item in evaluations
            ),
            "chunk": ranking_means(graded_chunks),
            "document": ranking_means(graded_documents),
            "expected_empty_accuracy": expected_empty_accuracy(evaluations),
            "latency": latency_percentiles(latencies),
        }
        await run.refresh_from_db(fields=["status"])
        if run.status == EvaluationRunStatus.CANCELED.value:
            return {"status": "canceled", "run_id": str(run.id)}
        run.status = EvaluationRunStatus.COMPLETED.value
        run.summary_metrics = summary
        run.finished_at = datetime.now(timezone.utc)
        await run.save(update_fields=["status", "summary_metrics", "finished_at"])
        return {
            "status": "completed",
            "run_id": str(run.id),
            "summary_metrics": summary,
        }
    except Exception as exc:
        run.status = EvaluationRunStatus.FAILED.value
        run.error_message = type(exc).__name__
        run.finished_at = datetime.now(timezone.utc)
        await run.save(update_fields=["status", "error_message", "finished_at"])
        return {"status": "failed", "run_id": str(run.id)}


@shared_task
def execute_evaluation_run_task(run_id: str) -> dict[str, Any]:
    return asyncio.run(execute_evaluation_run(UUID(run_id)))
