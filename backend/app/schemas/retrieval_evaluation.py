"""Schemas for persistent retrieval evaluation."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class EvaluationCaseInput(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    chunk_relevance: dict[UUID, int] = Field(default_factory=dict)
    document_relevance: dict[UUID, int] = Field(default_factory=dict)
    expected_empty: bool = False

    @model_validator(mode="after")
    def validate_relevance(self):
        if any(
            grade < 0 or grade > 3
            for grade in (
                *self.chunk_relevance.values(),
                *self.document_relevance.values(),
            )
        ):
            raise ValueError("relevance grades must be between 0 and 3")
        if self.expected_empty and (self.chunk_relevance or self.document_relevance):
            raise ValueError("expected-empty cases cannot contain relevance labels")
        return self


class EvaluationDatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    cases: list[EvaluationCaseInput] = Field(default_factory=list, max_length=1000)


class EvaluationDatasetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    cases: list[EvaluationCaseInput] | None = Field(default=None, max_length=1000)


class EvaluationCaseUpsert(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    chunk_relevance: dict[UUID, int] = Field(default_factory=dict)
    document_relevance: dict[UUID, int] = Field(default_factory=dict)
    expected_empty: bool = False
    labeling_metadata: dict = Field(default_factory=dict)
    expected_revision: int | None = None

    @model_validator(mode="after")
    def validate_relevance(self):
        if any(
            grade < 0 or grade > 3
            for grade in (
                *self.chunk_relevance.values(),
                *self.document_relevance.values(),
            )
        ):
            raise ValueError("relevance grades must be between 0 and 3")
        if self.expected_empty and (self.chunk_relevance or self.document_relevance):
            raise ValueError("expected-empty cases cannot contain relevance labels")
        return self


class EvaluationCaseResponse(EvaluationCaseInput):
    id: UUID

    model_config = {"from_attributes": True}


class EvaluationDatasetResponse(BaseModel):
    id: UUID
    knowledge_base_id: UUID
    name: str
    description: str | None
    created_by_id: UUID | None
    created_at: datetime
    updated_at: datetime
    cases: list[EvaluationCaseResponse] = []

    model_config = {"from_attributes": True}


class EvaluationRunCreate(BaseModel):
    search_mode: Literal["vector", "fulltext", "hybrid"] = "hybrid"
    top_k: int = Field(default=10, ge=1, le=100)
    score_threshold: float = Field(default=0, ge=0, le=1)
    dense_weight: float = Field(default=1, ge=0)
    lexical_weight: float = Field(default=1, ge=0)
    rrf_k: int = Field(default=60, ge=1, le=1000)
    rerank_enabled: bool = False
    rerank_candidate_k: int = Field(default=20, ge=1, le=100)
    rerank_score_threshold: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_weights(self):
        if (
            self.search_mode == "hybrid"
            and self.dense_weight == self.lexical_weight == 0
        ):
            raise ValueError("hybrid retrieval requires a positive weight")
        return self


class EvaluationCaseResultResponse(BaseModel):
    id: UUID
    case_id: UUID
    case_snapshot: dict
    candidates: list[dict]
    metrics: dict
    latency_ms: float
    error_message: str | None

    model_config = {"from_attributes": True}


class EvaluationRunResponse(BaseModel):
    id: UUID
    dataset_id: UUID
    created_by_id: UUID | None
    status: str
    config_snapshot: dict
    version_snapshot: dict
    summary_metrics: dict | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    case_results: list[EvaluationCaseResultResponse] = []

    model_config = {"from_attributes": True}
