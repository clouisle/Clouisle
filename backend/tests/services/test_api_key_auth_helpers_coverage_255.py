from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api import deps
from app.models.api_key import APIKey
from app.schemas.response import BusinessError, ResponseCode


class KeyQuery:
    def __init__(self, keys):
        self.keys = keys
        self.related = None

    def prefetch_related(self, *related):
        self.related = related

        async def result():
            return self.keys

        return result()


@pytest.mark.asyncio
async def test_authenticate_api_key_updates_last_used_for_matching_active_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    user = SimpleNamespace(is_active=True)
    key = SimpleNamespace(
        key_hash="hash",
        expires_at=None,
        user=user,
        last_used_at=None,
        save=AsyncMock(),
    )
    query = KeyQuery([key])
    captured = {}

    def fake_filter(**kwargs):
        captured.update(kwargs)
        return query

    monkeypatch.setattr(deps.APIKey, "filter", fake_filter)
    monkeypatch.setattr(
        deps.APIKey, "verify_key", lambda plain, hashed: plain == "clou_ok"
    )
    monkeypatch.setattr(deps, "now_utc", lambda: now)

    result_user, result_key = await deps._authenticate_api_key("clou_ok")

    assert (result_user, result_key) == (user, key)
    assert captured == {"key_prefix": "clou_ok", "is_active": True}
    assert query.related == ("user", "user__roles__permissions", "agents")
    assert key.last_used_at == now
    key.save.assert_awaited_once_with(update_fields=["last_used_at"])


@pytest.mark.asyncio
async def test_authenticate_api_key_rejects_missing_or_revoked_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = KeyQuery([])
    monkeypatch.setattr(deps.APIKey, "filter", lambda **kwargs: query)

    with pytest.raises(BusinessError) as error:
        await deps._authenticate_api_key("clou_missing")

    assert error.value.code == ResponseCode.INVALID_TOKEN
    assert error.value.msg_key == "invalid_api_key"
    assert query.related == ("user", "user__roles__permissions", "agents")


@pytest.mark.asyncio
async def test_authenticate_api_key_rejects_expired_key_without_persisting_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    key = SimpleNamespace(
        key_hash="hash",
        expires_at=now - timedelta(seconds=1),
        user=SimpleNamespace(is_active=True),
        save=AsyncMock(),
    )
    monkeypatch.setattr(deps.APIKey, "filter", lambda **kwargs: KeyQuery([key]))
    monkeypatch.setattr(deps.APIKey, "verify_key", lambda plain, hashed: True)
    monkeypatch.setattr(deps, "now_utc", lambda: now)

    with pytest.raises(BusinessError) as error:
        await deps._authenticate_api_key("clou_expired")

    assert error.value.code == ResponseCode.TOKEN_EXPIRED
    assert error.value.msg_key == "api_key_expired"
    key.save.assert_not_awaited()


def test_api_key_generation_keeps_secret_out_of_stored_hash() -> None:
    full_key, key_prefix, key_hash = APIKey.generate_key()

    assert full_key.startswith("clou_")
    assert key_prefix == full_key[:12]
    assert key_hash != full_key
    assert APIKey.verify_key(full_key, key_hash)
    assert not APIKey.verify_key(f"{full_key}x", key_hash)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("checker", "relation", "target"),
    [
        (deps.check_api_key_agent_access, "agents", uuid4()),
        (deps.check_api_key_workflow_access, "workflows", uuid4()),
    ],
)
async def test_api_key_resource_access_allows_unscoped_keys_and_denies_other_resources(
    checker,
    relation: str,
    target,
) -> None:
    unrestricted = SimpleNamespace(
        **{relation: SimpleNamespace(all=AsyncMock(return_value=[]))}
    )
    await checker(None, target)
    await checker(unrestricted, target)
    unrestricted.__getattribute__(relation).all.assert_awaited_once()

    restricted = SimpleNamespace(
        **{
            relation: SimpleNamespace(
                all=AsyncMock(return_value=[SimpleNamespace(id=uuid4())])
            )
        }
    )
    with pytest.raises(BusinessError) as error:
        await checker(restricted, target)

    assert error.value.code == ResponseCode.PERMISSION_DENIED
    assert error.value.status_code == 403
