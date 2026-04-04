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


@NodeExecutorRegistry.register("iteration_start")
class IterationStartNodeExecutor(NodeExecutor):
    """
    Iteration start node executor.

    This is an internal node inside iteration containers.
    It passes through the iteration variables (item, index, results) from the parent.
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute iteration start node - pass through parent's variables."""
        node_data = node.get("data", {})
        node_id = str(node.get("id") or "")

        # Try multiple ways to get parent ID
        parent_id = (
            node_data.get("parentIterationId")
            or node.get("parentId")
            or node_data.get("parentId")
        )

        logger.info(
            f"IterationStart: node_id={node_id}, node={node}, parent_id={parent_id}"
        )

        if parent_id:
            # Get parent iteration node's outputs
            parent_outputs = await context.get_node_outputs(parent_id)
            logger.info(
                f"IterationStart: parent_id={parent_id}, parent_outputs={parent_outputs}"
            )
            if parent_outputs:
                # Filter out internal fields
                outputs = {
                    k: v for k, v in parent_outputs.items() if not k.startswith("_")
                }
                logger.info(f"IterationStart: filtered outputs={outputs}")
                return ExecutionResult(outputs=outputs)
            else:
                logger.warning(
                    f"IterationStart: parent_outputs is None for parent_id={parent_id}"
                )
        else:
            logger.warning(f"IterationStart: parent_id is None, node_data={node_data}")

        return ExecutionResult(outputs={})


@NodeExecutorRegistry.register("loop_start")
class LoopStartNodeExecutor(NodeExecutor):
    """
    Loop start node executor.

    This is an internal node inside loop containers.
    It passes through the loop variables from the parent.
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute loop start node - pass through parent's variables."""
        node_data = node.get("data", {})
        node_id = str(node.get("id") or "")

        # Try multiple ways to get parent ID
        parent_id = (
            node_data.get("parentLoopId")
            or node.get("parentId")
            or node_data.get("parentId")
        )

        logger.info(f"LoopStart: node_id={node_id}, node={node}, parent_id={parent_id}")

        if parent_id:
            # Get parent loop node's outputs
            parent_outputs = await context.get_node_outputs(parent_id)
            logger.info(
                f"LoopStart: parent_id={parent_id}, parent_outputs={parent_outputs}"
            )
            if parent_outputs:
                # Filter out internal fields
                outputs = {
                    k: v for k, v in parent_outputs.items() if not k.startswith("_")
                }
                logger.info(f"LoopStart: filtered outputs={outputs}")
                return ExecutionResult(outputs=outputs)
            else:
                logger.warning(
                    f"LoopStart: parent_outputs is None for parent_id={parent_id}"
                )
        else:
            logger.warning(f"LoopStart: parent_id is None, node_data={node_data}")

        return ExecutionResult(outputs={})


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
        node_id = str(node.get("id") or "")
        node_data = node.get("data", {})
        # Frontend stores config in iterationConfig, fallback to config for backwards compatibility
        config = node_data.get("iterationConfig") or node_data.get("config", {})

        # Frontend uses iteratorVariable, backend also supports inputVariable for backwards compatibility
        input_var = config.get("iteratorVariable") or config.get("inputVariable", "")
        iterator_type = config.get("iteratorType", "array")  # 'array' or 'object'
        # Array iteration variables
        item_var = config.get("itemVariable", "item")
        index_var = config.get("indexVariable", "index")
        # Object iteration variables
        key_var = config.get("keyVariable", "key")
        value_var = config.get("valueVariable", "value")
        max_iterations = min(config.get("maxIterations", 100), MAX_ITERATIONS)

        # Get the data to iterate
        items = await context.resolve_variable_ref(input_var)

        logger.info(
            f"Iteration node {node_id}: input_var={input_var}, iterator_type={iterator_type}, raw items={items}, type={type(items)}"
        )

        # Handle object iteration
        if iterator_type == "object":
            return await self._execute_object_iteration(
                node_id, items, key_var, value_var, max_iterations, context
            )

        # Array iteration (default)
        return await self._execute_array_iteration(
            node_id, items, item_var, index_var, max_iterations, context
        )

    async def _execute_array_iteration(
        self,
        node_id: str,
        items: Any,
        item_var: str,
        index_var: str,
        max_iterations: int,
        context: "ExecutionContext",
    ) -> ExecutionResult:
        """Execute array iteration."""
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

        # Try to parse JSON string
        if isinstance(items, str):
            import json

            try:
                parsed = json.loads(items)
                if isinstance(parsed, (list, tuple)):
                    items = parsed
                    logger.info(f"Parsed JSON string to array: {items}")
            except (json.JSONDecodeError, TypeError):
                pass

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

        current_item = items[current_index]

        logger.info(
            f"Iteration node {node_id}: index={current_index}, item={current_item}, total={len(items)}"
        )

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

    async def _execute_object_iteration(
        self,
        node_id: str,
        items: Any,
        key_var: str,
        value_var: str,
        max_iterations: int,
        context: "ExecutionContext",
    ) -> ExecutionResult:
        """Execute object iteration (key-value pairs)."""
        if items is None or not isinstance(items, dict):
            # Try to parse JSON string
            if isinstance(items, str):
                import json

                try:
                    parsed = json.loads(items)
                    if isinstance(parsed, dict):
                        items = parsed
                except (json.JSONDecodeError, TypeError):
                    pass

            if not isinstance(items, dict):
                return ExecutionResult(
                    outputs={
                        key_var: None,
                        value_var: None,
                        "total": 0,
                        "results": [],
                        "_iteration_complete": True,
                    }
                )

        # Convert dict to list of (key, value) pairs
        pairs = list(items.items())

        # Limit iterations
        if len(pairs) > max_iterations:
            logger.warning(
                f"Iteration limited to {max_iterations} items (original: {len(pairs)})"
            )
            pairs = pairs[:max_iterations]

        # Get current iteration state
        iteration_state = await context.get_variable(f"{node_id}._iteration_state")

        if iteration_state is None:
            current_index = 0
            results = []
        else:
            current_index = iteration_state.get("index", 0) + 1
            results = iteration_state.get("results", [])

        # Check if iteration is complete
        if current_index >= len(pairs):
            return ExecutionResult(
                outputs={
                    key_var: None,
                    value_var: None,
                    "total": len(pairs),
                    "results": results,
                    "_iteration_complete": True,
                }
            )

        current_key, current_value = pairs[current_index]

        logger.info(
            f"Iteration node {node_id}: index={current_index}, key={current_key}, value={current_value}, total={len(pairs)}"
        )

        # Store iteration state
        await context.set_variable(
            f"{node_id}._iteration_state",
            {
                "index": current_index,
                "total": len(pairs),
                "results": results,
                "pairs": pairs,
            },
        )

        # Publish iteration event
        stream_manager = StreamManager(context.run_id)
        await stream_manager.publish_iteration(
            node_id=node_id,
            iteration=current_index + 1,
            total=len(pairs),
            is_start=True,
            item=current_key,
        )

        return ExecutionResult(
            outputs={
                key_var: current_key,
                value_var: current_value,
                "total": len(pairs),
                "results": results,
                "_iteration_complete": False,
                "_iteration_index": current_index,
            }
        )

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables."""
        iterator_type = config.get("iteratorType", "array")
        if iterator_type == "object":
            key_var = config.get("keyVariable", "key")
            value_var = config.get("valueVariable", "value")
            return [
                {"name": key_var, "type": "string"},
                {"name": value_var, "type": "any"},
                {"name": "total", "type": "number"},
                {"name": "results", "type": "array"},
            ]
        else:
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
        node_id = str(node.get("id") or "")
        node_data = node.get("data", {})
        # Frontend stores config in loopConfig, fallback to config for backwards compatibility
        config = node_data.get("loopConfig") or node_data.get("config", {})

        condition_var = config.get("conditionVariable", "")
        condition_op = config.get("conditionOperator", "equals")
        condition_value = config.get("conditionValue", "true")
        max_iterations = min(config.get("maxIterations", 100), MAX_ITERATIONS)
        counter_var = config.get("counterVariable") or config.get(
            "indexVariable", "loopCount"
        )
        output_var = config.get("outputVariable", "results")
        loop_variables = config.get("loopVariables", [])

        logger.info(
            f"Loop node {node_id}: config={config}, condition_var={condition_var}, max_iterations={max_iterations}"
        )

        # Get current loop state
        loop_state = await context.get_variable(f"{node_id}._loop_state")

        if loop_state is None:
            current_count = 0
            results = []
            logger.info(f"Loop node {node_id}: first iteration, count={current_count}")
        else:
            current_count = loop_state.get("count", 0) + 1
            results = loop_state.get("results", [])
            logger.info(
                f"Loop node {node_id}: continuing iteration, count={current_count}, results_count={len(results)}"
            )

        # Check if results variable was updated by child nodes (e.g., variable assignment)
        # This allows child nodes to modify the results array
        updated_results = await context.get_variable(f"{node_id}.{output_var}")
        if updated_results is not None:
            results = updated_results
            logger.info(
                f"Loop node {node_id}: loaded updated results from context, count={len(results)}"
            )

        # Check max iterations
        if current_count >= max_iterations:
            logger.warning(f"Loop reached max iterations: {max_iterations}")
            return ExecutionResult(
                outputs={
                    counter_var: current_count,
                    output_var: results,
                    "_loop_complete": True,
                    "_loop_reason": "max_iterations",
                }
            )

        # Evaluate condition (if condition variable is set)
        # If no condition is set, default to True (loop until maxIterations)

        # Check exit conditions (new format from frontend)
        exit_conditions = config.get("exitConditions", [])
        exit_logic_operator = config.get("exitLogicOperator", "and")

        if exit_conditions:
            # Evaluate all exit conditions
            condition_results = []
            for condition in exit_conditions:
                var_ref = condition.get("variable", "")
                operator = condition.get("operator", "equals")
                compare_value = condition.get("value", "")

                # Resolve variable reference (can access loop variables like {{loop-xxx.index}})
                result = await self._evaluate_condition(
                    context, var_ref, operator, compare_value
                )
                condition_results.append(result)
                logger.info(
                    f"Loop node {node_id}: exit condition {var_ref} {operator} {compare_value} = {result}"
                )

            # Apply logic operator
            if exit_logic_operator == "and":
                should_exit = all(condition_results)
            else:  # "or"
                should_exit = any(condition_results)

            if should_exit:
                logger.info(f"Loop node {node_id}: exit conditions met, ending loop")
                return ExecutionResult(
                    outputs={
                        counter_var: current_count,
                        output_var: results,
                        "_loop_complete": True,
                        "_loop_reason": "exit_conditions_met",
                    }
                )
        # Fallback to old single condition format for backwards compatibility
        elif condition_var:
            condition_result = await self._evaluate_condition(
                context, condition_var, condition_op, condition_value
            )
            logger.info(f"Loop node {node_id}: condition_result={condition_result}")

            if not condition_result:
                logger.info(f"Loop node {node_id}: condition false, ending loop")
                return ExecutionResult(
                    outputs={
                        counter_var: current_count,
                        output_var: results,
                        "_loop_complete": True,
                        "_loop_reason": "condition_false",
                    }
                )
        else:
            logger.info(
                f"Loop node {node_id}: no condition set, will loop until maxIterations"
            )

        # Store loop state
        await context.set_variable(
            f"{node_id}._loop_state",
            {
                "count": current_count,
                "results": results,
            },
        )

        # Build outputs with loop variables
        outputs = {
            counter_var: current_count,
            output_var: results,
            "_loop_complete": False,
            "_loop_iteration": current_count,
        }

        # Add loop variables (for custom variables defined in config)
        for var in loop_variables:
            var_name = var.get("name")
            if var_name:
                # Try to get existing value from context
                existing_value = await context.get_variable(f"{node_id}.{var_name}")
                if existing_value is not None:
                    outputs[var_name] = existing_value

        logger.info(f"Loop node {node_id}: continuing loop, outputs={outputs}")
        return ExecutionResult(outputs=outputs)

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
