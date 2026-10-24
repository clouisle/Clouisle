"""Original failure text recorded alongside a delivery's stable error key.

The key stays locale-neutral for behaviour; operators need the provider's own
message and code to fix it. The detail is bounded and never includes request
credentials.
"""

_MAX_DETAIL = 2000


def error_detail(exc: BaseException) -> str:
    parts = [f"{type(exc).__name__}: {exc}".strip()]
    status = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    if status is not None:
        parts.append(f"HTTP {status}")
    if code is not None:
        parts.append(f"code {code}")
    detail = getattr(exc, "detail", None)
    if detail:
        parts.append(str(detail))
    return " | ".join(part for part in parts if part)[:_MAX_DETAIL]
