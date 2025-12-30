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


async def init_db():
    """
    Initialize database with default permissions and roles.
    The first registered user will be promoted to Super Admin automatically.
    """
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

    logger.info("Database initialization complete.")
