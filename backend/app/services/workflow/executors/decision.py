"""Decision model workflow node executor."""

from typing import TYPE_CHECKING, Any
import logging

from app.llm import model_manager
from app.llm.types import DecisionQuestion, DecisionRequest
from ..errors import translate_public_workflow_error
from ..executor import ExecutionResult, NodeExecutor, NodeExecutorRegistry
from ..types import NodeOutputDecl, TypeSpec

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from ..context import ExecutionContext

logger = logging.getLogger(__name__)

MIN_CHOICE_OPTIONS = 1
MAX_CHOICE_OPTIONS = 255
MIN_SCORE_LEVELS = 2
MAX_SCORE_LEVELS = 10


@NodeExecutorRegistry.register("decision")
class DecisionNodeExecutor(NodeExecutor):
    """Evaluate a typed question and activate the matching branch."""

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        node_id = str(node.get("id") or "")
        data = node.get("data", {}) or {}
        config = data.get("decisionConfig", {}) or data.get("config", {})
        model_id = config.get("modelId")
        state_template = config.get("stateTemplate") or config.get("inputVariable", "")
        question_id = config.get("questionId", "decision")
        question_type = config.get("questionType", "choice")
        instructions = config.get("instructions", "")
        options = config.get("options", [])
        default_handle = config.get("defaultHandle")
        threshold = config.get("confidenceThreshold")

        if not model_id or not state_template or not instructions:
            return ExecutionResult(error="validation_error")
        if question_type not in ("choice", "score", "noul"):
            return ExecutionResult(error="validation_error")
        if question_type in ("choice", "score"):
            min_options = (
                MIN_CHOICE_OPTIONS if question_type == "choice" else MIN_SCORE_LEVELS
            )
            max_options = (
                MAX_CHOICE_OPTIONS if question_type == "choice" else MAX_SCORE_LEVELS
            )
            if (
                not isinstance(options, list)
                or not min_options <= len(options) <= max_options
            ):
                return ExecutionResult(error="validation_error")
            if any(
                not isinstance(option, str) or not option.strip() for option in options
            ) or len(options) != len(set(options)):
                return ExecutionResult(error="validation_error")

        try:
            state = await context.resolve_template(str(state_template))
            from app.models.workflow import Workflow

            workflow = await Workflow.get_or_none(id=run.workflow_id)
            if workflow is None:
                return ExecutionResult(error="workflow_not_found")

            criteria: dict[str, Any] | list[Any] | None = None
            if question_type == "choice":
                criteria = {option: None for option in options}
            elif question_type == "score":
                criteria = options
            request = DecisionRequest(
                state=state,
                questions={
                    question_id: DecisionQuestion(
                        type=question_type,
                        instructions=instructions,
                        criteria=criteria,
                    )
                },
            )
            response = await model_manager.team_decide(
                str(workflow.team_id), request, model_id=str(model_id)
            )
            answer = response.answers.get(question_id)
            if answer is None:
                return ExecutionResult(error="decision_result_missing")
            if answer.type != question_type:
                return ExecutionResult(error="decision_result_missing")

            if question_type == "choice":
                if answer.choice not in options or set(answer.probabilities) != set(
                    options
                ):
                    return ExecutionResult(error="decision_result_missing")
                selected = answer.choice
                confidence = answer.confidence
            elif question_type == "noul":
                selected = "yes" if answer.noul >= 0.5 else "no"
                confidence = None
            else:
                probabilities = answer.probabilities
                expected_keys = {str(index) for index in range(len(options))}
                if (
                    set(probabilities) != expected_keys
                    or set(answer.legend) != expected_keys
                ):
                    return ExecutionResult(error="decision_result_missing")
                level_key = max(probabilities, key=probabilities.get)
                selected = options[int(level_key)]
                confidence = answer.confidence
            handle = str(selected) if selected is not None else ""
            if (
                threshold is not None
                and confidence is not None
                and confidence < float(threshold)
            ):
                handle = str(default_handle or "default")
            if not handle:
                handle = str(default_handle or "default")

            await context.set_branch(node_id, handle)
            outputs = {
                "answer": selected,
                "selected_handle": handle,
                "usage": response.usage.model_dump(),
            }
            if question_type == "choice":
                outputs.update(
                    choice=answer.choice,
                    confidence=confidence,
                    probabilities=answer.probabilities,
                )
            elif question_type == "score":
                outputs.update(
                    score=answer.score,
                    confidence=confidence,
                    probabilities=answer.probabilities,
                )
            else:
                outputs["noul"] = answer.noul
            return ExecutionResult(outputs=outputs, next_handles=[handle])
        except Exception as exc:
            logger.exception("Decision node %s failed: %s", node_id, exc)
            return ExecutionResult(error=translate_public_workflow_error(exc))

    async def validate_config(self, config: dict) -> list[str]:
        errors: list[str] = []
        if not config.get("modelId"):
            errors.append("modelId is required")
        if not config.get("stateTemplate") and not config.get("inputVariable"):
            errors.append("stateTemplate is required")
        if not config.get("instructions"):
            errors.append("instructions is required")
        question_type = config.get("questionType", "choice")
        options = config.get("options", [])
        if question_type not in ("choice", "score", "noul"):
            errors.append("questionType must be choice, score, or noul")
        elif question_type in ("choice", "score"):
            min_options = (
                MIN_CHOICE_OPTIONS if question_type == "choice" else MIN_SCORE_LEVELS
            )
            max_options = (
                MAX_CHOICE_OPTIONS if question_type == "choice" else MAX_SCORE_LEVELS
            )
            if (
                not isinstance(options, list)
                or not min_options <= len(options) <= max_options
            ):
                errors.append(
                    f"{question_type} must have {min_options} to {max_options} options"
                )
            elif any(
                not isinstance(option, str) or not option.strip() for option in options
            ) or len(options) != len(set(options)):
                errors.append("options or score levels must be unique and non-empty")
        return errors

    def get_output_variables(self, config: dict) -> list[dict]:
        return [
            {"name": output.name, "type": output.type.kind}
            for output in self.get_output_specs(config)
        ]

    def get_output_specs(self, config: dict) -> list[NodeOutputDecl]:
        output_types = [("answer", "string")]
        question_type = config.get("questionType", "choice")
        if question_type == "choice":
            output_types.extend(
                [
                    ("choice", "string"),
                    ("confidence", "number"),
                    ("probabilities", "object"),
                ]
            )
        elif question_type == "score":
            output_types.extend(
                [
                    ("score", "number"),
                    ("confidence", "number"),
                    ("probabilities", "object"),
                ]
            )
        elif question_type == "noul":
            output_types.append(("noul", "number"))
        output_types.extend([("selected_handle", "string"), ("usage", "object")])
        return [
            NodeOutputDecl(name=name, type=TypeSpec(kind=kind))
            for name, kind in output_types
        ]
