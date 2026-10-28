"""Translate MCP adapter failures into localized API business errors.

Every MCP surface (capability browsing, the ad-hoc server tool listing used by
the tool editor, and tool execution) shares one classification:

* a local validation/configuration mistake is a 400, never a connection
  failure;
* a JSON-RPC rejection means the server was reached, so it is a 400 when the
  request itself was invalid and a 502 otherwise;
* an unsupported capability is a 409, a deadline is a 504 and oversized
  content is a 413;
* only an untyped transport failure is reported as a connection failure.

Transport and SDK failures are often wrapped in task-group ``ExceptionGroup``
leaves, so classification always starts from
:func:`~app.llm.tools.mcp_client.translate_mcp_error`.
"""

from __future__ import annotations

from app.llm.tools.mcp_client import (
    McpCapabilityUnavailable,
    McpContentTooLarge,
    McpError,
    McpInputRequired,
    McpInvalidRequest,
    McpServerError,
    McpTimeout,
    translate_mcp_error,
)
from app.schemas.response import BusinessError, ResponseCode

#: Operations whose invalid parameters are a bad resource URI, not a generic
#: request mistake; the distinction makes the user-facing hint actionable.
RESOURCE_URI_OPERATIONS = frozenset({"read:resource", "subscribe:resource"})


def map_mcp_error(
    exc: BaseException, *, operation: str | None = None
) -> BusinessError | None:
    """Return the business error for a typed MCP failure, else ``None``.

    ``None`` means the failure is not a classified MCP adapter error; callers
    keep their existing fallback (for example 502 for execution routes and
    500 for ad-hoc server configuration checks).
    """
    typed = translate_mcp_error(exc)
    if typed is None:
        return None
    if isinstance(typed, McpInvalidRequest):
        return BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key=(
                "mcp_invalid_resource_uri"
                if typed.reason == "resource_uri"
                else "mcp_invalid_request"
            ),
            status_code=400,
        )
    if isinstance(typed, McpServerError):
        if typed.invalid_request:
            return BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key=(
                    "mcp_invalid_resource_uri"
                    if operation in RESOURCE_URI_OPERATIONS
                    else "mcp_invalid_request"
                ),
                status_code=400,
            )
        return BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="mcp_server_error",
            status_code=502,
        )
    if isinstance(typed, McpCapabilityUnavailable):
        return BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="mcp_capability_unavailable",
            status_code=409,
            capability=typed.capability,
        )
    if isinstance(typed, McpTimeout):
        return BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="mcp_request_timeout",
            status_code=504,
        )
    if isinstance(typed, McpContentTooLarge):
        return BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="mcp_content_too_large",
            status_code=413,
        )
    if isinstance(typed, McpInputRequired):
        return BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="mcp_input_required",
            status_code=409,
        )
    if isinstance(typed, McpError):
        return BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="mcp_connection_failed",
            status_code=502,
        )
    return None


__all__ = ["RESOURCE_URI_OPERATIONS", "map_mcp_error"]
