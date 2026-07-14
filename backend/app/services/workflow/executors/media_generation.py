"""
Media generation node executor.

Handles image and video generation through the shared media tool pipeline.
"""

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
import logging
import re

from app.core.i18n import t
from app.llm.tools.builtin.media import generate_image, generate_video

from ..errors import translate_public_workflow_error
from ..executor import ExecutionResult, NodeExecutor, NodeExecutorRegistry
from ..types import NodeOutputDecl, TypeSpec, WorkflowValue, to_text

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from ..context import ExecutionContext

logger = logging.getLogger(__name__)


@NodeExecutorRegistry.register("media_generation")
class MediaGenerationNodeExecutor(NodeExecutor):
    """Media generation node executor."""

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        node_id = str(node.get("id") or "")
        node_data = node.get("data", {})
        config = node_data.get("mediaGenerationConfig") or node_data.get("config", {})
        mode = config.get("mode", "image")

        if mode not in {"image", "video"}:
            return ExecutionResult(error="validation_error")

        prompt = await self._build_prompt(config, context)
        if not prompt.strip():
            return ExecutionResult(error="validation_error")

        model_id = await self._resolve_model_id(config)
        if not model_id:
            return ExecutionResult(
                error="validation_error" if not config.get("modelId") else "model_not_found"
            )

        try:
            if mode == "image":
                tool_result = await self._execute_image(config, context, prompt, model_id)
            else:
                tool_result = await self._execute_video(config, context, prompt, model_id)

            return self._to_execution_result(tool_result, config)
        except Exception as exc:
            logger.exception("Media generation node %s failed: %s", node_id, exc)
            return ExecutionResult(error=translate_public_workflow_error(exc))

    async def _execute_image(
        self,
        config: dict[str, Any],
        context: "ExecutionContext",
        prompt: str,
        model_id: str,
    ) -> dict[str, Any]:
        images = await self._resolve_images(
            context,
            config.get("referenceImageVariable")
            or config.get("referenceImageVariableRef")
            or config.get("referenceImagesVariable"),
        )
        return await generate_image(
            prompt=prompt,
            width=_optional_int(config.get("width")),
            height=_optional_int(config.get("height")),
            num_images=_optional_int(config.get("numImages") or config.get("num_images"))
            or 1,
            style=config.get("style") or None,
            quality=config.get("quality") or None,
            negative_prompt=config.get("negativePrompt")
            or config.get("negative_prompt")
            or None,
            seed=_optional_int(config.get("seed")),
            images=images,
            extra_params=config.get("extraParams") or config.get("extra_params") or None,
            agent=self._media_agent(model_id, config),
        )

    async def _execute_video(
        self,
        config: dict[str, Any],
        context: "ExecutionContext",
        prompt: str,
        model_id: str,
    ) -> dict[str, Any]:
        start_images = await self._resolve_images(
            context,
            config.get("startImageVariable") or config.get("startImageVariableRef"),
        )
        current_images = start_images[:1] if start_images else None
        return await generate_video(
            prompt=prompt,
            duration=_optional_float(config.get("duration")),
            aspect_ratio=config.get("aspectRatio") or config.get("aspect_ratio") or None,
            motion_intensity=_optional_float(
                config.get("motionIntensity") or config.get("motion_intensity")
            ),
            camera_motion=config.get("cameraMotion")
            or config.get("camera_motion")
            or None,
            style=config.get("style") or None,
            seed=_optional_int(config.get("seed")),
            start_image_index=1 if current_images else None,
            extra_params=config.get("extraParams") or config.get("extra_params") or None,
            agent=self._media_agent(model_id, config),
            current_images=current_images,
        )

    async def _build_prompt(
        self,
        config: dict[str, Any],
        context: "ExecutionContext",
    ) -> str:
        prompt = config.get("prompt") or ""
        prompt = await self._resolve_template(str(prompt), context) if prompt else ""
        resolved_inputs = await self.resolve_inputs(context, config.get("inputs", []))
        if resolved_inputs:
            input_context = "\n".join(
                f"{key}: {to_text(value)}" for key, value in resolved_inputs.items()
            )
            prompt = f"{input_context}\n\n{prompt}" if prompt else input_context
        return prompt

    async def _resolve_template(
        self,
        template: str,
        context: "ExecutionContext",
    ) -> str:
        result = template
        for match in re.findall(r"\{\{([^}]+)\}\}", template):
            ref = f"{{{{{match}}}}}"
            value = await context.resolve_variable_ref(ref)
            if value is not None:
                result = result.replace(ref, to_text(value))
        return result

    async def _resolve_images(
        self,
        context: "ExecutionContext",
        variable_ref: Any,
    ) -> list[dict[str, Any]] | None:
        if not variable_ref:
            return None
        value = await context.resolve_variable_ref(str(variable_ref))
        if value is None:
            return None
        if isinstance(value, list):
            images = value
        else:
            images = [value]
        if not all(isinstance(image, dict) for image in images):
            raise ValueError(t("validation_error"))
        return images

    async def _resolve_model_id(self, config: dict[str, Any]) -> str | None:
        from app.models.model import Model, TeamModel

        team_model_id = config.get("modelId")
        if not team_model_id:
            return None

        team_model = (
            await TeamModel.filter(id=team_model_id).prefetch_related("model").first()
        )
        if team_model:
            return str(team_model.model.id)

        model = await Model.filter(id=team_model_id).first()
        return str(model.id) if model else None

    def _media_agent(self, model_id: str, config: dict[str, Any]) -> SimpleNamespace:
        num_images = _optional_int(config.get("numImages") or config.get("num_images"))
        duration = _optional_float(config.get("duration"))
        return SimpleNamespace(
            enable_image_generation=True,
            enable_video_generation=True,
            image_generation_config={
                "default_model_ref": model_id,
                "max_images": num_images or 4,
                "allow_reference_images": True,
            },
            video_generation_config={
                "default_model_ref": model_id,
                "default_duration": duration or 5.0,
                "max_duration": 30.0,
                "default_aspect_ratio": config.get("aspectRatio")
                or config.get("aspect_ratio")
                or "16:9",
                "poll_interval_ms": _optional_int(config.get("pollIntervalMs")) or 3000,
                "poll_timeout_s": _optional_int(config.get("pollTimeoutS")) or 120,
            },
        )

    def _to_execution_result(
        self,
        tool_result: dict[str, Any],
        config: dict[str, Any],
    ) -> ExecutionResult:
        display_result = tool_result.get("display_result", tool_result)
        llm_result = tool_result.get("llm_result", "")
        outputs: dict[str, WorkflowValue] = {
            "result": display_result,
            "llmResult": llm_result,
            "status": "success" if display_result.get("success") else "error",
        }
        output_var = config.get("outputVariable") or "result"
        if output_var != "result":
            outputs[str(output_var)] = display_result
        if not display_result.get("success"):
            return ExecutionResult(
                outputs=outputs,
                error=str(display_result.get("error") or "media_generation_failed"),
            )
        return ExecutionResult(outputs=outputs)

    async def validate_config(self, config: dict) -> list[str]:
        errors = []
        if config.get("mode", "image") not in {"image", "video"}:
            errors.append("Invalid media generation mode")
        if not config.get("modelId"):
            errors.append("Model ID is required")
        if not config.get("prompt") and not config.get("inputs"):
            errors.append("Prompt or inputs are required")
        return errors

    def get_output_variables(self, config: dict) -> list[dict]:
        output_var = config.get("outputVariable") or "result"
        outputs = [
            {"name": "result", "type": "object"},
            {"name": "llmResult", "type": "string"},
            {"name": "status", "type": "string"},
        ]
        if output_var != "result":
            outputs.append({"name": output_var, "type": "object"})
        return outputs

    def get_output_specs(self, config: dict) -> list[NodeOutputDecl]:
        result_spec = TypeSpec(
            kind="object",
            fields={
                "kind": TypeSpec(kind="string"),
                "success": TypeSpec(kind="boolean"),
                "prompt": TypeSpec(kind="string"),
                "error": TypeSpec(kind="string", nullable=True),
            },
        )
        output_var = config.get("outputVariable") or "result"
        decls = [
            NodeOutputDecl(name="result", type=result_spec),
            NodeOutputDecl(name="llmResult", type=TypeSpec(kind="string")),
            NodeOutputDecl(name="status", type=TypeSpec(kind="string")),
        ]
        if output_var != "result":
            decls.append(NodeOutputDecl(name=str(output_var), type=result_spec))
        return decls


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
