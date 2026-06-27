import hashlib
import hmac
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

from app.api import deps
from app.api.v1.endpoints import upload
from app.schemas.response import BusinessError, error


@pytest.fixture
def upload_test_client():
    app = FastAPI()
    app.include_router(upload.router, prefix="/api/v1/upload")

    @app.exception_handler(BusinessError)
    async def handle_business_error(_, exc: BusinessError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error(
                code=exc.code,
                msg=exc.msg,
                msg_key=exc.msg_key,
                data=exc.data,
                **exc.kwargs,
            ),
        )

    async def fake_auth():
        return SimpleNamespace(id="user-1", is_active=True, locale="en"), None

    app.dependency_overrides[deps.get_current_user_or_api_key] = fake_auth
    app.dependency_overrides[deps.get_current_user_or_api_key_optional] = fake_auth
    client = TestClient(app)
    with patch(
        "app.api.v1.endpoints.upload.AuditLogService.log",
        new=AsyncMock(),
    ):
        try:
            yield client
        finally:
            app.dependency_overrides.clear()


def test_upload_sandbox_artifact_returns_backend_metadata(upload_test_client):
    with patch(
        "app.api.v1.endpoints.upload.save_generated_upload",
        new=AsyncMock(
            return_value={
                "path": "/tmp/uploads/generated.txt",
                "url": "/api/v1/upload/files/sandbox-artifacts/2026/05/generated.txt",
                "filename": "generated.txt",
                "size": 2,
                "content_type": "text/plain",
            }
        ),
    ):
        response = upload_test_client.post(
            "/api/v1/upload/sandbox-artifact",
            files={"file": ("result.txt", b"ok", "text/plain")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["path"] == "/tmp/uploads/generated.txt"
    assert payload["data"]["url"].startswith("/api/v1/upload/files/sandbox-artifacts/")
    assert payload["data"]["filename"] == "generated.txt"
    assert payload["data"]["size"] == 2
    assert payload["data"]["content_type"] == "text/plain"


def test_upload_sandbox_artifact_allows_zip(upload_test_client):
    with patch(
        "app.api.v1.endpoints.upload.save_generated_upload",
        new=AsyncMock(
            return_value={
                "path": "/tmp/uploads/archive.zip",
                "url": "/api/v1/upload/files/sandbox-artifacts/2026/05/archive.zip",
                "filename": "archive.zip",
                "size": 4,
                "content_type": "application/zip",
            }
        ),
    ):
        response = upload_test_client.post(
            "/api/v1/upload/sandbox-artifact",
            files={"file": ("archive.zip", b"PK\x03\x04", "application/zip")},
        )

    assert response.status_code == 200
    assert response.json()["data"]["content_type"] == "application/zip"


def test_upload_sandbox_artifact_rejects_oversized_file(upload_test_client):
    with patch(
        "app.api.v1.endpoints.upload.settings.SANDBOX_ARTIFACT_MAX_FILE_SIZE_MB",
        0.000001,
    ):
        response = upload_test_client.post(
            "/api/v1/upload/sandbox-artifact",
            files={"file": ("large.txt", b"too-large", "text/plain")},
        )

    assert response.status_code == 400
    payload = response.json()
    assert payload["msg"]


def test_upload_sandbox_artifact_allows_internal_signature_without_auth_header(
    upload_test_client,
):
    content = b"ok"
    filename = "result.txt"
    timestamp = str(int(time.time()))
    signature = hmac.new(
        b"changethis-to-a-secure-random-secret-key",
        f"{timestamp}:{filename}:{hashlib.sha256(content).hexdigest()}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    with patch(
        "app.api.v1.endpoints.upload.save_generated_upload",
        new=AsyncMock(
            return_value={
                "path": "/tmp/uploads/generated.txt",
                "url": "/api/v1/upload/files/sandbox-artifacts/2026/05/generated.txt",
                "filename": "generated.txt",
                "size": 2,
                "content_type": "text/plain",
            }
        ),
    ):
        upload_test_client.app.dependency_overrides[
            deps.get_current_user_or_api_key_optional
        ] = lambda: None
        response = upload_test_client.post(
            "/api/v1/upload/sandbox-artifact",
            files={"file": (filename, content, "text/plain")},
            headers={
                "X-Sandbox-Artifact-Timestamp": timestamp,
                "X-Sandbox-Artifact-Signature": signature,
            },
        )

    assert response.status_code == 200
