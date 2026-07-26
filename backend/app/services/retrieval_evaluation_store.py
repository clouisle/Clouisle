"""Persistence helpers and bounded imports for retrieval evaluation."""

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import TypeAdapter, ValidationError
from tortoise.transactions import in_transaction

from app.models.knowledge_base import Document, DocumentChunk, KnowledgeBase
from app.models.retrieval_evaluation import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationRun,
)
from app.models.user import User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.retrieval_evaluation import EvaluationCaseInput, EvaluationRunCreate

MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_CASES = 1000
EXPORT_FORMATS = ("json", "csv")
_CSV_COLUMNS = ("query", "chunk_relevance", "document_relevance", "expected_empty")
_CASE_LIST = TypeAdapter(list[EvaluationCaseInput])


def _bad_import() -> BusinessError:
    return BusinessError(
        code=ResponseCode.VALIDATION_ERROR, msg_key="evaluation_import_invalid"
    )


def parse_cases(content: bytes, filename: str) -> list[EvaluationCaseInput]:
    if not content or len(content) > MAX_IMPORT_BYTES:
        raise _bad_import()
    try:
        text = content.decode("utf-8-sig")
        if filename.lower().endswith(".json"):
            raw = json.loads(text)
            raw = raw.get("cases", raw) if isinstance(raw, dict) else raw
        elif filename.lower().endswith(".csv"):
            raw = []
            for row in csv.DictReader(io.StringIO(text)):
                raw.append(
                    {
                        "query": row.get("query", ""),
                        "chunk_relevance": json.loads(
                            row.get("chunk_relevance") or "{}"
                        ),
                        "document_relevance": json.loads(
                            row.get("document_relevance") or "{}"
                        ),
                        "expected_empty": (row.get("expected_empty") or "").lower()
                        in {"1", "true", "yes"},
                    }
                )
        else:
            raise ValueError
        cases = _CASE_LIST.validate_python(raw)
    except (
        UnicodeDecodeError,
        csv.Error,
        json.JSONDecodeError,
        ValidationError,
        TypeError,
        ValueError,
    ):
        raise _bad_import() from None
    if not cases or len(cases) > MAX_CASES:
        raise _bad_import()
    return cases


def serialize_cases(cases: list[EvaluationCase], export_format: str) -> str:
    """Render cases in the exact shapes ``parse_cases`` accepts, so an export
    can be re-imported without any manual editing."""
    if export_format not in EXPORT_FORMATS:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="evaluation_export_format_invalid",
        )
    payload = [
        {
            "query": case.query,
            "chunk_relevance": case.chunk_relevance or {},
            "document_relevance": case.document_relevance or {},
            "expected_empty": case.expected_empty,
        }
        for case in cases
    ]
    if export_format == "json":
        return json.dumps({"cases": payload}, ensure_ascii=False, indent=2)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(_CSV_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for item in payload:
        writer.writerow(
            {
                "query": item["query"],
                "chunk_relevance": json.dumps(item["chunk_relevance"]),
                "document_relevance": json.dumps(item["document_relevance"]),
                "expected_empty": "true" if item["expected_empty"] else "false",
            }
        )
    return buffer.getvalue()


async def validate_case_labels(kb_id: UUID, cases: list[EvaluationCaseInput]) -> None:
    chunk_ids = {item for case in cases for item in case.chunk_relevance}
    document_ids = {item for case in cases for item in case.document_relevance}
    if chunk_ids:
        found = set(
            await DocumentChunk.filter(
                id__in=chunk_ids, document__knowledge_base_id=kb_id
            ).values_list("id", flat=True)
        )
        if found != chunk_ids:
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="evaluation_label_outside_kb",
            )
    if document_ids:
        found = set(
            await Document.filter(
                id__in=document_ids, knowledge_base_id=kb_id
            ).values_list("id", flat=True)
        )
        if found != document_ids:
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="evaluation_label_outside_kb",
            )


def _case_fields(case: EvaluationCaseInput) -> dict[str, Any]:
    return {
        "query": case.query,
        "chunk_relevance": {
            str(key): value for key, value in case.chunk_relevance.items()
        },
        "document_relevance": {
            str(key): value for key, value in case.document_relevance.items()
        },
        "expected_empty": case.expected_empty,
    }


async def replace_cases(
    dataset: EvaluationDataset, cases: list[EvaluationCaseInput]
) -> None:
    """Destructively swap the whole case set: every existing case row is deleted
    and recreated, so all case ids change and historical
    ``EvaluationCaseResult.case_id`` links are reset to null. Use it only for
    import and full-dataset replacement; use :func:`create_case` /
    :func:`update_case` to edit a dataset without losing per-case history."""
    async with in_transaction():
        await validate_case_labels(dataset.knowledge_base_id, cases)
        await EvaluationCase.filter(dataset_id=dataset.id).delete()
        if cases:
            await EvaluationCase.bulk_create(
                [
                    EvaluationCase(dataset_id=dataset.id, **_case_fields(case))
                    for case in cases
                ]
            )


async def create_case(
    dataset: EvaluationDataset, case: EvaluationCaseInput
) -> EvaluationCase:
    """Append one case, leaving every existing case id untouched."""
    async with in_transaction():
        if await EvaluationCase.filter(dataset_id=dataset.id).count() >= MAX_CASES:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST, msg_key="evaluation_dataset_case_limit"
            )
        await validate_case_labels(dataset.knowledge_base_id, [case])
        return await EvaluationCase.create(dataset_id=dataset.id, **_case_fields(case))


async def update_case(
    dataset: EvaluationDataset, existing: EvaluationCase, case: EvaluationCaseInput
) -> EvaluationCase:
    """Update one case in place so its id -- and the historical case results
    pointing at it -- survive the edit."""
    async with in_transaction():
        await validate_case_labels(dataset.knowledge_base_id, [case])
        fields = _case_fields(case)
        for name, value in fields.items():
            setattr(existing, name, value)
        await existing.save(update_fields=list(fields))
    return existing


async def create_run(
    dataset: EvaluationDataset, user: User, config: EvaluationRunCreate
) -> EvaluationRun:
    kb = await KnowledgeBase.get(id=dataset.knowledge_base_id)
    snapshot = config.model_dump(mode="json")
    version_snapshot: dict[str, Any] = {
        "embedding_model_id": str(kb.embedding_model_id)
        if kb.embedding_model_id
        else None,
        "rerank_model_id": str(kb.rerank_model_id) if kb.rerank_model_id else None,
        "embedding_dimension": kb.embedding_dimension,
        "retrieval_version": "unified-v2",
    }
    async with in_transaction():
        run = await EvaluationRun.create(
            dataset_id=dataset.id,
            created_by_id=user.id,
            config_snapshot=snapshot,
            version_snapshot=version_snapshot,
        )
    try:
        from app.tasks.retrieval_evaluation import execute_evaluation_run_task

        result = execute_evaluation_run_task.delay(str(run.id))
        run.task_id = result.id
        await run.save(update_fields=["task_id"])
    except Exception:
        run.status = "failed"
        run.error_message = "evaluation_dispatch_failed"
        run.finished_at = datetime.now(timezone.utc)
        await run.save(update_fields=["status", "error_message", "finished_at"])
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="evaluation_dispatch_failed",
            status_code=503,
        ) from None
    return run
