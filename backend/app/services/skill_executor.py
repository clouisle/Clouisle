"""Sandboxed Skill execution."""

from __future__ import annotations

import base64
import json
import re
from pathlib import PurePosixPath
from typing import Any

from app.llm.tools.builtin.media import ToolExecutionResult
from app.models.skill import Skill
from app.schemas.response import BusinessError, ResponseCode
from app.services.sandbox.gateway import sandbox_gateway
from app.services.sandbox.models import (
    SandboxArtifact,
    SandboxInputFileSpec,
    SandboxTaskStatus,
)

_SAFE_SKILL_DIR_PATTERN = re.compile(r"[^A-Za-z0-9_.-]")


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
        if (
            isinstance(self.result, dict)
            and self.result.get("type") == "skill_instructions"
        ):
            raw_skill = self.result.get("skill")
            skill = raw_skill if isinstance(raw_skill, dict) else {}
            display_skill = {
                key: skill.get(key)
                for key in (
                    "id",
                    "name",
                    "display_name",
                    "description",
                    "version",
                    "package_path",
                    "package_hash",
                )
                if skill.get(key) is not None
            }
            return {
                "success": self.success,
                "result": {
                    "type": "skill_instructions",
                    "skill": display_skill,
                    "workspace_root": self.result.get("workspace_root"),
                    "status": self.result.get("status") or "loaded",
                },
                "error": self.error,
                "artifacts": [],
                "duration_ms": self.duration_ms,
                "status": self.status.value if self.status else None,
            }

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
        payload = {
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "artifact_count": len(self.artifacts),
            "duration_ms": self.duration_ms,
            "status": self.status.value if self.status else None,
        }

        if self.artifacts:
            payload["artifacts"] = [
                {
                    "path": a.path,
                    "url": a.url,
                    "filename": a.filename,
                    "size": a.size,
                    "content_type": a.content_type,
                }
                for a in self.artifacts
            ]

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
    """Loads Skills for the model and stages their package resources."""

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
    async def execute(
        *,
        skill: Skill,
        arguments: dict[str, Any],
        config: dict[str, Any] | None = None,
        tenant_id: str | None = None,
        session_id: str | None = None,
    ) -> SkillExecutionResult:
        SkillExecutor.validate_arguments(skill, arguments)
        merged_config = dict(skill.default_config or {})
        merged_config.update(config or {})

        workspace_root = SkillExecutor.skill_workspace_root(skill)
        if session_id:
            await SkillExecutor.stage_package_resources(
                skill=skill,
                workspace_root=workspace_root,
                tenant_id=tenant_id,
                session_id=session_id,
            )

        return SkillExecutor.build_instruction_result(
            skill=skill,
            arguments=arguments,
            config=merged_config,
            workspace_root=workspace_root,
        )

    @staticmethod
    def build_instruction_result(
        *,
        skill: Skill,
        arguments: dict[str, Any],
        config: dict[str, Any],
        workspace_root: str,
    ) -> SkillExecutionResult:
        instructions = skill.instructions or skill.skill_md or ""
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
                    "package_hash": skill.package_hash,
                },
                "instructions": instructions,
                "arguments": arguments,
                "config": config,
                "manifest": {
                    "file_count": (skill.package_manifest or {}).get("file_count", 0),
                    "package_hash": skill.package_hash,
                },
                "artifact_guidance": (
                    "If this Skill creates user-facing files, keep them under /workspace/output. "
                    "When writing Python or Node scripts, prefer relative output paths such as "
                    "output/report.docx or derive paths from the working directory instead of "
                    "hardcoding /workspace/... inside the script. Verify the final paths with bash "
                    "commands such as ls/find/file, then call the artifact tool to generate Markdown "
                    "download links. Include those Markdown links directly in your final answer."
                ),
                "workspace_root": workspace_root,
                "status": "loaded",
            },
            status=SandboxTaskStatus.COMPLETED,
        )

    @staticmethod
    def build_package_input_files(
        *,
        skill: Skill,
        workspace_root: str,
    ) -> list[SandboxInputFileSpec]:
        package_files = (skill.skill_spec or {}).get("package_files")
        if not isinstance(package_files, list):
            return []

        input_files: list[SandboxInputFileSpec] = []
        for item in package_files:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            content_base64 = item.get("content_base64")
            if not isinstance(path, str) or not isinstance(content_base64, str):
                continue
            relative_path = PurePosixPath(path)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                continue
            input_files.append(
                SandboxInputFileSpec(
                    target_path=PurePosixPath(workspace_root, relative_path).as_posix(),
                    content_base64=content_base64,
                    mode=item.get("mode")
                    if isinstance(item.get("mode"), int)
                    else None,
                )
            )
        return input_files

    @staticmethod
    def skill_workspace_root(skill: Skill) -> str:
        safe_name = _SAFE_SKILL_DIR_PATTERN.sub("_", skill.name).strip("._-")
        if not safe_name:
            safe_name = str(skill.id)
        return f"/workspace/skill/{safe_name}"

    @staticmethod
    async def stage_package_resources(
        *,
        skill: Skill,
        workspace_root: str,
        tenant_id: str | None,
        session_id: str,
    ) -> None:
        workspace = await sandbox_gateway.get_session_workspace(
            session_id,
            team_id=tenant_id,
        )
        if workspace is None:
            return

        workspace_manager = sandbox_gateway._get_workspace_manager()
        for input_file in SkillExecutor.build_package_input_files(
            skill=skill,
            workspace_root=workspace_root,
        ):
            target = workspace_manager.resolve_workspace_path(
                workspace,
                input_file.target_path,
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(
                base64.b64decode(input_file.content_base64, validate=True)
            )
            if input_file.mode is not None:
                target.chmod(input_file.mode)

    @staticmethod
    def from_sandbox_result(result) -> SkillExecutionResult:
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
