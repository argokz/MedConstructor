"""assignment created by

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-18

"""
from typing import Sequence, Union

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS assignments ADD COLUMN IF NOT EXISTS created_by_id INTEGER NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_assignments_created_by_id ON assignments (created_by_id)")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_assignments_created_by_id_users'
            ) THEN
                ALTER TABLE assignments
                ADD CONSTRAINT fk_assignments_created_by_id_users
                FOREIGN KEY (created_by_id) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS assignments DROP CONSTRAINT IF EXISTS fk_assignments_created_by_id_users")
    op.execute("DROP INDEX IF EXISTS ix_assignments_created_by_id")
    op.execute("ALTER TABLE IF EXISTS assignments DROP COLUMN IF EXISTS created_by_id")
