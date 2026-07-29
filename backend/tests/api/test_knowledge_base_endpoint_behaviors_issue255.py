from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    SearchRequest,
)
from app.schemas.response import BusinessError, ResponseCode
from app.services.retrieval import RetrievalError
from app.services.vector_store import DimensionMismatchError


class _Query:
    def __init__(self, result=None, items=(), total=0):
        self.result = result
        self.items = list(items)
        self.total = total
        self.filters = []
        self.excludes = []
        self.offset_value = None
        self.limit_value = None

    def filter(self, *args, **kwargs):
        self.filters.append((args, kwargs))
        return self

    def exclude(self, **kwargs):
        self.excludes.append(kwargs)
        return self

    def prefetch_related(self, *relations):
        return self

    def offset(self, value):
        self.offset_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    async def first(self):
        return self.result

    async def count(self):
        return self.total

    async def all(self):
        return self.items

    async def values_list(self, *fields, **kwargs):
        return self.items

    def __await__(self):
        async def resolve():
            return self.result if self.result is not None else self.items

        return resolve().__await__()


class _Permission:
    def __init__(self, code):
        self.code = code


class _Role:
    def __init__(self, *codes):
        self.permissions = [_Permission(code) for code in codes]


def _user(*, superuser=False, roles=()):
    return SimpleNamespace(
        id=uuid4(), is_superuser=superuser, roles=list(roles), is_active=True
    )


def _team():
    return SimpleNamespace(id=uuid4(), name="Platform", avatar_url=None)


def _kb(*, user=None, team=None):
    return SimpleNamespace(
        id=uuid4(),
        name="Handbook",
        description=None,
        icon=None,
        team=team or _team(),
        team_id=(team or _team()).id,
        created_by=user,
        embedding_model_id=None,
        rerank_model_id=None,
        embedding_dimension=None,
        status="active",
        settings=None,
        document_count=0,
        total_chunks=0,
        total_tokens=0,
        save=AsyncMock(),
        delete=AsyncMock(),
    )


@pytest.fixture(autouse=True)
def mock_lexical_helpers(monkeypatch):
    for name in ("delete_lexical_document", "index_lexical_chunk"):
        monkeypatch.setattr(knowledge_bases, name, AsyncMock())


@pytest.mark.parametrize(
    ("user", "permission", "expected"),
    [
        (_user(superuser=True), "kb:delete", True),
        (_user(roles=[_Role("kb:read")]), "kb:read", True),
        (_user(roles=[_Role("*")]), "kb:update", True),
        (_user(roles=[_Role("kb:read")]), "kb:update", False),
        (_user(), "kb:read", False),
    ],
)
def test_has_permission_variants(user, permission, expected):
    assert knowledge_bases._has_permission(user, permission) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "require_admin", "membership", "expected_code"),
    [
        ("platform", False, None, ResponseCode.NOT_TEAM_MEMBER),
        (
            "platform",
            True,
            SimpleNamespace(role="member"),
            ResponseCode.TEAM_ADMIN_REQUIRED,
        ),
        ("platform", True, SimpleNamespace(role="admin"), None),
        ("admin", True, None, None),
    ],
)
async def test_check_team_access_enforces_isolation(
    monkeypatch, mode, require_admin, membership, expected_code
):
    team = _team()
    user = _user()
    monkeypatch.setattr(
        knowledge_bases.Team, "filter", MagicMock(return_value=_Query(team))
    )
    membership_query = _Query(membership)
    monkeypatch.setattr(
        knowledge_bases.TeamMember,
        "filter",
        MagicMock(return_value=membership_query),
    )
    token = knowledge_bases._kb_access_mode.set(mode)
    try:
        if expected_code:
            with pytest.raises(BusinessError) as caught:
                await knowledge_bases.check_team_access(
                    team.id, user, require_admin=require_admin
                )
            assert caught.value.code == expected_code
        else:
            assert (
                await knowledge_bases.check_team_access(
                    team.id, user, require_admin=require_admin
                )
                is team
            )
    finally:
        knowledge_bases._kb_access_mode.reset(token)


@pytest.mark.asyncio
async def test_check_team_access_reports_missing_team(monkeypatch):
    monkeypatch.setattr(
        knowledge_bases.Team, "filter", MagicMock(return_value=_Query(None))
    )

    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.check_team_access(uuid4(), _user())

    assert caught.value.code == ResponseCode.TEAM_NOT_FOUND
    assert caught.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kb", "require_write", "allow_owner", "admin_checks", "expected_code"),
    [
        (None, False, True, 0, ResponseCode.KB_NOT_FOUND),
        ("owner", True, True, 0, None),
        ("owner", True, False, 1, None),
        ("other", True, True, 1, None),
    ],
)
async def test_check_kb_access_owner_and_admin_rules(
    monkeypatch, kb, require_write, allow_owner, admin_checks, expected_code
):
    user = _user()
    record = None if kb is None else _kb(user=user if kb == "owner" else _user())
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase,
        "filter",
        MagicMock(return_value=_Query(record)),
    )
    team_access = AsyncMock(return_value=record.team if record else None)
    monkeypatch.setattr(knowledge_bases, "check_team_access", team_access)
    token = knowledge_bases._kb_access_mode.set("platform")
    try:
        if expected_code:
            with pytest.raises(BusinessError) as caught:
                await knowledge_bases.check_kb_access(uuid4(), user)
            assert caught.value.code == expected_code
        else:
            assert (
                await knowledge_bases.check_kb_access(
                    record.id,
                    user,
                    require_write=require_write,
                    allow_owner_write=allow_owner,
                )
                is record
            )
            assert (
                sum(
                    call.kwargs.get("require_admin", False)
                    for call in team_access.await_args_list
                )
                == admin_checks
            )
    finally:
        knowledge_bases._kb_access_mode.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "authorized", "expected_code"),
    [
        (None, True, ResponseCode.MODEL_NOT_FOUND),
        (
            SimpleNamespace(name="Chat", model_type="llm"),
            True,
            ResponseCode.VALIDATION_ERROR,
        ),
        (
            SimpleNamespace(name="Embed", model_type="embedding"),
            False,
            ResponseCode.MODEL_NOT_AUTHORIZED,
        ),
        (SimpleNamespace(name="Embed", model_type="embedding"), True, None),
    ],
)
async def test_ensure_team_authorized_model(
    monkeypatch, model, authorized, expected_code
):
    monkeypatch.setattr(
        knowledge_bases.Model, "filter", MagicMock(return_value=_Query(model))
    )
    monkeypatch.setattr(
        knowledge_bases.TeamModel,
        "filter",
        MagicMock(return_value=_Query(SimpleNamespace() if authorized else None)),
    )

    if expected_code:
        with pytest.raises(BusinessError) as caught:
            await knowledge_bases.ensure_team_authorized_model(
                uuid4(), uuid4(), "embedding"
            )
        assert caught.value.code == expected_code
    else:
        assert (
            await knowledge_bases.ensure_team_authorized_model(
                uuid4(), uuid4(), "embedding"
            )
            is model
        )


@pytest.mark.asyncio
async def test_list_knowledge_bases_applies_platform_filters_and_pagination(
    monkeypatch,
):
    user = _user()
    query = _Query(
        items=[SimpleNamespace(embedding_model_id=None, rerank_model_id=None)], total=1
    )
    memberships = _Query(items=[uuid4()])
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase, "all", MagicMock(return_value=query)
    )
    monkeypatch.setattr(
        knowledge_bases.TeamMember, "filter", MagicMock(return_value=memberships)
    )
    monkeypatch.setattr(
        knowledge_bases.Model, "filter", MagicMock(return_value=_Query(items=[]))
    )
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBaseList,
        "model_validate",
        MagicMock(
            return_value=SimpleNamespace(
                model_dump=lambda: {
                    "embedding_model_id": None,
                    "rerank_model_id": None,
                }
            )
        ),
    )
    token = knowledge_bases._kb_access_mode.set("platform")
    try:
        result = await knowledge_bases.list_knowledge_bases(
            search="hand",
            status=["active"],
            own_only=True,
            page=2,
            page_size=5,
            current_user=user,
        )
    finally:
        knowledge_bases._kb_access_mode.reset(token)

    filter_kwargs = [kwargs for _, kwargs in query.filters]
    assert {"team_id__in": memberships.items} in filter_kwargs
    assert {"created_by": user} in filter_kwargs
    assert {"name__icontains": "hand"} in filter_kwargs
    assert {"status__in": ["active"]} in filter_kwargs
    assert (query.offset_value, query.limit_value) == (5, 5)
    assert result["data"]["total"] == 1


@pytest.mark.asyncio
async def test_create_knowledge_base_persists_authorized_models_and_audits(monkeypatch):
    user = _user()
    team = _team()
    created = _kb(user=user, team=team)
    reloaded = _kb(user=user, team=team)
    reloaded.id = created.id
    create = AsyncMock(return_value=created)
    authorize = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(
        knowledge_bases, "check_team_access", AsyncMock(return_value=team)
    )
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase, "filter", MagicMock(return_value=_Query(None))
    )
    monkeypatch.setattr(knowledge_bases.KnowledgeBase, "create", create)
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase, "get", MagicMock(return_value=_Query(reloaded))
    )
    monkeypatch.setattr(knowledge_bases, "ensure_team_authorized_model", authorize)
    monkeypatch.setattr(
        knowledge_bases,
        "kb_with_model_info",
        AsyncMock(return_value={"id": created.id}),
    )
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", audit)
    embedding_id, rerank_id = uuid4(), uuid4()

    result = await knowledge_bases.create_knowledge_base(
        kb_in=KnowledgeBaseCreate(
            name="Handbook",
            team_id=team.id,
            embedding_model_id=embedding_id,
            rerank_model_id=rerank_id,
        ),
        request=SimpleNamespace(),
        current_user=user,
    )

    assert create.await_args.kwargs["team"] is team
    assert create.await_args.kwargs["created_by"] is user
    assert [call.args[2] for call in authorize.await_args_list] == [
        "embedding",
        "rerank",
    ]
    audit.assert_awaited_once()
    assert result["data"]["id"] == created.id


@pytest.mark.asyncio
async def test_create_knowledge_base_rejects_duplicate_name(monkeypatch):
    monkeypatch.setattr(
        knowledge_bases, "check_team_access", AsyncMock(return_value=_team())
    )
    monkeypatch.setattr(
        knowledge_bases.KnowledgeBase,
        "filter",
        MagicMock(return_value=_Query(SimpleNamespace())),
    )

    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.create_knowledge_base(
            kb_in=KnowledgeBaseCreate(name="Handbook", team_id=uuid4()),
            request=SimpleNamespace(),
            current_user=_user(),
        )

    assert caught.value.code == ResponseCode.KB_NAME_EXISTS


@pytest.mark.asyncio
async def test_get_knowledge_base_returns_serialized_detail(monkeypatch):
    record = _kb()
    monkeypatch.setattr(
        knowledge_bases, "check_kb_access", AsyncMock(return_value=record)
    )
    monkeypatch.setattr(
        knowledge_bases,
        "kb_with_model_info",
        AsyncMock(return_value={"id": record.id, "name": record.name}),
    )

    result = await knowledge_bases.get_knowledge_base(record.id, _user())

    assert result["data"]["name"] == "Handbook"


@pytest.mark.asyncio
async def test_update_knowledge_base_rejects_embedding_model_change(monkeypatch):
    record = _kb()
    record.embedding_model_id = uuid4()
    monkeypatch.setattr(
        knowledge_bases, "check_kb_access", AsyncMock(return_value=record)
    )

    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.update_knowledge_base(
            kb_id=record.id,
            kb_in=KnowledgeBaseUpdate(embedding_model_id=uuid4()),
            request=SimpleNamespace(),
            current_user=_user(),
        )

    assert caught.value.code == ResponseCode.VALIDATION_ERROR
    assert caught.value.msg_key == "embedding_model_locked_after_kb_creation"
    record.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_knowledge_base_removes_record_and_audits(monkeypatch):
    record = _kb()
    audit = AsyncMock()
    access = AsyncMock(return_value=record)
    monkeypatch.setattr(knowledge_bases, "check_kb_access", access)
    monkeypatch.setattr(knowledge_bases.AuditLogService, "log", audit)

    result = await knowledge_bases.delete_knowledge_base(
        record.id, SimpleNamespace(), _user()
    )

    assert access.await_args.kwargs == {
        "require_write": True,
        "allow_owner_write": False,
    }
    record.delete.assert_awaited_once()
    audit.assert_awaited_once()
    assert result["data"]["id"] == str(record.id)


@pytest.mark.asyncio
async def test_search_forwards_kb_models_filters_and_rerank_overrides(monkeypatch):
    kb_id, doc_id = uuid4(), uuid4()
    record = _kb()
    record.embedding_model_id = uuid4()
    record.rerank_model_id = uuid4()
    record.team_id = uuid4()
    diagnostic = SimpleNamespace(kb_id=kb_id, code="timeout", detail=None)
    timing = SimpleNamespace(stage="recall", latency_ms=12.5)
    retrieve = AsyncMock(
        return_value=SimpleNamespace(
            results=({"content": "answer", "score": 0.9},),
            diagnostics=(diagnostic,),
            timings=(timing,),
        )
    )
    monkeypatch.setattr(
        knowledge_bases, "check_kb_access", AsyncMock(return_value=record)
    )
    monkeypatch.setattr("app.services.retrieval.retrieve", retrieve)

    result = await knowledge_bases.search_knowledge_base(
        kb_id,
        SearchRequest(
            query="policy",
            search_mode="vector",
            top_k=3,
            score_threshold=0.4,
            dense_weight=1.5,
            lexical_weight=0.5,
            rrf_k=80,
            filter_doc_ids=[doc_id],
            rerank_enabled=False,
        ),
        _user(),
    )

    request = retrieve.await_args.args[0]
    assert request.query == "policy"
    assert request.search_mode == "vector"
    assert request.top_k == 3
    assert request.score_threshold == 0.4
    assert request.dense_weight == 1.5
    assert request.lexical_weight == 0.5
    assert request.rrf_k == 80
    assert request.rerank_overrides == {"rerank_enabled": False}
    assert request.targets[0].kb_id == record.id
    assert request.targets[0].document_ids == frozenset({doc_id})
    assert request.targets[0].embedding_model_id == record.embedding_model_id
    assert result["data"]["total"] == 1
    assert result["data"]["diagnostics"] == (diagnostic,)
    assert result["data"]["timings"] == (timing,)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_code", "msg_key"),
    [
        (
            DimensionMismatchError("wrong dimension"),
            ResponseCode.VALIDATION_ERROR,
            "kb_embedding_dimension_mismatch",
        ),
        (
            RetrievalError("all retrieval targets failed", ()),
            ResponseCode.UNKNOWN_ERROR,
            "vector_search_failed",
        ),
    ],
)
async def test_search_translates_provider_failures(
    monkeypatch, failure, expected_code, msg_key
):
    record = _kb()
    monkeypatch.setattr(
        knowledge_bases, "check_kb_access", AsyncMock(return_value=record)
    )
    monkeypatch.setattr(
        "app.services.retrieval.retrieve", AsyncMock(side_effect=failure)
    )

    with pytest.raises(BusinessError) as caught:
        await knowledge_bases.search_knowledge_base(
            record.id, SearchRequest(query="policy"), _user()
        )

    assert caught.value.code == expected_code
    assert caught.value.msg_key == msg_key
