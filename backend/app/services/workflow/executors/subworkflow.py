"""
Sub-workflow node executor.

Handles nested workflow execution with depth tracking.
"""

from typing import TYPE_CHECKING
from uuid import UUID
import logging

from ..executor import NodeExecutor, NodeExecutorRegistry, ExecutionResult
from ..errors import MaxDepthExceededError

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

        node.get("id")
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
            return ExecutionResult(error="Sub-workflow ID not configured")

        # Check depth to prevent infinite recursion
        current_depth = run.depth if hasattr(run, "depth") else 0
        if current_depth >= MAX_DEPTH:
            raise MaxDepthExceededError(MAX_DEPTH)

        # Load sub-workflow
        sub_workflow = await Workflow.filter(id=workflow_id).first()
        if not sub_workflow:
            return ExecutionResult(error=f"Sub-workflow not found: {workflow_id}")

        # Convert frontend inputMappings format to resolve_inputs format
        # Frontend format: {name, type, required, source, variableRef, constantValue}
        # resolve_inputs format: {name, value} or {name, variableRef}
        converted_mappings = []
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
        inputs = {}
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
            sub_run_id = await orchestrator.run(
                workflow_id=UUID(workflow_id),
                inputs=inputs,
                user_id=run.triggered_by_id,
                team_id=None,  # Inherit from parent
                stream=False,  # Don't stream sub-workflow
            )

            # Get sub-workflow results
            sub_run = await WorkflowRunModel.filter(id=sub_run_id).first()
            if not sub_run:
                return ExecutionResult(error="Sub-workflow run not found")

            # Update sub-run with parent info
            sub_run.parent_run_id = run.id
            sub_run.root_run_id = run.root_run_id or run.id
            sub_run.depth = current_depth + 1
            await sub_run.save()

            # Check sub-workflow result
            if sub_run.status == "failed":
                if fail_on_error:
                    return ExecutionResult(
                        error=f"Sub-workflow failed: {sub_run.error_message}"
                    )
                else:
                    return ExecutionResult(
                        outputs={
                            "_status": "failed",
                            "_error": sub_run.error_message,
                            "_sub_run_id": str(sub_run_id),
                        }
                    )

            # Map outputs
            sub_outputs = sub_run.outputs or {}

            # Frontend uses outputVariable as a single output name that contains all sub-workflow outputs
            # If outputVariable is set, wrap all outputs under that key
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
            if fail_on_error:
                return ExecutionResult(error=f"Sub-workflow error: {str(e)}")
            else:
                return ExecutionResult(
                    outputs={
                        "_status": "error",
                        "_error": str(e),
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
        """Execute file to URL conversion."""
        import os
        import base64
        import mimetypes
        from app.core.config import settings

        node_data = node.get("data", {})
        config = node_data.get("config", {})

        input_var = config.get("inputVariable", "")
        input_type = config.get("inputType", "path")
        output_type = config.get("outputType", "url")
        config.get("expiresIn", 3600)

        # Get input value
        input_value = await context.resolve_variable_ref(input_var)
        if not input_value:
            return ExecutionResult(error="No input file provided")

        try:
            if input_type == "path":
                # Input is a file path
                file_path = str(input_value)

                if not os.path.exists(file_path):
                    return ExecutionResult(error=f"File not found: {file_path}")

                filename = os.path.basename(file_path)
                mime_type, _ = mimetypes.guess_type(file_path)
                file_size = os.path.getsize(file_path)

                if output_type == "base64":
                    with open(file_path, "rb") as f:
                        content = base64.b64encode(f.read()).decode()
                    return ExecutionResult(
                        outputs={
                            "content": content,
                            "filename": filename,
                            "mimeType": mime_type or "application/octet-stream",
                            "size": file_size,
                        }
                    )
                else:
                    # Generate URL (simplified - in production use signed URLs)
                    relative_path = file_path.replace(
                        str(settings.UPLOAD_DIR), ""
                    ).lstrip("/")
                    url = f"{settings.BASE_URL}/uploads/{relative_path}"

                    return ExecutionResult(
                        outputs={
                            "url": url,
                            "filename": filename,
                            "mimeType": mime_type or "application/octet-stream",
                            "size": file_size,
                        }
                    )

            elif input_type == "base64":
                # Input is base64 content
                content = str(input_value)

                # Decode to get size
                try:
                    decoded = base64.b64decode(content)
                    file_size = len(decoded)
                except Exception:
                    file_size = len(content)

                if output_type == "base64":
                    return ExecutionResult(
                        outputs={
                            "content": content,
                            "size": file_size,
                        }
                    )
                else:
                    # Would need to save to storage and generate URL
                    # This is a simplified implementation
                    return ExecutionResult(
                        error="Converting base64 to URL requires file storage (not implemented)"
                    )

            else:
                return ExecutionResult(error=f"Unknown input type: {input_type}")

        except Exception as e:
            logger.exception(f"File conversion error: {e}")
            return ExecutionResult(error=f"File conversion failed: {str(e)}")

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables."""
        output_type = config.get("outputType", "url")
        if output_type == "url":
            return [
                {"name": "url", "type": "string"},
                {"name": "filename", "type": "string"},
                {"name": "mimeType", "type": "string"},
                {"name": "size", "type": "number"},
            ]
        else:
            return [
                {"name": "content", "type": "string"},
                {"name": "filename", "type": "string"},
                {"name": "mimeType", "type": "string"},
                {"name": "size", "type": "number"},
            ]
