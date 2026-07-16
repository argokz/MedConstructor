"""attempt review fields

Revision ID: d4e5f6a7b8c9
Revises: c8d9e0f1a2b3
Create Date: 2026-06-18

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS student_attempts ADD COLUMN IF NOT EXISTS review_status VARCHAR NULL")
    op.execute("ALTER TABLE IF EXISTS student_attempts ADD COLUMN IF NOT EXISTS teacher_comment TEXT NULL")
    op.execute("ALTER TABLE IF EXISTS student_attempts ADD COLUMN IF NOT EXISTS reviewed_by_id INTEGER NULL")
    op.execute("ALTER TABLE IF EXISTS student_attempts ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ NULL")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_student_attempts_reviewed_by_id_users'
            ) THEN
                ALTER TABLE student_attempts
                ADD CONSTRAINT fk_student_attempts_reviewed_by_id_users
                FOREIGN KEY (reviewed_by_id) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS student_attempts DROP CONSTRAINT IF EXISTS fk_student_attempts_reviewed_by_id_users")
    op.execute("ALTER TABLE IF EXISTS student_attempts DROP COLUMN IF EXISTS reviewed_at")
    op.execute("ALTER TABLE IF EXISTS student_attempts DROP COLUMN IF EXISTS reviewed_by_id")
    op.execute("ALTER TABLE IF EXISTS student_attempts DROP COLUMN IF EXISTS teacher_comment")
    op.execute("ALTER TABLE IF EXISTS student_attempts DROP COLUMN IF EXISTS review_status")
