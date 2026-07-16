import asyncio
import os
import sys

# Add backend dir to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import engine, Base
from app.models import *

async def reset_db():
    print("Connecting to database to reset schema...")
    async with engine.begin() as conn:
        # Drop schema public cascade and recreate
        await conn.execute(text("DROP SCHEMA public CASCADE;"))
        await conn.execute(text("CREATE SCHEMA public;"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO postgres;"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))
        print("Schema public dropped and recreated.")

        # Check if vector extension exists
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        print("Vector extension ensured.")
        
        # Create all tables from Base
        await conn.run_sync(Base.metadata.create_all)
        print("All tables created successfully.")

if __name__ == "__main__":
    asyncio.run(reset_db())
