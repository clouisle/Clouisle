"""Upgrade existing collection tables after schema creation, before API serving."""

from tortoise import Tortoise

from app.core.init_data import execute_startup_migration_query


async def migrate_wechat_knowledge_schema() -> None:
    connection = Tortoise.get_connection("default")
    await migrate_wechat_connection_configuration()
    await migrate_wechat_purpose()
    if connection.capabilities.dialect == "sqlite":
        columns = await connection.execute_query_dict(
            'PRAGMA table_info("wechat_knowledge_bindings")'
        )
        if columns and not any(
            column["name"] == "disconnected_at" for column in columns
        ):
            await connection.execute_query(
                'ALTER TABLE "wechat_knowledge_bindings" ADD COLUMN "disconnected_at" TIMESTAMP NULL'
            )
        await connection.execute_query(
            "UPDATE documents SET doc_type = 'markdown' WHERE doc_type = 'md'"
        )
        await restore_wechat_document_sources()
        return
    # ADD COLUMN IF NOT EXISTS is safe for concurrent API worker startup. A
    # failed upgrade must propagate: serving a partial schema causes HTTP 500s.
    await execute_startup_migration_query(
        connection,
        'ALTER TABLE IF EXISTS "wechat_knowledge_bindings" '
        'ADD COLUMN IF NOT EXISTS "disconnected_at" TIMESTAMPTZ NULL',
    )
    await execute_startup_migration_query(
        connection,
        "UPDATE documents SET doc_type = 'markdown' WHERE doc_type = 'md'",
    )
    await restore_wechat_document_sources()


async def migrate_wechat_purpose() -> None:
    """Existing configured collectors remain active; unused connections stay idle."""
    from tortoise.transactions import in_transaction

    async with in_transaction() as db:
        if db.capabilities.dialect == "sqlite":
            columns = await db.execute_query_dict(
                'PRAGMA table_info("wechat_knowledge_bindings")'
            )
            if not any(row["name"] == "purpose" for row in columns):
                await db.execute_query(
                    "ALTER TABLE wechat_knowledge_bindings ADD COLUMN purpose VARCHAR(24) NOT NULL DEFAULT 'none'"
                )
                await db.execute_query(
                    "UPDATE wechat_knowledge_bindings SET purpose='knowledge_collection' WHERE id IN (SELECT binding_id FROM wechat_knowledge_collections)"
                )
        else:
            await db.execute_query("SET LOCAL lock_timeout='2s'")
            await db.execute_query(
                "SELECT pg_advisory_xact_lock(hashtext('wechat-purpose'))"
            )
            columns = await db.execute_query_dict(
                "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='wechat_knowledge_bindings' AND column_name='purpose'"
            )
            if not columns:
                await db.execute_query(
                    "ALTER TABLE wechat_knowledge_bindings ADD COLUMN purpose VARCHAR(24) NOT NULL DEFAULT 'none'"
                )
                await db.execute_query(
                    "UPDATE wechat_knowledge_bindings SET purpose='knowledge_collection' WHERE id IN (SELECT binding_id FROM wechat_knowledge_collections)"
                )


async def migrate_wechat_connection_configuration() -> None:
    """Move legacy targets once, then remove the coupling columns."""
    connection = Tortoise.get_connection("default")
    sqlite = connection.capabilities.dialect == "sqlite"
    if sqlite:
        await connection.execute_query("PRAGMA foreign_keys = OFF")
    try:
        await _migrate_wechat_connection_configuration()
    finally:
        if sqlite:
            await connection.execute_query("PRAGMA foreign_keys = ON")


async def _migrate_wechat_connection_configuration() -> None:
    from tortoise.transactions import in_transaction

    async with in_transaction() as db:
        sqlite = db.capabilities.dialect == "sqlite"
        if not sqlite:
            await db.execute_query("SET LOCAL lock_timeout = '2s'")
            await db.execute_query(
                "SELECT pg_advisory_xact_lock(hashtext('wechat-connection-configuration'))"
            )

        async def columns(table):
            if sqlite:
                rows = await db.execute_query_dict(f'PRAGMA table_info("{table}")')
                return {row["name"] for row in rows}
            rows = await db.execute_query_dict(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = $1",
                [table],
            )
            return {row["column_name"] for row in rows}

        binding_columns = await columns("wechat_knowledge_bindings")
        if "knowledge_base_id" in binding_columns:
            await db.execute_query(
                "INSERT INTO wechat_knowledge_collections "
                "(id, binding_id, knowledge_base_id, vision_model_id, stt_model_id, created_at, updated_at) "
                "SELECT id, id, knowledge_base_id, vision_model_id, stt_model_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
                "FROM wechat_knowledge_bindings WHERE knowledge_base_id IS NOT NULL "
                "ON CONFLICT (binding_id) DO NOTHING"
            )
            if sqlite:
                # Rebuild below removes inline legacy foreign-key declarations too.
                await _rebuild_sqlite_connection_table(db, "wechat_knowledge_bindings")
            else:
                for column in ("knowledge_base_id", "vision_model_id", "stt_model_id"):
                    await db.execute_query(
                        f'ALTER TABLE wechat_knowledge_bindings DROP COLUMN IF EXISTS "{column}"'
                    )
        if "knowledge_base_id" in await columns("wechat_knowledge_logins"):
            if sqlite:
                await _rebuild_sqlite_connection_table(db, "wechat_knowledge_logins")
            else:
                for column in ("knowledge_base_id", "vision_model_id", "stt_model_id"):
                    await db.execute_query(
                        f'ALTER TABLE wechat_knowledge_logins DROP COLUMN IF EXISTS "{column}"'
                    )


async def _rebuild_sqlite_connection_table(db, table: str) -> None:
    """SQLite cannot drop a column referenced by an inline FK constraint."""
    from app.models.wechat_knowledge import WeChatKnowledgeBinding, WeChatKnowledgeLogin

    model = (
        WeChatKnowledgeBinding
        if table == "wechat_knowledge_bindings"
        else WeChatKnowledgeLogin
    )
    # Use the ORM's schema declaration so SQLite retains all current constraints.
    generator = db.schema_generator(db)
    ddl = generator._get_table_sql(model, safe=False)["table_creation_string"]
    temporary = table + "_decoupled"
    ddl = ddl.replace(f'CREATE TABLE "{table}"', f'CREATE TABLE "{temporary}"', 1)
    await db.execute_query(ddl)
    names = list(model._meta.fields_db_projection.values())
    available = {
        row["name"]
        for row in await db.execute_query_dict(f'PRAGMA table_info("{table}")')
    }
    names = [name for name in names if name in available]
    selected = ", ".join(f'"{name}"' for name in names)
    await db.execute_query(
        f'INSERT INTO "{temporary}" ({selected}) SELECT {selected} FROM "{table}"'
    )
    if table == "wechat_knowledge_bindings" and "purpose" not in available:
        await db.execute_query(
            f"UPDATE \"{temporary}\" SET purpose='knowledge_collection' WHERE id IN (SELECT binding_id FROM wechat_knowledge_collections)"
        )
    await db.execute_query(f'DROP TABLE "{table}"')
    await db.execute_query(f'ALTER TABLE "{temporary}" RENAME TO "{table}"')


async def restore_wechat_document_sources() -> None:
    from app.models.knowledge_base import Document
    from app.services.wechat_ingestion import document_source_fields

    async for document in Document.filter(doc_type__in=["markdown", "md"]):
        metadata = document.metadata or {}
        if metadata.get("source") != "wechat":
            continue
        fields = await document_source_fields(
            document.name, metadata, document.file_path
        )
        if fields["doc_type"] == "markdown":
            continue
        if fields["doc_type"] == "url":
            fields["name"] = str(
                metadata.get("title") or document.name.removesuffix(".md")
            )[:255]
        for key, value in fields.items():
            setattr(document, key, value)
        await document.save(update_fields=list(fields))
