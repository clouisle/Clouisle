"""
Decision model types (non-generative typed decisions).

A decision model evaluates a single `state` against a map of typed questions and
returns one typed answer per question, each carrying its probability distribution.
Nothing is generated, so answers are structured by construction.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from .base import Usage

DecisionQuestionType = Literal["choice", "score", "noul"]


class DecisionQuestion(BaseModel):
    """One typed question asked about the state"""

    type: DecisionQuestionType = Field(..., description="Question type")
    instructions: str | dict[str, Any] | list[Any] = Field(
        ..., description="The question to evaluate against the state"
    )
    criteria: dict[str, Any] | list[Any] | None = Field(
        default=None,
        description=(
            "Answers the question may take: options for 'choice', ordered levels "
            "for 'score', optional true/false descriptions for 'noul'"
        ),
    )


class DecisionRequest(BaseModel):
    """Decision evaluation request"""

    state: str | dict[str, Any] | list[Any] = Field(
        ..., description="Content to evaluate"
    )
    questions: dict[str, DecisionQuestion] = Field(
        ..., description="Questions keyed by the id used to read the answer back"
    )
    model: str | None = Field(
        default=None, description="Override the model configured on the provider"
    )


class DecisionAnswer(BaseModel):
    """One typed answer"""

    type: DecisionQuestionType = Field(..., description="Question type")

    # choice
    choice: str | None = Field(default=None, description="Highest-probability option")
    probabilities: dict[str, float] | None = Field(
        default=None, description="Probability per option or level"
    )
    confidence: float | None = Field(
        default=None, description="Certainty derived from the distribution"
    )

    # score
    score: float | None = Field(
        default=None, description="Probability-weighted position across the levels"
    )
    legend: dict[str, str] | None = Field(
        default=None, description="Level number mapped back to its description"
    )

    # noul
    noul: float | None = Field(
        default=None, description="Probability the answer is yes"
    )


class DecisionResponse(BaseModel):
    """Decision evaluation response"""

    model: str = Field(..., description="Model that produced the answers")
    answers: dict[str, DecisionAnswer] = Field(
        default_factory=dict, description="Answers keyed by question id"
    )
    usage: Usage = Field(default_factory=Usage, description="使用统计")
