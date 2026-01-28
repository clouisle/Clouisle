import logging

from tortoise import Tortoise

from app.models.user import Role, Permission
from app.models.site_setting import init_default_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# System role name constant
SUPER_ADMIN_ROLE = "Super Admin"


# Common embedding dimensions
EMBEDDING_DIMENSIONS = [768, 1024, 1536, 3072]


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
            workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
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


async def init_pgvector():
    """
    Initialize pgvector extension and create embedding columns for different dimensions.
    
    Supports multiple embedding dimensions to accommodate different models:
    - 768: BGE models, Silicon Flow Chinese models
    - 1024: Cohere embed-multilingual-v3.0, some BGE models
    - 1536: OpenAI text-embedding-ada-002, text-embedding-3-small
    - 3072: OpenAI text-embedding-3-large
    
    Each dimension has its own column. HNSW index is created for dimensions <= 2000
    (pgvector HNSW limit). Higher dimensions will use sequential scan.
    """
    # pgvector HNSW index maximum dimension limit
    HNSW_MAX_DIMENSION = 2000
    
    logger.info("Initializing pgvector extension...")
    
    conn = Tortoise.get_connection("default")
    
    # Enable pgvector extension
    try:
        await conn.execute_query("CREATE EXTENSION IF NOT EXISTS vector")
        logger.info("pgvector extension enabled")
    except Exception as e:
        logger.warning(f"Could not create pgvector extension (may already exist or not supported): {e}")
    
    # Create embedding columns for each supported dimension
    for dim in EMBEDDING_DIMENSIONS:
        col_name = f"embedding_{dim}"
        
        # Check if column exists
        _, rows = await conn.execute_query(f"""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'document_chunks' AND column_name = '{col_name}'
        """)
        
        if rows:
            logger.info(f"Column {col_name} already exists")
        else:
            try:
                await conn.execute_query(f"""
                    ALTER TABLE document_chunks 
                    ADD COLUMN {col_name} vector({dim})
                """)
                logger.info(f"Added {col_name} column to document_chunks table")
            except Exception as e:
                logger.warning(f"Could not add {col_name} column: {e}")
        
        # Create HNSW index for this dimension (only if <= 2000)
        if dim <= HNSW_MAX_DIMENSION:
            index_name = f"document_chunks_{col_name}_hnsw_idx"
            try:
                await conn.execute_query(f"""
                    CREATE INDEX IF NOT EXISTS {index_name}
                    ON document_chunks 
                    USING hnsw ({col_name} vector_cosine_ops)
                """)
                logger.info(f"Created HNSW index {index_name}")
            except Exception as e:
                logger.warning(f"Could not create index {index_name}: {e}")
        else:
            logger.info(f"Skipping HNSW index for {col_name} (dimension {dim} > {HNSW_MAX_DIMENSION})")


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

    # 4. Initialize pgvector for vector storage
    await init_pgvector()

    # 5. Initialize workflow tables
    await init_workflow_tables()

    # 6. Initialize agent tools_credentials field
    await init_agent_tools_credentials()

    logger.info("Database initialization complete.")
