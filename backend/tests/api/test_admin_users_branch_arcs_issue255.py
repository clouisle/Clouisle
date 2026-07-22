from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import users


class Query:
    def __init__(self):
        self.calls = []

    def filter(self, *args, **kwargs):
        self.calls.append(("filter", args, kwargs))
        return self

    def distinct(self):
        self.calls.append(("distinct", (), {}))
        return self

    def exclude(self, *args, **kwargs):
        self.calls.append(("exclude", args, kwargs))
        return self

    async def count(self):
        return 0

    def offset(self, value):
        self.calls.append(("offset", (value,), {}))
        return self

    def limit(self, value):
        self.calls.append(("limit", (value,), {}))
        return self

    def prefetch_related(self, *args):
        self.calls.append(("prefetch_related", args, {}))
        return self

    def __await__(self):
        async def resolve():
            return []

        return resolve().__await__()


@pytest.mark.parametrize(
    ("status", "search", "role", "excluded", "expected_operations"),
    [
        (None, None, None, None, []),
        (["unknown"], None, None, None, []),
        (
            ["active", "inactive", "pending"],
            "alice",
            ["admin"],
            [uuid4()],
            ["filter", "filter", "filter", "distinct", "exclude"],
        ),
    ],
)
@pytest.mark.asyncio
async def test_read_users_filter_branch_matrix_issue255(
    monkeypatch,
    status,
    search,
    role,
    excluded,
    expected_operations,
):
    query = Query()
    user_model = Mock()
    user_model.all.return_value = query
    monkeypatch.setattr(users, "User", user_model)

    response = await users.read_users(
        page=1,
        page_size=20,
        status=status,
        search=search,
        role=role,
        exclude_user_id=excluded,
        current_user=Mock(),
    )

    operations = [name for name, _, _ in query.calls]
    assert operations[: len(expected_operations)] == expected_operations
    assert operations[-3:] == ["offset", "limit", "prefetch_related"]
    assert response["data"]["total"] == 0
