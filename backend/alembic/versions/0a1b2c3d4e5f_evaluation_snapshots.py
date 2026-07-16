"""evaluation snapshots

Revision ID: 0a1b2c3d4e5f
Revises: d1f2a3b4c5e6
Create Date: 2026-06-30

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0a1b2c3d4e5f"
down_revision: Union[str, None] = "d1f2a3b4c5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS evaluation_snapshots (
            id SERIAL PRIMARY KEY,
            attempt_id INTEGER NULL REFERENCES student_attempts(id) ON DELETE CASCADE,
            assignment_id INTEGER NULL REFERENCES assignments(id) ON DELETE SET NULL,
            reference_graph_id INTEGER NULL REFERENCES reference_graphs(id) ON DELETE SET NULL,
            student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            graph_version INTEGER NOT NULL DEFAULT 1,
            submitted_graph JSONB NULL,
            metrics JSONB NULL,
            recommendations JSONB NULL,
            algorithm_version VARCHAR NULL,
            reference_content_hash VARCHAR NULL,
            embedding_model_version VARCHAR NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_evaluation_snapshots_attempt_id ON evaluation_snapshots (attempt_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_evaluation_snapshots_assignment_student "
        "ON evaluation_snapshots (assignment_id, student_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_evaluation_snapshots_reference_graph_id "
        "ON evaluation_snapshots (reference_graph_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_evaluation_snapshots_created_at "
        "ON evaluation_snapshots (created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_evaluation_snapshots_created_at")
    op.execute("DROP INDEX IF EXISTS ix_evaluation_snapshots_reference_graph_id")
    op.execute("DROP INDEX IF EXISTS ix_evaluation_snapshots_assignment_student")
    op.execute("DROP INDEX IF EXISTS ix_evaluation_snapshots_attempt_id")
    op.execute("DROP TABLE IF EXISTS evaluation_snapshots")
