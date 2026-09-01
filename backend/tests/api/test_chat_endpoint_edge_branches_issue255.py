from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat as chat_endpoint
from app.schemas.agent import ChatRequest
from app.schemas.response import BusinessError, ResponseCode


@pytest.mark.anyio
async def test_inactive_user_short_circuits_before_api_key_access(monkeypatch):
    api_key_check = AsyncMock()
    monkeypatch.setattr(chat_endpoint.deps, "check_api_key_agent_access", api_key_check)
    inactive = SimpleNamespace(is_active=False)

    with pytest.raises(BusinessError) as exc:
        await chat_endpoint.chat(
            uuid4(), ChatRequest(message="hello"), (inactive, None)
        )

    assert exc.value.code == ResponseCode.INACTIVE_USER
    assert api_key_check.await_count == 0
