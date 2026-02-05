"""
Migration script to add new Message fields: images, file_urls, reasoning_content

Run this script manually if Tortoise ORM doesn't auto-create the columns.
Usage:
  cd backend
  python -m app.scripts.migrate_message_fields

Or execute the SQL directly in PostgreSQL:
  ALTER TABLE messages ADD COLUMN IF NOT EXISTS images JSONB;
  ALTER TABLE messages ADD COLUMN IF NOT EXISTS file_urls JSONB;
  ALTER TABLE messages ADD COLUMN IF NOT EXISTS reasoning_content TEXT;
"""

import asyncio
import asyncpg


async def migrate():
    from app.core.config import settings

    # Build connection string
    dsn = (
        f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )

    print("Connecting to database...")
    conn = await asyncpg.connect(dsn)

    try:
        # Check if columns exist
        columns = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'messages'
        """)
        existing_columns = {row["column_name"] for row in columns}

        # Add images column if not exists
        if "images" not in existing_columns:
            print("Adding 'images' column...")
            await conn.execute("ALTER TABLE messages ADD COLUMN images JSONB")
            print("  ✓ Added 'images' column")
        else:
            print("  - 'images' column already exists")

        # Add file_urls column if not exists
        if "file_urls" not in existing_columns:
            print("Adding 'file_urls' column...")
            await conn.execute("ALTER TABLE messages ADD COLUMN file_urls JSONB")
            print("  ✓ Added 'file_urls' column")
        else:
            print("  - 'file_urls' column already exists")

        # Add reasoning_content column if not exists
        if "reasoning_content" not in existing_columns:
            print("Adding 'reasoning_content' column...")
            await conn.execute("ALTER TABLE messages ADD COLUMN reasoning_content TEXT")
            print("  ✓ Added 'reasoning_content' column")
        else:
            print("  - 'reasoning_content' column already exists")

        print("\nMigration completed successfully!")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
