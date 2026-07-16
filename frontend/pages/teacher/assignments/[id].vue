<script setup lang="ts">
import EmptyState from '~/components/shared/ui/EmptyState.vue'
import MetricCard from '~/components/shared/ui/MetricCard.vue'
import PageHeader from '~/components/shared/ui/PageHeader.vue'
import StatusChip from '~/components/shared/ui/StatusChip.vue'
import { applyBlockLayout } from '~/composables/useGraphLayout'
import { normalizeFlowEdges } from '~/composables/useGraphPayload'
import type {
  AssignmentApproveReferenceRequest,
  AssignmentDraftUpdate,
  AssignmentPublishRequest,
  AssignmentReviewBundle,
  AssignmentStatus,
  EdgeType,
  GraphSchema,
  JsonObject,
  JsonValue,
  NodeType,
} from '~/types/api'
import type { FlowEdge, FlowNode, GraphNodeCategory } from '~/types/graph'
import { getApiErrorMessage } from '~/utils/apiError'
import { createApiClient } from '~/utils/apiClient'

definePageMeta({
  middleware: 'teacher',
})

type AssignmentBundle = AssignmentReviewBundle
type SourceRow = {
  title: string
  meta: string
  url?: string
}

const NODE_TYPES: readonly NodeType[] = [
  'PATIENT_PROFILE',
  'SYMPTOM',
  'EXAM',
  'LAB_TEST',
  'INSTRUMENTAL_TEST',
  'DIAGNOSIS',
  'MEDICATION',
  'SURGERY',
  'MONITORING',
]

const EDGE_TYPES: readonly EdgeType[] = [
  'DETERMINES',
  'REQUIRES_CONFIRMATION',
  'EXCLUDES',
  'INDICATED_FOR',
  'CONTRAINDICATED_DUE_TO',
]

const auth = useAuthStore()
const route = useRoute()
const api = createApiClient()

const loading = ref(false)
const saving = ref(false)
const approving = ref(false)
const publishing = ref(false)
const errorText = ref('')
const notice = ref('')
const bundle = ref<AssignmentBundle | null>(null)
const titleDraft = ref('')
const descriptionDraft = ref('')
const timeLimitDraft = ref<number | null>(45)
const notesDraft = ref('')
const nodes = ref<FlowNode[]>([])
const edges = ref<FlowEdge[]>([])

const assignmentId = computed(() => Number(route.params.id))

const statusText = computed(() => {
  const status = bundle.value?.assignment.status
  if (status === 'published') return 'Опубликовано'
  if (status === 'teacher_approved') return 'Эталон подтверждён'
  if (status === 'needs_teacher_review' || status === 'review_ready') return 'Требует проверки'
  if (status === 'ai_generated') return 'AI-черновик'
  if (status === 'archived') return 'Архив'
  return 'Черновик'
})

const warnings = computed(() => bundle.value?.reference_graph.validation_warnings || [])
const quality = computed<JsonObject>(() =>
  bundle.value?.reference_graph.generation_quality || bundle.value?.assignment.reference_generation_quality || {}
)
const criticalCount = computed(() => Number(quality.value?.critical_count || 0))
const warningCount = computed(() => Number(quality.value?.warning_count || warnings.value.length || 0))
const referenceStatus = computed(() => bundle.value?.reference_graph.status || 'draft')
const isReferenceApproved = computed(() =>
  ['teacher_approved', 'published', 'approved'].includes(String(referenceStatus.value))
)
const referenceStatusText = computed(() => {
  if (referenceStatus.value === 'published') return 'Опубликован'
  if (referenceStatus.value === 'teacher_approved' || referenceStatus.value === 'approved') return 'Подтверждён'
  if (referenceStatus.value === 'ai_generated') return 'AI-черновик'
  if (referenceStatus.value === 'needs_teacher_review' || referenceStatus.value === 'review_ready') return 'На проверке'
  if (referenceStatus.value === 'archived') return 'Архив'
  return 'Черновик'
})
const canApproveReference = computed(() => Boolean(bundle.value && titleDraft.value.trim() && nodes.value.length && edges.value.length))
const canPublish = computed(() => Boolean(canApproveReference.value && isReferenceApproved.value && bundle.value?.assignment.status !== 'published'))
const qualityScoreText = computed(() => {
  const score = Number(quality.value.quality_score)
  return Number.isFinite(score) ? score.toFixed(2) : '—'
})
const sourceRows = computed<SourceRow[]>(() => {
  const sources = bundle.value?.reference_graph.source_protocols?.length
    ? bundle.value.reference_graph.source_protocols
    : bundle.value?.reference_graph.generation_context || []

  const rows: SourceRow[] = []
  const seen = new Set<string>()
  for (const source of sources) {
    const protocolId = textValue(source.protocol_id)
    const externalId = textValue(source.protocol_external_id)
    const title = textValue(source.protocol_title) || `Протокол #${protocolId || '—'}`
    const key = `${protocolId || ''}:${title}`
    if (seen.has(key)) continue
    seen.add(key)
    const meta = [
      externalId ? `ID МЗ РК ${externalId}` : protocolId ? `DB ID ${protocolId}` : null,
      textValue(source.protocol_year),
      textValue(source.protocol_category) || textValue(source.section),
    ].filter(Boolean).join(' · ')
    rows.push({
      title,
      meta: meta || 'источник протокола',
      url: textValue(source.protocol_url),
    })
  }
  return rows
})

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function textValue(value: unknown): string | undefined {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return undefined
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

  return {
    id: String(record.id ?? `node-${index}`),
    type: record.type === 'frame' ? 'frame' : 'med',
    position: {
      x: jsonNumber(rawPosition.x as JsonValue | undefined),
      y: jsonNumber(rawPosition.y as JsonValue | undefined),
    },
    data: {
      category: nodeCategory(rawData.category),
      label: textValue(rawData.label) || textValue(record.label) || 'Без названия',
    },
  }
}

function toNodeType(value: unknown): NodeType {
  if (typeof value === 'string' && NODE_TYPES.includes(value as NodeType)) return value as NodeType
  if (value === 'DISEASE') return 'DIAGNOSIS'
  return 'SYMPTOM'
}

function toEdgeType(value: unknown): EdgeType {
  if (typeof value === 'string' && EDGE_TYPES.includes(value as EdgeType)) return value as EdgeType
  return 'DETERMINES'
}

function toGraphSchema(): GraphSchema {
  const clinicalNodes = nodes.value.filter((node) => node.type !== 'frame' && node.type !== 'group')
  const conceptIds = new Set(clinicalNodes.map((node) => String(node.id)))

  return {
    nodes: clinicalNodes.map((node) => ({
      id: String(node.id),
      type: typeof node.type === 'string' ? node.type : 'med',
      position: {
        x: Number(node.position?.x ?? 0),
        y: Number(node.position?.y ?? 0),
      },
      data: {
        label: String(node.data?.label ?? '').trim() || 'unnamed',
        category: toNodeType(node.data?.category),
        description: typeof node.data?.description === 'string' ? node.data.description : null,
        protocol_refs: Array.isArray(node.data?.protocol_refs) ? node.data.protocol_refs : [],
        is_critical: Boolean(node.data?.is_critical),
        source: typeof node.data?.source === 'string' ? node.data.source : null,
        confidence: Number.isFinite(Number(node.data?.confidence)) ? Number(node.data?.confidence) : null,
      },
    })),
    edges: edges.value
      .filter((edge) => conceptIds.has(String(edge.source)) && conceptIds.has(String(edge.target)))
      .map((edge, index) => ({
        id: String(edge.id || `e_${edge.source}_${edge.target}_${index}`),
        type: typeof edge.type === 'string' ? edge.type : 'custom',
        source: String(edge.source),
        target: String(edge.target),
        label: toEdgeType(edge.label),
        sourceHandle: edge.sourceHandle || 's',
        targetHandle: edge.targetHandle || 't',
      })),
  }
}

function publishErrorMessage(error: unknown): string {
  if (isRecord(error) && isRecord(error.data) && isRecord(error.data.detail)) {
    const detail = error.data.detail
    const message = textValue(detail.message) || 'Публикация заблокирована'
    const warningsText = Array.isArray(detail.warnings)
      ? detail.warnings.map(textValue).filter((item): item is string => Boolean(item)).join('; ')
      : ''
    return warningsText ? `${message} ${warningsText}` : message
  }

  return getApiErrorMessage(error, 'Не удалось опубликовать задание')
}

function hydrate(data: AssignmentBundle) {
  bundle.value = data
  titleDraft.value = data.assignment.title
  descriptionDraft.value = data.assignment.description || ''
  timeLimitDraft.value = data.assignment.time_limit_minutes ?? null
  notesDraft.value = data.assignment.review_notes || data.reference_graph.review_notes || ''
  const graph = data.reference_graph.graph_data
  const mappedNodes = jsonArray(graph, 'nodes').map(toFlowNode)
  const mappedEdges = normalizeFlowEdges(jsonArray(graph, 'edges')) as FlowEdge[]
  // Reference solution opens in clinical-stage blocks; frame nodes are presentation
  // only and are stripped again on save (see saveDraft).
  nodes.value = applyBlockLayout(mappedNodes, mappedEdges)
  edges.value = mappedEdges
}

async function loadBundle() {
  loading.value = true
  errorText.value = ''
  try {
    const data = await api.endpoint('GET', `/assignments/${assignmentId.value}/review-bundle` as `/assignments/${number}/review-bundle`, {
      accessToken: auth.accessToken,
    })
    hydrate(data)
  } catch (error) {
    errorText.value = getApiErrorMessage(error, 'Не удалось загрузить задание')
  } finally {
    loading.value = false
  }
}

async function saveDraft(status: AssignmentStatus = 'needs_teacher_review') {
  saving.value = true
  errorText.value = ''
  notice.value = ''
  try {
    const body: AssignmentDraftUpdate = {
      title: titleDraft.value,
      description: descriptionDraft.value || null,
      time_limit_minutes: timeLimitDraft.value,
      review_notes: notesDraft.value || null,
      graph_data: toGraphSchema(),
      status,
    }
    const updated = await api.endpoint('PATCH', `/assignments/${assignmentId.value}/draft` as `/assignments/${number}/draft`, {
      accessToken: auth.accessToken,
      body: {
        ...body,
      },
    })
    hydrate(updated)
    notice.value = 'Черновик сохранён, автоматический аудит эталона пересчитан.'
    return true
  } catch (error) {
    errorText.value = getApiErrorMessage(error, 'Не удалось сохранить черновик')
    return false
  } finally {
    saving.value = false
  }
}

async function approveReference(force = false) {
  if (!canApproveReference.value) return
  approving.value = true
  errorText.value = ''
  notice.value = ''
  try {
    const saved = await saveDraft('needs_teacher_review')
    if (!saved) return
    const body: AssignmentApproveReferenceRequest = {
      review_notes: notesDraft.value || null,
      force,
    }
    const updated = await api.endpoint('POST', `/assignments/${assignmentId.value}/approve-reference` as `/assignments/${number}/approve-reference`, {
      accessToken: auth.accessToken,
      body,
    })
    hydrate(updated)
    notice.value = 'Эталонный граф подтверждён преподавателем. Теперь задание можно опубликовать студентам.'
  } catch (error) {
    errorText.value = publishErrorMessage(error)
  } finally {
    approving.value = false
  }
}

async function publish(force = false) {
  if (!canPublish.value) return
  publishing.value = true
  errorText.value = ''
  notice.value = ''
  try {
    const body: AssignmentPublishRequest = {
      review_notes: notesDraft.value || null,
      force,
    }
    const updated = await api.endpoint('POST', `/assignments/${assignmentId.value}/publish` as `/assignments/${number}/publish`, {
      accessToken: auth.accessToken,
      body,
    })
    hydrate(updated)
    notice.value = 'Задание опубликовано и теперь доступно студентам.'
  } catch (error) {
    errorText.value = publishErrorMessage(error)
  } finally {
    publishing.value = false
  }
}

onMounted(loadBundle)
</script>

<template>
  <v-container fluid class="assignment-review-page pa-3 pa-md-6">
    <PageHeader
      eyebrow="Преподавательский контроль"
      title="Ревизия клинического задания"
      subtitle="AI-граф является черновиком. Перед публикацией преподаватель должен проверить протокольную обоснованность, исправить граф и подтвердить ответственность за эталон."
    >
      <template #actions>
        <StatusChip :status="bundle?.assignment.status" :text="statusText" />
        <v-btn variant="tonal" color="primary" prepend-icon="mdi-refresh" :loading="loading" @click="loadBundle">Обновить</v-btn>
      </template>
    </PageHeader>

    <v-alert v-if="errorText" type="error" variant="tonal" rounded="lg" class="mb-4" closable @click:close="errorText = ''">
      {{ errorText }}
    </v-alert>
    <v-alert v-if="notice" type="success" variant="tonal" rounded="lg" class="mb-4" closable @click:close="notice = ''">
      {{ notice }}
    </v-alert>

    <v-row v-if="loading">
      <v-col cols="12"><v-skeleton-loader type="article" /></v-col>
    </v-row>

    <v-row v-else-if="bundle">
      <v-col cols="12" lg="4">
        <v-card class="panel" elevation="0">
          <v-card-title>Паспорт задания</v-card-title>
          <v-card-text class="d-flex flex-column ga-3">
            <v-text-field v-model="titleDraft" label="Название задания" variant="outlined" density="comfortable" />
            <v-textarea v-model="descriptionDraft" label="Описание для студента" variant="outlined" density="comfortable" rows="5" auto-grow />
            <v-text-field
              v-model.number="timeLimitDraft"
              label="Лимит времени (минуты)"
              type="number"
              min="5"
              max="1440"
              variant="outlined"
              density="comfortable"
              hint="Оставьте пустым, если ограничение по времени не требуется"
              persistent-hint
              clearable
            />
            <v-textarea v-model="notesDraft" label="Заметки преподавателя / экспертное обоснование" variant="outlined" density="comfortable" rows="4" auto-grow />

            <v-alert type="info" variant="tonal" density="compact" rounded="lg">
              Опубликованные задания попадают студентам. Черновики и задания на проверке видны только преподавателям, экспертам и администраторам.
            </v-alert>

            <v-row dense>
              <v-col cols="12" sm="6">
                <MetricCard
                  title="Критические"
                  :value="criticalCount"
                  :color="criticalCount ? 'error' : 'success'"
                  icon="mdi-alert-octagon-outline"
                />
              </v-col>
              <v-col cols="12" sm="6">
                <MetricCard
                  title="Предупреждения"
                  :value="warningCount"
                  :color="warningCount ? 'warning' : 'success'"
                  icon="mdi-alert-circle-outline"
                />
              </v-col>
              <v-col cols="12" sm="6">
                <MetricCard title="Качество" :value="qualityScoreText" icon="mdi-chart-line" />
              </v-col>
              <v-col cols="12" sm="6">
                <MetricCard title="Эталон" :value="referenceStatusText" icon="mdi-source-branch-check" />
              </v-col>
            </v-row>

            <v-expansion-panels v-if="warnings.length" variant="accordion" density="compact">
              <v-expansion-panel title="Предупреждения автоматического аудита">
                <v-expansion-panel-text>
                  <v-list density="compact" bg-color="transparent">
                    <v-list-item v-for="(item, index) in warnings" :key="index" prepend-icon="mdi-alert-circle-outline">
                      <v-list-item-title>{{ item }}</v-list-item-title>
                    </v-list-item>
                  </v-list>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
            <EmptyState
              v-else
              icon="mdi-check-circle-outline"
              title="Предупреждений аудита нет"
              color="success"
            />

            <v-expansion-panels v-if="sourceRows.length" variant="accordion" density="compact">
              <v-expansion-panel title="Источники протокола">
                <v-expansion-panel-text>
                  <div v-for="(src, i) in sourceRows" :key="i" class="source-row">
                    <div class="font-weight-bold">{{ src.title }}</div>
                    <div class="text-caption text-medium-emphasis">{{ src.meta }}</div>
                    <a v-if="src.url" class="source-link text-caption" :href="src.url" target="_blank" rel="noopener">
                      Открыть протокол
                    </a>
                  </div>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </v-card-text>
          <v-card-actions class="px-4 pb-4 d-flex flex-column ga-2">
            <v-btn block color="primary" variant="tonal" :loading="saving" @click="saveDraft()">
              Сохранить черновик
            </v-btn>
            <v-btn
              block
              color="success"
              variant="tonal"
              :disabled="!canApproveReference || bundle.assignment.status === 'published'"
              :loading="approving"
              @click="approveReference(false)"
            >
              Подтвердить эталон
            </v-btn>
            <v-alert
              v-if="!isReferenceApproved"
              type="info"
              variant="tonal"
              density="compact"
              rounded="lg"
              class="w-100"
            >
              Перед публикацией преподаватель должен проверить и подтвердить эталонный граф.
            </v-alert>
            <v-btn block color="success" variant="flat" :disabled="!canPublish" :loading="publishing" @click="publish(false)">
              Опубликовать студентам
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" lg="8">
        <v-card class="panel" elevation="0">
          <v-card-title class="d-flex align-center">
            Эталонное решение
            <v-spacer />
            <v-chip size="small" color="primary" variant="tonal">Reference #{{ bundle.reference_graph.id }}</v-chip>
          </v-card-title>
          <v-card-text class="pa-0">
            <div class="graph-editor">
              <ClientOnly>
                <GraphFlow v-model:nodes="nodes" v-model:edges="edges" :palette="[]" />
              </ClientOnly>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<style scoped>
.assignment-review-page {
  max-width: 1560px;
  margin: 0 auto;
}

.panel {
  border: 1px solid rgba(var(--v-border-color), 0.12);
  border-radius: 8px !important;
  background: rgba(var(--v-theme-surface), 0.96) !important;
}

.source-row {
  border-bottom: 1px solid rgba(var(--v-border-color), 0.08);
  padding: 8px 0;
}

.source-row:last-child {
  border-bottom: 0;
}

.graph-editor {
  height: calc(100vh - 220px);
  min-height: 620px;
}

@media (max-width: 960px) {
  .graph-editor {
    height: 70vh;
    min-height: 520px;
  }
}
</style>
