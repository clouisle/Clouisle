"""Sandboxed Skill execution."""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from app.llm.tools.builtin.media import ToolExecutionResult
from app.models.skill import Skill, SkillExecutionMode
from app.schemas.response import BusinessError, ResponseCode
from app.services.sandbox.gateway import sandbox_gateway
from app.services.sandbox.models import (
    SandboxArtifact,
    SandboxArtifactSpec,
    SandboxInputFileSpec,
    SandboxJob,
    SandboxJobSource,
    SandboxLimits,
    SandboxResult,
    SandboxTaskStatus,
)
from app.services.sandbox.skills import compile_skill_to_job
from app.services.skill import SkillService

_PLACEHOLDER_PATTERN = re.compile(r"{{\s*(args|config)\.([A-Za-z_][A-Za-z0-9_]*)\s*}}")
_MAX_ARGV_LENGTH = 8192
_MAX_COMMAND_LENGTH = 32768


class SkillExecutionResult:
    def __init__(
        self,
        *,
        success: bool,
        result: Any = None,
        error: str | None = None,
        stdout: str = "",
        stderr: str = "",
        artifacts: list[SandboxArtifact] | None = None,
        duration_ms: int | None = None,
        status: SandboxTaskStatus | None = None,
    ) -> None:
        self.success = success
        self.result = result
        self.error = error
        self.stdout = stdout
        self.stderr = stderr
        self.artifacts = artifacts or []
        self.duration_ms = duration_ms
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "artifacts": [
                artifact.model_dump(mode="json") for artifact in self.artifacts
            ],
            "duration_ms": self.duration_ms,
            "status": self.status.value if self.status else None,
        }

    def to_llm_payload(self) -> str:
        if isinstance(self.result, dict) and self.result.get("type") == "skill_instructions":
            payload = {
                "success": self.success,
                "type": "skill_instructions",
                "skill": self.result.get("skill"),
                "instructions": self.result.get("instructions"),
                "arguments": self.result.get("arguments"),
                "config": self.result.get("config"),
                "usage_policy": "Apply these Skill instructions silently. Do not quote, summarize, or print the tool result itself. Do not expose internal preflight, gate, checklist, diagnostic, or status lines such as IMPECCABLE_PREFLIGHT. Respond only with the user-facing final answer or artifact requested by the user.",
            }
            return json.dumps(payload, ensure_ascii=False)

        payload = {
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "artifact_count": len(self.artifacts),
            "duration_ms": self.duration_ms,
            "status": self.status.value if self.status else None,
        }
        if self.stdout:
            payload["stdout_summary"] = self.stdout[-2000:]
        if self.stderr:
            payload["stderr_summary"] = self.stderr[-2000:]
        return json.dumps(payload, ensure_ascii=False)

    def to_chat_payload(self) -> ToolExecutionResult:
        return ToolExecutionResult(
            display_result=self.to_dict(),
            llm_result=self.to_llm_payload(),
        )


class SkillExecutor:
    """Executes Skills through the sandbox gateway."""

    @staticmethod
    def validate_arguments(skill: Skill, arguments: dict[str, Any]) -> None:
        schema = skill.input_schema or {"type": "object", "properties": {}}
        properties = schema.get("properties") or {}
        required = schema.get("required") or []

        if not isinstance(arguments, dict):
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="skill_argument_validation_failed",
            )

        for key in required:
            if key not in arguments:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="skill_argument_validation_failed",
                    data={"path": [key], "message": "required"},
                )

        for key, value in arguments.items():
            expected = properties.get(key, {}).get("type")
            if expected and not SkillExecutor._matches_json_type(value, expected):
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="skill_argument_validation_failed",
                    data={"path": [key], "message": f"expected {expected}"},
                )

    @staticmethod
    def _matches_json_type(value: Any, expected: str | list[str]) -> bool:
        expected_types = expected if isinstance(expected, list) else [expected]
        for expected_type in expected_types:
            if expected_type == "string" and isinstance(value, str):
                return True
            if (
                expected_type == "integer"
                and isinstance(value, int)
                and not isinstance(value, bool)
            ):
                return True
            if (
                expected_type == "number"
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                return True
            if expected_type == "boolean" and isinstance(value, bool):
                return True
            if expected_type == "array" and isinstance(value, list):
                return True
            if expected_type == "object" and isinstance(value, dict):
                return True
            if expected_type == "null" and value is None:
                return True
        return False

    @staticmethod
    def _stringify_command_value(value: Any) -> str:
        if isinstance(value, str):
            rendered = value
        elif isinstance(value, (dict, list)):
            rendered = json.dumps(value, ensure_ascii=False)
        elif value is None:
            rendered = ""
        else:
            rendered = str(value)

        if not rendered:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="skill_command_template_invalid",
            )
        if len(rendered) > _MAX_ARGV_LENGTH:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="skill_command_too_long",
            )
        return rendered

    @staticmethod
    def render_command_template(
        command_template: list[str],
        *,
        arguments: dict[str, Any],
        config: dict[str, Any],
    ) -> list[str]:
        command: list[str] = []
        total_length = 0

        for item in command_template:
            matches = list(_PLACEHOLDER_PATTERN.finditer(item))
            raw_placeholders = re.findall(r"{{.*?}}", item)
            if len(raw_placeholders) != len(matches):
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="skill_command_template_invalid",
                )

            if len(matches) == 1 and matches[0].span() == (0, len(item)):
                source, key = matches[0].groups()
                values = arguments if source == "args" else config
                if key not in values:
                    raise BusinessError(
                        code=ResponseCode.BAD_REQUEST,
                        msg_key="skill_command_template_variable_missing",
                        variable=f"{source}.{key}",
                    )
                rendered = SkillExecutor._stringify_command_value(values[key])
            else:
                rendered = item
                for match in matches:
                    source, key = match.groups()
                    values = arguments if source == "args" else config
                    if key not in values:
                        raise BusinessError(
                            code=ResponseCode.BAD_REQUEST,
                            msg_key="skill_command_template_variable_missing",
                            variable=f"{source}.{key}",
                        )
                    value = SkillExecutor._stringify_command_value(values[key])
                    rendered = rendered.replace(match.group(0), value)

            if not rendered:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="skill_command_template_invalid",
                )
            command.append(rendered)
            total_length += len(rendered)

        if not command:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="skill_command_template_required",
            )
        if total_length > _MAX_COMMAND_LENGTH:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="skill_command_too_long",
            )
        return command

    @staticmethod
    async def execute(
        *,
        skill: Skill,
        arguments: dict[str, Any],
        config: dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> SkillExecutionResult:
        SkillExecutor.validate_arguments(skill, arguments)
        merged_config = dict(skill.default_config or {})
        merged_config.update(config or {})

        if skill.execution_mode == SkillExecutionMode.INSTRUCTIONS:
            return SkillExecutor.execute_instructions_mode(
                skill=skill,
                arguments=arguments,
                config=merged_config,
            )

        if skill.execution_mode == SkillExecutionMode.SCRIPT:
            return await SkillExecutor.execute_script_mode(
                skill=skill,
                arguments=arguments,
                config=merged_config,
                tenant_id=tenant_id,
            )

        skill_spec = SkillService.to_sandbox_spec(skill)
        command = SkillExecutor.render_command_template(
            skill_spec.command_template,
            arguments=arguments,
            config=merged_config,
        )
        job = compile_skill_to_job(skill_spec, command)
        job.tenant_id = tenant_id

        runtime_result = await sandbox_gateway.submit_and_wait(job)
        return SkillExecutor.from_sandbox_result(runtime_result)

    @staticmethod
    async def execute_script_mode(
        *,
        skill: Skill,
        arguments: dict[str, Any],
        config: dict[str, Any],
        tenant_id: str | None,
    ) -> SkillExecutionResult:
        execution_config = skill.execution_config or {}
        runtime = execution_config.get("runtime")
        script = execution_config.get("script")
        if runtime not in {"python", "node"} or not isinstance(script, str) or not script:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="skill_execution_config_invalid",
            )

        package_files = (skill.skill_spec or {}).get("package_files")
        if not isinstance(package_files, list) or not package_files:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="skill_package_payload_missing",
            )

        input_payload = {
            "arguments": arguments,
            "config": config,
            "skill": {
                "id": str(skill.id),
                "name": skill.name,
                "display_name": skill.display_name,
                "version": skill.version,
                "package_hash": skill.package_hash,
            },
        }
        input_files = SkillExecutor._build_script_input_files(
            package_files=package_files,
            input_payload=input_payload,
        )
        executable = "python" if runtime == "python" else "node"
        job = SandboxJob(
            source=SandboxJobSource.SKILL,
            tenant_id=tenant_id,
            shell=False,
            cwd="/workspace/skill",
            command=[executable, f"/workspace/skill/{script}"],
            input_files=input_files,
            artifacts=[
                SandboxArtifactSpec.model_validate(artifact)
                for artifact in execution_config.get("artifacts", [])
            ],
            limits=SandboxLimits.model_validate(execution_config.get("limits") or {}),
            env={
                "CLOUISLE_SKILL_INPUT": "/workspace/input/skill-input.json",
                "CLOUISLE_SKILL_ROOT": "/workspace/skill",
                "CLOUISLE_WORKSPACE": "/workspace",
            },
            metadata={
                "skill_id": str(skill.id),
                "skill_name": skill.name,
                "skill_version": skill.version,
                "skill_package_hash": skill.package_hash,
            },
        )
        runtime_result = await sandbox_gateway.submit_and_wait(job)
        return SkillExecutor.from_sandbox_result(runtime_result)

    @staticmethod
    def _build_script_input_files(
        *,
        package_files: list[Any],
        input_payload: dict[str, Any],
    ) -> list[SandboxInputFileSpec]:
        input_files = [
            SandboxInputFileSpec(
                target_path="/workspace/input/skill-input.json",
                content_base64=base64.b64encode(
                    json.dumps(input_payload, ensure_ascii=False).encode("utf-8")
                ).decode("ascii"),
            )
        ]
        for item in package_files:
            if not isinstance(item, dict):
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="skill_package_payload_invalid",
                )
            path = item.get("path")
            content_base64 = item.get("content_base64")
            if not isinstance(path, str) or not isinstance(content_base64, str):
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="skill_package_payload_invalid",
                )
            if path.startswith("/") or ".." in path.split("/"):
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="skill_package_payload_invalid",
                )
            input_files.append(
                SandboxInputFileSpec(
                    target_path=f"/workspace/skill/{path}",
                    content_base64=content_base64,
                    mode=item.get("mode"),
                )
            )
        return input_files

    @staticmethod
    def execute_instructions_mode(
        *,
        skill: Skill,
        arguments: dict[str, Any],
        config: dict[str, Any],
    ) -> SkillExecutionResult:
        return SkillExecutionResult(
            success=True,
            result={
                "type": "skill_instructions",
                "skill": {
                    "id": str(skill.id),
                    "name": skill.name,
                    "display_name": skill.display_name,
                    "description": skill.description,
                    "version": skill.version,
                    "package_path": skill.package_path,
                    "execution_mode": skill.execution_mode.value,
                },
                "instructions": skill.instructions or skill.skill_md,
                "arguments": arguments,
                "config": config,
                "manifest": {
                    "file_count": (skill.package_manifest or {}).get("file_count", 0),
                    "package_hash": skill.package_hash,
                },
            },
        )

    @staticmethod
    def from_sandbox_result(result: SandboxResult) -> SkillExecutionResult:
        return SkillExecutionResult(
            success=result.success,
            result=result.result,
            error=result.error,
            stdout=result.stdout,
            stderr=result.stderr,
            artifacts=result.artifacts,
            duration_ms=result.metadata.duration_ms,
            status=result.status,
        )
