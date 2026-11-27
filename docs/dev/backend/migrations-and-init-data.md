# Backend Migrations and Init Data

This project does not use Alembic or Aerich. Schema adjustments are applied through startup-time migration helpers in `app/core/init_data.py`.

## When to add a migration helper

Add an init-data migration when you:
- add a new database field
- change a field that requires schema adjustment
- need one-time bootstrap data during backend startup

## Required implementation

### 1. Add a migration function in `app/core/init_data.py`

Use the pattern below:

```python
async def init_<feature_name>():
    """Add <field_name> field to <table_name> table."""
    logger.info("Initializing <feature_name>...")

    conn = Tortoise.get_connection("default")

    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = '<table_name>' AND table_schema = 'public'
    """)

    if not tables:
        logger.info("<table_name> table does not exist yet, skipping migration")
        return

    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = '<table_name>' AND column_name = '<field_name>'
    """)

    if rows:
        logger.info("<field_name> field already exists, skipping")
        return

    logger.info("Adding <field_name> field to <table_name> table...")

    await conn.execute_query("""
        ALTER TABLE <table_name>
        ADD COLUMN IF NOT EXISTS <field_name> <TYPE> NOT NULL DEFAULT <default_value>
    """)

    logger.info("<field_name> field added successfully")
```

### 2. Call it during app startup in `app/main.py`

Import the migration helper in the lifespan import block and execute it before `await Tortoise.generate_schemas()`.

```python
from app.core.init_data import (
    ...,
    init_<feature_name>,
)

try:
    await init_<feature_name>()
except Exception as e:
    logger.warning(f"<Feature> migration failed: {e}")
```

## Rules

- Always check table existence before altering it.
- Always check whether the target column already exists.
- Make startup migrations idempotent.
- Keep migrations focused on the exact schema/bootstrap change being introduced.
- When a model change needs database support, do not rely on `generate_schemas()` alone.

## Agent and Workflow history isolation

Deploy this change with a **coordinated cutover**: stop the old API and task workers before starting the new version. Old processes can write conversations and runs without their credential binding; do not run mixed versions during the cutover or roll back to an old binary while relying on these access boundaries.

The startup migration records API key UUIDs on Agent conversations and Workflow runs. The UUID is not a foreign key: deleting or rotating a key must not make old records visible in personal history or transferable to a new key.

Records written before these columns existed become **the owner's own history**: `api_key_id` stays `NULL`, so they are served exactly like a web-login record and appear in the owner's personal history. A historical API call is deliberately **not** reconstructed as a separate origin — the migration does not guess which key created an old conversation or run, and it never splits or deletes a record. Only records written from now on carry a credential, and those stay bound to that exact key (another key of the same owner, a browser session, or another user cannot read, continue or replay them).

The `api_key_origin_unknown` column is added by the same statement because the access filters read it, but this migration never sets it. It stays in place so a database that already ran the earlier, evidence-based classification keeps those rows out of personal history; no new quarantine state is produced.

The backfill (now removed) used to classify rows once; the current migration only adds columns, so a record written by an old binary after the migration stays `api_key_id = NULL` and is served as the owner's own history. That is the intended outcome, not a leak: a historical API call is treated as ordinary user history. The coordinated cutover is still required because an old process also cannot write the key binding that *new* key-created records need.

## Related docs

- `./api-conventions.md`
- `../api/BACKEND_API.md`
