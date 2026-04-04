"""
Start node executors (user_input, trigger).

These are the entry points for workflow execution.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from ..executor import NodeExecutor, NodeExecutorRegistry, ExecutionResult

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from ..context import ExecutionContext


@NodeExecutorRegistry.register("user_input")
class UserInputNodeExecutor(NodeExecutor):
    """
    User input node executor.

    This node defines the input schema for a workflow.
    At execution time, it simply passes through the input values
    that were provided when the workflow was triggered.

    Node Config:
        {
            "variables": [
                {
                    "name": "query",
                    "type": "string",
                    "required": true,
                    "default": "",
                    "description": "User query"
                }
            ]
        }

    Outputs:
        All defined variables with their input values
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """
        Execute user input node.

        Simply extracts the configured variables from the workflow inputs.
        """
        node_data = node.get("data", {})
        config = node_data.get("config", {})

        # 前端存储为 "parameters"，后端兼容 "variables"
        variables = config.get("variables", [])
        if not variables:
            variables = node_data.get("parameters", [])

        outputs = {}

        for var in variables:
            var_name = var.get("name")
            if not var_name:
                continue

            var_type = var.get("type", "string")
            required = var.get("required", False)
            default = var.get("default")

            # Get value from context inputs
            value = await context.get_variable(f"sys.inputs.{var_name}")

            # Use default if no value provided
            if value is None:
                if required:
                    return ExecutionResult(
                        error=f"Required input '{var_name}' not provided"
                    )
                value = default

            # Type coercion
            value = self._coerce_type(value, var_type)

            outputs[var_name] = value

        return ExecutionResult(outputs=outputs)

    def _coerce_type(self, value, var_type: str):
        """Coerce value to the specified type."""
        if value is None:
            return None

        try:
            if var_type == "number":
                return float(value) if "." in str(value) else int(value)
            elif var_type == "boolean":
                if isinstance(value, bool):
                    return value
                return str(value).lower() in ("true", "1", "yes")
            elif var_type == "array":
                if isinstance(value, list):
                    return value
                return [value]
            elif var_type == "object":
                if isinstance(value, dict):
                    return value
                return {"value": value}
            else:  # string
                return str(value)
        except (ValueError, TypeError):
            return value

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables from config."""
        variables = config.get("variables", [])
        return [
            {"name": var.get("name"), "type": var.get("type", "string")}
            for var in variables
            if var.get("name")
        ]


@NodeExecutorRegistry.register("trigger")
class TriggerNodeExecutor(NodeExecutor):
    """
    Trigger node executor.

    Similar to user_input but supports scheduled/webhook triggers.

    Node Config:
        {
            "triggerType": "manual" | "scheduled" | "webhook",
            "variables": [...]
        }

    Outputs:
        All defined variables plus trigger metadata
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute trigger node."""
        node_data = node.get("data", {})
        config = node_data.get("config", {})
        trigger_type = config.get("triggerType", "manual")
        variables = config.get("variables", [])

        outputs = {
            "_trigger_type": trigger_type,
            "_trigger_time": datetime.utcnow().isoformat(),
        }

        # Process variables same as user_input
        for var in variables:
            var_name = var.get("name")
            if not var_name:
                continue

            value = await context.get_variable(f"sys.inputs.{var_name}")
            if value is None:
                value = var.get("default")

            outputs[var_name] = value

        return ExecutionResult(outputs=outputs)

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables from config."""
        variables = config.get("variables", [])
        result = [
            {"name": "_trigger_type", "type": "string"},
            {"name": "_trigger_time", "type": "string"},
        ]
        result.extend(
            [
                {"name": var.get("name"), "type": var.get("type", "string")}
                for var in variables
                if var.get("name")
            ]
        )
        return result
