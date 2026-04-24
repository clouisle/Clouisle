"""
Answer (output) node executor.

Handles final output of workflow execution.
All output variables are resolved, converted to strings, and concatenated.
Streaming is the default: LazyStreamResult triggers real streaming,
other values are pushed as pseudo-stream tokens.
"""

import logging
from typing import TYPE_CHECKING

from ..executor import NodeExecutor, NodeExecutorRegistry, ExecutionResult
from ..types import to_text

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from ..context import ExecutionContext

logger = logging.getLogger(__name__)


def _value_to_str(value: object) -> str:
    """Convert any value to a string for output."""
    return to_text(value)


@NodeExecutorRegistry.register("answer")
class AnswerNodeExecutor(NodeExecutor):
    """
    Answer node executor.

    Resolves source variables, converts to strings, and outputs concatenated text.
    Default streaming: LazyStreamResult streams natively, others push pseudo-stream tokens.
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute answer node."""
        from ..stream import StreamManager

        node_id = str(node.get("id") or "")
        node_data = node.get("data", {})

        answer_config = node_data.get("answerConfig", {})
        legacy_config = node_data.get("config", {})
        output_vars = answer_config.get("outputs", [])

        logger.info(
            f"Answer node {node_id}: {len(output_vars)} output vars configured, "
            f"raw outputs: {output_vars}"
        )

        stream_manager = StreamManager(context.run_id)
        parts: list[str] = []

        if output_vars:
            for idx, output_var in enumerate(output_vars):
                source_variable = output_var.get("sourceVariable", "")
                logger.info(
                    f"Answer node {node_id}: processing output [{idx}] "
                    f"sourceVariable={source_variable!r}"
                )
                if not source_variable:
                    logger.warning(
                        f"Answer node {node_id}: output [{idx}] has empty sourceVariable, skipping"
                    )
                    continue

                # Add separator between outputs
                if parts:
                    await stream_manager.publish_token(node_id, "\n")

                # Check if the source is a LazyStreamResult (LLM streaming)
                is_lazy = await self._is_lazy_variable(source_variable, context)

                if is_lazy:
                    # Resolve with stream_to_node_id — LazyStreamResult will stream tokens
                    value = await context.resolve_variable_ref(
                        source_variable, stream_to_node_id=node_id
                    )
                    text = _value_to_str(value)
                else:
                    # Resolve normally, then push as pseudo-stream token
                    value = await context.resolve_variable_ref(source_variable)
                    text = _value_to_str(value)
                    logger.info(
                        f"Answer node {node_id}: output [{idx}] resolved "
                        f"value={value!r} (type={type(value).__name__}), text={text!r}"
                    )
                    if text:
                        await stream_manager.publish_token(node_id, text)

                if text:
                    parts.append(text)

        # Handle legacy format for backward compatibility
        elif legacy_config:
            answer_template = legacy_config.get("answerTemplate", "")
            variables = legacy_config.get("variables", [])

            if answer_template:
                answer = await self._resolve_template(answer_template, context)
                parts.append(answer)

            resolved_inputs = await self.resolve_inputs(context, variables)
            for v in resolved_inputs.values():
                text = _value_to_str(v)
                if text:
                    parts.append(text)

        answer_text = "\n".join(parts)
        return ExecutionResult(outputs={"answer": answer_text})

    @staticmethod
    async def _is_lazy_variable(
        source_variable: str, context: "ExecutionContext"
    ) -> bool:
        """Check if a source variable reference points to a LazyStreamResult."""
        import re

        from ..lazy_stream import LazyStreamResult

        ref = source_variable.strip()
        match = re.fullmatch(r"\{\{([^}]+)\}\}", ref)
        if not match:
            return False

        var_path = match.group(1).strip()
        parts = var_path.split(".", 1)
        if len(parts) != 2:
            return False

        source, var_name = parts
        if source in ("sys", "conversation"):
            return False

        outputs = await context.get_node_outputs(source)
        if outputs and isinstance(outputs.get(var_name), LazyStreamResult):
            return True

        return False

    async def _resolve_template(
        self,
        template: str,
        context: "ExecutionContext",
    ) -> str:
        """Resolve variable references in template."""
        import re

        pattern = r"\{\{([^}]+)\}\}"
        matches = re.findall(pattern, template)

        result = template
        for match in matches:
            ref = f"{{{{{match}}}}}"
            value = await context.resolve_variable_ref(ref)
            if value is not None:
                result = result.replace(ref, str(value))

        return result

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables from config."""
        return [{"name": "answer", "type": "string"}]
