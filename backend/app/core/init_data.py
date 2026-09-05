import asyncio
import logging
from typing import Any

from tortoise import Tortoise

from app.models.user import Role, Permission, TeamMember
from app.models.site_setting import init_default_settings
from app.core.permissions import SystemPermissions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# System role name constant
SUPER_ADMIN_ROLE = "Super Admin"
STARTUP_MIGRATION_LOCK_TIMEOUT = "2s"
STARTUP_MIGRATION_QUERY_TIMEOUT_SECONDS = 3


async def init_model_endpoint_allowlist() -> None:
    """Seed the endpoint allowlist once from defaults and existing models."""
    from app.core.model_endpoint_policy import (
        DEFAULT_MODEL_ENDPOINT_ALLOWLIST,
        MODEL_ENDPOINT_ALLOWLIST_MAX_ENTRIES,
        MODEL_ENDPOINT_ALLOWLIST_SETTING,
        ModelEndpointPolicyError,
        normalize_model_endpoint_origin,
    )
    from app.models.model import Model
    from app.models.site_setting import SiteSetting

    existing = await SiteSetting.filter(key=MODEL_ENDPOINT_ALLOWLIST_SETTING).first()
    if existing:
        return

    allowlist = list(DEFAULT_MODEL_ENDPOINT_ALLOWLIST)
    seen = set(allowlist)
    model_origins: set[str] = set()
    for model in await Model.all():
        base_url = model.get_effective_base_url()
        if not base_url:
            continue
        try:
            origin = normalize_model_endpoint_origin(base_url)
        except ModelEndpointPolicyError:
            logger.warning(
                "Skipping invalid existing model Base URL while seeding allowlist: model=%s",
                model.id,
            )
            continue
        if origin not in seen:
            model_origins.add(origin)

    remaining_slots = max(MODEL_ENDPOINT_ALLOWLIST_MAX_ENTRIES - len(allowlist), 0)
    allowlist.extend(sorted(model_origins)[:remaining_slots])

    await SiteSetting.set_value(
        key=MODEL_ENDPOINT_ALLOWLIST_SETTING,
        value=allowlist,
        value_type="json",
        category="security",
        description="model_endpoint_allowlist_description",
        is_public=False,
    )


async def execute_startup_migration_query(conn, query: str):
    await conn.execute_query(f"SET lock_timeout = '{STARTUP_MIGRATION_LOCK_TIMEOUT}'")
    try:
        return await asyncio.wait_for(
            conn.execute_query(query), timeout=STARTUP_MIGRATION_QUERY_TIMEOUT_SECONDS
        )
    finally:
        await conn.execute_query("RESET lock_timeout")


async def _execute_ddl(conn: Any, query: str) -> None:
    """Execute DDL script, using execute_script on real PostgreSQL/asyncpg connections

    to support multiple commands without prepared-statement errors, while falling
    back to execute_query when execute_script is not available or for mocked connections.
    """
    if hasattr(conn, "execute_script"):
        dialect = getattr(getattr(conn, "capabilities", None), "dialect", "")
        if dialect != "sqlite":
            await conn.execute_script(query)
            return
    await conn.execute_query(query)


async def init_postgres_lexical_search() -> None:
    """Create and validate pg_search objects on first startup."""
    conn = Tortoise.get_connection("default")
    preload_rows = await conn.execute_query_dict(
        "SELECT current_setting('shared_preload_libraries') AS libraries"
    )
    preloaded = {
        value.strip() for value in str(preload_rows[0]["libraries"]).split(",")
    }
    required = {"pg_search", "pg_stat_statements"}
    missing = sorted(required - preloaded)
    if missing:
        raise RuntimeError(
            "PostgreSQL is missing required shared preload libraries: "
            + ", ".join(missing)
        )

    await conn.execute_query("CREATE EXTENSION IF NOT EXISTS pg_search CASCADE")
    version_rows = await conn.execute_query_dict(
        "SELECT extversion FROM pg_extension WHERE extname = 'pg_search'"
    )
    if not version_rows or version_rows[0]["extversion"] != "0.24.3":
        installed = version_rows[0]["extversion"] if version_rows else "missing"
        raise RuntimeError(
            f"pg_search 0.24.3 is required; installed version is {installed}"
        )

    await execute_startup_migration_query(
        conn,
        """
        ALTER TABLE document_chunks
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ
        """,
    )
    await execute_startup_migration_query(
        conn,
        """
        UPDATE document_chunks
        SET updated_at = created_at
        WHERE updated_at IS NULL
        """,
    )
    await execute_startup_migration_query(
        conn,
        """
        ALTER TABLE document_chunks
            ALTER COLUMN updated_at SET DEFAULT NOW(),
            ALTER COLUMN updated_at SET NOT NULL
        """,
    )
    await conn.execute_query("""
        CREATE TABLE IF NOT EXISTS knowledge_lexical_chunks (
            chunk_id UUID PRIMARY KEY REFERENCES document_chunks(id) ON DELETE CASCADE,
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            kb_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            chunk_index INTEGER NOT NULL,
            update_version BIGINT NOT NULL,
            language TEXT,
            section TEXT,
            title TEXT NOT NULL,
            identifiers TEXT[] NOT NULL DEFAULT ARRAY[]::text[]
        )
    """)
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS knowledge_lexical_chunks_bm25_idx
        ON knowledge_lexical_chunks
        USING bm25 (
            chunk_id, team_id, kb_id, document_id, status,
            (content::pdb.jieba), (title::pdb.jieba), (name::pdb.jieba),
            (section::pdb.jieba), identifiers, chunk_index, update_version
        )
        WITH (key_field = 'chunk_id')
    """)
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS knowledge_lexical_chunks_team_kb_idx
        ON knowledge_lexical_chunks (team_id, kb_id)
    """)
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS knowledge_lexical_chunks_team_document_idx
        ON knowledge_lexical_chunks (team_id, document_id)
    """)


async def sync_role_permissions(
    role: Role, target_permissions: list[str], role_name: str
):
    target_permission_set = set(target_permissions)

    for perm_code in target_permissions:
        perm = await Permission.filter(code=perm_code).first()
        if not perm:
            logger.warning(
                f"Permission {perm_code} not found while syncing {role_name} role"
            )
            continue

        existing = await role.permissions.filter(id=perm.id).exists()
        if not existing:
            await role.permissions.add(perm)
            logger.info(f"Added permission {perm_code} to {role_name} role")

    current_permissions = await role.permissions.all()
    for permission in current_permissions:
        if permission.code not in target_permission_set:
            await role.permissions.remove(permission)
            logger.info(f"Removed permission {permission.code} from {role_name} role")


async def migrate_auto_notification_types():
    """Merge newly introduced auto notification types into persisted configs.

    init_default_settings only writes defaults when the key is absent, so an
    existing deployment keeps its persisted enabled_types and never sees new
    types (e.g. workflow.pause_pending). Merge them in explicitly, preserving
    the admin's current choices.
    """
    from app.models.site_setting import SiteSetting

    current = await SiteSetting.get_value("auto_notification_config", None)
    if not isinstance(current, dict):
        return
    enabled = current.get("enabled_types")
    if not isinstance(enabled, list):
        return
    missing = [t for t in NEW_AUTO_NOTIFICATION_TYPES if t not in enabled]
    if not missing:
        return
    current["enabled_types"] = enabled + missing
    await SiteSetting.set_value(
        key="auto_notification_config",
        value=current,
        value_type="json",
        category="notification",
        description="Auto notification configuration",
        is_public=False,
    )
    logger.info("Migrated auto notification enabled_types: %s", missing)


NEW_AUTO_NOTIFICATION_TYPES = [
    "workflow.pause_pending",
]


async def init_workflow_tables():
    """
    Initialize workflow-related tables if they don't exist.
    This handles the migration for the new workflow feature.
    """
    logger.info("Initializing workflow tables...")

    conn = Tortoise.get_connection("default")

    # Check if workflows table exists
    _, rows = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'workflows'
    """)

    if rows:
        logger.info("Workflow tables already exist, skipping creation")
        return

    logger.info("Creating workflow tables...")

    # Create workflows table
    await conn.execute_query("""
        CREATE TABLE IF NOT EXISTS workflows (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            icon VARCHAR(50),
            definition JSONB NOT NULL DEFAULT '{"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}}',
            variables JSONB NOT NULL DEFAULT '[]',
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            version INT NOT NULL DEFAULT 1,
            trigger_type VARCHAR(20) NOT NULL DEFAULT 'manual',
            trigger_config JSONB NOT NULL DEFAULT '{}',
            webhook_token VARCHAR(64),
            run_count INT NOT NULL DEFAULT 0,
            success_count INT NOT NULL DEFAULT 0,
            fail_count INT NOT NULL DEFAULT 0,
            created_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    logger.info("Created workflows table")

    # Create workflow_runs table
    await conn.execute_query("""
        CREATE TABLE IF NOT EXISTS workflow_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workflow_id UUID REFERENCES workflows(id) ON DELETE SET NULL,
            trigger_type VARCHAR(20) NOT NULL DEFAULT 'manual',
            triggered_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            is_debug BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            inputs JSONB NOT NULL DEFAULT '{}',
            outputs JSONB,
            parent_run_id UUID REFERENCES workflow_runs(id) ON DELETE CASCADE,
            root_run_id UUID REFERENCES workflow_runs(id) ON DELETE CASCADE,
            depth INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            total_nodes INT NOT NULL DEFAULT 0,
            executed_nodes INT NOT NULL DEFAULT 0,
            failed_nodes INT NOT NULL DEFAULT 0,
            skipped_nodes INT NOT NULL DEFAULT 0,
            total_duration_ms INT,
            total_token_usage JSONB NOT NULL DEFAULT '{}',
            error_message TEXT,
            error_node_id VARCHAR(100)
        )
    """)
    logger.info("Created workflow_runs table")

    # Create node_executions table
    await conn.execute_query("""
        CREATE TABLE IF NOT EXISTS node_executions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
            node_id VARCHAR(100) NOT NULL,
            node_type VARCHAR(50) NOT NULL,
            node_name VARCHAR(100) NOT NULL,
            execution_order INT NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            queued_at TIMESTAMPTZ,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            queue_duration_ms INT,
            execution_duration_ms INT,
            inputs JSONB,
            inputs_storage_key VARCHAR(255),
            outputs JSONB,
            outputs_storage_key VARCHAR(255),
            config_snapshot JSONB,
            model_used VARCHAR(100),
            prompt_tokens INT,
            completion_tokens INT,
            total_tokens INT,
            sub_run_id UUID REFERENCES workflow_runs(id) ON DELETE SET NULL,
            error_message TEXT,
            error_type VARCHAR(100),
            retry_count INT NOT NULL DEFAULT 0
        )
    """)
    logger.info("Created node_executions table")

    # Create indexes for better query performance
    await _execute_ddl(
        conn,
        """
        CREATE INDEX IF NOT EXISTS idx_workflows_team_id ON workflows(team_id);
        CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status);
        CREATE INDEX IF NOT EXISTS idx_workflows_created_by ON workflows(created_by_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow_id ON workflow_runs(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status);
        CREATE INDEX IF NOT EXISTS idx_workflow_runs_parent_run_id ON workflow_runs(parent_run_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_runs_root_run_id ON workflow_runs(root_run_id);
        CREATE INDEX IF NOT EXISTS idx_node_executions_run_id ON node_executions(run_id);
        CREATE INDEX IF NOT EXISTS idx_node_executions_node_id ON node_executions(node_id);
        CREATE INDEX IF NOT EXISTS idx_node_executions_status ON node_executions(status);
    """,
    )
    logger.info("Created workflow indexes")

    logger.info("Workflow tables initialization complete")


async def init_workflow_pause_requests_table():
    """Create the workflow_pause_requests table if it does not exist."""
    logger.info("Initializing workflow pause requests table...")
    conn = Tortoise.get_connection("default")
    dialect = getattr(getattr(conn, "capabilities", None), "dialect", "")
    if dialect != "postgres":
        # The DDL below (JSONB, gen_random_uuid, TIMESTAMPTZ) is Postgres-only.
        # Workflow tables themselves are Postgres-only (init_workflow_tables
        # fails first on other backends), so this is defensive.
        logger.info(
            "Skipping workflow pause requests table for non-PostgreSQL database"
        )
        return
    # Existing workflow tables predate WorkflowRun.context_snapshot. Pause
    # resume pins the first-pass definition here, so older installations must
    # gain the column before a pause request can be created. On a fresh
    # database the tables do not exist yet (generate_schemas creates them),
    # so the ALTERs are best-effort and must not block the CREATE below.
    try:
        await conn.execute_query(
            """
            ALTER TABLE workflow_runs
            ADD COLUMN IF NOT EXISTS context_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb
            """
        )
    except Exception:
        logger.debug("workflow_runs not ready yet; generate_schemas will create it")

    await conn.execute_query(
        """
        CREATE TABLE IF NOT EXISTS workflow_pause_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
            node_execution_id UUID REFERENCES workflow_node_executions(id) ON DELETE CASCADE,
            workflow_id UUID REFERENCES workflows(id) ON DELETE SET NULL,
            node_id VARCHAR(100) NOT NULL,
            node_name VARCHAR(200) NOT NULL DEFAULT '',
            mode VARCHAR(20) NOT NULL DEFAULT 'variables',
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            values JSONB,
            comment TEXT,
            description TEXT,
            approvals JSONB,
            submitted_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            submitted_at TIMESTAMPTZ
        )
        """
    )
    # Older deployments already have the table without the description column;
    # add it now so the model and schema match before generate_schemas.
    try:
        await conn.execute_query(
            """
            ALTER TABLE workflow_pause_requests
            ADD COLUMN IF NOT EXISTS description TEXT
            """
        )
    except Exception:
        logger.debug(
            "workflow_pause_requests not ready yet; generate_schemas will create it"
        )
    try:
        await conn.execute_query(
            """
            ALTER TABLE workflow_pause_requests
            ADD COLUMN IF NOT EXISTS approvals JSONB
            """
        )
    except Exception:
        logger.debug(
            "workflow_pause_requests not ready yet; generate_schemas will create it"
        )
    await conn.execute_query(
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_pause_requests_run_id
        ON workflow_pause_requests(run_id)
        """
    )
    await conn.execute_query(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_workflow_pause_requests_run_node
        ON workflow_pause_requests(run_id, node_id)
        """
    )
    logger.info("Workflow pause requests table ready")


async def init_observability_indexes():
    """Create time-range indexes for raw observability queries."""
    conn = Tortoise.get_connection("default")
    dialect = getattr(getattr(conn, "capabilities", None), "dialect", "")
    if dialect != "postgres":
        logger.info("Skipping observability indexes for non-PostgreSQL database")
        return

    indexes = (
        (
            "idx_messages_observability_created_at_btree",
            "idx_messages_observability_created_at",
            """
            CREATE INDEX IF NOT EXISTS idx_messages_observability_created_at_btree
            ON messages (created_at)
            WHERE round_role = 'assistant_final' AND is_round_canonical = TRUE
            """,
        ),
        (
            "idx_workflow_runs_observability_created_at_btree",
            "idx_workflow_runs_observability_created_at",
            """
            CREATE INDEX IF NOT EXISTS idx_workflow_runs_observability_created_at_btree
            ON workflow_runs (created_at)
            """,
        ),
    )
    for index_name, legacy_index_name, query in indexes:
        try:
            await conn.execute_query(f"DROP INDEX IF EXISTS {legacy_index_name}")
        except Exception as exc:
            logger.warning(
                "Could not remove legacy observability index %s: %s",
                legacy_index_name,
                exc,
            )
        try:
            await conn.execute_query(query)
        except Exception as exc:
            logger.warning(
                "Could not create observability index %s: %s", index_name, exc
            )
        else:
            logger.info("Created observability index %s", index_name)


async def init_scoped_role_assignments_table():
    """Create and backfill team-scoped role assignments."""
    logger.info("Initializing scoped role assignments table...")
    conn = Tortoise.get_connection("default")

    await execute_startup_migration_query(
        conn,
        """
        CREATE TABLE IF NOT EXISTS scoped_role_assignments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            scope_type VARCHAR(20) NOT NULL,
            scope_id UUID NOT NULL,
            source VARCHAR(20) NOT NULL DEFAULT 'manual',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT scoped_role_assignments_unique UNIQUE (user_id, role_id, scope_type, scope_id)
        )
        """,
    )
    await execute_startup_migration_query(
        conn,
        """
        CREATE INDEX IF NOT EXISTS idx_scoped_role_assignments_user_scope
        ON scoped_role_assignments(user_id, scope_type, scope_id)
        """,
    )
    await execute_startup_migration_query(
        conn,
        """
        CREATE INDEX IF NOT EXISTS idx_scoped_role_assignments_role_scope
        ON scoped_role_assignments(role_id, scope_type, scope_id)
        """,
    )

    role_by_team_role = {
        "owner": await Role.filter(name="Admin").first(),
        "admin": await Role.filter(name="Admin").first(),
        "member": await Role.filter(name="Member").first(),
        "viewer": await Role.filter(name="Viewer").first(),
    }
    created = 0
    skipped = 0
    memberships = await TeamMember.all().prefetch_related("team", "user")
    for membership in memberships:
        role = role_by_team_role.get(membership.role)
        if not role:
            skipped += 1
            continue
        await execute_startup_migration_query(
            conn,
            f"""
            INSERT INTO scoped_role_assignments (
                id, user_id, role_id, scope_type, scope_id, source, created_at, updated_at
            )
            VALUES (
                gen_random_uuid(), '{membership.user.id}', '{role.id}',
                'team', '{membership.team.id}', 'migration', NOW(), NOW()
            )
            ON CONFLICT (user_id, role_id, scope_type, scope_id) DO NOTHING
            """,
        )
        created += 1

    logger.info(
        "Scoped role assignments initialized: %s attempted, %s skipped",
        created,
        skipped,
    )


async def init_user_locale_field():
    """
    Add locale field to users table if it doesn't exist.
    This handles the migration for the user language preference feature.
    """
    logger.info("Checking user locale field...")

    conn = Tortoise.get_connection("default")

    # Check if users table exists first
    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'users' AND table_schema = 'public'
    """)

    if not tables:
        logger.info("Users table does not exist yet, skipping locale migration")
        return

    # Check if locale column exists
    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'locale'
    """)

    if not rows:
        logger.info("Adding locale column to users table...")
        try:
            await conn.execute_query("""
                ALTER TABLE users
                ADD COLUMN locale VARCHAR(10) DEFAULT 'en'
            """)
            logger.info("Added locale column to users table")
        except Exception as e:
            logger.error(f"Could not add locale column: {e}")
            raise
    else:
        logger.info("locale column already exists")

    logger.info("User locale migration complete")


async def init_agent_attachment_fields() -> None:
    """Replace legacy agent vision and file-upload fields with attachments."""
    logger.info("Initializing agent attachment fields...")
    conn = Tortoise.get_connection("default")

    _, tables = await conn.execute_query(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'agents' AND table_schema = 'public'
        """
    )
    if not tables:
        logger.info("Agents table does not exist yet, skipping attachment migration")
        return

    _, rows = await conn.execute_query(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'agents' AND table_schema = 'public'
        """
    )
    columns = {row["column_name"] for row in rows}

    if "enable_attachments" not in columns:
        await execute_startup_migration_query(
            conn,
            """
            ALTER TABLE agents
            ADD COLUMN enable_attachments BOOLEAN NOT NULL DEFAULT FALSE
            """,
        )

    if "attachment_config" not in columns:
        await execute_startup_migration_query(
            conn,
            """
            ALTER TABLE agents
            ADD COLUMN attachment_config JSONB NOT NULL DEFAULT '{}'::jsonb
            """,
        )

    if {"enable_vision", "enable_file_upload"} & columns:
        vision = (
            "COALESCE(enable_vision, FALSE)" if "enable_vision" in columns else "FALSE"
        )
        uploads = (
            "COALESCE(enable_file_upload, FALSE)"
            if "enable_file_upload" in columns
            else "FALSE"
        )
        await execute_startup_migration_query(
            conn,
            f"""
            UPDATE agents
            SET enable_attachments = {vision} OR {uploads}
            """,
        )

    if "file_upload_config" in columns:
        await execute_startup_migration_query(
            conn,
            """
            UPDATE agents
            SET attachment_config = COALESCE(file_upload_config, '{}'::jsonb) - 'parser'
            """,
        )

    await execute_startup_migration_query(
        conn,
        """
        UPDATE agents
        SET attachment_config = attachment_config - 'parser'
        WHERE attachment_config ? 'parser'
        """,
    )

    legacy_columns = [
        column
        for column in ("enable_vision", "enable_file_upload", "file_upload_config")
        if column in columns
    ]
    if legacy_columns:
        await execute_startup_migration_query(
            conn,
            f"ALTER TABLE agents DROP COLUMN {', DROP COLUMN '.join(legacy_columns)}",
        )

    logger.info("Agent attachment fields migration complete")


async def init_agent_tools_credentials():
    """
    Initialize tools_credentials field for existing agents.
    This handles the migration for the new tools_credentials feature.
    Must be called BEFORE Tortoise.generate_schemas() to avoid schema mismatch.
    """
    logger.info("Checking agent tools_credentials field...")

    conn = Tortoise.get_connection("default")

    # Check if agents table exists first
    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'agents' AND table_schema = 'public'
    """)

    if not tables:
        logger.info(
            "Agents table does not exist yet, skipping tools_credentials migration"
        )
        return

    # Check if tools_credentials column exists
    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'agents' AND column_name = 'tools_credentials'
    """)

    if not rows:
        logger.info("Adding tools_credentials column to agents table...")
        try:
            await execute_startup_migration_query(
                conn,
                """
                ALTER TABLE agents
                ADD COLUMN tools_credentials JSONB NOT NULL DEFAULT '{}'::jsonb
                """,
            )
            logger.info("Added tools_credentials column to agents table")
        except Exception as e:
            logger.error(f"Could not add tools_credentials column: {e}")
            raise
    else:
        logger.info("tools_credentials column already exists")

    # Update existing agents with NULL tools_credentials (shouldn't happen with DEFAULT, but just in case)
    try:
        _, rows = await execute_startup_migration_query(
            conn,
            """
            SELECT COUNT(*) AS null_count
            FROM agents
            WHERE tools_credentials IS NULL
            """,
        )
        null_count = rows[0]["null_count"] if rows else 0
        if null_count:
            await execute_startup_migration_query(
                conn,
                """
                UPDATE agents
                SET tools_credentials = '{}'::jsonb
                WHERE tools_credentials IS NULL
                """,
            )
            logger.info("Updated existing agents with default tools_credentials")
        else:
            logger.info("No agents require tools_credentials backfill")
    except Exception as e:
        logger.warning(f"Could not update existing agents: {e}")

    logger.info("Agent tools_credentials migration complete")


async def init_agent_powered_by_text():
    """
    Add powered_by_text column to existing agents tables.
    Handles the migration for the agent-level chat footer config feature.
    Must be called BEFORE Tortoise.generate_schemas() to avoid schema mismatch.
    """
    logger.info("Checking agent powered_by_text field...")

    conn = Tortoise.get_connection("default")
    dialect = getattr(getattr(conn, "capabilities", None), "dialect", "")
    is_sqlite = dialect == "sqlite" or "sqlite" in conn.__class__.__name__.lower()

    # Check if agents table exists first
    if is_sqlite:
        _, tables = await conn.execute_query(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'agents'
            """
        )
    else:
        _, tables = await conn.execute_query(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'agents' AND table_schema = 'public'
            """
        )
    if not tables:
        logger.info(
            "Agents table does not exist yet, skipping powered_by_text migration"
        )
        return

    # Check if powered_by_text column exists
    if is_sqlite:
        _, columns = await conn.execute_query("PRAGMA table_info(agents)")
        column_exists = any(
            (column.get("name") if isinstance(column, dict) else column[1])
            == "powered_by_text"
            for column in columns
        )
        if column_exists:
            logger.info("powered_by_text column already exists")
            return
    else:
        _, rows = await conn.execute_query(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'agents' AND column_name = 'powered_by_text'
            """
        )
        if rows:
            logger.info("powered_by_text column already exists")
            return

    logger.info("Adding powered_by_text column to agents table...")
    await execute_startup_migration_query(
        conn,
        """
        ALTER TABLE agents
        ADD COLUMN powered_by_text TEXT
        """,
    )
    logger.info("Added powered_by_text column to agents table")
    logger.info("Agent powered_by_text migration complete")


async def init_agent_visibility_values():
    """
    Normalize legacy agent visibility values.
    Convert deprecated public visibility to team.
    """
    logger.info("Normalizing agent visibility values...")

    conn = Tortoise.get_connection("default")

    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'agents' AND table_schema = 'public'
    """)

    if not tables:
        logger.info(
            "Agents table does not exist yet, skipping visibility normalization"
        )
        return

    try:
        _, rows = await execute_startup_migration_query(
            conn,
            """
            SELECT COUNT(*) AS public_count
            FROM agents
            WHERE visibility = 'public'
            """,
        )
        public_count = rows[0]["public_count"] if rows else 0
        if public_count:
            await execute_startup_migration_query(
                conn,
                """
                UPDATE agents
                SET visibility = 'team'
                WHERE visibility = 'public'
                """,
            )
            logger.info("Normalized legacy public agent visibility to team")
        else:
            logger.info("No legacy public agent visibility values found")
    except Exception as e:
        logger.error(f"Could not normalize agent visibility values: {e}")
        raise


async def init_workflow_visibility_field():
    """
    Add visibility field to workflows table if it doesn't exist.
    This handles the migration for the workflow visibility feature.
    Must be called BEFORE Tortoise.generate_schemas() to avoid schema mismatch.
    """
    logger.info("Checking workflow visibility field...")

    conn = Tortoise.get_connection("default")

    # Check if workflows table exists first
    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'workflows' AND table_schema = 'public'
    """)

    if not tables:
        logger.info("Workflows table does not exist yet, skipping visibility migration")
        return

    # Check if visibility column exists
    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'workflows' AND column_name = 'visibility'
    """)

    if not rows:
        logger.info("Adding visibility column to workflows table...")
        try:
            await conn.execute_query("""
                ALTER TABLE workflows
                ADD COLUMN visibility VARCHAR(10) NOT NULL DEFAULT 'private'
            """)
            logger.info("Added visibility column to workflows table")
        except Exception as e:
            logger.error(f"Could not add visibility column: {e}")
            raise
    else:
        logger.info("visibility column already exists")

    logger.info("Workflow visibility migration complete")


async def init_agent_streaming_config():
    """
    Add streaming_config field to agents table if it doesn't exist.
    This handles the migration for the streaming configuration feature.
    Must be called BEFORE Tortoise.generate_schemas() to avoid schema mismatch.
    """
    logger.info("Checking agent streaming_config field...")

    conn = Tortoise.get_connection("default")

    # Check if agents table exists first
    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'agents' AND table_schema = 'public'
    """)

    if not tables:
        logger.info(
            "Agents table does not exist yet, skipping streaming_config migration"
        )
        return

    # Check if streaming_config column exists
    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'agents' AND column_name = 'streaming_config'
    """)

    if not rows:
        logger.info("Adding streaming_config column to agents table...")
        try:
            await execute_startup_migration_query(
                conn,
                """
                ALTER TABLE agents
                ADD COLUMN streaming_config JSONB NOT NULL DEFAULT '{}'::jsonb
                """,
            )
            logger.info("Added streaming_config column to agents table")
        except Exception as e:
            logger.error(f"Could not add streaming_config column: {e}")
            raise
    else:
        logger.info("streaming_config column already exists")

    logger.info("Agent streaming_config migration complete")


async def init_agent_context_compression_config():
    """
    Add context_compression_config field to agents table if it doesn't exist.
    This handles the migration for the context compression configuration feature.
    Must be called BEFORE Tortoise.generate_schemas() to avoid schema mismatch.
    """
    logger.info("Checking agent context_compression_config field...")

    conn = Tortoise.get_connection("default")

    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'agents' AND table_schema = 'public'
    """)

    if not tables:
        logger.info(
            "Agents table does not exist yet, skipping context_compression_config migration"
        )
        return

    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'agents' AND column_name = 'context_compression_config'
    """)

    if not rows:
        logger.info("Adding context_compression_config column to agents table...")
        try:
            await execute_startup_migration_query(
                conn,
                """
                ALTER TABLE agents
                ADD COLUMN context_compression_config JSONB NOT NULL DEFAULT '{}'::jsonb
                """,
            )
            logger.info("Added context_compression_config column to agents table")
        except Exception as e:
            logger.error(f"Could not add context_compression_config column: {e}")
            raise
    else:
        logger.info("context_compression_config column already exists")

    logger.info("Agent context_compression_config migration complete")


async def init_message_manual_stop_field():
    """
    Add is_manually_stopped field to messages table if it doesn't exist.
    This handles the migration for persisted manual stop state on assistant messages.
    Must be called BEFORE Tortoise.generate_schemas() to avoid schema mismatch.
    """
    logger.info("Checking message is_manually_stopped field...")

    conn = Tortoise.get_connection("default")

    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'messages' AND table_schema = 'public'
    """)

    if not tables:
        logger.info(
            "Messages table does not exist yet, skipping is_manually_stopped migration"
        )
        return

    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'messages' AND column_name = 'is_manually_stopped'
    """)

    if not rows:
        logger.info("Adding is_manually_stopped column to messages table...")
        try:
            await conn.execute_query("""
                ALTER TABLE messages
                ADD COLUMN is_manually_stopped BOOLEAN NOT NULL DEFAULT FALSE
            """)
            logger.info("Added is_manually_stopped column to messages table")
        except Exception as e:
            logger.error(f"Could not add is_manually_stopped column: {e}")
            raise
    else:
        logger.info("is_manually_stopped column already exists")

    logger.info("Message manual stop migration complete")


async def init_message_first_token_field():
    """Add first_token_ms field to messages table if it does not exist."""
    logger.info("Checking message first_token_ms field...")

    conn = Tortoise.get_connection("default")
    dialect = getattr(getattr(conn, "capabilities", None), "dialect", "")
    if dialect != "postgres":
        logger.info("Skipping first_token_ms migration for non-PostgreSQL database")
        return

    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'messages' AND table_schema = 'public'
    """)

    if not tables:
        logger.info(
            "Messages table does not exist yet, skipping first_token_ms migration"
        )
        return

    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'messages' AND column_name = 'first_token_ms'
    """)

    if rows:
        logger.info("first_token_ms column already exists")
        return

    logger.info("Adding first_token_ms column to messages table...")
    await execute_startup_migration_query(
        conn,
        """
        ALTER TABLE messages
        ADD COLUMN first_token_ms INT NULL
        """,
    )
    logger.info("Message first_token_ms migration complete")


async def init_message_round_fields():
    """
    Add round-aware metadata fields to messages table.
    This handles the migration for first-class round tracking.
    Must be called BEFORE Tortoise.generate_schemas() to avoid schema mismatch.
    """
    logger.info("Initializing message round metadata fields...")

    conn = Tortoise.get_connection("default")

    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'messages' AND table_schema = 'public'
    """)

    if not tables:
        logger.info(
            "Messages table does not exist yet, skipping round metadata migration"
        )
        return

    await conn.execute_query("""
        ALTER TABLE messages
        ADD COLUMN IF NOT EXISTS round_id UUID NULL
    """)
    await conn.execute_query("""
        ALTER TABLE messages
        ADD COLUMN IF NOT EXISTS round_index INT NOT NULL DEFAULT 0
    """)
    await conn.execute_query("""
        ALTER TABLE messages
        ADD COLUMN IF NOT EXISTS round_role VARCHAR(32) NULL
    """)
    await conn.execute_query("""
        ALTER TABLE messages
        ADD COLUMN IF NOT EXISTS is_round_canonical BOOLEAN NOT NULL DEFAULT FALSE
    """)
    await conn.execute_query("""
        ALTER TABLE messages
        ADD COLUMN IF NOT EXISTS iteration_index INT NULL
    """)
    await conn.execute_query("""
        ALTER TABLE messages
        ADD COLUMN IF NOT EXISTS round_status VARCHAR(32) NULL
    """)

    logger.info("Message round metadata migration complete")


async def init_message_branch_parent_field():
    """
    Add branch_parent_id to messages and backfill a best-effort visible branch.
    Must be called BEFORE Tortoise.generate_schemas() to avoid schema mismatch.
    """
    logger.info("Initializing message branch parent field...")

    conn = Tortoise.get_connection("default")
    dialect = getattr(getattr(conn, "capabilities", None), "dialect", "")
    is_sqlite = dialect == "sqlite" or "sqlite" in conn.__class__.__name__.lower()

    if is_sqlite:
        _, tables = await conn.execute_query("""
            SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'messages'
        """)
    else:
        _, tables = await conn.execute_query("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'messages' AND table_schema = 'public'
        """)

    if not tables:
        logger.info(
            "Messages table does not exist yet, skipping branch parent migration"
        )
        return

    if is_sqlite:
        _, columns = await conn.execute_query("PRAGMA table_info(messages)")
        column_exists = any(
            (column.get("name") if isinstance(column, dict) else column[1])
            == "branch_parent_id"
            for column in columns
        )
        if not column_exists:
            await conn.execute_query("""
                ALTER TABLE messages
                ADD COLUMN branch_parent_id CHAR(36) NULL
            """)
    else:
        await conn.execute_query("""
            ALTER TABLE messages
            ADD COLUMN IF NOT EXISTS branch_parent_id UUID NULL
        """)

    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_messages_conversation_branch_parent
        ON messages (conversation_id, branch_parent_id)
    """)

    await conn.execute_query("""
        WITH active_canonical AS (
            SELECT
                id,
                LAG(id) OVER (PARTITION BY conversation_id ORDER BY created_at, id) AS previous_id
            FROM messages
            WHERE is_active = TRUE
              AND (round_id IS NULL OR is_round_canonical = TRUE)
        )
        UPDATE messages AS m
        SET branch_parent_id = active_canonical.previous_id
        FROM active_canonical
        WHERE m.id = active_canonical.id
          AND m.branch_parent_id IS NULL
    """)

    await conn.execute_query("""
        UPDATE messages AS m
        SET branch_parent_id = root.branch_parent_id
        FROM messages AS root
        WHERE m.parent_id = root.id
          AND m.branch_parent_id IS NULL
    """)

    await conn.execute_query("""
        WITH round_canonical AS (
            SELECT
                conversation_id,
                round_id,
                id AS canonical_id,
                ROW_NUMBER() OVER (
                    PARTITION BY conversation_id, round_id
                    ORDER BY created_at, id
                ) AS rn
            FROM messages
            WHERE round_id IS NOT NULL
              AND is_round_canonical = TRUE
        )
        UPDATE messages AS m
        SET branch_parent_id = round_canonical.canonical_id
        FROM round_canonical
        WHERE m.conversation_id = round_canonical.conversation_id
          AND m.round_id = round_canonical.round_id
          AND round_canonical.rn = 1
          AND m.is_round_canonical = FALSE
          AND m.branch_parent_id IS NULL
    """)

    logger.info("Message branch parent migration complete")


async def init_message_history_index():
    """
    Create the composite index backing the conversation-history query
    (WHERE conversation_id = ? AND is_active = ? ORDER BY created_at).
    Without it, large conversations sort in memory on every history load.
    Idempotent; safe on every startup.
    """
    logger.info("Checking messages history index...")

    conn = Tortoise.get_connection("default")
    dialect = getattr(getattr(conn, "capabilities", None), "dialect", "")
    is_sqlite = dialect == "sqlite" or "sqlite" in conn.__class__.__name__.lower()

    if is_sqlite:
        _, tables = await conn.execute_query(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'messages'
            """
        )
    else:
        _, tables = await conn.execute_query(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'messages' AND table_schema = 'public'
            """
        )
    if not tables:
        logger.info(
            "Messages table does not exist yet, skipping history index migration"
        )
        return

    if is_sqlite:
        _, indexes = await conn.execute_query(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'index'
              AND tbl_name = 'messages'
              AND name = 'idx_messages_conversation_active_created_at'
            """
        )
    else:
        _, indexes = await conn.execute_query(
            """
            SELECT indexname FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'messages'
              AND indexname = 'idx_messages_conversation_active_created_at'
            """
        )
    if indexes:
        logger.info("Messages history index already exists")
        return

    await execute_startup_migration_query(
        conn,
        """
        CREATE INDEX idx_messages_conversation_active_created_at
        ON messages (conversation_id, is_active, created_at)
        """,
    )
    logger.info("Created messages history index")


async def init_conversation_context_summary_columns() -> None:
    """Add persistent context summary columns to conversations."""
    logger.info("Initializing conversation context summary columns...")

    conn = Tortoise.get_connection("default")
    await execute_startup_migration_query(
        conn,
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS context_summary_text TEXT",
    )
    await execute_startup_migration_query(
        conn,
        "ALTER TABLE conversations "
        "ADD COLUMN IF NOT EXISTS context_summary_watermark_id UUID",
    )
    logger.info("Conversation context summary columns initialized")


async def init_assets_tables() -> None:
    """Create durable Asset metadata and scoped reference tables."""
    logger.info("Initializing Asset tables...")
    conn = Tortoise.get_connection("default")

    await conn.execute_query("""
        CREATE TABLE IF NOT EXISTS assets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
            created_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            parent_id UUID REFERENCES assets(id) ON DELETE SET NULL,
            storage_key VARCHAR(1000) NOT NULL UNIQUE,
            original_filename VARCHAR(500) NOT NULL,
            display_filename VARCHAR(500) NOT NULL,
            content_type VARCHAR(255) NOT NULL,
            size BIGINT NOT NULL CHECK (size >= 0),
            checksum VARCHAR(64) NOT NULL,
            source VARCHAR(32) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'available',
            provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
            expires_at TIMESTAMPTZ,
            deleted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_assets_team_status_created
        ON assets(team_id, status, created_at)
    """)
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_assets_checksum ON assets(checksum)
    """)
    await conn.execute_query("""
        CREATE TABLE IF NOT EXISTS message_assets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            role VARCHAR(30) NOT NULL DEFAULT 'attachment',
            position INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(message_id, asset_id, role)
        )
    """)
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_message_assets_message_position
        ON message_assets(message_id, position, created_at)
    """)
    await conn.execute_query("""
        CREATE TABLE IF NOT EXISTS asset_scope_refs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scope_type VARCHAR(20) NOT NULL,
            scope_id UUID NOT NULL,
            asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            ref VARCHAR(4) NOT NULL CHECK (ref ~ '^[0-9a-f]{4}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(scope_type, scope_id, asset_id),
            UNIQUE(scope_type, scope_id, ref)
        )
    """)
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_asset_scope_refs_scope
        ON asset_scope_refs(scope_type, scope_id)
    """)
    logger.info("Asset table initialization complete")


async def init_permission_is_system_field():
    """
    Add is_system field to permissions table if it doesn't exist.
    This handles the migration for the system permission protection feature.
    Must be called BEFORE Tortoise.generate_schemas() to avoid schema mismatch.
    """
    logger.info("Checking permission is_system field...")

    conn = Tortoise.get_connection("default")

    # Check if permissions table exists first
    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'permissions' AND table_schema = 'public'
    """)

    if not tables:
        logger.info(
            "Permissions table does not exist yet, skipping is_system migration"
        )
        return

    # Check if is_system column exists
    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'permissions' AND column_name = 'is_system'
    """)

    if not rows:
        logger.info("Adding is_system column to permissions table...")
        try:
            await conn.execute_query("""
                ALTER TABLE permissions
                ADD COLUMN is_system BOOLEAN NOT NULL DEFAULT TRUE
            """)
            logger.info("Added is_system column to permissions table")
        except Exception as e:
            logger.error(f"Could not add is_system column: {e}")
            raise
    else:
        logger.info("is_system column already exists")

    logger.info("Permission is_system migration complete")


async def init_agent_run_fields():
    """Add durable worker and user-interaction fields to AgentRun."""
    conn = Tortoise.get_connection("default")
    _, tables = await conn.execute_query(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'agent_runs' AND table_schema = 'public'
        """
    )
    if not tables:
        return

    await execute_startup_migration_query(
        conn,
        """
        ALTER TABLE agent_runs
            ADD COLUMN IF NOT EXISTS worker_payload JSONB,
            ADD COLUMN IF NOT EXISTS pending_tool_call_id VARCHAR(200),
            ADD COLUMN IF NOT EXISTS pending_tool_name VARCHAR(200),
            ADD COLUMN IF NOT EXISTS pending_tool_input JSONB,
            ADD COLUMN IF NOT EXISTS pending_tool_round_id UUID,
            ADD COLUMN IF NOT EXISTS pending_tool_round_index INTEGER,
            ADD COLUMN IF NOT EXISTS pending_tool_iteration_index INTEGER
        """,
    )


async def init_agent_user_input_request():
    """Add the Agent ask_user enablement field when upgrading an existing database."""
    conn = Tortoise.get_connection("default")
    _, tables = await conn.execute_query(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'agents' AND table_schema = 'public'
        """
    )
    if not tables:
        return

    _, rows = await conn.execute_query(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'agents' AND column_name = 'enable_user_input_request'
        """
    )
    if not rows:
        await execute_startup_migration_query(
            conn,
            """
            ALTER TABLE agents
            ADD COLUMN enable_user_input_request BOOLEAN NOT NULL DEFAULT FALSE
            """,
        )


async def init_skills_table():
    """Initialize package-backed Agent Skills tables."""
    logger.info("Initializing skills table...")

    conn = Tortoise.get_connection("default")

    await conn.execute_query("""
        CREATE TABLE IF NOT EXISTS skills (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            display_name VARCHAR(100) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            icon VARCHAR(100),
            category VARCHAR(20) NOT NULL DEFAULT 'other',
            version VARCHAR(50) NOT NULL DEFAULT '1.0.0',
            source_type VARCHAR(20) NOT NULL DEFAULT 'legacy',
            source_uri TEXT,
            source_ref VARCHAR(255),
            source_subdir VARCHAR(500),
            package_path VARCHAR(500),
            package_storage_path VARCHAR(1000),
            package_hash VARCHAR(128),
            package_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
            skill_md TEXT NOT NULL DEFAULT '',
            instructions TEXT NOT NULL DEFAULT '',
            frontmatter JSONB NOT NULL DEFAULT '{}'::jsonb,
            execution_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            import_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
            input_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
            skill_spec JSONB NOT NULL DEFAULT '{}'::jsonb,
            config_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
            default_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(team_id, name)
        )
    """)

    await conn.execute_query("""
        ALTER TABLE skills
            ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) NOT NULL DEFAULT 'legacy',
            ADD COLUMN IF NOT EXISTS source_uri TEXT,
            ADD COLUMN IF NOT EXISTS source_ref VARCHAR(255),
            ADD COLUMN IF NOT EXISTS source_subdir VARCHAR(500),
            ADD COLUMN IF NOT EXISTS package_path VARCHAR(500),
            ADD COLUMN IF NOT EXISTS package_storage_path VARCHAR(1000),
            ADD COLUMN IF NOT EXISTS package_hash VARCHAR(128),
            ADD COLUMN IF NOT EXISTS package_manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS skill_md TEXT NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS instructions TEXT NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS frontmatter JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS execution_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS import_warnings JSONB NOT NULL DEFAULT '[]'::jsonb
    """)

    await conn.execute_query("""
        CREATE TABLE IF NOT EXISTS skill_import_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
            source_type VARCHAR(20) NOT NULL,
            source_uri TEXT,
            source_ref VARCHAR(255),
            source_subdir VARCHAR(500),
            status VARCHAR(20) NOT NULL DEFAULT 'previewed',
            preview JSONB NOT NULL DEFAULT '{}'::jsonb,
            temp_storage_path VARCHAR(1000),
            expires_at TIMESTAMPTZ NOT NULL,
            created_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    await _execute_ddl(
        conn,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_skills_system_name
        ON skills(name)
        WHERE team_id IS NULL;
        CREATE INDEX IF NOT EXISTS idx_skills_team_id ON skills(team_id);
        CREATE INDEX IF NOT EXISTS idx_skills_created_by ON skills(created_by_id);
        CREATE INDEX IF NOT EXISTS idx_skills_enabled ON skills(is_enabled);
        CREATE INDEX IF NOT EXISTS idx_skills_source_type ON skills(source_type);
        CREATE INDEX IF NOT EXISTS idx_skill_import_sessions_team_id ON skill_import_sessions(team_id);
        CREATE INDEX IF NOT EXISTS idx_skill_import_sessions_status ON skill_import_sessions(status);
        CREATE INDEX IF NOT EXISTS idx_skill_import_sessions_expires_at ON skill_import_sessions(expires_at);
    """,
    )

    logger.info("skills table initialization complete")


async def init_tool_shares_table():
    """
    Initialize tool_shares table for cross-team tool sharing feature.
    This handles the migration for the new tool sharing functionality.
    """
    logger.info("Initializing tool_shares table...")

    conn = Tortoise.get_connection("default")

    # Check if tool_shares table exists
    _, rows = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'tool_shares'
    """)

    if rows:
        logger.info("tool_shares table already exists, skipping creation")
        return

    logger.info("Creating tool_shares table...")

    # Create tool_shares table
    await conn.execute_query("""
        CREATE TABLE IF NOT EXISTS tool_shares (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tool_id UUID NOT NULL REFERENCES tools(id) ON DELETE CASCADE,
            shared_with_team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            permission VARCHAR(20) NOT NULL DEFAULT 'read_only',
            shared_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            shared_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(tool_id, shared_with_team_id)
        )
    """)
    logger.info("Created tool_shares table")

    # Create indexes for better query performance
    await _execute_ddl(
        conn,
        """
        CREATE INDEX IF NOT EXISTS idx_tool_shares_tool_id ON tool_shares(tool_id);
        CREATE INDEX IF NOT EXISTS idx_tool_shares_team_id ON tool_shares(shared_with_team_id);
        CREATE INDEX IF NOT EXISTS idx_tool_shares_shared_by ON tool_shares(shared_by_id);
    """,
    )
    logger.info("Created tool_shares indexes")

    logger.info("tool_shares table initialization complete")


async def init_notification_tables():
    """
    Initialize notification tables if they don't exist.
    This handles the migration for the notification center feature.
    """
    logger.info("Initializing notification tables...")

    conn = Tortoise.get_connection("default")

    # Check if notifications table exists
    _, rows = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'notifications'
    """)

    if not rows:
        logger.info("Creating notification tables...")

        await conn.execute_query("""
            CREATE TABLE IF NOT EXISTS notifications (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                scope VARCHAR(20) NOT NULL,
                team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                type VARCHAR(100) NOT NULL,
                source VARCHAR(20) NOT NULL,
                title VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                level VARCHAR(20) NOT NULL,
                data JSONB,
                link_url VARCHAR(500),
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                expires_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        await conn.execute_query("""
            CREATE TABLE IF NOT EXISTS notification_reads (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                notification_id UUID NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                read_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(notification_id, user_id)
            )
        """)

        await conn.execute_query("""
            CREATE TABLE IF NOT EXISTS notification_audits (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                notification_id UUID NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
                user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                action VARCHAR(20) NOT NULL,
                meta JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        await _execute_ddl(
            conn,
            """
            CREATE INDEX IF NOT EXISTS idx_notifications_scope_created_at
                ON notifications(scope, created_at);
            CREATE INDEX IF NOT EXISTS idx_notifications_team_id_created_at
                ON notifications(team_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_notifications_user_id_created_at
                ON notifications(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_notifications_type_created_at
                ON notifications(type, created_at);

            CREATE INDEX IF NOT EXISTS idx_notification_reads_user_id_read_at
                ON notification_reads(user_id, read_at);
            CREATE INDEX IF NOT EXISTS idx_notification_reads_notification_id_user_id
                ON notification_reads(notification_id, user_id);

            CREATE INDEX IF NOT EXISTS idx_notification_audits_notification_id_created_at
                ON notification_audits(notification_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_notification_audits_user_id_created_at
                ON notification_audits(user_id, created_at);
        """,
        )

        logger.info("Notification tables created")
    else:
        logger.info("Notification tables already exist")

    # Check and create notification_deliveries table
    _, rows = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'notification_deliveries'
    """)

    if not rows:
        logger.info("Creating notification_deliveries table...")

        await conn.execute_query("""
            CREATE TABLE IF NOT EXISTS notification_deliveries (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                notification_id UUID NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
                channel VARCHAR(20) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                task_id VARCHAR(100),
                error_message TEXT,
                retry_count INT NOT NULL DEFAULT 0,
                sent_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(notification_id, channel)
            )
        """)

        await _execute_ddl(
            conn,
            """
            CREATE INDEX IF NOT EXISTS idx_notification_deliveries_notification_channel
                ON notification_deliveries(notification_id, channel);
            CREATE INDEX IF NOT EXISTS idx_notification_deliveries_status_created
                ON notification_deliveries(status, created_at);
        """,
        )

        logger.info("notification_deliveries table created")
    else:
        logger.info("notification_deliveries table already exists")

    logger.info("Notification tables initialization complete")


async def fix_cascade_delete_policies():
    """
    Fix CASCADE delete policies to SET NULL for better data preservation.
    This migration updates foreign key constraints to prevent data loss when users are deleted.
    """
    logger.info("Fixing CASCADE delete policies...")

    conn = Tortoise.get_connection("default")

    try:
        await conn.execute_query(
            f"SET lock_timeout = '{STARTUP_MIGRATION_LOCK_TIMEOUT}'"
        )
        # 1. Fix Agent.created_by: CASCADE -> SET NULL
        logger.info("Fixing agents.created_by_id foreign key...")
        await conn.execute_query("""
            ALTER TABLE agents
            DROP CONSTRAINT IF EXISTS agents_created_by_id_fkey;
        """)
        await conn.execute_query("""
            ALTER TABLE agents
            ADD CONSTRAINT agents_created_by_id_fkey
            FOREIGN KEY (created_by_id) REFERENCES users(id) ON DELETE SET NULL;
        """)
        logger.info("Fixed agents.created_by_id")

        # 2. Fix Workflow.created_by: CASCADE -> SET NULL
        logger.info("Fixing workflows.created_by_id foreign key...")
        await conn.execute_query("""
            ALTER TABLE workflows
            DROP CONSTRAINT IF EXISTS workflows_created_by_id_fkey;
        """)
        await conn.execute_query("""
            ALTER TABLE workflows
            ADD CONSTRAINT workflows_created_by_id_fkey
            FOREIGN KEY (created_by_id) REFERENCES users(id) ON DELETE SET NULL;
        """)
        logger.info("Fixed workflows.created_by_id")

        # 3. Fix Tool.created_by: CASCADE -> SET NULL
        logger.info("Fixing tools.created_by_id foreign key...")
        await conn.execute_query("""
            ALTER TABLE tools
            DROP CONSTRAINT IF EXISTS tools_created_by_id_fkey;
        """)
        await conn.execute_query("""
            ALTER TABLE tools
            ADD CONSTRAINT tools_created_by_id_fkey
            FOREIGN KEY (created_by_id) REFERENCES users(id) ON DELETE SET NULL;
        """)
        logger.info("Fixed tools.created_by_id")

        # 4. Fix ToolShare.shared_by: CASCADE -> SET NULL
        logger.info("Fixing tool_shares.shared_by_id foreign key...")
        await conn.execute_query("""
            ALTER TABLE tool_shares
            DROP CONSTRAINT IF EXISTS tool_shares_shared_by_id_fkey;
        """)
        await conn.execute_query("""
            ALTER TABLE tool_shares
            ADD CONSTRAINT tool_shares_shared_by_id_fkey
            FOREIGN KEY (shared_by_id) REFERENCES users(id) ON DELETE SET NULL;
        """)
        logger.info("Fixed tool_shares.shared_by_id")

        # 5. Fix WorkflowRun.workflow: CASCADE -> SET NULL
        logger.info("Fixing workflow_runs.workflow_id foreign key...")
        await conn.execute_query("""
            ALTER TABLE workflow_runs
            DROP CONSTRAINT IF EXISTS workflow_runs_workflow_id_fkey;
        """)
        await conn.execute_query("""
            ALTER TABLE workflow_runs
            ADD CONSTRAINT workflow_runs_workflow_id_fkey
            FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE SET NULL;
        """)
        logger.info("Fixed workflow_runs.workflow_id")

        # 6. Fix Conversation.agent: CASCADE -> SET NULL
        logger.info("Fixing conversations.agent_id foreign key...")
        await conn.execute_query("""
            ALTER TABLE conversations
            DROP CONSTRAINT IF EXISTS conversations_agent_id_fkey;
        """)
        await conn.execute_query("""
            ALTER TABLE conversations
            ADD CONSTRAINT conversations_agent_id_fkey
            FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE SET NULL;
        """)
        logger.info("Fixed conversations.agent_id")

        # 7. Add soft delete fields to teams table
        logger.info("Adding soft delete fields to teams table...")

        # Check if is_deleted column exists
        _, rows = await conn.execute_query("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'teams' AND column_name = 'is_deleted'
        """)

        if not rows:
            await conn.execute_query("""
                ALTER TABLE teams
                ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT FALSE;
            """)
            logger.info("Added is_deleted column to teams")

        # Check if deleted_at column exists
        _, rows = await conn.execute_query("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'teams' AND column_name = 'deleted_at'
        """)

        if not rows:
            await conn.execute_query("""
                ALTER TABLE teams
                ADD COLUMN deleted_at TIMESTAMPTZ NULL;
            """)
            logger.info("Added deleted_at column to teams")

        # Check if deleted_by_id column exists
        _, rows = await conn.execute_query("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'teams' AND column_name = 'deleted_by_id'
        """)

        if not rows:
            await conn.execute_query("""
                ALTER TABLE teams
                ADD COLUMN deleted_by_id UUID NULL REFERENCES users(id) ON DELETE SET NULL;
            """)
            logger.info("Added deleted_by_id column to teams")

        # 8. Add cumulative statistics fields
        logger.info("Adding cumulative statistics fields...")

        # Add total_tokens to agents table
        _, rows = await conn.execute_query("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'agents' AND column_name = 'total_tokens'
        """)

        if not rows:
            await conn.execute_query("""
                ALTER TABLE agents
                ADD COLUMN total_tokens BIGINT NOT NULL DEFAULT 0;
            """)
            logger.info("Added total_tokens column to agents")

        # Add total_tokens to workflows table
        _, rows = await conn.execute_query("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'workflows' AND column_name = 'total_tokens'
        """)

        if not rows:
            await conn.execute_query("""
                ALTER TABLE workflows
                ADD COLUMN total_tokens BIGINT NOT NULL DEFAULT 0;
            """)
            logger.info("Added total_tokens column to workflows")

        # Add statistics fields to teams table
        _, rows = await conn.execute_query("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'teams' AND column_name = 'total_conversations'
        """)

        if not rows:
            await conn.execute_query("""
                ALTER TABLE teams
                ADD COLUMN total_conversations INT NOT NULL DEFAULT 0,
                ADD COLUMN total_messages INT NOT NULL DEFAULT 0,
                ADD COLUMN total_tokens BIGINT NOT NULL DEFAULT 0;
            """)
            logger.info("Added statistics columns to teams")

        logger.info("CASCADE delete policies fixed successfully")

    except Exception as e:
        logger.error(f"Error fixing CASCADE delete policies: {e}")
        # Don't raise - allow app to continue even if migration fails
        logger.warning("Continuing despite migration errors...")
    finally:
        await conn.execute_query("RESET lock_timeout")


async def init_sso_tables():
    """
    Initialize SSO (Single Sign-On) related tables if they don't exist.
    This handles the migration for the SSO feature.
    """
    logger.info("Initializing SSO tables...")

    conn = Tortoise.get_connection("default")

    # Check if sso_providers table exists
    _, rows = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'sso_providers'
    """)

    if rows:
        logger.info("SSO tables already exist, skipping creation")
        return

    logger.info("Creating SSO tables...")

    # Create sso_providers table
    await conn.execute_query("""
        CREATE TABLE IF NOT EXISTS sso_providers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(100) UNIQUE NOT NULL,
            protocol VARCHAR(20) NOT NULL,
            display_name VARCHAR(100) NOT NULL,
            icon_url VARCHAR(512),
            button_text VARCHAR(50),
            config JSONB NOT NULL,
            attribute_mapping JSONB NOT NULL DEFAULT '{}',
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            allow_signup BOOLEAN NOT NULL DEFAULT TRUE,
            require_approval BOOLEAN NOT NULL DEFAULT FALSE,
            default_role_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_by_id UUID REFERENCES users(id) ON DELETE SET NULL
        )
    """)
    logger.info("Created sso_providers table")

    # Create user_sso_connections table
    await conn.execute_query("""
        CREATE TABLE IF NOT EXISTS user_sso_connections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider_id UUID NOT NULL REFERENCES sso_providers(id) ON DELETE CASCADE,
            provider_user_id VARCHAR(255) NOT NULL,
            provider_username VARCHAR(255),
            provider_email VARCHAR(255),
            provider_data JSONB NOT NULL DEFAULT '{}',
            first_login TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (provider_id, provider_user_id)
        )
    """)
    logger.info("Created user_sso_connections table")

    # Create sso_sessions table
    await conn.execute_query("""
        CREATE TABLE IF NOT EXISTS sso_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id VARCHAR(255) UNIQUE NOT NULL,
            provider_id UUID NOT NULL REFERENCES sso_providers(id) ON DELETE CASCADE,
            code_verifier VARCHAR(255),
            nonce VARCHAR(255),
            redirect_url VARCHAR(512),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL
        )
    """)
    logger.info("Created sso_sessions table")

    # Create indexes for better performance
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_user_sso_connections_user_id
        ON user_sso_connections(user_id)
    """)
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_user_sso_connections_provider_id
        ON user_sso_connections(provider_id)
    """)
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_sso_sessions_session_id
        ON sso_sessions(session_id)
    """)
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_sso_sessions_expires_at
        ON sso_sessions(expires_at)
    """)
    logger.info("Created SSO indexes")

    logger.info("SSO tables initialization complete")


async def migrate_registration_settings_category():
    """
    Migrate registration settings from 'general' category to 'security' category.
    This ensures existing installations have the correct category for registration settings.
    """
    logger.info("Checking registration settings category...")

    from app.models.site_setting import SiteSetting

    # Settings that should be in 'security' category
    registration_keys = [
        "allow_registration",
        "require_approval",
        "email_verification",
        "allow_account_deletion",
    ]

    migrated_count = 0
    for key in registration_keys:
        setting = await SiteSetting.filter(key=key).first()
        if setting and setting.category == "general":
            setting.category = "security"
            await setting.save()
            migrated_count += 1
            logger.info(f"Migrated {key} from 'general' to 'security' category")

    if migrated_count > 0:
        logger.info(
            f"Migrated {migrated_count} registration settings to 'security' category"
        )
    else:
        logger.info("Registration settings already in correct category")


async def migrate_storage_settings_category():
    """
    Migrate audit log settings from 'audit' category to 'storage' category.
    This ensures existing installations have the correct category for storage settings.
    """
    logger.info("Checking storage settings category...")

    from app.models.site_setting import SiteSetting

    # Settings that should be in 'storage' category
    storage_keys = [
        "audit_log_retention_days",
        "audit_log_archive_path",
    ]

    migrated_count = 0
    for key in storage_keys:
        setting = await SiteSetting.filter(key=key).first()
        if setting and setting.category == "audit":
            setting.category = "storage"
            await setting.save()
            migrated_count += 1
            logger.info(f"Migrated {key} from 'audit' to 'storage' category")

    if migrated_count > 0:
        logger.info(f"Migrated {migrated_count} storage settings to 'storage' category")
    else:
        logger.info("Storage settings already in correct category")


async def init_memory_tables():
    """
    Initialize memory-related tables for user memory graph.
    This handles the migration for the memory feature.
    """
    logger.info("Initializing memory tables...")

    conn = Tortoise.get_connection("default")

    # Check if memory_entities table exists
    _, rows = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'memory_entities'
    """)

    if rows:
        logger.info("Memory tables already exist, checking for schema updates...")

        # Migrate embedding_model_id from UUID to VARCHAR(255)
        try:
            # Check current column type
            _, col_info = await conn.execute_query("""
                SELECT data_type FROM information_schema.columns
                WHERE table_name = 'memory_entities' AND column_name = 'embedding_model_id'
            """)

            if col_info and col_info[0]["data_type"] == "uuid":
                logger.info("Migrating embedding_model_id from UUID to VARCHAR(255)...")
                await conn.execute_query("""
                    ALTER TABLE memory_entities
                    ALTER COLUMN embedding_model_id TYPE VARCHAR(255)
                    USING embedding_model_id::text
                """)
                logger.info("Successfully migrated embedding_model_id to VARCHAR(255)")
        except Exception as e:
            logger.error(f"Failed to migrate embedding_model_id: {e}")

        return

    logger.info("Creating memory tables...")

    # Create memory_entities table
    await conn.execute_query("""
        CREATE TABLE IF NOT EXISTS memory_entities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            entity_type VARCHAR(20) NOT NULL,
            description TEXT,
            properties JSONB NOT NULL DEFAULT '{}',
            source_conversation_id UUID,
            source_message_id UUID,
            embedding_id VARCHAR(100),
            embedding_model_id VARCHAR(255),
            access_count INT NOT NULL DEFAULT 0,
            last_accessed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, name, entity_type)
        )
    """)
    logger.info("Created memory_entities table")

    # Create indexes for memory_entities
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_memory_entities_user_type
        ON memory_entities(user_id, entity_type)
    """)
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_memory_entities_user_name
        ON memory_entities(user_id, name)
    """)
    logger.info("Created indexes for memory_entities")

    # Create memory_relations table
    await conn.execute_query("""
        CREATE TABLE IF NOT EXISTS memory_relations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_entity_id UUID NOT NULL REFERENCES memory_entities(id) ON DELETE CASCADE,
            target_entity_id UUID NOT NULL REFERENCES memory_entities(id) ON DELETE CASCADE,
            relation_type VARCHAR(20) NOT NULL,
            description TEXT,
            properties JSONB NOT NULL DEFAULT '{}',
            source_conversation_id UUID,
            source_message_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, source_entity_id, target_entity_id, relation_type)
        )
    """)
    logger.info("Created memory_relations table")

    # Create indexes for memory_relations
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_memory_relations_user_source
        ON memory_relations(user_id, source_entity_id)
    """)
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_memory_relations_user_target
        ON memory_relations(user_id, target_entity_id)
    """)
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_memory_relations_user_type
        ON memory_relations(user_id, relation_type)
    """)
    logger.info("Created indexes for memory_relations")

    logger.info("Memory tables initialization complete")


async def init_agent_hide_tool_calls_field():
    """Add hide_tool_calls field to agents table."""
    logger.info("Initializing agent hide_tool_calls field...")

    conn = Tortoise.get_connection("default")

    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'agents' AND table_schema = 'public'
    """)

    if not tables:
        logger.info(
            "Agents table does not exist yet, skipping hide_tool_calls migration"
        )
        return

    await execute_startup_migration_query(
        conn,
        """
        ALTER TABLE agents
        ADD COLUMN IF NOT EXISTS hide_tool_calls BOOLEAN NOT NULL DEFAULT FALSE
        """,
    )

    logger.info("Agent hide_tool_calls field added successfully")


async def init_agent_hide_message_actions_reasoning_fields():
    """Add hide_message_actions and hide_reasoning fields to agents table."""
    logger.info("Initializing agent hide_message_actions and hide_reasoning fields...")

    conn = Tortoise.get_connection("default")

    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'agents' AND table_schema = 'public'
    """)

    if not tables:
        logger.info(
            "Agents table does not exist yet, skipping hide_message_actions/hide_reasoning migration"
        )
        return

    await execute_startup_migration_query(
        conn,
        """
        ALTER TABLE agents
        ADD COLUMN IF NOT EXISTS hide_message_actions BOOLEAN NOT NULL DEFAULT FALSE
        """,
    )

    await execute_startup_migration_query(
        conn,
        """
        ALTER TABLE agents
        ADD COLUMN IF NOT EXISTS hide_reasoning BOOLEAN NOT NULL DEFAULT FALSE
        """,
    )

    logger.info(
        "Agent hide_message_actions and hide_reasoning fields added successfully"
    )


async def init_agent_memory_fields():
    """
    Add enable_memory and memory_config fields to agents table.
    """
    logger.info("Initializing agent memory fields...")

    conn = Tortoise.get_connection("default")

    # Check if enable_memory column exists
    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'agents' AND column_name = 'enable_memory'
    """)

    if rows:
        logger.info("Agent memory fields already exist, skipping")
        return

    logger.info("Adding enable_memory and memory_config fields to agents table...")

    # Add enable_memory field
    await execute_startup_migration_query(
        conn,
        """
        ALTER TABLE agents
        ADD COLUMN IF NOT EXISTS enable_memory BOOLEAN NOT NULL DEFAULT FALSE
        """,
    )

    # Add memory_config field
    await execute_startup_migration_query(
        conn,
        """
        ALTER TABLE agents
        ADD COLUMN IF NOT EXISTS memory_config JSONB NOT NULL DEFAULT '{}'
        """,
    )

    logger.info("Agent memory fields added successfully")


async def init_agent_media_generation_fields():
    """
    Add media generation module fields to agents table.
    """
    logger.info("Initializing agent media generation fields...")

    conn = Tortoise.get_connection("default")

    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'agents' AND table_schema = 'public'
    """)

    if not tables:
        logger.info(
            "Agents table does not exist yet, skipping media generation migration"
        )
        return

    await execute_startup_migration_query(
        conn,
        """
        ALTER TABLE agents
        ADD COLUMN IF NOT EXISTS enable_image_generation BOOLEAN NOT NULL DEFAULT FALSE
        """,
    )
    await execute_startup_migration_query(
        conn,
        """
        ALTER TABLE agents
        ADD COLUMN IF NOT EXISTS image_generation_config JSONB NOT NULL DEFAULT '{}'::jsonb
        """,
    )
    await execute_startup_migration_query(
        conn,
        """
        ALTER TABLE agents
        ADD COLUMN IF NOT EXISTS enable_video_generation BOOLEAN NOT NULL DEFAULT FALSE
        """,
    )
    await execute_startup_migration_query(
        conn,
        """
        ALTER TABLE agents
        ADD COLUMN IF NOT EXISTS video_generation_config JSONB NOT NULL DEFAULT '{}'::jsonb
        """,
    )

    logger.info("Agent media generation fields added successfully")


async def init_password_expiration():
    """
    Add password expiration fields to users table and create password_history table.
    This handles the migration for the password expiration feature.
    """
    logger.info("Initializing password expiration...")

    conn = Tortoise.get_connection("default")

    # Check if users table exists first
    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'users' AND table_schema = 'public'
    """)

    if not tables:
        logger.info(
            "Users table does not exist yet, skipping password expiration migration"
        )
        return

    # Check if password_changed_at column exists
    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'password_changed_at'
    """)

    if not rows:
        logger.info("Adding password expiration fields to users table...")
        try:
            await conn.execute_query("""
                ALTER TABLE users
                ADD COLUMN password_changed_at TIMESTAMPTZ NULL,
                ADD COLUMN password_expires_at TIMESTAMPTZ NULL,
                ADD COLUMN force_password_change BOOLEAN NOT NULL DEFAULT FALSE,
                ADD COLUMN password_expiration_exempt BOOLEAN NOT NULL DEFAULT FALSE,
                ADD COLUMN password_expiration_notified_at TIMESTAMPTZ NULL
            """)
            logger.info("Added password expiration fields to users table")

            # Initialize password_changed_at = created_at for existing users
            await conn.execute_query("""
                UPDATE users
                SET password_changed_at = created_at
                WHERE password_changed_at IS NULL AND auth_source = 'local'
            """)
            logger.info("Initialized password_changed_at for existing users")
        except Exception as e:
            logger.error(f"Could not add password expiration fields: {e}")
            raise
    else:
        logger.info("Password expiration fields already exist")

    # Check if password_history table exists
    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'password_history' AND table_schema = 'public'
    """)

    if not tables:
        logger.info("Creating password_history table...")
        try:
            await conn.execute_query("""
                CREATE TABLE IF NOT EXISTS password_history (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    hashed_password VARCHAR(255) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            logger.info("Created password_history table")

            # Create index for better query performance
            await conn.execute_query("""
                CREATE INDEX IF NOT EXISTS idx_password_history_user_id
                ON password_history(user_id, created_at DESC)
            """)
            logger.info("Created password_history index")
        except Exception as e:
            logger.error(f"Could not create password_history table: {e}")
            raise
    else:
        logger.info("password_history table already exists")

    logger.info("Password expiration migration complete")


async def init_user_approval_status_field():
    """
    Add approval_status field to users table.
    This distinguishes pending approval users from manually inactive users.
    """
    logger.info("Initializing user approval_status field...")

    conn = Tortoise.get_connection("default")

    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'users' AND table_schema = 'public'
    """)

    if not tables:
        logger.info(
            "Users table does not exist yet, skipping approval_status migration"
        )
        return

    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'approval_status'
    """)

    if not rows:
        logger.info("Adding approval_status field to users table...")
        try:
            await conn.execute_query("""
                ALTER TABLE users
                ADD COLUMN approval_status VARCHAR(20) NOT NULL DEFAULT 'approved'
            """)
            logger.info("Added approval_status field to users table")
        except Exception as e:
            logger.error(f"Could not add approval_status field: {e}")
            raise
    else:
        logger.info("approval_status field already exists")

    await conn.execute_query("""
        UPDATE users
        SET approval_status = 'approved'
        WHERE approval_status IS NULL OR approval_status = ''
    """)

    logger.info("User approval_status migration complete")


async def init_totp_fields():
    """
    Add TOTP (Two-Factor Authentication) fields to users table.
    This handles the migration for the TOTP 2FA feature.
    """
    logger.info("Initializing TOTP fields...")

    conn = Tortoise.get_connection("default")

    # Check if users table exists first
    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'users' AND table_schema = 'public'
    """)

    if not tables:
        logger.info("Users table does not exist yet, skipping TOTP migration")
        return

    # Check if totp_secret column exists
    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'totp_secret'
    """)

    if not rows:
        logger.info("Adding TOTP fields to users table...")
        try:
            await conn.execute_query("""
                ALTER TABLE users
                ADD COLUMN totp_secret VARCHAR(255) NULL,
                ADD COLUMN totp_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                ADD COLUMN totp_enabled_at TIMESTAMPTZ NULL,
                ADD COLUMN totp_backup_codes_hash TEXT NULL
            """)
            logger.info("Added TOTP fields to users table")
        except Exception as e:
            logger.error(f"Could not add TOTP fields: {e}")
            raise
    else:
        logger.info("TOTP fields already exist")

    logger.info("TOTP migration complete")


async def init_agent_kb_search_mode():
    """
    Add search_mode field to agent_knowledge_bases table.
    """
    logger.info("Initializing agent knowledge base search_mode field...")

    conn = Tortoise.get_connection("default")

    # Check if agent_knowledge_bases table exists first
    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'agent_knowledge_bases' AND table_schema = 'public'
    """)

    if not tables:
        logger.info(
            "agent_knowledge_bases table does not exist yet, skipping search_mode migration"
        )
        return

    # Check if search_mode column exists
    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'agent_knowledge_bases' AND column_name = 'search_mode'
    """)

    if rows:
        logger.info("search_mode field already exists, skipping")
        return

    logger.info("Adding search_mode field to agent_knowledge_bases table...")

    # Add search_mode field with default value 'hybrid'
    await conn.execute_query("""
        ALTER TABLE agent_knowledge_bases
        ADD COLUMN IF NOT EXISTS search_mode VARCHAR(20) NOT NULL DEFAULT 'hybrid'
    """)

    logger.info("search_mode field added successfully")


async def init_chunk_status():
    """Add status and error_message fields to document_chunks table."""
    logger.info("Initializing chunk status fields...")

    conn = Tortoise.get_connection("default")

    # Check if document_chunks table exists first
    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'document_chunks' AND table_schema = 'public'
    """)

    if not tables:
        logger.info("document_chunks table does not exist yet, skipping migration")
        return

    # Check if status column exists
    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'document_chunks' AND column_name = 'status'
    """)

    if not rows:
        logger.info("Adding status field to document_chunks table...")
        # Default to 'embedded' for existing chunks (they were already processed)
        await conn.execute_query("""
            ALTER TABLE document_chunks
            ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'embedded'
        """)
        # Change default for new rows to 'pending'
        await conn.execute_query("""
            ALTER TABLE document_chunks
            ALTER COLUMN status SET DEFAULT 'pending'
        """)
        logger.info("status field added successfully")
    else:
        logger.info("status field already exists, skipping")

    # Check if error_message column exists
    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'document_chunks' AND column_name = 'error_message'
    """)

    if not rows:
        logger.info("Adding error_message field to document_chunks table...")
        await conn.execute_query("""
            ALTER TABLE document_chunks
            ADD COLUMN IF NOT EXISTS error_message TEXT
        """)
        logger.info("error_message field added successfully")
    else:
        logger.info("error_message field already exists, skipping")

    logger.info("Chunk status migration complete")


async def init_workflow_run_page_config() -> None:
    """Add the workflow run-page presentation configuration field."""
    conn = Tortoise.get_connection("default")
    await execute_startup_migration_query(
        conn,
        """
        ALTER TABLE workflows
            ADD COLUMN IF NOT EXISTS run_page_config JSONB NOT NULL
            DEFAULT '{"presentation_mode": "simple"}'::jsonb
        """,
    )
    logger.info("Workflow run_page_config migration complete")


async def init_embed_config():
    """Add embed_config field to agents and workflows tables."""
    logger.info("Initializing embed_config fields...")

    conn = Tortoise.get_connection("default")

    for table_name in ("agents", "workflows"):
        _, tables = await conn.execute_query(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_name = $1 AND table_schema = 'public'
            """,
            [table_name],
        )

        if not tables:
            logger.info(f"{table_name} table does not exist yet, skipping migration")
            continue

        _, rows = await conn.execute_query(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = $1 AND column_name = 'embed_config'
            """,
            [table_name],
        )

        if rows:
            logger.info(f"embed_config field already exists in {table_name}, skipping")
            continue

        logger.info(f"Adding embed_config field to {table_name} table...")
        await conn.execute_query(f"""
            ALTER TABLE {table_name}
            ADD COLUMN IF NOT EXISTS embed_config JSONB NOT NULL DEFAULT '{{}}'::jsonb
        """)
        logger.info(f"embed_config field added to {table_name} successfully")

    logger.info("Embed config migration complete")


async def drop_model_provider_uniqueness():
    """Drop legacy unique constraints on models(provider, model_id[, model_type]).

    The same provider/model_id may be configured multiple times (e.g., different
    API keys or base URLs). Model identity is carried by the primary-key UUID,
    not the provider/model_id pair.
    """
    logger.info("Dropping legacy model provider uniqueness constraints...")

    conn = Tortoise.get_connection("default")

    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'models' AND table_schema = 'public'
    """)

    if not tables:
        logger.info("models table does not exist yet, skipping constraint migration")
        return

    await conn.execute_query("""
        DO $$
        DECLARE constraint_name text;
        BEGIN
            FOR constraint_name IN
                SELECT c.conname
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE t.relname = 'models'
                  AND n.nspname = 'public'
                  AND c.contype = 'u'
                  AND (
                      pg_get_constraintdef(c.oid) = 'UNIQUE (provider, model_id)'
                      OR pg_get_constraintdef(c.oid) =
                          'UNIQUE (provider, model_id, model_type)'
                  )
            LOOP
                EXECUTE format(
                    'ALTER TABLE models DROP CONSTRAINT %I',
                    constraint_name
                );
            END LOOP;
        END $$;
    """)

    logger.info("Model provider uniqueness constraints dropped")


async def init_model_provider_display_name() -> None:
    """Add the optional display-only provider name to existing model tables."""
    logger.info("Adding provider display name field to models table...")

    conn = Tortoise.get_connection("default")
    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'models' AND table_schema = 'public'
    """)
    if not tables:
        logger.info("models table does not exist yet, skipping provider display name")
        return

    await conn.execute_query("""
        ALTER TABLE models
        ADD COLUMN IF NOT EXISTS provider_display_name VARCHAR(100)
    """)
    logger.info("Provider display name field is ready")


async def revert_channel_id_to_model_id():
    """Rename models.channel_id back to models.model_id if needed.

    A previous migration incorrectly renamed the column; this reverses it
    so the ORM model definition (which uses ``model_id``) matches the schema.
    """
    logger.info("Checking for models.channel_id to revert...")

    conn = Tortoise.get_connection("default")

    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'models' AND table_schema = 'public'
    """)

    if not tables:
        logger.info("models table does not exist yet, skipping revert")
        return

    _, channel_col = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'models'
          AND column_name = 'channel_id'
          AND table_schema = 'public'
    """)

    if not channel_col:
        logger.info("models.channel_id not found, no revert needed")
        return

    await conn.execute_query("ALTER TABLE models RENAME COLUMN channel_id TO model_id")
    logger.info("models.channel_id renamed back to model_id")


async def init_kb_rerank_fields():
    """Add rerank model support fields to knowledge_bases table."""
    logger.info("Initializing knowledge base rerank fields...")

    conn = Tortoise.get_connection("default")

    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'knowledge_bases' AND table_schema = 'public'
    """)

    if not tables:
        logger.info("knowledge_bases table does not exist yet, skipping migration")
        return

    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'knowledge_bases' AND column_name = 'rerank_model_id'
    """)

    if rows:
        logger.info("rerank_model_id field already exists, skipping")
        return

    await conn.execute_query("""
        ALTER TABLE knowledge_bases
        ADD COLUMN IF NOT EXISTS rerank_model_id UUID NULL
    """)

    logger.info("Knowledge base rerank fields migration complete")


async def init_clouisle_import_sessions_table():
    """Create short-lived Clouisle package import sessions table."""
    logger.info("Initializing Clouisle import sessions table...")

    conn = Tortoise.get_connection("default")

    _, rows = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'clouisle_import_sessions'
    """)

    if rows:
        await conn.execute_query("""
            ALTER TABLE clouisle_import_sessions
            ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'platform'
        """)
        await conn.execute_query("""
            CREATE INDEX IF NOT EXISTS idx_clouisle_import_sessions_source_status
            ON clouisle_import_sessions(source, status)
        """)
        logger.info("Clouisle import sessions table already exists, ensured columns")
        return

    await conn.execute_query("""
        CREATE TABLE IF NOT EXISTS clouisle_import_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            resource_type VARCHAR(50) NOT NULL,
            resource_name VARCHAR(255) NOT NULL,
            package_id UUID NOT NULL,
            source VARCHAR(20) NOT NULL DEFAULT 'platform',
            status VARCHAR(20) NOT NULL DEFAULT 'previewed',
            manifest JSONB NOT NULL DEFAULT '{}',
            resource_payload JSONB NOT NULL DEFAULT '{}',
            preview JSONB NOT NULL DEFAULT '{}',
            temp_storage_path VARCHAR(1000),
            package_checksum VARCHAR(128),
            expires_at TIMESTAMPTZ NOT NULL,
            created_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_clouisle_import_sessions_team_status
        ON clouisle_import_sessions(team_id, status)
    """)
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_clouisle_import_sessions_source_status
        ON clouisle_import_sessions(source, status)
    """)
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_clouisle_import_sessions_expires_at
        ON clouisle_import_sessions(expires_at)
    """)

    logger.info("Clouisle import sessions table initialization complete")


async def drop_obsolete_retrieval_evaluation_tables():
    """Remove the retired persistent retrieval evaluation schema."""
    conn = Tortoise.get_connection("default")
    await execute_startup_migration_query(
        conn,
        """
        DO $$
        BEGIN
            ALTER TABLE IF EXISTS evaluation_runs
                DROP COLUMN IF EXISTS sweep_id;
            ALTER TABLE IF EXISTS evaluation_sweeps
                DROP COLUMN IF EXISTS best_run_id,
                DROP COLUMN IF EXISTS verification_run_id;

            DROP TABLE IF EXISTS evaluation_case_results;
            DROP TABLE IF EXISTS evaluation_sweeps;
            DROP TABLE IF EXISTS evaluation_runs;
            DROP TABLE IF EXISTS evaluation_cases;
            DROP TABLE IF EXISTS evaluation_datasets;
        END $$
        """,
    )


async def init_db():
    """
    Initialize database with default permissions and roles.
    The first registered user will be promoted to Super Admin automatically.
    """
    # IMPORTANT: Run schema migrations FIRST, before other initializations
    # This ensures columns exist before Tortoise validates the schema
    try:
        await init_user_locale_field()
    except Exception as e:
        logger.warning(f"User locale migration failed (may be first run): {e}")

    try:
        await init_agent_attachment_fields()
    except Exception as e:
        logger.warning(f"Agent attachment migration failed (may be first run): {e}")

    try:
        await init_agent_tools_credentials()
    except Exception as e:
        logger.warning(
            f"Agent tools_credentials migration failed (may be first run): {e}"
        )

    try:
        await init_agent_powered_by_text()
    except Exception as e:
        logger.warning(
            f"Agent powered_by_text migration failed (may be first run): {e}"
        )

    try:
        await init_message_history_index()
    except Exception as e:
        logger.warning(
            f"Message history index migration failed (may be first run): {e}"
        )

    try:
        await init_permission_is_system_field()
    except Exception as e:
        logger.warning(f"Permission is_system migration failed (may be first run): {e}")

    try:
        await drop_model_provider_uniqueness()
    except Exception as e:
        logger.warning(
            f"Model provider uniqueness migration failed (may be first run): {e}"
        )

    await init_model_provider_display_name()

    try:
        await init_kb_rerank_fields()
    except Exception as e:
        logger.warning(f"KB rerank migration failed (may be first run): {e}")

    try:
        await init_clouisle_import_sessions_table()
    except Exception as e:
        logger.warning(
            f"Clouisle import sessions migration failed (may be first run): {e}"
        )

    try:
        await drop_obsolete_retrieval_evaluation_tables()
    except Exception as e:
        logger.warning(f"Retrieval evaluation cleanup failed (may be first run): {e}")

    # 1. Initialize Permissions
    logger.info("Initializing permissions from SystemPermissions...")
    permissions_data = SystemPermissions.get_all_definitions()

    logger.info("Initializing permissions...")
    for perm_data in permissions_data:
        await Permission.get_or_create(
            code=perm_data["code"],
            defaults={
                "scope": perm_data["scope"],
                "description": perm_data["description"],
                "is_system": True,
            },
        )

    # 2. Initialize System Roles
    logger.info("Initializing roles...")

    # Super Admin - has all permissions
    super_admin_role, created = await Role.get_or_create(
        name=SUPER_ADMIN_ROLE,
        defaults={
            "description": "Full system control with all permissions",
            "is_system_role": True,
        },
    )
    if created:
        all_perm = await Permission.get(code="*")
        await super_admin_role.permissions.add(all_perm)
        logger.info(f"Created system role: {SUPER_ADMIN_ROLE}")

    admin_permissions = [
        # Admin permissions (system-wide)
        "admin:dashboard:access",
        "admin:user:read",
        "admin:user:create",
        "admin:user:update",
        "admin:user:delete",
        "admin:role:read",
        "admin:permission:read",
        "admin:team:read",
        "admin:team:create",
        "admin:team:update",
        "admin:team:delete",
        "admin:model:read",
        "admin:model:create",
        "admin:model:update",
        "admin:model:delete",
        "admin:capability:read",
        "admin:capability:create",
        "admin:capability:update",
        "admin:capability:delete",
        "admin:capability:execute",
        "admin:app:read",
        "admin:app:create",
        "admin:app:update",
        "admin:app:delete",
        "admin:app:publish",
        "admin:app:duplicate",
        "admin:knowledge-base:read",
        "admin:knowledge-base:test",
        "admin:knowledge-base:create",
        "admin:knowledge-base:update",
        "admin:knowledge-base:delete",
        "admin:settings:read",
        "admin:sso:read",
        "audit:read",
        "audit:export",
        "admin:conversation:read",
        "admin:conversation:delete",
        "admin:notification:create",
        "admin:notification:delete",
        "admin:memory:read",
        # Platform permissions (team-scoped)
        "team:read",
        "team:create",
        "team:update",
        "team:delete",
        "team:manage",
        "agent:read",
        "agent:create",
        "agent:update",
        "agent:delete",
        "agent:publish",
        "agent:chat",
        "workflow:read",
        "workflow:create",
        "workflow:update",
        "workflow:delete",
        "workflow:publish",
        "workflow:run",
        "workflow:execute",
        "kb:read",
        "kb:test",
        "kb:create",
        "kb:update",
        "kb:delete",
        "tool:read",
        "tool:create",
        "tool:update",
        "tool:delete",
        "tool:execute",
        "skill:read",
        "skill:create",
        "skill:update",
        "skill:delete",
        "skill:execute",
        "apikey:read",
        "apikey:create",
        "apikey:update",
        "apikey:delete",
        "conversation:read",
        "conversation:delete",
    ]

    # Admin - dashboard access with system read visibility and team-scoped resource management
    admin_role, created = await Role.get_or_create(
        name="Admin",
        defaults={
            "description": "Admin role with dashboard access, system read access, and team-scoped resource management",
            "is_system_role": True,
        },
    )
    if created:
        logger.info("Created system role: Admin")

    await sync_role_permissions(admin_role, admin_permissions, "Admin")

    member_permissions = [
        "team:read",
        "agent:read",
        "agent:create",
        "agent:update",
        "agent:chat",
        "workflow:read",
        "workflow:create",
        "workflow:update",
        "workflow:run",
        "kb:read",
        "kb:test",
        "kb:create",
        "kb:update",
        "kb:delete",
        "tool:read",
        "tool:create",
        "tool:update",
        "tool:delete",
        "tool:execute",
        "skill:read",
        "skill:create",
        "skill:update",
        "skill:delete",
        "skill:execute",
        "apikey:read",
        "apikey:create",
        "apikey:update",
        "apikey:delete",
        "conversation:read",
        "conversation:delete",
    ]

    # Member - collaborative contributor role without dashboard access
    member_role, created = await Role.get_or_create(
        name="Member",
        defaults={
            "description": "Collaborative member role for daily resource creation and editing without dashboard access",
            "is_system_role": True,
        },
    )
    if created:
        logger.info("Created system role: Member")

    await sync_role_permissions(member_role, member_permissions, "Member")

    viewer_permissions = [
        "team:read",
        "agent:read",
        "agent:chat",
        "workflow:read",
        "workflow:run",
        "kb:read",
        "kb:test",
        "tool:read",
        "tool:execute",
        "skill:read",
        "skill:execute",
        "conversation:read",
    ]

    # Viewer - default read-only role with execute permissions
    viewer_role, created = await Role.get_or_create(
        name="Viewer",
        defaults={
            "description": "Default read-only role with execute permissions",
            "is_system_role": True,
        },
    )
    if created:
        logger.info("Created system role: Viewer")

    await sync_role_permissions(viewer_role, viewer_permissions, "Viewer")

    try:
        await init_scoped_role_assignments_table()
    except Exception:
        logger.exception("Scoped role assignment migration failed")
        raise

    # 3. Initialize Site Settings
    logger.info("Initializing site settings...")
    await init_model_endpoint_allowlist()
    await init_default_settings()
    await migrate_auto_notification_types()

    # 3.0. Set default_role_id to Viewer if not yet configured
    from app.models.site_setting import SiteSetting

    current_default_role_id = await SiteSetting.get_value("default_role_id", "")
    if not current_default_role_id:
        await SiteSetting.set_value(
            key="default_role_id",
            value=str(viewer_role.id),
            value_type="string",
            category="security",
            description="Default role ID for new users",
            is_public=False,
        )
        logger.info(f"Set default_role_id to Viewer role: {viewer_role.id}")

    # 3.1. Migrate registration settings category
    await migrate_registration_settings_category()

    # 3.2. Migrate storage settings category
    await migrate_storage_settings_category()

    # 4. Initialize workflow tables
    await init_workflow_tables()
    await init_observability_indexes()

    # 5. Initialize notification tables
    await init_notification_tables()

    # 6. Initialize agent tools_credentials field
    await init_agent_tools_credentials()

    # 7. Initialize tool_shares table
    await init_tool_shares_table()

    # 7.1. Initialize skills table
    await init_skills_table()

    # 8. Fix CASCADE delete policies
    await fix_cascade_delete_policies()

    # 9. Initialize SSO tables
    await init_sso_tables()

    # 10. Initialize memory tables
    await init_memory_tables()

    # 11. Initialize agent hide_tool_calls field
    await init_agent_hide_tool_calls_field()

    # 11.1 Initialize agent hide_message_actions and hide_reasoning fields
    await init_agent_hide_message_actions_reasoning_fields()

    # 12. Initialize agent memory fields
    await init_agent_memory_fields()

    # 13. Initialize agent media generation fields
    await init_agent_media_generation_fields()

    logger.info("Database initialization complete.")
