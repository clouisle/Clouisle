from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.endpoints import knowledge_bases
from app.schemas.response import BusinessError, error


class Query:
    def __init__(self, items=(), *, first=None, total=None):
        self.items = list(items)
        self.first_value = first
        self.total = len(self.items) if total is None else total
        self.filters = []
        self.offset_value = None
        self.limit_value = None
        self.prefetches = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def prefetch_related(self, *args):
        self.prefetches.extend(args)
        return self

    def offset(self, value):
        self.offset_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    async def count(self):
        return self.total

    async def first(self):
        return self.first_value

    async def all(self):
        return self.items

    async def values_list(self, *_args, **_kwargs):
        return [item.team_id for item in self.items]

    def __await__(self):
        async def resolve():
            return self.items

        return resolve().__await__()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(knowledge_bases.router, prefix="/api/v1/knowledge-bases")

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

    user = SimpleNamespace(id=uuid4(), is_active=True, is_superuser=False, roles=[])

    async def current_user():
        return user

    app.dependency_overrides[deps.get_current_active_user] = current_user
    try:
        yield TestClient(app), user
    finally:
        app.dependency_overrides.clear()


def team(id=None):
    return SimpleNamespace(id=id or uuid4(), name="Docs")


def user(id=None):
    return SimpleNamespace(
        id=id or uuid4(), username="owner", email="owner@example.com"
    )


def kb(**overrides):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    data = {
        "id": uuid4(),
        "name": "Handbook",
        "description": None,
        "icon": None,
        "team": team(),
        "created_by": user(),
        "status": "active",
        "embedding_model_id": None,
        "rerank_model_id": None,
        "embedding_dimension": None,
        "settings": None,
        "document_count": 1,
        "total_chunks": 2,
        "total_tokens": 12,
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    if "team_id" not in data:
        data["team_id"] = data["team"].id
    return SimpleNamespace(**data)


def doc(**overrides):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    data = {
        "id": uuid4(),
        "knowledge_base_id": uuid4(),
        "name": "page.html",
        "doc_type": "url",
        "file_path": None,
        "file_size": None,
        "source_url": "https://example.com/page",
        "status": "error",
        "error_message": "safe failure",
        "chunk_count": 0,
        "token_count": 0,
        "metadata": {},
        "uploaded_by": user(),
        "created_at": now,
        "updated_at": now,
        "processed_at": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


async def allow_kb_access(*_args, **_kwargs):
    return kb()


def test_list_knowledge_bases_filters_memberships_search_status_and_models(
    client, monkeypatch
):
    api, current_user = client
    team_id = uuid4()
    embedding_model_id = uuid4()
    rerank_model_id = uuid4()
    kb_query = Query(
        [
            kb(
                team=team(team_id),
                created_by=user(current_user.id),
                embedding_model_id=embedding_model_id,
                rerank_model_id=rerank_model_id,
            )
        ],
        total=7,
    )
    model_query = Query(
        [
            SimpleNamespace(
                id=embedding_model_id,
                name="Embed",
                provider="test",
                model_id="embed-1",
            ),
            SimpleNamespace(
                id=rerank_model_id,
                name="Rerank",
                provider="test",
                model_id="rerank-1",
            ),
        ]
    )
    monkeypatch.setattr(knowledge_bases.KnowledgeBase, "all", lambda: kb_query)
    monkeypatch.setattr(
        knowledge_bases.TeamMember,
        "filter",
        lambda **_kwargs: Query([SimpleNamespace(team_id=team_id)]),
    )
    monkeypatch.setattr(knowledge_bases.Model, "filter", lambda **_kwargs: model_query)

    response = api.get(
        "/api/v1/knowledge-bases?search=hand&own_only=true&page=2&page_size=3"
    )

    assert response.status_code == 200
    data = response.json()["data"]
    item = data["items"][0]
    assert data["total"] == 7
    assert item["embedding_model"]["name"] == "Embed"
    assert item["rerank_model"]["name"] == "Rerank"
    assert kb_query.filters == [
        {"team_id__in": [team_id]},
        {"created_by": current_user},
        {"name__icontains": "hand"},
    ]
    assert kb_query.offset_value == 3
    assert kb_query.limit_value == 3


def test_get_document_returns_not_found_before_serialization(client, monkeypatch):
    api, _ = client
    kb_id = uuid4()
    monkeypatch.setattr(knowledge_bases, "check_kb_access", allow_kb_access)
    monkeypatch.setattr(knowledge_bases.Document, "filter", lambda **_kwargs: Query())

    response = api.get(f"/api/v1/knowledge-bases/{kb_id}/documents/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == 6002


def test_preview_chunks_rejects_document_without_file_or_url(client, monkeypatch):
    api, _ = client
    kb_id = uuid4()
    document = doc(knowledge_base_id=kb_id, file_path=None, source_url=None)
    monkeypatch.setattr(knowledge_bases, "check_kb_access", allow_kb_access)
    monkeypatch.setattr(
        knowledge_bases.Document,
        "filter",
        lambda **_kwargs: Query(first=document),
    )

    response = api.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/{document.id}/preview-chunks",
        json={"chunk_size": 100, "chunk_overlap": 10, "clean_text": True},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 1001


def test_add_url_document_requires_source_url(client, monkeypatch):
    api, _ = client
    kb_id = uuid4()
    monkeypatch.setattr(knowledge_bases, "check_kb_access", allow_kb_access)

    response = api.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/url",
        json={"name": "missing-url"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 1001
