from unittest.mock import AsyncMock, patch

import pytest

from app.core import init_data
from app.core.permissions import SystemPermissions


@pytest.mark.anyio
async def test_evaluation_migration_is_idempotent_and_preserves_results():
    connection = object()
    execute = AsyncMock()
    with (
        patch.object(init_data.Tortoise, "get_connection", return_value=connection),
        patch.object(init_data, "execute_startup_migration_query", execute),
    ):
        await init_data.init_retrieval_evaluation_tables()

    sql = "\n".join(call.args[1] for call in execute.await_args_list)
    assert "CREATE TABLE IF NOT EXISTS evaluation_case_results" in sql
    assert "case_snapshot" in sql
    assert "ON DELETE SET NULL" in sql
    assert "UPDATE evaluation_case_results" in sql


def test_evaluation_permissions_are_registered():
    codes = {item["code"] for item in SystemPermissions.get_all_definitions()}
    assert {"kb:evaluate", "admin:knowledge-base:evaluate"} <= codes
