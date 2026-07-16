"""add source-system identifier to clinical protocols

Revision ID: 2c3d4e5f6a7b
Revises: 1b2c3d4e5f6a
Create Date: 2026-07-14

"""

from typing import Sequence, Union

from alembic import op


revision: str = "2c3d4e5f6a7b"
down_revision: Union[str, None] = "1b2c3d4e5f6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE IF EXISTS clinical_protocols "
        "ADD COLUMN IF NOT EXISTS external_id VARCHAR NULL"
    )
    op.execute(
        """
        UPDATE clinical_protocols
        SET external_id = substring(split_part(url, '?', 1) FROM '/([0-9]+)$')
        WHERE external_id IS NULL
          AND split_part(url, '?', 1) ~ '/[0-9]+$'
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clinical_protocols_external_id "
        "ON clinical_protocols (external_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_clinical_protocols_external_id")
    op.execute(
        "ALTER TABLE IF EXISTS clinical_protocols "
        "DROP COLUMN IF EXISTS external_id"
    )
