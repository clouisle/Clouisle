"""
Code node executor.

Executes Python/JavaScript code snippets within a sandboxed environment.
Uses subprocess isolation for security.
"""

from typing import TYPE_CHECKING
import logging

from ..executor import NodeExecutor, NodeExecutorRegistry, ExecutionResult
from ..errors import translate_public_workflow_error
from app.core.i18n import t
from app.services.sandbox.compiler import compile_code_config_job
from app.services.sandbox.gateway import sandbox_gateway
from app.services.sandbox.models import SandboxJobSource

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from ..context import ExecutionContext

logger = logging.getLogger(__name__)


# Maximum execution time for code (seconds)
CODE_TIMEOUT = 30


@NodeExecutorRegistry.register("code")
class CodeNodeExecutor(NodeExecutor):
    """
    Code node executor.

    Executes Python or JavaScript code with input variables and returns output.

    Node Config:
        {
            "language": "python",  // or "javascript"
            "code": "def main(inputs):\\n    return {'result': inputs['x'] * 2}",
            "inputs": [
                {"name": "x", "variableRef": "{{start.number}}"}
            ],
            "outputs": [
                {"name": "result", "type": "number"}
            ]
        }

    Python code must define a `main(inputs)` function that:
    - Takes a dict of input variables (available as `inputs`)
    - Returns a dict of output variables

    JavaScript code must define a `main(params)` function that:
    - Takes an object with input variables
    - Returns an object with output variables

    Outputs:
        Whatever the main() function returns
    """

    def __init__(self):
        pass

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute code node."""
        node_data = node.get("data", {})
        # Try codeConfig first (frontend structure), then fall back to config
        config = node_data.get("codeConfig") or node_data.get("config", {})

        logger.debug(f"Code node config: {config}")

        language = config.get("language", "python")
        code = config.get("code", "")
        input_mappings = config.get("inputs", [])

        logger.debug(f"Code node inputs: {input_mappings}")

        if not code:
            return ExecutionResult(error="tool_code_not_defined")

        try:
            # Resolve input variables
            inputs = await self.resolve_inputs(context, input_mappings)

            logger.info(f"Code node resolved inputs: {inputs}")

            # Prepare code based on language
            if language == "python":
                # Python code should define main(inputs) function
                wrapped_code = self._wrap_python_code(code)
            elif language == "javascript":
                # JavaScript code should define main(params) function
                wrapped_code = self._wrap_javascript_code(code)
            else:
                return ExecutionResult(
                    error=t("unsupported_code_execution_language", language=language)
                )

            job = compile_code_config_job(
                code_config={
                    "language": language,
                    "code": wrapped_code,
                },
                params=inputs,
                timeout=CODE_TIMEOUT,
                source=SandboxJobSource.WORKFLOW,
            )
            sandbox_result = await sandbox_gateway.submit_and_wait(
                job,
                timeout_seconds=CODE_TIMEOUT + 5,
            )

            logger.info(
                f"Code execution success={sandbox_result.success}, result={sandbox_result.result}"
            )

            if sandbox_result.stdout:
                logger.debug(f"Code stdout: {sandbox_result.stdout}")
            if sandbox_result.stderr:
                logger.warning(f"Code stderr: {sandbox_result.stderr}")

            if not sandbox_result.success:
                return ExecutionResult(
                    error=translate_public_workflow_error(
                        sandbox_result.error or "code_execution_failed"
                    )
                )

            result = sandbox_result.result

            if isinstance(result, dict):
                logger.info(f"Returning dict outputs: {result}")
                return ExecutionResult(outputs=result)
            elif result is None:
                logger.info("Code returned None, returning empty result")
                return ExecutionResult(outputs={"result": None})
            else:
                logger.info(f"Returning wrapped result: {result}")
                return ExecutionResult(outputs={"result": result})

        except Exception as e:
            logger.exception(f"Code execution error: {e}")
            return ExecutionResult(error=translate_public_workflow_error(e))

    def _wrap_python_code(self, code: str) -> str:
        """
        Wrap Python code to call main(inputs) and return result.

        The user code should define:
            def main(inputs):
                # process inputs
                return {"result": value}

        We provide `inputs` as alias for `params`.
        The sandbox wraps code in __execute__() function and returns __execute__().
        """
        return f"""
inputs = params  # Alias for compatibility

{code}

# Call main function and return result
return main(inputs)
"""

    def _wrap_javascript_code(self, code: str) -> str:
        """
        Wrap JavaScript code.

        The user code should define:
            function main(params) {
                // process params
                return { result: value };
            }

        Input variables are available as `params` object.
        The sandbox wraps code in async __execute__() and returns await __execute__().
        """
        return f"""
// User code
{code}

// Call main function
return main(params);
"""

    async def validate_config(self, config: dict) -> list[str]:
        """Validate code node configuration."""
        errors = []

        code = config.get("code", "")
        if not code:
            errors.append("Code is required")

        language = config.get("language", "python")
        if language == "python":
            if "def main" not in code:
                errors.append("Python code must define a 'main(inputs)' function")
        elif language == "javascript":
            if (
                "function main" not in code
                and "const main" not in code
                and "let main" not in code
            ):
                errors.append("JavaScript code must define a 'main(params)' function")
        else:
            errors.append(
                f"Unsupported language: {language}. Use 'python' or 'javascript'"
            )

        # Check for duplicate input parameter names
        input_mappings = config.get("inputs", [])
        names = [m.get("name") for m in input_mappings if m.get("name")]
        seen = set()
        duplicates = set()
        for name in names:
            if name in seen:
                duplicates.add(name)
            seen.add(name)

        if duplicates:
            duplicate_list = ", ".join(sorted(duplicates))
            errors.append(f"Duplicate input parameter names found: {duplicate_list}")

        return errors

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables from config."""
        return config.get("outputs", [{"name": "result", "type": "any"}])
