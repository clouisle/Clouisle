"""Sandbox skill helpers scaffold."""

from __future__ import annotations

from .models import SandboxJob, SandboxJobSource, SandboxSkillSpec


def compile_skill_to_job(skill: SandboxSkillSpec, command: list[str]) -> SandboxJob:
    return SandboxJob(
        source=SandboxJobSource.SKILL,
        runtime_profile=skill.runtime_profile,
        command=command,
        python_packages=skill.python_packages,
        js_packages=skill.js_packages,
        env=skill.env,
        limits=skill.limits,
        artifacts=skill.artifacts,
        metadata={"skill_name": skill.name, "skill_version": skill.version, **skill.metadata},
    )
