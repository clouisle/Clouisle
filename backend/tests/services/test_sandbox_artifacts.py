import hashlib
import hmac
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.sandbox.artifacts import SandboxArtifactStore
from app.services.sandbox.models import SandboxArtifactLimits, SandboxArtifactSpec
from app.services.sandbox.workspace import SandboxWorkspaceManager


class _FakeResponse:
    def __init__(self, data: dict):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return {"code": 0, "data": self._data, "msg": "success"}


@pytest.mark.anyio
async def test_collect_uploads_file_artifact_via_http(tmp_path: Path):
    workspace_manager = SandboxWorkspaceManager(root=str(tmp_path))
    store = SandboxArtifactStore(workspace_manager)
    workspace = workspace_manager.prepare("job-1")
    output = workspace.root / "output" / "report.txt"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("ok", encoding="utf-8")

    captured: dict = {}

    async def fake_post(self, url, files=None, headers=None):
        captured["url"] = url
        captured["files"] = files
        captured["headers"] = headers
        return _FakeResponse(
            {
                "path": "/tmp/uploads/report.txt",
                "url": "/api/v1/upload/files/sandbox-artifacts/2026/05/report.txt",
                "filename": "report.txt",
                "size": 2,
                "content_type": "text/plain",
            }
        )

    with patch("httpx.AsyncClient.post", new=fake_post), patch(
        "app.services.sandbox.artifacts.settings.SANDBOX_ARTIFACT_UPLOAD_BASE_URL",
        "http://backend:8000",
    ):
        artifacts = await store.collect(
            job_id="job-1",
            artifacts=[SandboxArtifactSpec(path="/workspace/output/report.txt")],
            workspace=workspace,
            artifact_limits=SandboxArtifactLimits(max_size_mb=10, max_total_size_mb=10),
        )

    assert len(artifacts) == 1
    assert artifacts[0].url.startswith("/api/v1/upload/files/sandbox-artifacts/")
    assert artifacts[0].storage_path == "/tmp/uploads/report.txt"
    assert captured["url"] == "http://backend:8000/api/v1/upload/sandbox-artifact"
    filename, content, content_type = captured["files"]["file"]
    timestamp = captured["headers"]["X-Sandbox-Artifact-Timestamp"]
    signature = captured["headers"]["X-Sandbox-Artifact-Signature"]
    expected = hmac.new(
        b"changethis-to-a-secure-random-secret-key",
        f"{timestamp}:{filename}:{hashlib.sha256(content).hexdigest()}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert signature == expected
    assert filename == "job-1_report.txt"
    assert content == b"ok"
    assert content_type == "text/plain"


@pytest.mark.anyio
async def test_collect_rejects_file_over_max_size(tmp_path: Path):
    workspace_manager = SandboxWorkspaceManager(root=str(tmp_path))
    store = SandboxArtifactStore(workspace_manager)
    workspace = workspace_manager.prepare("job-2")
    output = workspace.root / "output" / "large.bin"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"x" * 2048)

    with pytest.raises(ValueError, match="per-file limit"):
        await store.collect(
            job_id="job-2",
            artifacts=[SandboxArtifactSpec(path="/workspace/output/large.bin")],
            workspace=workspace,
            artifact_limits=SandboxArtifactLimits(max_size_mb=0.001, max_total_size_mb=10),
        )


@pytest.mark.anyio
async def test_collect_rejects_total_size_over_limit(tmp_path: Path):
    workspace_manager = SandboxWorkspaceManager(root=str(tmp_path))
    store = SandboxArtifactStore(workspace_manager)
    workspace = workspace_manager.prepare("job-3")
    output_dir = workspace.root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "a.txt").write_bytes(b"a" * 900)
    (output_dir / "b.txt").write_bytes(b"b" * 900)

    async def fake_post(self, url, files=None, headers=None):
        filename, content, content_type = files["file"]
        return _FakeResponse(
            {
                "path": f"/tmp/uploads/{filename}",
                "url": f"/api/v1/upload/files/sandbox-artifacts/2026/05/{filename}",
                "filename": filename,
                "size": len(content),
                "content_type": content_type,
            }
        )

    with patch("httpx.AsyncClient.post", new=fake_post), patch(
        "app.services.sandbox.artifacts.settings.SANDBOX_ARTIFACT_UPLOAD_BASE_URL",
        "http://backend:8000",
    ), pytest.raises(ValueError, match="total limit"):
        await store.collect(
            job_id="job-3",
            artifacts=[
                SandboxArtifactSpec(path="/workspace/output/a.txt"),
                SandboxArtifactSpec(path="/workspace/output/b.txt"),
            ],
            workspace=workspace,
            artifact_limits=SandboxArtifactLimits(max_size_mb=10, max_total_size_mb=0.0015),
        )


def test_upload_base_url_prefers_explicit_env_override(tmp_path: Path):
    store = SandboxArtifactStore(SandboxWorkspaceManager(root=str(tmp_path)))

    with patch(
        "app.services.sandbox.artifacts.settings.SANDBOX_ARTIFACT_UPLOAD_BASE_URL",
        "http://artifact-backend:9000",
    ), patch(
        "app.services.sandbox.artifacts.settings.API_BASE_URL",
        "http://localhost:8000",
    ):
        assert store._upload_base_url() == "http://artifact-backend:9000"


def test_upload_base_url_defaults_to_backend_service_in_container_for_localhost_api(tmp_path: Path):
    store = SandboxArtifactStore(SandboxWorkspaceManager(root=str(tmp_path)))

    with patch(
        "app.services.sandbox.artifacts.settings.SANDBOX_ARTIFACT_UPLOAD_BASE_URL",
        None,
    ), patch(
        "app.services.sandbox.artifacts.settings.API_BASE_URL",
        "http://localhost:8000",
    ), patch(
        "app.services.sandbox.artifacts.os.path.exists",
        return_value=True,
    ), patch.dict(
        "app.services.sandbox.artifacts.os.environ",
        {},
        clear=False,
    ):
        assert store._upload_base_url() == "http://backend:8000"


def test_upload_base_url_keeps_non_localhost_api_base_url(tmp_path: Path):
    store = SandboxArtifactStore(SandboxWorkspaceManager(root=str(tmp_path)))

    with patch(
        "app.services.sandbox.artifacts.settings.SANDBOX_ARTIFACT_UPLOAD_BASE_URL",
        None,
    ), patch(
        "app.services.sandbox.artifacts.settings.API_BASE_URL",
        "http://backend:8000",
    ):
        assert store._upload_base_url() == "http://backend:8000"
