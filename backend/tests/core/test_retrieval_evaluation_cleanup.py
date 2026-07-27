from unittest.mock import AsyncMock, patch

import pytest
from tortoise import Tortoise
from tortoise.utils import get_schema_sql

from app.core import init_data


@pytest.mark.anyio
async def test_evaluation_cleanup_is_narrow_and_idempotent():
    connection = object()
    execute = AsyncMock()
    with (
        patch.object(init_data.Tortoise, "get_connection", return_value=connection),
        patch.object(init_data, "execute_startup_migration_query", execute),
    ):
        await init_data.drop_obsolete_retrieval_evaluation_tables()
        await init_data.drop_obsolete_retrieval_evaluation_tables()

    assert execute.await_count == 2
    sql = execute.await_args.args[1]
    assert "ALTER TABLE IF EXISTS evaluation_runs" in sql
    assert "ALTER TABLE IF EXISTS evaluation_sweeps" in sql
    assert "DROP COLUMN IF EXISTS sweep_id" in sql
    assert "DROP COLUMN IF EXISTS best_run_id" in sql
    assert "DROP COLUMN IF EXISTS verification_run_id" in sql
    assert sql.index("DROP TABLE IF EXISTS evaluation_case_results") < sql.index(
        "DROP TABLE IF EXISTS evaluation_sweeps"
    )
    assert sql.index("DROP TABLE IF EXISTS evaluation_sweeps") < sql.index(
        "DROP TABLE IF EXISTS evaluation_runs"
    )
    assert sql.index("DROP TABLE IF EXISTS evaluation_runs") < sql.index(
        "DROP TABLE IF EXISTS evaluation_cases"
    )
    assert sql.index("DROP TABLE IF EXISTS evaluation_cases") < sql.index(
        "DROP TABLE IF EXISTS evaluation_datasets"
    )
    assert "CASCADE" not in sql
    assert "knowledge_bases" not in sql
    assert "users" not in sql


@pytest.mark.anyio
async def test_postgres_schema_generation_excludes_evaluation_tables():
    await Tortoise.init(
        db_url="postgres://postgres:password@localhost:5432/clouisle",
        modules={"models": ["app.models"]},
    )
    try:
        schema = get_schema_sql(Tortoise.get_connection("default"), safe=True)
    finally:
        await Tortoise.close_connections()

    assert "evaluation_datasets" not in schema
    assert "evaluation_cases" not in schema
    assert "evaluation_runs" not in schema
    assert "evaluation_case_results" not in schema
    assert "evaluation_sweeps" not in schema
