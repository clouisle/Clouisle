import io
import zipfile
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.package_import import (
    ClouisleImportSessionStatus,
    ClouisleImportSource,
)
from app.schemas.clouisle_package import (
    ClouisleConflictAction,
    ClouisleImportInstallRequest,
    ClouisleManifest,
    ClouisleResourceType,
)
from app.schemas.response import BusinessError
from app.services import clouisle_package
from app.services.clouisle_package import ClouislePackageService


def _error_key(callable_):
    with pytest.raises(BusinessError) as exc_info:
        callable_()
    return exc_info.value.msg_key


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _manifest() -> ClouisleManifest:
    return ClouisleManifest(
        format_version="1",
        app_version="0.1.0",
        package_id=uuid4(),
        exported_at=datetime.now(UTC),
        resource_type=ClouisleResourceType.TOOL,
        resource_name="Demo",
        resource_id=str(uuid4()),
        dependencies=[],
        checksums={},
    )


def test_clouisle_package_read_rejects_size_and_file_count(monkeypatch):
    monkeypatch.setattr(clouisle_package, "_MAX_PACKAGE_BYTES", 1)
    assert (
        _error_key(lambda: ClouislePackageService._read_package("demo.clouisle", b"12"))
        == "clouisle_zip_too_large"
    )

    monkeypatch.setattr(clouisle_package, "_MAX_PACKAGE_BYTES", 1024)
    monkeypatch.setattr(clouisle_package, "_MAX_FILE_COUNT", 0)
    content = _zip({"manifest.json": b"{}"})
    assert (
        _error_key(
            lambda: ClouislePackageService._read_package("demo.clouisle", content)
        )
        == "clouisle_invalid_zip"
    )


def test_clouisle_package_read_rejects_uncompressed_size_and_bad_json(monkeypatch):
    content = _zip({"manifest.json": b"{}"})
    monkeypatch.setattr(clouisle_package, "_MAX_TOTAL_UNCOMPRESSED_BYTES", 1)
    assert (
        _error_key(
            lambda: ClouislePackageService._read_package("demo.clouisle", content)
        )
        == "clouisle_zip_too_large"
    )

    monkeypatch.setattr(clouisle_package, "_MAX_TOTAL_UNCOMPRESSED_BYTES", 1024)
    bad_manifest = _zip(
        {
            "manifest.json": b"not-json",
            "resources/resource.json": b"{}",
            "checksums.json": b"{}",
        }
    )
    assert (
        _error_key(
            lambda: ClouislePackageService._read_package("demo.clouisle", bad_manifest)
        )
        == "clouisle_missing_manifest"
    )


def test_clouisle_package_scan_allows_placeholders_and_finds_nested_secrets():
    payload = {
        "api_key": "{{API_KEY}}",
        "credentials": [{"token": "plain"}],
        "empty_secret": " ",
    }

    assert clouisle_package._scan_for_plaintext_secrets(payload) == [
        "credentials[0].token",
        "credentials[0].token",
    ]


@pytest.mark.anyio
async def test_clouisle_package_team_access_covers_not_found_and_roles(monkeypatch):
    user = SimpleNamespace(is_superuser=False)
    monkeypatch.setattr(
        clouisle_package.Team,
        "filter",
        lambda **_kwargs: SimpleNamespace(first=AsyncMock(return_value=None)),
    )
    with pytest.raises(BusinessError) as exc_info:
        await ClouislePackageService._check_team_access(uuid4(), user)
    assert exc_info.value.msg_key == "team_not_found"

    team = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        clouisle_package.Team,
        "filter",
        lambda **_kwargs: SimpleNamespace(first=AsyncMock(return_value=team)),
    )
    monkeypatch.setattr(
        clouisle_package.TeamMember,
        "filter",
        lambda **_kwargs: SimpleNamespace(first=AsyncMock(return_value=None)),
    )
    with pytest.raises(BusinessError) as exc_info:
        await ClouislePackageService._check_team_access(team.id, user)
    assert exc_info.value.msg_key == "not_team_member"

    monkeypatch.setattr(
        clouisle_package.TeamMember,
        "filter",
        lambda **_kwargs: SimpleNamespace(
            first=AsyncMock(return_value=SimpleNamespace(role="member"))
        ),
    )
    with pytest.raises(BusinessError) as exc_info:
        await ClouislePackageService._check_team_access(
            team.id, user, require_admin=True
        )
    assert exc_info.value.msg_key == "team_admin_required"

    assert (
        await ClouislePackageService._check_team_access(
            team.id, SimpleNamespace(is_superuser=True), require_admin=True
        )
        is team
    )


def test_clouisle_package_stage_without_files_and_cleanup_guards(tmp_path, monkeypatch):
    assert ClouislePackageService._stage_package_files(b"", _manifest()) is None

    outside = tmp_path / "outside"
    outside.mkdir()
    temp_root = tmp_path / "temp"
    temp_root.mkdir()
    monkeypatch.setattr(clouisle_package.tempfile, "gettempdir", lambda: str(temp_root))
    ClouislePackageService._cleanup_staged_package(None)
    ClouislePackageService._cleanup_staged_package(str(outside))
    assert outside.exists()

    staged = temp_root / "staged"
    staged.mkdir()
    ClouislePackageService._cleanup_staged_package(str(staged))
    assert not staged.exists()


@pytest.mark.anyio
async def test_clouisle_package_install_rejects_session_boundaries(monkeypatch):
    user = SimpleNamespace()
    request = ClouisleImportInstallRequest(action=ClouisleConflictAction.INSTALL)

    monkeypatch.setattr(
        clouisle_package.ClouisleImportSession,
        "filter",
        lambda **_kwargs: SimpleNamespace(first=AsyncMock(return_value=None)),
    )
    with pytest.raises(BusinessError) as exc_info:
        await ClouislePackageService.install(
            session_id=uuid4(), user=user, install_in=request
        )
    assert exc_info.value.msg_key == "clouisle_import_session_not_found"

    session = SimpleNamespace(
        status=ClouisleImportSessionStatus.PREVIEWED,
        source=ClouisleImportSource.PLATFORM,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        temp_storage_path=None,
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        clouisle_package.ClouisleImportSession,
        "filter",
        lambda **_kwargs: SimpleNamespace(first=AsyncMock(return_value=session)),
    )
    with pytest.raises(BusinessError) as exc_info:
        await ClouislePackageService.install(
            session_id=uuid4(), user=user, install_in=request
        )
    assert exc_info.value.msg_key == "clouisle_import_session_expired"
    assert session.status == ClouisleImportSessionStatus.EXPIRED
    session.save.assert_awaited_once()
