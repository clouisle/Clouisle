"""OAuth start/status and one-time browser callback endpoints.

The callback is intentionally state-bound rather than bearer-token-bound: an
OAuth provider redirect arrives in a browser without the SPA's Authorization
header. The unguessable, single-use state is bound to the logged-in user and a
concrete connection when the flow starts, is stored only as a hash, and expires
after ten minutes. No token or provider error detail is ever echoed into the
redirect.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import RedirectResponse

from app.api import deps
from app.models.user import User
from app.schemas.response import Response, success
from app.schemas.tool_oauth import (
    OAuthConnectionStatusOut,
    OAuthDisconnectOut,
    OAuthStartOut,
    OAuthStartRequest,
)
from app.services.tool_oauth import ToolOAuthService

router = APIRouter()
callback_router = APIRouter()


@router.post(
    "/{connection_id}/oauth/start",
    response_model=Response[OAuthStartOut],
)
async def start_tool_oauth(
    connection_id: UUID,
    payload: OAuthStartRequest | None = Body(default=None),
    current_user: User = Depends(deps.get_current_user),
) -> dict:
    """Create a one-time PKCE flow for an existing connection.

    ``client_secret`` is write-only, requires tool write access and is stored
    encrypted on the provider row; it is never returned.
    """
    request = payload or OAuthStartRequest()
    result = await ToolOAuthService.start_authorization(
        actor=current_user,
        connection_id=connection_id,
        redirect_path=request.redirect_path,
        client_secret=request.client_secret,
    )
    return success(data=result, msg_key="success")


@router.get(
    "/{connection_id}/oauth",
    response_model=Response[OAuthConnectionStatusOut],
)
async def get_tool_oauth_status(
    connection_id: UUID,
    team_id: UUID | None = Query(default=None),
    current_user: User = Depends(deps.get_current_user),
) -> dict:
    """Return secret-free OAuth state for a connection."""
    status = await ToolOAuthService.get_status(
        actor=current_user,
        connection_id=connection_id,
        team_id=team_id,
    )
    return success(data=status, msg_key="success")


@router.post(
    "/{connection_id}/oauth/disconnect",
    response_model=Response[OAuthDisconnectOut],
)
async def disconnect_tool_oauth(
    connection_id: UUID,
    current_user: User = Depends(deps.get_current_user),
) -> dict:
    """Clear local tokens; attempt provider revocation best effort.

    Remote failure or an unsupported provider never blocks the local revoke and
    is reported explicitly in ``remote_revocation``.
    """
    result = await ToolOAuthService.disconnect(
        actor=current_user, connection_id=connection_id
    )
    return success(data=result, msg_key="success")


@callback_router.get("/callback")
async def tool_oauth_callback(
    code: str | None = Query(default=None, max_length=4096),
    state: str | None = Query(default=None, max_length=512),
    error: str | None = Query(default=None, max_length=200),
    error_description: str | None = Query(default=None, max_length=500),
) -> RedirectResponse:
    """Consume the one-time state and exchange the authorization code.

    Always redirects to an allowlisted frontend path; provider errors and
    internal failures are mapped to stable error keys without exposing tokens.
    """
    redirect_url = await ToolOAuthService.handle_callback(
        state=state,
        code=code,
        error=error,
        error_description=error_description,
    )
    return RedirectResponse(
        url=redirect_url,
        status_code=302,
        headers={"Cache-Control": "no-store"},
    )


__all__ = ["callback_router", "router"]
