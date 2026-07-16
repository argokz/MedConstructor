"""human review workflow

Revision ID: f0a1b2c3d4e5
Revises: e5f6a7b8c9d0
Create Date: 2026-06-18

"""
from typing import Sequence, Union

from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS reference_graphs ADD COLUMN IF NOT EXISTS status VARCHAR NULL")
    op.execute("ALTER TABLE IF EXISTS reference_graphs ADD COLUMN IF NOT EXISTS source_type VARCHAR NULL")
    op.execute("ALTER TABLE IF EXISTS reference_graphs ADD COLUMN IF NOT EXISTS generation_context JSONB NULL")
    op.execute("ALTER TABLE IF EXISTS reference_graphs ADD COLUMN IF NOT EXISTS generation_quality JSONB NULL")
    op.execute("ALTER TABLE IF EXISTS reference_graphs ADD COLUMN IF NOT EXISTS validation_warnings JSONB NULL")
    op.execute("ALTER TABLE IF EXISTS reference_graphs ADD COLUMN IF NOT EXISTS review_notes TEXT NULL")
    op.execute("ALTER TABLE IF EXISTS reference_graphs ADD COLUMN IF NOT EXISTS approved_by_id INTEGER NULL")
    op.execute("ALTER TABLE IF EXISTS reference_graphs ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ NULL")
    op.execute("UPDATE reference_graphs SET status = 'approved' WHERE status IS NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reference_graphs_status ON reference_graphs (status)")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_reference_graphs_approved_by_id_users'
            ) THEN
                ALTER TABLE reference_graphs
                ADD CONSTRAINT fk_reference_graphs_approved_by_id_users
                FOREIGN KEY (approved_by_id) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$
        """
    )

    op.execute("ALTER TABLE IF EXISTS assignments ADD COLUMN IF NOT EXISTS status VARCHAR NULL")
    op.execute("ALTER TABLE IF EXISTS assignments ADD COLUMN IF NOT EXISTS review_notes TEXT NULL")
    op.execute("ALTER TABLE IF EXISTS assignments ADD COLUMN IF NOT EXISTS approved_by_id INTEGER NULL")
    op.execute("ALTER TABLE IF EXISTS assignments ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ NULL")
    op.execute("ALTER TABLE IF EXISTS assignments ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ NULL")
    op.execute("UPDATE assignments SET status = 'published' WHERE status IS NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_assignments_status ON assignments (status)")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_assignments_approved_by_id_users'
            ) THEN
                ALTER TABLE assignments
                ADD CONSTRAINT fk_assignments_approved_by_id_users
                FOREIGN KEY (approved_by_id) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS expert_reviews (
            id SERIAL PRIMARY KEY,
            reviewer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            item_type VARCHAR NOT NULL,
            item_id INTEGER NOT NULL,
            assignment_id INTEGER NULL REFERENCES assignments(id) ON DELETE SET NULL,
            reference_graph_id INTEGER NULL REFERENCES reference_graphs(id) ON DELETE SET NULL,
            student_attempt_id INTEGER NULL REFERENCES student_attempts(id) ON DELETE SET NULL,
            score DOUBLE PRECISION NULL,
            step_scores JSONB NULL,
            issue_tags JSONB NULL,
            comment TEXT NULL,
            recommendation TEXT NULL,
            status VARCHAR NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_expert_reviews_item_type ON expert_reviews (item_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_expert_reviews_item_id ON expert_reviews (item_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_expert_review_reviewer_item ON expert_reviews (reviewer_id, item_type, item_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS expert_reviews")
    op.execute("ALTER TABLE IF EXISTS assignments DROP CONSTRAINT IF EXISTS fk_assignments_approved_by_id_users")
    op.execute("DROP INDEX IF EXISTS ix_assignments_status")
    op.execute("ALTER TABLE IF EXISTS assignments DROP COLUMN IF EXISTS published_at")
    op.execute("ALTER TABLE IF EXISTS assignments DROP COLUMN IF EXISTS approved_at")
    op.execute("ALTER TABLE IF EXISTS assignments DROP COLUMN IF EXISTS approved_by_id")
    op.execute("ALTER TABLE IF EXISTS assignments DROP COLUMN IF EXISTS review_notes")
    op.execute("ALTER TABLE IF EXISTS assignments DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE IF EXISTS reference_graphs DROP CONSTRAINT IF EXISTS fk_reference_graphs_approved_by_id_users")
    op.execute("DROP INDEX IF EXISTS ix_reference_graphs_status")
    op.execute("ALTER TABLE IF EXISTS reference_graphs DROP COLUMN IF EXISTS approved_at")
    op.execute("ALTER TABLE IF EXISTS reference_graphs DROP COLUMN IF EXISTS approved_by_id")
    op.execute("ALTER TABLE IF EXISTS reference_graphs DROP COLUMN IF EXISTS review_notes")
    op.execute("ALTER TABLE IF EXISTS reference_graphs DROP COLUMN IF EXISTS validation_warnings")
    op.execute("ALTER TABLE IF EXISTS reference_graphs DROP COLUMN IF EXISTS generation_quality")
    op.execute("ALTER TABLE IF EXISTS reference_graphs DROP COLUMN IF EXISTS generation_context")
    op.execute("ALTER TABLE IF EXISTS reference_graphs DROP COLUMN IF EXISTS source_type")
    op.execute("ALTER TABLE IF EXISTS reference_graphs DROP COLUMN IF EXISTS status")
