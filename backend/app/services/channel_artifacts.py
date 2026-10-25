"""Conversation-scoped generated artifacts shared by external channels."""

from __future__ import annotations

import json
from uuid import UUID

from app.models.agent import Agent, Message, MessageRole
from app.models.asset import Asset, AssetScopeRef, AssetScopeType
from app.models.user import User
from app.schemas.response import BusinessError
from app.services.asset import asset_service


async def resolve_run_assets(run, agent: Agent, user: User) -> list[Asset]:
    """Collect generated Assets from the run's canonical round only.

    The canonical message must belong to the run's own conversation: a stale
    or forged pointer never widens the artifact set into another chat.
    """
    conversation_id = run.conversation_id
    if not conversation_id or not run.canonical_message_id:
        return []
    canonical = await Message.get_or_none(id=run.canonical_message_id)
    if canonical is None or canonical.conversation_id != conversation_id:
        return []
    # Legacy canonical rows may not carry their round id; the durable run's
    # submission round still identifies its tool results.
    round_id = canonical.round_id or getattr(run, "active_round_id", None)
    refs: list[str] = []
    if round_id is not None:
        tools = (
            await Message.filter(
                conversation_id=conversation_id,
                role=MessageRole.TOOL,
                round_id=round_id,
            )
            .exclude(round_role=None)
            .order_by("round_index", "created_at")
        )
        for message in tools:
            try:
                display = json.loads(message.content)
            except (TypeError, ValueError):
                continue
            if not isinstance(display, dict):
                continue
            refs.extend(display_asset_refs(display))
    assets: list[Asset] = []
    seen: set[UUID] = set()
    for ref in dict.fromkeys(refs):
        try:
            asset = await asset_service.resolve_ref(
                scope_type=AssetScopeType.CONVERSATION,
                scope_id=conversation_id,
                ref=ref,
                team_id=agent.team_id,
                user_id=user.id,
            )
        except BusinessError:
            continue
        if asset.id in seen:
            continue
        seen.add(asset.id)
        assets.append(asset)
    return assets


def display_asset_refs(display: dict) -> list[str]:
    """Extract Asset refs from recognized tool display schemas only."""
    refs: list[str] = []
    kind = display.get("kind")
    if kind == "media.image" and display.get("success"):
        for generated in display.get("images") or []:
            image = generated.get("image") if isinstance(generated, dict) else None
            ref = image.get("asset_ref") if isinstance(image, dict) else None
            if ref:
                refs.append(str(ref))
    elif kind == "media.video" and display.get("success"):
        video = display.get("video")
        ref = video.get("asset_ref") if isinstance(video, dict) else None
        if ref:
            refs.append(str(ref))
    if display.get("success"):
        for artifact in display.get("artifacts") or []:
            ref = artifact.get("asset_ref") if isinstance(artifact, dict) else None
            if ref:
                refs.append(str(ref))
    return refs


async def authorize_output_asset(
    asset_id,
    *,
    conversation_id: UUID,
    agent: Agent,
    user: User,
) -> Asset | None:
    """Authorize a generated Asset for outbound delivery to one channel.

    Stricter than the generic web path: the Asset must be scoped to this exact
    conversation (or attached to a message inside it), so another
    conversation's artifact can never be sent to an external user.
    """
    from app.models.asset import MessageAsset
    from app.services.asset_access import authorize_asset_for_scope

    try:
        asset = await authorize_asset_for_scope(
            UUID(str(asset_id)),
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=conversation_id,
            user=user,
            expected_team_id=agent.team_id,
        )
    except BusinessError:
        return None
    scoped = await AssetScopeRef.filter(
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation_id,
        asset_id=asset.id,
    ).exists()
    if not scoped:
        scoped = await MessageAsset.filter(
            asset_id=asset.id, message__conversation_id=conversation_id
        ).exists()
    return asset if scoped else None


async def read_asset_bytes(asset: Asset) -> bytes:
    """Read authorized Asset bytes through local storage or the upload gateway."""
    from app.api.v1.endpoints.upload import UPLOAD_ROOT
    from app.services.document_processor import document_processor
    from app.services.upload_storage import get_upload_storage_backend

    if document_processor._remote_mode():
        from app.services import upload_gateway

        return await upload_gateway.read(asset.storage_key)
    storage = await get_upload_storage_backend(UPLOAD_ROOT)
    return await storage.read(asset.storage_key)
