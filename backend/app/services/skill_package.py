"""Skill package parsing helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from app.models.skill import SkillCategory
from app.services.sandbox.models import SandboxArtifactSpec, SandboxLimits

DEFAULT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": "The user task for this skill.",
        }
    },
    "required": ["prompt"],
}

IGNORED_DIR_NAMES = {
    ".git",
    "node_modules",
    ".next",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
}

NESTED_ARCHIVE_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"}
_SAFE_PACKAGE_NAME_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def resolve_child_path(root: Path, relative_path: str | PurePosixPath) -> Path | None:
    root = root.resolve()
    path = PurePosixPath(str(relative_path))
    if path.is_absolute() or ".." in path.parts:
        return None
    candidate = (root / Path(*path.parts)).resolve()
    if candidate == root or root in candidate.parents:
        return candidate
    return None


def safe_package_segment(value: str) -> str:
    segment = _SAFE_PACKAGE_NAME_RE.sub("-", value.strip())[:80].strip(".-_")
    return segment or "skill"


class ParsedSkillPackage(BaseModel):
    package_path: str
    name: str | None = None
    display_name: str | None = None
    description: str = ""
    version: str = "1.0.0"
    category: SkillCategory = SkillCategory.OTHER
    icon: str | None = None
    skill_md: str = ""
    instructions: str = ""
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    input_schema: dict[str, Any] = Field(
        default_factory=lambda: dict(DEFAULT_INPUT_SCHEMA)
    )
    execution_config: dict[str, Any] = Field(default_factory=dict)
    package_manifest: dict[str, Any] = Field(default_factory=dict)
    package_hash: str | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


class SkillPackageService:
    """Parse package roots that contain a SKILL.md file."""

    @staticmethod
    def find_skill_roots(root: Path, *, max_depth: int = 6) -> list[Path]:
        root = root.resolve()
        skill_roots: list[Path] = []
        for current, dirnames, filenames in os.walk(root):
            current_path = Path(current).resolve()
            relative = current_path.relative_to(root)
            depth = 0 if str(relative) == "." else len(relative.parts)
            dirnames[:] = [name for name in dirnames if name not in IGNORED_DIR_NAMES]
            if depth >= max_depth:
                dirnames[:] = []
            if "SKILL.md" in filenames:
                skill_roots.append(current_path)
        return sorted(skill_roots, key=lambda path: path.relative_to(root).as_posix())

    @staticmethod
    def parse_skill_root(source_root: Path, skill_root: Path) -> ParsedSkillPackage:
        source_root = source_root.resolve()
        skill_root = skill_root.resolve()
        try:
            relative_root = skill_root.relative_to(source_root)
        except ValueError:
            parsed = ParsedSkillPackage(package_path=".")
            parsed.errors.append("skill_package_path_invalid")
            return parsed
        package_path = relative_root.as_posix() or "."
        skill_md_path = resolve_child_path(skill_root, "SKILL.md")
        parsed = ParsedSkillPackage(package_path=package_path)
        if skill_md_path is None:
            parsed.errors.append("skill_md_not_found")
            return parsed

        try:
            skill_md = skill_md_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            parsed.errors.append("skill_md_must_be_utf8")
            return parsed
        except OSError:
            parsed.errors.append("skill_md_not_found")
            return parsed

        parsed.skill_md = skill_md
        frontmatter, instructions, errors = SkillPackageService.parse_skill_md(skill_md)
        parsed.frontmatter = frontmatter
        parsed.instructions = instructions
        parsed.errors.extend(errors)

        parsed.name = SkillPackageService._string_field(frontmatter, "name")
        parsed.display_name = (
            SkillPackageService._string_field(frontmatter, "display_name")
            or parsed.name
        )
        parsed.description = (
            SkillPackageService._string_field(frontmatter, "description") or ""
        )
        parsed.version = (
            SkillPackageService._string_field(frontmatter, "version") or "1.0.0"
        )
        parsed.icon = SkillPackageService._string_field(frontmatter, "icon")
        parsed.category = SkillPackageService._category_field(
            frontmatter.get("category")
        )

        if not parsed.name:
            parsed.errors.append("skill_name_required")
        if not parsed.description:
            parsed.errors.append("skill_description_required")

        clouisle = frontmatter.get("x-clouisle")
        if clouisle is not None and not isinstance(clouisle, dict):
            parsed.errors.append("skill_clouisle_extension_invalid")
            clouisle = {}
        clouisle = clouisle or {}

        input_schema = clouisle.get("input_schema", DEFAULT_INPUT_SCHEMA)
        if SkillPackageService._is_object_schema(input_schema):
            parsed.input_schema = input_schema
        else:
            parsed.errors.append("skill_invalid_input_schema")

        execution = clouisle.get("execution", {})
        if execution is None:
            execution = {}
        if not isinstance(execution, dict):
            parsed.errors.append("skill_execution_invalid")
            execution = {}

        execution_config, execution_errors = (
            SkillPackageService._normalize_execution_config(execution, skill_root)
        )
        parsed.execution_config = execution_config
        parsed.errors.extend(execution_errors)

        manifest, package_hash, manifest_errors = SkillPackageService.build_manifest(
            skill_root
        )
        parsed.package_manifest = manifest
        parsed.package_hash = package_hash
        parsed.errors.extend(manifest_errors)
        return parsed

    @staticmethod
    def _normalize_execution_config(
        execution: dict[str, Any], skill_root: Path
    ) -> tuple[dict[str, Any], list[str]]:
        errors: list[str] = []
        if not execution:
            return {}, errors

        config: dict[str, Any] = dict(execution)
        raw_mode = execution.get("mode", "instructions")
        if not isinstance(raw_mode, str):
            errors.append("skill_execution_mode_invalid")
            return config, errors

        mode = raw_mode.strip().lower() or "instructions"
        if mode not in {"instructions", "script"}:
            errors.append("skill_execution_mode_invalid")
            return config, errors
        config["mode"] = mode

        if mode == "instructions":
            return {"mode": "instructions"}, errors

        runtime = str(execution.get("runtime") or "").strip().lower()
        script_value = execution.get("script")
        script = script_value if isinstance(script_value, str) else None
        has_script = bool(script and script.strip())

        if not runtime:
            errors.append("skill_script_runtime_required")
        elif runtime not in {"python", "node", "javascript"}:
            errors.append("skill_script_runtime_invalid")
        else:
            config["runtime"] = "node" if runtime == "javascript" else runtime

        if not has_script:
            errors.append("skill_script_required")
        elif script is not None:
            script_path = PurePosixPath(script.strip())
            normalized_script = script_path.as_posix()
            if not SkillPackageService._is_safe_relative_path(normalized_script):
                errors.append("skill_script_path_invalid")
            else:
                script_file = resolve_child_path(skill_root, normalized_script)
                if script_file is None or not script_file.is_file():
                    errors.append("skill_script_not_found")
                else:
                    config["script"] = normalized_script

        limits, limits_error = SkillPackageService._normalize_execution_limits(
            execution.get("limits")
        )
        if limits_error:
            errors.append(limits_error)
        else:
            config["limits"] = limits

        artifacts, artifacts_errors = (
            SkillPackageService._normalize_execution_artifacts(
                execution.get("artifacts", [])
            )
        )
        config["artifacts"] = artifacts
        errors.extend(artifacts_errors)
        return config, errors

    @staticmethod
    def _normalize_execution_limits(value: Any) -> tuple[dict[str, Any], str | None]:
        if value is None:
            return SandboxLimits().model_dump(), None
        if not isinstance(value, dict):
            return SandboxLimits().model_dump(), "skill_execution_limits_invalid"
        try:
            return SandboxLimits.model_validate(value).model_dump(), None
        except ValidationError:
            return SandboxLimits().model_dump(), "skill_execution_limits_invalid"

    @staticmethod
    def _normalize_execution_artifacts(
        value: Any,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if value is None:
            return [], []
        if not isinstance(value, list):
            return [], ["skill_execution_artifacts_invalid"]

        artifacts: list[dict[str, Any]] = []
        errors: list[str] = []
        for item in value:
            if isinstance(item, str):
                raw = {"path": item}
            elif isinstance(item, dict):
                raw = dict(item)
            else:
                errors.append("skill_execution_artifacts_invalid")
                continue

            path = raw.get("path")
            if not isinstance(path, str) or not path.strip():
                errors.append("skill_execution_artifact_path_invalid")
                continue
            normalized_path = SkillPackageService._normalize_workspace_path(path)
            if normalized_path is None:
                errors.append("skill_execution_artifact_path_invalid")
                continue
            raw["path"] = normalized_path
            try:
                artifact = SandboxArtifactSpec.model_validate(raw)
            except ValidationError:
                errors.append("skill_execution_artifacts_invalid")
                continue
            artifacts.append(artifact.model_dump(exclude_none=True))
        return artifacts, errors

    @staticmethod
    def _normalize_workspace_path(value: str) -> str | None:
        raw = value.strip()
        path = PurePosixPath(raw)
        if path.is_absolute() and not raw.startswith("/workspace"):
            return None
        workspace_relative = (
            raw.removeprefix("/workspace/") if raw != "/workspace" else ""
        )
        relative_path = PurePosixPath(workspace_relative)
        if ".." in relative_path.parts:
            return None
        if raw == "/workspace":
            return "/workspace"
        if raw.startswith("/workspace/"):
            return PurePosixPath("/workspace", relative_path).as_posix()
        return PurePosixPath("/workspace", path).as_posix()

    @staticmethod
    def parse_skill_md(skill_md: str) -> tuple[dict[str, Any], str, list[str]]:
        if not skill_md.startswith("---\n"):
            return {}, skill_md, ["skill_frontmatter_required"]

        end_marker = "\n---\n"
        end_index = skill_md.find(end_marker, 4)
        if end_index == -1:
            return {}, skill_md, ["skill_frontmatter_unclosed"]

        raw_frontmatter = skill_md[4:end_index]
        instructions = skill_md[end_index + len(end_marker) :].lstrip("\n")
        try:
            frontmatter = yaml.safe_load(raw_frontmatter) or {}
        except yaml.YAMLError:
            return {}, instructions, ["skill_frontmatter_invalid"]
        if not isinstance(frontmatter, dict):
            return {}, instructions, ["skill_frontmatter_invalid"]
        return frontmatter, instructions, []

    @staticmethod
    def build_manifest(skill_root: Path) -> tuple[dict[str, Any], str, list[str]]:
        files: list[dict[str, Any]] = []
        digest = hashlib.sha256()
        errors: list[str] = []

        skill_root = skill_root.resolve()
        for raw_path in sorted(skill_root.rglob("*")):
            if raw_path.is_symlink():
                errors.append("skill_package_symlink_not_allowed")
                continue
            path = raw_path.resolve()
            try:
                relative_path = path.relative_to(skill_root)
            except ValueError:
                errors.append("skill_package_path_invalid")
                continue
            relative = relative_path.as_posix()
            if any(part in IGNORED_DIR_NAMES for part in relative_path.parts):
                continue
            if not path.is_file():
                continue
            if (
                path.suffix.lower() in NESTED_ARCHIVE_SUFFIXES
                and path.name != "SKILL.md"
            ):
                errors.append("skill_package_nested_archive_not_allowed")
                continue
            stat = path.stat()
            files.append({"path": relative, "size": stat.st_size})
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")

        manifest = {"files": files, "file_count": len(files)}
        manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        digest.update(manifest_json.encode("utf-8"))
        return manifest, digest.hexdigest(), errors

    @staticmethod
    def _string_field(data: dict[str, Any], key: str) -> str | None:
        value = data.get(key)
        if value is None:
            return None
        return str(value).strip() or None

    @staticmethod
    def _category_field(value: Any) -> SkillCategory:
        if isinstance(value, str):
            try:
                return SkillCategory(value)
            except ValueError:
                return SkillCategory.OTHER
        return SkillCategory.OTHER

    @staticmethod
    def _is_object_schema(value: Any) -> bool:
        return (
            isinstance(value, dict)
            and value.get("type") == "object"
            and isinstance(value.get("properties", {}), dict)
            and isinstance(value.get("required", []), list)
        )

    @staticmethod
    def _is_safe_relative_path(value: str) -> bool:
        path = Path(value)
        return not path.is_absolute() and ".." not in path.parts
