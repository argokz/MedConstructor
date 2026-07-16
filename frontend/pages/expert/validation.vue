<script setup lang="ts">
import type { JsonObject, JsonValue, ValidationAcceptStatus, ValidationRatingPublic, ValidationVariantBlinded } from '~/types/api'
import type { FlowEdge, FlowNode, GraphNodeCategory } from '~/types/graph'
import EmptyState from '~/components/shared/ui/EmptyState.vue'
import MetricCard from '~/components/shared/ui/MetricCard.vue'
import PageHeader from '~/components/shared/ui/PageHeader.vue'
import StatusChip from '~/components/shared/ui/StatusChip.vue'
import { applyAutoLayout } from '~/composables/useGraphLayout'
import { normalizeFlowEdges } from '~/composables/useGraphPayload'
import { categoryMeta, relationMeta } from '~/constants/clinicalOntology'
import { getApiErrorMessage } from '~/utils/apiError'
import { createApiClient } from '~/utils/apiClient'

definePageMeta({
  middleware: 'expert',
  keepalive: true,
})

type ValidationItem = ValidationVariantBlinded

const auth = useAuthStore()
const api = createApiClient()
const validationCohort = 'cardiology_pilot_v2'

const loading = ref(false)
const saving = ref(false)
const errorText = ref('')
const notice = ref('')
const items = ref<ValidationItem[]>([])
const total = ref(0)
const rated = ref(0)
const selectedId = ref<string | null>(null)
const onlyUnrated = ref(false)

const score = ref<number>(80)
const accept = ref<ValidationAcceptStatus | null>(null)
const comment = ref('')

const selected = computed(() => items.value.find((i) => i.review_item_id === selectedId.value) || null)

const progress = computed(() => (total.value ? Math.round((rated.value / total.value) * 100) : 0))

const orderedItems = computed(() =>
  [...items.value].sort((a, b) => (a.display_order || 0) - (b.display_order || 0))
)

const filteredItems = computed(() =>
  orderedItems.value.filter((i) => (onlyUnrated.value ? !isRated(i) : true))
)

function isRated(item: ValidationItem) {
  return item.my_rating != null && item.my_rating.score != null
}

function positionLabel(item: ValidationItem) {
  const idx = orderedItems.value.findIndex((i) => i.review_item_id === item.review_item_id)
  return idx >= 0 ? `№ ${idx + 1}` : ''
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function jsonNumber(value: JsonValue | undefined, fallback = 0): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function jsonText(value: JsonValue | undefined): string | null {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
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

  return {
    id: String(record.id ?? `node-${index}`),
    type: typeof record.type === 'string' && record.type === 'frame' ? 'frame' : 'med',
    position: {
      x: jsonNumber(rawPosition.x as JsonValue | undefined),
      y: jsonNumber(rawPosition.y as JsonValue | undefined),
    },
    data: {
      category: nodeCategory(rawData.category),
      label: jsonText(rawData.label as JsonValue | undefined) ?? 'Без названия',
    },
  }
}

const selectedGraph = computed(() => {
  const graph = selected.value?.student_graph
  const mappedNodes = jsonArray(graph, 'nodes').map(toFlowNode)
  const mappedEdges = normalizeFlowEdges(jsonArray(graph, 'edges')) as FlowEdge[]
  return {
    // Edge-aware dagre layout: keeps causal connections readable. (The earlier
    // category-band layout ignored edges and then clashed with the read-only
    // preview's own auto-layout, detaching blocks from their frames.)
    nodes: applyAutoLayout(mappedNodes, mappedEdges, { spacious: true }),
    edges: mappedEdges,
  }
})

// Text (JSON) rendering of the same graph — blocks grouped by clinical category
// plus the directed connections between them, opened from a button so experts
// can cross-check the picture against the underlying structure.
const showGraphText = ref(false)

const graphSummary = computed(() => {
  const clinicalNodes = selectedGraph.value.nodes.filter((n) => n.type !== 'frame')
  const labelById = new Map(clinicalNodes.map((n) => [n.id, n.data?.label || 'Без названия']))

  const groups = new Map<string, { title: string; color: string; labels: string[] }>()
  for (const node of clinicalNodes) {
    const meta = categoryMeta(node.data?.category)
    if (!groups.has(meta.value)) groups.set(meta.value, { title: meta.title, color: meta.color, labels: [] })
    groups.get(meta.value)!.labels.push(node.data?.label || 'Без названия')
  }

  const connections = selectedGraph.value.edges.map((edge) => {
    const meta = relationMeta(edge.label)
    return {
      from: labelById.get(String(edge.source)) || String(edge.source),
      to: labelById.get(String(edge.target)) || String(edge.target),
      relation: meta?.short || 'Связь',
      color: meta?.color || '#64748b',
    }
  })

  return {
    blockCount: clinicalNodes.length,
    groups: [...groups.values()],
    connections,
  }
})

const scoreColor = computed(() => {
  if (score.value >= 75) return 'success'
  if (score.value >= 60) return 'info'
  if (score.value >= 40) return 'warning'
  return 'error'
})

function loadForm(item: ValidationItem | null) {
  const r = item?.my_rating
  score.value = Number(r?.score ?? 80)
  accept.value = r?.accept ?? null
  comment.value = r?.comment || ''
}

function selectItem(item: ValidationItem) {
  selectedId.value = item.review_item_id
  loadForm(item)
}

async function loadItems() {
  loading.value = true
  errorText.value = ''
  try {
    const res = await api.endpoint('GET', '/expert/validation/items', {
      accessToken: auth.accessToken,
      query: { cohort: validationCohort },
    })
    items.value = res.items
    total.value = res.total
    rated.value = res.rated
    if (!selectedId.value && items.value.length) {
      const firstUnrated = orderedItems.value.find((i) => !isRated(i))
      selectItem(firstUnrated || orderedItems.value[0])
    } else if (selected.value) {
      loadForm(selected.value)
    }
  } catch (error) {
    errorText.value = getApiErrorMessage(error, 'Не удалось загрузить варианты для оценки')
  } finally {
    loading.value = false
  }
}

async function saveRating(goNext = false) {
  if (!selected.value) return
  saving.value = true
  errorText.value = ''
  notice.value = ''
  try {
    const updated: ValidationRatingPublic = await api.endpoint('POST', '/expert/validation/ratings', {
      accessToken: auth.accessToken,
      body: {
        review_item_id: selected.value.review_item_id,
        score: score.value,
        accept: accept.value,
        comment: comment.value || null,
        status: 'submitted',
      },
    })
    const wasRated = isRated(selected.value)
    items.value = items.value.map((i) =>
      i.review_item_id === selected.value?.review_item_id ? { ...i, my_rating: updated } : i,
    )
    if (!wasRated) rated.value += 1
    notice.value = 'Оценка сохранена.'
    if (goNext) {
      const next = orderedItems.value.find((i) => !isRated(i))
      if (next) selectItem(next)
      else notice.value = 'Готово! Все варианты оценены. Спасибо.'
    }
  } catch (error) {
    errorText.value = getApiErrorMessage(error, 'Не удалось сохранить оценку')
  } finally {
    saving.value = false
  }
}

onMounted(loadItems)
</script>

<template>
  <v-container fluid class="validation-page pa-3 pa-md-6">
    <PageHeader
      eyebrow="Экспертная валидация"
      title="Слепая оценка клинических графов"
      subtitle="Оцените каждый граф по клиническому качеству от 0 до 100. Вы не видите оценку системы и тип ошибки — это сохраняет независимость вашего экспертного суждения."
    >
      <template #actions>
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="loadItems">Обновить</v-btn>
      </template>
    </PageHeader>

    <v-alert v-if="errorText" type="error" variant="tonal" rounded="lg" class="mb-4" closable @click:close="errorText = ''">
      {{ errorText }}
    </v-alert>
    <v-alert v-if="notice" type="success" variant="tonal" rounded="lg" class="mb-4" closable @click:close="notice = ''">
      {{ notice }}
    </v-alert>

    <v-row class="mb-2">
      <v-col cols="12" sm="4">
        <MetricCard title="Всего вариантов" :value="total" icon="mdi-clipboard-pulse-outline" />
      </v-col>
      <v-col cols="12" sm="4">
        <MetricCard title="Оценено" :value="rated" icon="mdi-check-circle-outline" color="success" />
      </v-col>
      <v-col cols="12" sm="4">
        <MetricCard title="Прогресс" :value="`${progress}%`" icon="mdi-chart-donut" color="warning" />
      </v-col>
    </v-row>

    <v-card class="panel mb-4" elevation="0">
      <v-card-text class="d-flex align-center ga-4 flex-wrap">
        <div class="flex-grow-1 min-progress">
          <div class="d-flex justify-space-between text-caption text-medium-emphasis mb-1">
            <span>Прогресс оценки</span>
            <span>{{ rated }} / {{ total }}</span>
          </div>
          <v-progress-linear :model-value="progress" color="success" height="10" rounded />
        </div>
        <v-switch v-model="onlyUnrated" label="Только неоценённые" color="primary" density="compact" hide-details />
      </v-card-text>
    </v-card>

    <v-row>
      <v-col cols="12" lg="4">
        <v-card class="panel" elevation="0">
          <v-card-title class="d-flex align-center">
            Варианты
            <v-spacer />
            <v-chip size="small" color="primary" variant="tonal">{{ filteredItems.length }}</v-chip>
          </v-card-title>
          <v-list class="variant-list" density="comfortable" bg-color="transparent">
            <v-list-item
              v-for="item in filteredItems"
              :key="item.review_item_id"
              :active="item.review_item_id === selectedId"
              rounded="lg"
              @click="selectItem(item)"
            >
              <template #prepend>
                <v-icon
                  :icon="isRated(item) ? 'mdi-check-circle' : 'mdi-circle-outline'"
                  :color="isRated(item) ? 'success' : 'medium-emphasis'"
                />
              </template>
              <v-list-item-title class="font-weight-medium">{{ positionLabel(item) }} · {{ item.case_title || 'Клинический случай' }}</v-list-item-title>
              <v-list-item-subtitle v-if="isRated(item)">Ваша оценка: {{ Math.round(Number(item.my_rating?.score)) }}</v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </v-card>
      </v-col>

      <v-col cols="12" lg="8">
        <v-card v-if="selected" class="panel sticky-detail" elevation="0">
          <v-card-title class="d-flex align-center">
            {{ positionLabel(selected) }} · {{ selected.case_title || 'Клинический случай' }}
            <v-spacer />
            <StatusChip v-if="isRated(selected)" status="accepted" text="оценён" />
          </v-card-title>
          <v-card-text class="d-flex flex-column ga-4">
            <v-alert v-if="selected.case_prompt" type="info" variant="tonal" density="comfortable" rounded="lg">
              {{ selected.case_prompt }}
            </v-alert>

            <div class="d-flex justify-end">
              <v-btn
                variant="tonal"
                color="primary"
                size="small"
                prepend-icon="mdi-format-list-bulleted-type"
                @click="showGraphText = true"
              >
                Блоки и связи текстом
              </v-btn>
            </div>

            <div class="graph-preview">
              <ClientOnly>
                <GraphFlow :nodes="selectedGraph.nodes" :edges="selectedGraph.edges" :palette="[]" read-only />
              </ClientOnly>
            </div>

            <v-divider />

            <div>
              <div class="d-flex justify-space-between align-center mb-1">
                <span class="text-subtitle-2 font-weight-bold">Клиническая оценка графа</span>
                <v-chip :color="scoreColor" variant="flat" size="large">{{ Math.round(score) }} / 100</v-chip>
              </div>
              <v-slider v-model="score" min="0" max="100" step="1" :color="scoreColor" thumb-label hide-details class="mt-2" />
              <div class="scale-hint text-caption text-medium-emphasis mt-1">
                90–100 клинически полно и безопасно · 75–89 незначительные пропуски · 60–74 важные пробелы ·
                40–59 серьёзный дефект рассуждения · 0–39 небезопасно / пропущено критическое
              </div>
            </div>

            <div class="d-flex align-center ga-4 flex-wrap">
              <span class="text-body-2 text-medium-emphasis">Клинически приемлемо?</span>
              <v-btn-toggle v-model="accept" color="primary" variant="outlined" density="comfortable" rounded="lg">
                <v-btn value="yes" prepend-icon="mdi-check">Да</v-btn>
                <v-btn value="no" prepend-icon="mdi-close">Нет</v-btn>
              </v-btn-toggle>
            </div>

            <v-textarea v-model="comment" label="Комментарий (необязательно): что не так / клиническое замечание" variant="outlined" rows="3" auto-grow hide-details />

            <div class="d-flex ga-2 flex-wrap">
              <v-btn color="primary" variant="flat" :loading="saving" prepend-icon="mdi-content-save" @click="saveRating(false)">Сохранить</v-btn>
              <v-btn color="success" variant="tonal" :loading="saving" append-icon="mdi-arrow-right" @click="saveRating(true)">Сохранить и далее</v-btn>
            </div>
          </v-card-text>
        </v-card>

        <v-card v-else class="panel" elevation="0">
          <v-card-text>
            <EmptyState
              icon="mdi-clipboard-pulse-outline"
              title="Выберите вариант"
              text="Слева список графов для слепой оценки."
            />
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-dialog v-model="showGraphText" max-width="720" scrollable>
      <v-card class="panel">
        <v-card-title class="d-flex align-center">
          Блоки и связи графа
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" aria-label="Закрыть" @click="showGraphText = false" />
        </v-card-title>
        <v-divider />
        <v-card-text style="max-height: 70vh">
          <div class="text-subtitle-2 font-weight-bold mb-2">
            Блоки ({{ graphSummary.blockCount }})
          </div>
          <div v-for="group in graphSummary.groups" :key="group.title" class="mb-3">
            <div class="d-flex align-center ga-2 mb-1">
              <span class="cat-dot" :style="{ background: group.color }" />
              <span class="text-caption font-weight-bold text-medium-emphasis">{{ group.title }}</span>
            </div>
            <ul class="text-body-2 block-list">
              <li v-for="(label, idx) in group.labels" :key="idx">{{ label }}</li>
            </ul>
          </div>

          <v-divider class="my-3" />

          <div class="text-subtitle-2 font-weight-bold mb-2">
            Связи ({{ graphSummary.connections.length }})
          </div>
          <div v-if="!graphSummary.connections.length" class="text-body-2 text-medium-emphasis">
            Связей нет.
          </div>
          <ul class="text-body-2 conn-list">
            <li v-for="(conn, idx) in graphSummary.connections" :key="idx" class="mb-1">
              <span class="font-weight-medium">{{ conn.from }}</span>
              <span class="mx-1">→</span>
              <span class="font-weight-medium">{{ conn.to }}</span>
              <v-chip size="x-small" variant="tonal" class="ml-2" :style="{ color: conn.color, borderColor: conn.color }">
                {{ conn.relation }}
              </v-chip>
            </li>
          </ul>
        </v-card-text>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<style scoped>
.validation-page {
  max-width: 1560px;
  margin: 0 auto;
}

.panel {
  border: 1px solid rgba(var(--v-border-color), 0.12);
  border-radius: 8px !important;
  background: rgba(var(--v-theme-surface), 0.96) !important;
}

.variant-list {
  max-height: 640px;
  overflow-y: auto;
}

.sticky-detail {
  position: sticky;
  top: 84px;
}

.graph-preview {
  height: 460px;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), 0.12);
  border-radius: 8px;
}

.graph-preview :deep(.flow-wrap) {
  height: 460px;
}

.graph-preview :deep(.canvas-toolbar) {
  display: none;
}

.min-progress {
  min-width: 220px;
}

.cat-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex: 0 0 auto;
}

.block-list,
.conn-list {
  margin: 0;
  padding-left: 22px;
}

.block-list li,
.conn-list li {
  line-height: 1.5;
}

@media (max-width: 960px) {
  .sticky-detail {
    position: static;
  }
}
</style>
