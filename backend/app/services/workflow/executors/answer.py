"""
Answer (output) node executor.

Handles final output of workflow execution.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from ..executor import NodeExecutor, NodeExecutorRegistry, ExecutionResult
from ..stream import StreamManager

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from ..context import ExecutionContext

logger = logging.getLogger(__name__)


@NodeExecutorRegistry.register("answer")
class AnswerNodeExecutor(NodeExecutor):
    """
    Answer node executor.

    Collects and formats the final output of the workflow.

    Frontend stores config in `answerConfig`:
        {
            "outputs": [
                {
                    "id": "...",
                    "name": "result",
                    "sourceVariable": "{{llm.response}}",
                    "type": "string"
                }
            ],
            "streaming": {
                "enabled": false,
                "variable": "..."
            }
        }

    Outputs:
        {
            "result": "Value from source variable"
        }
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute answer node."""
        node_id = node.get("id")
        node_data = node.get("data", {})
        
        # Debug: log entire node structure
        logger.info(f"Answer node {node_id}: full node_data = {node_data}")
        
        # Frontend uses answerConfig, fallback to config for compatibility
        answer_config = node_data.get("answerConfig", {})
        legacy_config = node_data.get("config", {})
        
        # Check streaming configuration
        streaming_config = answer_config.get("streaming", {})
        is_streaming = streaming_config.get("enabled", False)
        streaming_variable = streaming_config.get("variable", "")
        
        logger.info(f"Answer node {node_id}: is_streaming={is_streaming}, streaming_variable={streaming_variable}")
        
        outputs = {}

        # Handle new frontend format (answerConfig.outputs)
        output_vars = answer_config.get("outputs", [])
        
        logger.info(f"Answer node {node_id}: node_data keys={list(node_data.keys())}")
        logger.info(f"Answer node {node_id}: answerConfig={answer_config}, output_vars={output_vars}")
        
        if output_vars:
            for output_var in output_vars:
                name = output_var.get("name")
                source_variable = output_var.get("sourceVariable", "")
                
                if name and source_variable:
                    # For streaming answer node, if this is the streaming variable,
                    # pass our node_id so LazyStreamResult streams directly to us
                    should_stream_here = (
                        is_streaming and 
                        streaming_variable and 
                        source_variable == streaming_variable
                    )
                    
                    # Resolve the source variable reference
                    # If should_stream_here, lazy LLM result will stream tokens with our node_id
                    value = await context.resolve_variable_ref(
                        source_variable,
                        stream_to_node_id=node_id if should_stream_here else None
                    )
                    
                    logger.info(f"Answer node {node_id}: resolved '{source_variable}' -> {value}")
                    
                    if value is not None:
                        outputs[name] = value
                    else:
                        # Variable not found - log warning and try to find alternatives
                        logger.warning(f"Answer node {node_id}: variable '{source_variable}' not found")
                else:
                    # sourceVariable is empty, skip this output with warning
                    logger.warning(f"Answer node {node_id}: output '{name}' has no sourceVariable configured")
        
        # If no outputs from configured variables, try to get all upstream outputs automatically
        if not outputs:
            logger.info(f"Answer node {node_id}: no outputs resolved, collecting upstream outputs")
            # Get all node outputs from context
            all_node_outputs = await context.get_all_node_outputs()
            for out_node_id, node_outputs in all_node_outputs.items():
                if out_node_id != node_id and isinstance(node_outputs, dict):
                    for var_name, value in node_outputs.items():
                        if value is not None:
                            # Use node_id.var_name as key to avoid conflicts
                            key = f"{out_node_id}.{var_name}" if len(all_node_outputs) > 1 else var_name
                            outputs[key] = value
            logger.info(f"Answer node {node_id}: collected upstream outputs: {list(outputs.keys())}")
        
        # Handle legacy format (config.variables) for backward compatibility
        elif legacy_config and not output_vars:
            answer_template = legacy_config.get("answerTemplate", "")
            variables = legacy_config.get("variables", [])
            
            # Resolve answer template
            if answer_template:
                answer = await self._resolve_template(answer_template, context)
                outputs["answer"] = answer

            # Resolve output variables
            resolved_inputs = await self.resolve_inputs(context, variables)
            outputs.update(resolved_inputs)

            # If no explicit answer but has resolved inputs, use first one
            if "answer" not in outputs and resolved_inputs:
                first_key = next(iter(resolved_inputs))
                outputs["answer"] = resolved_inputs[first_key]

        return ExecutionResult(outputs=outputs)

    async def _resolve_template(
        self,
        template: str,
        context: "ExecutionContext",
    ) -> str:
        """
        Resolve variable references in template.

        Handles {{node.variable}} patterns.
        """
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
        # Handle new format
        outputs = config.get("outputs", [])
        if outputs:
            return [
                {"name": out.get("name"), "type": out.get("type", "any")}
                for out in outputs
                if out.get("name")
            ]
        
        # Handle legacy format
        variables = config.get("variables", [])
        result = [{"name": "answer", "type": "string"}]
        result.extend([
            {"name": var.get("name"), "type": "any"}
            for var in variables
            if var.get("name")
        ])
        return result
