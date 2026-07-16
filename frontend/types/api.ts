export type JsonPrimitive = string | number | boolean | null
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[]

export interface JsonObject {
  [key: string]: JsonValue
}

export type Nullable<T> = T | null

export type NodeType =
  | 'PATIENT_PROFILE'
  | 'SYMPTOM'
  | 'EXAM'
  | 'LAB_TEST'
  | 'INSTRUMENTAL_TEST'
  | 'DIAGNOSIS'
  | 'MEDICATION'
  | 'SURGERY'
  | 'MONITORING'

export type EdgeType =
  | 'DETERMINES'
  | 'REQUIRES_CONFIRMATION'
  | 'EXCLUDES'
  | 'INDICATED_FOR'
  | 'CONTRAINDICATED_DUE_TO'

export type UserRole = 'student' | 'teacher' | 'expert' | 'admin'
export type AssignmentStatus =
  | 'draft'
  | 'ai_generated'
  | 'needs_teacher_review'
  | 'review_ready'
  | 'teacher_approved'
  | 'published'
  | 'archived'
export type AssignmentProgressStatus =
  | 'not_started'
  | 'in_progress'
  | 'submitted'
  | 'needs_revision'
  | 'completed'
export type AttemptReviewStatus = 'needs_review' | 'accepted' | 'revision_requested'
export type ExpertReviewItemType = 'student_attempt' | 'reference_graph' | 'assignment'
export type ExpertReviewStatus = 'draft' | 'submitted'
export type ValidationAcceptStatus = 'yes' | 'no'

export interface GraphNodeData {
  label: string
  category: NodeType
  description?: string | null
  protocol_refs?: JsonObject[]
  is_critical?: boolean
  source?: string | null
  confidence?: number | null
}

export interface GraphPosition {
  [key: string]: number
}

export interface GraphNode {
  id: string
  type?: string | null
  position: GraphPosition
  data: GraphNodeData
}

export interface GraphEdge {
  id: string
  type?: string | null
  source: string
  target: string
  label: EdgeType
  sourceHandle?: string | null
  targetHandle?: string | null
}

export interface GraphSchema {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface GraphEvaluationRequest {
  reference_graph_id: number
  assignment_id?: number | null
  student_id?: number | null
  student_graph: GraphSchema
  idempotency_key?: string | null
}

export interface GraphEvaluationResponse {
  precision: number
  recall: number
  f1_score: number
  missing_edges: Record<string, string>[]
  incorrect_edges: Record<string, string>[]
  message: string
  composite_score?: number | null
  edge_f1?: number | null
  weighted_precision?: number | null
  weighted_recall?: number | null
  weighted_edge_f1?: number | null
  node_coverage?: number | null
  chain_completeness?: number | null
  directed_path_completeness?: number | null
  category_accuracy?: number | null
  structural_correctness?: number | null
  safety_penalty?: number | null
  edge_count_penalty?: number | null
  student_edge_count?: number | null
  reference_edge_count?: number | null
  unsafe_extra_action?: number | null
  missing_critical_action?: number | null
  diagnostic_evidence_gap?: number | null
  diagnostic_evidence_findings?: Record<string, string>[] | null
  clinical_connectivity_gap?: number | null
  clinical_connectivity_findings?: Record<string, string>[] | null
  score_caps?: Record<string, JsonValue>[] | null
  safety_findings?: Record<string, string>[] | null
  missing_nodes?: string[] | null
  algorithm_version?: string | null
  attempt_id?: number | null
  evaluation_snapshot_id?: number | null
  graph_version?: number | null
  evaluation_timing_ms?: Record<string, number> | null
}

export interface UserRegisterRequest {
  email: string
  password: string
  full_name?: string | null
}

export interface UserLoginRequest {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface UserPublic {
  id: number
  email: string
  role: UserRole
  full_name: string | null
  specialty_id: number | null
  group_id: number | null
}

export interface UserCreateRequest {
  email: string
  password: string
  full_name?: string | null
  role?: UserRole
  specialty_id?: number | null
  group_id?: number | null
}

export interface UserUpdateRequest {
  email?: string | null
  password?: string | null
  full_name?: string | null
  role?: UserRole | null
  specialty_id?: number | null
  group_id?: number | null
}

export interface UserListResponse {
  items: UserPublic[]
}

export interface SpecialtyPublic {
  id: number
  name: string
  code: string | null
  description: string | null
}

export interface SpecialtyCreate {
  name: string
  code?: string | null
  description?: string | null
}

export interface SpecialtyListResponse {
  items: SpecialtyPublic[]
}

export interface StudentGroupPublic {
  id: number
  name: string
  specialty_id: number | null
  year: number | null
}

export interface StudentGroupCreate {
  name: string
  specialty_id?: number | null
  year?: number | null
}

export interface StudentGroupListResponse {
  items: StudentGroupPublic[]
}

export interface AssignmentTargetPublic {
  id: number
  assignment_id: number
  specialty_id: number | null
  group_id: number | null
}

export interface AssignmentTargetsUpdate {
  specialty_ids: number[]
  group_ids: number[]
}

export interface AssignmentPublic {
  id: number
  title: string
  description: string | null
  discipline_id: number
  reference_graph_id: number
  created_by_id: number | null
  created_by_email: string | null
  created_by_name: string | null
  status: AssignmentStatus | null
  review_notes: string | null
  approved_by_id: number | null
  approved_at: string | null
  published_at: string | null
  time_limit_minutes: number | null
  reference_status: string | null
  reference_validation_warnings: string[]
  reference_generation_quality: JsonObject | null
  protocol_id: number | null
  protocol_external_id: string | null
  protocol_title: string | null
  protocol_year: number | null
  protocol_version: string | null
  protocol_url: string | null
  protocol_category: string | null
  protocol_sections: string[]
  source_protocols: JsonObject[]
  targets: AssignmentTargetPublic[]
  progress_status: AssignmentProgressStatus | null
  latest_attempt_id: number | null
  latest_score: number | null
  started_at: string | null
  submitted_at: string | null
  completed_at: string | null
  deadline_at: string | null
}

export interface AssignmentProgressPublic {
  assignment_id: number
  student_id: number
  status: AssignmentProgressStatus
  latest_attempt_id: number | null
  latest_score: number | null
  started_at: string | null
  submitted_at: string | null
  completed_at: string | null
  deadline_at: string | null
}

export interface AssignmentCreate {
  title: string
  description?: string | null
  discipline_id: number
  reference_graph_id: number
  time_limit_minutes?: number | null
  status?: AssignmentStatus | null
}

export interface AssignmentDraftUpdate {
  title?: string | null
  description?: string | null
  time_limit_minutes?: number | null
  graph_data?: GraphSchema | null
  review_notes?: string | null
  status?: AssignmentStatus | null
}

export interface AssignmentPublishRequest {
  review_notes?: string | null
  force?: boolean
}

export interface AssignmentApproveReferenceRequest {
  review_notes?: string | null
  force?: boolean
}

export interface ReferenceGraphPublic {
  id: number
  title: string
  description: string | null
  graph_data: JsonObject | null
  discipline_id: number | null
  status: string | null
  source_type: string | null
  generation_context: JsonObject[] | null
  generation_quality: JsonObject | null
  protocol_id: number | null
  protocol_external_id: string | null
  protocol_title: string | null
  protocol_year: number | null
  protocol_version: string | null
  protocol_url: string | null
  protocol_category: string | null
  protocol_sections: string[]
  source_protocols: JsonObject[]
  validation_warnings: string[]
  review_notes: string | null
  approved_by_id: number | null
  approved_at: string | null
}

export interface AssignmentReviewBundle {
  assignment: AssignmentPublic
  reference_graph: ReferenceGraphPublic
}

export interface AssignmentListResponse {
  items: AssignmentPublic[]
}

export interface StudentAttemptPublic {
  id: number
  assignment_id: number | null
  assignment_title: string | null
  assignment_description: string | null
  assignment_time_limit_minutes: number | null
  reference_graph_id: number | null
  student_id: number
  student_email: string | null
  student_name: string | null
  submitted_graph: JsonObject | null
  metrics: JsonObject | null
  review_status: AttemptReviewStatus | null
  teacher_comment: string | null
  teacher_score: number | null
  teacher_rubric: Record<string, number> | null
  reviewed_by_id: number | null
  reviewed_at: string | null
  created_at: string | null
}

export interface StudentAttemptListResponse {
  items: StudentAttemptPublic[]
}

export interface EvaluationSnapshotPublic {
  id: number
  attempt_id: number | null
  assignment_id: number | null
  reference_graph_id: number | null
  student_id: number
  graph_version: number
  submitted_graph: JsonObject | null
  metrics: JsonObject | null
  recommendations: JsonObject | null
  algorithm_version: string | null
  reference_content_hash: string | null
  embedding_model_version: string | null
  created_at: string | null
}

export interface EvaluationSnapshotListResponse {
  items: EvaluationSnapshotPublic[]
}

export interface StudentAttemptReviewUpdate {
  review_status: AttemptReviewStatus
  teacher_comment?: string | null
  teacher_score?: number | null
  teacher_rubric?: {
    clinical_reasoning?: number | null
    diagnostic_justification?: number | null
    treatment_safety?: number | null
    graph_structure?: number | null
  } | null
}

export interface ExpertReviewPublic {
  id: number
  reviewer_id: number
  reviewer_email: string | null
  reviewer_name: string | null
  item_type: ExpertReviewItemType
  item_id: number
  assignment_id: number | null
  reference_graph_id: number | null
  student_attempt_id: number | null
  score: number | null
  step_scores: JsonObject | null
  issue_tags: string[]
  comment: string | null
  recommendation: string | null
  status: ExpertReviewStatus | null
  created_at: string | null
  updated_at: string | null
}

export interface ExpertReviewUpsert {
  item_type: ExpertReviewItemType
  item_id: number
  score?: number | null
  step_scores?: JsonObject | null
  issue_tags?: string[]
  comment?: string | null
  recommendation?: string | null
  status?: ExpertReviewStatus
}

export interface ExpertReviewItem {
  item_type: ExpertReviewItemType
  item_id: number
  title: string
  status: string | null
  assignment_id: number | null
  assignment_title: string | null
  reference_graph_id: number | null
  student_attempt_id: number | null
  student_id: number | null
  student_email: string | null
  student_name: string | null
  reference_graph: JsonObject | null
  student_graph: JsonObject | null
  metrics: JsonObject | null
  validation_warnings: string[]
  generation_quality: JsonObject | null
  existing_review: ExpertReviewPublic | null
}

export interface ExpertReviewItemListResponse {
  items: ExpertReviewItem[]
}

export interface ExpertReviewListResponse {
  items: ExpertReviewPublic[]
}

export interface ValidationRatingPublic {
  review_item_id: string
  score: number | null
  accept: ValidationAcceptStatus | null
  confidence: number | null
  comment: string | null
  status: ExpertReviewStatus | null
  updated_at: string | null
}

export interface ValidationRatingUpsert {
  review_item_id: string
  score: number
  accept?: ValidationAcceptStatus | null
  confidence?: number | null
  comment?: string | null
  status?: ExpertReviewStatus
}

export interface ValidationVariantBlinded {
  review_item_id: string
  case_title: string | null
  case_prompt: string | null
  graph_under_review: string | null
  student_graph: JsonObject | null
  display_order: number | null
  my_rating: ValidationRatingPublic | null
}

export interface ValidationItemsResponse {
  cohort: string
  total: number
  rated: number
  items: ValidationVariantBlinded[]
}

export interface AssignmentDraftResponse {
  title: string
  student_prompt: string
  checklist: string[]
  commentary: string
  reference_graph_id: number
}

export interface GraphHintsRequest {
  reference_graph_id: number
  student_graph: GraphSchema
  missing_edges?: Record<string, string>[]
  incorrect_edges?: Record<string, string>[]
}

export interface HintItem {
  text: string
  priority: number
}

export interface GraphHintsResponse {
  hints: HintItem[]
  summary: string
}

export interface GraphFeedbackResponse {
  feedback: string
}

export interface ClinicalTaskGenerateRequest {
  protocol_id: number
}

export interface ClinicalTaskResponse {
  id: number
  protocol_id: number
  case_description: string
  expected_diagnosis: string | null
  expected_treatment: string | null
}

export interface StudentAnswerRequest {
  student_answer: string
}

export interface ValidationResponse {
  id: number
  task_id: number
  score: number
  validation_result: JsonObject
}

export interface ClinicalProtocolPublic {
  id: number
  external_id: string | null
  title: string
  category: string | null
  version: string | null
  year: number | null
  url: string | null
  mkb_categories: string[] | null
  medical_sections: string[] | null
}

export interface ProtocolListResponse {
  items: ClinicalProtocolPublic[]
  total: number
}

export interface ClinicalProtocolDetail extends ClinicalProtocolPublic {
  text_content: string
}

export interface RagAskRequest {
  question: string
  protocol_id?: number | null
}

export interface RagSource {
  id: string
  protocol_id: number
  protocol_title: string
  text: string
}

export interface RagAskResponse {
  answer: string
  sources: RagSource[]
}

export interface RagSearchResult {
  chunk_id: number
  protocol_id: number
  protocol_title: string
  text: string
}

export interface ScenarioSuggestion {
  title: string
  description: string
  difficulty: string | null
  target_competency: string | null
  expected_reasoning_steps: string[] | null
  red_flags: string[] | null
}

export interface RagScenariosRequest {
  protocol_ids: number[]
}

export interface RagScenariosResponse {
  scenarios: ScenarioSuggestion[]
}

export interface RagGraphGenerateRequest {
  protocol_ids: number[]
  scenario_title: string
  scenario_description: string
}

export interface RagGraphGenerateResponse {
  graph: GraphSchema
  generation_context: JsonObject[] | null
  validation_warnings: string[] | null
  generation_quality: JsonObject | null
}

export interface AssignmentFromRagRequest {
  title: string
  description?: string | null
  time_limit_minutes?: number | null
  graph_data: GraphSchema
  generation_context?: JsonObject[] | null
  validation_warnings?: string[]
}

export interface ConceptSuggestion {
  id: number
  name: string
  category: string
  external_id: string | null
  source: string | null
}

export interface ConceptPaletteItem {
  id: number
  label: string
  category: string
  source: string | null
}

export interface ConceptPaletteResponse {
  items: ConceptPaletteItem[]
  total?: number
}

export interface AssignmentPaletteResponse {
  items: ConceptPaletteItem[]
  categories: string[]
  scoped: boolean
  keyword_count: number
}

export type BenchmarkCsvDelimiter = ',' | ';'
export type BenchmarkAnalyzeDelimiter = 'auto' | BenchmarkCsvDelimiter

export interface BenchmarkArtifactInfo {
  name: string
  exists: boolean
  size_bytes: number
  updated_at: string | null
  download_url: string | null
}

export type BenchmarkRow = Record<string, unknown>

export interface BenchmarkSummary {
  rag: {
    seed_cases: number | null
    generated_at: string | null
    summary: JsonObject | null
  }
  rag_ablation: {
    generated_at: string | null
    summary_by_mode: Record<string, JsonObject> | null
  }
  graph: {
    seed_cases: number | null
    generated_at: string | null
    summary: JsonObject | null
    reference_quality: JsonObject | null
  }
  cardiology: {
    seed_cases: number | null
    generated_at: string | null
    summary: JsonObject | null
    parameters: JsonObject | null
  }
  expert: JsonObject | null
  artifacts: BenchmarkArtifactInfo[]
}

export interface BenchmarkDetails {
  rag: {
    results: BenchmarkRow[]
    misses: BenchmarkRow[]
    ablation_results: BenchmarkRow[]
  }
  graph: {
    results: BenchmarkRow[]
    reference_quality: BenchmarkRow[]
  }
  cardiology: {
    tasks: BenchmarkRow[]
    results: BenchmarkRow[]
    reference_quality: BenchmarkRow[]
    expert_ratings: BenchmarkRow[]
    expert_items: BenchmarkRow[]
    expert_by_expert: BenchmarkRow[]
    expert_by_pattern: BenchmarkRow[]
    pattern_summary: BenchmarkRow[]
    baseline_comparison: BenchmarkRow[]
    real_baseline_comparison: BenchmarkRow[]
    recommendations: BenchmarkRow[]
  }
  expert: {
    items: BenchmarkRow[]
    by_expert: BenchmarkRow[]
    by_expected_pattern: BenchmarkRow[]
    baseline_comparison: BenchmarkRow[]
    skipped_rows: BenchmarkRow[]
    inter_rater_pairs: BenchmarkRow[]
  }
  generation: {
    generated_at?: string
    summary?: JsonObject | null
    items?: BenchmarkRow[]
  }
  problems: BenchmarkRow[]
  history: BenchmarkRow[]
}

export interface BenchmarkActionResponse {
  ok?: boolean
  message?: string | null
  [key: string]: JsonValue | undefined
}

export interface BenchmarkRagSeedRequest {
  target: number
}

export interface BenchmarkRagRunRequest {
  limit: number | null
  ablation: boolean
}

export interface BenchmarkGraphSeedRequest {
  target: number
}

export interface BenchmarkGraphRunRequest {
  limit: number | null
  use_embeddings: boolean
}

export interface BenchmarkCardiologySyntheticRunRequest {
  case_count: number
  expert_count: number
  seed: number
  use_embeddings: boolean
}

export interface BenchmarkCardiologyDemoImportRequest {
  refresh_timestamps: boolean
}

export interface BenchmarkExpertExportRequest {
  shuffle: boolean
  shuffle_seed: number
  delimiter: BenchmarkCsvDelimiter
}

export interface BenchmarkExpertAnalyzeRequest {
  csv_text: string
  delimiter: BenchmarkAnalyzeDelimiter
}

export interface BenchmarkGenerationAuditRequest {
  limit: number
}

export interface ApiEndpoint<TResponse, TBody = never> {
  response: TResponse
  body: TBody
}

export interface ApiEndpointMap {
  GET: {
    '/auth/me': ApiEndpoint<UserPublic>
    '/admin/users': ApiEndpoint<UserListResponse>
    '/admin/specialties': ApiEndpoint<SpecialtyListResponse>
    '/admin/groups': ApiEndpoint<StudentGroupListResponse>
    '/assignments': ApiEndpoint<AssignmentListResponse>
    '/attempts/me': ApiEndpoint<StudentAttemptListResponse>
    '/attempts': ApiEndpoint<StudentAttemptListResponse>
    '/expert/items': ApiEndpoint<ExpertReviewItemListResponse>
    '/expert/reviews': ApiEndpoint<ExpertReviewListResponse>
    '/expert/validation/items': ApiEndpoint<ValidationItemsResponse>
    '/benchmarks/summary': ApiEndpoint<BenchmarkSummary>
    '/benchmarks/details': ApiEndpoint<BenchmarkDetails>
    '/protocols': ApiEndpoint<ProtocolListResponse>
    '/protocols/sections': ApiEndpoint<string[]>
    '/rag/search': ApiEndpoint<RagSearchResult[]>
    '/concepts/suggest': ApiEndpoint<ConceptSuggestion[]>
    '/concepts/palette': ApiEndpoint<ConceptPaletteResponse>
    [path: `/assignments/${number}`]: ApiEndpoint<AssignmentPublic>
    [path: `/assignments/${number}/attempts`]: ApiEndpoint<StudentAttemptListResponse>
    [path: `/assignments/${number}/initial-nodes`]: ApiEndpoint<GraphNode[]>
    [path: `/assignments/${number}/palette`]: ApiEndpoint<AssignmentPaletteResponse>
    [path: `/assignments/${number}/reference`]: ApiEndpoint<GraphSchema>
    [path: `/assignments/${number}/review-bundle`]: ApiEndpoint<AssignmentReviewBundle>
    [path: `/attempts/${number}`]: ApiEndpoint<StudentAttemptPublic>
    [path: `/attempts/${number}/snapshots`]: ApiEndpoint<EvaluationSnapshotListResponse>
    [path: `/protocols/${number}`]: ApiEndpoint<ClinicalProtocolDetail>
  }
  POST: {
    '/auth/login': ApiEndpoint<TokenResponse, UserLoginRequest>
    '/auth/register': ApiEndpoint<UserPublic, UserRegisterRequest>
    '/admin/users': ApiEndpoint<UserPublic, UserCreateRequest>
    '/admin/specialties': ApiEndpoint<SpecialtyPublic, SpecialtyCreate>
    '/admin/groups': ApiEndpoint<StudentGroupPublic, StudentGroupCreate>
    '/assignments': ApiEndpoint<AssignmentPublic, AssignmentCreate>
    '/assignments/from-rag': ApiEndpoint<AssignmentPublic, AssignmentFromRagRequest>
    '/evaluate': ApiEndpoint<GraphEvaluationResponse, GraphEvaluationRequest>
    '/expert/reviews': ApiEndpoint<ExpertReviewPublic, ExpertReviewUpsert>
    '/expert/validation/ratings': ApiEndpoint<ValidationRatingPublic, ValidationRatingUpsert>
    '/benchmarks/rag/seed': ApiEndpoint<BenchmarkActionResponse, BenchmarkRagSeedRequest>
    '/benchmarks/rag/run': ApiEndpoint<BenchmarkActionResponse, BenchmarkRagRunRequest>
    '/benchmarks/graph/seed': ApiEndpoint<BenchmarkActionResponse, BenchmarkGraphSeedRequest>
    '/benchmarks/graph/run': ApiEndpoint<BenchmarkActionResponse, BenchmarkGraphRunRequest>
    '/benchmarks/cardiology/synthetic/run': ApiEndpoint<BenchmarkActionResponse, BenchmarkCardiologySyntheticRunRequest>
    '/benchmarks/cardiology/synthetic/import-demo': ApiEndpoint<BenchmarkActionResponse, BenchmarkCardiologyDemoImportRequest>
    '/benchmarks/expert/export': ApiEndpoint<BenchmarkActionResponse, BenchmarkExpertExportRequest>
    '/benchmarks/tables/export': ApiEndpoint<BenchmarkActionResponse, Record<string, never>>
    '/benchmarks/generation/audit': ApiEndpoint<BenchmarkActionResponse, BenchmarkGenerationAuditRequest>
    '/benchmarks/expert/analyze': ApiEndpoint<BenchmarkActionResponse, BenchmarkExpertAnalyzeRequest>
    '/graph/feedback': ApiEndpoint<GraphFeedbackResponse, GraphHintsRequest>
    '/graph/hints': ApiEndpoint<GraphHintsResponse, GraphHintsRequest>
    '/rag/ask': ApiEndpoint<RagAskResponse, RagAskRequest>
    '/rag/reference-graph': ApiEndpoint<RagGraphGenerateResponse, RagGraphGenerateRequest>
    '/rag/scenarios': ApiEndpoint<RagScenariosResponse, RagScenariosRequest>
    '/rag/tasks': ApiEndpoint<ClinicalTaskResponse, ClinicalTaskGenerateRequest>
    [path: `/assignments/${number}/generate`]: ApiEndpoint<AssignmentDraftResponse>
    [path: `/assignments/${number}/approve-reference`]: ApiEndpoint<AssignmentReviewBundle, AssignmentApproveReferenceRequest>
    [path: `/assignments/${number}/publish`]: ApiEndpoint<AssignmentReviewBundle, AssignmentPublishRequest>
    [path: `/assignments/${number}/start`]: ApiEndpoint<AssignmentProgressPublic>
    [path: `/rag/tasks/${number}/validate`]: ApiEndpoint<ValidationResponse, StudentAnswerRequest>
  }
  PATCH: {
    [path: `/admin/users/${number}`]: ApiEndpoint<UserPublic, UserUpdateRequest>
    [path: `/assignments/${number}/draft`]: ApiEndpoint<AssignmentReviewBundle, AssignmentDraftUpdate>
    [path: `/attempts/${number}/review`]: ApiEndpoint<StudentAttemptPublic, StudentAttemptReviewUpdate>
  }
  PUT: {
    [path: `/assignments/${number}/targets`]: ApiEndpoint<AssignmentPublic, AssignmentTargetsUpdate>
  }
  DELETE: {
    [path: `/admin/users/${number}`]: ApiEndpoint<void>
    [path: `/admin/specialties/${number}`]: ApiEndpoint<void>
    [path: `/admin/groups/${number}`]: ApiEndpoint<void>
    [path: `/assignments/${number}`]: ApiEndpoint<void>
  }
}

export type ApiMethod = keyof ApiEndpointMap
export type ApiEndpointPath<TMethod extends ApiMethod> = Extract<keyof ApiEndpointMap[TMethod], string>

export type ApiEndpointResponse<
  TMethod extends ApiMethod,
  TPath extends ApiEndpointPath<TMethod>,
> = ApiEndpointMap[TMethod][TPath] extends ApiEndpoint<infer TResponse, unknown> ? TResponse : never

export type ApiEndpointBody<
  TMethod extends ApiMethod,
  TPath extends ApiEndpointPath<TMethod>,
> = ApiEndpointMap[TMethod][TPath] extends ApiEndpoint<unknown, infer TBody> ? TBody : never
