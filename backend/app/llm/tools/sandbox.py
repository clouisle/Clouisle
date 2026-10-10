"""
代码沙箱执行器

提供安全的代码执行环境，支持 JavaScript 和 Python。
使用 subprocess 隔离执行，带有超时和资源限制。
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.core.config import settings
from app.core.i18n import t
from app.services.sandbox.compiler import compile_legacy_code_job
from app.services.sandbox.gateway import sandbox_gateway
from app.services.sandbox.models import SandboxJobSource

logger = logging.getLogger(__name__)


class CodeLanguage(str, Enum):
    """支持的代码语言"""

    JAVASCRIPT = "javascript"
    PYTHON = "python"


@dataclass
class ExecutionResult:
    """执行结果"""

    success: bool
    result: Any = None
    error: str | None = None
    stdout: str = ""
    stderr: str = ""


async def execute_code(
    language: str,
    code: str,
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
    session_id: str | None = None,
    agent_id: str | None = None,
    team_id: str | None = None,
) -> ExecutionResult:
    """
    执行代码的便捷函数

    Args:
        language: 代码语言 (javascript/python)
        code: 代码内容
        params: 传入的参数
        timeout: 超时时间（秒）

    Returns:
        执行结果
    """
    if not settings.SANDBOX_RUNTIME_ENABLED:
        return ExecutionResult(success=False, error=t("tool_execution_failed"))

    job = compile_legacy_code_job(
        language=language,
        code=code,
        params=params,
        timeout=timeout,
        source=SandboxJobSource.LEGACY_SNIPPET,
    )
    try:
        runtime_result = await sandbox_gateway.submit_and_wait(
            job,
            timeout_seconds=timeout + 5,
            session_id=session_id,
            agent_id=agent_id,
            team_id=team_id,
        )
    except Exception as exc:
        logger.warning("Sandbox runtime gateway failed: %s", exc)
        return ExecutionResult(success=False, error=t("tool_execution_failed"))

    return ExecutionResult(
        success=runtime_result.success,
        result=runtime_result.result,
        error=runtime_result.error,
        stdout=runtime_result.stdout,
        stderr=runtime_result.stderr,
    )
