<script setup lang="ts">
import EmptyState from '~/components/shared/ui/EmptyState.vue'
import MetricCard from '~/components/shared/ui/MetricCard.vue'
import PageHeader from '~/components/shared/ui/PageHeader.vue'
import StatusChip from '~/components/shared/ui/StatusChip.vue'
import { prepareGraphForDisplay } from '~/composables/useGraphPreview'
import type {
  AttemptReviewStatus,
  EvaluationSnapshotListResponse,
  EvaluationSnapshotPublic,
  JsonObject,
  JsonValue,
  StudentAttemptPublic,
  StudentAttemptReviewUpdate,
} from '~/types/api'
import type { FlowEdge, FlowNode } from '~/types/graph'
import { getApiErrorMessage } from '~/utils/apiError'
import { createApiClient } from '~/utils/apiClient'

type AttemptDetail = StudentAttemptPublic
type PreviewGraph = { nodes?: unknown[]; edges?: unknown[] } | null
type FeedbackRow = {
  source: string
  target: string
  relation?: string
  label?: string
  kind?: string
}

definePageMeta({ keepalive: true })

const route = useRoute()
const auth = useAuthStore()
const api = createApiClient()

const attempt = ref<AttemptDetail | null>(null)
const loading = ref(false)
const errorText = ref('')
const graphNodes = ref<FlowNode[]>([])
const graphEdges = ref<FlowEdge[]>([])
const snapshots = ref<EvaluationSnapshotPublic[]>([])
const reviewSaving = ref(false)
const reviewNotice = ref('')
const reviewStatusDraft = ref<AttemptReviewStatus>('needs_review')
const teacherCommentDraft = ref('')
const teacherScoreDraft = ref<number | null>(null)
const teacherRubricDraft = ref<Record<string, number | null>>({
  clinical_reasoning: null,
  diagnostic_justification: null,
  treatment_safety: null,
  graph_structure: null,
})

const isTeacherLike = computed(() => auth.user?.role === 'teacher' || auth.user?.role === 'admin')

const reviewStatusItems = [
  { title: 'Требует проверки', value: 'needs_review' },
  { title: 'Принято', value: 'accepted' },
  { title: 'Нужна доработка', value: 'revision_requested' },
]

const teacherRubricItems = [
  { key: 'clinical_reasoning', label: 'Клиническое рассуждение' },
  { key: 'diagnostic_justification', label: 'Обоснование диагноза' },
  { key: 'treatment_safety', label: 'Лечение и безопасность' },
  { key: 'graph_structure', label: 'Структура графа' },
]

const snapshotHeaders = [
  { title: 'Версия', key: 'graph_version' },
  { title: 'Дата', key: 'created_at' },
  { title: 'Итог', key: 'score' },
  { title: 'Edge F1', key: 'edge_f1' },
  { title: 'Цепочка', key: 'path' },
  { title: 'Риск', key: 'safety' },
  { title: 'Алгоритм', key: 'algorithm_version' },
]

const attemptId = computed(() => Number(route.params.id))

function isJsonObject(value: JsonValue): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function textValue(value: unknown): string | undefined {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return undefined
}

function metricValue(key: string): JsonValue | undefined {
  return attempt.value?.metrics?.[key]
}

function snapshotMetric(snapshot: EvaluationSnapshotPublic, key: string): JsonValue | undefined {
  return snapshot.metrics?.[key]
}

function graphArrayLength(graph: JsonObject | null | undefined, key: string): number {
  const value = graph?.[key]
  return Array.isArray(value) ? value.length : 0
}

function toPreviewGraph(graph: JsonObject | null | undefined): PreviewGraph {
  if (!graph) return null
  return {
    nodes: Array.isArray(graph.nodes) ? graph.nodes : [],
    edges: Array.isArray(graph.edges) ? graph.edges : [],
  }
}

function feedbackRows(key: string): FeedbackRow[] {
  const value = metricValue(key)
  if (!Array.isArray(value)) return []
  return value.filter(isJsonObject).map((row) => ({
    source: textValue(row.source) || '—',
    target: textValue(row.target) || '—',
    relation: textValue(row.relation),
    label: textValue(row.label),
    kind: textValue(row.kind),
  }))
}

const metricCards = computed(() => {
  return [
    { label: 'Итог', value: metricPercent(metricValue('composite_score') ?? metricValue('f1_score')), color: 'primary', hint: 'Сводный балл с учётом связей и безопасности', icon: 'mdi-chart-donut' },
    { label: 'Точность связей', value: metricPercent(metricValue('precision')), color: 'success', hint: 'Доля верных связей студента', icon: 'mdi-crosshairs-gps' },
    { label: 'Полнота связей', value: metricPercent(metricValue('recall')), color: 'warning', hint: 'Доля найденных эталонных связей', icon: 'mdi-format-list-checks' },
    { label: 'Edge F1', value: metricPercent(metricValue('edge_f1') ?? metricValue('weighted_edge_f1')), color: 'secondary', hint: 'Баланс точности и полноты по рёбрам', icon: 'mdi-vector-line' },
    { label: 'Узлы', value: metricPercent(metricValue('node_coverage')), color: 'info', hint: 'Покрытие клинических понятий', icon: 'mdi-graph-outline' },
    { label: 'Цепочка', value: metricPercent(metricValue('directed_path_completeness')), color: 'warning', hint: 'Целостность клинического пути', icon: 'mdi-transit-connection-variant' },
  ]
})

const evaluationTiming = computed(() => {
  const timing = metricValue('evaluation_timing_ms')
  if (!timing || !isJsonObject(timing)) return null
  const total = Number(timing.total ?? timing.compute_total)
  const embedding = Number(timing.label_embedding)
  if (!Number.isFinite(total)) return null
  return {
    total: Math.round(total),
    embedding: Number.isFinite(embedding) ? Math.round(embedding) : null,
  }
})

const graphStats = computed(() => {
  return {
    studentEdges: jsonNumber(metricValue('student_edge_count'), graphArrayLength(attempt.value?.submitted_graph, 'edges')),
    referenceEdges: jsonNumber(metricValue('reference_edge_count')),
    edgePenalty: jsonNumber(metricValue('edge_count_penalty')),
  }
})

const missingEdges = computed(() => feedbackRows('missing_edges'))
const incorrectEdges = computed(() => feedbackRows('incorrect_edges'))
const safetyFindings = computed(() => feedbackRows('safety_findings'))

function jsonNumber(value: JsonValue | undefined, fallback = 0) {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function metricPercent(value: unknown) {
  const n = Number(value)
  return Number.isFinite(n) ? `${Math.round(n * 100)}%` : '—'
}

function snapshotPercent(snapshot: EvaluationSnapshotPublic, key: string) {
  return metricPercent(snapshotMetric(snapshot, key))
}

function snapshotScore(snapshot: EvaluationSnapshotPublic) {
  return metricPercent(snapshotMetric(snapshot, 'composite_score') ?? snapshotMetric(snapshot, 'f1_score'))
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ru-RU')
}

function statusText(value?: string | null) {
  if (value === 'accepted') return 'Принято'
  if (value === 'revision_requested') return 'Нужна доработка'
  return 'Ожидает проверки'
}

function normalizedTeacherScore(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(Number(value))) return null
  return Math.min(100, Math.max(0, Number(value))) / 100
}

function populateTeacherReviewDraft(res: StudentAttemptPublic) {
  reviewStatusDraft.value = res.review_status || 'needs_review'
  teacherCommentDraft.value = res.teacher_comment || ''
  teacherScoreDraft.value = res.teacher_score == null ? null : Math.round(res.teacher_score * 100)
  teacherRubricDraft.value = Object.fromEntries(teacherRubricItems.map(({ key }) => [
    key,
    res.teacher_rubric?.[key] == null ? null : Math.round(Number(res.teacher_rubric[key]) * 100),
  ]))
}

async function loadAttempt() {
  loading.value = true
  errorText.value = ''
  try {
    const res = await api.endpoint('GET', `/attempts/${attemptId.value}` as `/attempts/${number}`, {
      accessToken: auth.accessToken,
    })
    attempt.value = res
    populateTeacherReviewDraft(res)
    const prepared = prepareGraphForDisplay(toPreviewGraph(res.submitted_graph), { spacious: true })
    graphNodes.value = prepared.nodes
    graphEdges.value = prepared.edges
    await loadSnapshots()
  } catch (error) {
    errorText.value = getApiErrorMessage(error, 'Не удалось загрузить попытку')
  } finally {
    loading.value = false
  }
}

async function saveTeacherReview() {
  if (!attempt.value || !isTeacherLike.value) return
  reviewSaving.value = true
  reviewNotice.value = ''
  errorText.value = ''
  try {
    const body: StudentAttemptReviewUpdate = {
      review_status: reviewStatusDraft.value,
      teacher_comment: teacherCommentDraft.value || null,
      teacher_score: normalizedTeacherScore(teacherScoreDraft.value),
      teacher_rubric: Object.fromEntries(
        Object.entries(teacherRubricDraft.value)
          .filter(([, value]) => value != null)
          .map(([key, value]) => [key, normalizedTeacherScore(value)]),
      ),
    }
    const updated = await api.endpoint('PATCH', `/attempts/${attempt.value.id}/review` as `/attempts/${number}/review`, {
      accessToken: auth.accessToken,
      body,
    })
    attempt.value = updated
    populateTeacherReviewDraft(updated)
    reviewNotice.value = 'Оценка преподавателя сохранена.'
  } catch (error) {
    errorText.value = getApiErrorMessage(error, 'Не удалось сохранить оценку преподавателя')
  } finally {
    reviewSaving.value = false
  }
}

async function loadSnapshots() {
  try {
    const res: EvaluationSnapshotListResponse = await api.endpoint('GET', `/attempts/${attemptId.value}/snapshots` as `/attempts/${number}/snapshots`, {
      accessToken: auth.accessToken,
    })
    snapshots.value = res.items
  } catch {
    snapshots.value = []
  }
}

onMounted(loadAttempt)
</script>

<template>
  <v-container fluid class="attempt-page pa-3 pa-md-6">
    <PageHeader
      :title="attempt?.assignment_title || 'Моя сдача'"
      :subtitle="`Отправлено: ${formatDate(attempt?.created_at)}`"
    >
      <template #actions>
        <v-btn to="/dashboard" variant="text" color="primary" prepend-icon="mdi-arrow-left">
          К панели
        </v-btn>
        <StatusChip
          :status="attempt?.review_status"
          :text="statusText(attempt?.review_status)"
          size="large"
        />
      </template>
    </PageHeader>

    <v-alert v-if="errorText" type="error" variant="tonal" rounded="lg" class="mb-4">
      {{ errorText }}
    </v-alert>

    <v-row v-if="loading">
      <v-col v-for="n in 4" :key="n" cols="12" md="6">
        <v-skeleton-loader type="article" class="rounded-lg" />
      </v-col>
    </v-row>

    <template v-else-if="attempt">
      <v-card class="panel mb-4" elevation="0">
        <v-card-title>Условие задания</v-card-title>
        <v-card-text>
          <div class="task-description">{{ attempt.assignment_description || 'Описание задания недоступно.' }}</div>
          <div v-if="attempt.assignment_time_limit_minutes" class="text-caption text-medium-emphasis mt-2">
            Лимит времени на выполнение: {{ attempt.assignment_time_limit_minutes }} мин.
          </div>
        </v-card-text>
      </v-card>

      <v-row class="mb-2">
        <v-col v-for="metric in metricCards" :key="metric.label" cols="12" sm="6" lg="4" xl="2">
          <v-tooltip :text="metric.hint" location="top">
            <template #activator="{ props }">
              <MetricCard
                v-bind="props"
                :title="metric.label"
                :value="metric.value"
                :color="metric.color"
                :icon="metric.icon"
              />
            </template>
          </v-tooltip>
        </v-col>
      </v-row>

      <div v-if="evaluationTiming" class="d-flex flex-wrap ga-2 mb-4">
        <v-chip size="small" color="info" variant="tonal" prepend-icon="mdi-timer-outline">
          Проверка: {{ evaluationTiming.total }} мс
        </v-chip>
        <v-chip v-if="evaluationTiming.embedding != null" size="small" variant="tonal">
          Эмбеддинги: {{ evaluationTiming.embedding }} мс
        </v-chip>
      </div>

      <v-card class="panel mb-4" elevation="0">
        <v-card-title class="d-flex align-center">
          История автоматических проверок
          <v-spacer />
          <v-chip size="small" color="primary" variant="tonal">{{ snapshots.length }}</v-chip>
        </v-card-title>
        <v-card-text>
          <v-alert type="info" variant="tonal" density="compact" rounded="lg" class="mb-3">
            Каждая строка фиксирует отдельный расчет метрик: версию графа, дату, итоговую оценку, качество связей, полноту клинической цепочки и штраф безопасности.
          </v-alert>
          <v-data-table
            :headers="snapshotHeaders"
            :items="snapshots"
            density="compact"
            :items-per-page="5"
          >
            <template #item.created_at="{ item }">{{ formatDate(item.created_at) }}</template>
            <template #item.score="{ item }">
              <v-chip size="small" color="primary" variant="tonal">{{ snapshotScore(item) }}</v-chip>
            </template>
            <template #item.edge_f1="{ item }">{{ snapshotPercent(item, 'weighted_edge_f1') }}</template>
            <template #item.path="{ item }">{{ snapshotPercent(item, 'directed_path_completeness') }}</template>
            <template #item.safety="{ item }">{{ snapshotPercent(item, 'safety_penalty') }}</template>
            <template #item.algorithm_version="{ item }">{{ item.algorithm_version || '—' }}</template>
            <template #no-data>
              <EmptyState
                icon="mdi-history"
                title="История пока пуста"
                text="Новые автоматические проверки будут сохраняться здесь после применения миграции."
              />
            </template>
          </v-data-table>
        </v-card-text>
      </v-card>

      <v-alert
        v-if="graphStats.studentEdges === 0 && graphStats.referenceEdges > 0"
        type="warning"
        variant="tonal"
        class="mb-4"
        rounded="lg"
      >
        В решении нет связей между блоками. Такой граф не может получить высокую оценку: связи обязательны для клинической цепочки.
      </v-alert>

      <v-row>
        <v-col cols="12" lg="8">
          <v-card class="panel" elevation="0">
            <v-card-title class="d-flex align-center">
              Ваш граф
              <v-spacer />
              <v-chip size="small" color="primary" variant="tonal">
                Связей: {{ graphStats.studentEdges }}
              </v-chip>
            </v-card-title>
            <v-card-text>
              <div class="graph-view">
                <ClientOnly>
                  <GraphFlow
                    :key="`attempt-graph-${attempt.id}-${graphStats.studentEdges}`"
                    v-model:nodes="graphNodes"
                    v-model:edges="graphEdges"
                    :palette="[]"
                    read-only
                    preview-mode
                  />
                </ClientOnly>
              </div>
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12" lg="4">
          <v-card v-if="isTeacherLike" class="panel mb-4" elevation="0">
            <v-card-title>Оценка преподавателя</v-card-title>
            <v-card-text class="d-flex flex-column ga-3">
              <v-alert v-if="reviewNotice" type="success" variant="tonal" density="compact">
                {{ reviewNotice }}
              </v-alert>
              <v-select
                v-model="reviewStatusDraft"
                :items="reviewStatusItems"
                label="Решение по работе"
                variant="outlined"
                density="compact"
                hide-details
              />
              <v-text-field
                v-model.number="teacherScoreDraft"
                label="Итоговая оценка, 0–100"
                type="number"
                min="0"
                max="100"
                step="1"
                variant="outlined"
                density="compact"
                hint="Ручной балл хранится отдельно от автоматической оценки."
                persistent-hint
              />
              <v-expansion-panels variant="accordion" density="compact">
                <v-expansion-panel title="Подробная рубрика">
                  <v-expansion-panel-text>
                    <v-text-field
                      v-for="item in teacherRubricItems"
                      :key="item.key"
                      v-model.number="teacherRubricDraft[item.key]"
                      :label="`${item.label}, 0–100`"
                      type="number"
                      min="0"
                      max="100"
                      step="1"
                      variant="outlined"
                      density="compact"
                      class="mb-2"
                      hide-details
                    />
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
              <v-textarea
                v-model="teacherCommentDraft"
                label="Комментарий студенту"
                variant="outlined"
                density="compact"
                rows="4"
                auto-grow
                hide-details
              />
              <v-btn color="primary" :loading="reviewSaving" @click="saveTeacherReview">
                Сохранить оценку
              </v-btn>
            </v-card-text>
          </v-card>

          <v-card class="panel mb-4" elevation="0">
            <v-card-title>Комментарий преподавателя</v-card-title>
            <v-card-text>
              <v-chip v-if="attempt.teacher_score != null" color="primary" variant="tonal" class="mb-3">
                Оценка преподавателя: {{ Math.round(attempt.teacher_score * 100) }}/100
              </v-chip>
              <div v-if="attempt.teacher_comment" class="teacher-comment">
                {{ attempt.teacher_comment }}
              </div>
              <EmptyState
                v-else
                icon="mdi-message-text-outline"
                title="Комментария пока нет"
                text="Когда преподаватель проверит работу, обратная связь появится здесь."
              />
              <div v-if="attempt.reviewed_at" class="text-caption text-medium-emphasis mt-3">
                Проверено: {{ formatDate(attempt.reviewed_at) }}
              </div>
            </v-card-text>
          </v-card>

          <v-card class="panel" elevation="0">
            <v-card-title>Что улучшить</v-card-title>
            <v-card-text>
              <v-expansion-panels variant="accordion">
                <v-expansion-panel v-if="missingEdges.length" title="Пропущенные связи">
                  <v-expansion-panel-text>
                    <div v-for="(edge, index) in missingEdges" :key="`m-${index}`" class="feedback-row">
                      <strong>{{ edge.source }}</strong> → <strong>{{ edge.target }}</strong>
                      <span class="text-medium-emphasis">({{ edge.relation }})</span>
                    </div>
                  </v-expansion-panel-text>
                </v-expansion-panel>
                <v-expansion-panel v-if="incorrectEdges.length" title="Неверные связи">
                  <v-expansion-panel-text>
                    <div v-for="(edge, index) in incorrectEdges" :key="`i-${index}`" class="feedback-row incorrect">
                      <strong>{{ edge.source }}</strong> → <strong>{{ edge.target }}</strong>
                      <span class="text-medium-emphasis">({{ edge.relation }})</span>
                    </div>
                  </v-expansion-panel-text>
                </v-expansion-panel>
                <v-expansion-panel v-if="safetyFindings.length" title="Клинические риски">
                  <v-expansion-panel-text>
                    <div v-for="(finding, index) in safetyFindings" :key="`s-${index}`" class="feedback-row risk">
                      <strong>{{ finding.source }}</strong> → <strong>{{ finding.target }}</strong>
                      <span class="text-medium-emphasis">({{ finding.relation }})</span>
                    </div>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
              <EmptyState
                v-if="!missingEdges.length && !incorrectEdges.length && !safetyFindings.length"
                icon="mdi-check-circle-outline"
                title="Критичных замечаний нет"
                color="success"
              />
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </template>
  </v-container>
</template>

<style scoped>
.attempt-page {
  max-width: 1440px;
  margin: 0 auto;
}

.panel {
  border: 1px solid rgba(var(--v-border-color), 0.12);
  border-radius: 8px !important;
  background: rgba(var(--v-theme-surface), 0.94) !important;
}

.graph-view {
  height: 720px;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), 0.12);
  border-radius: 8px;
}

.graph-view :deep(.flow-wrap) {
  height: 720px;
}

.task-description {
  white-space: pre-wrap;
  line-height: 1.6;
}

.graph-view :deep(.canvas-toolbar) {
  display: none;
}

.teacher-comment {
  white-space: pre-wrap;
  line-height: 1.55;
  border-radius: 8px;
  padding: 14px;
  background: rgba(var(--v-theme-primary), 0.08);
  border: 1px solid rgba(var(--v-theme-primary), 0.16);
}

.feedback-row {
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 8px;
  background: rgba(var(--v-theme-warning), 0.1);
}

.feedback-row.incorrect,
.feedback-row.risk {
  background: rgba(var(--v-theme-error), 0.08);
}

@media (max-width: 720px) {
  .graph-view,
  .graph-view :deep(.flow-wrap) {
    height: 520px;
  }
}
</style>
