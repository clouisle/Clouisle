"""
Condition node executor.

Handles conditional branching in workflows.
"""

from typing import TYPE_CHECKING, Any, cast
import logging

from ..executor import NodeExecutor, NodeExecutorRegistry, ExecutionResult

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from ..context import ExecutionContext

logger = logging.getLogger(__name__)


# Comparison operators
OPERATORS = {
    "equals": lambda a, b: a == b,
    "not_equals": lambda a, b: a != b,
    "contains": lambda a, b: str(b) in str(a),
    "not_contains": lambda a, b: str(b) not in str(a),
    "starts_with": lambda a, b: str(a).startswith(str(b)),
    "ends_with": lambda a, b: str(a).endswith(str(b)),
    "greater_than": lambda a, b: float(a) > float(b),
    "less_than": lambda a, b: float(a) < float(b),
    "greater_or_equal": lambda a, b: float(a) >= float(b),
    "less_or_equal": lambda a, b: float(a) <= float(b),
    "is_empty": lambda a, b: (
        not a or (isinstance(a, (list, dict, str)) and len(a) == 0)
    ),
    "is_not_empty": lambda a, b: (
        a and (not isinstance(a, (list, dict, str)) or len(a) > 0)
    ),
    "is_null": lambda a, b: a is None,
    "is_not_null": lambda a, b: a is not None,
    "regex_match": lambda a, b: bool(__import__("re").match(str(b), str(a))),
}


@NodeExecutorRegistry.register("condition")
class ConditionNodeExecutor(NodeExecutor):
    """
    Condition node executor.

    Evaluates conditions and determines which branch to take.

    Node Config:
        {
            "conditions": [
                {
                    "id": "condition_1",
                    "variable": "{{llm.response}}",
                    "operator": "contains",
                    "value": "error",
                    "logicalOperator": "and"  # for chaining conditions
                }
            ],
            "branches": [
                {
                    "id": "branch_if",
                    "handle": "if",
                    "conditions": ["condition_1"]
                },
                {
                    "id": "branch_else",
                    "handle": "else",
                    "isDefault": true
                }
            ]
        }

    Outputs:
        {
            "matched_branch": "if" | "else",
            "conditions_result": {...}
        }

    next_handles:
        ["if"] or ["else"] - which branch to execute
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute condition node."""
        node_id = str(node.get("id") or "")
        node_data = node.get("data", {})

        # Frontend stores branches directly in node_data, conditions inside branches
        # Also check config/conditionConfig for backward compatibility
        config = node_data.get("config", {})
        condition_config = node_data.get("conditionConfig", config)

        # Branches can be in node_data directly or in config
        branches = node_data.get("branches", []) or condition_config.get("branches", [])

        # Conditions are typically inside each branch, but may also be at top level
        conditions = condition_config.get("conditions", [])

        logger.info(f"Condition node {node_id}: branches count={len(branches)}")

        # Evaluate all top-level conditions first (if any)
        condition_results = {}
        for cond in conditions:
            cond_id = cond.get("id")
            result = await self._evaluate_condition(cond, context)
            condition_results[cond_id] = result
            logger.info(f"Top-level condition {cond_id}: {result}")

        # Determine which branch to take
        matched_branch = None
        matched_handle = None

        for branch in branches:
            branch_id = branch.get("id")
            is_default = branch.get("isDefault", False)

            if is_default:
                continue

            # Get conditions for this branch - they may be embedded in the branch
            branch_conditions = branch.get("conditions", [])
            logical_op = branch.get("logicalOperator", "and")

            logger.info(
                f"Evaluating branch {branch_id}: conditions={branch_conditions}, op={logical_op}, isDefault={is_default}"
            )

            if not branch_conditions:
                continue

            # Evaluate each condition in this branch
            branch_condition_results = []
            for cond in branch_conditions:
                if isinstance(cond, dict):
                    # Condition is embedded in branch
                    result = await self._evaluate_condition(cond, context)
                    branch_condition_results.append(result)
                    logger.info(f"  Branch condition: {cond} -> {result}")
                elif isinstance(cond, str):
                    # Condition is a reference to top-level condition
                    result = condition_results.get(cond, False)
                    branch_condition_results.append(result)

            # Evaluate branch condition combination
            if logical_op == "and":
                branch_result = (
                    all(branch_condition_results) if branch_condition_results else False
                )
            else:  # or
                branch_result = (
                    any(branch_condition_results) if branch_condition_results else False
                )

            logger.info(f"Branch {branch_id} result: {branch_result}")

            if branch_result:
                matched_branch = branch_id
                # Handle IS the branch ID (if, else_if_xxx, else)
                # This matches the React Flow Handle id={branch.id} in condition-node.tsx
                matched_handle = branch_id
                logger.info(
                    f"Matched branch: {matched_branch}, handle: {matched_handle}"
                )
                break

        # Use default branch if no condition matched
        if not matched_handle:
            for branch in branches:
                if branch.get("isDefault") or branch.get("type") == "else":
                    matched_branch = branch.get("id")
                    # Handle IS the branch ID - for else branch, id is typically "else"
                    matched_handle = matched_branch
                    logger.info(
                        f"Using default/else branch: {matched_branch}, handle: {matched_handle}"
                    )
                    break

        if not matched_handle:
            matched_handle = "else"

        # Store branch taken in context for downstream nodes
        await context.set_branch(node_id, matched_handle)

        return ExecutionResult(
            outputs={
                "matched_branch": matched_handle,
                "condition_results": condition_results,
            },
            next_handles=[matched_handle],
        )

    async def _evaluate_condition(
        self,
        condition: dict,
        context: "ExecutionContext",
    ) -> bool:
        """Evaluate a single condition."""
        variable_ref = condition.get("variable", "")
        op = condition.get("operator", "equals")
        compare_value = condition.get("value", "")

        # Resolve variable reference
        actual_value = await context.resolve_variable_ref(variable_ref)

        # Resolve compare value if it's a reference
        if isinstance(compare_value, str) and compare_value.startswith("{{"):
            compare_value = await context.resolve_variable_ref(compare_value)

        # Get operator function
        op_func = OPERATORS.get(op)
        if not op_func:
            logger.warning(f"Unknown operator: {op}, defaulting to equals")
            op_func = OPERATORS["equals"]

        try:
            return op_func(actual_value, compare_value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Condition evaluation error: {e}")
            return False

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables."""
        return [
            {"name": "matched_branch", "type": "string"},
            {"name": "condition_results", "type": "object"},
        ]


@NodeExecutorRegistry.register("question_classifier")
class QuestionClassifierNodeExecutor(NodeExecutor):
    """
    Question classifier node executor.

    Uses LLM to classify input into predefined categories.

    Node Config:
        {
            "modelId": "uuid",
            "inputVariable": "{{start.query}}",
            "categories": [
                {
                    "id": "tech",
                    "name": "Technical Support",
                    "description": "Questions about technical issues",
                    "handle": "tech"
                },
                {
                    "id": "billing",
                    "name": "Billing",
                    "description": "Questions about billing and payments",
                    "handle": "billing"
                }
            ],
            "defaultCategory": "other"
        }

    Outputs:
        {
            "category": "tech",
            "confidence": 0.95,
            "reasoning": "The question mentions error codes..."
        }

    next_handles:
        ["tech"] - which category branch to take
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute question classifier node."""
        from app.llm import model_manager
        from app.models.model import Model, TeamModel
        import json

        node_id = str(node.get("id") or "")
        node_data = node.get("data", {})

        # Frontend stores config in questionClassifierConfig, also check config for backward compatibility
        config = node_data.get("questionClassifierConfig", {}) or node_data.get(
            "config", {}
        )

        logger.info(
            f"Question classifier node {node_id}: config keys={list(config.keys())}"
        )

        # Note: modelId from frontend is team_models.id (TeamModel ID), not models.id
        team_model_id = config.get("modelId")
        # Frontend uses sourceVariable, backend uses inputVariable for compatibility
        input_var = config.get("sourceVariable") or config.get("inputVariable", "")
        categories = config.get("categories", [])
        default_category = config.get("defaultCategory", "other")
        instruction = config.get("instruction", "")

        if not team_model_id:
            logger.error(
                f"Question classifier node {node_id}: modelId not found. Config: {config}"
            )
            return ExecutionResult(error="Model ID not configured")

        # Get input value
        input_value = await context.resolve_variable_ref(input_var)
        if not input_value:
            return ExecutionResult(error="No input provided for classification")

        # First try to find as TeamModel ID, then fallback to Model ID
        team_model = (
            await TeamModel.filter(id=team_model_id).prefetch_related("model").first()
        )
        model_id: str
        if team_model:
            model_id = str(team_model.model.id)
        else:
            # Fallback: try as direct Model ID for backward compatibility
            model = await Model.filter(id=team_model_id).first()
            if model is None:
                return ExecutionResult(error=f"Model not found: {team_model_id}")
            model_id = str(model.id)

        # Build classification prompt
        category_descriptions = "\n".join(
            [
                f"- {cat.get('id')}: {cat.get('name')} - {cat.get('description', '')}"
                for cat in categories
            ]
        )

        # Build system prompt with optional instruction
        base_prompt = f"""You are a question classifier. Classify the user's input into one of these categories:

{category_descriptions}

Respond in JSON format:
{{"category": "category_id", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}"""

        if instruction:
            system_prompt = f"{base_prompt}\n\nAdditional instructions:\n{instruction}"
        else:
            system_prompt = base_prompt

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": str(input_value)},
        ]

        try:
            result = await model_manager.chat(
                messages=cast(list[Any], messages),
                model_id=str(model_id),
                temperature=0.1,  # Low temperature for classification
                max_tokens=256,
            )

            response_text = result.content or ""

            # Parse JSON response
            try:
                # Try to extract JSON from response
                import re

                json_match = re.search(r"\{[^}]+\}", response_text)
                if json_match:
                    parsed = json.loads(json_match.group())
                else:
                    parsed = json.loads(response_text)

                category = parsed.get("category", default_category)
                confidence = parsed.get("confidence", 0.5)
                reasoning = parsed.get("reasoning", "")

                # Validate category exists - check both id and name
                valid_ids = [c.get("id") for c in categories]
                valid_names = [c.get("name") for c in categories]

                if category not in valid_ids:
                    # Try matching by name
                    if category in valid_names:
                        # Convert name to id
                        for cat in categories:
                            if cat.get("name") == category:
                                category = cat.get("id")
                                break
                    else:
                        category = default_category

            except json.JSONDecodeError:
                # Fallback: try to find category name/id in response
                category = default_category
                response_lower = response_text.lower()
                for cat in categories:
                    cat_id = cat.get("id", "").lower()
                    cat_name = cat.get("name", "").lower()
                    if cat_id in response_lower or cat_name in response_lower:
                        category = cat.get("id")
                        break
                confidence = 0.5
                reasoning = response_text

            # Handle IS the category ID (matches React Flow Handle id={category.id})
            handle = category
            valid_ids = [c.get("id") for c in categories]
            if not handle or (
                handle == default_category and default_category not in valid_ids
            ):
                # Use first category as fallback if default_category is not a valid id
                if categories:
                    handle = categories[0].get("id")
                else:
                    handle = default_category

            await context.set_branch(node_id, handle)

            return ExecutionResult(
                outputs={
                    "category": category,
                    "confidence": confidence,
                    "reasoning": reasoning,
                },
                next_handles=[handle],
            )

        except Exception as e:
            logger.exception(f"Question classifier error: {e}")
            return ExecutionResult(error=f"Classification error: {str(e)}")
