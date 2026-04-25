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
    """
    Agent node executor.

    Invokes an AI agent with a message and optional context.

    Node Config:
        {
            "agentId": "uuid",
            "message": "{{start.query}}",
            "context": [
                {"name": "history", "variableRef": "{{chat.history}}"}
            ],
            "stream": true,
            "maxTurns": 10
        }

    Outputs:
        {
            "response": "Agent's response",
            "toolCalls": [...],
            "usage": {...}
        }
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute agent node."""
        from app.models.agent import Agent
        from app.services.agent import AgentService

        node_id = str(node.get("id") or "")
        node_data = node.get("data", {})
        # Try agentConfig first (frontend structure), then fall back to config
        config = node_data.get("agentConfig") or node_data.get("config", {})

        agent_id = config.get("agentId")
        message_template = config.get("message", "")
        context_mappings = config.get("context", [])
        should_stream = config.get("stream", True)
        max_turns = config.get("maxTurns", 10)

        if not agent_id:
            return ExecutionResult(error="validation_error")

        # Load agent
        agent = await Agent.filter(id=agent_id).first()
        if not agent:
            return ExecutionResult(error="agent_not_found")

        # Resolve message
        message = await self._resolve_template(message_template, context)

        # Resolve context
        agent_context = await self.resolve_inputs(context, context_mappings)

        try:
            agent_service = AgentService()

            if should_stream:
                # Streaming mode
                response_text = ""
                tool_calls = []
                usage = {}
                stream_manager = StreamManager(context.run_id)

                async for chunk in agent_service.chat_stream(
                    agent=agent,
                    message=message,
                    context=agent_context,
                    user_id=str(run.triggered_by_id) if run.triggered_by_id else None,
                    max_turns=max_turns,
                ):
                    if isinstance(chunk, dict):
                        if "tool_call" in chunk:
                            tool_calls.append(chunk["tool_call"])
                        if "usage" in chunk:
                            usage = chunk["usage"]
                    else:
                        response_text += chunk
                        await stream_manager.publish_token(node_id, chunk)

                return ExecutionResult(
                    outputs={
                        "response": response_text,
                        "toolCalls": tool_calls,
                        "usage": usage,
                    }
                )
            else:
                # Non-streaming mode
                result = await agent_service.chat(
                    agent=agent,
                    message=message,
                    context=agent_context,
                    user_id=str(run.triggered_by_id) if run.triggered_by_id else None,
                    max_turns=max_turns,
                )

                return ExecutionResult(
                    outputs={
                        "response": result.get("response", ""),
                        "toolCalls": result.get("tool_calls", []),
                        "usage": result.get("usage", {}),
                    }
                )

        except Exception as e:
            logger.exception(f"Agent execution error: {e}")
            return ExecutionResult(error=translate_public_workflow_error(e))

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
        """Get output variables."""
        return [
            {"name": "response", "type": "string"},
            {"name": "toolCalls", "type": "array"},
            {"name": "usage", "type": "object"},
        ]

    def get_output_specs(self, config: dict) -> list["NodeOutputDecl"]:
        """Get output specs with TypeSpec for type inference."""
        return [
            NodeOutputDecl(name="response", type=TypeSpec(kind="string")),
            NodeOutputDecl(name="toolCalls", type=TypeSpec(kind="array")),
            NodeOutputDecl(name="usage", type=TypeSpec(kind="object")),
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
            return ExecutionResult(
                error=resolve_user_visible_error(str(e))
            )

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
