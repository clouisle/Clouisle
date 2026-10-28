"""
Tool and agent node executors.

Handles external tool calls and agent invocations.
"""

import asyncio
import json
import logging
import math
import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.core.network_security import (
    get_ssrf_allowed_targets,
    validate_external_http_url,
)
from app.schemas.response import BusinessError
from app.services.error_messages import resolve_user_visible_error

from ..executor import NodeExecutor, NodeExecutorRegistry, ExecutionResult
from ..stream import StreamManager
from ..errors import WorkflowError, translate_public_workflow_error
from ..types import NodeOutputDecl, TypeSpec, WorkflowValue

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from ..context import ExecutionContext

logger = logging.getLogger(__name__)


def _first_configured(config: dict[str, Any], *names: str) -> Any:
    """First non-empty value among the accepted field spellings."""
    for name in names:
        value = config.get(name)
        if value is not None and value != "":
            return value
    return None


def _optional_uuid(value: Any) -> tuple[UUID | None, bool]:
    """Parse an optional UUID; the flag is False when a value is malformed."""
    if value is None or value == "":
        return None, True
    try:
        return UUID(str(value)), True
    except (TypeError, ValueError, AttributeError):
        return None, False


def _error_result(error: str, output_var: str, start_time: float) -> ExecutionResult:
    """Node failure with the same output shape as the generic error path."""
    from app.core.i18n import t

    duration_ms = int((time.time() - start_time) * 1000)
    public_error = t(error)
    outputs: dict[str, Any] = {
        "result": None,
        "status": "error",
        "error": public_error,
        "executionTime": duration_ms,
    }
    if output_var and output_var != "result":
        outputs[output_var] = None
    return ExecutionResult(outputs=outputs, error=error)


async def _cancel_unexecuted(execution_id: UUID) -> None:
    """Cancel a pending approval request that no run will ever resume."""
    from app.schemas.tool_approval import ToolExecutionCancelReason
    from app.services import tool_approvals

    try:
        await tool_approvals.cancel_execution(
            execution_id, reason=ToolExecutionCancelReason.CANCELLED
        )
    except Exception:
        logger.warning(
            "Failed to cancel unexecuted tool execution %s",
            execution_id,
            exc_info=True,
        )


def _convert_tool_input(value: WorkflowValue, parameter_type: str) -> WorkflowValue:
    """Convert text mappings without truncating or changing native typed values."""
    expected = {
        "string": (str,),
        "integer": (int,),
        "number": (int, float),
        "boolean": (bool,),
        "array": (list,),
        "object": (dict,),
    }.get(parameter_type)
    if expected is None:
        return value
    try:
        if isinstance(value, str):
            if parameter_type == "integer":
                value = int(value)
            elif parameter_type == "number":
                value = float(value)
            elif parameter_type in {"boolean", "array", "object"}:
                value = json.loads(value)
        if type(value) not in expected:
            raise ValueError
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError
    except (ValueError, TypeError, OverflowError) as exc:
        raise WorkflowError(
            "invalid_tool_arguments", msg_key="invalid_tool_arguments"
        ) from exc
    return value


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
        from app.models.user import User
        from app.models.workflow import Workflow
        from app.schemas.tool_approval import ExecutionRunKind
        from app.services.tool import ToolExecutor
        from app.services.tool_execution import PendingToolApproval, ToolCallContext

        from ..execution_origin import read_run_origin
        from ..tool_approval_resume import (
            approval_deadline_passed,
            find_execution_for_token,
            terminal_execution_error,
            token_for_attempt,
        )

        tool_executor = ToolExecutor()

        node_id = str(node.get("id") or "")
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

        # Stored connection references: canonical snake_case fields with the
        # camelCase names the workflow node editor persists.
        connection_mode = _first_configured(config, "connectionMode", "connection_mode")
        connection_id, connection_id_valid = _optional_uuid(
            _first_configured(config, "connectionId", "connection_id")
        )
        if not connection_id_valid:
            return ExecutionResult(error="tool_connection_invalid")

        # MCP operations are keyed by the original server-side tool name; a
        # model-facing alias must never become the policy key.
        raw_operation = _first_configured(config, "mcpToolName", "mcp_tool_name")
        if raw_operation is not None and (
            not isinstance(raw_operation, str) or not raw_operation.strip()
        ):
            return ExecutionResult(error="invalid_tool_arguments")
        operation = raw_operation.strip() if isinstance(raw_operation, str) else None

        # Resolve inputs
        inputs = await self.resolve_inputs(context, input_mappings)
        workflow_team_id = None
        if run.workflow_id:
            workflow = await Workflow.filter(id=run.workflow_id).only("team_id").first()
            workflow_team_id = workflow.team_id if workflow else None

        start_time = time.time()

        try:
            for mapping in input_mappings:
                name = mapping.get("name")
                if name in inputs:
                    inputs[name] = _convert_tool_input(
                        inputs[name], mapping.get("type", "")
                    )

            # Load the tool with the workflow team's boundary before any
            # identity/approval work: an inaccessible tool is not distinguishable
            # from a missing one and leaks no approval state.
            tool = None
            if not (tool_type == "builtin" and tool_name):
                from app.models.tool import ToolShare, ToolVisibility

                tool = await Tool.filter(id=tool_id).first()
                if not tool:
                    return ExecutionResult(error="tool_not_found")

                if (
                    workflow_team_id
                    and tool.team_id
                    and tool.team_id != workflow_team_id
                ):
                    has_share = await ToolShare.filter(
                        tool_id=tool.id,
                        shared_with_team_id=workflow_team_id,
                    ).exists()
                    if not has_share or tool.visibility == ToolVisibility.PRIVATE:
                        return ExecutionResult(error="tool_not_found")

                if (
                    tool.visibility == ToolVisibility.PRIVATE
                    and run.triggered_by_id
                    and tool.created_by_id
                    and str(run.triggered_by_id) != str(tool.created_by_id)
                ):
                    return ExecutionResult(error="tool_not_found")

                from app.models.tool import ToolType

                tool_type_value = getattr(tool.type, "value", tool.type)
                if tool_type_value == ToolType.MCP.value and operation is None:
                    # An MCP node without its original internal tool name would
                    # execute (and policy-key) the wrong operation.
                    return ExecutionResult(error="invalid_tool_arguments")

            # A workflow is non-interactive for approval gates; a manual run
            # may still auto-select the triggering user's personal connection.
            # The identity, team and stable entrypoint reference are built here
            # and never taken from node inputs, so a renamed alias cannot
            # redirect the execution.
            actor = (
                await User.get_or_none(id=run.triggered_by_id)
                if run.triggered_by_id
                else None
            )
            if actor is None or workflow_team_id is None or not run.workflow_id:
                return _error_result("user_context_required", output_var, start_time)

            # Provenance comes from the trusted creation route, never from the
            # workflow's configured trigger: a manual run of a cron workflow is
            # still the workflow surface, and an API-key/embed run must bind its
            # grants to that key/surface rather than to the workflow.
            origin = read_run_origin(run)
            if origin is None:
                return _error_result("user_context_required", output_var, start_time)
            # Stable per-attempt call id: the deferred approval execution is
            # found again (never recreated) on retry and on resume.
            call_token = await token_for_attempt(run, node_id)
            call_context = ToolCallContext(
                actor=actor,
                team_id=workflow_team_id,
                entrypoint=origin.entrypoint,
                entrypoint_id=origin.entrypoint_id,
                run_kind=ExecutionRunKind.WORKFLOW,
                run_id=run.id,
                tool_call_id=call_token,
                connection_mode=(
                    str(connection_mode) if connection_mode is not None else None
                ),
                connection_id=connection_id,
                interactive=False,
                require_approval=False,
            )

            # A parked call only reaches this point again after an approval
            # decision: a terminal decision fails the node exactly once and a
            # miss (expiry sweep not yet run) is expired here, never re-parked.
            previous = await find_execution_for_token(run, call_token)
            if previous is not None:
                terminal_error = terminal_execution_error(previous)
                if terminal_error is not None:
                    return _error_result(terminal_error, output_var, start_time)
                from app.services import tool_approvals
                from app.schemas.tool_approval import ToolExecutionStatus

                if (
                    previous.status == ToolExecutionStatus.AWAITING_APPROVAL
                    and approval_deadline_passed(previous)
                ):
                    await tool_approvals.expire_execution(previous.id)
                    return _error_result(
                        "tool_approval_expired", output_var, start_time
                    )

            # Execute through the single tool execution boundary.
            if tool is None:
                result = await tool_executor.execute_builtin_tool(
                    tool_name=tool_name,
                    arguments=inputs,
                    team_id=workflow_team_id,
                    context=call_context,
                    workflow_run_id=run.id,
                    operation=tool_name,
                )
            else:
                result = await tool_executor.execute(
                    tool=tool,
                    arguments=inputs,
                    user_id=str(run.triggered_by_id) if run.triggered_by_id else None,
                    team_id=workflow_team_id,
                    context=call_context,
                    operation=operation or tool.name,
                )
            if isinstance(result, PendingToolApproval):
                # Workflows never wait for tool approval. This defensive branch
                # covers a boundary/configuration regression: drop the
                # unexecuted request and fail the node instead of turning the
                # workflow into an approval surface.
                await _cancel_unexecuted(result.execution_id)
                return _error_result("tool_approval_cancelled", output_var, start_time)

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
                str(mapping.get("attachmentType") or mapping.get("type") or "").lower()
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
            from app.core.i18n import resolve_language
            from app.services.tool_context import (
                RuntimeToolIdentity,
                tool_identity_scope,
            )
            from app.schemas.tool_approval import ExecutionRunKind

            from ..execution_origin import read_run_origin

            # Delegated tool calls are attributed to the workflow run and its
            # real entrypoint. A pending approval cannot park this blocking
            # AgentService call, so the agent layer fails it closed instead of
            # returning an interaction object to a loop with no pause. The node
            # has no surface for choosing a connection, hence non-interactive
            # even for a manual workflow run.
            origin = read_run_origin(run)
            if origin is None:
                return ExecutionResult(error="user_context_required")
            tool_identity = RuntimeToolIdentity(
                run_id=run.id,
                run_kind=ExecutionRunKind.WORKFLOW.value,
                entrypoint=origin.entrypoint.value,
                entrypoint_id=origin.entrypoint_id,
                interactive=False,
                tool_call_prefix=f"workflow-agent:{run.id}:{node_id}",
            )

            triggered_user_locale = None
            if run.triggered_by_id:
                await run.fetch_related("triggered_by")
                if run.triggered_by:
                    triggered_user_locale = getattr(run.triggered_by, "locale", None)
            user_locale = await resolve_language(triggered_user_locale)
            if (images or files) and not getattr(agent, "enable_attachments", False):
                return ExecutionResult(error="attachments_not_enabled")
            configured_turns = config.get("maxTurns")
            agent_turns = getattr(agent, "max_iterations", None)
            candidate_turns = configured_turns or agent_turns or 10
            try:
                max_turns = (
                    int(candidate_turns)
                    if isinstance(candidate_turns, (int, str))
                    else 10
                )
            except (TypeError, ValueError, OverflowError):
                max_turns = 10
            output_var = str(config.get("outputVariable") or "response")
            outputs: dict[str, Any]
            if config.get("stream", True):
                response_text = ""
                tool_calls: list[Any] = []
                usage: dict[str, Any] = {}
                dialogue: list[dict[str, Any]] = []
                artifacts: list[Any] = []
                stream_manager = StreamManager(context.run_id)
                with tool_identity_scope(tool_identity):
                    async for chunk in agent_service.chat_stream(
                        agent=agent,
                        message=message,
                        context=agent_context,
                        images=images or None,
                        files=files or None,
                        user_id=str(run.triggered_by_id)
                        if run.triggered_by_id
                        else None,
                        workflow_run_id=run.id,
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
                with tool_identity_scope(tool_identity):
                    result = await agent_service.chat(
                        agent=agent,
                        message=message,
                        context=agent_context,
                        images=images or None,
                        files=files or None,
                        user_id=str(run.triggered_by_id)
                        if run.triggered_by_id
                        else None,
                        workflow_run_id=run.id,
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
            if output_var not in outputs:
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
        if output_var and all(variable["name"] != output_var for variable in variables):
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
        try:
            allowlist = await get_ssrf_allowed_targets()

            def _validate():
                try:
                    return validate_external_http_url(url, allowlist=allowlist)
                except TypeError:
                    return validate_external_http_url(url)

            validated_url = await asyncio.to_thread(_validate)
        except BusinessError as exc:
            return ExecutionResult(error=resolve_user_visible_error(str(exc)))
        except ValueError as exc:
            return ExecutionResult(error=resolve_user_visible_error(str(exc)))
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
                    url=validated_url,
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
