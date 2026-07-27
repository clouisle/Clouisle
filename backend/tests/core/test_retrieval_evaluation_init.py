from unittest.mock import AsyncMock, patch

import pytest
from tortoise import Tortoise
from tortoise.utils import get_schema_sql

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


@pytest.mark.anyio
async def test_postgres_schema_generation_has_no_cyclic_foreign_keys():
    await Tortoise.init(
        db_url="postgres://postgres:password@localhost:5432/clouisle",
        modules={"models": ["app.models"]},
    )
    try:
        schema = get_schema_sql(Tortoise.get_connection("default"), safe=True)
    finally:
        await Tortoise.close_connections()

    assert "evaluation_sweeps" in schema
    assert "evaluation_runs" in schema
