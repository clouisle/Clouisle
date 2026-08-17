"""
Sub-workflow node executor.

Handles nested workflow execution with depth tracking.
"""

from typing import TYPE_CHECKING, cast
from uuid import UUID
import logging
import mimetypes
import os

from app.services import upload_gateway
from ..executor import NodeExecutor, NodeExecutorRegistry, ExecutionResult
from ..types import NodeOutputDecl, TypeSpec, WorkflowValue
from ..errors import MaxDepthExceededError
from ..errors import translate_public_workflow_error

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from ..context import ExecutionContext

logger = logging.getLogger(__name__)

# Maximum nesting depth
MAX_DEPTH = 5


@NodeExecutorRegistry.register("sub_workflow")
class SubWorkflowNodeExecutor(NodeExecutor):
    """
    Sub-workflow node executor.

    Executes another workflow as a nested call.

    Node Config:
        {
            "workflowId": "uuid",
            "inputs": [
                {"name": "query", "variableRef": "{{start.query}}"}
            ],
            "outputMapping": {
                "result": "answer"
            },
            "timeout": 300,
            "failOnError": true
        }

    Outputs:
        Whatever the sub-workflow outputs, mapped according to outputMapping
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute sub-workflow node."""
        from app.models.workflow import Workflow, WorkflowRun as WorkflowRunModel
        from ..orchestrator import WorkflowOrchestrator

        node_data = node.get("data", {})
        # Try subWorkflowConfig first (frontend structure), then fall back to config
        config = node_data.get("subWorkflowConfig") or node_data.get("config", {})

        workflow_id = config.get("workflowId")
        # Frontend uses inputMappings, backend fallback uses inputs
        input_mappings_raw = config.get("inputMappings") or config.get("inputs", [])
        output_mapping = config.get("outputMapping", {})
        output_variable = config.get("outputVariable", "result")
        timeout = config.get("timeout", 300)
        fail_on_error = config.get("failOnError", True)

        if not workflow_id:
            return ExecutionResult(error="validation_error")

        # Check depth to prevent infinite recursion
        current_depth = run.depth if hasattr(run, "depth") else 0
        if current_depth >= MAX_DEPTH:
            raise MaxDepthExceededError(MAX_DEPTH, current_depth)

        # Load sub-workflow
        sub_workflow = await Workflow.filter(id=workflow_id).first()
        if not sub_workflow:
            return ExecutionResult(error="workflow_not_found")

        # Convert frontend inputMappings format to resolve_inputs format
        # Frontend format: {name, type, required, source, variableRef, constantValue}
        # resolve_inputs format: {name, value} or {name, variableRef}
        converted_mappings: list[dict[str, str]] = []
        for mapping in input_mappings_raw:
            name = mapping.get("name", "")
            source = mapping.get("source", "variable")

            if source == "variable":
                var_ref = mapping.get("variableRef", "")
                converted_mappings.append({"name": name, "value": var_ref})
            elif source == "constant":
                const_value = mapping.get("constantValue", "")
                # For constants, pass the value directly (no need to resolve)
                converted_mappings.append({"name": name, "constantValue": const_value})
            else:
                # Fallback to old format compatibility
                if "value" in mapping or "variableRef" in mapping:
                    converted_mappings.append(mapping)

        # Resolve inputs
        inputs: dict[str, WorkflowValue] = {}
        for mapping in converted_mappings:
            name = mapping.get("name", "")
            if not name:
                continue

            if "constantValue" in mapping:
                inputs[name] = mapping["constantValue"]
            else:
                # Use value or variableRef field
                ref = mapping.get("value") or mapping.get("variableRef", "")
                if ref:
                    inputs[name] = await context.resolve_variable_ref(ref)

        try:
            # Create sub-orchestrator
            orchestrator = WorkflowOrchestrator(timeout=timeout)

            # Run sub-workflow
            triggered_by_id = run.triggered_by_id
            if triggered_by_id is None:
                return ExecutionResult(error="validation_error")

            sub_run_id = await orchestrator.run(
                workflow_id=UUID(workflow_id),
                inputs=inputs,
                user_id=triggered_by_id,
                team_id=None,  # Inherit from parent
                stream=False,  # Don't stream sub-workflow
            )

            # Get sub-workflow results
            sub_run = await WorkflowRunModel.filter(id=sub_run_id).first()
            if sub_run is None:
                return ExecutionResult(error="workflow_run_not_found")

            # Update sub-run with parent info
            sub_run.parent_run_id = run.id
            sub_run.root_run_id = run.root_run_id or run.id
            sub_run.depth = current_depth + 1
            await sub_run.save()

            # Check sub-workflow result
            if sub_run.status == "failed":
                public_error = translate_public_workflow_error(sub_run.error_message)
                if fail_on_error:
                    return ExecutionResult(error=public_error)
                else:
                    return ExecutionResult(
                        outputs={
                            "_status": "failed",
                            "_error": public_error,
                            "_sub_run_id": str(sub_run_id),
                        }
                    )

            # Map outputs
            sub_outputs = sub_run.outputs or {}

            # Frontend uses outputVariable as a single output name that contains all sub-workflow outputs
            # If outputVariable is set, wrap all outputs under that key
            outputs: dict[str, WorkflowValue]
            if output_variable:
                outputs = {
                    output_variable: sub_outputs,
                    "_sub_run_id": str(sub_run_id),
                }
            elif output_mapping:
                # Legacy: use output_mapping if available
                outputs = {"_sub_run_id": str(sub_run_id)}
                for local_name, sub_name in output_mapping.items():
                    outputs[local_name] = sub_outputs.get(sub_name)
            else:
                # Pass through all outputs
                outputs = {"_sub_run_id": str(sub_run_id)}
                outputs.update(sub_outputs)

            return ExecutionResult(outputs=outputs)

        except MaxDepthExceededError:
            raise
        except Exception as e:
            logger.exception(f"Sub-workflow execution error: {e}")
            public_error = translate_public_workflow_error(e)
            if fail_on_error:
                return ExecutionResult(error=public_error)
            else:
                return ExecutionResult(
                    outputs={
                        "_status": "error",
                        "_error": public_error,
                    }
                )

    async def validate_config(self, config: dict) -> list[str]:
        """Validate sub-workflow configuration."""
        errors = []

        if not config.get("workflowId"):
            errors.append("Sub-workflow ID is required")

        return errors

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables from config."""
        output_mapping = config.get("outputMapping", {})
        if output_mapping:
            return [{"name": name, "type": "any"} for name in output_mapping.keys()]
        return [{"name": "result", "type": "any"}]

    def get_output_specs(self, config: dict) -> list["NodeOutputDecl"]:
        """Get output specs with TypeSpec for type inference."""
        output_mapping = config.get("outputMapping", {})
        if output_mapping:
            return [
                NodeOutputDecl(name=name, type=TypeSpec(kind="any"))
                for name in output_mapping.keys()
            ]
        return [NodeOutputDecl(name="result", type=TypeSpec(kind="any"))]


@NodeExecutorRegistry.register("file_to_url")
class FileToURLNodeExecutor(NodeExecutor):
    """
    File to URL node executor.

    Converts file content or path to a publicly accessible URL.

    Node Config:
        {
            "inputVariable": "{{upload.file}}",
            "inputType": "path" | "base64" | "content",
            "outputType": "url" | "base64",
            "expiresIn": 3600
        }

    Outputs:
        {
            "url": "https://...",
            "filename": "document.pdf",
            "mimeType": "application/pdf",
            "size": 1024
        }
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute file to URL conversion.

        Workflow file parameters are uploaded when the run starts; the
        variable value is already the upload URL (frontend stores
        ``result.url``, a list of URLs for multi-file parameters). This node
        therefore never reads file bytes — it resolves the file variable(s)
        and returns their URL(s), optionally absolutized. No local filesystem
        access, so it runs on any worker without the uploads volume.
        """
        import base64
        import mimetypes
        from urllib.parse import urlparse

        from app.core.config import settings

        node_data = node.get("data", {})
        legacy_config = node_data.get("config", {})
        config = node_data.get("fileToUrlConfig", legacy_config)

        inputs = config.get("inputs", [])
        ensure_absolute = bool(config.get("ensureAbsolute", True))
        input_var = config.get("inputVariable", "") or legacy_config.get(
            "inputVariable", ""
        )
        input_type = config.get("inputType", "path") or legacy_config.get(
            "inputType", "path"
        )
        output_type = config.get("outputType", "url") or legacy_config.get(
            "outputType", "url"
        )

        try:
            # 绝对化兜底：优先请求来源（run/debug 端点传入），其次 PUBLIC_API_URL
            public_base = context.get_public_base_url() or str(
                getattr(settings, "PUBLIC_API_URL", "") or ""
            ).rstrip("/")

            if inputs:
                outputs: dict[str, WorkflowValue] = {}
                for item in inputs:
                    name = item.get("name", "")
                    ref = item.get("sourceVariable", "")
                    if not name or not ref:
                        continue
                    value = await context.resolve_variable_ref(ref)
                    if not self._has_file_value(value):
                        return ExecutionResult(error="validation_error")
                    outputs[name] = cast(
                        WorkflowValue,
                        self._normalize_urls(value, ensure_absolute, public_base),
                    )
                if not outputs:
                    return ExecutionResult(error="validation_error")
                return ExecutionResult(outputs=outputs)

            # Legacy base64/content modes — pure string handling, no filesystem.
            if input_type == "content":
                return ExecutionResult(error="validation_error")
            if input_type == "base64":
                value = await context.resolve_variable_ref(input_var or "")
                if value is None:
                    return ExecutionResult(error="validation_error")
                content = str(value)
                try:
                    decoded = base64.b64decode(content)
                    file_size = len(decoded)
                except Exception:
                    file_size = len(content)
                if output_type == "base64":
                    return ExecutionResult(
                        outputs={"content": content, "size": file_size}
                    )
                return ExecutionResult(error="workflow_execution_error")

            if not input_var:
                return ExecutionResult(error="validation_error")

            value = await context.resolve_variable_ref(input_var)
            if not self._has_file_value(value):
                return ExecutionResult(error="validation_error")

            if input_type == "path" and output_type == "base64":
                return await self._legacy_path_to_base64(value, run)

            converted = self._normalize_urls(value, ensure_absolute, public_base)
            if isinstance(converted, list):
                first = str(converted[0]) if converted else ""
                filename = os.path.basename(urlparse(first).path) or "file"
                mime_type, _ = mimetypes.guess_type(filename)
                return ExecutionResult(
                    outputs={
                        "urls": cast(WorkflowValue, converted),
                        "filename": filename,
                        "mimeType": mime_type or "application/octet-stream",
                    }
                )
            filename = os.path.basename(urlparse(converted).path) or "file"
            mime_type, _ = mimetypes.guess_type(filename)
            return ExecutionResult(
                outputs={
                    "url": converted,
                    "filename": filename,
                    "mimeType": mime_type or "application/octet-stream",
                    "size": 0,
                }
            )
        except Exception as e:
            logger.exception(f"File conversion error: {e}")
            return ExecutionResult(error=translate_public_workflow_error(e))

    @staticmethod
    def _has_file_value(value: WorkflowValue) -> bool:
        if isinstance(value, list):
            return bool(value) and all(
                isinstance(item, str) and item.strip() for item in value
            )
        return isinstance(value, str) and bool(value.strip())

    @staticmethod
    async def _legacy_path_to_base64(
        value: WorkflowValue, run: "WorkflowRun"
    ) -> ExecutionResult:
        """Read a legacy uploaded path through api, never from worker disk."""
        import base64
        from pathlib import PurePosixPath
        from urllib.parse import unquote, urlsplit

        if not isinstance(value, str):
            return ExecutionResult(error="validation_error")
        raw_path = unquote(urlsplit(value).path or value)
        marker = "/api/v1/upload/files/"
        if marker in raw_path:
            storage_key = raw_path.split(marker, 1)[1]
        elif "/uploads/" in raw_path:
            storage_key = raw_path.split("/uploads/", 1)[1]
        elif raw_path.startswith("documents/"):
            storage_key = raw_path
        else:
            return ExecutionResult(error="workflow_execution_error")
        key_path = PurePosixPath(storage_key)
        if key_path.is_absolute() or not key_path.parts or ".." in key_path.parts:
            return ExecutionResult(error="validation_error")

        if len(key_path.parts) > 1 and key_path.parts[0] == "documents":
            try:
                kb_id = UUID(key_path.parts[1])
            except ValueError:
                return ExecutionResult(error="not_found")
            else:
                from app.models.knowledge_base import KnowledgeBase
                from app.models.workflow import Workflow

                workflow_id = getattr(run, "workflow_id", None)
                workflow = await Workflow.filter(id=workflow_id).only("team_id").first()
                if not workflow:
                    return ExecutionResult(error="not_found")
                kb = await KnowledgeBase.filter(
                    id=kb_id, team_id=workflow.team_id
                ).first()
                if not kb:
                    return ExecutionResult(error="not_found")

        content = await upload_gateway.read(key_path.as_posix())

        filename = os.path.basename(raw_path) or "file"
        mime_type, _ = mimetypes.guess_type(filename)
        return ExecutionResult(
            outputs={
                "content": base64.b64encode(content).decode("ascii"),
                "filename": filename,
                "mimeType": mime_type or "application/octet-stream",
                "size": len(content),
            }
        )

    @staticmethod
    def _normalize_urls(
        value: WorkflowValue, ensure_absolute: bool, base_url: str
    ) -> str | list[str]:
        """Normalize a file variable value (URL or URL list) without reading files."""

        def _absolutize(url: str) -> str:
            url = url.strip()
            if not ensure_absolute or url.startswith(("http://", "https://")):
                return url
            if not base_url:
                return url
            return f"{base_url}{url if url.startswith('/') else '/' + url}"

        if isinstance(value, list):
            return [_absolutize(v) for v in value if isinstance(v, str) and v.strip()]
        if isinstance(value, str) and value.strip():
            return _absolutize(value)
        return _absolutize(str(value))

    @staticmethod
    def _configured_input_names(config: dict) -> list[str]:
        inputs = config.get("inputs", [])
        if not isinstance(inputs, list):
            return []
        return [
            name
            for item in inputs
            if isinstance(item, dict)
            and isinstance((name := item.get("name")), str)
            and name
        ]

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables."""
        input_names = self._configured_input_names(config)
        if input_names:
            return [{"name": name, "type": "any"} for name in input_names]

        output_type = config.get("outputType", "url")
        if output_type == "url":
            return [
                {"name": "url", "type": "string"},
                {"name": "urls", "type": "array"},
                {"name": "filename", "type": "string"},
                {"name": "mimeType", "type": "string"},
                {"name": "size", "type": "number"},
            ]
        return [
            {"name": "content", "type": "string"},
            {"name": "filename", "type": "string"},
            {"name": "mimeType", "type": "string"},
            {"name": "size", "type": "number"},
        ]

    def get_output_specs(self, config: dict) -> list["NodeOutputDecl"]:
        """Get output specs with TypeSpec for type inference."""
        input_names = self._configured_input_names(config)
        if input_names:
            return [
                NodeOutputDecl(name=name, type=TypeSpec(kind="any"))
                for name in input_names
            ]

        output_type = config.get("outputType", "url")
        specs = [
            NodeOutputDecl(name="filename", type=TypeSpec(kind="string")),
            NodeOutputDecl(name="mimeType", type=TypeSpec(kind="string")),
            NodeOutputDecl(name="size", type=TypeSpec(kind="number")),
        ]
        if output_type == "url":
            specs.insert(0, NodeOutputDecl(name="url", type=TypeSpec(kind="string")))
            specs.insert(
                1,
                NodeOutputDecl(
                    name="urls",
                    type=TypeSpec(
                        kind="array",
                        item=TypeSpec(kind="string"),
                    ),
                ),
            )
        else:
            specs.insert(
                0, NodeOutputDecl(name="content", type=TypeSpec(kind="string"))
            )
        return specs
