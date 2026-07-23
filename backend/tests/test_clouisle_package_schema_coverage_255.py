from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.schemas.clouisle_package import (
    ClouisleConflictAction,
    ClouisleDependencyStatus,
    ClouisleImportInstallOut,
    ClouisleImportInstallRequest,
    ClouisleImportPreviewOut,
    ClouisleManifest,
    ClouislePackageDependency,
    ClouisleResourceType,
)


def test_manifest_serializes_enum_uuid_datetime_and_dependency() -> None:
    package_id = uuid4()
    dependency_id = uuid4()
    exported_at = datetime(2026, 7, 20, 9, 30, tzinfo=UTC)
    manifest = ClouisleManifest(
        format_version="1.0",
        app_version="2.0",
        package_id=package_id,
        exported_at=exported_at,
        resource_type=ClouisleResourceType.WORKFLOW,
        resource_name="Daily report",
        resource_id="workflow-1",
        dependencies=[
            ClouislePackageDependency(
                type="tool",
                source_id="tool-1",
                status=ClouisleDependencyStatus.RESOLVED,
                matched_id=dependency_id,
                hints={"provider": "builtin"},
            )
        ],
        checksums={"manifest.json": "abc123"},
    )

    assert manifest.model_dump(mode="json") == {
        "format_version": "1.0",
        "app_version": "2.0",
        "package_id": str(package_id),
        "exported_at": "2026-07-20T09:30:00Z",
        "resource_type": "workflow",
        "resource_name": "Daily report",
        "resource_id": "workflow-1",
        "dependencies": [
            {
                "type": "tool",
                "source_id": "tool-1",
                "name": None,
                "required": True,
                "hints": {"provider": "builtin"},
                "status": "resolved",
                "matched_id": str(dependency_id),
                "message": None,
            }
        ],
        "checksums": {"manifest.json": "abc123"},
    }


def test_import_preview_defaults_are_isolated_and_public() -> None:
    preview_id = uuid4()
    package_id = uuid4()
    first = ClouisleImportPreviewOut(
        session_id=preview_id,
        package_id=package_id,
        resource_type=ClouisleResourceType.AGENT,
        resource_name="Support agent",
        source_resource_id="agent-1",
        format_version="1.0",
        app_version="2.0",
        exported_at=datetime(2026, 7, 20, tzinfo=UTC),
        valid=True,
    )
    second = ClouisleImportPreviewOut(
        session_id=uuid4(),
        package_id=package_id,
        resource_type=ClouisleResourceType.AGENT,
        resource_name="Support agent",
        source_resource_id="agent-1",
        format_version="1.0",
        app_version="2.0",
        exported_at=datetime(2026, 7, 20, tzinfo=UTC),
        valid=True,
    )
    first.errors.append("missing tool")

    assert first.default_action is ClouisleConflictAction.INSTALL
    assert second.errors == []
    assert second.warnings == []
    assert second.dependencies == []
    assert first.model_dump(mode="json", exclude_none=True) == {
        "session_id": str(preview_id),
        "package_id": str(package_id),
        "resource_type": "agent",
        "resource_name": "Support agent",
        "source_resource_id": "agent-1",
        "format_version": "1.0",
        "app_version": "2.0",
        "exported_at": "2026-07-20T00:00:00Z",
        "valid": True,
        "errors": ["missing tool"],
        "warnings": [],
        "dependencies": [],
        "allowed_actions": [],
        "default_action": "install",
    }


@pytest.mark.parametrize("target_name", ["", "x" * 101])
def test_import_request_rejects_invalid_target_name(target_name: str) -> None:
    with pytest.raises(ValidationError):
        ClouisleImportInstallRequest(target_name=target_name)


def test_package_schema_rejects_invalid_enum_and_serializes_install_out() -> None:
    with pytest.raises(ValidationError):
        ClouisleImportInstallRequest(action="delete")  # type: ignore[arg-type]

    installed_id = uuid4()
    result = ClouisleImportInstallOut(installed=installed_id)

    assert result.model_dump(mode="json", exclude_none=True) == {
        "installed": str(installed_id),
        "skipped": False,
        "errors": [],
        "warnings": [],
    }
    assert UUID(result.model_dump(mode="json")["installed"]) == installed_id
