from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.schemas.clouisle_package import (
    ClouisleConflictAction,
    ClouisleDependencyStatus,
    ClouisleImportInstallRequest,
    ClouislePackageDependency,
)
from app.services import clouisle_package_resources as resources
from app.services.clouisle_package_resources import (
    ToolPackageAdapter,
    _collect_payload_assets,
    _resolve_model_dependency,
    _resolve_resource_dependency,
    _restore_payload_assets,
    _workflow_fields,
)


def test_collect_payload_assets_stages_only_upload_backed_files(tmp_path, monkeypatch):
    source = tmp_path / "logo.png"
    source.write_bytes(b"icon-bytes")
    monkeypatch.setattr(resources, "_asset_source_path", lambda _path: source)
    payload = {
        "icon": "/api/v1/upload/files/avatar/2026/05/logo.png",
        "avatar_url": "https://example.com/avatar.png",
    }

    files = _collect_payload_assets(payload, ("icon", "avatar_url"))

    assert files == {"assets/icon/avatar/2026/05/logo.png": b"icon-bytes"}
    assert payload["assets"] == {"icon": "assets/icon/avatar/2026/05/logo.png"}


@pytest.mark.asyncio
async def test_restore_payload_assets_rejects_traversal_and_restores_valid_file(
    tmp_path, monkeypatch
):
    package_dir = tmp_path / "package"
    asset = package_dir / "assets" / "icon" / "logo.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"icon-bytes")
    save_upload = AsyncMock(
        return_value={"url": "/api/v1/upload/files/clouisle-assets/2026/05/logo.png"}
    )
    monkeypatch.setattr(resources, "save_generated_upload", save_upload)
    payload = {
        "icon": "original",
        "assets": {
            "icon": "assets/icon/logo.png",
            "avatar_url": "../outside.png",
        },
    }

    restored = await _restore_payload_assets(payload, package_dir)

    assert restored["icon"].endswith("/logo.png")
    assert "avatar_url" not in restored
    assert payload["icon"] == "original"
    save_upload.assert_awaited_once_with(
        content=b"icon-bytes",
        category="clouisle-assets",
        content_type="image/png",
        filename="logo.png",
    )


@pytest.mark.asyncio
async def test_dependency_resolution_marks_missing_and_uses_name_fallback(monkeypatch):
    missing_model = ClouislePackageDependency(type="model", hints={})
    resolved_model = await _resolve_model_dependency(missing_model, uuid4())

    assert resolved_model.status == ClouisleDependencyStatus.MISSING
    assert resolved_model.message == "clouisle_dependency_missing"

    item = SimpleNamespace(id=uuid4())
    first = AsyncMock(side_effect=[None, item])

    class FakeQuery:
        async def first(self):
            return await first()

    class FakeTool:
        @staticmethod
        def filter(**_kwargs):
            return FakeQuery()

    monkeypatch.setattr(resources, "Tool", FakeTool)
    dependency = ClouislePackageDependency(
        type="tool", source_id=str(uuid4()), name="Fallback Tool"
    )

    resolved_resource = await _resolve_resource_dependency(dependency, uuid4())

    assert resolved_resource.status == ClouisleDependencyStatus.RESOLVED
    assert resolved_resource.matched_id == item.id
    assert first.await_count == 2


@pytest.mark.asyncio
async def test_dependency_resolution_marks_unsupported_type():
    dependency = ClouislePackageDependency(type="dataset", name="Dataset")

    resolved = await _resolve_resource_dependency(dependency, uuid4())

    assert resolved.status == ClouisleDependencyStatus.UNSUPPORTED
    assert resolved.message == "clouisle_dependency_missing"


@pytest.mark.asyncio
async def test_target_name_advances_past_existing_import_names():
    exists = AsyncMock(side_effect=[True, True, False])

    class FakeQuery:
        async def exists(self):
            return await exists()

    class FakeModel:
        @staticmethod
        def filter(**_kwargs):
            return FakeQuery()

    target = await ToolPackageAdapter()._target_name(
        {"name": "Imported Tool"},
        uuid4(),
        ClouisleImportInstallRequest(action=ClouisleConflictAction.RENAME),
        FakeModel,
    )

    assert target == "Imported Tool_import_2"
    assert exists.await_count == 3


def test_workflow_fields_rewrites_references_without_mutating_payload():
    source_id, target_id = str(uuid4()), uuid4()
    payload = {
        "definition": {"nodes": [{"data": {"toolId": source_id}}]},
        "trigger_type": "webhook",
    }

    fields = _workflow_fields(payload, {source_id: target_id})

    assert fields["definition"]["nodes"][0]["data"]["toolId"] == str(target_id)
    assert payload["definition"]["nodes"][0]["data"]["toolId"] == source_id
    assert fields["trigger_type"].value == "manual"
