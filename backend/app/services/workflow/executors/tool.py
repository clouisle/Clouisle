"""
Tool and agent node executors.

Handles external tool calls and agent invocations.
"""

from typing import TYPE_CHECKING, Any
import logging
import json

from app.services.error_messages import resolve_user_visible_error

from ..executor import NodeExecutor, NodeExecutorRegistry, ExecutionResult
from ..stream import StreamManager
from ..errors import translate_public_workflow_error
from ..types import NodeOutputDecl, TypeSpec, WorkflowValue

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from ..context import ExecutionContext

logger = logging.getLogger(__name__)


@NodeExecutorRegistry.register("tool")
class ToolNodeExecutor(NodeExecutor):
    """
    Tool node executor.

    Executes a configured tool with input parameters.

    Node Config:
        {
            "toolId": "uuid",
            "inputs": [
                {"name": "query", "variableRef": "{{start.query}}"},
                {"name": "limit", "constantValue": "10"}
            ]
        }

    Outputs:
        {
            "result": tool_output,
            "status": "success" | "error",
            "executionTime": duration_ms
        }
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute tool node."""
        from app.models.tool import Tool
        from app.models.workflow import Workflow
        from app.services.tool import ToolExecutor
        import time

        node_data = node.get("data", {})
        # Try toolConfig first (frontend structure), then fall back to config.
        config = node_data.get("toolConfig") or node_data.get("config", {})

        tool_id = config.get("toolId") or config.get("tool_id")
        tool_name = config.get("toolName")
        tool_type = config.get("toolType")
        input_mappings = config.get("parameterMappings") or config.get("inputs", [])
        if not input_mappings and config.get("arguments"):
            input_mappings = [
                {
                    "name": name,
                    "source": "variable",
                    "variableRef": value,
                }
                for name, value in config["arguments"].items()
            ]
        output_var = config.get("outputVariable", "result")

        if not tool_id and not (tool_type == "builtin" and tool_name):
            return ExecutionResult(error="tool_not_found")

        # Resolve inputs
        inputs = await self.resolve_inputs(context, input_mappings)
        workflow_team_id = None
        if run.workflow_id:
            workflow = await Workflow.filter(id=run.workflow_id).only("team_id").first()
            workflow_team_id = workflow.team_id if workflow else None

        start_time = time.time()

        try:
            # Execute tool
            tool_executor = ToolExecutor()
            if tool_type == "builtin" and tool_name:
                result = await tool_executor.execute_builtin_tool(
                    tool_name=tool_name,
                    arguments=inputs,
                    team_id=workflow_team_id,
                )
            else:
                # Load tool
                tool = await Tool.filter(id=tool_id).first()
                if not tool:
                    return ExecutionResult(error="tool_not_found")

                result = await tool_executor.execute(
                    tool=tool,
                    arguments=inputs,
                    user_id=str(run.triggered_by_id) if run.triggered_by_id else None,
                    team_id=workflow_team_id,
                )

            duration_ms = int((time.time() - start_time) * 1000)

            outputs = {
                "result": result,
                "status": "success",
                "executionTime": duration_ms,
            }
            if output_var and output_var != "result":
                outputs[output_var] = result

            return ExecutionResult(outputs=outputs)

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.exception(f"Tool execution error: {e}")
            public_error = translate_public_workflow_error(e)
            outputs = {
                "result": None,
                "status": "error",
                "error": public_error,
                "executionTime": duration_ms,
            }
            if output_var and output_var != "result":
                outputs[output_var] = None
            return ExecutionResult(
                outputs=outputs,
                error=public_error,
            )

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables."""
        output_var = config.get("outputVariable", "result")
        variables = [
            {"name": "result", "type": "any"},
            {"name": "status", "type": "string"},
            {"name": "executionTime", "type": "number"},
        ]
        if output_var and output_var != "result":
            variables.insert(0, {"name": output_var, "type": "any"})
        return variables

    def get_output_specs(self, config: dict) -> list["NodeOutputDecl"]:
        """Get output specs with TypeSpec for type inference."""
        output_var = config.get("outputVariable", "result")
        specs = [
            NodeOutputDecl(name="result", type=TypeSpec(kind="any")),
            NodeOutputDecl(name="status", type=TypeSpec(kind="string")),
            NodeOutputDecl(name="executionTime", type=TypeSpec(kind="number")),
        ]
        if output_var and output_var != "result":
            specs.insert(0, NodeOutputDecl(name=output_var, type=TypeSpec(kind="any")))
        return specs


@NodeExecutorRegistry.register("agent")
class AgentNodeExecutor(NodeExecutor):
    """Invoke a configured Agent using the shared AgentService contract."""

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        from app.models.agent import Agent
        from app.services.agent import AgentService

        node_id = str(node.get("id") or "")
        node_data = node.get("data", {})
        config = node_data.get("agentConfig") or node_data.get("config", {})
        agent_id = config.get("agentId") or config.get("agent_id")
        if not agent_id:
            return ExecutionResult(error="validation_error")
        agent = await Agent.filter(id=agent_id).first()
        if not agent:
            return ExecutionResult(error="agent_not_found")

        message_source = config.get("messageSource")
        if message_source == "constant":
            message_template = config.get("messageConstantValue", "")
        elif message_source == "variable":
            message_template = config.get("messageVariableRef", "")
        else:
            message_template = config.get("message", "")
        message = await self._resolve_template(str(message_template or ""), context)

        mappings = (
            config.get("inputMappings")
            or config.get("parameterMappings")
            or config.get("context", [])
        )
        attachment_mappings = config.get("attachmentMappings") or []
        resolved = await self.resolve_inputs(context, mappings)
        resolved_attachments = await self.resolve_inputs(context, attachment_mappings)

        images: list[Any] = []
        files: list[Any] = []
        agent_context: dict[str, Any] = {}
        for mapping in mappings:
            name = mapping.get("name") if isinstance(mapping, dict) else None
            if not name or name not in resolved:
                continue
            value = resolved[name]
            value_type = (
                str(mapping.get("type", "string")).lower()
                if isinstance(mapping, dict)
                else "string"
            )
            values = value if isinstance(value, list) else [value]
            if value_type in {"image", "images"}:
                images.extend(item for item in values if item is not None)
            elif value_type in {"file", "files"}:
                files.extend(item for item in values if item is not None)
            else:
                agent_context[name] = value
        for mapping in attachment_mappings:
            name = mapping.get("name") if isinstance(mapping, dict) else None
            if not name or name not in resolved_attachments:
                continue
            value = resolved_attachments[name]
            values = value if isinstance(value, list) else [value]
            attachment_type = (
                str(mapping.get("attachmentType") or "").lower()
                if isinstance(mapping, dict)
                else ""
            )
            for item in values:
                if item is None:
                    continue
                if attachment_type in {"image", "images"} or self._is_image_attachment(
                    item
                ):
                    images.append(item)
                else:
                    files.append(item)

        try:
            agent_service = AgentService()
            user_locale = "en"
            if run.triggered_by_id:
                await run.fetch_related("triggered_by")
                if run.triggered_by:
                    user_locale = getattr(run.triggered_by, "locale", None) or "en"
            if (images or files) and not getattr(agent, "enable_attachments", False):
                return ExecutionResult(error="attachments_not_enabled")
            configured_turns = config.get("maxTurns")
            agent_turns = getattr(agent, "max_iterations", None)
            max_turns = (
                int(configured_turns or agent_turns or 10)
                if isinstance(configured_turns or agent_turns, int)
                else 10
            )
            output_var = str(config.get("outputVariable") or "response")
            outputs: dict[str, Any]
            if config.get("stream", True):
                response_text = ""
                tool_calls: list[Any] = []
                usage: dict[str, Any] = {}
                dialogue: list[dict[str, Any]] = []
                artifacts: list[Any] = []
                stream_manager = StreamManager(context.run_id)
                async for chunk in agent_service.chat_stream(
                    agent=agent,
                    message=message,
                    context=agent_context,
                    images=images or None,
                    files=files or None,
                    user_id=str(run.triggered_by_id) if run.triggered_by_id else None,
                    max_turns=max_turns,
                    user_locale=user_locale,
                ):
                    if isinstance(chunk, str):
                        response_text += chunk
                        await stream_manager.publish_token(node_id, chunk)
                    elif "tool_call" in chunk:
                        call_data = chunk["tool_call"]
                        tool_calls.append(call_data)
                        dialogue.append(
                            {"role": "assistant", "tool_calls": [call_data]}
                        )
                    elif "tool_result" in chunk:
                        tool_result = chunk["tool_result"]
                        dialogue.append({"role": "tool", **tool_result})
                        artifacts.extend(
                            self._extract_artifacts(tool_result.get("result"))
                        )
                    elif "usage" in chunk:
                        usage = chunk["usage"]
                    elif "dialogue" in chunk:
                        dialogue = chunk["dialogue"]
                        artifacts = chunk.get("artifacts") or []
                outputs = {
                    "response": response_text,
                    "toolCalls": tool_calls,
                    "usage": usage,
                    "dialogue": dialogue,
                    "artifacts": artifacts,
                }
            else:
                result = await agent_service.chat(
                    agent=agent,
                    message=message,
                    context=agent_context,
                    images=images or None,
                    files=files or None,
                    user_id=str(run.triggered_by_id) if run.triggered_by_id else None,
                    max_turns=max_turns,
                    user_locale=user_locale,
                )
                outputs = {
                    "response": result.get("response", ""),
                    "toolCalls": result.get("tool_calls", []),
                    "usage": result.get("usage", {}),
                    "dialogue": result.get("dialogue", []),
                    "artifacts": result.get("artifacts", []),
                }
            if output_var != "response":
                outputs[output_var] = outputs["response"]
            return ExecutionResult(outputs=outputs)
        except Exception as e:
            logger.exception("Agent execution error: %s", e)
            return ExecutionResult(error=translate_public_workflow_error(e))

    async def _resolve_template(
        self, template: str, context: "ExecutionContext"
    ) -> str:
        import re

        result = template
        for match in re.findall(r"\{\{([^}]+)\}\}", template):
            ref = f"{{{{{match}}}}}"
            value = await context.resolve_variable_ref(ref)
            if value is not None:
                result = result.replace(ref, str(value))
        return result

    @staticmethod
    def _is_image_attachment(value: Any) -> bool:
        """Recognize only the explicit image record used by Agent chat."""
        return isinstance(value, dict) and value.get("type") == "image_url"

    @staticmethod
    def _extract_artifacts(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, dict):
            return []
        artifacts: list[dict[str, Any]] = []
        for key in ("artifacts", "files"):
            items = value.get(key)
            if isinstance(items, list):
                artifacts.extend(item for item in items if isinstance(item, dict))
        nested = value.get("display_result")
        if isinstance(nested, dict):
            artifacts.extend(AgentNodeExecutor._extract_artifacts(nested))
        return artifacts

    def get_output_variables(self, config: dict) -> list[dict]:
        output_var = config.get("outputVariable", "response")
        variables = [
            {"name": "response", "type": "string"},
            {"name": "toolCalls", "type": "array"},
            {"name": "usage", "type": "object"},
            {"name": "dialogue", "type": "array"},
            {"name": "artifacts", "type": "array"},
        ]
        if output_var and output_var != "response":
            variables.insert(0, {"name": output_var, "type": "string"})
        return variables

    def get_output_specs(self, config: dict) -> list["NodeOutputDecl"]:
        return [
            NodeOutputDecl(name=item["name"], type=TypeSpec(kind=item["type"]))
            for item in self.get_output_variables(config)
        ]


@NodeExecutorRegistry.register("http_request")
class HTTPRequestNodeExecutor(NodeExecutor):
    """
    HTTP request node executor.

    Makes HTTP requests to external APIs.

    Node Config:
        {
            "method": "GET" | "POST" | "PUT" | "DELETE",
            "url": "https://api.example.com/{{path}}",
            "headers": {
                "Authorization": "Bearer {{token}}"
            },
            "body": {...},
            "timeout": 30
        }

    Outputs:
        {
            "statusCode": 200,
            "body": {...},
            "headers": {...}
        }
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute HTTP request node."""
        import httpx

        node_data = node.get("data", {})
        config = node_data.get("config", {})

        method = config.get("method", "GET").upper()
        url_template = config.get("url", "")
        headers_template = config.get("headers", {})
        body_template = config.get("body")
        timeout = config.get("timeout", 30)

        if not url_template:
            return ExecutionResult(error="tool_execution_failed")

        # Resolve templates
        url = await self._resolve_template(url_template, context)
        headers: dict[str, str] = {}
        for key, value in headers_template.items():
            headers[key] = await self._resolve_template(str(value), context)

        body: WorkflowValue | None = None
        if body_template:
            if isinstance(body_template, str):
                body = await self._resolve_template(body_template, context)
            else:
                # Resolve variables in body object
                body = await self._resolve_body(body_template, context)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=body if isinstance(body, dict) else None,
                    content=body if isinstance(body, str) else None,
                )

                # Try to parse JSON response
                try:
                    response_body = response.json()
                except json.JSONDecodeError:
                    response_body = response.text

                return ExecutionResult(
                    outputs={
                        "statusCode": response.status_code,
                        "body": response_body,
                        "headers": dict(response.headers),
                    }
                )

        except httpx.TimeoutException:
            return ExecutionResult(
                error=resolve_user_visible_error(
                    f"Request timed out after {timeout}s",
                    fallback_key="request_timeout",
                )
            )
        except Exception as e:
            logger.exception(f"HTTP request error: {e}")
            return ExecutionResult(error=resolve_user_visible_error(str(e)))

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

    async def _resolve_body(
        self,
        body: dict[str, Any],
        context: "ExecutionContext",
    ) -> dict[str, Any]:
        """Recursively resolve variables in body object."""
        result: dict[str, Any] = {}
        for key, value in body.items():
            if isinstance(value, str):
                result[key] = await self._resolve_template(value, context)
            elif isinstance(value, dict):
                result[key] = await self._resolve_body(value, context)
            elif isinstance(value, list):
                result[key] = [
                    await self._resolve_body(item, context)
                    if isinstance(item, dict)
                    else await self._resolve_template(str(item), context)
                    if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables."""
        return [
            {"name": "statusCode", "type": "number"},
            {"name": "body", "type": "any"},
            {"name": "headers", "type": "object"},
        ]

    def get_output_specs(self, config: dict) -> list["NodeOutputDecl"]:
        """Get output specs with TypeSpec for type inference."""
        return [
            NodeOutputDecl(name="statusCode", type=TypeSpec(kind="number")),
            NodeOutputDecl(name="body", type=TypeSpec(kind="any")),
            NodeOutputDecl(name="headers", type=TypeSpec(kind="object")),
        ]
