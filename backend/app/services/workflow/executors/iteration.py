"""
Iteration and loop node executors.

Handles iterative execution patterns in workflows.
"""

from typing import TYPE_CHECKING, Any
import logging

from ..executor import NodeExecutor, NodeExecutorRegistry, ExecutionResult
from ..stream import StreamManager

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from ..context import ExecutionContext

logger = logging.getLogger(__name__)

# Maximum iterations to prevent infinite loops
MAX_ITERATIONS = 1000


@NodeExecutorRegistry.register("iteration")
class IterationNodeExecutor(NodeExecutor):
    """
    Iteration node executor.

    Iterates over an array and executes downstream nodes for each item.

    Node Config:
        {
            "inputVariable": "{{start.items}}",
            "itemVariable": "item",
            "indexVariable": "index",
            "parallel": false,
            "maxIterations": 100
        }

    Outputs:
        {
            "item": current_item,
            "index": current_index,
            "total": total_items,
            "results": []  # Aggregated results after all iterations
        }

    Note: This node works with the orchestrator to execute downstream
    nodes multiple times. The actual iteration logic is handled by
    the orchestrator based on the `_iteration_state` output.
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute iteration node."""
        node_id = node.get("id")
        node_data = node.get("data", {})
        config = node_data.get("config", {})

        input_var = config.get("inputVariable", "")
        item_var = config.get("itemVariable", "item")
        index_var = config.get("indexVariable", "index")
        max_iterations = min(config.get("maxIterations", 100), MAX_ITERATIONS)

        # Get the array to iterate
        items = await context.resolve_variable_ref(input_var)

        if items is None:
            return ExecutionResult(
                outputs={
                    item_var: None,
                    index_var: 0,
                    "total": 0,
                    "results": [],
                    "_iteration_complete": True,
                }
            )

        if not isinstance(items, (list, tuple)):
            items = [items]

        # Limit iterations
        if len(items) > max_iterations:
            logger.warning(
                f"Iteration limited to {max_iterations} items (original: {len(items)})"
            )
            items = items[:max_iterations]

        # Get current iteration state
        iteration_state = await context.get_variable(f"{node_id}._iteration_state")

        if iteration_state is None:
            # First iteration
            current_index = 0
            results = []
        else:
            current_index = iteration_state.get("index", 0) + 1
            results = iteration_state.get("results", [])

        # Check if iteration is complete
        if current_index >= len(items):
            return ExecutionResult(
                outputs={
                    item_var: None,
                    index_var: current_index,
                    "total": len(items),
                    "results": results,
                    "_iteration_complete": True,
                }
            )

        # Get current item
        current_item = items[current_index]

        # Store iteration state
        await context.set_variable(
            f"{node_id}._iteration_state",
            {
                "index": current_index,
                "total": len(items),
                "results": results,
                "items": items,
            },
        )

        # Publish iteration event
        stream_manager = StreamManager(context.run_id)
        await stream_manager.publish_iteration(
            node_id=node_id,
            iteration=current_index + 1,
            total=len(items),
            is_start=True,
            item=current_item if not isinstance(current_item, (dict, list)) else None,
        )

        return ExecutionResult(
            outputs={
                item_var: current_item,
                index_var: current_index,
                "total": len(items),
                "results": results,
                "_iteration_complete": False,
                "_iteration_index": current_index,
            }
        )

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables."""
        item_var = config.get("itemVariable", "item")
        index_var = config.get("indexVariable", "index")
        return [
            {"name": item_var, "type": "any"},
            {"name": index_var, "type": "number"},
            {"name": "total", "type": "number"},
            {"name": "results", "type": "array"},
        ]


@NodeExecutorRegistry.register("loop")
class LoopNodeExecutor(NodeExecutor):
    """
    Loop node executor.

    Executes downstream nodes while a condition is true.

    Node Config:
        {
            "conditionVariable": "{{process.continue}}",
            "conditionOperator": "equals",
            "conditionValue": "true",
            "maxIterations": 100,
            "counterVariable": "loopCount"
        }

    Outputs:
        {
            "loopCount": current_count,
            "_loop_complete": boolean
        }
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute loop node."""
        node_id = node.get("id")
        node_data = node.get("data", {})
        config = node_data.get("config", {})

        condition_var = config.get("conditionVariable", "")
        condition_op = config.get("conditionOperator", "equals")
        condition_value = config.get("conditionValue", "true")
        max_iterations = min(config.get("maxIterations", 100), MAX_ITERATIONS)
        counter_var = config.get("counterVariable", "loopCount")

        # Get current loop state
        loop_state = await context.get_variable(f"{node_id}._loop_state")

        if loop_state is None:
            current_count = 0
        else:
            current_count = loop_state.get("count", 0) + 1

        # Check max iterations
        if current_count >= max_iterations:
            logger.warning(f"Loop reached max iterations: {max_iterations}")
            return ExecutionResult(
                outputs={
                    counter_var: current_count,
                    "_loop_complete": True,
                    "_loop_reason": "max_iterations",
                }
            )

        # Evaluate condition
        condition_result = await self._evaluate_condition(
            context, condition_var, condition_op, condition_value
        )

        if not condition_result:
            return ExecutionResult(
                outputs={
                    counter_var: current_count,
                    "_loop_complete": True,
                    "_loop_reason": "condition_false",
                }
            )

        # Store loop state
        await context.set_variable(
            f"{node_id}._loop_state",
            {"count": current_count},
        )

        return ExecutionResult(
            outputs={
                counter_var: current_count,
                "_loop_complete": False,
                "_loop_iteration": current_count,
            }
        )

    async def _evaluate_condition(
        self,
        context: "ExecutionContext",
        var_ref: str,
        operator: str,
        compare_value: str,
    ) -> bool:
        """Evaluate loop condition."""
        actual_value = await context.resolve_variable_ref(var_ref)

        # Resolve compare value if it's a reference
        if compare_value.startswith("{{"):
            compare_value = await context.resolve_variable_ref(compare_value)

        try:
            if operator == "equals":
                return str(actual_value) == str(compare_value)
            elif operator == "not_equals":
                return str(actual_value) != str(compare_value)
            elif operator == "greater_than":
                return float(actual_value) > float(compare_value)
            elif operator == "less_than":
                return float(actual_value) < float(compare_value)
            elif operator == "is_true":
                return bool(actual_value)
            elif operator == "is_false":
                return not bool(actual_value)
            elif operator == "is_not_empty":
                return actual_value is not None and actual_value != ""
            else:
                return bool(actual_value)
        except (ValueError, TypeError):
            return False

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables."""
        counter_var = config.get("counterVariable", "loopCount")
        return [
            {"name": counter_var, "type": "number"},
        ]
