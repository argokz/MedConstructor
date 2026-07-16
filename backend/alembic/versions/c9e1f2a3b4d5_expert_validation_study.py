"""expert validation study (blinded in-system variant rating)

Revision ID: c9e1f2a3b4d5
Revises: b8c9d0e1f2a3
Create Date: 2026-06-29 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c9e1f2a3b4d5"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "validation_variants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("review_item_id", sa.String(), nullable=False),
        sa.Column("cohort", sa.String(), nullable=False, server_default="cardiology_pilot"),
        sa.Column("case_id", sa.String(), nullable=True),
        sa.Column("case_title", sa.String(), nullable=True),
        sa.Column("case_prompt", sa.Text(), nullable=True),
        sa.Column("variant_id", sa.String(), nullable=True),
        sa.Column("expected_pattern", sa.String(), nullable=True),
        sa.Column("graph_under_review", sa.Text(), nullable=True),
        sa.Column("student_graph", sa.JSON(), nullable=True),
        sa.Column("reference_graph", sa.JSON(), nullable=True),
        sa.Column("model_metrics", sa.JSON(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_item_id", name="uq_validation_variant_review_item_id"),
    )
    op.create_index(op.f("ix_validation_variants_id"), "validation_variants", ["id"], unique=False)
    op.create_index(op.f("ix_validation_variants_review_item_id"), "validation_variants", ["review_item_id"], unique=True)
    op.create_index(op.f("ix_validation_variants_cohort"), "validation_variants", ["cohort"], unique=False)

    op.create_table(
        "validation_ratings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("variant_id", sa.Integer(), nullable=False),
        sa.Column("expert_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("accept", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=True, server_default="submitted"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["variant_id"], ["validation_variants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["expert_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("variant_id", "expert_id", name="uq_validation_rating_variant_expert"),
    )
    op.create_index(op.f("ix_validation_ratings_id"), "validation_ratings", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_validation_ratings_id"), table_name="validation_ratings")
    op.drop_table("validation_ratings")
    op.drop_index(op.f("ix_validation_variants_cohort"), table_name="validation_variants")
    op.drop_index(op.f("ix_validation_variants_review_item_id"), table_name="validation_variants")
    op.drop_index(op.f("ix_validation_variants_id"), table_name="validation_variants")
    op.drop_table("validation_variants")
