"""Skill package import service."""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import shutil
import stat
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from uuid import UUID

from app.models.skill import (
    Skill,
    SkillImportSession,
    SkillImportSessionStatus,
    SkillSourceType,
)
from app.models.user import User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.skill import (
    SkillConflict,
    SkillImportInstallItem,
    SkillImportInstallOut,
    SkillImportPreviewOut,
    SkillInstallAction,
    SkillPreviewItem,
)
from app.services.skill import SkillService
from app.services.skill_package import (
    IGNORED_DIR_NAMES,
    NESTED_ARCHIVE_SUFFIXES,
    ParsedSkillPackage,
    SkillPackageService,
)

_MAX_ZIP_FILE_COUNT = 500
_MAX_ZIP_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
_MAX_ZIP_SINGLE_FILE_BYTES = 10 * 1024 * 1024
_MAX_PACKAGE_PAYLOAD_BYTES = 50 * 1024 * 1024
_IMPORT_SESSION_TTL = timedelta(hours=1)
_GIT_TIMEOUT_SECONDS = 180


class SkillImportService:
    """Preview and install package-backed Skills from zip or Git."""

    @staticmethod
    async def preview_zip(
        *,
        team_id: UUID | None,
        user: User,
        filename: str,
        content: bytes,
    ) -> SkillImportPreviewOut:
        team = None
        if team_id is not None:
            team = await SkillService.check_team_access(
                team_id, user, require_admin=True
            )
        elif not user.is_superuser:
            raise BusinessError(
                code=ResponseCode.PERMISSION_DENIED,
                msg_key="skill_system_admin_required",
                status_code=403,
            )

        if not filename.lower().endswith(".zip"):
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST, msg_key="skill_zip_required"
            )

        temp_root = Path(tempfile.mkdtemp(prefix="clouisle-skill-import-"))
        zip_path = temp_root / "source.zip"
        extract_root = temp_root / "source"
        extract_root.mkdir(parents=True, exist_ok=True)
        zip_path.write_bytes(content)

        SkillImportService._extract_zip(zip_path, extract_root)
        return await SkillImportService._create_preview_session(
            team_id=team_id,
            team=team,
            user=user,
            source_type=SkillSourceType.ZIP,
            source_uri=filename,
            source_ref=None,
            source_subdir=None,
            source_root=extract_root,
            temp_storage_path=temp_root,
        )

    @staticmethod
    async def preview_git(
        *,
        team_id: UUID | None,
        user: User,
        repo_url: str,
        ref: str | None = None,
    ) -> SkillImportPreviewOut:
        team = None
        if team_id is not None:
            team = await SkillService.check_team_access(
                team_id, user, require_admin=True
            )
        elif not user.is_superuser:
            raise BusinessError(
                code=ResponseCode.PERMISSION_DENIED,
                msg_key="skill_system_admin_required",
                status_code=403,
            )

        SkillImportService._validate_git_url(repo_url)

        temp_root = Path(tempfile.mkdtemp(prefix="clouisle-skill-import-"))
        repo_root = temp_root / "repo"
        await SkillImportService._clone_git_repo(repo_url, ref, repo_root)
        resolved_ref = await SkillImportService._resolve_git_ref(repo_root)
        return await SkillImportService._create_preview_session(
            team_id=team_id,
            team=team,
            user=user,
            source_type=SkillSourceType.GIT,
            source_uri=SkillImportService._redact_url(repo_url),
            source_ref=resolved_ref or ref,
            source_subdir=None,
            source_root=repo_root,
            temp_storage_path=temp_root,
        )

    @staticmethod
    async def install_from_session(
        *,
        session_id: UUID,
        items: list[SkillImportInstallItem],
        is_enabled: bool,
        user: User,
    ) -> SkillImportInstallOut:
        session = await SkillImportSession.filter(id=session_id).first()
        if not session:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="skill_import_session_not_found",
                status_code=404,
            )
        if session.expires_at < datetime.now(UTC):
            session.status = SkillImportSessionStatus.EXPIRED
            await session.save(update_fields=["status", "updated_at"])
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST, msg_key="skill_import_session_expired"
            )
        if session.team_id is not None:
            await SkillService.check_team_access(
                session.team_id, user, require_admin=True
            )
        elif not user.is_superuser:
            raise BusinessError(
                code=ResponseCode.PERMISSION_DENIED,
                msg_key="skill_system_admin_required",
                status_code=403,
            )

        source_root = SkillImportService._source_root_for_session(session)
        selected = {item.package_path: item for item in items}
        preview_paths = {
            item.get("package_path") for item in session.preview.get("skills", [])
        }
        result = SkillImportInstallOut()

        for package_path, item in selected.items():
            if item.action == SkillInstallAction.SKIP:
                result.skipped.append(package_path)
                continue
            if package_path not in preview_paths:
                result.errors.append(f"{package_path}: skill_package_not_in_session")
                continue

            skill_root = (source_root / package_path).resolve()
            if (
                source_root.resolve() not in skill_root.parents
                and skill_root != source_root.resolve()
            ):
                result.errors.append(f"{package_path}: skill_package_path_invalid")
                continue

            parsed = SkillPackageService.parse_skill_root(source_root, skill_root)
            if not parsed.valid or not parsed.name:
                result.errors.append(f"{package_path}: skill_package_invalid")
                continue

            existing = await Skill.filter(
                team_id=session.team_id, name=parsed.name
            ).first()
            if item.action == SkillInstallAction.INSTALL and existing:
                result.errors.append(f"{package_path}: skill_name_exists")
                continue
            if item.action == SkillInstallAction.UPDATE:
                existing = await SkillImportService._resolve_update_target(
                    session.team_id, parsed.name, item.skill_id
                )

            storage_path = SkillImportService._copy_to_private_storage(
                skill_root=skill_root,
                team_id=session.team_id,
                skill_name=parsed.name,
                package_hash=parsed.package_hash or "unknown",
            )
            skill_spec = SkillImportService._build_private_skill_spec(skill_root)
            skill = await SkillImportService._upsert_skill(
                existing=existing,
                parsed=parsed,
                session=session,
                storage_path=storage_path,
                skill_spec=skill_spec,
                is_enabled=is_enabled,
                user=user,
            )
            if existing:
                result.updated.append(skill.id)
            else:
                result.installed.append(skill.id)

        session.status = SkillImportSessionStatus.INSTALLED
        await session.save(update_fields=["status", "updated_at"])
        return result

    @staticmethod
    async def _create_preview_session(
        *,
        team_id: UUID | None,
        team: object | None,
        user: User,
        source_type: SkillSourceType,
        source_uri: str | None,
        source_ref: str | None,
        source_subdir: str | None,
        source_root: Path,
        temp_storage_path: Path,
    ) -> SkillImportPreviewOut:
        parsed_packages = [
            SkillPackageService.parse_skill_root(source_root, skill_root)
            for skill_root in SkillPackageService.find_skill_roots(source_root)
        ]
        await SkillImportService._attach_conflicts(team_id, parsed_packages)
        SkillImportService._attach_duplicate_warnings(parsed_packages)

        valid_items = [
            SkillImportService._to_preview_item(package)
            for package in parsed_packages
            if package.valid
        ]
        invalid_items = [
            SkillImportService._to_preview_item(package)
            for package in parsed_packages
            if not package.valid
        ]
        preview_data = {
            "source_type": source_type.value,
            "source_uri": source_uri,
            "source_ref": source_ref,
            "source_subdir": source_subdir,
            "skills": [item.model_dump(mode="json") for item in valid_items],
            "invalid": [item.model_dump(mode="json") for item in invalid_items],
        }
        session = await SkillImportSession.create(
            team=team,
            source_type=source_type,
            source_uri=source_uri,
            source_ref=source_ref,
            source_subdir=source_subdir,
            preview=preview_data,
            temp_storage_path=str(temp_storage_path),
            expires_at=datetime.now(UTC) + _IMPORT_SESSION_TTL,
            created_by=user,
        )
        return SkillImportPreviewOut(
            session_id=session.id,
            source_type=source_type,
            source_uri=source_uri,
            source_ref=source_ref,
            source_subdir=source_subdir,
            skills=valid_items,
            invalid=invalid_items,
        )

    @staticmethod
    async def _attach_conflicts(
        team_id: UUID | None, packages: list[ParsedSkillPackage]
    ) -> None:
        for package in packages:
            if not package.name:
                continue
            existing = await Skill.filter(team_id=team_id, name=package.name).first()
            if existing:
                package.warnings.append("skill_name_conflict")

    @staticmethod
    def _attach_duplicate_warnings(packages: list[ParsedSkillPackage]) -> None:
        seen: dict[str, str] = {}
        for package in packages:
            if not package.name:
                continue
            previous_path = seen.get(package.name)
            if previous_path:
                package.warnings.append("skill_duplicate_name_in_source")
            else:
                seen[package.name] = package.package_path

    @staticmethod
    def _to_preview_item(package: ParsedSkillPackage) -> SkillPreviewItem:
        conflict = None
        if "skill_name_conflict" in package.warnings:
            conflict = SkillConflict(type="existing_team_skill")
        return SkillPreviewItem(
            package_path=package.package_path,
            name=package.name,
            display_name=package.display_name,
            description=package.description,
            version=package.version,
            category=package.category,
            icon=package.icon,
            valid=package.valid,
            errors=package.errors,
            warnings=package.warnings,
            conflict=conflict,
            file_count=int(package.package_manifest.get("file_count", 0)),
            package_hash=package.package_hash,
        )

    @staticmethod
    def _extract_zip(zip_path: Path, extract_root: Path) -> None:
        try:
            archive = zipfile.ZipFile(zip_path)
        except zipfile.BadZipFile as exc:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST, msg_key="skill_zip_invalid"
            ) from exc

        with archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if len(infos) > _MAX_ZIP_FILE_COUNT:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST, msg_key="skill_zip_too_many_files"
                )
            total_size = sum(info.file_size for info in infos)
            if total_size > _MAX_ZIP_UNCOMPRESSED_BYTES:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST, msg_key="skill_zip_too_large"
                )

            for info in infos:
                SkillImportService._validate_zip_member(info)
                target = (extract_root / info.filename).resolve()
                if extract_root.resolve() not in target.parents:
                    raise BusinessError(
                        code=ResponseCode.BAD_REQUEST, msg_key="skill_zip_path_invalid"
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)

    @staticmethod
    def _validate_zip_member(info: zipfile.ZipInfo) -> None:
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts or not str(path):
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST, msg_key="skill_zip_path_invalid"
            )
        if info.file_size > _MAX_ZIP_SINGLE_FILE_BYTES:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST, msg_key="skill_zip_file_too_large"
            )
        mode = info.external_attr >> 16
        if mode and (mode & 0o170000) == 0o120000:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST, msg_key="skill_zip_symlink_not_allowed"
            )
        if path.suffix.lower() in NESTED_ARCHIVE_SUFFIXES:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="skill_zip_nested_archive_not_allowed",
            )

    @staticmethod
    def _validate_git_url(repo_url: str) -> None:
        parsed = urlparse(repo_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST, msg_key="skill_git_url_invalid"
            )
        if parsed.username or parsed.password:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="skill_git_credentials_not_allowed",
            )
        host = parsed.hostname.lower()
        if host in {"localhost", "local"}:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST, msg_key="skill_git_url_invalid"
            )
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST, msg_key="skill_git_url_invalid"
            )

    @staticmethod
    async def _clone_git_repo(repo_url: str, ref: str | None, repo_root: Path) -> None:
        command = ["git", "clone", "--depth", "1"]
        if ref:
            command.extend(["--branch", ref])
        command.extend([repo_url, str(repo_root)])
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=_GIT_TIMEOUT_SECONDS
            )
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST, msg_key="skill_git_clone_timeout"
            ) from exc
        if process.returncode != 0:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="skill_git_clone_failed",
                data={"stderr": stderr.decode("utf-8", errors="ignore")[-500:]},
            )

    @staticmethod
    async def _resolve_git_ref(repo_root: Path) -> str | None:
        process = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(repo_root),
            "rev-parse",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await process.communicate()
        if process.returncode != 0:
            return None
        return stdout.decode("utf-8", errors="ignore").strip() or None

    @staticmethod
    def _redact_url(url: str) -> str:
        parsed = urlparse(url)
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        return parsed._replace(netloc=netloc).geturl()

    @staticmethod
    def _source_root_for_session(session: SkillImportSession) -> Path:
        if not session.temp_storage_path:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="skill_import_session_missing_source",
            )
        temp_root = Path(session.temp_storage_path)
        if session.source_type == SkillSourceType.GIT:
            return (temp_root / "repo").resolve()
        return (temp_root / "source").resolve()

    @staticmethod
    async def _resolve_update_target(
        team_id: UUID | None, name: str, skill_id: UUID | None
    ) -> Skill | None:
        if skill_id:
            skill = await Skill.filter(id=skill_id, team_id=team_id).first()
        else:
            skill = await Skill.filter(team_id=team_id, name=name).first()
        if not skill:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND, msg_key="skill_not_found", status_code=404
            )
        return skill

    @staticmethod
    def _copy_to_private_storage(
        *, skill_root: Path, team_id: UUID | None, skill_name: str, package_hash: str
    ) -> str:
        base_dir = Path(__file__).resolve().parents[3] / "uploads" / "skills"
        scope = str(team_id) if team_id else "system"
        destination = (base_dir / scope / skill_name / package_hash[:16]).resolve()
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(skill_root, destination, symlinks=False)
        return str(destination)

    @staticmethod
    def _build_private_skill_spec(skill_root: Path) -> dict:
        files = []
        total_size = 0
        for path in sorted(skill_root.rglob("*")):
            relative_path = path.relative_to(skill_root)
            if any(part in IGNORED_DIR_NAMES for part in relative_path.parts):
                continue
            if path.is_symlink():
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="skill_package_symlink_not_allowed",
                )
            if not path.is_file():
                continue
            if path.suffix.lower() in NESTED_ARCHIVE_SUFFIXES and path.name != "SKILL.md":
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="skill_package_nested_archive_not_allowed",
                )
            content = path.read_bytes()
            total_size += len(content)
            if total_size > _MAX_PACKAGE_PAYLOAD_BYTES:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="skill_zip_too_large",
                )
            files.append(
                {
                    "path": relative_path.as_posix(),
                    "content_base64": base64.b64encode(content).decode("ascii"),
                    "mode": stat.S_IMODE(path.stat().st_mode),
                }
            )
        return {"package_files": files}

    @staticmethod
    async def _upsert_skill(
        *,
        existing: Skill | None,
        parsed: ParsedSkillPackage,
        session: SkillImportSession,
        storage_path: str,
        skill_spec: dict,
        is_enabled: bool,
        user: User,
    ) -> Skill:
        display_name = parsed.display_name or parsed.name or parsed.package_path
        if existing:
            existing.display_name = display_name
            existing.description = parsed.description
            existing.icon = parsed.icon
            existing.category = parsed.category
            existing.version = parsed.version
            existing.source_type = session.source_type
            existing.source_uri = session.source_uri
            existing.source_ref = session.source_ref
            existing.source_subdir = session.source_subdir
            existing.package_path = parsed.package_path
            existing.package_storage_path = storage_path
            existing.package_hash = parsed.package_hash
            existing.package_manifest = parsed.package_manifest
            existing.skill_md = parsed.skill_md
            existing.instructions = parsed.instructions
            existing.frontmatter = parsed.frontmatter
            existing.input_schema = parsed.input_schema
            existing.skill_spec = skill_spec
            existing.execution_config = parsed.execution_config
            existing.import_warnings = parsed.warnings
            existing.is_enabled = is_enabled
            await existing.save()
            return existing
        return await Skill.create(
            team_id=session.team_id,
            name=parsed.name,
            display_name=display_name,
            description=parsed.description,
            icon=parsed.icon,
            category=parsed.category,
            version=parsed.version,
            source_type=session.source_type,
            source_uri=session.source_uri,
            source_ref=session.source_ref,
            source_subdir=session.source_subdir,
            package_path=parsed.package_path,
            package_storage_path=storage_path,
            package_hash=parsed.package_hash,
            package_manifest=parsed.package_manifest,
            skill_md=parsed.skill_md,
            instructions=parsed.instructions,
            frontmatter=parsed.frontmatter,
            input_schema=parsed.input_schema,
            skill_spec=skill_spec,
            execution_config=parsed.execution_config,
            import_warnings=parsed.warnings,
            is_enabled=is_enabled,
            created_by=user,
        )
