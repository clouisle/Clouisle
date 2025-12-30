"""
Migration script for dynamic embedding dimensions.

This script:
1. Adds embedding_dimension column to knowledge_bases table if missing
2. Detects existing embedding column and migrates data to dimension-specific columns
3. Sets embedding_dimension for existing knowledge bases based on their data

Run this script after updating the code to support dynamic dimensions.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tortoise import Tortoise

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """Run the migration."""
    from app.core.config import settings
    
    # Initialize Tortoise ORM
    await Tortoise.init(
        db_url=settings.DATABASE_URL,
        modules={"models": ["app.models"]},
    )
    
    conn = Tortoise.get_connection("default")
    
    logger.info("Starting embedding migration...")
    
    # 1. Add embedding_dimension column to knowledge_bases if not exists
    logger.info("Step 1: Adding embedding_dimension column to knowledge_bases...")
    _, rows = await conn.execute_query("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'knowledge_bases' AND column_name = 'embedding_dimension'
    """)
    
    if not rows:
        await conn.execute_query("""
            ALTER TABLE knowledge_bases 
            ADD COLUMN embedding_dimension INTEGER
        """)
        logger.info("Added embedding_dimension column to knowledge_bases")
    else:
        logger.info("embedding_dimension column already exists")
    
    # 2. Check if old 'embedding' column exists and determine its dimension
    logger.info("Step 2: Checking for existing embedding column...")
    _, rows = await conn.execute_query("""
        SELECT column_name, udt_name 
        FROM information_schema.columns 
        WHERE table_name = 'document_chunks' AND column_name = 'embedding'
    """)
    
    old_column_exists = bool(rows)
    detected_dimension = None
    
    if old_column_exists:
        logger.info("Found old 'embedding' column")
        
        # Try to detect dimension from existing data
        try:
            _, dim_rows = await conn.execute_query("""
                SELECT vector_dims(embedding) as dim 
                FROM document_chunks 
                WHERE embedding IS NOT NULL 
                LIMIT 1
            """)
            if dim_rows and dim_rows[0].get("dim"):
                detected_dimension = dim_rows[0]["dim"]
                logger.info(f"Detected embedding dimension: {detected_dimension}")
        except Exception as e:
            logger.warning(f"Could not detect dimension: {e}")
    
    # 3. If we have a dimension, create the new column and migrate data
    if detected_dimension and old_column_exists:
        new_col_name = f"embedding_{detected_dimension}"
        
        logger.info(f"Step 3: Migrating to {new_col_name} column...")
        
        # Check if new column exists
        _, col_rows = await conn.execute_query(f"""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'document_chunks' AND column_name = '{new_col_name}'
        """)
        
        if not col_rows:
            # Create new column
            await conn.execute_query(f"""
                ALTER TABLE document_chunks 
                ADD COLUMN {new_col_name} vector({detected_dimension})
            """)
            logger.info(f"Created {new_col_name} column")
        
        # Copy data from old column to new column
        await conn.execute_query(f"""
            UPDATE document_chunks 
            SET {new_col_name} = embedding 
            WHERE embedding IS NOT NULL AND {new_col_name} IS NULL
        """)
        logger.info(f"Copied embeddings to {new_col_name}")
        
        # Create HNSW index (only if dimension <= 2000, pgvector limit)
        HNSW_MAX_DIMENSION = 2000
        if detected_dimension <= HNSW_MAX_DIMENSION:
            index_name = f"document_chunks_{new_col_name}_hnsw_idx"
            try:
                await conn.execute_query(f"""
                    CREATE INDEX IF NOT EXISTS {index_name}
                    ON document_chunks 
                    USING hnsw ({new_col_name} vector_cosine_ops)
                """)
                logger.info(f"Created HNSW index: {index_name}")
            except Exception as e:
                logger.warning(f"Could not create index: {e}")
        else:
            logger.info(f"Skipping HNSW index for {new_col_name} (dimension {detected_dimension} > {HNSW_MAX_DIMENSION})")
        
        # 4. Update knowledge_bases with the detected dimension
        logger.info("Step 4: Setting embedding_dimension for existing knowledge bases...")
        
        # Get all KBs that have chunks with embeddings
        _, kb_rows = await conn.execute_query(f"""
            SELECT DISTINCT kb.id
            FROM knowledge_bases kb
            JOIN documents d ON d.knowledge_base_id = kb.id
            JOIN document_chunks dc ON dc.document_id = d.id
            WHERE dc.{new_col_name} IS NOT NULL
        """)
        
        for kb_row in kb_rows:
            kb_id = kb_row["id"]
            await conn.execute_query(f"""
                UPDATE knowledge_bases 
                SET embedding_dimension = {detected_dimension}
                WHERE id = $1 AND embedding_dimension IS NULL
            """, [str(kb_id)])
            logger.info(f"Set embedding_dimension={detected_dimension} for KB {kb_id}")
        
        logger.info(f"Updated {len(kb_rows)} knowledge bases")
    else:
        logger.info("No existing embeddings to migrate")
    
    # 5. Summary
    logger.info("\n=== Migration Summary ===")
    
    # Count chunks with embeddings in each dimension column
    _, dim_cols = await conn.execute_query("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'document_chunks' 
        AND column_name LIKE 'embedding_%'
    """)
    
    for col_row in dim_cols:
        col_name = col_row["column_name"]
        _, count_rows = await conn.execute_query(f"""
            SELECT COUNT(*) as cnt FROM document_chunks WHERE {col_name} IS NOT NULL
        """)
        count = count_rows[0]["cnt"] if count_rows else 0
        logger.info(f"  {col_name}: {count} chunks with embeddings")
    
    # Count KBs by dimension
    _, kb_dim_rows = await conn.execute_query("""
        SELECT embedding_dimension, COUNT(*) as cnt 
        FROM knowledge_bases 
        GROUP BY embedding_dimension
    """)
    
    logger.info("\nKnowledge bases by dimension:")
    for row in kb_dim_rows:
        dim = row["embedding_dimension"]
        cnt = row["cnt"]
        logger.info(f"  dimension={dim}: {cnt} knowledge bases")
    
    logger.info("\nMigration completed!")
    
    await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(migrate())
