from typing import Any, Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict, model_validator

ASSIGNMENT_STATUS_PATTERN = (
    "^(draft|ai_generated|needs_teacher_review|review_ready|"
    "teacher_approved|published|archived)$"
)

# --- Enums для Графа ---
class NodeType(str, Enum):
    PATIENT_PROFILE = "PATIENT_PROFILE"
    SYMPTOM = "SYMPTOM"
    EXAM = "EXAM"
    LAB_TEST = "LAB_TEST"
    INSTRUMENTAL_TEST = "INSTRUMENTAL_TEST"
    DIAGNOSIS = "DIAGNOSIS"
    MEDICATION = "MEDICATION"
    SURGERY = "SURGERY"
    MONITORING = "MONITORING"

class EdgeType(str, Enum):
    DETERMINES = "DETERMINES"
    REQUIRES_CONFIRMATION = "REQUIRES_CONFIRMATION"
    EXCLUDES = "EXCLUDES"
    INDICATED_FOR = "INDICATED_FOR"
    CONTRAINDICATED_DUE_TO = "CONTRAINDICATED_DUE_TO"

# --- Схемы для Графа ---
class NodeData(BaseModel):
    label: str
    category: NodeType
    description: Optional[str] = None
    protocol_refs: List[Dict[str, Any]] = Field(default_factory=list)
    is_critical: bool = False
    source: Optional[str] = None
    confidence: Optional[float] = None

class NodeSchema(BaseModel):
    id: str  # Уникальный ID узла во Vue Flow
    type: Optional[str] = "default"
    position: Dict[str, float]
    data: NodeData

class EdgeSchema(BaseModel):
    id: str
    type: Optional[str] = None
    source: str  # ID исходного узла
    target: str  # ID целевого узла
    label: EdgeType
    sourceHandle: Optional[str] = "s"
    targetHandle: Optional[str] = "t"

class GraphSchema(BaseModel):
    nodes: List[NodeSchema]
    edges: List[EdgeSchema]
    
    @model_validator(mode='after')
    def validate_edges(self):
        node_types = {n.id: n.data.category for n in self.nodes}
        for edge in self.edges:
            source_type = node_types.get(edge.source)
            target_type = node_types.get(edge.target)
            if not source_type or not target_type:
                continue
                
            if edge.label == EdgeType.INDICATED_FOR:
                if source_type != NodeType.DIAGNOSIS or target_type not in (NodeType.MEDICATION, NodeType.SURGERY, NodeType.MONITORING):
                    raise ValueError(f"INDICATED_FOR edge must go from DIAGNOSIS to MEDICATION, SURGERY or MONITORING. Found {source_type} -> {target_type}")
            elif edge.label == EdgeType.CONTRAINDICATED_DUE_TO:
                if source_type not in (NodeType.MEDICATION, NodeType.SURGERY) or target_type not in (NodeType.PATIENT_PROFILE, NodeType.DIAGNOSIS, NodeType.SYMPTOM):
                    raise ValueError(f"CONTRAINDICATED_DUE_TO edge must go from MEDICATION/SURGERY to PATIENT_PROFILE/DIAGNOSIS/SYMPTOM. Found {source_type} -> {target_type}")
        return self

# --- Схемы для API Request/Response ---
class GraphEvaluationRequest(BaseModel):
    reference_graph_id: int
    assignment_id: Optional[int] = None
    student_id: Optional[int] = Field(
        default=None,
        description="If omitted, the authenticated JWT user id is used.",
    )
    student_graph: GraphSchema
    idempotency_key: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Повтор с тем же ключом возвращает ту же оценку без повторного расчёта.",
    )

class GraphEvaluationResponse(BaseModel):
    precision: float
    recall: float
    f1_score: float
    missing_edges: List[Dict[str, str]]
    incorrect_edges: List[Dict[str, str]]
    message: str
    composite_score: Optional[float] = None
    edge_f1: Optional[float] = None
    weighted_precision: Optional[float] = None
    weighted_recall: Optional[float] = None
    weighted_edge_f1: Optional[float] = None
    node_coverage: Optional[float] = None
    chain_completeness: Optional[float] = None
    directed_path_completeness: Optional[float] = None
    category_accuracy: Optional[float] = None
    structural_correctness: Optional[float] = None
    safety_penalty: Optional[float] = None
    edge_count_penalty: Optional[float] = None
    student_edge_count: Optional[int] = None
    reference_edge_count: Optional[int] = None
    unsafe_extra_action: Optional[float] = None
    missing_critical_action: Optional[float] = None
    diagnostic_evidence_gap: Optional[float] = None
    diagnostic_evidence_findings: Optional[List[Dict[str, str]]] = None
    clinical_connectivity_gap: Optional[float] = None
    clinical_connectivity_findings: Optional[List[Dict[str, str]]] = None
    score_caps: Optional[List[Dict[str, Any]]] = None
    safety_findings: Optional[List[Dict[str, str]]] = None
    missing_nodes: Optional[List[str]] = None
    algorithm_version: Optional[str] = None
    attempt_id: Optional[int] = None
    evaluation_snapshot_id: Optional[int] = None
    graph_version: Optional[int] = None
    evaluation_timing_ms: Optional[Dict[str, float]] = None


# --- Auth & assignments ---
class UserRegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=128)
    full_name: Optional[str] = None


class UserLoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserPublic(BaseModel):
    id: int
    email: str
    role: str
    full_name: Optional[str] = None
    specialty_id: Optional[int] = None
    group_id: Optional[int] = None


class UserCreateRequest(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=128)
    full_name: Optional[str] = None
    role: str = Field(default="student", pattern="^(student|teacher|expert|admin)$")
    specialty_id: Optional[int] = None
    group_id: Optional[int] = None


class UserUpdateRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    full_name: Optional[str] = None
    role: Optional[str] = Field(default=None, pattern="^(student|teacher|expert|admin)$")
    specialty_id: Optional[int] = None
    group_id: Optional[int] = None


class UserListResponse(BaseModel):
    items: List[UserPublic]


class SpecialtyPublic(BaseModel):
    id: int
    name: str
    code: Optional[str] = None
    description: Optional[str] = None


class SpecialtyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: Optional[str] = Field(default=None, max_length=40)
    description: Optional[str] = None


class SpecialtyListResponse(BaseModel):
    items: List[SpecialtyPublic]


class StudentGroupPublic(BaseModel):
    id: int
    name: str
    specialty_id: Optional[int] = None
    year: Optional[int] = None


class StudentGroupCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    specialty_id: Optional[int] = None
    year: Optional[int] = None


class StudentGroupListResponse(BaseModel):
    items: List[StudentGroupPublic]


class AssignmentTargetPublic(BaseModel):
    id: int
    assignment_id: int
    specialty_id: Optional[int] = None
    group_id: Optional[int] = None


class AssignmentTargetsUpdate(BaseModel):
    specialty_ids: List[int] = Field(default_factory=list)
    group_ids: List[int] = Field(default_factory=list)


class AssignmentPublic(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    discipline_id: int
    reference_graph_id: int
    created_by_id: Optional[int] = None
    created_by_email: Optional[str] = None
    created_by_name: Optional[str] = None
    status: Optional[str] = None
    review_notes: Optional[str] = None
    approved_by_id: Optional[int] = None
    approved_at: Optional[str] = None
    published_at: Optional[str] = None
    time_limit_minutes: Optional[int] = None
    reference_status: Optional[str] = None
    reference_validation_warnings: List[str] = Field(default_factory=list)
    reference_generation_quality: Optional[Dict[str, Any]] = None
    protocol_id: Optional[int] = None
    protocol_external_id: Optional[str] = None
    protocol_title: Optional[str] = None
    protocol_year: Optional[int] = None
    protocol_version: Optional[str] = None
    protocol_url: Optional[str] = None
    protocol_category: Optional[str] = None
    protocol_sections: List[str] = Field(default_factory=list)
    source_protocols: List[Dict[str, Any]] = Field(default_factory=list)
    targets: List[AssignmentTargetPublic] = Field(default_factory=list)
    progress_status: Optional[str] = None
    latest_attempt_id: Optional[int] = None
    latest_score: Optional[float] = None
    started_at: Optional[str] = None
    submitted_at: Optional[str] = None
    completed_at: Optional[str] = None
    deadline_at: Optional[str] = None


class AssignmentProgressPublic(BaseModel):
    assignment_id: int
    student_id: int
    status: str
    latest_attempt_id: Optional[int] = None
    latest_score: Optional[float] = None
    started_at: Optional[str] = None
    submitted_at: Optional[str] = None
    completed_at: Optional[str] = None
    deadline_at: Optional[str] = None


class AssignmentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    discipline_id: int
    reference_graph_id: int
    time_limit_minutes: Optional[int] = Field(default=None, ge=5, le=24 * 60)
    status: Optional[str] = Field(default="published", pattern=ASSIGNMENT_STATUS_PATTERN)


class AssignmentDraftUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=240)
    description: Optional[str] = None
    time_limit_minutes: Optional[int] = Field(default=None, ge=5, le=24 * 60)
    graph_data: Optional[GraphSchema] = None
    review_notes: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern=ASSIGNMENT_STATUS_PATTERN)


class AssignmentApproveReferenceRequest(BaseModel):
    review_notes: Optional[str] = None
    force: bool = Field(
        default=False,
        description="Allow teacher approval despite critical automatic warnings after documented clinical review.",
    )


class AssignmentPublishRequest(BaseModel):
    review_notes: Optional[str] = None
    force: bool = Field(
        default=False,
        description="Allow publishing even when the automatic judge still has non-critical warnings.",
    )


class ReferenceGraphPublic(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    graph_data: Optional[Dict[str, Any]] = None
    discipline_id: Optional[int] = None
    status: Optional[str] = None
    source_type: Optional[str] = None
    generation_context: Optional[List[Dict[str, Any]]] = None
    generation_quality: Optional[Dict[str, Any]] = None
    protocol_id: Optional[int] = None
    protocol_external_id: Optional[str] = None
    protocol_title: Optional[str] = None
    protocol_year: Optional[int] = None
    protocol_version: Optional[str] = None
    protocol_url: Optional[str] = None
    protocol_category: Optional[str] = None
    protocol_sections: List[str] = Field(default_factory=list)
    source_protocols: List[Dict[str, Any]] = Field(default_factory=list)
    validation_warnings: List[str] = Field(default_factory=list)
    review_notes: Optional[str] = None
    approved_by_id: Optional[int] = None
    approved_at: Optional[str] = None


class AssignmentReviewBundle(BaseModel):
    assignment: AssignmentPublic
    reference_graph: ReferenceGraphPublic


class AssignmentListResponse(BaseModel):
    items: List[AssignmentPublic]


class StudentAttemptPublic(BaseModel):
    id: int
    assignment_id: Optional[int] = None
    assignment_title: Optional[str] = None
    assignment_description: Optional[str] = None
    assignment_time_limit_minutes: Optional[int] = None
    reference_graph_id: Optional[int] = None
    student_id: int
    student_email: Optional[str] = None
    student_name: Optional[str] = None
    submitted_graph: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None
    review_status: Optional[str] = None
    teacher_comment: Optional[str] = None
    teacher_score: Optional[float] = None
    teacher_rubric: Optional[Dict[str, float]] = None
    reviewed_by_id: Optional[int] = None
    reviewed_at: Optional[str] = None
    created_at: Optional[str] = None


class StudentAttemptListResponse(BaseModel):
    items: List[StudentAttemptPublic]


class EvaluationSnapshotPublic(BaseModel):
    id: int
    attempt_id: Optional[int] = None
    assignment_id: Optional[int] = None
    reference_graph_id: Optional[int] = None
    student_id: int
    graph_version: int
    submitted_graph: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None
    recommendations: Optional[Dict[str, Any]] = None
    algorithm_version: Optional[str] = None
    reference_content_hash: Optional[str] = None
    embedding_model_version: Optional[str] = None
    created_at: Optional[str] = None


class EvaluationSnapshotListResponse(BaseModel):
    items: List[EvaluationSnapshotPublic]


class TeacherRubricScores(BaseModel):
    clinical_reasoning: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    diagnostic_justification: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    treatment_safety: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    graph_structure: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class StudentAttemptReviewUpdate(BaseModel):
    review_status: str = Field(pattern="^(needs_review|accepted|revision_requested)$")
    teacher_comment: Optional[str] = None
    teacher_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    teacher_rubric: Optional[TeacherRubricScores] = None


class ExpertReviewPublic(BaseModel):
    id: int
    reviewer_id: int
    reviewer_email: Optional[str] = None
    reviewer_name: Optional[str] = None
    item_type: str
    item_id: int
    assignment_id: Optional[int] = None
    reference_graph_id: Optional[int] = None
    student_attempt_id: Optional[int] = None
    score: Optional[float] = None
    step_scores: Optional[Dict[str, Any]] = None
    issue_tags: List[str] = Field(default_factory=list)
    comment: Optional[str] = None
    recommendation: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ExpertReviewUpsert(BaseModel):
    item_type: str = Field(pattern="^(student_attempt|reference_graph|assignment)$")
    item_id: int
    score: Optional[float] = Field(default=None, ge=0, le=1)
    step_scores: Optional[Dict[str, Any]] = None
    issue_tags: List[str] = Field(default_factory=list)
    comment: Optional[str] = None
    recommendation: Optional[str] = None
    status: str = Field(default="submitted", pattern="^(draft|submitted)$")


class ExpertReviewItem(BaseModel):
    item_type: str
    item_id: int
    title: str
    status: Optional[str] = None
    assignment_id: Optional[int] = None
    assignment_title: Optional[str] = None
    reference_graph_id: Optional[int] = None
    student_attempt_id: Optional[int] = None
    student_id: Optional[int] = None
    student_email: Optional[str] = None
    student_name: Optional[str] = None
    reference_graph: Optional[Dict[str, Any]] = None
    student_graph: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None
    validation_warnings: List[str] = Field(default_factory=list)
    generation_quality: Optional[Dict[str, Any]] = None
    existing_review: Optional[ExpertReviewPublic] = None


class ExpertReviewItemListResponse(BaseModel):
    items: List[ExpertReviewItem]


class ExpertReviewListResponse(BaseModel):
    items: List[ExpertReviewPublic]


# --- Blinded expert validation study (in-system variant rating) ---

class ValidationRatingPublic(BaseModel):
    review_item_id: str
    score: Optional[float] = None  # 0-100
    accept: Optional[str] = None
    confidence: Optional[float] = None
    comment: Optional[str] = None
    status: Optional[str] = None
    updated_at: Optional[str] = None


class ValidationRatingUpsert(BaseModel):
    review_item_id: str
    score: float = Field(ge=0, le=100)
    accept: Optional[str] = Field(default=None, pattern="^(yes|no)$")
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    comment: Optional[str] = None
    status: str = Field(default="submitted", pattern="^(draft|submitted)$")


class ValidationVariantBlinded(BaseModel):
    """Blinded variant payload. Never includes expected_pattern or model metrics."""
    review_item_id: str
    case_title: Optional[str] = None
    case_prompt: Optional[str] = None
    graph_under_review: Optional[str] = None
    student_graph: Optional[Dict[str, Any]] = None
    display_order: Optional[int] = None
    my_rating: Optional[ValidationRatingPublic] = None


class ValidationItemsResponse(BaseModel):
    cohort: str
    total: int
    rated: int
    items: List[ValidationVariantBlinded]


class AssignmentDraftResponse(BaseModel):
    title: str
    student_prompt: str
    checklist: List[str]
    commentary: str
    reference_graph_id: int


# --- AI hints ---
class GraphHintsRequest(BaseModel):
    reference_graph_id: int
    student_graph: GraphSchema
    missing_edges: List[Dict[str, str]] = Field(default_factory=list)
    incorrect_edges: List[Dict[str, str]] = Field(default_factory=list)


class HintItem(BaseModel):
    text: str
    priority: int = 1


class GraphHintsResponse(BaseModel):
    hints: List[HintItem]
    summary: str

class GraphFeedbackResponse(BaseModel):
    feedback: str

# --- RAG / LLM Evaluation ---
class ClinicalTaskGenerateRequest(BaseModel):
    protocol_id: int

class ClinicalTaskResponse(BaseModel):
    id: int
    protocol_id: int
    case_description: str
    expected_diagnosis: Optional[str] = None
    expected_treatment: Optional[str] = None
    
class StudentAnswerRequest(BaseModel):
    student_answer: str

class ValidationResponse(BaseModel):
    id: int
    task_id: int
    score: int
    validation_result: Dict[str, Any]

# --- Protocols ---
class ClinicalProtocolPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: Optional[str] = None
    title: str
    category: Optional[str] = None
    version: Optional[str] = None
    year: Optional[int] = None
    url: Optional[str] = None
    mkb_categories: Optional[List[str]] = None
    medical_sections: Optional[List[str]] = None

class ProtocolListResponse(BaseModel):
    items: List[ClinicalProtocolPublic]
    total: int

class ClinicalProtocolDetail(ClinicalProtocolPublic):
    text_content: str

class RagAskRequest(BaseModel):
    question: str
    protocol_id: Optional[int] = None

class RagSource(BaseModel):
    id: str
    protocol_id: int
    protocol_title: str
    text: str

class RagAskResponse(BaseModel):
    answer: str
    sources: List[RagSource]

class ScenarioSuggestion(BaseModel):
    title: str
    description: str
    difficulty: Optional[str] = None
    target_competency: Optional[str] = None
    expected_reasoning_steps: Optional[List[str]] = None
    red_flags: Optional[List[str]] = None

class RagScenariosRequest(BaseModel):
    protocol_ids: List[int]

class RagScenariosResponse(BaseModel):
    scenarios: List[ScenarioSuggestion]

class RagGraphGenerateRequest(BaseModel):
    protocol_ids: List[int]
    scenario_title: str
    scenario_description: str

class RagGraphGenerateResponse(BaseModel):
    graph: GraphSchema
    generation_context: Optional[List[Dict[str, Any]]] = None
    validation_warnings: Optional[List[str]] = None
    generation_quality: Optional[Dict[str, Any]] = None

class AssignmentFromRagRequest(BaseModel):
    title: str
    description: Optional[str] = None
    time_limit_minutes: Optional[int] = Field(default=None, ge=5, le=24 * 60)
    graph_data: GraphSchema
    generation_context: Optional[List[Dict[str, Any]]] = None
    validation_warnings: List[str] = Field(default_factory=list)
