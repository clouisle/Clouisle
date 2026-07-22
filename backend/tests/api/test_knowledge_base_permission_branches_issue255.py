from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.api.v1.endpoints import knowledge_bases


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("dependency", "action"),
    [
        (knowledge_bases.require_kb_read, "read"),
        (knowledge_bases.require_kb_create, "create"),
        (knowledge_bases.require_kb_update, "update"),
        (knowledge_bases.require_kb_delete, "delete"),
    ],
)
@pytest.mark.parametrize("admin", [False, True])
async def test_kb_dependencies_only_enforce_actions_on_admin_routes(
    monkeypatch, dependency, action, admin
):
    require_action = Mock()
    monkeypatch.setattr(knowledge_bases, "_require_kb_action", require_action)
    prefix = "/api/v1/admin" if admin else "/api/v1"
    request = SimpleNamespace(url=SimpleNamespace(path=f"{prefix}/knowledge-bases"))
    user = SimpleNamespace()

    assert await dependency(request, user) is user

    if admin:
        require_action.assert_called_once_with(user, action)
    else:
        require_action.assert_not_called()
