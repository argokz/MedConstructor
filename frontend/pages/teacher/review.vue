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
  StudentAttemptListResponse,
  StudentAttemptPublic,
  StudentAttemptReviewUpdate,
} from '~/types/api'
import type { FlowEdge, FlowNode } from '~/types/graph'
import { getApiErrorMessage } from '~/utils/apiError'
import { createApiClient } from '~/utils/apiClient'

definePageMeta({
  middleware: 'teacher',
  keepalive: true,
})

type ReviewStatus = AttemptReviewStatus
type AttemptRow = StudentAttemptPublic
type PreviewGraph = { nodes?: unknown[]; edges?: unknown[] } | null
type FeedbackRow = {
  source: string
  target: string
  relation?: string
  label?: string
  kind?: string
}

const auth = useAuthStore()
const api = createApiClient()

const attempts = ref<AttemptRow[]>([])
const selectedAttempt = ref<AttemptRow | null>(null)
const loading = ref(false)
const saving = ref(false)
const errorText = ref('')
const notice = ref('')
const statusDraft = ref<ReviewStatus>('needs_review')
const commentDraft = ref('')
const teacherScoreDraft = ref<number | null>(null)
const rubricDraft = ref<Record<string, number | null>>({
  clinical_reasoning: null,
  diagnostic_justification: null,
  treatment_safety: null,
  graph_structure: null,
})
const reviewNodes = ref<FlowNode[]>([])
const reviewEdges = ref<FlowEdge[]>([])
const statusFilter = ref<'all' | ReviewStatus>('all')
const demoOnly = ref(false)
const snapshotsByAttempt = ref<Record<number, EvaluationSnapshotPublic[]>>({})
const snapshotsLoading = ref(false)

const reviewStatusItems = [
  { title: 'Требует проверки', value: 'needs_review' },
  { title: 'Принято', value: 'accepted' },
  { title: 'Нужна доработка', value: 'revision_requested' },
]

const rubricItems = [
  { key: 'clinical_reasoning', label: 'Клиническое рассуждение' },
  { key: 'diagnostic_justification', label: 'Обоснование диагноза' },
  { key: 'treatment_safety', label: 'Лечение и безопасность' },
  { key: 'graph_structure', label: 'Структура графа' },
]

const statusFilterItems = [
  { title: 'Все статусы', value: 'all' },
  ...reviewStatusItems,
]

const filteredAttempts = computed(() =>
  attempts.value.filter((attempt) => {
    if (statusFilter.value !== 'all' && attempt.review_status !== statusFilter.value) return false
    if (demoOnly.value && !metricValue(attempt, 'demo_workflow')) return false
    return true
  })
)

const statusCounts = computed(() => ({
  all: attempts.value.length,
  needs_review: attempts.value.filter((attempt) => attempt.review_status === 'needs_review').length,
  accepted: attempts.value.filter((attempt) => attempt.review_status === 'accepted').length,
  revision_requested: attempts.value.filter((attempt) => attempt.review_status === 'revision_requested').length,
  demo: attempts.value.filter((attempt) => Boolean(metricValue(attempt, 'demo_workflow'))).length,
}))

const headers = [
  { title: 'Студент', key: 'student' },
  { title: 'Задание', key: 'assignment_title' },
  { title: 'Вариант', key: 'variant' },
  { title: 'Авто', key: 'score' },
  { title: 'Преподаватель', key: 'teacher_score' },
  { title: 'Статус', key: 'review_status' },
  { title: 'Дата', key: 'created_at' },
  { title: '', key: 'actions', sortable: false, align: 'end' as const },
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

function isJsonObject(value: JsonValue): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function textValue(value: unknown): string | undefined {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return undefined
}

function metricValue(row: AttemptRow | null | undefined, key: string): JsonValue | undefined {
  return row?.metrics?.[key]
}

function toPreviewGraph(graph: JsonObject | null | undefined): PreviewGraph {
  if (!graph) return null
  return {
    nodes: Array.isArray(graph.nodes) ? graph.nodes : [],
    edges: Array.isArray(graph.edges) ? graph.edges : [],
  }
}

function feedbackRows(row: AttemptRow | null | undefined, key: string): FeedbackRow[] {
  const value = metricValue(row, key)
  if (!Array.isArray(value)) return []
  return value.filter(isJsonObject).map((item) => ({
    source: textValue(item.source) || '—',
    target: textValue(item.target) || '—',
    relation: textValue(item.relation),
    label: textValue(item.label),
    kind: textValue(item.kind),
  }))
}

function textList(row: AttemptRow | null | undefined, key: string): string[] {
  const value = metricValue(row, key)
  if (!Array.isArray(value)) return []
  return value.map(textValue).filter((item): item is string => Boolean(item))
}

function scorePercent(row: AttemptRow) {
  const score = Number(metricValue(row, 'composite_score') ?? metricValue(row, 'f1_score'))
  return Number.isFinite(score) ? `${Math.round(score * 100)}%` : '—'
}

function metricPercent(value: unknown) {
  const score = Number(value)
  return Number.isFinite(score) ? `${Math.round(score * 100)}%` : '—'
}

function normalizedScore(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(Number(value))) return null
  return Math.min(100, Math.max(0, Number(value))) / 100
}

function snapshotMetric(row: EvaluationSnapshotPublic, key: string): JsonValue | undefined {
  return row.metrics?.[key]
}

function snapshotScore(row: EvaluationSnapshotPublic) {
  return metricPercent(snapshotMetric(row, 'composite_score') ?? snapshotMetric(row, 'f1_score'))
}

function snapshotPercent(row: EvaluationSnapshotPublic, key: string) {
  return metricPercent(snapshotMetric(row, key))
}

function shortText(value?: string | null, limit = 140) {
  if (!value) return '—'
  return value.length > limit ? `${value.slice(0, limit)}...` : value
}

function variantText(row?: AttemptRow | null) {
  const variant = textValue(metricValue(row, 'benchmark_variant_id'))
  const pattern = textValue(metricValue(row, 'expected_pattern_ru') || metricValue(row, 'expected_pattern'))
  if (variant && pattern) return `${variant} · ${pattern}`
  return variant || pattern || '—'
}

function recommendationText(row?: AttemptRow | null) {
  return textValue(metricValue(row, 'system_recommendation')) || row?.teacher_comment || '—'
}

const selectedMetricCards = computed(() => {
  return [
    { label: 'Итог', value: metricPercent(metricValue(selectedAttempt.value, 'composite_score') ?? metricValue(selectedAttempt.value, 'f1_score')), color: 'primary', hint: 'Сводный балл решения: учитывает связи, полноту понятий, направление клинической цепочки и безопасность.', icon: 'mdi-chart-donut' },
    { label: 'Точность', value: metricPercent(metricValue(selectedAttempt.value, 'precision')), color: 'success', hint: 'Какая доля связей студента совпала с эталоном.', icon: 'mdi-crosshairs-gps' },
    { label: 'Полнота', value: metricPercent(metricValue(selectedAttempt.value, 'recall')), color: 'warning', hint: 'Какая доля эталонных связей была найдена в решении студента.', icon: 'mdi-format-list-checks' },
    { label: 'Edge F1', value: metricPercent(metricValue(selectedAttempt.value, 'edge_f1') ?? metricValue(selectedAttempt.value, 'weighted_edge_f1')), color: 'secondary', hint: 'Баланс точности и полноты по связям графа.', icon: 'mdi-vector-line' },
    { label: 'Узлы', value: metricPercent(metricValue(selectedAttempt.value, 'node_coverage')), color: 'info', hint: 'Доля важных клинических понятий эталона, которые студент включил в граф.', icon: 'mdi-graph-outline' },
    { label: 'Цепочка', value: metricPercent(metricValue(selectedAttempt.value, 'directed_path_completeness')), color: 'warning', hint: 'Сохранился ли путь от симптомов и обследований к диагнозу и действиям.', icon: 'mdi-transit-connection-variant' },
    { label: 'Категории', value: metricPercent(metricValue(selectedAttempt.value, 'category_accuracy')), color: 'info', hint: 'Насколько правильно выбраны типы узлов: симптом, диагноз, лекарство, мониторинг и т.д.', icon: 'mdi-shape-outline' },
    { label: 'Риск', value: metricPercent(metricValue(selectedAttempt.value, 'safety_penalty')), color: 'error', hint: 'Штраф за опасные лишние действия или пропуск критически важных действий.', icon: 'mdi-shield-alert-outline' },
  ]
})

const selectedEvaluationTiming = computed(() => {
  const timing = metricValue(selectedAttempt.value, 'evaluation_timing_ms')
  if (!timing || !isJsonObject(timing)) return null
  const total = Number(timing.total ?? timing.compute_total)
  const embedding = Number(timing.label_embedding)
  if (!Number.isFinite(total)) return null
  return {
    total: Math.round(total),
    embedding: Number.isFinite(embedding) ? Math.round(embedding) : null,
  }
})

const selectedSafetyFindings = computed(() => feedbackRows(selectedAttempt.value, 'safety_findings'))
const selectedMissingEdges = computed(() => feedbackRows(selectedAttempt.value, 'missing_edges'))
const selectedMissingNodes = computed(() => textList(selectedAttempt.value, 'missing_nodes'))
const selectedSnapshots = computed(() =>
  selectedAttempt.value ? (snapshotsByAttempt.value[selectedAttempt.value.id] || []) : []
)

function formatDate(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ru-RU')
}

function statusText(value?: string | null) {
  return reviewStatusItems.find((item) => item.value === value)?.title || 'Требует проверки'
}

function selectAttempt(row: AttemptRow) {
  selectedAttempt.value = row
  statusDraft.value = row.review_status || 'needs_review'
  commentDraft.value = row.teacher_comment || ''
  teacherScoreDraft.value = row.teacher_score == null ? null : Math.round(row.teacher_score * 100)
  rubricDraft.value = Object.fromEntries(rubricItems.map(({ key }) => [
    key,
    row.teacher_rubric?.[key] == null ? null : Math.round(Number(row.teacher_rubric[key]) * 100),
  ]))
  const prepared = prepareGraphForDisplay(toPreviewGraph(row.submitted_graph), { spacious: true })
  reviewNodes.value = prepared.nodes
  reviewEdges.value = prepared.edges
  void loadSnapshotsForAttempt(row.id)
}

async function loadSnapshotsForAttempt(attemptId: number) {
  if (snapshotsByAttempt.value[attemptId]) return
  snapshotsLoading.value = true
  try {
    const res: EvaluationSnapshotListResponse = await api.endpoint('GET', `/attempts/${attemptId}/snapshots` as `/attempts/${number}/snapshots`, {
      accessToken: auth.accessToken,
    })
    snapshotsByAttempt.value = {
      ...snapshotsByAttempt.value,
      [attemptId]: res.items,
    }
  } catch {
    snapshotsByAttempt.value = {
      ...snapshotsByAttempt.value,
      [attemptId]: [],
    }
  } finally {
    snapshotsLoading.value = false
  }
}

async function loadAttempts() {
  loading.value = true
  errorText.value = ''
  try {
    const res: StudentAttemptListResponse = await api.endpoint('GET', '/attempts', {
      accessToken: auth.accessToken,
    })
    attempts.value = res.items
    if (!selectedAttempt.value && attempts.value.length) {
      selectAttempt(attempts.value[0])
    } else if (selectedAttempt.value) {
      const updated = attempts.value.find((item) => item.id === selectedAttempt.value?.id)
      if (updated) selectAttempt(updated)
    }
  } catch (error) {
    errorText.value = getApiErrorMessage(error, 'Не удалось загрузить сдачи')
  } finally {
    loading.value = false
  }
}

async function saveReview() {
  if (!selectedAttempt.value) return
  saving.value = true
  errorText.value = ''
  notice.value = ''
  try {
    const body: StudentAttemptReviewUpdate = {
      review_status: statusDraft.value,
      teacher_comment: commentDraft.value || null,
      teacher_score: normalizedScore(teacherScoreDraft.value),
      teacher_rubric: Object.fromEntries(
        Object.entries(rubricDraft.value)
          .filter(([, value]) => value != null)
          .map(([key, value]) => [key, normalizedScore(value)]),
      ),
    }
    const updated = await api.endpoint('PATCH', `/attempts/${selectedAttempt.value.id}/review` as `/attempts/${number}/review`, {
      accessToken: auth.accessToken,
      body,
    })
    attempts.value = attempts.value.map((item) => item.id === updated.id ? updated : item)
    selectAttempt(updated)
    notice.value = 'Ревью сохранено'
  } catch (error) {
    errorText.value = getApiErrorMessage(error, 'Не удалось сохранить ревью')
  } finally {
    saving.value = false
  }
}

onMounted(loadAttempts)
</script>

<template>
  <v-container fluid class="review-page pa-3 pa-md-6">
    <PageHeader
      eyebrow="Преподаватель"
      title="Проверка заданий"
      subtitle="Просмотр сдач студентов, автоматических метрик и ручная обратная связь."
    >
      <template #actions>
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="loadAttempts">
          Обновить
        </v-btn>
      </template>
    </PageHeader>

    <v-alert v-if="errorText" type="error" variant="tonal" rounded="lg" class="mb-4" closable @click:close="errorText = ''">
      {{ errorText }}
    </v-alert>
    <v-alert v-if="notice" type="success" variant="tonal" rounded="lg" class="mb-4" closable @click:close="notice = ''">
      {{ notice }}
    </v-alert>

    <v-row>
      <v-col cols="12" lg="7">
        <v-card class="panel" elevation="0">
          <v-card-title class="d-flex align-center">
            Сдачи
            <v-spacer />
            <v-chip size="small" color="primary" variant="tonal">{{ filteredAttempts.length }} / {{ attempts.length }}</v-chip>
          </v-card-title>
          <v-card-text>
            <div class="review-filters mb-3">
              <v-select
                v-model="statusFilter"
                :items="statusFilterItems"
                label="Статус"
                variant="outlined"
                density="compact"
                hide-details
              />
              <v-switch
                v-model="demoOnly"
                label="Только демо-кардиология"
                color="primary"
                density="compact"
                hide-details
              />
              <div class="review-counts">
                <StatusChip status="info" :text="`Всего: ${statusCounts.all}`" />
                <StatusChip status="primary" :text="`Демо: ${statusCounts.demo}`" />
                <StatusChip status="accepted" :text="`Принято: ${statusCounts.accepted}`" />
                <StatusChip status="revision_requested" :text="`Доработка: ${statusCounts.revision_requested}`" />
                <StatusChip status="needs_review" :text="`Новые: ${statusCounts.needs_review}`" />
              </div>
            </div>
            <v-data-table
              :headers="headers"
              :items="filteredAttempts"
              :loading="loading"
              density="comfortable"
              :items-per-page="10"
              class="attempt-table"
            >
              <template #item.student="{ item }">
                <div class="font-weight-bold">{{ item.student_name || item.student_email || `Студент #${item.student_id}` }}</div>
                <div class="text-caption text-medium-emphasis">{{ item.student_email }}</div>
              </template>
              <template #item.assignment_title="{ item }">{{ item.assignment_title || 'Без задания' }}</template>
              <template #item.variant="{ item }">
                <span class="text-body-2">{{ shortText(variantText(item), 90) }}</span>
              </template>
              <template #item.score="{ item }">
                <v-chip size="small" color="success" variant="tonal">{{ scorePercent(item) }}</v-chip>
              </template>
              <template #item.teacher_score="{ item }">
                <v-chip v-if="item.teacher_score != null" size="small" color="primary" variant="tonal">
                  {{ Math.round(item.teacher_score * 100) }}%
                </v-chip>
                <span v-else>—</span>
              </template>
              <template #item.review_status="{ item }">
                <StatusChip :status="item.review_status" :text="statusText(item.review_status)" />
              </template>
              <template #item.created_at="{ item }">{{ formatDate(item.created_at) }}</template>
              <template #item.actions="{ item }">
                <v-btn icon="mdi-eye-outline" size="small" variant="text" color="primary" @click="selectAttempt(item)" />
                <v-btn :to="`/student/attempts/${item.id}`" icon="mdi-open-in-new" size="small" variant="text" color="secondary" />
              </template>
              <template #no-data>
                <EmptyState
                  icon="mdi-clipboard-search-outline"
                  title="Сдачи не найдены"
                  text="Когда студенты отправят решения, они появятся в этом списке."
                />
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" lg="5">
        <v-card class="panel sticky-detail" elevation="0">
          <template v-if="selectedAttempt">
            <v-card-title class="d-flex align-center">
              Детали сдачи
              <v-spacer />
              <StatusChip :status="selectedAttempt.review_status" :text="statusText(selectedAttempt.review_status)" />
            </v-card-title>
            <v-card-text class="d-flex flex-column ga-4">
              <div>
                <div class="text-caption text-medium-emphasis">Студент</div>
                <div class="font-weight-bold">{{ selectedAttempt.student_name || selectedAttempt.student_email }}</div>
              </div>
              <div>
                <div class="text-caption text-medium-emphasis">Задание</div>
                <div class="font-weight-bold">{{ selectedAttempt.assignment_title || 'Без задания' }}</div>
              </div>

              <v-expansion-panels variant="accordion" density="compact">
                <v-expansion-panel title="Условие задания">
                  <v-expansion-panel-text>
                    <div class="task-description">{{ selectedAttempt.assignment_description || 'Описание задания недоступно.' }}</div>
                    <div v-if="selectedAttempt.assignment_time_limit_minutes" class="text-caption text-medium-emphasis mt-2">
                      Лимит времени: {{ selectedAttempt.assignment_time_limit_minutes }} мин.
                    </div>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>

              <v-row dense>
                <v-tooltip
                  v-for="metric in selectedMetricCards"
                  :key="metric.label"
                  :text="metric.hint"
                  location="top"
                >
                  <template #activator="{ props }">
                    <v-col v-bind="props" cols="12" sm="6">
                      <MetricCard
                        :title="metric.label"
                        :value="metric.value"
                        :color="metric.color"
                        :icon="metric.icon"
                      />
                    </v-col>
                  </template>
                </v-tooltip>
              </v-row>

              <div v-if="selectedEvaluationTiming" class="d-flex flex-wrap ga-2">
                <v-chip size="small" color="info" variant="tonal" prepend-icon="mdi-timer-outline">
                  Проверка: {{ selectedEvaluationTiming.total }} мс
                </v-chip>
                <v-chip v-if="selectedEvaluationTiming.embedding != null" size="small" variant="tonal">
                  Эмбеддинги: {{ selectedEvaluationTiming.embedding }} мс
                </v-chip>
              </div>

              <v-alert type="info" variant="tonal" density="compact" class="review-recommendation">
                {{ recommendationText(selectedAttempt) }}
              </v-alert>

              <v-card class="snapshot-card" variant="tonal">
                <v-card-title class="text-subtitle-1 d-flex align-center">
                  История автоматических проверок
                  <v-spacer />
                  <v-chip size="small" color="primary" variant="tonal">{{ selectedSnapshots.length }}</v-chip>
                </v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="snapshotHeaders"
                    :items="selectedSnapshots"
                    :loading="snapshotsLoading"
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
                      <div class="text-body-2 text-medium-emphasis pa-3">
                        История появится после новых автоматических проверок или повторного импорта демо-данных.
                      </div>
                    </template>
                  </v-data-table>
                </v-card-text>
              </v-card>

              <v-expansion-panels variant="accordion" density="compact">
                <v-expansion-panel v-if="selectedSafetyFindings.length" title="Клинические риски">
                  <v-expansion-panel-text>
                    <v-list density="compact" bg-color="transparent">
                      <v-list-item v-for="(item, index) in selectedSafetyFindings" :key="index">
                        <v-list-item-title>{{ item.source }} → {{ item.target }}</v-list-item-title>
                        <v-list-item-subtitle>{{ item.kind }} · {{ item.relation }}</v-list-item-subtitle>
                      </v-list-item>
                    </v-list>
                  </v-expansion-panel-text>
                </v-expansion-panel>
                <v-expansion-panel v-if="selectedMissingEdges.length" title="Пропущенные связи">
                  <v-expansion-panel-text>
                    <v-list density="compact" bg-color="transparent">
                      <v-list-item v-for="(item, index) in selectedMissingEdges" :key="index">
                        <v-list-item-title>{{ item.source }} → {{ item.target }}</v-list-item-title>
                        <v-list-item-subtitle>{{ item.label || item.relation }}</v-list-item-subtitle>
                      </v-list-item>
                    </v-list>
                  </v-expansion-panel-text>
                </v-expansion-panel>
                <v-expansion-panel v-if="selectedMissingNodes.length" title="Пропущенные понятия">
                  <v-expansion-panel-text>
                    <v-chip v-for="item in selectedMissingNodes" :key="item" size="small" color="warning" variant="tonal" class="mr-1 mb-1">
                      {{ item }}
                    </v-chip>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>

              <div class="graph-preview">
                <ClientOnly>
                  <GraphFlow
                    :key="`review-graph-${selectedAttempt.id}-${metricValue(selectedAttempt, 'student_edge_count') || reviewEdges.length}`"
                    v-model:nodes="reviewNodes"
                    v-model:edges="reviewEdges"
                    :palette="[]"
                    read-only
                    preview-mode
                  />
                </ClientOnly>
              </div>

              <v-select
                v-model="statusDraft"
                :items="reviewStatusItems"
                label="Статус проверки"
                variant="outlined"
                density="comfortable"
              />
              <v-text-field
                v-model.number="teacherScoreDraft"
                label="Итоговая оценка преподавателя, 0–100"
                type="number"
                min="0"
                max="100"
                step="1"
                variant="outlined"
                density="comfortable"
                hint="Сохраняется отдельно от автоматического балла системы."
                persistent-hint
              />
              <v-expansion-panels variant="accordion" density="compact">
                <v-expansion-panel title="Подробная рубрика преподавателя">
                  <v-expansion-panel-text>
                    <v-row dense>
                      <v-col v-for="item in rubricItems" :key="item.key" cols="12" sm="6">
                        <v-text-field
                          v-model.number="rubricDraft[item.key]"
                          :label="`${item.label}, 0–100`"
                          type="number"
                          min="0"
                          max="100"
                          step="1"
                          variant="outlined"
                          density="compact"
                          hide-details
                        />
                      </v-col>
                    </v-row>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
              <v-textarea
                v-model="commentDraft"
                label="Комментарий студенту"
                variant="outlined"
                density="comfortable"
                rows="4"
                auto-grow
              />
              <v-btn color="primary" variant="flat" :loading="saving" @click="saveReview">
                Сохранить ревью
              </v-btn>
            </v-card-text>
          </template>
          <template v-else>
            <v-card-text>
              <EmptyState
                icon="mdi-clipboard-search-outline"
                title="Выберите сдачу"
                text="После выбора здесь появятся граф, метрики и форма ревью."
              />
            </v-card-text>
          </template>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<style scoped>
.review-page {
  max-width: 1440px;
  margin: 0 auto;
}

.panel {
  border: 1px solid rgba(var(--v-border-color), 0.12);
  border-radius: 8px !important;
  background: rgba(var(--v-theme-surface), 0.94) !important;
}

.sticky-detail {
  position: sticky;
  top: 84px;
}

.review-filters {
  display: grid;
  grid-template-columns: minmax(180px, 240px) minmax(220px, 1fr);
  gap: 12px;
  align-items: center;
}

.review-counts {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.review-recommendation {
  border-radius: 8px;
}

.snapshot-card {
  border-radius: 8px !important;
}

.graph-preview {
  height: 520px;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), 0.12);
  border-radius: 8px;
}

.graph-preview :deep(.flow-wrap) {
  height: 520px;
}

.task-description {
  white-space: pre-wrap;
  line-height: 1.55;
}

.graph-preview :deep(.canvas-toolbar) {
  display: none;
}

@media (max-width: 960px) {
  .sticky-detail {
    position: static;
  }
}

@media (max-width: 720px) {
  .review-filters {
    grid-template-columns: 1fr;
  }

  .review-counts {
    grid-column: auto;
  }
}
</style>
