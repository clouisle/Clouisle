import logging

from tortoise import Tortoise

from app.models.user import Role, Permission
from app.models.site_setting import init_default_settings
from app.core.permissions import SystemPermissions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# System role name constant
SUPER_ADMIN_ROLE = "Super Admin"


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
    await conn.execute_query("""
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
    """)
    logger.info("Created workflow indexes")

    logger.info("Workflow tables initialization complete")


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
            await conn.execute_query("""
                ALTER TABLE agents
                ADD COLUMN tools_credentials JSONB NOT NULL DEFAULT '{}'::jsonb
            """)
            logger.info("Added tools_credentials column to agents table")
        except Exception as e:
            logger.error(f"Could not add tools_credentials column: {e}")
            raise
    else:
        logger.info("tools_credentials column already exists")

    # Update existing agents with NULL tools_credentials (shouldn't happen with DEFAULT, but just in case)
    try:
        await conn.execute_query("""
            UPDATE agents
            SET tools_credentials = '{}'::jsonb
            WHERE tools_credentials IS NULL
        """)
        logger.info("Updated existing agents with default tools_credentials")
    except Exception as e:
        logger.warning(f"Could not update existing agents: {e}")

    logger.info("Agent tools_credentials migration complete")


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
            await conn.execute_query("""
                ALTER TABLE agents
                ADD COLUMN streaming_config JSONB NOT NULL DEFAULT '{}'::jsonb
            """)
            logger.info("Added streaming_config column to agents table")
        except Exception as e:
            logger.error(f"Could not add streaming_config column: {e}")
            raise
    else:
        logger.info("streaming_config column already exists")

    logger.info("Agent streaming_config migration complete")


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


async def init_agent_user_input_request():
    """
    Add enable_user_input_request field to agents table if it doesn't exist.
    This handles the migration for the user input request feature.
    Must be called BEFORE Tortoise.generate_schemas() to avoid schema mismatch.
    """
    logger.info("Checking agent enable_user_input_request field...")

    conn = Tortoise.get_connection("default")

    # Check if agents table exists first
    _, tables = await conn.execute_query("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name = 'agents' AND table_schema = 'public'
    """)

    if not tables:
        logger.info(
            "Agents table does not exist yet, skipping enable_user_input_request migration"
        )
        return

    # Check if enable_user_input_request column exists
    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'agents' AND column_name = 'enable_user_input_request'
    """)

    if not rows:
        logger.info("Adding enable_user_input_request column to agents table...")
        try:
            await conn.execute_query("""
                ALTER TABLE agents
                ADD COLUMN enable_user_input_request BOOLEAN NOT NULL DEFAULT FALSE
            """)
            logger.info("Added enable_user_input_request column to agents table")
        except Exception as e:
            logger.error(f"Could not add enable_user_input_request column: {e}")
            raise
    else:
        logger.info("enable_user_input_request column already exists")

    logger.info("Agent enable_user_input_request migration complete")


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
    await conn.execute_query("""
        CREATE INDEX IF NOT EXISTS idx_tool_shares_tool_id ON tool_shares(tool_id);
        CREATE INDEX IF NOT EXISTS idx_tool_shares_team_id ON tool_shares(shared_with_team_id);
        CREATE INDEX IF NOT EXISTS idx_tool_shares_shared_by ON tool_shares(shared_by_id);
    """)
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

        await conn.execute_query("""
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
        """)

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

        await conn.execute_query("""
            CREATE INDEX IF NOT EXISTS idx_notification_deliveries_notification_channel
                ON notification_deliveries(notification_id, channel);
            CREATE INDEX IF NOT EXISTS idx_notification_deliveries_status_created
                ON notification_deliveries(status, created_at);
        """)

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
    await conn.execute_query("""
        ALTER TABLE agents
        ADD COLUMN IF NOT EXISTS enable_memory BOOLEAN NOT NULL DEFAULT FALSE
    """)

    # Add memory_config field
    await conn.execute_query("""
        ALTER TABLE agents
        ADD COLUMN IF NOT EXISTS memory_config JSONB NOT NULL DEFAULT '{}'
    """)

    logger.info("Agent memory fields added successfully")


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
        logger.info("Users table does not exist yet, skipping password expiration migration")
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
        await init_agent_tools_credentials()
    except Exception as e:
        logger.warning(
            f"Agent tools_credentials migration failed (may be first run): {e}"
        )

    try:
        await init_permission_is_system_field()
    except Exception as e:
        logger.warning(
            f"Permission is_system migration failed (may be first run): {e}"
        )

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

    # Admin - can access dashboard and manage users/models, but data is team-isolated
    admin_role, created = await Role.get_or_create(
        name="Admin",
        defaults={
            "description": "Admin role with dashboard access and user/model management",
            "is_system_role": True,
        },
    )
    if created:
        admin_permissions = [
            # Admin permissions (system-wide)
            "admin:dashboard:access",
            "admin:user:read",
            "admin:user:create",
            "admin:user:update",
            "admin:user:delete",
            "admin:role:read",
            "admin:role:create",
            "admin:role:update",
            "admin:role:delete",
            "admin:permission:read",
            "admin:permission:create",
            "admin:permission:update",
            "admin:permission:delete",
            "admin:team:read",
            "admin:team:create",
            "admin:team:update",
            "admin:team:delete",
            "admin:model:read",
            "admin:model:create",
            "admin:model:update",
            "admin:model:delete",
            "admin:settings:read",
            "admin:settings:update",
            "admin:audit:read",
            "admin:audit:export",
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
            "kb:read",
            "kb:create",
            "kb:update",
            "kb:delete",
            "tool:read",
            "tool:create",
            "tool:update",
            "tool:delete",
            "tool:execute",
            "apikey:read",
            "apikey:create",
            "apikey:update",
            "apikey:delete",
            "conversation:read",
            "conversation:delete",
        ]
        for perm_code in admin_permissions:
            perm = await Permission.filter(code=perm_code).first()
            if perm:
                await admin_role.permissions.add(perm)
        logger.info("Created system role: Admin")
    else:
        # Ensure existing Admin role has all required permissions
        admin_permissions = [
            # Admin permissions (system-wide)
            "admin:dashboard:access",
            "admin:user:read",
            "admin:user:create",
            "admin:user:update",
            "admin:user:delete",
            "admin:role:read",
            "admin:role:create",
            "admin:role:update",
            "admin:role:delete",
            "admin:permission:read",
            "admin:permission:create",
            "admin:permission:update",
            "admin:permission:delete",
            "admin:team:read",
            "admin:team:create",
            "admin:team:update",
            "admin:team:delete",
            "admin:model:read",
            "admin:model:create",
            "admin:model:update",
            "admin:model:delete",
            "admin:settings:read",
            "admin:settings:update",
            "admin:audit:read",
            "admin:audit:export",
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
            "kb:read",
            "kb:create",
            "kb:update",
            "kb:delete",
            "tool:read",
            "tool:create",
            "tool:update",
            "tool:delete",
            "tool:execute",
            "apikey:read",
            "apikey:create",
            "apikey:update",
            "apikey:delete",
            "conversation:read",
            "conversation:delete",
        ]
        for perm_code in admin_permissions:
            perm = await Permission.filter(code=perm_code).first()
            if perm:
                existing = await admin_role.permissions.filter(id=perm.id).exists()
                if not existing:
                    await admin_role.permissions.add(perm)
                    logger.info(f"Added permission {perm_code} to Admin role")

    # Member - default role for regular users with full resource access (no dashboard access)
    member_role, created = await Role.get_or_create(
        name="Member",
        defaults={
            "description": "Default role with full access to teams, agents, workflows, knowledge bases, and tools",
            "is_system_role": True,
        },
    )
    if created:
        # Add all resource permissions for Member role (no dashboard access, no team:delete)
        member_permissions = [
            # Team permissions (no team:delete)
            "team:read",
            "team:create",
            "team:update",
            "team:manage",
            # Agent permissions
            "agent:read",
            "agent:create",
            "agent:update",
            "agent:delete",
            "agent:publish",
            "agent:chat",
            # Workflow permissions
            "workflow:read",
            "workflow:create",
            "workflow:update",
            "workflow:delete",
            "workflow:publish",
            "workflow:run",
            # Knowledge Base permissions
            "kb:read",
            "kb:create",
            "kb:update",
            "kb:delete",
            # Tool permissions
            "tool:read",
            "tool:create",
            "tool:update",
            "tool:delete",
            "tool:execute",
            # API Key permissions (own keys)
            "apikey:read",
            "apikey:create",
            "apikey:update",
            "apikey:delete",
            # Conversation permissions
            "conversation:read",
            "conversation:delete",
        ]
        for perm_code in member_permissions:
            perm = await Permission.filter(code=perm_code).first()
            if perm:
                await member_role.permissions.add(perm)
        logger.info("Created system role: Member")
    else:
        # Ensure existing Member role has correct permissions (remove team:delete if present)
        member_permissions = [
            "team:read",
            "team:create",
            "team:update",
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
            "kb:read",
            "kb:create",
            "kb:update",
            "kb:delete",
            "tool:read",
            "tool:create",
            "tool:update",
            "tool:delete",
            "tool:execute",
            "apikey:read",
            "apikey:create",
            "apikey:update",
            "apikey:delete",
            "conversation:read",
            "conversation:delete",
        ]
        for perm_code in member_permissions:
            perm = await Permission.filter(code=perm_code).first()
            if perm:
                existing = await member_role.permissions.filter(id=perm.id).exists()
                if not existing:
                    await member_role.permissions.add(perm)
                    logger.info(f"Added permission {perm_code} to Member role")
        # Remove team:delete from Member role if present
        team_delete_perm = await Permission.filter(code="team:delete").first()
        if team_delete_perm:
            existing = await member_role.permissions.filter(
                id=team_delete_perm.id
            ).exists()
            if existing:
                await member_role.permissions.remove(team_delete_perm)
                logger.info("Removed team:delete permission from Member role")

    # Viewer - read-only access plus execute permissions
    viewer_role, created = await Role.get_or_create(
        name="Viewer",
        defaults={
            "description": "Read-only access with execute permissions",
            "is_system_role": True,
        },
    )
    if created:
        viewer_permissions = [
            "team:read",
            "agent:read",
            "agent:chat",
            "workflow:read",
            "workflow:run",
            "kb:read",
            "tool:read",
            "tool:execute",
            "apikey:read",
            "conversation:read",
        ]
        for perm_code in viewer_permissions:
            perm = await Permission.filter(code=perm_code).first()
            if perm:
                await viewer_role.permissions.add(perm)
        logger.info("Created system role: Viewer")
    else:
        # Ensure existing Viewer role has all required permissions
        viewer_permissions = [
            "team:read",
            "agent:read",
            "agent:chat",
            "workflow:read",
            "workflow:run",
            "kb:read",
            "tool:read",
            "tool:execute",
            "apikey:read",
            "conversation:read",
        ]
        for perm_code in viewer_permissions:
            perm = await Permission.filter(code=perm_code).first()
            if perm:
                existing = await viewer_role.permissions.filter(id=perm.id).exists()
                if not existing:
                    await viewer_role.permissions.add(perm)
                    logger.info(f"Added permission {perm_code} to Viewer role")

    # 3. Initialize Site Settings
    logger.info("Initializing site settings...")
    await init_default_settings()

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

    # 5. Initialize notification tables
    await init_notification_tables()

    # 6. Initialize agent tools_credentials field
    await init_agent_tools_credentials()

    # 7. Initialize tool_shares table
    await init_tool_shares_table()

    # 8. Fix CASCADE delete policies
    await fix_cascade_delete_policies()

    # 9. Initialize SSO tables
    await init_sso_tables()

    # 10. Initialize memory tables
    await init_memory_tables()

    # 11. Initialize agent memory fields
    await init_agent_memory_fields()

    logger.info("Database initialization complete.")
