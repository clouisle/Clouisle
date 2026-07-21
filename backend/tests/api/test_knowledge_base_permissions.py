from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.endpoints import knowledge_bases
from app.schemas.response import BusinessError, error


class _Permission:
    def __init__(self, code: str):
        self.code = code


class _Role:
    def __init__(self, *codes: str):
        self.permissions = [_Permission(code) for code in codes]


@pytest.fixture
def kb_permission_client():
    app = FastAPI()
    app.include_router(knowledge_bases.router, prefix="/api/v1/knowledge-bases")
    app.include_router(knowledge_bases.router, prefix="/api/v1/admin/knowledge-bases")

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

    user = SimpleNamespace(
        id=uuid4(),
        is_active=True,
        is_superuser=False,
        roles=[],
        locale="en",
    )

    async def fake_current_user():
        return user

    app.dependency_overrides[deps.get_current_active_user] = fake_current_user
    client = TestClient(app)
    try:
        yield client, user
    finally:
        app.dependency_overrides.clear()


def test_admin_kb_route_requires_admin_permission(kb_permission_client):
    client, user = kb_permission_client
    user.roles = [_Role("kb:read")]

    response = client.get("/api/v1/admin/knowledge-bases")

    assert response.status_code == 403
    assert response.json()["code"] == 3000


@pytest.mark.anyio
async def test_platform_kb_route_uses_team_membership_not_global_permission(
    kb_permission_client,
):
    _, user = kb_permission_client
    user.roles = [_Role("admin:knowledge-base:read")]
    request = SimpleNamespace(url=SimpleNamespace(path="/api/v1/knowledge-bases"))

    result = await knowledge_bases.require_kb_read(request, user)

    assert result is user


class _Query:
    def __init__(self, *, first=None, items=()):
        self.first_result = first
        self.items = list(items)

    def filter(self, **_kwargs):
        return self

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.first_result

    async def all(self):
        return self.items


def test_admin_kb_stats_requires_read_permission(kb_permission_client):
    client, user = kb_permission_client
    user.roles = [_Role("admin:knowledge-base:update")]

    response = client.get(f"/api/v1/admin/knowledge-bases/{uuid4()}/stats")

    assert response.status_code == 403
    assert response.json()["code"] == 3000


def test_get_document_returns_not_found_within_authorized_kb(
    kb_permission_client, monkeypatch
):
    client, user = kb_permission_client
    user.is_superuser = True
    kb_id = uuid4()
    kb = SimpleNamespace(id=kb_id, team=SimpleNamespace(id=uuid4()), created_by=user)
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase,
        "filter",
        lambda **_kwargs: _Query(first=kb),
    )
    monkeypatch.setattr(
        knowledge_bases.Document,
        "filter",
        lambda **_kwargs: _Query(),
    )

    response = client.get(f"/api/v1/knowledge-bases/{kb_id}/documents/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == 6002


def test_kb_stats_reconciles_and_persists_actual_document_totals(
    kb_permission_client, monkeypatch
):
    client, user = kb_permission_client
    user.is_superuser = True
    kb_id = uuid4()
    kb = SimpleNamespace(
        id=kb_id,
        name="Team knowledge",
        team=SimpleNamespace(id=uuid4()),
        created_by=user,
        document_count=99,
        total_chunks=99,
        total_tokens=99,
        embedding_dimension=1536,
        save=AsyncMock(),
    )
    documents = [
        SimpleNamespace(
            status="completed", doc_type="txt", chunk_count=2, token_count=8
        ),
        SimpleNamespace(status="error", doc_type="url", chunk_count=1, token_count=4),
    ]
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase,
        "filter",
        lambda **_kwargs: _Query(first=kb),
    )
    monkeypatch.setattr(
        knowledge_bases.Document,
        "filter",
        lambda **_kwargs: _Query(items=documents),
    )
    monkeypatch.setattr(
        knowledge_bases.VectorStore,
        "get_embedding_stats",
        AsyncMock(return_value={"vectors_count": 3}),
    )

    response = client.get(f"/api/v1/knowledge-bases/{kb_id}/stats")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "id": str(kb_id),
        "name": "Team knowledge",
        "document_count": 2,
        "total_chunks": 3,
        "total_tokens": 12,
        "documents_by_status": {"completed": 1, "error": 1},
        "documents_by_type": {"txt": 1, "url": 1},
        "embedding_dimension": 1536,
        "embedding_stats": {"vectors_count": 3},
    }
    kb.save.assert_awaited_once()
    assert (kb.document_count, kb.total_chunks, kb.total_tokens) == (2, 3, 12)
