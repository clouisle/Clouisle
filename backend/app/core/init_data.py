import logging

from tortoise import Tortoise

from app.models.user import Role, Permission
from app.models.site_setting import init_default_settings

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
        logger.info("Agents table does not exist yet, skipping tools_credentials migration")
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
        result = await conn.execute_query("""
            UPDATE agents
            SET tools_credentials = '{}'::jsonb
            WHERE tools_credentials IS NULL
        """)
        logger.info("Updated existing agents with default tools_credentials")
    except Exception as e:
        logger.warning(f"Could not update existing agents: {e}")

    logger.info("Agent tools_credentials migration complete")


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
        logger.info(f"Migrated {migrated_count} registration settings to 'security' category")
    else:
        logger.info("Registration settings already in correct category")


async def init_db():
    """
    Initialize database with default permissions and roles.
    The first registered user will be promoted to Super Admin automatically.
    """
    # IMPORTANT: Run agent tools_credentials migration FIRST, before other initializations
    # This ensures the column exists before Tortoise validates the schema
    try:
        await init_agent_tools_credentials()
    except Exception as e:
        logger.warning(f"Agent tools_credentials migration failed (may be first run): {e}")

    # 1. Initialize Permissions
    permissions_data = [
        # User permissions
        {"code": "user:read", "scope": "user", "description": "Read users"},
        {"code": "user:create", "scope": "user", "description": "Create users"},
        {"code": "user:update", "scope": "user", "description": "Update users"},
        {"code": "user:delete", "scope": "user", "description": "Delete users"},
        {
            "code": "user:manage",
            "scope": "user",
            "description": "Manage users, roles, permissions",
        },
        # Role permissions
        {"code": "role:read", "scope": "role", "description": "Read roles"},
        {"code": "role:create", "scope": "role", "description": "Create roles"},
        {"code": "role:update", "scope": "role", "description": "Update roles"},
        {"code": "role:delete", "scope": "role", "description": "Delete roles"},
        # Permission permissions
        {
            "code": "permission:read",
            "scope": "permission",
            "description": "Read permissions",
        },
        {
            "code": "permission:create",
            "scope": "permission",
            "description": "Create permissions",
        },
        {
            "code": "permission:update",
            "scope": "permission",
            "description": "Update permissions",
        },
        {
            "code": "permission:delete",
            "scope": "permission",
            "description": "Delete permissions",
        },
        # Team permissions
        {"code": "team:read", "scope": "team", "description": "Read teams"},
        {"code": "team:create", "scope": "team", "description": "Create teams"},
        {"code": "team:update", "scope": "team", "description": "Update teams"},
        {"code": "team:delete", "scope": "team", "description": "Delete teams"},
        {"code": "team:manage", "scope": "team", "description": "Manage team members"},
        # Site settings permissions
        {
            "code": "settings:read",
            "scope": "settings",
            "description": "Read site settings",
        },
        {
            "code": "settings:update",
            "scope": "settings",
            "description": "Update site settings",
        },
        # Model permissions
        {
            "code": "model:read",
            "scope": "model",
            "description": "Read model configurations",
        },
        {
            "code": "model:create",
            "scope": "model",
            "description": "Create model configurations",
        },
        {
            "code": "model:update",
            "scope": "model",
            "description": "Update model configurations",
        },
        {
            "code": "model:delete",
            "scope": "model",
            "description": "Delete model configurations",
        },
        # Agent permissions
        {
            "code": "agent:read",
            "scope": "agent",
            "description": "Read agents",
        },
        {
            "code": "agent:create",
            "scope": "agent",
            "description": "Create agents",
        },
        {
            "code": "agent:update",
            "scope": "agent",
            "description": "Update agents",
        },
        {
            "code": "agent:delete",
            "scope": "agent",
            "description": "Delete agents",
        },
        {
            "code": "agent:publish",
            "scope": "agent",
            "description": "Publish/unpublish agents",
        },
        {
            "code": "agent:chat",
            "scope": "agent",
            "description": "Chat with agents",
        },
        # System wildcard permission
        {"code": "*", "scope": "system", "description": "All permissions (superuser)"},
    ]

    logger.info("Initializing permissions...")
    for perm_data in permissions_data:
        await Permission.get_or_create(
            code=perm_data["code"],
            defaults={
                "scope": perm_data["scope"],
                "description": perm_data["description"],
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

    # Viewer - read-only access
    viewer_role, created = await Role.get_or_create(
        name="Viewer",
        defaults={"description": "Read-only access", "is_system_role": True},
    )
    if created:
        read_perm = await Permission.get(code="user:read")
        await viewer_role.permissions.add(read_perm)
        logger.info("Created system role: Viewer")

    # 3. Initialize Site Settings
    logger.info("Initializing site settings...")
    await init_default_settings()

    # 3.1. Migrate registration settings category
    await migrate_registration_settings_category()

    # 4. Initialize workflow tables
    await init_workflow_tables()

    # 5. Initialize agent tools_credentials field
    await init_agent_tools_credentials()

    # 6. Initialize tool_shares table
    await init_tool_shares_table()

    # 7. Fix CASCADE delete policies
    await fix_cascade_delete_policies()

    logger.info("Database initialization complete.")
