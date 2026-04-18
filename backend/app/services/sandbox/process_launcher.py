"""Sandbox process launcher."""

from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass


@dataclass
class ProcessLaunchResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class SandboxProcessLauncher:
    async def launch(
        self,
        command: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
        max_stdout_kb: int = 256,
        max_stderr_kb: int = 256,
    ) -> ProcessLaunchResult:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
            return ProcessLaunchResult(
                exit_code=process.returncode or 0,
                stdout=self._truncate_output(stdout, max_stdout_kb),
                stderr=self._truncate_output(stderr, max_stderr_kb),
            )
        except asyncio.TimeoutError:
            await self._terminate_process_group(process)
            return ProcessLaunchResult(
                exit_code=-1,
                stderr=f"Execution timeout ({timeout_seconds}s)",
                timed_out=True,
            )

    async def _terminate_process_group(
        self,
        process: asyncio.subprocess.Process,
    ) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return

        try:
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
            await process.wait()

    def _truncate_output(self, payload: bytes, max_kb: int) -> str:
        text = payload.decode("utf-8", errors="replace")
        max_chars = max_kb * 1024
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n...<truncated>"
