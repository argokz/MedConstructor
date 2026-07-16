"""academic admin structure

Revision ID: c8d9e0f1a2b3
Revises: b7c9d1e2f3a4
Create Date: 2026-06-17

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "b7c9d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS specialties (
            id SERIAL PRIMARY KEY,
            name VARCHAR NOT NULL UNIQUE,
            code VARCHAR NULL UNIQUE,
            description TEXT NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_specialties_id ON specialties (id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_specialties_name ON specialties (name)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_specialties_code ON specialties (code)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS student_groups (
            id SERIAL PRIMARY KEY,
            name VARCHAR NOT NULL UNIQUE,
            specialty_id INTEGER NULL REFERENCES specialties(id) ON DELETE SET NULL,
            year INTEGER NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_student_groups_id ON student_groups (id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_student_groups_name ON student_groups (name)")

    op.execute("ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS specialty_id INTEGER NULL")
    op.execute("ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS group_id INTEGER NULL")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints tc
                WHERE tc.constraint_name = 'fk_users_specialty_id_specialties'
            ) THEN
                ALTER TABLE users
                ADD CONSTRAINT fk_users_specialty_id_specialties
                FOREIGN KEY (specialty_id) REFERENCES specialties(id) ON DELETE SET NULL;
            END IF;
        END $$
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints tc
                WHERE tc.constraint_name = 'fk_users_group_id_student_groups'
            ) THEN
                ALTER TABLE users
                ADD CONSTRAINT fk_users_group_id_student_groups
                FOREIGN KEY (group_id) REFERENCES student_groups(id) ON DELETE SET NULL;
            END IF;
        END $$
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS assignment_targets (
            id SERIAL PRIMARY KEY,
            assignment_id INTEGER NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
            specialty_id INTEGER NULL REFERENCES specialties(id) ON DELETE CASCADE,
            group_id INTEGER NULL REFERENCES student_groups(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_assignment_targets_id ON assignment_targets (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_assignment_targets_assignment_id ON assignment_targets (assignment_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_assignment_targets_specialty_id ON assignment_targets (specialty_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_assignment_targets_group_id ON assignment_targets (group_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS assignment_targets")
    op.execute("ALTER TABLE IF EXISTS users DROP CONSTRAINT IF EXISTS fk_users_group_id_student_groups")
    op.execute("ALTER TABLE IF EXISTS users DROP CONSTRAINT IF EXISTS fk_users_specialty_id_specialties")
    op.execute("ALTER TABLE IF EXISTS users DROP COLUMN IF EXISTS group_id")
    op.execute("ALTER TABLE IF EXISTS users DROP COLUMN IF EXISTS specialty_id")
    op.execute("DROP TABLE IF EXISTS student_groups")
    op.execute("DROP TABLE IF EXISTS specialties")
