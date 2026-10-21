from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import wechat_knowledge
from app.models.wechat_agent import WeChatAgentReceipt
from app.schemas.response import BusinessError, ResponseCode


@pytest.fixture(autouse=True)
def enabled_wechat_features(monkeypatch):
    monkeypatch.setattr(wechat_knowledge, "require_feature", AsyncMock())


@pytest.mark.asyncio
async def test_purpose_rejects_fields_from_the_other_purpose(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    binding = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        wechat_knowledge, "owned_binding", AsyncMock(return_value=binding)
    )
    collection_query = MagicMock()
    collection_query.first = AsyncMock()
    monkeypatch.setattr(
        wechat_knowledge.WeChatKnowledgeCollection,
        "filter",
        MagicMock(return_value=collection_query),
    )

    with pytest.raises(BusinessError) as error:
        await wechat_knowledge.update_purpose(
            binding.id,
            wechat_knowledge.PurposeInput(purpose="agent", knowledge_base_id=uuid4()),
            user,
        )

    assert error.value.msg_key == "validation_error"
    collection_query.first.assert_not_awaited()

    with pytest.raises(BusinessError) as error:
        await wechat_knowledge.update_purpose(
            binding.id,
            wechat_knowledge.PurposeInput(
                purpose="knowledge_collection", agent_id=uuid4()
            ),
            user,
        )

    assert error.value.msg_key == "validation_error"
    collection_query.first.assert_not_awaited()


@pytest.mark.asyncio
async def test_purpose_refuses_to_read_configuration_for_foreign_binding(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    binding_id = uuid4()
    denied = BusinessError(
        code=ResponseCode.VALIDATION_ERROR,
        msg_key="wechat_binding_not_found",
        status_code=404,
    )
    monkeypatch.setattr(
        wechat_knowledge, "owned_binding", AsyncMock(side_effect=denied)
    )
    collection_filter = MagicMock()
    monkeypatch.setattr(
        wechat_knowledge.WeChatKnowledgeCollection, "filter", collection_filter
    )

    with pytest.raises(BusinessError) as error:
        await wechat_knowledge.update_purpose(
            binding_id,
            wechat_knowledge.PurposeInput(purpose="knowledge_collection"),
            user,
        )

    assert error.value is denied
    collection_filter.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["receipts", "agent_receipts"])
async def test_receipt_lists_reject_foreign_binding_before_reading_receipts(
    monkeypatch, route
):
    user = SimpleNamespace(id=uuid4())
    binding_id = uuid4()
    denied = BusinessError(
        code=ResponseCode.VALIDATION_ERROR,
        msg_key="wechat_binding_not_found",
        status_code=404,
    )
    monkeypatch.setattr(
        wechat_knowledge, "owned_binding", AsyncMock(side_effect=denied)
    )
    receipt_model = (
        wechat_knowledge.WeChatKnowledgeReceipt
        if route == "receipts"
        else WeChatAgentReceipt
    )
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    receipt_filter = MagicMock(return_value=query)
    monkeypatch.setattr(receipt_model, "filter", receipt_filter)

    with pytest.raises(BusinessError) as error:
        await getattr(wechat_knowledge, route)(binding_id=binding_id, user=user)

    assert error.value is denied
    receipt_filter.assert_called_once_with(user_id=user.id)
    wechat_knowledge.owned_binding.assert_awaited_once_with(binding_id, user)
    query.filter.assert_not_called()


@pytest.mark.asyncio
async def test_targets_exclude_write_unauthorized_candidates_and_restore_access_mode(
    monkeypatch,
):
    from app.api.v1.endpoints import knowledge_bases

    denied_kb = SimpleNamespace(
        id=uuid4(), name="Read-only", team=SimpleNamespace(name="Team")
    )
    allowed_kb = SimpleNamespace(
        id=uuid4(), name="Writable", team=SimpleNamespace(name="Team")
    )

    class CandidateQuery:
        def filter(self, *_args):
            return self

        def prefetch_related(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def __await__(self):
            async def rows():
                return [denied_kb, allowed_kb]

            return rows().__await__()

    monkeypatch.setattr(
        wechat_knowledge.KnowledgeBase,
        "filter",
        MagicMock(return_value=CandidateQuery()),
    )
    monkeypatch.setattr(
        knowledge_bases, "kb_read_visibility_filter", AsyncMock(return_value=None)
    )

    async def authorize(identifier, _user):
        if identifier == denied_kb.id:
            raise BusinessError(
                code=ResponseCode.INSUFFICIENT_PRIVILEGES,
                msg_key="permission_denied",
                status_code=403,
            )
        return allowed_kb

    target_check = AsyncMock(side_effect=authorize)
    monkeypatch.setattr(wechat_knowledge, "check_binding_target", target_check)
    user = SimpleNamespace(id=uuid4())
    prior_mode = knowledge_bases._kb_access_mode.get()

    result = await wechat_knowledge.targets(user)

    assert result["data"] == [
        {"id": str(allowed_kb.id), "name": "Writable", "team_name": "Team"}
    ]
    assert target_check.await_count == 2
    assert knowledge_bases._kb_access_mode.get() == prior_mode


@pytest.mark.asyncio
async def test_agent_model_lookup_requires_authorized_agent(monkeypatch):
    from app.services import wechat_purpose

    user = SimpleNamespace(id=uuid4())
    agent_id = uuid4()
    denied = BusinessError(
        code=ResponseCode.INSUFFICIENT_PRIVILEGES,
        msg_key="permission_denied",
        status_code=403,
    )
    authorize = AsyncMock(side_effect=denied)
    monkeypatch.setattr(wechat_purpose, "authorized_agent", authorize)
    model_lookup = AsyncMock()
    monkeypatch.setattr(wechat_knowledge, "available_models", model_lookup)

    with pytest.raises(BusinessError) as error:
        await wechat_knowledge.agent_models(agent_id, user)

    assert error.value is denied
    authorize.assert_awaited_once_with(agent_id, user)
    model_lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_model_options_require_authorized_target(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    kb_id = uuid4()
    denied = BusinessError(
        code=ResponseCode.INSUFFICIENT_PRIVILEGES,
        msg_key="permission_denied",
        status_code=403,
    )
    authorize = AsyncMock(side_effect=denied)
    monkeypatch.setattr(wechat_knowledge, "check_binding_target", authorize)
    model_lookup = AsyncMock()
    monkeypatch.setattr(wechat_knowledge, "available_models", model_lookup)

    with pytest.raises(BusinessError) as error:
        await wechat_knowledge.models(kb_id, user)

    assert error.value is denied
    authorize.assert_awaited_once_with(kb_id, user)
    model_lookup.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("item_state", ["missing", "without_original"])
async def test_original_download_rejects_missing_retained_item(monkeypatch, item_state):
    from app.models.wechat_knowledge import WeChatKnowledgeItem

    item = None if item_state == "missing" else SimpleNamespace(original_path=None)
    query = MagicMock()
    query.prefetch_related.return_value = query
    query.first = AsyncMock(return_value=item)
    lookup = MagicMock(return_value=query)
    monkeypatch.setattr(WeChatKnowledgeItem, "filter", lookup)

    with pytest.raises(BusinessError) as error:
        await wechat_knowledge.original(uuid4(), SimpleNamespace(id=uuid4()))

    assert error.value.msg_key == "file_not_found"


@pytest.mark.asyncio
async def test_original_download_rejects_noncanonical_path_before_storage(monkeypatch):
    from app.api.v1.endpoints import knowledge_bases
    from app.models.wechat_knowledge import WeChatKnowledgeItem
    from app.services import document_processor, upload_storage

    kb_id, item_id = uuid4(), uuid4()
    item = SimpleNamespace(
        id=item_id,
        original_path="documents/foreign/wechat/item/original/file.pdf",
        receipt=SimpleNamespace(knowledge_base_id=kb_id),
        name="file.pdf",
    )
    query = MagicMock()
    query.prefetch_related.return_value = query
    query.first = AsyncMock(return_value=item)
    monkeypatch.setattr(WeChatKnowledgeItem, "filter", MagicMock(return_value=query))
    authorize = AsyncMock()
    monkeypatch.setattr(knowledge_bases, "check_kb_access", authorize)
    storage = SimpleNamespace(exists=AsyncMock(return_value=True))
    get_storage = AsyncMock(return_value=storage)
    monkeypatch.setattr(upload_storage, "get_upload_storage_backend", get_storage)
    monkeypatch.setattr(document_processor, "_storage_root", lambda: "/uploads")
    user = SimpleNamespace(id=uuid4())
    prior_mode = knowledge_bases._kb_access_mode.get()

    with pytest.raises(BusinessError) as error:
        await wechat_knowledge.original(item_id, user)

    assert error.value.msg_key == "file_not_found"
    authorize.assert_awaited_once_with(kb_id, user)
    assert knowledge_bases._kb_access_mode.get() == prior_mode
    get_storage.assert_not_awaited()


@pytest.mark.asyncio
async def test_original_download_returns_authorized_retained_file(monkeypatch):
    from app.api.v1.endpoints import knowledge_bases
    from app.models.wechat_knowledge import WeChatKnowledgeItem
    from app.services import document_processor, upload_storage

    kb_id, item_id = uuid4(), uuid4()
    path = f"documents/{kb_id}/wechat/{item_id}/original/article.pdf"
    item = SimpleNamespace(
        id=item_id,
        original_path=path,
        receipt=SimpleNamespace(knowledge_base_id=kb_id),
        name="",
    )
    query = MagicMock()
    query.prefetch_related.return_value = query
    query.first = AsyncMock(return_value=item)
    monkeypatch.setattr(WeChatKnowledgeItem, "filter", MagicMock(return_value=query))
    authorize = AsyncMock()
    monkeypatch.setattr(knowledge_bases, "check_kb_access", authorize)
    response = object()
    storage = SimpleNamespace(
        exists=AsyncMock(return_value=True),
        response=AsyncMock(return_value=response),
    )
    monkeypatch.setattr(
        upload_storage,
        "get_upload_storage_backend",
        AsyncMock(return_value=storage),
    )
    monkeypatch.setattr(document_processor, "_storage_root", lambda: "/uploads")

    result = await wechat_knowledge.original(item_id, SimpleNamespace(id=uuid4()))

    assert result is response
    storage.exists.assert_awaited_once_with(path)
    storage.response.assert_awaited_once_with(
        path, content_type="application/octet-stream", filename="original"
    )


@pytest.mark.asyncio
async def test_original_download_rejects_storage_object_that_no_longer_exists(
    monkeypatch,
):
    from app.api.v1.endpoints import knowledge_bases
    from app.models.wechat_knowledge import WeChatKnowledgeItem
    from app.services import document_processor, upload_storage

    kb_id, item_id = uuid4(), uuid4()
    path = f"documents/{kb_id}/wechat/{item_id}/original/article.pdf"
    item = SimpleNamespace(
        id=item_id,
        original_path=path,
        receipt=SimpleNamespace(knowledge_base_id=kb_id),
        name="article.pdf",
    )
    query = MagicMock()
    query.prefetch_related.return_value = query
    query.first = AsyncMock(return_value=item)
    monkeypatch.setattr(WeChatKnowledgeItem, "filter", MagicMock(return_value=query))
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    response = AsyncMock()
    storage = SimpleNamespace(exists=AsyncMock(return_value=False), response=response)
    get_storage = AsyncMock(return_value=storage)
    monkeypatch.setattr(upload_storage, "get_upload_storage_backend", get_storage)
    monkeypatch.setattr(document_processor, "_storage_root", lambda: "/uploads")

    with pytest.raises(BusinessError) as error:
        await wechat_knowledge.original(item_id, SimpleNamespace(id=uuid4()))

    assert error.value.msg_key == "file_not_found"
    storage.exists.assert_awaited_once_with(path)
    response.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_receipt_list_filters_owned_binding_and_falls_back_to_session(
    monkeypatch,
):
    from app.models.wechat_agent import WeChatAgentSession

    user = SimpleNamespace(id=uuid4())
    binding_id, agent_id, conversation_id = uuid4(), uuid4(), uuid4()
    receipt_id = uuid4()
    receipt = SimpleNamespace(
        id=receipt_id,
        binding_id=binding_id,
        status="completed",
        agent=SimpleNamespace(id=agent_id, name="Writer"),
        agent_id=agent_id,
        run=None,
        run_id=None,
        error=None,
        deliveries=[SimpleNamespace(status="submitted")],
        created_at="created",
    )

    class Query:
        def __init__(self):
            self.filters = []

        def filter(self, **kwargs):
            self.filters.append(kwargs)
            return self

        def prefetch_related(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def limit(self, *_args):
            return self

        def __await__(self):
            async def resolve():
                return [receipt]

            return resolve().__await__()

    query = Query()
    receipt_filter = MagicMock(return_value=query)
    monkeypatch.setattr(WeChatAgentReceipt, "filter", receipt_filter)
    monkeypatch.setattr(
        wechat_knowledge, "owned_binding", AsyncMock(return_value=SimpleNamespace())
    )
    session_query = SimpleNamespace(
        first=AsyncMock(return_value=SimpleNamespace(conversation_id=conversation_id))
    )
    session_filter = MagicMock(return_value=session_query)
    monkeypatch.setattr(WeChatAgentSession, "filter", session_filter)

    result = await wechat_knowledge.agent_receipts(binding_id=binding_id, user=user)

    assert query.filters == [{"binding_id": binding_id}]
    wechat_knowledge.owned_binding.assert_awaited_once_with(binding_id, user)
    session_filter.assert_called_once_with(binding_id=binding_id, agent_id=agent_id)
    row = result["data"][0]
    assert row["conversation_id"] == str(conversation_id)
    assert row["delivery_status"] == ["submitted"]
    assert row["agent_name"] == "Writer"


@pytest.mark.asyncio
async def test_agent_discovery_skips_unauthorized_published_candidates(monkeypatch):
    from app.models.agent import Agent
    from app.services import wechat_purpose

    user = SimpleNamespace(id=uuid4())
    denied = SimpleNamespace(id=uuid4())
    allowed = SimpleNamespace(
        id=uuid4(),
        name="Writer",
        team=SimpleNamespace(name="Team"),
        variables=[],
        enable_attachments=True,
        attachment_config={"max_files": 2},
    )

    class Candidates:
        def only(self, *_fields):
            return self

        def order_by(self, *_fields):
            return self

        def __aiter__(self):
            async def rows():
                for candidate in (denied, allowed):
                    yield candidate

            return rows().__aiter__()

    monkeypatch.setattr(Agent, "filter", lambda **_kwargs: Candidates())

    async def authorize(identifier, _user):
        if identifier == denied.id:
            raise BusinessError(
                code=ResponseCode.INSUFFICIENT_PRIVILEGES,
                msg_key="permission_denied",
                status_code=403,
            )
        return allowed

    authorize_agent = AsyncMock(side_effect=authorize)
    monkeypatch.setattr(wechat_purpose, "authorized_agent", authorize_agent)

    result = await wechat_knowledge.agents(user)

    assert result["data"] == [
        {
            "id": str(allowed.id),
            "name": "Writer",
            "team_name": "Team",
            "variables": [],
            "enable_attachments": True,
            "attachment_config": {"max_files": 2},
        }
    ]
    assert authorize_agent.await_args_list[0].args == (denied.id, user)
    assert authorize_agent.await_args_list[1].args == (allowed.id, user)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["receipts", "agent_receipts"])
async def test_receipt_lists_without_binding_id_keep_user_scope_only(
    monkeypatch, route
):
    from app.models.wechat_agent import WeChatAgentReceipt

    user = SimpleNamespace(id=uuid4())

    class Query:
        def __init__(self):
            self.filters = []

        def filter(self, **kwargs):
            self.filters.append(kwargs)
            return self

        def prefetch_related(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def limit(self, *_args):
            return self

        def __await__(self):
            async def resolve():
                return []

            return resolve().__await__()

    model = (
        wechat_knowledge.WeChatKnowledgeReceipt
        if route == "receipts"
        else WeChatAgentReceipt
    )
    query = Query()
    receipt_filter = MagicMock(return_value=query)
    monkeypatch.setattr(model, "filter", receipt_filter)
    owned_binding = AsyncMock()
    monkeypatch.setattr(wechat_knowledge, "owned_binding", owned_binding)

    result = await getattr(wechat_knowledge, route)(user=user)

    assert result["data"] == []
    receipt_filter.assert_called_once_with(user_id=user.id)
    assert query.filters == []
    owned_binding.assert_not_awaited()
