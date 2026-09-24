"""
Decision model types (non-generative typed decisions).

A decision model evaluates a single `state` against a map of typed questions and
returns one typed answer per question, each carrying its probability distribution.
Nothing is generated, so answers are structured by construction.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

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

    @model_validator(mode="after")
    def validate_contract(self) -> "DecisionQuestion":
        if self.type == "choice":
            if not isinstance(self.criteria, dict) or not self.criteria:
                raise ValueError("choice criteria must be a non-empty object")
            if len(self.criteria) > 255:
                raise ValueError("choice criteria cannot exceed 255 options")
            if any(not option.strip() for option in self.criteria):
                raise ValueError("choice option names must be non-empty")
        elif self.type == "score":
            if not isinstance(self.criteria, list) or not 2 <= len(self.criteria) <= 10:
                raise ValueError("score criteria must contain 2 to 10 ordered levels")
        elif self.criteria is not None and (
            not isinstance(self.criteria, dict)
            or any(key not in {"true", "false"} for key in self.criteria)
        ):
            raise ValueError(
                "noul criteria must be an object with true/false descriptions"
            )
        return self


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
        default=None,
        description="Certainty derived from the distribution",
        ge=0,
        le=1,
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
        default=None, description="Probability the answer is yes", ge=0, le=1
    )

    @model_validator(mode="after")
    def validate_contract(self) -> "DecisionAnswer":
        if self.probabilities is not None and any(
            not 0 <= probability <= 1 for probability in self.probabilities.values()
        ):
            raise ValueError("answer probabilities must be between 0 and 1")
        if self.type == "choice" and (
            self.choice is None or self.probabilities is None or self.confidence is None
        ):
            raise ValueError(
                "choice answer requires choice, probabilities, and confidence"
            )
        if self.type == "score" and (
            self.score is None
            or self.probabilities is None
            or self.confidence is None
            or self.legend is None
        ):
            raise ValueError(
                "score answer requires score, probabilities, confidence, and legend"
            )
        if self.type == "noul" and self.noul is None:
            raise ValueError("noul answer requires noul probability")
        return self


class DecisionResponse(BaseModel):
    """Decision evaluation response"""

    model: str = Field(..., description="Model that produced the answers")
    answers: dict[str, DecisionAnswer] = Field(
        default_factory=dict, description="Answers keyed by question id"
    )
    usage: Usage = Field(default_factory=Usage, description="使用统计")
