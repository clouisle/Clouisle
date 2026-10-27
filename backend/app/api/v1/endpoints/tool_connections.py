"""Tool connection management endpoints.

Secret-safe CRUD and delegation-grant APIs for external identities used by
tools. This module never returns credential values: responses only expose
``secret_fields`` (names), ``account_label`` and lifecycle metadata.

Authorization is layered and non-substitutable:

1. Tool access – canonical ``check_tool_access`` for the owning team, or an
   explicit cross-team ``ToolShare`` for the consuming team.
2. Connection management – service-enforced owner/team-admin/site-admin rules.
3. Delegation – only the personal connection owner can grant an entrypoint.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api import deps
from app.api.team_access import check_team_access
from app.api.v1.endpoints.tools import check_tool_access
from app.llm.tools import tool_registry
from app.models.tool import Tool, ToolShare, ToolVisibility
from app.models.user import User
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.schemas.tool_connection import (
    ToolConnectionCreate,
    ToolConnectionForToolCreate,
    ToolConnectionOut,
    ToolConnectionUpdate,
)
from app.services.tool_connections import ToolConnectionService

router = APIRouter()
connection_router = APIRouter()


# ============ Helpers ============


def _tool_visibility(tool: Tool) -> str:
    value = getattr(tool, "visibility", ToolVisibility.PRIVATE)
    return value.value if isinstance(value, ToolVisibility) else str(value)


async def _load_tool(tool_id: UUID) -> Tool:
    tool = await Tool.filter(id=tool_id).first()
    if not tool:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_not_found",
            status_code=404,
        )
    return tool


async def _assert_tool_access(tool: Tool, team_id: UUID, user: User) -> None:
    """Verify the team may use the tool definition.

    Same-team access uses the canonical tool guard (including PRIVATE
    creator-only semantics). Cross-team access requires an explicit share from
    the owning team; the connection itself remains owned by the consuming team
    and never inherits the owner team's identities.
    """
    if tool.team_id == team_id:
        await check_tool_access(tool, user)
        return

    await check_team_access(team_id, user)
    if _tool_visibility(tool) == ToolVisibility.PRIVATE.value:
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="tool_access_denied",
            status_code=403,
        )
    shared = await ToolShare.filter(
        tool_id=tool.id, shared_with_team_id=team_id
    ).exists()
    if not shared:
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="tool_access_denied",
            status_code=403,
        )


async def _assert_builtin_tool(builtin_tool_key: str) -> None:
    # Builtins are global definitions; the team only owns its connection.
    if tool_registry.get_tool(builtin_tool_key) is None:
        from app.llm.tools.builtin import register_all_builtin_tools

        register_all_builtin_tools()
    if tool_registry.get_tool(builtin_tool_key) is None:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_not_found",
            status_code=404,
        )


def _secret_field_declarations(
    tool: Tool,
) -> tuple[set[str] | None, set[str] | None]:
    """Map all encrypted connection fields to allowed/required names.

    ``secret`` controls input masking, not whether a field is accepted.
    ``None`` means the definition declares no restriction.
    """
    declarations = getattr(tool, "connection_fields", None)
    if not declarations:
        return None, None
    declared: set[str] = set()
    required: set[str] = set()
    for item in declarations:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        declared.add(name)
        if item.get("required"):
            required.add(name)
    return declared, required


# ============ Tool-scoped connection APIs ============


@router.get("/{tool_id}/connections", response_model=Response[list[ToolConnectionOut]])
async def list_tool_connections(
    tool_id: UUID,
    team_id: UUID = Query(..., description="Consuming team"),
    include_site: bool = True,
    include_revoked: bool = False,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """List secret-safe connection metadata usable for this tool and team."""
    tool = await _load_tool(tool_id)
    await _assert_tool_access(tool, team_id, current_user)
    connections = await ToolConnectionService.list_connections(
        actor=current_user,
        team_id=team_id,
        tool_id=tool.id,
        include_site=include_site,
        include_revoked=include_revoked,
    )
    return success(data=connections, msg_key="success")


@router.post(
    "/{tool_id}/connections",
    response_model=Response[ToolConnectionOut],
)
async def create_tool_connection(
    tool_id: UUID,
    payload: ToolConnectionForToolCreate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Create a connection for the tool identified by the path."""
    tool = await _load_tool(tool_id)
    # Site connections have no team; site tools are managed by site admins.
    if payload.team_id is not None:
        await _assert_tool_access(tool, payload.team_id, current_user)
    elif not getattr(current_user, "is_superuser", False):
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="permission_denied",
            status_code=403,
        )

    create_payload = ToolConnectionCreate(
        team_id=payload.team_id,
        scope=payload.scope,
        name=payload.name,
        account_label=payload.account_label,
        config=payload.config,
        is_default=payload.is_default,
        tool_id=tool.id,
    )
    declared, required = _secret_field_declarations(tool)
    connection = await ToolConnectionService.create_connection(
        actor=current_user,
        payload=create_payload,
        declared_secret_fields=declared,
        required_secret_fields=required,
    )
    return success(data=connection, msg_key="success")


# ============ Generic connection APIs ============


@connection_router.get("", response_model=Response[list[ToolConnectionOut]])
async def list_connections(
    team_id: UUID = Query(..., description="Team context"),
    tool_id: UUID | None = None,
    builtin_tool_key: str | None = Query(default=None, max_length=100),
    include_site: bool = True,
    include_revoked: bool = False,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """List connections visible to the caller within a team."""
    if tool_id is not None:
        tool = await _load_tool(tool_id)
        await _assert_tool_access(tool, team_id, current_user)
    elif builtin_tool_key:
        await _assert_builtin_tool(builtin_tool_key)

    connections = await ToolConnectionService.list_connections(
        actor=current_user,
        team_id=team_id,
        tool_id=tool_id,
        builtin_tool_key=builtin_tool_key,
        include_site=include_site,
        include_revoked=include_revoked,
    )
    return success(data=connections, msg_key="success")


@connection_router.post("", response_model=Response[ToolConnectionOut])
async def create_connection(
    payload: ToolConnectionCreate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Create a connection for a Tool row or a builtin tool key."""
    tool: Tool | None = None
    if payload.tool_id is not None:
        tool = await _load_tool(payload.tool_id)
        if payload.team_id is not None:
            await _assert_tool_access(tool, payload.team_id, current_user)
        elif not getattr(current_user, "is_superuser", False):
            raise BusinessError(
                code=ResponseCode.PERMISSION_DENIED,
                msg_key="permission_denied",
                status_code=403,
            )
    elif payload.builtin_tool_key:
        await _assert_builtin_tool(payload.builtin_tool_key)

    declared, required = (
        _secret_field_declarations(tool) if tool is not None else (None, None)
    )
    connection = await ToolConnectionService.create_connection(
        actor=current_user,
        payload=payload,
        declared_secret_fields=declared,
        required_secret_fields=required,
    )
    return success(data=connection, msg_key="success")


@connection_router.get("/{connection_id}", response_model=Response[ToolConnectionOut])
async def get_connection(
    connection_id: UUID,
    team_id: UUID | None = Query(
        default=None,
        description="Required to read a site connection as a team member",
    ),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    connection = await ToolConnectionService.get_connection(
        actor=current_user, connection_id=connection_id, team_id=team_id
    )
    return success(data=connection, msg_key="success")


@connection_router.patch("/{connection_id}", response_model=Response[ToolConnectionOut])
async def update_connection(
    connection_id: UUID,
    payload: ToolConnectionUpdate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    current = await ToolConnectionService.get_connection(
        actor=current_user, connection_id=connection_id
    )
    declared: set[str] | None = None
    required: set[str] | None = None
    if current.tool_id is not None:
        tool = await _load_tool(current.tool_id)
        declared, required = _secret_field_declarations(tool)

    connection = await ToolConnectionService.update_connection(
        actor=current_user,
        connection_id=connection_id,
        payload=payload,
        declared_secret_fields=declared,
        required_secret_fields=required,
    )
    return success(data=connection, msg_key="success")


@connection_router.delete(
    "/{connection_id}", response_model=Response[ToolConnectionOut]
)
async def revoke_connection(
    connection_id: UUID,
    reason: str | None = Query(default=None, max_length=500),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Revoke a connection and every grant attached to it (no hard delete)."""
    connection = await ToolConnectionService.revoke_connection(
        actor=current_user, connection_id=connection_id, reason=reason
    )
    return success(data=connection, msg_key="success")


__all__ = ["connection_router", "router"]
