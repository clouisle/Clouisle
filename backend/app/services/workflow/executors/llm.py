"""
LLM node executor.

Handles AI model inference calls.
"""

from typing import TYPE_CHECKING
import logging

from ..executor import NodeExecutor, NodeExecutorRegistry, ExecutionResult
from ..lazy_stream import LazyStreamResult

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from ..context import ExecutionContext

logger = logging.getLogger(__name__)


@NodeExecutorRegistry.register("llm")
class LLMNodeExecutor(NodeExecutor):
    """
    LLM node executor.

    Calls language models with configurable prompts and parameters.

    Node Config:
        {
            "modelId": "uuid-of-model",
            "systemPrompt": "You are a helpful assistant",
            "userPrompt": "{{start.query}}",
            "temperature": 0.7,
            "maxTokens": 2048,
            "topP": 1.0,
            "stream": true,
            "inputs": [
                {"name": "context", "variableRef": "{{kb.results}}"}
            ]
        }

    Outputs:
        {
            "response": "Generated text response",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150
            }
        }
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute LLM node."""
        from app.llm import model_manager
        from app.models.model import Model, TeamModel

        node_id = node.get("id")
        node_data = node.get("data", {})
        config = node_data.get("config", {})
        llm_config = node_data.get("llmConfig", config)

        logger.info(f"LLM node {node_id}: node_data keys={list(node_data.keys())}")
        logger.info(f"LLM node {node_id}: llmConfig={llm_config}")

        # Get model configuration
        # Note: modelId from frontend is team_models.id (TeamModel ID), not models.id
        team_model_id = llm_config.get("modelId")
        if not team_model_id:
            logger.error(
                f"LLM node {node_id}: modelId not found in llmConfig. Available keys: {list(llm_config.keys())}"
            )
            return ExecutionResult(error="Model ID not configured")

        # First try to find as TeamModel ID, then fallback to Model ID
        team_model = (
            await TeamModel.filter(id=team_model_id).prefetch_related("model").first()
        )
        if team_model:
            model = team_model.model
            model_id = str(model.id)
        else:
            # Fallback: try as direct Model ID for backward compatibility
            model = await Model.filter(id=team_model_id).first()
            if not model:
                return ExecutionResult(error=f"Model not found: {team_model_id}")
            model_id = str(model.id)

        # Resolve prompts
        system_prompt = llm_config.get("systemPrompt", "")
        user_prompt = llm_config.get("userPrompt", "")

        if system_prompt:
            system_prompt = await self._resolve_template(system_prompt, context)
        if user_prompt:
            user_prompt = await self._resolve_template(user_prompt, context)

        # Resolve input variables
        inputs = llm_config.get("inputs", [])
        resolved_inputs = await self.resolve_inputs(context, inputs)

        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Include resolved inputs in user prompt if any
        if resolved_inputs:
            input_context = "\n".join([f"{k}: {v}" for k, v in resolved_inputs.items()])
            user_prompt = (
                f"{input_context}\n\n{user_prompt}" if user_prompt else input_context
            )

        messages.append({"role": "user", "content": user_prompt})

        # LLM parameters
        temperature = llm_config.get("temperature", 0.7)
        max_tokens = llm_config.get("maxTokens", 2048)
        top_p = llm_config.get("topP", 1.0)
        should_stream = llm_config.get(
            "streaming", False
        )  # Frontend uses "streaming", default to non-streaming

        # Response format configuration
        response_format = None
        response_format_type = llm_config.get("responseFormat", "text")
        logger.info(f"LLM node {node_id}: responseFormat={response_format_type}")
        logger.info(f"LLM node {node_id}: Full llmConfig={llm_config}")

        if response_format_type == "json":
            response_format = {"type": "json_object"}
            logger.info(f"LLM node {node_id}: Using JSON object response format")
        elif response_format_type == "json_schema":
            json_schema_str = llm_config.get("jsonSchema")
            logger.info(f"LLM node {node_id}: jsonSchema string={json_schema_str}")
            if json_schema_str:
                try:
                    import json

                    schema = json.loads(json_schema_str)
                    response_format = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "response",
                            "strict": True,
                            "schema": schema,
                        },
                    }
                    logger.info(f"LLM node {node_id}: Constructed response_format={json.dumps(response_format, ensure_ascii=False)}")
                except json.JSONDecodeError as e:
                    logger.warning(
                        f"LLM node {node_id}: Invalid JSON schema: {e}, ignoring response_format"
                    )

        try:
            if should_stream:
                # For streaming mode, return a lazy result
                # The actual LLM call will be triggered when an Answer node references it
                lazy_result = LazyStreamResult(
                    model_id=str(model_id),
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    response_format=response_format,
                    context=context,
                    source_node_id=node_id,
                )

                logger.info(f"LLM node {node_id} returning lazy stream result")

                return ExecutionResult(
                    outputs={
                        "response": lazy_result,  # Lazy result, will be executed when referenced
                        "usage": {},  # Will be populated after execution
                    }
                )
            else:
                # Non-streaming mode
                result = await model_manager.chat(
                    messages=messages,
                    model_id=str(model_id),
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    response_format=response_format,
                )

                return ExecutionResult(
                    outputs={
                        "response": result.content or "",
                        "usage": {
                            "prompt_tokens": result.usage.prompt_tokens
                            if result.usage
                            else 0,
                            "completion_tokens": result.usage.completion_tokens
                            if result.usage
                            else 0,
                            "total_tokens": result.usage.total_tokens
                            if result.usage
                            else 0,
                        },
                    }
                )

        except Exception as e:
            logger.exception(f"LLM execution error: {e}")
            return ExecutionResult(error=f"LLM error: {str(e)}")

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

    async def validate_config(self, config: dict) -> list[str]:
        """Validate LLM node configuration."""
        errors = []

        if not config.get("modelId"):
            errors.append("Model ID is required")

        if not config.get("userPrompt") and not config.get("inputs"):
            errors.append("User prompt or inputs are required")

        return errors

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables."""
        return [
            {"name": "response", "type": "string"},
            {"name": "usage", "type": "object"},
        ]
