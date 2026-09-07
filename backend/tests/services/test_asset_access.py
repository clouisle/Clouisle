from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.asset import AssetScopeType, AssetStatus
from app.schemas.response import BusinessError, ResponseCode
from app.services import asset_access


@pytest.mark.asyncio
async def test_protected_asset_requires_authentication():
    with pytest.raises(BusinessError) as error:
        await asset_access.authorize_protected_asset(
            "generated-images/2026/09/image.png", authenticated=None
        )

    assert error.value.code == ResponseCode.UNAUTHORIZED
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_protected_asset_hides_missing_or_unscoped_records(monkeypatch):
    asset_query = SimpleNamespace(first=AsyncMock(return_value=None))
    monkeypatch.setattr(asset_access.Asset, "filter", lambda **_: asset_query)
    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])

    with pytest.raises(BusinessError) as missing:
        await asset_access.authorize_protected_asset(
            "sandbox-artifacts/2026/09/missing.txt",
            authenticated=(user, None),
        )
    assert missing.value.status_code == 404

    asset_query.first.return_value = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        asset_access.AssetScopeRef, "filter", AsyncMock(return_value=[])
    )
    with pytest.raises(BusinessError) as unscoped:
        await asset_access.authorize_protected_asset(
            "sandbox-artifacts/2026/09/legacy.txt",
            authenticated=(user, None),
        )
    assert unscoped.value.status_code == 404


@pytest.mark.asyncio
async def test_protected_asset_allows_creator_for_legacy_unscoped_record(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])
    asset = SimpleNamespace(id=uuid4(), created_by_id=user.id)
    monkeypatch.setattr(
        asset_access.Asset,
        "filter",
        lambda **_: SimpleNamespace(first=AsyncMock(return_value=asset)),
    )
    monkeypatch.setattr(
        asset_access.AssetScopeRef, "filter", AsyncMock(return_value=[])
    )

    result = await asset_access.authorize_protected_asset(
        "sandbox-artifacts/2026/09/legacy.txt",
        authenticated=(user, None),
    )

    assert result is asset


@pytest.mark.asyncio
async def test_protected_asset_denies_user_without_scope_access(monkeypatch):
    asset_id = uuid4()
    conversation_id = uuid4()
    asset = SimpleNamespace(id=asset_id)
    monkeypatch.setattr(
        asset_access.Asset,
        "filter",
        lambda **_: SimpleNamespace(first=AsyncMock(return_value=asset)),
    )
    monkeypatch.setattr(
        asset_access.AssetScopeRef,
        "filter",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    scope_type=AssetScopeType.CONVERSATION,
                    scope_id=conversation_id,
                )
            ]
        ),
    )
    monkeypatch.setattr(
        asset_access.Conversation,
        "filter",
        lambda **_: SimpleNamespace(
            prefetch_related=lambda *_: SimpleNamespace(
                first=AsyncMock(
                    return_value=SimpleNamespace(
                        id=conversation_id,
                        agent_id=uuid4(),
                    )
                )
            )
        ),
    )
    monkeypatch.setattr(
        asset_access, "can_access_conversation", AsyncMock(return_value=False)
    )

    with pytest.raises(BusinessError) as denied:
        await asset_access.authorize_protected_asset(
            "sandbox-artifacts/2026/09/private.txt",
            authenticated=(SimpleNamespace(id=uuid4()), None),
        )
    assert denied.value.code == ResponseCode.PERMISSION_DENIED
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_conversation_asset_uses_canonical_api_key_scope_check(monkeypatch):
    asset_id = uuid4()
    agent_id = uuid4()
    conversation_id = uuid4()
    asset = SimpleNamespace(id=asset_id, status=AssetStatus.AVAILABLE)
    conversation = SimpleNamespace(
        id=conversation_id,
        user_id=uuid4(),
        agent_id=agent_id,
        agent=SimpleNamespace(team_id=uuid4()),
    )
    monkeypatch.setattr(
        asset_access.Asset,
        "filter",
        lambda **_: SimpleNamespace(first=AsyncMock(return_value=asset)),
    )
    monkeypatch.setattr(
        asset_access.AssetScopeRef,
        "filter",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    asset_id=asset_id,
                    scope_type=AssetScopeType.CONVERSATION,
                    scope_id=conversation_id,
                )
            ]
        ),
    )
    monkeypatch.setattr(
        asset_access.Conversation,
        "filter",
        lambda **_: SimpleNamespace(
            prefetch_related=lambda *_: SimpleNamespace(
                first=AsyncMock(return_value=conversation)
            )
        ),
    )
    monkeypatch.setattr(
        asset_access, "can_access_conversation", AsyncMock(return_value=True)
    )
    check_agent = AsyncMock()
    monkeypatch.setattr(asset_access, "check_api_key_agent_access", check_agent)

    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])
    api_key = SimpleNamespace()
    result = await asset_access.authorize_protected_asset(
        "generated-images/2026/09/image.png", authenticated=(user, api_key)
    )

    assert result is asset
    check_agent.assert_awaited_once_with(api_key, agent_id)

    check_agent.side_effect = BusinessError(
        code=ResponseCode.PERMISSION_DENIED,
        msg_key="api_key_no_agent_access",
        status_code=403,
    )
    with pytest.raises(BusinessError) as error:
        await asset_access.authorize_protected_asset(
            "generated-images/2026/09/image.png", authenticated=(user, api_key)
        )
    assert error.value.code == ResponseCode.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_workflow_asset_requires_workflow_access_and_api_key_scope(monkeypatch):
    asset_id = uuid4()
    workflow_id = uuid4()
    run_id = uuid4()
    user_id = uuid4()
    asset = SimpleNamespace(id=asset_id, status=AssetStatus.AVAILABLE)
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        triggered_by_id=user_id,
        workflow=SimpleNamespace(team_id=uuid4()),
    )
    monkeypatch.setattr(
        asset_access.Asset,
        "filter",
        lambda **_: SimpleNamespace(first=AsyncMock(return_value=asset)),
    )
    monkeypatch.setattr(
        asset_access.AssetScopeRef,
        "filter",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    asset_id=asset_id,
                    scope_type=AssetScopeType.WORKFLOW_RUN,
                    scope_id=run_id,
                )
            ]
        ),
    )
    monkeypatch.setattr(
        asset_access.WorkflowRun,
        "filter",
        lambda **_: SimpleNamespace(
            prefetch_related=lambda *_: SimpleNamespace(
                first=AsyncMock(return_value=run)
            )
        ),
    )
    check_workflow = AsyncMock()
    monkeypatch.setattr(asset_access, "check_api_key_workflow_access", check_workflow)

    user = SimpleNamespace(id=user_id, is_superuser=False, roles=[])
    api_key = SimpleNamespace()
    result = await asset_access.authorize_protected_asset(
        "sandbox-artifacts/2026/09/result.txt", authenticated=(user, api_key)
    )

    assert result is asset
    check_workflow.assert_awaited_once_with(api_key, workflow_id)


@pytest.mark.asyncio
async def test_api_key_denied_conversation_ref_continues_to_workflow_run_ref(
    monkeypatch,
):
    asset_id = uuid4()
    conversation_id = uuid4()
    workflow_id = uuid4()
    run_id = uuid4()
    user_id = uuid4()
    asset = SimpleNamespace(id=asset_id, status=AssetStatus.AVAILABLE)
    conversation = SimpleNamespace(id=conversation_id, agent_id=uuid4())
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        triggered_by_id=user_id,
        workflow=SimpleNamespace(team_id=uuid4()),
    )
    monkeypatch.setattr(
        asset_access.Asset,
        "filter",
        lambda **_: SimpleNamespace(first=AsyncMock(return_value=asset)),
    )
    monkeypatch.setattr(
        asset_access.AssetScopeRef,
        "filter",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    asset_id=asset_id,
                    scope_type=AssetScopeType.CONVERSATION,
                    scope_id=conversation_id,
                ),
                SimpleNamespace(
                    asset_id=asset_id,
                    scope_type=AssetScopeType.WORKFLOW_RUN,
                    scope_id=run_id,
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        asset_access.Conversation,
        "filter",
        lambda **_: SimpleNamespace(
            prefetch_related=lambda *_: SimpleNamespace(
                first=AsyncMock(return_value=conversation)
            )
        ),
    )
    monkeypatch.setattr(
        asset_access.WorkflowRun,
        "filter",
        lambda **_: SimpleNamespace(
            prefetch_related=lambda *_: SimpleNamespace(
                first=AsyncMock(return_value=run)
            )
        ),
    )
    monkeypatch.setattr(
        asset_access, "can_access_conversation", AsyncMock(return_value=True)
    )
    check_agent = AsyncMock(
        side_effect=BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="api_key_no_agent_access",
            status_code=403,
        )
    )
    check_workflow = AsyncMock()
    monkeypatch.setattr(asset_access, "check_api_key_agent_access", check_agent)
    monkeypatch.setattr(asset_access, "check_api_key_workflow_access", check_workflow)

    api_key = SimpleNamespace()
    result = await asset_access.authorize_protected_asset(
        "sandbox-artifacts/2026/09/shared.txt",
        authenticated=(
            SimpleNamespace(id=user_id, is_superuser=False, roles=[]),
            api_key,
        ),
    )

    assert result is asset
    check_agent.assert_awaited_once_with(api_key, conversation.agent_id)
    check_workflow.assert_awaited_once_with(api_key, workflow_id)


@pytest.mark.asyncio
async def test_unexpected_conversation_api_key_error_is_reraised(monkeypatch):
    asset_id = uuid4()
    conversation_id = uuid4()
    run_id = uuid4()
    user_id = uuid4()
    asset = SimpleNamespace(id=asset_id, status=AssetStatus.AVAILABLE)
    conversation = SimpleNamespace(id=conversation_id, agent_id=uuid4())
    monkeypatch.setattr(
        asset_access.Asset,
        "filter",
        lambda **_: SimpleNamespace(first=AsyncMock(return_value=asset)),
    )
    monkeypatch.setattr(
        asset_access.AssetScopeRef,
        "filter",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    asset_id=asset_id,
                    scope_type=AssetScopeType.CONVERSATION,
                    scope_id=conversation_id,
                ),
                SimpleNamespace(
                    asset_id=asset_id,
                    scope_type=AssetScopeType.WORKFLOW_RUN,
                    scope_id=run_id,
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        asset_access.Conversation,
        "filter",
        lambda **_: SimpleNamespace(
            prefetch_related=lambda *_: SimpleNamespace(
                first=AsyncMock(return_value=conversation)
            )
        ),
    )
    monkeypatch.setattr(
        asset_access, "can_access_conversation", AsyncMock(return_value=True)
    )
    unexpected = BusinessError(
        code=ResponseCode.INTERNAL_ERROR,
        msg_key="scope_check_failed",
        status_code=500,
    )
    check_agent = AsyncMock(side_effect=unexpected)
    check_workflow = AsyncMock()
    monkeypatch.setattr(asset_access, "check_api_key_agent_access", check_agent)
    monkeypatch.setattr(asset_access, "check_api_key_workflow_access", check_workflow)

    with pytest.raises(BusinessError) as error:
        await asset_access.authorize_protected_asset(
            "sandbox-artifacts/2026/09/shared.txt",
            authenticated=(
                SimpleNamespace(id=user_id, is_superuser=False, roles=[]),
                SimpleNamespace(),
            ),
        )

    assert error.value is unexpected
    check_workflow.assert_not_awaited()
