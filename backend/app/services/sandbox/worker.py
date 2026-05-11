"""Sandbox worker bootstrap helpers."""

from .manager import SandboxManager


async def run_sandbox_worker() -> None:
    manager = SandboxManager()
    await manager.run_once()
