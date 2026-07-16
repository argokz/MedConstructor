from sqlalchemy import Column, Float, Integer, String, Text, DateTime, func, ForeignKey, JSON, ARRAY, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(String, nullable=False)
    specialty_id = Column(Integer, ForeignKey("specialties.id", ondelete="SET NULL"), nullable=True)
    group_id = Column(Integer, ForeignKey("student_groups.id", ondelete="SET NULL"), nullable=True)

    specialty = relationship("Specialty")
    group = relationship("StudentGroup")


class Specialty(Base):
    __tablename__ = "specialties"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    code = Column(String, nullable=True, unique=True, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class StudentGroup(Base):
    __tablename__ = "student_groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    specialty_id = Column(Integer, ForeignKey("specialties.id", ondelete="SET NULL"), nullable=True)
    year = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    specialty = relationship("Specialty")

class ClinicalProtocol(Base):
    __tablename__ = "clinical_protocols"
    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, nullable=True, index=True)
    title = Column(String, nullable=False, index=True)
    category = Column(String, nullable=True)                      # legacy, kept for compat
    version = Column(String, nullable=True)                       # e.g. "Клинические протоколы МЗ РК - 2016 (Казахстан)"
    mkb_categories = Column(ARRAY(String), nullable=True)         # ["Травма кровеносных сосудов... (S35)", ...]
    medical_sections = Column(ARRAY(String), nullable=True)       # ["Травматология и ортопедия", "Хирургия"]
    year = Column(Integer, nullable=True)
    url = Column(String, nullable=False, unique=True)
    text_content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ProtocolChunk(Base):
    __tablename__ = "protocol_chunks"
    id = Column(Integer, primary_key=True, index=True)
    protocol_id = Column(Integer, ForeignKey("clinical_protocols.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    text_content = Column(Text, nullable=False)
    embedding = Column(Vector(1536))  # OpenAI text-embedding-3-small = 1536 dimensions

    protocol = relationship("ClinicalProtocol", backref="chunks")

class StudentTask(Base):
    __tablename__ = "student_tasks"
    id = Column(Integer, primary_key=True, index=True)
    protocol_id = Column(Integer, ForeignKey("clinical_protocols.id", ondelete="CASCADE"), nullable=False)
    case_description = Column(Text, nullable=False)  # Сгенерированный анамнез/жалобы пациента
    expected_diagnosis = Column(String, nullable=True)
    expected_treatment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    protocol = relationship("ClinicalProtocol")

class StudentTaskAttempt(Base):
    __tablename__ = "student_task_attempts"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("student_tasks.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    student_answer = Column(Text, nullable=False)  # Ответ студента (диагноз, лечение)
    validation_result = Column(JSON, nullable=True)  # Оценка и обратная связь от LLM
    score = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship("StudentTask")
    student = relationship("User")

class Discipline(Base):
    __tablename__ = "disciplines"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    code = Column(String, nullable=True, unique=True, index=True)

class ReferenceGraph(Base):
    __tablename__ = "reference_graphs"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    graph_data = Column(JSON, nullable=True)
    discipline_id = Column(Integer, ForeignKey("disciplines.id", ondelete="CASCADE"), nullable=True)
    status = Column(String, nullable=True, default="draft")
    source_type = Column(String, nullable=True)
    generation_context = Column(JSON, nullable=True)
    generation_quality = Column(JSON, nullable=True)
    validation_warnings = Column(JSON, nullable=True)
    review_notes = Column(Text, nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    discipline = relationship("Discipline")
    approved_by = relationship("User", foreign_keys=[approved_by_id])

class Assignment(Base):
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    discipline_id = Column(Integer, ForeignKey("disciplines.id", ondelete="CASCADE"), nullable=False)
    reference_graph_id = Column(Integer, ForeignKey("reference_graphs.id", ondelete="CASCADE"), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String, nullable=True, default="draft")
    review_notes = Column(Text, nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    time_limit_minutes = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    discipline = relationship("Discipline")
    reference_graph = relationship("ReferenceGraph")
    created_by = relationship("User", foreign_keys=[created_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])


class AssignmentTarget(Base):
    __tablename__ = "assignment_targets"
    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False)
    specialty_id = Column(Integer, ForeignKey("specialties.id", ondelete="CASCADE"), nullable=True)
    group_id = Column(Integer, ForeignKey("student_groups.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    assignment = relationship("Assignment")
    specialty = relationship("Specialty")
    group = relationship("StudentGroup")

class StudentAttempt(Base):
    __tablename__ = "student_attempts"
    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id", ondelete="CASCADE"), nullable=True)
    reference_graph_id = Column(Integer, ForeignKey("reference_graphs.id", ondelete="CASCADE"), nullable=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    student_graph = Column(JSON, nullable=True)
    submitted_graph = Column(JSON, nullable=True)
    metrics = Column(JSON, nullable=True)
    review_status = Column(String, nullable=True)
    teacher_comment = Column(Text, nullable=True)
    teacher_score = Column(Float, nullable=True)
    teacher_rubric = Column(JSON, nullable=True)
    reviewed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    algorithm_version = Column(String, nullable=True)
    reference_content_hash = Column(String, nullable=True)
    embedding_model_version = Column(String, nullable=True)
    idempotency_key = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    assignment = relationship("Assignment")
    reference_graph = relationship("ReferenceGraph")
    student = relationship("User", foreign_keys=[student_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])


class EvaluationSnapshot(Base):
    __tablename__ = "evaluation_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(Integer, ForeignKey("student_attempts.id", ondelete="CASCADE"), nullable=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id", ondelete="SET NULL"), nullable=True)
    reference_graph_id = Column(Integer, ForeignKey("reference_graphs.id", ondelete="SET NULL"), nullable=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    graph_version = Column(Integer, nullable=False, default=1)
    submitted_graph = Column(JSON, nullable=True)
    metrics = Column(JSON, nullable=True)
    recommendations = Column(JSON, nullable=True)
    algorithm_version = Column(String, nullable=True)
    reference_content_hash = Column(String, nullable=True)
    embedding_model_version = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    attempt = relationship("StudentAttempt")
    assignment = relationship("Assignment")
    reference_graph = relationship("ReferenceGraph")
    student = relationship("User", foreign_keys=[student_id])


class StudentAssignmentProgress(Base):
    __tablename__ = "student_assignment_progress"
    __table_args__ = (
        UniqueConstraint("student_id", "assignment_id", name="uq_student_assignment_progress_student_assignment"),
    )

    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, nullable=False, default="not_started")
    latest_attempt_id = Column(Integer, ForeignKey("student_attempts.id", ondelete="SET NULL"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    deadline_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    assignment = relationship("Assignment")
    student = relationship("User", foreign_keys=[student_id])
    latest_attempt = relationship("StudentAttempt", foreign_keys=[latest_attempt_id])


class ExpertReview(Base):
    __tablename__ = "expert_reviews"
    id = Column(Integer, primary_key=True, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_type = Column(String, nullable=False, index=True)
    item_id = Column(Integer, nullable=False, index=True)
    assignment_id = Column(Integer, ForeignKey("assignments.id", ondelete="SET NULL"), nullable=True)
    reference_graph_id = Column(Integer, ForeignKey("reference_graphs.id", ondelete="SET NULL"), nullable=True)
    student_attempt_id = Column(Integer, ForeignKey("student_attempts.id", ondelete="SET NULL"), nullable=True)
    score = Column(Float, nullable=True)
    step_scores = Column(JSON, nullable=True)
    issue_tags = Column(JSON, nullable=True)
    comment = Column(Text, nullable=True)
    recommendation = Column(Text, nullable=True)
    status = Column(String, nullable=True, default="submitted")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    reviewer = relationship("User", foreign_keys=[reviewer_id])
    assignment = relationship("Assignment")
    reference_graph = relationship("ReferenceGraph")
    student_attempt = relationship("StudentAttempt")

class ValidationVariant(Base):
    """A blinded graph variant rated in-system by the expert validation panel.

    Used by the cardiology (and future) expert-validation study: experts log in
    and rate ``student_graph`` for clinical quality. ``expected_pattern`` and
    ``model_metrics`` are researcher-only and never serialized in the blinded
    payload sent to raters.
    """

    __tablename__ = "validation_variants"
    id = Column(Integer, primary_key=True, index=True)
    review_item_id = Column(String, nullable=False, unique=True, index=True)  # blinded id, e.g. cre_xxxx
    cohort = Column(String, nullable=False, default="cardiology_pilot", index=True)
    case_id = Column(String, nullable=True)
    case_title = Column(String, nullable=True)
    case_prompt = Column(Text, nullable=True)            # clinical task text shown to the rater
    variant_id = Column(String, nullable=True)
    expected_pattern = Column(String, nullable=True)     # researcher-only
    graph_under_review = Column(Text, nullable=True)     # short neutral description
    student_graph = Column(JSON, nullable=True)          # the graph the expert evaluates
    reference_graph = Column(JSON, nullable=True)        # researcher-only context
    model_metrics = Column(JSON, nullable=True)          # researcher-only (model_score, etc.)
    display_order = Column(Integer, nullable=True)
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ValidationRating(Base):
    """A single expert's blinded 0-100 rating of a ValidationVariant."""

    __tablename__ = "validation_ratings"
    __table_args__ = (
        UniqueConstraint("variant_id", "expert_id", name="uq_validation_rating_variant_expert"),
    )
    id = Column(Integer, primary_key=True, index=True)
    variant_id = Column(Integer, ForeignKey("validation_variants.id", ondelete="CASCADE"), nullable=False)
    expert_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    score = Column(Float, nullable=True)                 # 0-100 scale
    accept = Column(String, nullable=True)               # "yes" / "no"
    confidence = Column(Float, nullable=True)            # optional 0-1
    comment = Column(Text, nullable=True)
    status = Column(String, nullable=True, default="submitted")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    variant = relationship("ValidationVariant")
    expert = relationship("User")


class MedicalNode(Base):
    __tablename__ = "medical_nodes"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    external_id = Column(String, nullable=True)
    source = Column(String, nullable=True)
    embedding = Column(Vector(1536), nullable=True)

class MedicalEdge(Base):
    __tablename__ = "medical_edges"
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("medical_nodes.id", ondelete="CASCADE"), nullable=False)
    target_id = Column(Integer, ForeignKey("medical_nodes.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String, nullable=False)
    weight = Column(Integer, nullable=True, default=1)


Index(
    "uq_student_attempt_idempotency_key",
    StudentAttempt.student_id,
    StudentAttempt.idempotency_key,
    unique=True,
    postgresql_where=StudentAttempt.idempotency_key.isnot(None),
)

Index("ix_evaluation_snapshots_attempt_id", EvaluationSnapshot.attempt_id)
Index("ix_evaluation_snapshots_assignment_student", EvaluationSnapshot.assignment_id, EvaluationSnapshot.student_id)
Index("ix_evaluation_snapshots_reference_graph_id", EvaluationSnapshot.reference_graph_id)

Index(
    "uq_expert_review_reviewer_item",
    ExpertReview.reviewer_id,
    ExpertReview.item_type,
    ExpertReview.item_id,
    unique=True,
)
