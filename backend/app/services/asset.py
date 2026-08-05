"""Registration and authorization boundary for durable Assets."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from tortoise.exceptions import IntegrityError

from app.models.asset import (
    Asset,
    AssetScopeRef,
    AssetScopeType,
    AssetSource,
    AssetStatus,
    MessageAsset,
)
from app.schemas.response import BusinessError, ResponseCode
from app.services.upload_storage import UploadStorageBackend


class AssetService:
    REF_ALPHABET = "0123456789abcdef"
    REF_LENGTH = 4
    REF_ATTEMPTS = 32

    async def register(
        self,
        *,
        storage_key: str,
        original_filename: str,
        content_type: str,
        size: int,
        checksum: str,
        source: AssetSource,
        team_id: UUID | None,
        created_by_id: UUID | None,
        display_filename: str | None = None,
        parent_id: UUID | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> Asset:
        if size < 0 or len(checksum) != 64:
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="validation_error",
            )
        return await Asset.create(
            storage_key=storage_key,
            original_filename=original_filename,
            display_filename=display_filename or original_filename,
            content_type=content_type,
            size=size,
            checksum=checksum.lower(),
            source=source,
            team_id=team_id,
            created_by_id=created_by_id,
            parent_id=parent_id,
            provenance=provenance or {},
        )

    async def register_bytes(
        self,
        *,
        storage_key: str,
        original_filename: str,
        content_type: str,
        content: bytes,
        source: AssetSource,
        team_id: UUID | None,
        created_by_id: UUID | None,
        provenance: dict[str, Any] | None = None,
    ) -> Asset:
        return await self.register(
            storage_key=storage_key,
            original_filename=original_filename,
            content_type=content_type,
            size=len(content),
            checksum=hashlib.sha256(content).hexdigest(),
            source=source,
            team_id=team_id,
            created_by_id=created_by_id,
            provenance=provenance,
        )

    async def attach_to_message(
        self,
        *,
        asset: Asset,
        message_id: UUID,
        role: str = "attachment",
        position: int = 0,
    ) -> MessageAsset:
        link, _ = await MessageAsset.get_or_create(
            message_id=message_id,
            asset_id=asset.id,
            role=role,
            defaults={"position": position},
        )
        return link

    async def copy_message_attachments(
        self,
        *,
        source_message_id: UUID,
        target_message_id: UUID,
    ) -> None:
        links = await MessageAsset.filter(message_id=source_message_id).order_by(
            "position"
        )
        for link in links:
            await MessageAsset.get_or_create(
                message_id=target_message_id,
                asset_id=link.asset_id,
                role=link.role,
                defaults={"position": link.position},
            )

    async def get_authorized(
        self,
        asset_id: UUID,
        *,
        team_id: UUID | None,
        user_id: UUID | None,
    ) -> Asset:
        asset = await Asset.get_or_none(id=asset_id)
        if asset is None or asset.status != AssetStatus.AVAILABLE:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="file_not_found",
                status_code=404,
            )
        if asset.team_id is not None:
            if team_id != asset.team_id:
                raise self._access_denied()
        elif asset.created_by_id is not None and user_id != asset.created_by_id:
            raise self._access_denied()
        return asset

    async def get_or_create_ref(
        self,
        *,
        scope_type: AssetScopeType,
        scope_id: UUID,
        asset: Asset,
    ) -> AssetScopeRef:
        existing = await AssetScopeRef.get_or_none(
            scope_type=scope_type,
            scope_id=scope_id,
            asset_id=asset.id,
        )
        if existing is not None:
            return existing

        for _ in range(self.REF_ATTEMPTS):
            ref = "".join(
                secrets.choice(self.REF_ALPHABET) for _ in range(self.REF_LENGTH)
            )
            try:
                return await AssetScopeRef.create(
                    scope_type=scope_type,
                    scope_id=scope_id,
                    asset_id=asset.id,
                    ref=ref,
                )
            except IntegrityError:
                existing = await AssetScopeRef.get_or_none(
                    scope_type=scope_type,
                    scope_id=scope_id,
                    asset_id=asset.id,
                )
                if existing is not None:
                    return existing

        raise RuntimeError("Unable to allocate a scoped Asset reference")

    async def resolve_ref(
        self,
        *,
        scope_type: AssetScopeType,
        scope_id: UUID,
        ref: str,
        team_id: UUID | None,
        user_id: UUID | None,
    ) -> Asset:
        if len(ref) != self.REF_LENGTH or any(
            char not in self.REF_ALPHABET for char in ref
        ):
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="validation_error",
            )
        binding = await AssetScopeRef.get_or_none(
            scope_type=scope_type,
            scope_id=scope_id,
            ref=ref,
        )
        if binding is None:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="file_not_found",
                status_code=404,
            )
        return await self.get_authorized(
            binding.asset_id,
            team_id=team_id,
            user_id=user_id,
        )

    async def build_conversation_manifest(
        self,
        *,
        conversation_id: UUID,
        team_id: UUID | None,
        user_id: UUID | None,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        links = (
            await MessageAsset.filter(message__conversation_id=conversation_id)
            .prefetch_related("asset")
            .order_by("-message__created_at", "position")
            .limit(limit)
        )
        manifest: list[dict[str, Any]] = []
        seen: set[UUID] = set()
        for link in links:
            if link.asset_id in seen:
                continue
            try:
                asset = await self.get_authorized(
                    link.asset_id,
                    team_id=team_id,
                    user_id=user_id,
                )
            except BusinessError:
                seen.add(link.asset_id)
                continue
            binding = await self.get_or_create_ref(
                scope_type=AssetScopeType.CONVERSATION,
                scope_id=conversation_id,
                asset=asset,
            )
            manifest.append(
                {
                    "ref": binding.ref,
                    "name": asset.display_filename,
                    "type": asset.content_type,
                    "size": asset.size,
                    "origin": asset.source.value,
                    "capabilities": self.capabilities(asset),
                }
            )
            seen.add(link.asset_id)

        if len(manifest) < limit:
            bindings = (
                await AssetScopeRef.filter(
                    scope_type=AssetScopeType.CONVERSATION,
                    scope_id=conversation_id,
                )
                .prefetch_related("asset")
                .order_by("-created_at")
                .limit(limit - len(manifest))
            )
            for binding in bindings:
                if binding.asset_id in seen:
                    continue
                try:
                    asset = await self.get_authorized(
                        binding.asset_id,
                        team_id=team_id,
                        user_id=user_id,
                    )
                except BusinessError:
                    seen.add(binding.asset_id)
                    continue
                manifest.append(
                    {
                        "ref": binding.ref,
                        "name": asset.display_filename,
                        "type": asset.content_type,
                        "size": asset.size,
                        "origin": asset.source.value,
                        "capabilities": self.capabilities(asset),
                    }
                )
                seen.add(binding.asset_id)
        return manifest

    @staticmethod
    def capabilities(asset: Asset) -> list[str]:
        from app.services.file_parser import file_parser_service

        capabilities = ["inspect", "sandbox"]
        content_type = asset.content_type.lower()
        if content_type.startswith("text/") or content_type in {
            "application/json",
            "application/xml",
        }:
            capabilities.append("read")
        if file_parser_service.is_supported(asset.original_filename):
            capabilities.append("parse")
        if content_type.startswith("image/"):
            capabilities.extend(["vision", "generate"])
        return capabilities

    @staticmethod
    def format_manifest(manifest: list[dict[str, Any]]) -> str:
        if not manifest:
            return (
                "<available_assets>\n"
                "No attachments are available in this conversation. "
                "Do not call Asset tools or guess refs.\n"
                "</available_assets>"
            )
        lines = [
            "<available_assets>",
            (
                "Use the exact 4-character ref with Asset tools or "
                "reference_image_refs for image generation. Do not guess refs."
            ),
        ]
        for item in manifest:
            capabilities = ",".join(item["capabilities"])
            lines.append(
                f"{item['ref']} | {item['name']} | {item['type']} | "
                f"{item['size']}B | {item['origin']} | {capabilities}"
            )
        lines.append("</available_assets>")
        return "\n".join(lines)

    async def read(
        self,
        asset: Asset,
        *,
        storage: UploadStorageBackend,
    ) -> bytes:
        content = await storage.read(asset.storage_key)
        if (
            len(content) != asset.size
            or hashlib.sha256(content).hexdigest() != asset.checksum
        ):
            raise RuntimeError("Stored Asset content does not match its metadata")
        return content

    async def mark_deleted(self, asset: Asset) -> None:
        asset.status = AssetStatus.DELETED
        asset.deleted_at = datetime.now(UTC)
        await asset.save(update_fields=["status", "deleted_at", "updated_at"])

    @staticmethod
    def _access_denied() -> BusinessError:
        return BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="access_denied",
            status_code=403,
        )


asset_service = AssetService()
