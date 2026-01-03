"""
Template node executor.

Handles text templating with Jinja2 template engine.
"""

from typing import TYPE_CHECKING, Any
import logging

from jinja2 import Environment, BaseLoader, UndefinedError, TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment

from ..executor import NodeExecutor, NodeExecutorRegistry, ExecutionResult

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from ..context import ExecutionContext

logger = logging.getLogger(__name__)


@NodeExecutorRegistry.register("template")
class TemplateNodeExecutor(NodeExecutor):
    """
    Template node executor.

    Performs text templating using Jinja2 template engine.

    Node Config:
        {
            "template": "Hello {{ name }}, your order #{{ order.id }} is {{ status }}.",
            "inputs": [
                {"name": "name", "variableRef": "{{start.user_name}}"},
                {"name": "order", "variableRef": "{{db.order}}"},
                {"name": "status", "variableRef": "{{process.status}}"}
            ]
        }

    Supports full Jinja2 syntax:
        - {{ variable }} - variable output
        - {% if condition %}...{% endif %} - conditionals
        - {% for item in items %}...{% endfor %} - loops
        - {{ value | filter }} - filters

    Outputs:
        {
            "output": "Hello John, your order #12345 is shipped."
        }
    """

    def __init__(self):
        # Use sandboxed environment for security
        self.env = SandboxedEnvironment(
            loader=BaseLoader(),
            autoescape=False,  # Don't auto-escape for text templates
            trim_blocks=True,
            lstrip_blocks=True,
        )

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """Execute template node."""
        node_data = node.get("data", {})
        # Try templateConfig first (frontend structure), then fall back to config
        config = node_data.get("templateConfig") or node_data.get("config", {})
        
        logger.debug(f"Template node config: {config}")

        template_str = config.get("template", "")
        input_mappings = config.get("inputs", [])
        output_var = config.get("outputVariable", "output")
        
        logger.debug(f"Template inputs: {input_mappings}, output_var: {output_var}")

        if not template_str:
            return ExecutionResult(outputs={output_var: ""})

        # Resolve input variables
        inputs = await self.resolve_inputs(context, input_mappings)
        
        logger.info(f"Template resolved inputs: {inputs}")

        try:
            # Compile and render Jinja2 template
            template = self.env.from_string(template_str)
            result = template.render(**inputs)
            
            logger.info(f"Template result: {result[:100]}..." if len(result) > 100 else f"Template result: {result}")

            return ExecutionResult(outputs={output_var: result})

        except TemplateSyntaxError as e:
            logger.error(f"Template syntax error: {e}")
            return ExecutionResult(error=f"Template syntax error: {str(e)}")
        except UndefinedError as e:
            logger.error(f"Template undefined variable: {e}")
            return ExecutionResult(error=f"Undefined variable: {str(e)}")
        except Exception as e:
            logger.error(f"Template rendering error: {e}")
            return ExecutionResult(error=f"Template error: {str(e)}")

    def get_output_variables(self, config: dict) -> list[dict]:
        """Get output variables."""
        output_var = config.get("outputVariable", "output")
        return [{"name": output_var, "type": "string"}]
