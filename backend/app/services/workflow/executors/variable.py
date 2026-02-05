"""
Variable node executors.

Handles variable manipulation: assignment, aggregation, etc.
"""

from typing import TYPE_CHECKING, Any
import logging

from ..executor import NodeExecutor, NodeExecutorRegistry, ExecutionResult

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from ..context import ExecutionContext

logger = logging.getLogger(__name__)


@NodeExecutorRegistry.register("variable_assignment")
class VariableAssignmentNodeExecutor(NodeExecutor):
    """
    Variable assignment node executor.

    Assigns values to variables for use in downstream nodes.

    Node Config (variableAssignmentConfig):
        {
            "assignments": [
                {
                    "id": "xxx",
                    "targetVariable": "conversation.processed_query",
                    "operation": "overwrite",
                    "variableRef": "{{start.query}}"
                },
                {
                    "id": "yyy",
                    "targetVariable": "conversation.status",
                    "operation": "set",
                    "constantValue": "completed"
                },
                {
                    "id": "zzz",
                    "targetVariable": "conversation.temp",
                    "operation": "clear"
                }
            ]
        }

    Outputs:
        All assigned variables with their target names (without conversation. prefix)
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute variable assignment node.
        
        This node modifies the original node's output so that all downstream
        references to the variable will get the new value.
        """
        node_data = node.get("data", {})
        # Try variableAssignmentConfig first (frontend structure), then fall back to config
        config = node_data.get("variableAssignmentConfig") or node_data.get("config", {})
        
        logger.info(f"Variable assignment node: {node.get('id')}, config: {config}")
        
        assignments = config.get("assignments", [])

        outputs = {}

        for assignment in assignments:
            target_var = assignment.get("targetVariable", "")
            operation = assignment.get("operation", "overwrite")

            if not target_var:
                continue

            # Parse target variable - could be:
            # - "conversation.xxx" -> conversation variable
            # - "nodeId.varName" -> node output variable (e.g., iteration results)
            # - "xxx" -> simple variable name
            target_node_id = None
            name = target_var

            if name.startswith("conversation."):
                name = name[len("conversation."):]
            elif "." in name and not name.startswith("sys."):
                # Format: nodeId.varName (e.g., "iteration-123.results")
                parts = name.rsplit(".", 1)
                if len(parts) == 2:
                    target_node_id = parts[0]
                    name = parts[1]

            if operation == "overwrite":
                var_ref = assignment.get("variableRef", "")
                value = await context.resolve_variable_ref(var_ref)
                logger.info(f"Variable assignment overwrite: var_ref={var_ref}, value={value}")
            elif operation == "set":
                value = assignment.get("constantValue", "")
            elif operation == "clear":
                value = None
            elif operation == "append":
                # Append based on target type
                var_ref = assignment.get("variableRef", "")
                append_value = await context.resolve_variable_ref(var_ref)
                logger.info(f"Variable assignment append: var_ref={var_ref}, append_value={append_value}")

                # Get current value of target variable
                current_value = None
                if target_node_id:
                    # For iteration results, get from _iteration_state first (most up-to-date)
                    if name == "results":
                        iteration_state = await context.get_variable(f"{target_node_id}._iteration_state")
                        if iteration_state:
                            current_value = iteration_state.get("results")
                    # Fallback to node outputs
                    if current_value is None:
                        node_outputs = await context.get_node_outputs(target_node_id)
                        if node_outputs:
                            current_value = node_outputs.get(name)
                else:
                    current_value = await context.get_variable(name) or await context.get_variable(f"conversation.{name}")

                if isinstance(current_value, list):
                    # Append to array
                    value = current_value + [append_value] if not isinstance(append_value, list) else current_value + append_value
                elif isinstance(current_value, dict) and isinstance(append_value, dict):
                    # Merge into object
                    value = {**current_value, **append_value}
                elif isinstance(current_value, str):
                    # String concatenation
                    value = current_value + str(append_value)
                elif isinstance(current_value, (int, float)) and isinstance(append_value, (int, float)):
                    # Numeric addition
                    value = current_value + append_value
                elif current_value is None:
                    # Initialize as array with single element
                    value = [append_value] if not isinstance(append_value, list) else append_value
                else:
                    # Convert to array and append
                    value = [current_value, append_value]
            else:
                value = None

            outputs[name] = value

            # Update the target location
            if target_node_id:
                # Update specific node's outputs
                node_outputs = await context.get_node_outputs(target_node_id) or {}
                node_outputs[name] = value
                await context.set_node_outputs(target_node_id, node_outputs)
                logger.info(f"Updated {target_node_id}.{name} = {value}")

                # Also update iteration/loop state if this is results
                if name == "results":
                    # Update iteration state
                    iteration_state = await context.get_variable(f"{target_node_id}._iteration_state")
                    if iteration_state:
                        iteration_state["results"] = value
                        await context.set_variable(f"{target_node_id}._iteration_state", iteration_state)

                    # Update loop state
                    loop_state = await context.get_variable(f"{target_node_id}._loop_state")
                    if loop_state:
                        loop_state["results"] = value
                        await context.set_variable(f"{target_node_id}._loop_state", loop_state)
                        logger.info(f"Updated {target_node_id}._loop_state.results = {value}")
            else:
                # Store in global variables for conversation.xxx access
                await context.set_variable(name, value)
                await context.set_variable(f"conversation.{name}", value)

                # IMPORTANT: Also update ALL node outputs that have this variable name
                # This ensures that downstream references like {{开始.query}} get the new value
                all_outputs = await context.get_all_node_outputs()
                for node_id, node_outputs in all_outputs.items():
                    if node_outputs and name in node_outputs:
                        node_outputs[name] = value
                        await context.set_node_outputs(node_id, node_outputs)
                        logger.info(f"Updated {node_id}.{name} = {value}")

            logger.info(f"Assigned variable {target_var} = {value}")

        logger.info(f"Variable assignment outputs: {outputs}")
        return ExecutionResult(outputs=outputs)

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables from config."""
        assignments = config.get("assignments", [])
        return [
            {"name": a.get("name"), "type": "any"}
            for a in assignments
            if a.get("name")
        ]


@NodeExecutorRegistry.register("variable_aggregator")
class VariableAggregatorNodeExecutor(NodeExecutor):
    """
    Variable aggregator node executor.

    Combines multiple variables into a single output.

    Node Config (variableAggregatorConfig):
        {
            "mode": "array" | "object" | "concat" | "merge",
            "variables": [
                {"id": "xxx", "sourceVariable": "{{node1.result}}", "targetKey": "key1"},
                {"id": "yyy", "sourceVariable": "{{node2.result}}", "targetKey": "key2"}
            ],
            "outputVariable": "result",
            "separator": ""  # for concat mode
        }

    Outputs:
        {
            "result": [...] | {...} | "concatenated string"
        }
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute variable aggregator node."""
        node_data = node.get("data", {})
        # Try variableAggregatorConfig first (frontend structure), then fall back to config
        config = node_data.get("variableAggregatorConfig") or node_data.get("config", {})
        
        logger.info(f"Variable aggregator node_data keys: {list(node_data.keys())}")
        logger.info(f"Variable aggregator config: {config}")

        mode = config.get("mode", "array")
        variables = config.get("variables", [])
        output_var = config.get("outputVariable", "result")
        separator = config.get("separator", "")
        
        logger.info(f"Mode: {mode}, variables count: {len(variables)}, output_var: {output_var}")
        
        logger.debug(f"Mode: {mode}, variables: {variables}, output_var: {output_var}")

        # Resolve all variables - frontend uses 'sourceVariable' field with 'value' format for resolve_inputs
        # We need to convert the format
        input_mappings = []
        for var in variables:
            source_var = var.get("sourceVariable", "")
            target_key = var.get("targetKey") or var.get("id", "")
            input_mappings.append({
                "name": target_key,
                "value": source_var,
            })
        
        resolved = await self.resolve_inputs(context, input_mappings)
        
        logger.info(f"Variable aggregator resolved: {resolved}")

        # Aggregate based on mode
        if mode == "array":
            # Return values as array, maintaining order
            result = list(resolved.values())
        elif mode == "object":
            # Return as object with targetKey as keys
            result = resolved
        elif mode == "concat":
            # Concatenate string values
            result = separator.join(str(v) for v in resolved.values() if v is not None)
        elif mode == "merge":
            # Deep merge objects
            result = {}
            for value in resolved.values():
                if isinstance(value, dict):
                    result = self._deep_merge(result, value)
                else:
                    logger.warning(f"Cannot merge non-dict value: {value}")
        else:
            result = resolved
        
        logger.info(f"Variable aggregator result: {result}")

        return ExecutionResult(outputs={output_var: result})

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables."""
        output_var = config.get("outputVariable", "result")
        mode = config.get("mode", "array")
        var_type = "array" if mode == "array" else "object" if mode in ("object", "merge") else "string"
        return [{"name": output_var, "type": var_type}]


@NodeExecutorRegistry.register("parameter_extractor")
class ParameterExtractorNodeExecutor(NodeExecutor):
    """
    Parameter extractor node executor.

    Uses LLM to extract structured parameters from text.

    Node Config (parameterExtractorConfig):
        {
            "extractionMethod": "llm",
            "sourceVariable": "{{start.query}}",
            "modelId": "uuid",
            "useJsonSchema": true,
            "parameters": [
                {
                    "id": "xxx",
                    "name": "date",
                    "type": "string",
                    "description": "Date mentioned in the text",
                    "required": true
                },
                {
                    "id": "yyy",
                    "name": "location",
                    "type": "string",
                    "description": "Location or place mentioned",
                    "required": false
                }
            ]
        }

    Outputs:
        {
            "date": "2024-01-15",
            "location": "New York",
            "_extraction_confidence": 0.9
        }
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute parameter extractor node."""

        node_data = node.get("data", {})
        # Try parameterExtractorConfig first (frontend structure), then fall back to config
        config = node_data.get("parameterExtractorConfig") or node_data.get("config", {})
        
        logger.debug(f"Parameter extractor config: {config}")

        source_var = config.get("sourceVariable", "")
        parameters = config.get("parameters", [])
        extraction_method = config.get("extractionMethod", "llm")

        # Get input value
        input_value = await context.resolve_variable_ref(source_var)
        if input_value is None:
            return ExecutionResult(error="No input provided for extraction")
        
        logger.info(f"Parameter extractor input: {str(input_value)[:200]}...")
        logger.info(f"Extraction method: {extraction_method}")

        # Route to appropriate extraction method
        if extraction_method == "json_path":
            return await self._extract_with_jsonpath(input_value, parameters)
        elif extraction_method == "regex":
            return await self._extract_with_regex(str(input_value), parameters)
        else:  # llm
            return await self._extract_with_llm(input_value, parameters, config, run)

    async def _extract_with_jsonpath(
        self, input_value: Any, parameters: list[dict]
    ) -> ExecutionResult:
        """Extract parameters using JSONPath expressions."""
        import json

        try:
            import jsonpath_ng  # noqa: F401
            from jsonpath_ng import parse as jsonpath_parse
        except ImportError:
            return ExecutionResult(error="jsonpath-ng package not installed. Run: pip install jsonpath-ng")
        
        # Parse input as JSON if it's a string
        if isinstance(input_value, str):
            try:
                data = json.loads(input_value)
            except json.JSONDecodeError:
                return ExecutionResult(error="Input is not valid JSON")
        elif isinstance(input_value, (dict, list)):
            data = input_value
        else:
            return ExecutionResult(error=f"Input must be JSON string, dict, or list, got {type(input_value)}")
        
        outputs = {}
        for param in parameters:
            name = param.get("name")
            json_path = param.get("jsonPath", "")
            required = param.get("required", False)
            default_value = param.get("defaultValue")
            param_type = param.get("type", "string")
            
            if not name or not json_path:
                continue
            
            try:
                # Parse and execute JSONPath
                jsonpath_expr = jsonpath_parse(json_path)
                matches = jsonpath_expr.find(data)
                
                if matches:
                    # Get the first match value
                    value = matches[0].value
                    
                    # If multiple matches and expecting array, return all
                    if len(matches) > 1 and param_type == "array":
                        value = [m.value for m in matches]
                    
                    outputs[name] = value
                elif default_value is not None:
                    # Try to parse default value based on type
                    outputs[name] = self._parse_default_value(default_value, param_type)
                elif required:
                    return ExecutionResult(error=f"Required parameter '{name}' not found at path: {json_path}")
                else:
                    outputs[name] = None
                    
            except Exception as e:
                logger.warning(f"JSONPath error for {name}: {e}")
                if required:
                    return ExecutionResult(error=f"JSONPath error for '{name}': {str(e)}")
                outputs[name] = self._parse_default_value(default_value, param_type) if default_value else None
        
        outputs["_extraction_method"] = "json_path"
        logger.info(f"JSONPath extraction outputs: {outputs}")
        return ExecutionResult(outputs=outputs)

    async def _extract_with_regex(
        self, input_text: str, parameters: list[dict]
    ) -> ExecutionResult:
        """Extract parameters using regex patterns."""
        import re
        
        outputs = {}
        for param in parameters:
            name = param.get("name")
            pattern = param.get("pattern", "")
            required = param.get("required", False)
            default_value = param.get("defaultValue")
            param_type = param.get("type", "string")
            
            if not name or not pattern:
                continue
            
            try:
                matches = re.findall(pattern, input_text)
                
                if matches:
                    if param_type == "array":
                        # Return all matches as array
                        outputs[name] = list(matches)
                    else:
                        # Return first match
                        value = matches[0]
                        # Handle groups - if match is tuple, take first group
                        if isinstance(value, tuple):
                            value = value[0] if value else ""
                        outputs[name] = self._convert_value(value, param_type)
                elif default_value is not None:
                    outputs[name] = self._parse_default_value(default_value, param_type)
                elif required:
                    return ExecutionResult(error=f"Required parameter '{name}' not found with pattern: {pattern}")
                else:
                    outputs[name] = None
                    
            except re.error as e:
                logger.warning(f"Regex error for {name}: {e}")
                if required:
                    return ExecutionResult(error=f"Invalid regex pattern for '{name}': {str(e)}")
                outputs[name] = self._parse_default_value(default_value, param_type) if default_value else None
        
        outputs["_extraction_method"] = "regex"
        logger.info(f"Regex extraction outputs: {outputs}")
        return ExecutionResult(outputs=outputs)

    async def _extract_with_llm(
        self, input_value: Any, parameters: list[dict], config: dict, run: "WorkflowRun"
    ) -> ExecutionResult:
        """Extract parameters using LLM."""
        from app.llm import model_manager
        from app.models.model import Model, TeamModel
        import json

        # Note: modelId from frontend is team_models.id (TeamModel ID), not models.id
        team_model_id = config.get("modelId")

        if not team_model_id:
            return ExecutionResult(error="Model ID not configured for LLM extraction")

        # First try to find as TeamModel ID, then fallback to Model ID
        team_model = await TeamModel.filter(id=team_model_id).prefetch_related("model").first()
        if team_model:
            model = team_model.model
            model_id = str(model.id)
        else:
            # Fallback: try as direct Model ID for backward compatibility
            model = await Model.filter(id=team_model_id).first()
            if not model:
                return ExecutionResult(error=f"Model not found: {team_model_id}")
            model_id = str(model.id)

        # Build extraction prompt
        param_schema = []
        for param in parameters:
            param_desc = {
                "name": param.get("name"),
                "type": param.get("type", "string"),
                "description": param.get("description", ""),
                "required": param.get("required", False),
            }
            param_schema.append(param_desc)

        schema_json = json.dumps(param_schema, indent=2, ensure_ascii=False)

        system_prompt = config.get("systemPrompt") or f"""You are a parameter extraction assistant. Extract the following parameters from the user's input:

{schema_json}

Respond in JSON format with the extracted values. If a parameter cannot be found and is not required, use null.
Example response: {{"date": "2024-01-15", "location": null}}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": str(input_value)},
        ]

        try:
            result = await model_manager.chat(
                messages=messages,
                model_id=str(model_id),
                temperature=0.1,
                max_tokens=512,
            )

            response_text = result.content or ""
            
            logger.info(f"Parameter extractor LLM response: {response_text}")

            # Parse JSON response
            try:
                import re
                json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                else:
                    parsed = json.loads(response_text)

                # Validate required parameters
                outputs = {}
                for param in parameters:
                    name = param.get("name")
                    required = param.get("required", False)
                    value = parsed.get(name)

                    if required and value is None:
                        return ExecutionResult(
                            error=f"Required parameter '{name}' could not be extracted"
                        )

                    outputs[name] = value

                outputs["_extraction_method"] = "llm"
                outputs["_extraction_confidence"] = 0.9  # Placeholder
                
                logger.info(f"LLM extraction outputs: {outputs}")

                return ExecutionResult(outputs=outputs)

            except json.JSONDecodeError:
                return ExecutionResult(error="Failed to parse LLM extraction result")

        except Exception as e:
            logger.exception(f"LLM parameter extraction error: {e}")
            return ExecutionResult(error=f"LLM extraction error: {str(e)}")

    def _parse_default_value(self, value: str | None, param_type: str) -> Any:
        """Parse default value string to the appropriate type."""
        if value is None:
            return None
        
        import json
        
        try:
            if param_type == "number":
                return float(value) if "." in value else int(value)
            elif param_type == "boolean":
                return value.lower() in ("true", "1", "yes")
            elif param_type in ("array", "object"):
                return json.loads(value)
            else:
                return value
        except (ValueError, json.JSONDecodeError):
            return value

    def _convert_value(self, value: str, param_type: str) -> Any:
        """Convert extracted string value to the appropriate type."""
        if param_type == "number":
            try:
                return float(value) if "." in value else int(value)
            except ValueError:
                return value
        elif param_type == "boolean":
            return value.lower() in ("true", "1", "yes")
        else:
            return value

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables from config."""
        parameters = config.get("parameters", [])
        result = [
            {"name": p.get("name"), "type": p.get("type", "string")}
            for p in parameters
            if p.get("name")
        ]
        result.append({"name": "_extraction_confidence", "type": "number"})
        return result
