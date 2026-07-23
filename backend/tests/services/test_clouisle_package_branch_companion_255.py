import io
import json
import zipfile
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.schemas.response import BusinessError
from app.services import clouisle_package as package_module
from app.services.clouisle_package import ClouislePackageService


def _sha256(data: bytes) -> str:
    return package_module._sha256(data)


def _archive(
    *,
    manifest: bytes | None = None,
    resource: bytes = b"{}",
    checksums: bytes | None = None,
    extras: dict[str, bytes] | None = None,
) -> bytes:
    manifest_data = {
        "format_version": "1",
        "app_version": "test",
        "package_id": str(uuid4()),
        "exported_at": datetime.now(UTC).isoformat(),
        "resource_type": "tool",
        "resource_name": "test",
        "resource_id": "source",
        "dependencies": [],
        "checksums": {"resources/resource.json": _sha256(resource)},
    }
    manifest_bytes = manifest or json.dumps(manifest_data).encode()
    checksum_bytes = checksums or json.dumps(manifest_data["checksums"]).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", manifest_bytes)
        archive.writestr("resources/resource.json", resource)
        archive.writestr("checksums.json", checksum_bytes)
        for name, value in (extras or {}).items():
            archive.writestr(name, value)
    return buffer.getvalue()


def _error(content: bytes) -> str | None:
    with pytest.raises(BusinessError) as caught:
        ClouislePackageService._read_package("test.clouisle", content)
    return caught.value.msg_key


def test_issue255_package_size_and_archive_limits(monkeypatch):
    content = _archive(extras={"extra": b"x"})

    monkeypatch.setattr(package_module, "_MAX_PACKAGE_BYTES", len(content) - 1)
    assert _error(content) == "clouisle_zip_too_large"
    monkeypatch.setattr(package_module, "_MAX_PACKAGE_BYTES", len(content))

    monkeypatch.setattr(package_module, "_MAX_FILE_COUNT", 3)
    assert _error(content) == "clouisle_invalid_zip"
    monkeypatch.setattr(package_module, "_MAX_FILE_COUNT", 2000)

    monkeypatch.setattr(package_module, "_MAX_TOTAL_UNCOMPRESSED_BYTES", 1)
    assert _error(content) == "clouisle_zip_too_large"


def test_issue255_package_rejects_malformed_json_documents():
    assert _error(_archive(manifest=b"{")) == "clouisle_missing_manifest"
    assert _error(_archive(checksums=b"{")) == "clouisle_checksum_mismatch"
    assert _error(_archive(resource=b"{")) == "clouisle_missing_resource"
    assert _error(_archive(resource=b"[]")) == "clouisle_missing_resource"


def test_issue255_package_rejects_checksum_manifest_disagreement():
    assert _error(_archive(checksums=b"{}")) == "clouisle_checksum_mismatch"


def test_issue255_package_rejects_missing_manifest_checksum_target():
    resource = b"{}"
    manifest_data = {
        "format_version": "1",
        "app_version": "test",
        "package_id": str(uuid4()),
        "exported_at": datetime.now(UTC).isoformat(),
        "resource_type": "tool",
        "resource_name": "test",
        "resource_id": "source",
        "dependencies": [],
        "checksums": {
            "resources/resource.json": _sha256(resource),
            "assets/missing.txt": _sha256(b"missing"),
        },
    }
    manifest = json.dumps(manifest_data).encode()

    assert _error(_archive(manifest=manifest, checksums=manifest)) == (
        "clouisle_checksum_mismatch"
    )


def test_issue255_package_helper_fallbacks(monkeypatch, tmp_path):
    assert package_module._is_placeholder("  ")
    assert package_module._is_placeholder("{{API_TOKEN}}")
    assert not package_module._is_placeholder("plaintext")
    assert package_module._slugify("  Demo___Tool !!! ") == "demo-tool"

    monkeypatch.setattr(package_module.tempfile, "gettempdir", lambda: str(tmp_path))
    outside = tmp_path.parent / "outside-clouisle-stage"
    ClouislePackageService._cleanup_staged_package(None)
    ClouislePackageService._cleanup_staged_package(str(tmp_path))
    ClouislePackageService._cleanup_staged_package(str(outside))
