<script setup lang="ts">
import type { ExpertReviewItem, ExpertReviewPublic, ExpertReviewStatus, JsonObject, JsonValue } from '~/types/api'
import type { FlowEdge, FlowNode, GraphNodeCategory } from '~/types/graph'
import { applyAutoLayout, applyBlockLayout } from '~/composables/useGraphLayout'
import { normalizeFlowEdges } from '~/composables/useGraphPayload'
import { getApiErrorMessage } from '~/utils/apiError'
import { createApiClient } from '~/utils/apiClient'

definePageMeta({
  middleware: 'expert',
  keepalive: true,
})

type ExpertItem = ExpertReviewItem
type ExpertReview = ExpertReviewPublic

const auth = useAuthStore()
const api = createApiClient()

const loading = ref(false)
const saving = ref(false)
const errorText = ref('')
const notice = ref('')
const items = ref<ExpertItem[]>([])
const selected = ref<ExpertItem | null>(null)
const typeFilter = ref<'all' | ExpertItem['item_type']>('all')
const onlyUnreviewed = ref(false)
const graphTab = ref<'student' | 'reference'>('student')

const score = ref(0.8)
const clinicalScore = ref(0.8)
const completenessScore = ref(0.8)
const safetyScore = ref(0.8)
const educationalScore = ref(0.8)
const issueTags = ref<string[]>([])
const comment = ref('')
const recommendation = ref('')

const filteredItems = computed(() =>
  items.value.filter((item) => {
    if (typeFilter.value !== 'all' && item.item_type !== typeFilter.value) return false
    if (onlyUnreviewed.value && item.existing_review) return false
    return true
  })
)

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function jsonText(value: JsonValue | undefined): string | null {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

function jsonNumber(value: JsonValue | undefined, fallback = 0): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function jsonArray(value: JsonObject | null | undefined, key: string): unknown[] {
  const nested = value?.[key]
  return Array.isArray(nested) ? nested : []
}

function nodeCategory(value: unknown): GraphNodeCategory {
  return typeof value === 'string' ? value : 'SYMPTOM'
}

function toFlowNode(value: unknown, index: number): FlowNode {
  const record = isRecord(value) ? value : {}
  const rawData = isRecord(record.data) ? record.data : {}
  const rawPosition = isRecord(record.position) ? record.position : {}
  const type = typeof record.type === 'string' && record.type === 'frame' ? 'frame' : 'med'

  return {
    id: String(record.id ?? `node-${index}`),
    type,
    position: {
      x: jsonNumber(rawPosition.x as JsonValue | undefined, 0),
      y: jsonNumber(rawPosition.y as JsonValue | undefined, 0),
    },
    data: {
      category: nodeCategory(rawData.category),
      label: jsonText(rawData.label as JsonValue | undefined) ?? 'Без названия',
    },
  }
}

function metricField(item: ExpertItem | null, key: string): JsonValue | undefined {
  return item?.metrics?.[key]
}

function stepScore(review: ExpertReview | null | undefined, key: string): number {
  return jsonNumber(review?.step_scores?.[key], 0.8)
}

const selectedGraph = computed(() => {
  const graph = graphTab.value === 'student'
    ? selected.value?.student_graph || selected.value?.reference_graph
    : selected.value?.reference_graph || selected.value?.student_graph
  const mappedNodes = jsonArray(graph, 'nodes').map(toFlowNode)
  const mappedEdges = normalizeFlowEdges(jsonArray(graph, 'edges')) as FlowEdge[]
  // Reference solution is shown in clinical-stage blocks; student graph keeps free layout.
  const layout = graphTab.value === 'reference' ? applyBlockLayout : applyAutoLayout
  return {
    nodes: layout(mappedNodes, mappedEdges),
    edges: mappedEdges,
  }
})

const reviewedCount = computed(() => items.value.filter((item) => item.existing_review).length)
const unreviewedCount = computed(() => items.value.length - reviewedCount.value)

const headers = [
  { title: 'Объект', key: 'title' },
  { title: 'Тип', key: 'item_type' },
  { title: 'Статус', key: 'status' },
  { title: 'Оценка', key: 'score' },
  { title: '', key: 'actions', sortable: false, align: 'end' as const },
]

const typeItems = [
  { title: 'Все объекты', value: 'all' },
  { title: 'Сдачи студентов', value: 'student_attempt' },
  { title: 'Эталонные графы', value: 'reference_graph' },
  { title: 'Задания', value: 'assignment' },
]

const tagItems = [
  'Пропущена диагностика',
  'Неверная категория узла',
  'Нарушена клиническая цепочка',
  'Опасное лишнее действие',
  'Слабое педагогическое описание',
  'Эталон требует доработки',
  'Автоматическая оценка завышена',
  'Автоматическая оценка занижена',
]

function typeText(value: string) {
  if (value === 'student_attempt') return 'Сдача'
  if (value === 'reference_graph') return 'Эталон'
  return 'Задание'
}

function scoreText(value?: number | null) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `${Math.round(n * 100)}%`
}

function metricPercent(value: unknown) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `${Math.round(n * 100)}%`
}

function selectItem(item: ExpertItem) {
  selected.value = item
  graphTab.value = item.student_graph ? 'student' : 'reference'
  const review = item.existing_review
  score.value = Number(review?.score ?? metricField(item, 'composite_score') ?? 0.8)
  clinicalScore.value = stepScore(review, 'clinical_correctness')
  completenessScore.value = stepScore(review, 'completeness')
  safetyScore.value = stepScore(review, 'safety')
  educationalScore.value = stepScore(review, 'educational_value')
  issueTags.value = [...(review?.issue_tags || [])]
  comment.value = review?.comment || ''
  recommendation.value = review?.recommendation || ''
}

async function loadItems() {
  loading.value = true
  errorText.value = ''
  try {
    const res = await api.endpoint('GET', '/expert/items', { accessToken: auth.accessToken })
    items.value = res.items
    if (!selected.value && items.value.length) {
      selectItem(items.value[0])
    } else if (selected.value) {
      const updated = items.value.find((item) => item.item_type === selected.value?.item_type && item.item_id === selected.value?.item_id)
      if (updated) selectItem(updated)
    }
  } catch (error) {
    errorText.value = getApiErrorMessage(error, 'Не удалось загрузить экспертный кабинет')
  } finally {
    loading.value = false
  }
}

async function saveReview(status: ExpertReviewStatus = 'submitted') {
  if (!selected.value) return
  saving.value = true
  errorText.value = ''
  notice.value = ''
  try {
    const updated = await api.endpoint('POST', '/expert/reviews', {
      accessToken: auth.accessToken,
      body: {
        item_type: selected.value.item_type,
        item_id: selected.value.item_id,
        score: score.value,
        step_scores: {
          clinical_correctness: clinicalScore.value,
          completeness: completenessScore.value,
          safety: safetyScore.value,
          educational_value: educationalScore.value,
        },
        issue_tags: issueTags.value,
        comment: comment.value || null,
        recommendation: recommendation.value || null,
        status,
      },
    })
    items.value = items.value.map((item) => {
      if (item.item_type === selected.value?.item_type && item.item_id === selected.value?.item_id) {
        return { ...item, existing_review: updated }
      }
      return item
    })
    selectItem({ ...selected.value, existing_review: updated })
    notice.value = 'Экспертная оценка сохранена.'
  } catch (error) {
    errorText.value = getApiErrorMessage(error, 'Не удалось сохранить экспертную оценку')
  } finally {
    saving.value = false
  }
}

onMounted(loadItems)
</script>

<template>
  <v-container fluid class="expert-page pa-3 pa-md-6">
    <div class="expert-head mb-4">
      <div>
        <div class="text-overline text-primary font-weight-bold">Экспертный кабинет</div>
        <h1 class="text-h5 text-md-h4 font-weight-bold mb-1">Оценка графов и клинических заданий</h1>
        <p class="text-body-2 text-medium-emphasis mb-0">
          Независимая оценка эталонов, заданий и работ студентов. Данные используются для калибровки метрик и повышения достоверности системы.
        </p>
      </div>
      <v-btn color="primary" variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="loadItems">Обновить</v-btn>
    </div>

    <v-alert v-if="errorText" type="error" variant="tonal" rounded="lg" class="mb-4" closable @click:close="errorText = ''">
      {{ errorText }}
    </v-alert>
    <v-alert v-if="notice" type="success" variant="tonal" rounded="lg" class="mb-4" closable @click:close="notice = ''">
      {{ notice }}
    </v-alert>

    <v-row class="mb-2">
      <v-col cols="12" sm="4">
        <v-card class="metric-card" elevation="0">
          <div class="text-caption text-medium-emphasis">Объекты</div>
          <div class="text-h4 font-weight-bold">{{ items.length }}</div>
        </v-card>
      </v-col>
      <v-col cols="12" sm="4">
        <v-card class="metric-card" elevation="0">
          <div class="text-caption text-medium-emphasis">Оценено</div>
          <div class="text-h4 font-weight-bold text-success">{{ reviewedCount }}</div>
        </v-card>
      </v-col>
      <v-col cols="12" sm="4">
        <v-card class="metric-card" elevation="0">
          <div class="text-caption text-medium-emphasis">Осталось</div>
          <div class="text-h4 font-weight-bold text-warning">{{ unreviewedCount }}</div>
        </v-card>
      </v-col>
    </v-row>

    <v-row>
      <v-col cols="12" lg="5">
        <v-card class="panel" elevation="0">
          <v-card-title class="d-flex align-center">
            Объекты для оценки
            <v-spacer />
            <v-chip size="small" color="primary" variant="tonal">{{ filteredItems.length }}</v-chip>
          </v-card-title>
          <v-card-text>
            <div class="filters mb-3">
              <v-select v-model="typeFilter" :items="typeItems" label="Тип объекта" variant="outlined" density="compact" hide-details />
              <v-switch v-model="onlyUnreviewed" label="Только без моей оценки" color="primary" density="compact" hide-details />
            </div>
            <v-data-table :headers="headers" :items="filteredItems" :loading="loading" density="comfortable" :items-per-page="10">
              <template #[`item.title`]="{ item }">
                <div class="font-weight-bold">{{ item.title }}</div>
                <div class="text-caption text-medium-emphasis">
                  {{ item.student_name || item.student_email || item.assignment_title || `ID ${item.item_id}` }}
                </div>
              </template>
              <template #[`item.item_type`]="{ item }">
                <v-chip size="small" color="primary" variant="tonal">{{ typeText(item.item_type) }}</v-chip>
              </template>
              <template #[`item.status`]="{ item }">{{ item.status || '—' }}</template>
              <template #[`item.score`]="{ item }">
                <v-chip size="small" :color="item.existing_review ? 'success' : 'warning'" variant="tonal">
                  {{ item.existing_review ? scoreText(item.existing_review.score) : 'нет' }}
                </v-chip>
              </template>
              <template #[`item.actions`]="{ item }">
                <v-btn icon="mdi-eye-outline" size="small" variant="text" color="primary" @click="selectItem(item)" />
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" lg="7">
        <v-card v-if="selected" class="panel sticky-detail" elevation="0">
          <v-card-title class="d-flex align-center">
            {{ selected.title }}
            <v-spacer />
            <v-chip size="small" color="primary" variant="tonal">{{ typeText(selected.item_type) }}</v-chip>
          </v-card-title>
          <v-card-text class="d-flex flex-column ga-4">
            <div class="metric-grid">
              <div>
                <div class="text-caption text-medium-emphasis">Авто-оценка</div>
                <div class="text-h6 font-weight-bold">{{ metricPercent(metricField(selected, 'composite_score') ?? metricField(selected, 'f1_score')) }}</div>
              </div>
              <div>
                <div class="text-caption text-medium-emphasis">Риск</div>
                <div class="text-h6 font-weight-bold text-error">{{ metricPercent(metricField(selected, 'safety_penalty')) }}</div>
              </div>
              <div>
                <div class="text-caption text-medium-emphasis">Предупреждения</div>
                <div class="text-h6 font-weight-bold">{{ selected.validation_warnings?.length || 0 }}</div>
              </div>
              <div>
                <div class="text-caption text-medium-emphasis">Моя оценка</div>
                <div class="text-h6 font-weight-bold text-success">{{ selected.existing_review ? scoreText(selected.existing_review.score) : '—' }}</div>
              </div>
            </div>

            <v-tabs v-model="graphTab" color="primary" density="comfortable">
              <v-tab value="student" :disabled="!selected.student_graph">Граф студента</v-tab>
              <v-tab value="reference">Эталонный граф</v-tab>
            </v-tabs>
            <div class="graph-preview">
              <ClientOnly>
                <GraphFlow
                  :nodes="selectedGraph.nodes"
                  :edges="selectedGraph.edges"
                  :palette="[]"
                  read-only
                />
              </ClientOnly>
            </div>

            <v-expansion-panels v-if="selected.validation_warnings?.length" variant="accordion" density="compact">
              <v-expansion-panel title="Предупреждения по эталону">
                <v-expansion-panel-text>
                  <v-list density="compact" bg-color="transparent">
                    <v-list-item v-for="(warning, index) in selected.validation_warnings" :key="index" prepend-icon="mdi-alert-outline">
                      <v-list-item-title>{{ warning }}</v-list-item-title>
                    </v-list-item>
                  </v-list>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>

            <v-divider />

            <div class="score-grid">
              <v-slider v-model="score" label="Итоговая оценка" min="0" max="1" step="0.01" thumb-label />
              <v-slider v-model="clinicalScore" label="Клиническая корректность" min="0" max="1" step="0.01" thumb-label />
              <v-slider v-model="completenessScore" label="Полнота" min="0" max="1" step="0.01" thumb-label />
              <v-slider v-model="safetyScore" label="Безопасность" min="0" max="1" step="0.01" thumb-label />
              <v-slider v-model="educationalScore" label="Педагогическая ценность" min="0" max="1" step="0.01" thumb-label />
            </div>

            <v-combobox
              v-model="issueTags"
              :items="tagItems"
              label="Метки замечаний"
              variant="outlined"
              density="comfortable"
              multiple
              chips
            />
            <v-textarea v-model="comment" label="Что не так / клиническое замечание" variant="outlined" rows="4" auto-grow />
            <v-textarea v-model="recommendation" label="Рекомендация по доработке системы или задания" variant="outlined" rows="3" auto-grow />

            <div class="d-flex ga-2">
              <v-btn color="primary" variant="flat" :loading="saving" @click="saveReview('submitted')">Сохранить оценку</v-btn>
              <v-btn color="secondary" variant="tonal" :loading="saving" @click="saveReview('draft')">Сохранить как черновик</v-btn>
            </div>
          </v-card-text>
        </v-card>

        <v-card v-else class="panel" elevation="0">
          <v-card-text class="empty-state">
            <v-icon icon="mdi-stethoscope" size="48" color="primary" />
            <div class="font-weight-bold mt-2">Выберите объект</div>
            <div class="text-body-2 text-medium-emphasis">Здесь появятся графы, метрики и форма экспертной оценки.</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<style scoped>
.expert-page {
  max-width: 1560px;
  margin: 0 auto;
}

.expert-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.panel,
.metric-card {
  border: 1px solid rgba(var(--v-border-color), 0.12);
  border-radius: 8px !important;
  background: rgba(var(--v-theme-surface), 0.96) !important;
}

.metric-card {
  padding: 18px;
  min-height: 108px;
}

.filters {
  display: grid;
  grid-template-columns: minmax(180px, 240px) minmax(220px, 1fr);
  gap: 12px;
  align-items: center;
}

.sticky-detail {
  position: sticky;
  top: 84px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.metric-grid > div {
  border: 1px solid rgba(var(--v-border-color), 0.1);
  border-radius: 8px;
  padding: 10px 12px;
  background: rgba(var(--v-theme-surface-variant), 0.34);
}

.graph-preview {
  height: 440px;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), 0.12);
  border-radius: 8px;
}

.graph-preview :deep(.flow-wrap) {
  height: 440px;
}

.graph-preview :deep(.canvas-toolbar) {
  display: none;
}

.score-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 18px;
}

.score-grid .v-slider:first-child {
  grid-column: 1 / -1;
}

.empty-state {
  min-height: 320px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 24px;
}

@media (max-width: 960px) {
  .expert-head,
  .filters {
    align-items: stretch;
    grid-template-columns: 1fr;
    flex-direction: column;
  }

  .sticky-detail {
    position: static;
  }

  .metric-grid,
  .score-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .metric-grid,
  .score-grid {
    grid-template-columns: 1fr;
  }
}
</style>
