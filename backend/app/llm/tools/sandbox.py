"""
代码沙箱执行器

提供安全的代码执行环境，支持 JavaScript 和 Python。
使用 subprocess 隔离执行，带有超时和资源限制。
"""

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass
from enum import Enum
from typing import Any

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


class CodeSandbox:
    """代码沙箱执行器"""

    def __init__(
        self,
        timeout: float = 30.0,
        max_memory_mb: int = 128,
    ):
        self.timeout = timeout
        self.max_memory_mb = max_memory_mb

    async def execute(
        self,
        language: CodeLanguage | str,
        code: str,
        params: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """
        执行代码

        Args:
            language: 代码语言
            code: 代码内容
            params: 传入的参数（作为 params 变量）

        Returns:
            执行结果
        """
        if isinstance(language, str):
            language = CodeLanguage(language.lower())

        params = params or {}

        if language == CodeLanguage.JAVASCRIPT:
            return await self._execute_javascript(code, params)
        elif language == CodeLanguage.PYTHON:
            return await self._execute_python(code, params)
        else:
            return ExecutionResult(
                success=False,
                error=f"Unsupported language: {language}",
            )

    async def _execute_javascript(
        self,
        code: str,
        params: dict[str, Any],
    ) -> ExecutionResult:
        """执行 JavaScript 代码"""
        # 检查 Node.js 是否可用
        if not shutil.which("node"):
            return ExecutionResult(
                success=False,
                error="Node.js is not installed on the server",
            )

        # 创建包装代码
        wrapper_code = f"""
const params = {json.dumps(params)};

// 捕获 console.log 输出
const logs = [];
const originalLog = console.log;
console.log = (...args) => {{
    logs.push(args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' '));
}};

// 执行用户代码
async function __execute__() {{
    {code}
}}

// 运行并输出结果
(async () => {{
    try {{
        const result = await __execute__();
        console.log = originalLog;
        const output = {{
            success: true,
            result: result,
            logs: logs,
        }};
        process.stdout.write('__RESULT__' + JSON.stringify(output) + '__END__');
    }} catch (e) {{
        console.log = originalLog;
        const output = {{
            success: false,
            error: e.message || String(e),
            logs: logs,
        }};
        process.stdout.write('__RESULT__' + JSON.stringify(output) + '__END__');
    }}
}})();
"""

        return await self._run_subprocess(
            ["node", "-e", wrapper_code],
            language="javascript",
        )

    async def _execute_python(
        self,
        code: str,
        params: dict[str, Any],
    ) -> ExecutionResult:
        """执行 Python 代码"""
        # 检查 Python 是否可用
        python_cmd = shutil.which("python3") or shutil.which("python")
        if not python_cmd:
            return ExecutionResult(
                success=False,
                error="Python is not installed on the server",
            )

        params_json = json.dumps(params)

        # 创建包装代码
        wrapper_code = f"""
import json
import sys
from io import StringIO

params = json.loads({params_json!r})

# 捕获 print 输出
_logs = []
_original_stdout = sys.stdout
sys.stdout = StringIO()

def __execute__():
{self._indent_code(code, 4)}

try:
    result = __execute__()
    _captured = sys.stdout.getvalue()
    sys.stdout = _original_stdout
    if _captured:
        _logs.extend(_captured.strip().split("\\n"))
    output = {{
        "success": True,
        "result": result,
        "logs": _logs,
    }}
    print("__RESULT__" + json.dumps(output, default=str) + "__END__")
except Exception as e:
    sys.stdout = _original_stdout
    output = {{
        "success": False,
        "error": str(e),
        "logs": _logs,
    }}
    print("__RESULT__" + json.dumps(output, default=str) + "__END__")
"""

        return await self._run_subprocess(
            [python_cmd, "-c", wrapper_code],
            language="python",
        )

    def _indent_code(self, code: str, spaces: int) -> str:
        """缩进代码"""
        indent = " " * spaces
        lines = code.split("\n")
        return "\n".join(indent + line for line in lines)

    async def _run_subprocess(
        self,
        cmd: list[str],
        language: str,
    ) -> ExecutionResult:
        """运行子进程"""
        try:
            # 创建子进程
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # 限制环境变量，增强安全性
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "HOME": os.environ.get("HOME", "/tmp"),
                    "LANG": "en_US.UTF-8",
                    "LC_ALL": "en_US.UTF-8",
                },
            )

            try:
                # 等待执行完成（带超时）
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                # 超时，终止进程
                process.kill()
                await process.wait()
                return ExecutionResult(
                    success=False,
                    error=f"Execution timeout ({self.timeout}s)",
                )

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # 解析结果
            if "__RESULT__" in stdout_str and "__END__" in stdout_str:
                try:
                    start = stdout_str.index("__RESULT__") + len("__RESULT__")
                    end = stdout_str.index("__END__")
                    result_json = stdout_str[start:end]
                    result_data = json.loads(result_json)

                    logs = result_data.get("logs", [])
                    logs_str = "\n".join(logs) if logs else ""

                    return ExecutionResult(
                        success=result_data.get("success", False),
                        result=result_data.get("result"),
                        error=result_data.get("error"),
                        stdout=logs_str,
                        stderr=stderr_str,
                    )
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"Failed to parse execution result: {e}")
                    return ExecutionResult(
                        success=False,
                        error=f"Failed to parse result: {e}",
                        stdout=stdout_str,
                        stderr=stderr_str,
                    )
            else:
                # 没有找到结果标记
                if process.returncode != 0:
                    return ExecutionResult(
                        success=False,
                        error=stderr_str
                        or f"Process exited with code {process.returncode}",
                        stdout=stdout_str,
                        stderr=stderr_str,
                    )
                return ExecutionResult(
                    success=False,
                    error="No result returned from code execution",
                    stdout=stdout_str,
                    stderr=stderr_str,
                )

        except Exception as e:
            logger.exception(f"Subprocess execution error: {e}")
            return ExecutionResult(
                success=False,
                error=f"Execution error: {str(e)}",
            )


# 全局沙箱实例
code_sandbox = CodeSandbox()


async def execute_code(
    language: str,
    code: str,
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
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
    sandbox = CodeSandbox(timeout=timeout)
    return await sandbox.execute(language, code, params)
