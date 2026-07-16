"""teacher attempt scores and rubric

Revision ID: 1b2c3d4e5f6a
Revises: 0a1b2c3d4e5f
Create Date: 2026-07-13

"""
from typing import Sequence, Union

from alembic import op

revision: str = "1b2c3d4e5f6a"
down_revision: Union[str, None] = "0a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS student_attempts ADD COLUMN IF NOT EXISTS teacher_score DOUBLE PRECISION NULL")
    op.execute("ALTER TABLE IF EXISTS student_attempts ADD COLUMN IF NOT EXISTS teacher_rubric JSONB NULL")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_student_attempts_teacher_score_unit'
            ) THEN
                ALTER TABLE student_attempts
                ADD CONSTRAINT ck_student_attempts_teacher_score_unit
                CHECK (teacher_score IS NULL OR (teacher_score >= 0.0 AND teacher_score <= 1.0));
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS student_attempts DROP CONSTRAINT IF EXISTS ck_student_attempts_teacher_score_unit")
    op.execute("ALTER TABLE IF EXISTS student_attempts DROP COLUMN IF EXISTS teacher_rubric")
    op.execute("ALTER TABLE IF EXISTS student_attempts DROP COLUMN IF EXISTS teacher_score")
