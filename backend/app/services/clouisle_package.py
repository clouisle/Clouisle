"""Clouisle package import/export service.

Builds and parses `.clouisle` ZIP packages and orchestrates per-resource
adapters for export, preview, and install.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import shutil
import tempfile
import zipfile
from datetime import UTC, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.core.config import settings
from app.core.timezone import now_utc
from app.models.package_import import (
    ClouisleImportSession,
    ClouisleImportSessionStatus,
    ClouisleImportSource,
)
from app.models.user import Team, TeamMember, User
from app.schemas.clouisle_package import (
    ClouisleConflictAction,
    ClouisleImportInstallOut,
    ClouisleImportInstallRequest,
    ClouisleImportPreviewOut,
    ClouisleManifest,
    ClouisleResourceType,
)
from app.schemas.response import BusinessError, ResponseCode

logger = logging.getLogger(__name__)

FORMAT_VERSION = "1"
SESSION_TTL_MINUTES = 30

MANIFEST_FILENAME = "manifest.json"
RESOURCE_FILENAME = "resources/resource.json"
CHECKSUMS_FILENAME = "checksums.json"

_MAX_PACKAGE_BYTES = 50 * 1024 * 1024  # 50 MiB compressed upload
_MAX_TOTAL_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200 MiB extracted
_MAX_FILE_COUNT = 2000

# Field-name fragments that must never carry a plaintext value in a package.
_SENSITIVE_FIELD_FRAGMENTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
    "authorization",
)


def _is_placeholder(value: str) -> bool:
    """A value that only references an environment variable is safe to export."""
    stripped = value.strip()
    if not stripped:
        return True
    return "{{" in stripped and "}}" in stripped


def _scan_for_plaintext_secrets(
    payload: Any, path: str = "", parent_is_sensitive: bool = False
) -> list[str]:
    """Return dotted paths of fields that look like plaintext secrets."""
    findings: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_lower = str(key).lower()
            current = f"{path}.{key}" if path else str(key)
            is_sensitive = parent_is_sensitive or any(
                frag in key_lower for frag in _SENSITIVE_FIELD_FRAGMENTS
            )
            if isinstance(value, str) and value.strip():
                if is_sensitive and not _is_placeholder(value):
                    findings.append(current)
            findings.extend(_scan_for_plaintext_secrets(value, current, is_sensitive))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            findings.extend(
                _scan_for_plaintext_secrets(
                    item, f"{path}[{index}]", parent_is_sensitive
                )
            )
    elif isinstance(payload, str) and payload.strip():
        if parent_is_sensitive and not _is_placeholder(payload):
            findings.append(path)
    return findings


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class ClouislePackageService:
    """Stateless helpers + session-backed preview/install for `.clouisle`."""

    # ------------------------------------------------------------------ build

    @staticmethod
    def build_package(
        *,
        resource_type: ClouisleResourceType,
        resource_id: str,
        resource_name: str,
        resource_payload: dict[str, Any],
        dependencies: list[dict[str, Any]],
        files: dict[str, bytes] | None = None,
    ) -> bytes:
        """Serialize a single resource into `.clouisle` ZIP bytes."""
        files = files or {}
        resource_bytes = json.dumps(
            resource_payload, ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8")
        checksums = {RESOURCE_FILENAME: _sha256(resource_bytes)}
        for path, content in files.items():
            checksums[path] = _sha256(content)
        checksums_bytes = json.dumps(
            checksums, ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8")

        manifest = {
            "format_version": FORMAT_VERSION,
            "app_version": settings.PROJECT_NAME and _app_version(),
            "package_id": str(uuid4()),
            "exported_at": now_utc().isoformat(),
            "resource_type": resource_type.value,
            "resource_name": resource_name,
            "resource_id": str(resource_id),
            "dependencies": dependencies,
            "checksums": checksums,
        }
        manifest_bytes = json.dumps(
            manifest, ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8")

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(MANIFEST_FILENAME, manifest_bytes)
            zf.writestr(RESOURCE_FILENAME, resource_bytes)
            for path, content in files.items():
                zf.writestr(path, content)
            zf.writestr(CHECKSUMS_FILENAME, checksums_bytes)
        return buffer.getvalue()

    @staticmethod
    def export_filename(resource_type: ClouisleResourceType, slug: str) -> str:
        safe_slug = _slugify(slug) or resource_type.value
        timestamp = now_utc().strftime("%Y%m%d%H%M%S")
        return f"{resource_type.value}-{safe_slug}-{timestamp}.clouisle"

    # --------------------------------------------------------------- validate

    @staticmethod
    def _read_package(
        filename: str, content: bytes
    ) -> tuple[ClouisleManifest, dict[str, Any]]:
        """Validate envelope and return (manifest, resource_payload)."""
        if not filename.lower().endswith(".clouisle"):
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="clouisle_invalid_extension",
            )
        if len(content) > _MAX_PACKAGE_BYTES:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="clouisle_zip_too_large",
            )

        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="clouisle_invalid_zip",
            )

        with zf:
            infos = zf.infolist()
            if len(infos) > _MAX_FILE_COUNT:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="clouisle_invalid_zip",
                )
            total_uncompressed = 0
            for info in infos:
                name = info.filename
                if name.startswith("/") or ".." in _path_parts(name):
                    raise BusinessError(
                        code=ResponseCode.BAD_REQUEST,
                        msg_key="clouisle_zip_path_invalid",
                    )
                total_uncompressed += info.file_size
                if total_uncompressed > _MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise BusinessError(
                        code=ResponseCode.BAD_REQUEST,
                        msg_key="clouisle_zip_too_large",
                    )

            names = set(zf.namelist())
            if MANIFEST_FILENAME not in names:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="clouisle_missing_manifest",
                )
            if RESOURCE_FILENAME not in names:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="clouisle_missing_resource",
                )
            if CHECKSUMS_FILENAME not in names:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="clouisle_checksum_mismatch",
                )

            manifest_raw = zf.read(MANIFEST_FILENAME)
            resource_raw = zf.read(RESOURCE_FILENAME)
            checksums_raw = zf.read(CHECKSUMS_FILENAME)

        try:
            manifest_data = json.loads(manifest_raw)
        except json.JSONDecodeError:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="clouisle_missing_manifest",
            )

        try:
            manifest = ClouisleManifest.model_validate(manifest_data)
        except Exception:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="clouisle_invalid_resource_type",
            )

        if manifest.format_version != FORMAT_VERSION:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="clouisle_unsupported_format_version",
            )

        expected = manifest.checksums.get(RESOURCE_FILENAME)
        if not expected or expected != _sha256(resource_raw):
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="clouisle_checksum_mismatch",
            )

        with zipfile.ZipFile(io.BytesIO(content)) as checksum_zf:
            for path, expected_hash in manifest.checksums.items():
                if path == RESOURCE_FILENAME:
                    continue
                if path not in names:
                    raise BusinessError(
                        code=ResponseCode.BAD_REQUEST,
                        msg_key="clouisle_checksum_mismatch",
                    )
                if expected_hash != _sha256(checksum_zf.read(path)):
                    raise BusinessError(
                        code=ResponseCode.BAD_REQUEST,
                        msg_key="clouisle_checksum_mismatch",
                    )

        if CHECKSUMS_FILENAME in names:
            try:
                checksum_manifest = json.loads(checksums_raw)
            except json.JSONDecodeError:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="clouisle_checksum_mismatch",
                )
            if checksum_manifest != manifest.checksums:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="clouisle_checksum_mismatch",
                )

        try:
            resource_payload = json.loads(resource_raw)
        except json.JSONDecodeError:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="clouisle_missing_resource",
            )
        if not isinstance(resource_payload, dict):
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="clouisle_missing_resource",
            )

        secrets = _scan_for_plaintext_secrets(resource_payload)
        if secrets:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="clouisle_plaintext_secret_detected",
            )

        return manifest, resource_payload

    # ---------------------------------------------------------------- preview

    @staticmethod
    async def _check_team_access(
        team_id: UUID, user: User, require_admin: bool = False
    ) -> Team:
        team = await Team.filter(id=team_id).first()
        if not team:
            raise BusinessError(
                code=ResponseCode.TEAM_NOT_FOUND,
                msg_key="team_not_found",
                status_code=404,
            )
        if user.is_superuser:
            return team
        membership = await TeamMember.filter(team=team, user=user).first()
        if not membership:
            raise BusinessError(
                code=ResponseCode.NOT_TEAM_MEMBER,
                msg_key="not_team_member",
                status_code=403,
            )
        if require_admin and membership.role not in ("owner", "admin"):
            raise BusinessError(
                code=ResponseCode.TEAM_ADMIN_REQUIRED,
                msg_key="team_admin_required",
                status_code=403,
            )
        return team

    @staticmethod
    async def preview(
        *,
        team_id: UUID,
        user: User,
        filename: str,
        content: bytes,
        source: ClouisleImportSource = ClouisleImportSource.PLATFORM,
        check_permission: bool = True,
        check_team_membership: bool = True,
    ) -> ClouisleImportPreviewOut:
        from app.services.clouisle_package_resources import get_adapter

        if check_team_membership:
            team = await ClouislePackageService._check_team_access(team_id, user)
        else:
            team = await Team.filter(id=team_id).first()
            if not team:
                raise BusinessError(
                    code=ResponseCode.TEAM_NOT_FOUND,
                    msg_key="team_not_found",
                    status_code=404,
                )
        manifest, resource_payload = ClouislePackageService._read_package(
            filename, content
        )

        adapter = get_adapter(manifest.resource_type)
        if check_permission:
            adapter.ensure_import_permission(user)
        temp_storage_path = ClouislePackageService._stage_package_files(
            content, manifest
        )

        dependencies = await adapter.resolve_dependencies(
            manifest=manifest, team_id=team.id, user=user
        )
        conflict = await adapter.detect_conflict(
            resource_payload=resource_payload, team_id=team.id
        )

        errors: list[str] = []
        warnings: list[str] = []
        for dep in dependencies:
            if dep.status and dep.status.value == "forbidden":
                errors.append(dep.message or "clouisle_dependency_forbidden")
            elif dep.required and dep.status and dep.status.value == "missing":
                errors.append(dep.message or "clouisle_dependency_missing")
            elif dep.status and dep.status.value in ("missing", "unsupported"):
                warnings.append(dep.message or "clouisle_dependency_missing")

        valid = not errors

        allowed_actions = [ClouisleConflictAction.RENAME, ClouisleConflictAction.SKIP]
        default_action = ClouisleConflictAction.INSTALL
        if conflict and conflict.type != "none":
            allowed_actions = [
                ClouisleConflictAction.RENAME,
                ClouisleConflictAction.UPDATE,
                ClouisleConflictAction.SKIP,
            ]
            default_action = ClouisleConflictAction.RENAME
        else:
            allowed_actions = [ClouisleConflictAction.INSTALL]

        session = await ClouisleImportSession.create(
            team=team,
            resource_type=manifest.resource_type.value,
            resource_name=manifest.resource_name,
            package_id=manifest.package_id,
            source=source,
            status=ClouisleImportSessionStatus.PREVIEWED,
            manifest=manifest.model_dump(mode="json"),
            resource_payload=resource_payload,
            preview={},
            temp_storage_path=temp_storage_path,
            package_checksum=_sha256(content),
            expires_at=now_utc() + timedelta(minutes=SESSION_TTL_MINUTES),
            created_by=user,
        )

        result = ClouisleImportPreviewOut(
            session_id=session.id,
            package_id=manifest.package_id,
            resource_type=manifest.resource_type,
            resource_name=manifest.resource_name,
            source_resource_id=manifest.resource_id,
            format_version=manifest.format_version,
            app_version=manifest.app_version,
            exported_at=manifest.exported_at,
            valid=valid,
            errors=errors,
            warnings=warnings,
            dependencies=dependencies,
            conflict=conflict,
            allowed_actions=allowed_actions,
            default_action=default_action,
        )

        session.preview = result.model_dump(mode="json")
        await session.save(update_fields=["preview", "updated_at"])
        return result

    @staticmethod
    def _stage_package_files(content: bytes, manifest: ClouisleManifest) -> str | None:
        file_paths = [
            path
            for path in manifest.checksums
            if path != RESOURCE_FILENAME and path != CHECKSUMS_FILENAME
        ]
        if not file_paths:
            return None
        temp_dir = Path(tempfile.mkdtemp(prefix="clouisle-import-")).resolve()
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for path in file_paths:
                    target = temp_dir.joinpath(*_path_parts(path)).resolve()
                    if temp_dir != target and temp_dir not in target.parents:
                        raise BusinessError(
                            code=ResponseCode.BAD_REQUEST,
                            msg_key="clouisle_zip_path_invalid",
                        )
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(path))
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        return str(temp_dir)

    # ---------------------------------------------------------------- install

    @staticmethod
    async def install(
        *,
        session_id: UUID,
        user: User,
        install_in: ClouisleImportInstallRequest,
        source: ClouisleImportSource = ClouisleImportSource.PLATFORM,
        check_permission: bool = True,
        check_team_membership: bool = True,
    ) -> ClouisleImportInstallOut:
        from app.services.clouisle_package_resources import get_adapter

        session = await ClouisleImportSession.filter(id=session_id).first()
        if not session:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="clouisle_import_session_not_found",
                status_code=404,
            )
        if session.status != ClouisleImportSessionStatus.PREVIEWED:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="clouisle_import_session_not_found",
            )
        if session.source != source:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="clouisle_import_session_not_found",
                status_code=404,
            )
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < now_utc():
            session.status = ClouisleImportSessionStatus.EXPIRED
            await session.save(update_fields=["status", "updated_at"])
            ClouislePackageService._cleanup_staged_package(session.temp_storage_path)
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="clouisle_import_session_expired",
            )

        if check_team_membership:
            team = await ClouislePackageService._check_team_access(
                session.team_id, user
            )
        else:
            team = await Team.filter(id=session.team_id).first()
            if not team:
                raise BusinessError(
                    code=ResponseCode.TEAM_NOT_FOUND,
                    msg_key="team_not_found",
                    status_code=404,
                )
        resource_type = ClouisleResourceType(session.resource_type)
        adapter = get_adapter(resource_type)
        if check_permission:
            if install_in.action == ClouisleConflictAction.UPDATE:
                adapter.ensure_update_permission(user)
            elif install_in.action != ClouisleConflictAction.SKIP:
                adapter.ensure_import_permission(user)

        if install_in.action == ClouisleConflictAction.SKIP:
            session.status = ClouisleImportSessionStatus.INSTALLED
            await session.save(update_fields=["status", "updated_at"])
            ClouislePackageService._cleanup_staged_package(session.temp_storage_path)
            return ClouisleImportInstallOut(skipped=True)

        manifest = ClouisleManifest.model_validate(session.manifest)
        for dep in session.preview.get("dependencies", []):
            status = dep.get("status")
            if dep.get("required") and status in {"missing", "forbidden"}:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key=(
                        "clouisle_dependency_forbidden"
                        if status == "forbidden"
                        else "clouisle_dependency_missing"
                    ),
                )
        mapping = dict(install_in.dependency_mapping)
        for dep in session.preview.get("dependencies", []):
            source_id = dep.get("source_id")
            matched_id = dep.get("matched_id")
            if source_id and matched_id and source_id not in mapping:
                mapping[source_id] = UUID(str(matched_id))
        install_in = install_in.model_copy(update={"dependency_mapping": mapping})
        package_dir = (
            Path(session.temp_storage_path) if session.temp_storage_path else None
        )
        try:
            resource_payload = await adapter.materialize_files(
                session.resource_payload,
                package_dir,
            )
            result = await adapter.install(
                manifest=manifest,
                resource_payload=resource_payload,
                team=team,
                user=user,
                install_in=install_in,
                package_dir=package_dir,
                check_update_permission=check_permission,
            )
        except BusinessError:
            session.status = ClouisleImportSessionStatus.FAILED
            await session.save(update_fields=["status", "updated_at"])
            ClouislePackageService._cleanup_staged_package(session.temp_storage_path)
            raise

        session.status = ClouisleImportSessionStatus.INSTALLED
        await session.save(update_fields=["status", "updated_at"])
        ClouislePackageService._cleanup_staged_package(session.temp_storage_path)
        return result

    @staticmethod
    async def cleanup_expired_sessions() -> int:
        expired_sessions = await ClouisleImportSession.filter(
            status=ClouisleImportSessionStatus.PREVIEWED,
            expires_at__lt=now_utc(),
        )
        cleaned = 0
        for session in expired_sessions:
            ClouislePackageService._cleanup_staged_package(session.temp_storage_path)
            session.status = ClouisleImportSessionStatus.EXPIRED
            await session.save(update_fields=["status", "updated_at"])
            cleaned += 1
        return cleaned

    @staticmethod
    def _cleanup_staged_package(temp_storage_path: str | None) -> None:
        if not temp_storage_path:
            return
        temp_path = Path(temp_storage_path).resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()
        if temp_path == temp_root or temp_root not in temp_path.parents:
            return
        shutil.rmtree(temp_path, ignore_errors=True)


def _app_version() -> str:
    try:
        from importlib.metadata import version

        return version("clouisle-backend")
    except Exception:
        return "0.1.0"


def _slugify(value: str) -> str:
    cleaned = []
    for char in value.strip().lower():
        if char.isalnum():
            cleaned.append(char)
        elif char in (" ", "-", "_"):
            cleaned.append("-")
    slug = "".join(cleaned).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:60]


def _path_parts(name: str) -> list[str]:
    return name.replace("\\", "/").split("/")
