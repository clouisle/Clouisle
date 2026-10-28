"""File download for the model tool surface.

Chat previously served ``file_download`` from an inline branch that called the
HTTP transport directly, so a model-named download bypassed tool policy and
approvals. It is now a registry builtin: the call materializes a stable Tool
definition and executes through the unified connection/approval boundary using
the shared SSRF-validated HTTP executor. The definition defaults to allow;
confirmation is opt-in through the Agent switch or a stored policy layer.

The tool stays non-selectable (see ``NON_SELECTABLE_BUILTIN_TOOLS``): it is not
advertised in the catalog or through agent tool configuration, so it remains a
compatibility path for calls that already name it rather than a new product
surface.
"""

from typing import Any

from app.llm.tools.executors import execute_http_tool, format_http_result_for_llm

from ..registry import ToolConcurrency, ToolParameter, tool_registry

FILE_DOWNLOAD_TIMEOUT_SECONDS = 60.0


async def file_download(url: str) -> dict[str, Any]:
    """Fetch one HTTP(S) URL through the shared SSRF-validated transport."""
    result = await execute_http_tool(
        http_config={"url": url, "method": "GET"},
        arguments={},
        timeout=FILE_DOWNLOAD_TIMEOUT_SECONDS,
    )
    return {
        "result": result,
        "llm_result": format_http_result_for_llm(result),
    }


def register_file_download_tool() -> None:
    tool_registry.register(
        name="file_download",
        description=(
            "Download the content of an HTTP(S) URL and return it as text. "
            "The call runs through the tool execution boundary; enable "
            "'Require confirmation' on the Agent to gate it per call."
        ),
        parameters=[
            ToolParameter(
                name="url",
                type="string",
                description="HTTP(S) URL to download",
                required=True,
            )
        ],
        concurrency=ToolConcurrency.EXCLUSIVE,
    )(file_download)


__all__ = ["file_download", "register_file_download_tool"]
