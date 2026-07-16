"""add hnsw index on protocol_chunks embedding

Revision ID: a1b2c3d4e5f6
Revises: 26eaf0620136
Create Date: 2026-06-10

"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "26eaf0620136"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # HNSW requires a fixed-dimension vector column. Legacy schema used bare `vector`.
    op.execute(
        """
        DO $$
        DECLARE
            col_type text;
        BEGIN
            SELECT format_type(a.atttypid, a.atttypmod)
            INTO col_type
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            WHERE c.relname = 'protocol_chunks'
              AND a.attname = 'embedding'
              AND NOT a.attisdropped;

            IF col_type IS NOT NULL AND col_type NOT LIKE 'vector(1536)%' THEN
                ALTER TABLE protocol_chunks
                ALTER COLUMN embedding TYPE vector(1536)
                USING embedding::vector(1536);
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS protocol_chunks_embedding_hnsw_idx
        ON protocol_chunks
        USING hnsw (embedding vector_l2_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS protocol_chunks_embedding_hnsw_idx")
