"""repair missing core tables and idempotency index

Revision ID: b7c9d1e2f3a4
Revises: a1b2c3d4e5f6
Create Date: 2026-06-16

"""
from typing import Sequence, Union

from alembic import op

revision: str = "b7c9d1e2f3a4"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR NOT NULL UNIQUE,
            password_hash VARCHAR NOT NULL,
            full_name VARCHAR NULL,
            role VARCHAR NOT NULL
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_id ON users (id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clinical_protocols (
            id SERIAL PRIMARY KEY,
            title VARCHAR NOT NULL,
            category VARCHAR NULL,
            version VARCHAR NULL,
            mkb_categories VARCHAR[] NULL,
            medical_sections VARCHAR[] NULL,
            year INTEGER NULL,
            url VARCHAR NOT NULL UNIQUE,
            text_content TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_clinical_protocols_id ON clinical_protocols (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_clinical_protocols_title ON clinical_protocols (title)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS protocol_chunks (
            id SERIAL PRIMARY KEY,
            protocol_id INTEGER NOT NULL REFERENCES clinical_protocols(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            text_content TEXT NOT NULL,
            embedding vector(1536) NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_protocol_chunks_id ON protocol_chunks (id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS student_tasks (
            id SERIAL PRIMARY KEY,
            protocol_id INTEGER NOT NULL REFERENCES clinical_protocols(id) ON DELETE CASCADE,
            case_description TEXT NOT NULL,
            expected_diagnosis VARCHAR NULL,
            expected_treatment TEXT NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_student_tasks_id ON student_tasks (id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS student_task_attempts (
            id SERIAL PRIMARY KEY,
            task_id INTEGER NOT NULL REFERENCES student_tasks(id) ON DELETE CASCADE,
            student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            student_answer TEXT NOT NULL,
            validation_result JSON NULL,
            score INTEGER NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_student_task_attempts_id ON student_task_attempts (id)")

    op.execute("ALTER TABLE IF EXISTS disciplines ADD COLUMN IF NOT EXISTS code VARCHAR NULL")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_disciplines_code ON disciplines (code)")

    op.execute("ALTER TABLE IF EXISTS reference_graphs ADD COLUMN IF NOT EXISTS graph_data JSON NULL")
    op.execute("ALTER TABLE IF EXISTS reference_graphs ADD COLUMN IF NOT EXISTS discipline_id INTEGER NULL")

    op.execute("ALTER TABLE IF EXISTS student_attempts ADD COLUMN IF NOT EXISTS reference_graph_id INTEGER NULL")
    op.execute("ALTER TABLE IF EXISTS student_attempts ADD COLUMN IF NOT EXISTS submitted_graph JSON NULL")
    op.execute("ALTER TABLE IF EXISTS student_attempts ADD COLUMN IF NOT EXISTS metrics JSON NULL")
    op.execute("ALTER TABLE IF EXISTS student_attempts ADD COLUMN IF NOT EXISTS algorithm_version VARCHAR NULL")
    op.execute("ALTER TABLE IF EXISTS student_attempts ADD COLUMN IF NOT EXISTS reference_content_hash VARCHAR NULL")
    op.execute("ALTER TABLE IF EXISTS student_attempts ADD COLUMN IF NOT EXISTS embedding_model_version VARCHAR NULL")
    op.execute("ALTER TABLE IF EXISTS student_attempts ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR NULL")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'reference_graphs'
            ) AND EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'disciplines'
            ) AND NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.constraint_schema = kcu.constraint_schema
                JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name = ccu.constraint_name
                 AND tc.constraint_schema = ccu.constraint_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_name = 'reference_graphs'
                  AND kcu.column_name = 'discipline_id'
                  AND ccu.table_name = 'disciplines'
                  AND ccu.column_name = 'id'
            ) THEN
                ALTER TABLE reference_graphs
                ADD CONSTRAINT fk_reference_graphs_discipline_id_disciplines
                FOREIGN KEY (discipline_id) REFERENCES disciplines(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'student_attempts'
            ) AND EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'reference_graphs'
            ) AND NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.constraint_schema = kcu.constraint_schema
                JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name = ccu.constraint_name
                 AND tc.constraint_schema = ccu.constraint_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_name = 'student_attempts'
                  AND kcu.column_name = 'reference_graph_id'
                  AND ccu.table_name = 'reference_graphs'
                  AND ccu.column_name = 'id'
            ) THEN
                ALTER TABLE student_attempts
                ADD CONSTRAINT fk_student_attempts_reference_graph_id_reference_graphs
                FOREIGN KEY (reference_graph_id) REFERENCES reference_graphs(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_student_attempt_idempotency_key
        ON student_attempts (student_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_student_attempt_idempotency_key")
