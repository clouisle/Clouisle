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

## Related docs

- `./api-conventions.md`
- `../api/BACKEND_API.md`
