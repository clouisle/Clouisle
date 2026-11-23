"""Push installed Skill packages into a session workspace.

Skill packages are delivered to a worker node through the sandbox job payload
(``input_files``), never through shared or distributed storage: a node only ever
sees the bytes the control plane hands it. Sync therefore happens once per
session workspace generation — at session creation and as a safety net before a
Skill call — instead of on every Skill invocation.
"""

from __future__ import annotations

import logging
import re
from pathlib import PurePosixPath
from typing import Any, Iterable, Sequence

from app.core.config import settings
from app.models.skill import Skill
from app.schemas.response import BusinessError, ResponseCode

from .gateway import sandbox_gateway
from .models import (
    SandboxInputFileSpec,
    SandboxJob,
    SandboxJobSource,
    SandboxLimits,
    SandboxSkillSyncState,
)
from .session_store import sandbox_session_store

logger = logging.getLogger(__name__)

WORKSPACE_SKILLS_DIR = "skills"
SYNC_MARKER_FILENAME = ".clouisle-sync.json"
_SAFE_DIR_PATTERN = re.compile(r"[^A-Za-z0-9_.-]")

SkillPackage = tuple[Skill, list[dict[str, Any]]]


class SkillWorkspaceSync:
    """Materialize Skill packages inside the session workspace of one node."""

    @staticmethod
    def skill_dirname(skill: Skill) -> str:
        safe_name = _SAFE_DIR_PATTERN.sub("_", skill.name).strip("._-")
        return safe_name or str(skill.id)

    @classmethod
    def skill_root(cls, skill: Skill) -> str:
        """Logical workspace path the model reads Skill files from."""
        return f"/workspace/{WORKSPACE_SKILLS_DIR}/{cls.skill_dirname(skill)}"

    @staticmethod
    def skill_files(skill: Skill) -> list[dict[str, Any]]:
        """Installed package files, skipping entries that could escape the package."""
        package_files = (skill.skill_spec or {}).get("package_files")
        if not isinstance(package_files, list):
            return []
        files: list[dict[str, Any]] = []
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
            mode = item.get("mode")
            files.append(
                {
                    "path": relative_path.as_posix(),
                    "content_base64": content_base64,
                    "mode": mode if isinstance(mode, int) else None,
                }
            )
        return files

    @classmethod
    async def ensure_skills(
        cls,
        *,
        session_id: str,
        skills: Sequence[Skill],
        team_id: str | None = None,
        agent_id: str | None = None,
        force: bool = False,
    ) -> list[str]:
        """Push every Skill the session is missing and return the synced IDs.

        The recorded state is bound to the workspace generation, so a reset or
        recovery invalidates it and the next caller syncs again.
        """
        pending: list[SkillPackage] = []
        for skill in skills:
            if not getattr(skill, "is_enabled", True):
                continue
            files = cls.skill_files(skill)
            if not files:
                continue
            pending.append((skill, files))
        if not pending:
            return []

        binding = await sandbox_session_store.get_binding(session_id)
        generation = binding.generation if binding else None
        state = await sandbox_session_store.get_skill_sync(session_id)
        synced = (
            {}
            if force or state is None or state.generation != generation
            else dict(state.skills)
        )

        missing = [
            entry
            for entry in pending
            if synced.get(str(entry[0].id)) != (entry[0].package_hash or "")
        ]
        if not missing:
            return []

        synced_ids: list[str] = []
        for chunk in cls._chunk_by_payload(missing):
            job = cls._build_job(chunk)
            result = await sandbox_gateway.submit_and_wait(
                job,
                session_id=session_id,
                agent_id=agent_id,
                team_id=team_id,
                timeout_seconds=settings.SKILL_SYNC_TIMEOUT_SECONDS,
            )
            if not result.success:
                logger.warning(
                    "Skill package sync failed for session %s: %s",
                    session_id,
                    result.error,
                )
                raise BusinessError(
                    code=ResponseCode.INTERNAL_ERROR,
                    msg_key="skill_package_sync_failed",
                    status_code=502,
                )
            for skill, _files in chunk:
                synced[str(skill.id)] = skill.package_hash or ""
                synced_ids.append(str(skill.id))
            synced_generation = (
                result.binding.generation if result.binding else generation
            )
            await sandbox_session_store.set_skill_sync(
                session_id,
                SandboxSkillSyncState(
                    generation=synced_generation, skills=dict(synced)
                ),
            )
        logger.info(
            "Synced %d Skill package(s) into sandbox session %s",
            len(synced_ids),
            session_id,
        )
        return synced_ids

    @classmethod
    def _chunk_by_payload(
        cls, pending: Iterable[SkillPackage]
    ) -> list[list[SkillPackage]]:
        """Group Skills so one job stays inside the configured payload bound."""
        limit = settings.SKILL_SYNC_MAX_TOTAL_BYTES
        chunks: list[list[SkillPackage]] = []
        current: list[SkillPackage] = []
        current_size = 0
        for skill, files in pending:
            skill_size = sum(len(item["content_base64"]) for item in files)
            if skill_size > limit:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="skill_package_sync_too_large",
                    data={"name": skill.name, "limit": limit},
                )
            if current and current_size + skill_size > limit:
                chunks.append(current)
                current = []
                current_size = 0
            current.append((skill, files))
            current_size += skill_size
        if current:
            chunks.append(current)
        return chunks

    @classmethod
    def _build_job(cls, chunk: Sequence[SkillPackage]) -> SandboxJob:
        job = SandboxJob(
            source=SandboxJobSource.SKILL,
            language="python",
            cwd="/workspace",
            limits=SandboxLimits(
                timeout_seconds=settings.SKILL_SYNC_TIMEOUT_SECONDS,
            ),
        )
        staging_root = f".skill-sync/{job.job_id}"
        directories: list[str] = []
        plan: list[dict[str, Any]] = []
        markers: list[dict[str, Any]] = []

        for skill, files in chunk:
            directory = f"{WORKSPACE_SKILLS_DIR}/{cls.skill_dirname(skill)}"
            directories.append(directory)
            for item in files:
                staged = f"{staging_root}/{len(plan)}"
                job.input_files.append(
                    SandboxInputFileSpec(
                        target_path=f"/workspace/{staged}",
                        content_base64=item["content_base64"],
                        mode=item["mode"],
                    )
                )
                plan.append(
                    {
                        "src": staged,
                        "dest": f"{directory}/{item['path']}",
                        "mode": item["mode"],
                    }
                )
            markers.append(
                {
                    "path": f"{directory}/{SYNC_MARKER_FILENAME}",
                    "payload": {
                        "skill_id": str(skill.id),
                        "name": skill.name,
                        "package_hash": skill.package_hash,
                        "file_count": len(files),
                    },
                }
            )

        job.code = cls._bootstrap_code(
            staging_root=staging_root,
            directories=directories,
            plan=plan,
            markers=markers,
        )
        job.metadata = {
            "skill_sync": [
                {
                    "skill_id": str(skill.id),
                    "name": skill.name,
                    "package_hash": skill.package_hash,
                }
                for skill, _files in chunk
            ]
        }
        return job

    @staticmethod
    def _bootstrap_code(
        *,
        staging_root: str,
        directories: list[str],
        plan: list[dict[str, Any]],
        markers: list[dict[str, Any]],
    ) -> str:
        return (
            "import json\n"
            "import os\n"
            "import shutil\n"
            "from pathlib import Path\n"
            f"staging_root = {staging_root!r}\n"
            f"directories = {directories!r}\n"
            f"plan = {plan!r}\n"
            f"markers = {markers!r}\n"
            "root = Path.cwd().resolve()\n"
            "\n"
            "def target_path(relative):\n"
            "    target = root / relative\n"
            "    if not target.resolve().is_relative_to(root):\n"
            "        raise ValueError('Skill path escapes workspace')\n"
            "    current = target\n"
            "    while current != root:\n"
            "        if current.is_symlink():\n"
            "            raise ValueError('Skill path contains a symlink')\n"
            "        current = current.parent\n"
            "    return target\n"
            "\n"
            "try:\n"
            "    for relative in directories:\n"
            "        directory = target_path(relative)\n"
            "        if directory.is_symlink() or (\n"
            "            directory.exists() and not directory.is_dir()\n"
            "        ):\n"
            "            raise ValueError('Skill directory conflicts with a file')\n"
            "        if directory.exists():\n"
            "            shutil.rmtree(directory)\n"
            "    for entry in plan:\n"
            "        destination = target_path(entry['dest'])\n"
            "        destination.parent.mkdir(parents=True, exist_ok=True)\n"
            "        os.replace(root / entry['src'], destination)\n"
            "        if entry.get('mode') is not None:\n"
            "            os.chmod(destination, entry['mode'])\n"
            "    for marker in markers:\n"
            "        path = target_path(marker['path'])\n"
            "        path.write_text(\n"
            "            json.dumps(marker['payload'], sort_keys=True),\n"
            "            encoding='utf-8',\n"
            "        )\n"
            "finally:\n"
            "    shutil.rmtree(root / staging_root, ignore_errors=True)\n"
            "return {'skills': directories}\n"
        )
