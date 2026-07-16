"""pg_trgm GIN index on clinical_protocols.title for title-candidate retrieval

Revision ID: d1f2a3b4c5e6
Revises: c9e1f2a3b4d5
Create Date: 2026-06-29 13:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d1f2a3b4c5e6"
down_revision: Union[str, None] = "c9e1f2a3b4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clinical_protocols_title_trgm "
        "ON clinical_protocols USING gin (title gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_clinical_protocols_title_trgm")
