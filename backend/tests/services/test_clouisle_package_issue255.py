from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.models.package_import import (
    ClouisleImportSessionStatus,
    ClouisleImportSource,
)
from app.schemas.clouisle_package import (
    ClouisleConflictAction,
    ClouisleImportInstallOut,
    ClouisleImportInstallRequest,
    ClouisleManifest,
    ClouislePackageConflict,
    ClouislePackageDependency,
)
from app.schemas.response import BusinessError
from app.services import clouisle_package, clouisle_package_resources
from app.services.clouisle_package import ClouislePackageService


def _manifest() -> ClouisleManifest:
    return ClouisleManifest(
        format_version="1",
        app_version="test",
        package_id=uuid4(),
        exported_at=datetime.now(UTC),
        resource_type="tool",
        resource_name="Tool",
        resource_id=str(uuid4()),
    )


class Query:
    def __init__(self, result):
        self.result = result

    async def first(self):
        return self.result


class Session(SimpleNamespace):
    async def save(self, update_fields):
        self.saved_fields = update_fields


def _session(**overrides) -> Session:
    manifest = _manifest()
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "status": ClouisleImportSessionStatus.PREVIEWED,
        "source": ClouisleImportSource.PLATFORM,
        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
        "resource_type": "tool",
        "manifest": manifest.model_dump(mode="json"),
        "resource_payload": {"name": "Tool"},
        "preview": {"dependencies": []},
        "temp_storage_path": None,
        "saved_fields": None,
    }
    values.update(overrides)
    return Session(**values)


def _patch_session_query(monkeypatch, session):
    monkeypatch.setattr(
        clouisle_package.ClouisleImportSession,
        "filter",
        lambda **_kwargs: Query(session),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("team", "user", "membership", "require_admin", "message"),
    [
        (None, SimpleNamespace(is_superuser=False), None, False, "team_not_found"),
        (object(), SimpleNamespace(is_superuser=False), None, False, "not_team_member"),
        (
            object(),
            SimpleNamespace(is_superuser=False),
            SimpleNamespace(role="member"),
            True,
            "team_admin_required",
        ),
    ],
)
async def test_check_team_access_rejects_invalid_access(
    monkeypatch, team, user, membership, require_admin, message
):
    monkeypatch.setattr(clouisle_package.Team, "filter", lambda **_kwargs: Query(team))
    monkeypatch.setattr(
        clouisle_package.TeamMember,
        "filter",
        lambda **_kwargs: Query(membership),
    )

    with pytest.raises(BusinessError) as exc_info:
        await ClouislePackageService._check_team_access(
            uuid4(), user, require_admin=require_admin
        )

    assert exc_info.value.msg_key == message


@pytest.mark.asyncio
@pytest.mark.parametrize("superuser", [True, False])
async def test_check_team_access_accepts_superuser_or_admin(monkeypatch, superuser):
    team = object()
    user = SimpleNamespace(is_superuser=superuser)
    monkeypatch.setattr(clouisle_package.Team, "filter", lambda **_kwargs: Query(team))
    monkeypatch.setattr(
        clouisle_package.TeamMember,
        "filter",
        lambda **_kwargs: Query(SimpleNamespace(role="admin")),
    )

    assert await ClouislePackageService._check_team_access(uuid4(), user, True) is team


@pytest.mark.asyncio
@pytest.mark.parametrize("has_conflict", [True, False])
async def test_preview_classifies_dependencies_and_conflicts(monkeypatch, has_conflict):
    team = SimpleNamespace(id=uuid4())
    user = SimpleNamespace()
    manifest = _manifest()
    dependencies = [
        ClouislePackageDependency(type="model", status="forbidden", message="denied"),
        ClouislePackageDependency(type="tool", status="missing"),
        ClouislePackageDependency(
            type="knowledge_base", required=False, status="unsupported", message="warn"
        ),
    ]
    adapter = SimpleNamespace(
        ensure_import_permission=Mock(),
        resolve_dependencies=AsyncMock(return_value=dependencies),
        detect_conflict=AsyncMock(
            return_value=ClouislePackageConflict(
                type="name_exists" if has_conflict else "none"
            )
        ),
    )
    created = Session(id=uuid4(), preview=None, saved_fields=None)
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(
        ClouislePackageService, "_check_team_access", AsyncMock(return_value=team)
    )
    monkeypatch.setattr(
        ClouislePackageService,
        "_read_package",
        lambda *_args: (manifest, {"name": "Tool"}),
    )
    monkeypatch.setattr(
        ClouislePackageService, "_stage_package_files", lambda *_args: None
    )
    monkeypatch.setattr(
        clouisle_package_resources, "get_adapter", lambda _type: adapter
    )
    monkeypatch.setattr(clouisle_package.ClouisleImportSession, "create", create)

    result = await ClouislePackageService.preview(
        team_id=team.id,
        user=user,
        filename="tool.clouisle",
        content=b"package",
    )

    assert result.valid is False
    assert result.errors == ["denied", "clouisle_dependency_missing"]
    assert result.warnings == ["warn"]
    assert result.default_action == (
        ClouisleConflictAction.RENAME
        if has_conflict
        else ClouisleConflictAction.INSTALL
    )
    assert created.preview["valid"] is False
    assert created.saved_fields == ["preview", "updated_at"]
    adapter.ensure_import_permission.assert_called_once_with(user)


@pytest.mark.asyncio
async def test_preview_without_membership_requires_existing_team(monkeypatch):
    monkeypatch.setattr(clouisle_package.Team, "filter", lambda **_kwargs: Query(None))

    with pytest.raises(BusinessError) as exc_info:
        await ClouislePackageService.preview(
            team_id=uuid4(),
            user=SimpleNamespace(),
            filename="tool.clouisle",
            content=b"package",
            check_team_membership=False,
        )

    assert exc_info.value.msg_key == "team_not_found"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session", "source", "message"),
    [
        (None, ClouisleImportSource.PLATFORM, "clouisle_import_session_not_found"),
        (
            _session(status=ClouisleImportSessionStatus.INSTALLED),
            ClouisleImportSource.PLATFORM,
            "clouisle_import_session_not_found",
        ),
        (
            _session(source=ClouisleImportSource.ADMIN),
            ClouisleImportSource.PLATFORM,
            "clouisle_import_session_not_found",
        ),
    ],
)
async def test_install_rejects_unusable_session(monkeypatch, session, source, message):
    _patch_session_query(monkeypatch, session)

    with pytest.raises(BusinessError) as exc_info:
        await ClouislePackageService.install(
            session_id=uuid4(),
            user=SimpleNamespace(),
            install_in=ClouisleImportInstallRequest(),
            source=source,
        )

    assert exc_info.value.msg_key == message


@pytest.mark.asyncio
async def test_install_expires_session_and_cleans_files(monkeypatch):
    session = _session(
        expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10)
    )
    cleanup = Mock()
    _patch_session_query(monkeypatch, session)
    monkeypatch.setattr(ClouislePackageService, "_cleanup_staged_package", cleanup)

    with pytest.raises(BusinessError) as exc_info:
        await ClouislePackageService.install(
            session_id=session.id,
            user=SimpleNamespace(),
            install_in=ClouisleImportInstallRequest(),
        )

    assert exc_info.value.msg_key == "clouisle_import_session_expired"
    assert session.status == ClouisleImportSessionStatus.EXPIRED
    cleanup.assert_called_once_with(None)


@pytest.mark.asyncio
async def test_install_skip_checks_permission_and_finishes(monkeypatch):
    session = _session()
    team = SimpleNamespace(id=session.team_id)
    adapter = SimpleNamespace(
        ensure_import_permission=Mock(), ensure_update_permission=Mock()
    )
    cleanup = Mock()
    _patch_session_query(monkeypatch, session)
    monkeypatch.setattr(
        ClouislePackageService, "_check_team_access", AsyncMock(return_value=team)
    )
    monkeypatch.setattr(
        clouisle_package_resources, "get_adapter", lambda _type: adapter
    )
    monkeypatch.setattr(ClouislePackageService, "_cleanup_staged_package", cleanup)

    result = await ClouislePackageService.install(
        session_id=session.id,
        user=SimpleNamespace(),
        install_in=ClouisleImportInstallRequest(action=ClouisleConflictAction.SKIP),
    )

    assert result.skipped is True
    assert session.status == ClouisleImportSessionStatus.INSTALLED
    adapter.ensure_import_permission.assert_not_called()
    adapter.ensure_update_permission.assert_not_called()
    cleanup.assert_called_once_with(None)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_install_merges_dependency_mapping_and_records_outcome(
    monkeypatch, tmp_path, failure
):
    source_id = "source-model"
    matched_id = uuid4()
    explicit_id = uuid4()
    session = _session(
        temp_storage_path=str(tmp_path),
        preview={
            "dependencies": [
                {
                    "source_id": source_id,
                    "matched_id": str(matched_id),
                    "status": "resolved",
                }
            ]
        },
    )
    team = SimpleNamespace(id=session.team_id)
    error = BusinessError(msg_key="install_failed")
    install_result = ClouisleImportInstallOut(installed=uuid4())
    adapter = SimpleNamespace(
        ensure_import_permission=Mock(),
        ensure_update_permission=Mock(),
        materialize_files=AsyncMock(return_value={"name": "materialized"}),
        install=AsyncMock(
            side_effect=error if failure else None, return_value=install_result
        ),
    )
    cleanup = Mock()
    _patch_session_query(monkeypatch, session)
    monkeypatch.setattr(
        ClouislePackageService, "_check_team_access", AsyncMock(return_value=team)
    )
    monkeypatch.setattr(
        clouisle_package_resources, "get_adapter", lambda _type: adapter
    )
    monkeypatch.setattr(ClouislePackageService, "_cleanup_staged_package", cleanup)
    install_in = ClouisleImportInstallRequest(
        action=ClouisleConflictAction.UPDATE,
        dependency_mapping={source_id: explicit_id},
    )

    if failure:
        with pytest.raises(BusinessError, match="install_failed"):
            await ClouislePackageService.install(
                session_id=session.id, user=SimpleNamespace(), install_in=install_in
            )
        assert session.status == ClouisleImportSessionStatus.FAILED
    else:
        result = await ClouislePackageService.install(
            session_id=session.id, user=SimpleNamespace(), install_in=install_in
        )
        assert result == install_result
        assert session.status == ClouisleImportSessionStatus.INSTALLED
        passed_request = adapter.install.call_args.kwargs["install_in"]
        assert passed_request.dependency_mapping[source_id] == explicit_id
    adapter.ensure_update_permission.assert_called_once()
    cleanup.assert_called_once_with(str(tmp_path))


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["missing", "forbidden"])
async def test_install_rejects_unresolved_required_dependency(monkeypatch, status):
    session = _session(preview={"dependencies": [{"required": True, "status": status}]})
    adapter = SimpleNamespace(ensure_import_permission=Mock())
    _patch_session_query(monkeypatch, session)
    monkeypatch.setattr(
        ClouislePackageService,
        "_check_team_access",
        AsyncMock(return_value=SimpleNamespace(id=session.team_id)),
    )
    monkeypatch.setattr(
        clouisle_package_resources, "get_adapter", lambda _type: adapter
    )

    with pytest.raises(BusinessError) as exc_info:
        await ClouislePackageService.install(
            session_id=session.id,
            user=SimpleNamespace(),
            install_in=ClouisleImportInstallRequest(),
        )

    assert exc_info.value.msg_key == f"clouisle_dependency_{status}"


def test_cleanup_staged_package_only_removes_safe_temp_children(tmp_path, monkeypatch):
    remove = Mock()
    monkeypatch.setattr(clouisle_package.shutil, "rmtree", remove)
    monkeypatch.setattr(clouisle_package.tempfile, "gettempdir", lambda: str(tmp_path))

    ClouislePackageService._cleanup_staged_package(None)
    ClouislePackageService._cleanup_staged_package(str(tmp_path))
    ClouislePackageService._cleanup_staged_package(str(tmp_path.parent))
    child = tmp_path / "staged"
    ClouislePackageService._cleanup_staged_package(str(child))

    remove.assert_called_once_with(child, ignore_errors=True)
