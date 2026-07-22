from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import api_keys
from app.schemas.response import BusinessError, ResponseCode


def user(*, is_superuser=False):
    return SimpleNamespace(id=uuid4(), is_superuser=is_superuser)


@pytest.mark.asyncio
async def test_owner_and_superuser_authorization_boundaries():
    owner = user()
    key = SimpleNamespace(user_id=owner.id)

    await api_keys.ensure_api_key_owner(key, owner)
    await api_keys.ensure_api_key_owner(key, user(is_superuser=True))

    with pytest.raises(BusinessError) as exc_info:
        await api_keys.ensure_api_key_owner(key, user())

    assert exc_info.value.code == ResponseCode.PERMISSION_DENIED
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_missing_api_key_returns_not_found(monkeypatch):
    query = MagicMock()
    query.prefetch_related.return_value.first = AsyncMock(return_value=None)
    filter_mock = MagicMock(return_value=query)
    monkeypatch.setattr(api_keys.APIKey, "filter", filter_mock)
    key_id = uuid4()

    with pytest.raises(BusinessError) as exc_info:
        await api_keys.get_api_key_or_404(key_id)

    filter_mock.assert_called_once_with(id=key_id)
    assert exc_info.value.code == ResponseCode.NOT_FOUND
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_activate_api_key_happy_path(monkeypatch):
    current_user = user()
    key = SimpleNamespace(
        id=uuid4(),
        user_id=current_user.id,
        name="Deploy key",
        is_active=False,
        save=AsyncMock(),
    )
    audit_log = AsyncMock()
    monkeypatch.setattr(api_keys, "get_api_key_or_404", AsyncMock(return_value=key))
    monkeypatch.setattr(
        api_keys, "build_api_key_response", AsyncMock(return_value={"id": key.id})
    )
    monkeypatch.setattr(api_keys.AuditLogService, "log", audit_log)

    result = await api_keys.activate_api_key(MagicMock(), key.id, current_user)

    assert key.is_active is True
    key.save.assert_awaited_once_with()
    audit_log.assert_awaited_once()
    assert result["data"] == {"id": key.id}
    assert result["code"] == ResponseCode.SUCCESS


@pytest.mark.asyncio
async def test_activate_api_key_rejects_already_active(monkeypatch):
    current_user = user()
    key = SimpleNamespace(user_id=current_user.id, is_active=True)
    monkeypatch.setattr(api_keys, "get_api_key_or_404", AsyncMock(return_value=key))

    with pytest.raises(BusinessError) as exc_info:
        await api_keys.activate_api_key(MagicMock(), uuid4(), current_user)

    assert exc_info.value.code == ResponseCode.BAD_REQUEST
    assert exc_info.value.msg_key == "api_key_already_active"


@pytest.mark.asyncio
async def test_deactivate_api_key_rejects_already_inactive(monkeypatch):
    current_user = user()
    key = SimpleNamespace(user_id=current_user.id, is_active=False)
    monkeypatch.setattr(api_keys, "get_api_key_or_404", AsyncMock(return_value=key))

    with pytest.raises(BusinessError) as exc_info:
        await api_keys.deactivate_api_key(MagicMock(), uuid4(), current_user)

    assert exc_info.value.code == ResponseCode.BAD_REQUEST
    assert exc_info.value.msg_key == "api_key_already_inactive"
