from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.api.v1.endpoints import agents as user_agents
from app.api.v1.endpoints import knowledge_bases as kb_endpoints
from app.models.knowledge_base import KnowledgeBaseSharePermission
from app.schemas.agent import AgentCreate, AgentKnowledgeBaseConfig
from app.schemas.knowledge_base import KnowledgeBaseShareInput
from app.schemas.response import BusinessError, ResponseCode

UTC = timezone.utc


class Query:
    def __init__(self, data=None):
        self._data = data

    def filter(self, *args, **kwargs):
        return self

    def exclude(self, *args, **kwargs):
        return self

    def prefetch_related(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def offset(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def values(self, *args, **kwargs):
        return self

    def values_list(self, *args, **kwargs):
        return self

    def __await__(self):
        async def _resolve():
            if isinstance(self._data, list):
                return self._data
            return [self._data] if self._data is not None else []

        return _resolve().__await__()

    async def first(self):
        if isinstance(self._data, list):
            return self._data[0] if self._data else None
        return self._data

    async def all(self):
        if isinstance(self._data, list):
            return self._data
        return [self._data] if self._data is not None else []

    async def count(self):
        if isinstance(self._data, list):
            return len(self._data)
        return 1 if self._data is not None else 0

    async def exists(self):
        if isinstance(self._data, list):
            return len(self._data) > 0
        if isinstance(self._data, bool):
            return self._data
        return self._data is not None


class SingleQuery:
    def __init__(self, data):
        self._data = data

    def prefetch_related(self, *args, **kwargs):
        return self

    def __await__(self):
        async def _resolve():
            return self._data

        return _resolve().__await__()


@pytest.mark.anyio
async def test_share_knowledge_base_creates_audits_and_serializes():
    kb_id, owner_team_id, target_team_id, user_id = (uuid4() for _ in range(4))
    kb = SimpleNamespace(
        id=kb_id,
        team_id=owner_team_id,
        team=SimpleNamespace(id=owner_team_id, name="Owner Team"),
        name="Docs",
        created_by=SimpleNamespace(id=user_id),
    )
    user = SimpleNamespace(id=user_id, username="alice", is_superuser=False)
    share = SimpleNamespace(
        id=uuid4(),
        knowledge_base_id=kb_id,
        knowledge_base=kb,
        shared_with_team_id=target_team_id,
        shared_with_team=SimpleNamespace(name="Target Team"),
        permission=KnowledgeBaseSharePermission.READ_ONLY,
        shared_by_id=user_id,
        shared_by=SimpleNamespace(username="alice"),
        shared_at=datetime.now(UTC),
        fetch_related=AsyncMock(),
    )

    with (
        patch.object(kb_endpoints.KnowledgeBase, "filter", return_value=Query(kb)),
        patch.object(
            kb_endpoints.Team,
            "filter",
            return_value=Query(SimpleNamespace(id=target_team_id)),
        ),
        patch.object(
            kb_endpoints.KnowledgeBaseShare, "filter", return_value=Query(None)
        ),
        patch.object(
            kb_endpoints.KnowledgeBaseShare,
            "create",
            new=AsyncMock(return_value=share),
        ) as create_mock,
        patch.object(kb_endpoints, "check_team_access", new=AsyncMock()) as access_mock,
        patch.object(
            kb_endpoints.AuditLogService, "log", new=AsyncMock()
        ) as audit_mock,
    ):
        response = await kb_endpoints.share_knowledge_base(
            kb_id,
            KnowledgeBaseShareInput(
                team_id=target_team_id,
                permission=KnowledgeBaseSharePermission.READ_ONLY,
            ),
            SimpleNamespace(),
            user,
        )

    access_mock.assert_awaited_once_with(owner_team_id, user, require_admin=True)
    create_mock.assert_awaited_once_with(
        knowledge_base_id=kb_id,
        shared_with_team_id=target_team_id,
        permission=KnowledgeBaseSharePermission.READ_ONLY,
        shared_by_id=user_id,
    )
    audit_mock.assert_awaited_once()
    assert response["data"]["shared_by_name"] == "alice"
    assert response["data"]["shared_with_team_name"] == "Target Team"
    assert response["data"]["knowledge_base_name"] == "Docs"


@pytest.mark.anyio
async def test_share_knowledge_base_validation_errors():
    kb_id, owner_team_id, target_team_id, user_id = (uuid4() for _ in range(4))
    kb = SimpleNamespace(
        id=kb_id,
        team_id=owner_team_id,
        team=SimpleNamespace(id=owner_team_id, name="Owner Team"),
        name="Docs",
    )
    user = SimpleNamespace(id=user_id)

    # 1. KB not found
    with (
        patch.object(kb_endpoints.KnowledgeBase, "filter", return_value=Query(None)),
        pytest.raises(BusinessError) as exc_info,
    ):
        await kb_endpoints.share_knowledge_base(
            kb_id,
            KnowledgeBaseShareInput(team_id=target_team_id),
            SimpleNamespace(),
            user,
        )
    assert exc_info.value.code == ResponseCode.KB_NOT_FOUND

    # 2. Target team not found
    with (
        patch.object(kb_endpoints.KnowledgeBase, "filter", return_value=Query(kb)),
        patch.object(kb_endpoints, "check_team_access", new=AsyncMock()),
        patch.object(kb_endpoints.Team, "filter", return_value=Query(None)),
        pytest.raises(BusinessError) as exc_info,
    ):
        await kb_endpoints.share_knowledge_base(
            kb_id,
            KnowledgeBaseShareInput(team_id=target_team_id),
            SimpleNamespace(),
            user,
        )
    assert exc_info.value.code == ResponseCode.TEAM_NOT_FOUND

    # 3. Cannot share to own team
    with (
        patch.object(kb_endpoints.KnowledgeBase, "filter", return_value=Query(kb)),
        patch.object(kb_endpoints, "check_team_access", new=AsyncMock()),
        patch.object(
            kb_endpoints.Team,
            "filter",
            return_value=Query(SimpleNamespace(id=owner_team_id)),
        ),
        pytest.raises(BusinessError) as exc_info,
    ):
        await kb_endpoints.share_knowledge_base(
            kb_id,
            KnowledgeBaseShareInput(team_id=owner_team_id),
            SimpleNamespace(),
            user,
        )
    assert exc_info.value.code == ResponseCode.BAD_REQUEST
    assert exc_info.value.msg_key == "kb_cannot_share_to_own_team"

    # 4. Already shared
    with (
        patch.object(kb_endpoints.KnowledgeBase, "filter", return_value=Query(kb)),
        patch.object(kb_endpoints, "check_team_access", new=AsyncMock()),
        patch.object(
            kb_endpoints.Team,
            "filter",
            return_value=Query(SimpleNamespace(id=target_team_id)),
        ),
        patch.object(
            kb_endpoints.KnowledgeBaseShare,
            "filter",
            return_value=Query(SimpleNamespace()),
        ),
        pytest.raises(BusinessError) as exc_info,
    ):
        await kb_endpoints.share_knowledge_base(
            kb_id,
            KnowledgeBaseShareInput(team_id=target_team_id),
            SimpleNamespace(),
            user,
        )
    assert exc_info.value.code == ResponseCode.DUPLICATE_NAME
    assert exc_info.value.msg_key == "kb_already_shared"


@pytest.mark.anyio
async def test_list_knowledge_base_shares_and_unshare():
    kb_id, owner_team_id, target_team_id, user_id = (uuid4() for _ in range(4))
    kb = SimpleNamespace(
        id=kb_id,
        team_id=owner_team_id,
        team=SimpleNamespace(id=owner_team_id, name="Owner Team"),
        name="Docs",
    )
    user = SimpleNamespace(id=user_id)
    share = SimpleNamespace(
        id=uuid4(),
        knowledge_base_id=kb_id,
        knowledge_base=kb,
        shared_with_team_id=target_team_id,
        shared_with_team=SimpleNamespace(name="Target Team"),
        permission=KnowledgeBaseSharePermission.READ_ONLY,
        shared_by_id=None,
        shared_by=None,
        shared_at=datetime.now(UTC),
        delete=AsyncMock(),
    )

    # List shares
    with (
        patch.object(kb_endpoints.KnowledgeBase, "filter", return_value=Query(kb)),
        patch.object(
            kb_endpoints.KnowledgeBaseShare, "filter", return_value=Query([share])
        ),
        patch.object(kb_endpoints, "check_team_access", new=AsyncMock()) as access_mock,
    ):
        res = await kb_endpoints.list_knowledge_base_shares(kb_id, user)
    access_mock.assert_awaited_once_with(owner_team_id, user)
    assert res["data"]["total"] == 1
    assert res["data"]["shares"][0]["shared_by_name"] == ""

    # Unshare
    with (
        patch.object(kb_endpoints.KnowledgeBase, "filter", return_value=Query(kb)),
        patch.object(
            kb_endpoints.KnowledgeBaseShare, "filter", return_value=Query(share)
        ),
        patch.object(kb_endpoints, "check_team_access", new=AsyncMock()) as access_mock,
        patch.object(
            kb_endpoints.AuditLogService, "log", new=AsyncMock()
        ) as audit_mock,
    ):
        unshare_res = await kb_endpoints.unshare_knowledge_base(
            kb_id, target_team_id, SimpleNamespace(), user
        )
    access_mock.assert_awaited_once_with(owner_team_id, user, require_admin=True)
    share.delete.assert_awaited_once()
    audit_mock.assert_awaited_once()
    assert unshare_res["code"] == ResponseCode.SUCCESS

    # Unshare not found
    with (
        patch.object(kb_endpoints.KnowledgeBase, "filter", return_value=Query(kb)),
        patch.object(
            kb_endpoints.KnowledgeBaseShare, "filter", return_value=Query(None)
        ),
        patch.object(kb_endpoints, "check_team_access", new=AsyncMock()),
        pytest.raises(BusinessError) as exc_info,
    ):
        await kb_endpoints.unshare_knowledge_base(
            kb_id, target_team_id, SimpleNamespace(), user
        )
    assert exc_info.value.code == ResponseCode.NOT_FOUND
    assert exc_info.value.msg_key == "kb_share_not_found"


@pytest.mark.anyio
async def test_check_kb_access_allows_shared_team_read_only():
    kb_id, owner_team_id, shared_team_id, user_id = (uuid4() for _ in range(4))
    kb = SimpleNamespace(
        id=kb_id,
        team_id=owner_team_id,
        team=SimpleNamespace(id=owner_team_id, name="Owner Team"),
        name="Docs",
        created_by=SimpleNamespace(id=uuid4()),
    )
    user = SimpleNamespace(id=user_id, is_superuser=False)

    async def fail_team_access(team_id, user, require_admin=False):
        if team_id == owner_team_id:
            raise BusinessError(
                code=ResponseCode.FORBIDDEN, msg_key="not_in_team", status_code=403
            )

    # 1. Read access when KB is shared with user's team
    with (
        patch.object(kb_endpoints.KnowledgeBase, "filter", return_value=Query(kb)),
        patch.object(kb_endpoints, "check_team_access", side_effect=fail_team_access),
        patch.object(
            kb_endpoints.TeamMember, "filter", return_value=Query([shared_team_id])
        ),
        patch.object(
            kb_endpoints.KnowledgeBaseShare, "filter", return_value=Query(True)
        ),
    ):
        result = await kb_endpoints.check_kb_access(kb_id, user, require_write=False)
        assert result.id == kb.id

    # 2. Write access denied even if shared
    with (
        patch.object(kb_endpoints.KnowledgeBase, "filter", return_value=Query(kb)),
        patch.object(kb_endpoints, "check_team_access", side_effect=fail_team_access),
        patch.object(
            kb_endpoints.TeamMember, "filter", return_value=Query([shared_team_id])
        ),
        patch.object(
            kb_endpoints.KnowledgeBaseShare, "filter", return_value=Query(True)
        ),
        pytest.raises(BusinessError) as exc_info,
    ):
        await kb_endpoints.check_kb_access(kb_id, user, require_write=True)
    assert exc_info.value.code == ResponseCode.FORBIDDEN
    # 3. Read access denied when not shared with user's team
    with (
        patch.object(kb_endpoints.KnowledgeBase, "filter", return_value=Query(kb)),
        patch.object(kb_endpoints, "check_team_access", side_effect=fail_team_access),
        patch.object(
            kb_endpoints.TeamMember, "filter", return_value=Query([shared_team_id])
        ),
        patch.object(
            kb_endpoints.KnowledgeBaseShare, "filter", return_value=Query(False)
        ),
        pytest.raises(BusinessError) as exc_info,
    ):
        await kb_endpoints.check_kb_access(kb_id, user, require_write=False)
    assert exc_info.value.code == ResponseCode.FORBIDDEN

    # 4. list_shares and unshare with missing KB raises 404
    with (
        patch.object(kb_endpoints.KnowledgeBase, "filter", return_value=Query(None)),
        pytest.raises(BusinessError) as exc_info,
    ):
        await kb_endpoints.list_knowledge_base_shares(kb_id, user)
    assert exc_info.value.code == ResponseCode.KB_NOT_FOUND

    with (
        patch.object(kb_endpoints.KnowledgeBase, "filter", return_value=Query(None)),
        pytest.raises(BusinessError) as exc_info,
    ):
        await kb_endpoints.unshare_knowledge_base(
            kb_id, shared_team_id, SimpleNamespace(), user
        )
    assert exc_info.value.code == ResponseCode.KB_NOT_FOUND


@pytest.mark.anyio
async def test_agent_linking_shared_knowledge_base():
    kb_id, owner_team_id, agent_team_id, user_id = (uuid4() for _ in range(4))
    kb = SimpleNamespace(
        id=kb_id,
        team_id=owner_team_id,
        team=SimpleNamespace(id=owner_team_id, name="Owner Team"),
        name="Shared Manual",
    )
    user = SimpleNamespace(id=user_id, username="alice", is_superuser=False)
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=agent_team_id,
        name="Support Agent",
        description=None,
        icon=None,
        avatar_url=None,
        rag_mode="agentic",
        tools_config=[],
        enable_attachments=False,
        attachment_config={},
        enable_user_input_request=False,
        enable_memory=False,
        enable_image_generation=False,
        enable_video_generation=False,
        context_compression_config=None,
        image_generation_config=None,
        video_generation_config=None,
        memory_config=None,
        variables=[],
        opening_message=None,
        suggested_questions=[],
        powered_by_text=None,
        embed_config={},
        status=SimpleNamespace(value="published"),
        visibility=SimpleNamespace(value="team"),
        conversation_count=0,
        message_count=0,
        total_tokens=0,
        created_by=user,
        model_id=None,
        model=None,
        team=SimpleNamespace(id=agent_team_id, name="Agent Team"),
        system_prompt="",
        max_iterations=10,
        hide_tool_calls=False,
        hide_message_actions=False,
        hide_reasoning=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        save=AsyncMock(),
    )

    agent_in = AgentCreate(
        name="Support Agent",
        team_id=agent_team_id,
        knowledge_base_configs=[AgentKnowledgeBaseConfig(knowledge_base_id=kb_id)],
    )

    # 1. Succeeded when KB is shared with agent_team_id
    with (
        patch.object(user_agents, "check_team_access", new=AsyncMock()),
        patch.object(user_agents.KnowledgeBase, "filter", return_value=Query(kb)),
        patch.object(
            user_agents.KnowledgeBaseShare, "filter", return_value=Query(True)
        ),
        patch.object(user_agents.Agent, "filter", return_value=Query(None)),
        patch.object(user_agents.Agent, "create", new=AsyncMock(return_value=agent)),
        patch.object(user_agents.deps, "check_scoped_permission", new=AsyncMock()),
        patch.object(user_agents.Agent, "get", lambda **kwargs: SingleQuery(agent)),
        patch.object(user_agents.AgentKnowledgeBase, "filter", return_value=Query([])),
        patch.object(
            user_agents.AgentKnowledgeBase, "create", new=AsyncMock()
        ) as akb_create,
        patch.object(user_agents.AuditLogService, "log", new=AsyncMock()),
        patch.object(user_agents.AuditLogService, "snapshot", return_value={}),
    ):
        await user_agents.create_agent(
            agent_in=agent_in, request=SimpleNamespace(), current_user=user
        )
        akb_create.assert_awaited_once()

    # 2. Failed when KB is not owned and not shared
    with (
        patch.object(user_agents.deps, "check_scoped_permission", new=AsyncMock()),
        patch.object(user_agents, "check_team_access", new=AsyncMock()),
        patch.object(user_agents.Agent, "filter", return_value=Query(None)),
        patch.object(user_agents.KnowledgeBase, "filter", return_value=Query(kb)),
        patch.object(
            user_agents.KnowledgeBaseShare, "filter", return_value=Query(False)
        ),
        pytest.raises(BusinessError) as exc_info,
    ):
        await user_agents.create_agent(
            agent_in=agent_in, request=SimpleNamespace(), current_user=user
        )
    assert exc_info.value.code == ResponseCode.KB_NOT_FOUND


@pytest.mark.anyio
async def test_list_knowledge_bases_with_shared_and_get_kb():
    owner_team_id, caller_team_id, user_id = (uuid4() for _ in range(3))
    owned_kb = SimpleNamespace(
        id=uuid4(),
        name="Owned KB",
        description="Owned",
        icon=None,
        team_id=caller_team_id,
        team=SimpleNamespace(id=caller_team_id, name="Caller Team"),
        created_by=SimpleNamespace(id=user_id, username="alice"),
        status="active",
        embedding_model_id=None,
        rerank_model_id=None,
        embedding_dimension=1536,
        document_count=2,
        total_chunks=10,
        total_tokens=1000,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    shared_kb = SimpleNamespace(
        id=uuid4(),
        name="Shared KB",
        description="Shared",
        icon=None,
        team_id=owner_team_id,
        team=SimpleNamespace(id=owner_team_id, name="Owner Team"),
        created_by=SimpleNamespace(id=uuid4(), username="bob"),
        status="active",
        embedding_model_id=None,
        rerank_model_id=None,
        embedding_dimension=1536,
        document_count=5,
        total_chunks=25,
        total_tokens=5000,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    share_record = SimpleNamespace(
        knowledge_base_id=shared_kb.id,
        shared_with_team_id=caller_team_id,
        permission="read_only",
    )
    user = SimpleNamespace(id=user_id, is_superuser=False)

    # 1. list_knowledge_bases with include_shared=True
    with (
        patch.object(kb_endpoints, "check_team_access", new=AsyncMock()),
        patch.object(
            kb_endpoints.KnowledgeBaseShare,
            "filter",
            return_value=Query([share_record]),
        ),
        patch.object(
            kb_endpoints.KnowledgeBase, "all", return_value=Query([owned_kb, shared_kb])
        ),
        patch.object(kb_endpoints.Model, "filter", return_value=Query([])),
    ):
        res = await kb_endpoints.list_knowledge_bases(
            team_id=caller_team_id,
            include_shared=True,
            current_user=user,
        )
    items = res["data"]["items"]
    assert len(items) == 2
    assert items[0]["is_owned"] is True
    assert items[1]["is_owned"] is False
    assert items[1]["owner_team_name"] == "Owner Team"

    # 2. get_knowledge_base with caller_team_id
    with (
        patch.object(
            kb_endpoints, "check_kb_access", new=AsyncMock(return_value=shared_kb)
        ),
        patch.object(
            kb_endpoints, "get_embedding_model_info", new=AsyncMock(return_value=None)
        ),
        patch.object(
            kb_endpoints, "get_rerank_model_info", new=AsyncMock(return_value=None)
        ),
        patch.object(
            kb_endpoints.KnowledgeBaseShare, "filter", return_value=Query(share_record)
        ),
    ):
        get_res = await kb_endpoints.get_knowledge_base(
            kb_id=shared_kb.id,
            team_id=caller_team_id,
            current_user=user,
        )
    assert get_res["data"]["is_owned"] is False
    assert get_res["data"]["owner_team_name"] == "Owner Team"
    assert get_res["data"]["share_permission"] == KnowledgeBaseSharePermission.READ_ONLY

    # 3. list without shared KBs when include_shared=False
    share_filter_mock = MagicMock(return_value=Query([]))
    with (
        patch.object(kb_endpoints, "check_team_access", new=AsyncMock()),
        patch.object(kb_endpoints.KnowledgeBase, "all", return_value=Query([owned_kb])),
        patch.object(kb_endpoints.KnowledgeBaseShare, "filter", share_filter_mock),
        patch.object(kb_endpoints.Model, "filter", return_value=Query([])),
    ):
        res_no_shared = await kb_endpoints.list_knowledge_bases(
            team_id=caller_team_id,
            include_shared=False,
            current_user=user,
        )
    assert len(res_no_shared["data"]["items"]) == 1
    # KnowledgeBaseShare.filter(shared_with_team_id=...) must not be called when include_shared=False
    assert not any(
        c.kwargs.get("shared_with_team_id") == caller_team_id
        for c in share_filter_mock.call_args_list
    )
    # 4. list without team_id and include_shared=False
    with (
        patch.object(
            kb_endpoints.TeamMember, "filter", return_value=Query([caller_team_id])
        ),
        patch.object(kb_endpoints.KnowledgeBase, "all", return_value=Query([owned_kb])),
        patch.object(kb_endpoints.Model, "filter", return_value=Query([])),
    ):
        res_no_team_no_shared = await kb_endpoints.list_knowledge_bases(
            include_shared=False,
            current_user=user,
        )
    assert len(res_no_team_no_shared["data"]["items"]) == 1

    # 5. list without team_id and include_shared=True
    with (
        patch.object(
            kb_endpoints.TeamMember, "filter", return_value=Query([caller_team_id])
        ),
        patch.object(
            kb_endpoints.KnowledgeBaseShare,
            "filter",
            return_value=Query([share_record]),
        ),
        patch.object(
            kb_endpoints.KnowledgeBase, "all", return_value=Query([owned_kb, shared_kb])
        ),
        patch.object(kb_endpoints.Model, "filter", return_value=Query([])),
    ):
        res_no_team_shared = await kb_endpoints.list_knowledge_bases(
            include_shared=True,
            current_user=user,
        )
    assert len(res_no_team_shared["data"]["items"]) == 2
    items_by_id = {item["id"]: item for item in res_no_team_shared["data"]["items"]}
    assert items_by_id[owned_kb.id]["is_owned"] is True
    assert items_by_id[shared_kb.id]["is_owned"] is False
    assert (
        items_by_id[shared_kb.id]["share_permission"]
        == KnowledgeBaseSharePermission.READ_ONLY
    )
    assert items_by_id[shared_kb.id]["shared_with_count"] == 0

    # 5b. get without team_id for shared KB
    with (
        patch.object(
            kb_endpoints, "check_kb_access", new=AsyncMock(return_value=shared_kb)
        ),
        patch.object(
            kb_endpoints.TeamMember, "filter", return_value=Query([caller_team_id])
        ),
        patch.object(
            kb_endpoints.KnowledgeBaseShare,
            "filter",
            return_value=Query([share_record]),
        ),
        patch.object(
            kb_endpoints, "get_embedding_model_info", new=AsyncMock(return_value=None)
        ),
        patch.object(
            kb_endpoints, "get_rerank_model_info", new=AsyncMock(return_value=None)
        ),
    ):
        get_no_team_res = await kb_endpoints.get_knowledge_base(
            kb_id=shared_kb.id,
            team_id=None,
            current_user=user,
        )
    assert get_no_team_res["data"]["is_owned"] is False
    assert (
        get_no_team_res["data"]["share_permission"]
        == KnowledgeBaseSharePermission.READ_ONLY
    )
    assert get_no_team_res["data"]["shared_with_count"] == 0

    # 5c. kb_with_model_info TeamMember exception fallback
    with (
        patch.object(
            kb_endpoints.TeamMember,
            "filter",
            side_effect=RuntimeError("team lookup error"),
        ),
        patch.object(
            kb_endpoints.KnowledgeBaseShare,
            "filter",
            return_value=Query([share_record]),
        ),
        patch.object(
            kb_endpoints, "get_embedding_model_info", new=AsyncMock(return_value=None)
        ),
        patch.object(
            kb_endpoints, "get_rerank_model_info", new=AsyncMock(return_value=None)
        ),
    ):
        res_tm_err = await kb_endpoints.kb_with_model_info(
            shared_kb, current_team_id=None, current_user=user
        )
    assert res_tm_err["is_owned"] is True
    with (
        patch.object(
            kb_endpoints, "check_kb_access", new=AsyncMock(return_value=shared_kb)
        ),
        patch.object(
            kb_endpoints, "get_embedding_model_info", new=AsyncMock(return_value=None)
        ),
        patch.object(
            kb_endpoints, "get_rerank_model_info", new=AsyncMock(return_value=None)
        ),
        patch.object(
            kb_endpoints.KnowledgeBaseShare,
            "filter",
            side_effect=RuntimeError("db error"),
        ),
    ):
        err_res = await kb_endpoints.get_knowledge_base(
            kb_id=shared_kb.id,
            team_id=caller_team_id,
            current_user=user,
        )
    assert err_res["data"]["shared_with_count"] == 0
    assert err_res["data"]["share_permission"] == KnowledgeBaseSharePermission.READ_ONLY

    # 7. unshare non-existent share error branch
    with (
        patch.object(
            kb_endpoints.KnowledgeBase, "filter", return_value=Query(owned_kb)
        ),
        patch.object(kb_endpoints, "check_team_access", new=AsyncMock()),
        patch.object(
            kb_endpoints.KnowledgeBaseShare, "filter", return_value=Query(None)
        ),
        pytest.raises(BusinessError) as unshare_exc,
    ):
        await kb_endpoints.unshare_knowledge_base(
            kb_id=owned_kb.id,
            team_id=uuid4(),
            request=SimpleNamespace(),
            current_user=user,
        )
    assert unshare_exc.value.code == ResponseCode.NOT_FOUND
