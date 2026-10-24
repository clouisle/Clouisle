"""Authorization for protected generated assets."""

from __future__ import annotations
from uuid import UUID


from app.api.conversation_access import can_access_conversation
from app.api.deps import check_api_key_agent_access, check_api_key_workflow_access
from app.models.agent import Conversation
from app.models.api_key import APIKey
from app.models.asset import (
    Asset,
    AssetScopeRef,
    AssetScopeType,
    AssetStatus,
)
from app.models.user import User
from app.models.workflow import WorkflowRun
from app.schemas.response import BusinessError, ResponseCode


PROTECTED_FILE_CATEGORIES = frozenset(
    {"agent-attachments", "sandbox-artifacts", "generated-images", "generated-videos"}
)


async def authorize_asset_for_scope(
    asset_id: UUID,
    *,
    scope_type: AssetScopeType,
    scope_id: UUID,
    user: User | None,
    api_key: APIKey | None = None,
    expected_team_id: UUID | None = None,
) -> Asset:
    """Authorize an Asset against its owner/team and execution scope."""
    team_id = await authorize_asset_scope(
        scope_type=scope_type,
        scope_id=scope_id,
        user=user,
        api_key=api_key,
        expected_team_id=expected_team_id,
    )
    from app.services.asset import asset_service

    return await asset_service.get_authorized(
        asset_id,
        team_id=team_id,
        user_id=user.id if user is not None else None,
    )


async def resolve_authorized_asset_ref(
    ref: str,
    *,
    scope_type: AssetScopeType,
    scope_id: UUID,
    user: User | None,
    api_key: APIKey | None = None,
    expected_team_id: UUID | None = None,
) -> Asset:
    """Resolve a scope-local ref after authorizing its conversation or run."""
    team_id = await authorize_asset_scope(
        scope_type=scope_type,
        scope_id=scope_id,
        user=user,
        api_key=api_key,
        expected_team_id=expected_team_id,
    )
    from app.services.asset import asset_service

    asset = await asset_service.resolve_ref(
        scope_type=scope_type,
        scope_id=scope_id,
        ref=ref,
        team_id=team_id,
        user_id=user.id if user is not None else None,
    )
    if scope_type == AssetScopeType.CONVERSATION:
        from app.models.asset import MessageAsset

        links = MessageAsset.filter(
            asset_id=asset.id, message__conversation_id=scope_id
        )
        if (
            await links.exists()
            and not await links.filter(message__is_active=True).exists()
        ):
            raise _not_found()
    return asset


async def list_authorized_assets(
    *,
    scope_type: AssetScopeType,
    scope_id: UUID,
    user: User | None,
    expected_team_id: UUID | None = None,
    query: str = "",
    kind: str | None = None,
    cursor: str | None = None,
    limit: int = 10,
) -> dict:
    """Discover scope-local assets without reading bytes or crossing branches."""
    from datetime import UTC, datetime
    from tortoise.expressions import Q, Subquery
    from app.models.asset import MessageAsset
    from app.services.asset import asset_service

    team_id = await authorize_asset_scope(
        scope_type=scope_type,
        scope_id=scope_id,
        user=user,
        api_key=None,
        expected_team_id=expected_team_id,
    )
    if type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError("limit must be between 1 and 30")
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("query must be a filename substring of at most 200 characters")
    if kind not in (None, "image", "audio", "video", "file"):
        raise ValueError("kind must be image, audio, video, or file")
    if cursor is not None and (
        not isinstance(cursor, str)
        or len(cursor) != 4
        or any(c not in "0123456789abcdef" for c in cursor)
    ):
        raise ValueError("cursor must be a ref returned by list_assets")
    bindings = AssetScopeRef.filter(
        scope_type=scope_type,
        scope_id=scope_id,
        asset__status=AssetStatus.AVAILABLE,
    ).filter(
        Q(asset__expires_at__isnull=True) | Q(asset__expires_at__gt=datetime.now(UTC))
    )
    owner = Q(asset__created_by_id__isnull=True)
    if user is not None:
        owner |= Q(asset__created_by_id=user.id)
    access = Q(asset__team_id__isnull=True) & owner
    if team_id is not None:
        access |= Q(asset__team_id=team_id)
    bindings = bindings.filter(access)
    if scope_type == AssetScopeType.CONVERSATION:
        active = MessageAsset.filter(
            message__conversation_id=scope_id, message__is_active=True
        ).values("asset_id")
        hidden = (
            MessageAsset.filter(message__conversation_id=scope_id)
            .exclude(asset_id__in=Subquery(active))
            .values("asset_id")
        )
        bindings = bindings.exclude(asset_id__in=Subquery(hidden))
    if query.strip():
        bindings = bindings.filter(
            Q(asset__display_filename__icontains=query.strip())
            | Q(asset__original_filename__icontains=query.strip())
        )
    if kind in {"image", "audio", "video"}:
        bindings = bindings.filter(asset__content_type__istartswith=f"{kind}/")
    elif kind == "file":
        bindings = bindings.exclude(
            Q(asset__content_type__istartswith="image/")
            | Q(asset__content_type__istartswith="audio/")
            | Q(asset__content_type__istartswith="video/")
        )
    if cursor:
        bindings = bindings.filter(ref__gt=cursor)
    rows = await bindings.order_by("ref").prefetch_related("asset").limit(limit + 1)
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "items": [
            {
                "ref": row.ref,
                "name": row.asset.display_filename,
                "type": row.asset.content_type,
                "size": row.asset.size,
                "origin": row.asset.source.value,
                "created_at": row.asset.created_at.isoformat(),
                "capabilities": asset_service.capabilities(row.asset),
            }
            for row in page
        ],
        "has_more": has_more,
        "next_cursor": page[-1].ref if has_more else None,
    }


async def authorize_asset_scope(
    *,
    scope_type: AssetScopeType,
    scope_id: UUID,
    user: User | None,
    api_key: APIKey | None = None,
    expected_team_id: UUID | None = None,
) -> UUID | None:
    """Authorize the execution scope itself and return its team id.

    Call this before any attachment fetch or storage write so network and disk
    IO only happen for callers allowed to use the conversation/run.
    """
    if scope_type == AssetScopeType.CONVERSATION:
        conversation = (
            await Conversation.filter(id=scope_id).prefetch_related("agent").first()
        )
        if conversation is None or conversation.agent is None:
            raise _not_found()
        if user is None or not await can_access_conversation(conversation, user):
            raise _access_denied()
        try:
            await check_api_key_agent_access(api_key, conversation.agent_id)
        except BusinessError as error:
            if error.msg_key == "api_key_no_agent_access":
                raise _access_denied() from error
            raise
        team_id = conversation.agent.team_id
    elif scope_type == AssetScopeType.WORKFLOW_RUN:
        run = await WorkflowRun.filter(id=scope_id).prefetch_related("workflow").first()
        if run is None or run.workflow is None or run.workflow_id is None:
            raise _not_found()
        if user is not None and not await _can_access_workflow_run(run, user):
            raise _access_denied()
        try:
            await check_api_key_workflow_access(api_key, run.workflow_id)
        except BusinessError as error:
            if error.msg_key == "api_key_no_workflow_access":
                raise _access_denied() from error
            raise
        team_id = run.workflow.team_id
    else:
        raise _not_found()

    if expected_team_id is not None and team_id != expected_team_id:
        raise _access_denied()
    return team_id


def _access_denied() -> BusinessError:
    return BusinessError(
        code=ResponseCode.PERMISSION_DENIED,
        msg_key="access_denied",
        status_code=403,
    )


async def authorize_protected_asset(
    storage_key: str,
    *,
    authenticated: tuple[User, APIKey | None] | None,
) -> Asset:
    """Authorize a protected file through any valid Asset scope."""
    if authenticated is None:
        raise BusinessError(
            code=ResponseCode.UNAUTHORIZED,
            msg_key="not_authenticated",
            status_code=401,
        )

    user, api_key = authenticated
    from app.models.asset import AssetSource

    asset = await Asset.filter(
        storage_key=storage_key,
        status=AssetStatus.AVAILABLE,
    ).first()
    if asset is None or getattr(asset, "source", None) == AssetSource.DERIVED_TEXT:
        raise _not_found()

    refs = await AssetScopeRef.filter(asset_id=asset.id)
    if not refs:
        if user.is_superuser or (
            api_key is None and getattr(asset, "created_by_id", None) == user.id
        ):
            return asset
        raise _not_found()

    for ref in refs:
        try:
            await authorize_asset_for_scope(
                asset.id,
                scope_type=ref.scope_type,
                scope_id=ref.scope_id,
                user=user,
                api_key=api_key,
            )
        except BusinessError as error:
            if error.status_code in (403, 404):
                continue
            raise
        return asset

    raise _access_denied()


async def _can_access_workflow_run(run: WorkflowRun, user: User) -> bool:
    from app.api.workflow_access import check_workflow_access

    if run.triggered_by_id == user.id or user.is_superuser:
        return True
    try:
        await check_workflow_access(run.workflow_id, user)
    except BusinessError:
        return False
    return True


def _not_found() -> BusinessError:
    return BusinessError(
        code=ResponseCode.NOT_FOUND,
        msg_key="file_not_found",
        status_code=404,
    )
