import io
import json
import zipfile
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.api.v1.endpoints.packages import _content_disposition
from app.schemas.clouisle_package import ClouisleResourceType
from app.schemas.response import BusinessError
from app.services.clouisle_package import ClouislePackageService
from app.services.clouisle_package_resources import _asset_package_path


def _resource_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def _sha256(data: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(data).hexdigest()


def _manifest(resource_payload: dict, **overrides) -> dict:
    resource = _resource_bytes(resource_payload)
    manifest = {
        "format_version": "1",
        "app_version": "0.1.0",
        "package_id": str(uuid4()),
        "exported_at": datetime.now(UTC).isoformat(),
        "resource_type": "tool",
        "resource_name": "Demo Tool",
        "resource_id": str(uuid4()),
        "dependencies": [],
        "checksums": {"resources/resource.json": _sha256(resource)},
    }
    manifest.update(overrides)
    return manifest


def _package(
    resource_payload: dict | None = None,
    *,
    manifest_overrides: dict | None = None,
    include_manifest: bool = True,
    include_resource: bool = True,
    include_checksums: bool = True,
    extra_entries: dict[str, bytes] | None = None,
) -> bytes:
    payload = resource_payload or {"name": "demo"}
    manifest = _manifest(payload, **(manifest_overrides or {}))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if include_manifest:
            zf.writestr("manifest.json", json.dumps(manifest).encode("utf-8"))
        if include_resource:
            zf.writestr("resources/resource.json", _resource_bytes(payload))
        if include_checksums:
            zf.writestr(
                "checksums.json", json.dumps(manifest["checksums"]).encode("utf-8")
            )
        for name, content in (extra_entries or {}).items():
            zf.writestr(name, content)
    return buffer.getvalue()


def _assert_package_error(filename: str, content: bytes, msg_key: str) -> None:
    with pytest.raises(BusinessError) as exc_info:
        ClouislePackageService._read_package(filename, content)
    assert exc_info.value.msg_key == msg_key


def test_content_disposition_supports_non_latin_filename():
    header = _content_disposition("workflow-中文-20260529120000.clouisle")

    header.encode("latin-1")
    assert 'filename="package.clouisle"' in header
    assert (
        "filename*=UTF-8''workflow-%E4%B8%AD%E6%96%87-20260529120000.clouisle" in header
    )


def test_read_package_rejects_non_clouisle_extension():
    _assert_package_error("demo.zip", b"not-a-zip", "clouisle_invalid_extension")


def test_read_package_rejects_broken_zip():
    _assert_package_error("demo.clouisle", b"not-a-zip", "clouisle_invalid_zip")


def test_read_package_rejects_zip_slip_entry():
    content = _package(extra_entries={"../evil.txt": b"nope"})
    _assert_package_error("demo.clouisle", content, "clouisle_zip_path_invalid")


def test_read_package_rejects_missing_manifest():
    content = _package(include_manifest=False)
    _assert_package_error("demo.clouisle", content, "clouisle_missing_manifest")


def test_read_package_rejects_missing_resource():
    content = _package(include_resource=False)
    _assert_package_error("demo.clouisle", content, "clouisle_missing_resource")


def test_read_package_rejects_missing_checksums_file():
    content = _package(include_checksums=False)
    _assert_package_error("demo.clouisle", content, "clouisle_checksum_mismatch")


def test_read_package_rejects_unsupported_format_version():
    content = _package(manifest_overrides={"format_version": "999"})
    _assert_package_error(
        "demo.clouisle", content, "clouisle_unsupported_format_version"
    )


def test_read_package_rejects_invalid_resource_type():
    content = _package(manifest_overrides={"resource_type": "dataset"})
    _assert_package_error("demo.clouisle", content, "clouisle_invalid_resource_type")


def test_read_package_rejects_checksum_mismatch():
    content = _package(
        manifest_overrides={"checksums": {"resources/resource.json": "sha256:wrong"}}
    )
    _assert_package_error("demo.clouisle", content, "clouisle_checksum_mismatch")


def test_read_package_rejects_plaintext_secret_payload():
    payload = {"name": "demo", "api_key": "sk-test"}
    content = _package(payload)
    _assert_package_error(
        "demo.clouisle", content, "clouisle_plaintext_secret_detected"
    )


def test_upload_file_url_maps_to_asset_package_path():
    assert (
        _asset_package_path("icon", "/api/v1/upload/files/avatar/2026/05/logo.png")
        == "assets/icon/avatar/2026/05/logo.png"
    )


def test_build_package_includes_and_validates_extra_files():
    payload = {
        "name": "demo",
        "assets": {"icon": "assets/icon/general/2026/05/icon.png"},
    }
    content = ClouislePackageService.build_package(
        resource_type=ClouisleResourceType.TOOL,
        resource_id=str(uuid4()),
        resource_name="Demo Tool",
        resource_payload=payload,
        dependencies=[],
        files={"assets/icon/general/2026/05/icon.png": b"image-bytes"},
    )

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        assert zf.read("assets/icon/general/2026/05/icon.png") == b"image-bytes"

    _, resource = ClouislePackageService._read_package("demo.clouisle", content)
    assert resource == payload


def test_stage_package_files_accepts_safe_asset_paths():
    payload = {
        "name": "demo",
        "assets": {"icon": "assets/icon/general/2026/05/icon.png"},
    }
    content = ClouislePackageService.build_package(
        resource_type=ClouisleResourceType.TOOL,
        resource_id=str(uuid4()),
        resource_name="Demo Tool",
        resource_payload=payload,
        dependencies=[],
        files={"assets/icon/general/2026/05/icon.png": b"image-bytes"},
    )
    manifest, _ = ClouislePackageService._read_package("demo.clouisle", content)

    temp_dir = ClouislePackageService._stage_package_files(content, manifest)

    assert temp_dir is not None
    with open(f"{temp_dir}/assets/icon/general/2026/05/icon.png", "rb") as f:
        assert f.read() == b"image-bytes"


def test_read_package_rejects_extra_file_checksum_mismatch():
    payload = {"name": "demo"}
    resource = _resource_bytes(payload)
    manifest = _manifest(
        payload,
        checksums={
            "resources/resource.json": _sha256(resource),
            "assets/icon/general/2026/05/icon.png": _sha256(b"expected"),
        },
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest).encode("utf-8"))
        zf.writestr("resources/resource.json", resource)
        zf.writestr("assets/icon/general/2026/05/icon.png", b"actual")
        zf.writestr("checksums.json", json.dumps(manifest["checksums"]).encode("utf-8"))

    _assert_package_error(
        "demo.clouisle", buffer.getvalue(), "clouisle_checksum_mismatch"
    )


def test_build_package_round_trips_resource_payload():
    payload = {"name": "demo", "config": {"endpoint": "https://example.local"}}
    content = ClouislePackageService.build_package(
        resource_type=ClouisleResourceType.TOOL,
        resource_id=str(uuid4()),
        resource_name="Demo Tool",
        resource_payload=payload,
        dependencies=[],
    )

    manifest, resource = ClouislePackageService._read_package("demo.clouisle", content)

    assert manifest.resource_type == ClouisleResourceType.TOOL
    assert manifest.resource_name == "Demo Tool"
    assert resource == payload
