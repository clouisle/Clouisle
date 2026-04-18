"""Sandbox scheduler scaffold."""

from __future__ import annotations

from .models import SandboxJob


class SandboxScheduler:
    def can_schedule(self, job: SandboxJob) -> bool:
        return True
