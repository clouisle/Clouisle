"""Shared sandbox workspace path helpers.

Kept in a standalone module so callers (sandbox file tools, chat asset tools)
can normalize workspace paths without importing ``sandbox_files`` directly,
which would trigger a circular import through ``app.llm.tools.builtin``.
"""

from __future__ import annotations

from pathlib import PurePosixPath


def normalize_workspace_path(path: str) -> str:
    """Validate and normalize a path to a ``/workspace``-prefixed POSIX path."""
    raw = str(path or "").strip()
    if not raw:
        raise ValueError("path is required")
    posix_path = PurePosixPath(raw)
    if posix_path.is_absolute() and not raw.startswith("/workspace"):
        raise ValueError("path must stay inside /workspace")
    relative = raw.removeprefix("/workspace/") if raw != "/workspace" else ""
    relative_path = PurePosixPath(relative)
    if ".." in relative_path.parts:
        raise ValueError("path must stay inside /workspace")
    if raw == "/workspace":
        return "/workspace"
    if raw.startswith("/workspace/"):
        return PurePosixPath("/workspace", relative_path).as_posix()
    return PurePosixPath("/workspace", posix_path).as_posix()


def runtime_workspace_path(path: str) -> str:
    """Convert a normalized ``/workspace``-prefixed path to a workspace-relative one."""
    if path == "/workspace":
        return "."
    return path.removeprefix("/workspace/")
