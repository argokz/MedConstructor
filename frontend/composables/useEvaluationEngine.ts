import { computed, ref, type ComputedRef, type Ref } from 'vue'
import type {
  AssignmentPublic,
  GraphEdge as ApiGraphEdge,
  GraphEvaluationResponse,
  GraphHintsRequest,
  GraphNode as ApiGraphNode,
  GraphSchema,
} from '~/types/api'
import type { FlowEdge, FlowNode, GraphNodeCategory, PaletteItem } from '~/types/graph'
import { applyBlockLayout, placeGhostNodes } from '~/composables/useGraphLayout'
import { normalizeFlowEdges, serializeStudentGraph, toPlainEdges, toPlainNodes } from '~/composables/useGraphPayload'
import { createApiClient } from '~/utils/apiClient'
import { renderSafeMarkdown } from '~/utils/markdown'
import type { useAssignmentTimer } from '~/composables/useAssignmentTimer'
import type { useAuthStore } from '~/stores/auth'

type AuthStore = ReturnType<typeof useAuthStore>
type AssignmentTimerState = ReturnType<typeof useAssignmentTimer>

interface UseEvaluationEngineOptions {
  auth: AuthStore
  nodes: Ref<FlowNode[]>
  edges: Ref<FlowEdge[]>
  reviewMode: Ref<boolean>
  evalResult: Ref<GraphEvaluationResponse | null>
  selectedNode: Ref<FlowNode | null>
  assignmentId: Ref<number | null>
  assignments: Ref<AssignmentPublic[]>
  selectedRefId: ComputedRef<number>
  assignmentTimer: AssignmentTimerState
  dbPalette: Ref<PaletteItem[]>
  loading: Ref<boolean>
  notify: (message: string) => void
  resetGraph: () => void
}

interface HintItem {
  text: string
  priority: number
}

interface HintsResult {
  hints: HintItem[]
  summary: string
}

function metricValue(value?: number | null): number {
  return Math.min(100, Math.max(0, Number(value ?? 0) * 100))
}

function metricPercent(value?: number | null): number {
  return Math.round(metricValue(value))
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function detailToMessage(detail: unknown): string | null {
  if (typeof detail === 'string') return detail

  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      if (isRecord(item) && typeof item.msg === 'string') return item.msg
      return JSON.stringify(item)
    })

    return messages.length ? messages.join('; ') : null
  }

  return null
}

function extractApiMessage(error: unknown, fallback: string): string {
  if (!isRecord(error)) return fallback

  const data = error.data
  if (isRecord(data)) {
    const detailMessage = detailToMessage(data.detail)
    if (detailMessage) return detailMessage
  }

  return typeof error.message === 'string' ? error.message : fallback
}

function serializedGraph(nodes: FlowNode[], edges: FlowEdge[]): GraphSchema {
  return serializeStudentGraph(nodes, edges) as GraphSchema
}

function evaluationIdempotencyKey(
  graph: GraphSchema,
  assignmentId: number | null,
  referenceGraphId: number,
  studentId: number,
): string {
  const labelsById = new Map(
    graph.nodes.map((node) => [String(node.id), `${node.data.category}:${node.data.label.trim().toLowerCase()}`]),
  )
  const payload = JSON.stringify({
    assignmentId,
    referenceGraphId,
    studentId,
    nodes: Array.from(labelsById.values()).sort(),
    edges: graph.edges.map((edge) => [
      labelsById.get(String(edge.source)) || String(edge.source),
      labelsById.get(String(edge.target)) || String(edge.target),
      String(edge.label || '').toUpperCase(),
    ]).sort((left, right) => JSON.stringify(left).localeCompare(JSON.stringify(right))),
  })
  let hash = 2166136261
  for (let index = 0; index < payload.length; index += 1) {
    hash ^= payload.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return `evaluate-v1-${(hash >>> 0).toString(16)}`
}

function getLabelById(nodes: FlowNode[], id: string): string {
  const node = nodes.find((item) => item.id === id)
  return node ? node.data.label : ''
}

function normalizeRelation(relation: string | undefined): string {
  return (relation || 'unknown').toLowerCase().trim()
}

function isIncorrectEdge(edge: FlowEdge, incorrectEdges: Record<string, string>[], nodes: FlowNode[]): boolean {
  const sourceLabel = getLabelById(nodes, edge.source).toLowerCase()
  const targetLabel = getLabelById(nodes, edge.target).toLowerCase()
  const relation = normalizeRelation(typeof edge.label === 'string' ? edge.label : undefined)

  return incorrectEdges.some((incorrectEdge) => {
    if (incorrectEdge.id) return incorrectEdge.id === edge.id

    return incorrectEdge.source.toLowerCase() === sourceLabel
      && incorrectEdge.target.toLowerCase() === targetLabel
      && normalizeRelation(incorrectEdge.relation) === relation
  })
}

function toCanvasNode(node: ApiGraphNode): FlowNode {
  return {
    id: String(node.id),
    type: node.type === 'frame' ? 'frame' : 'med',
    position: {
      x: Number(node.position.x ?? 0),
      y: Number(node.position.y ?? 0),
    },
    data: {
      label: node.data.label,
      category: node.data.category,
    },
  }
}

function hasGraphPayload(value: GraphSchema | null | undefined): value is GraphSchema {
  return Boolean(value && Array.isArray(value.nodes) && Array.isArray(value.edges))
}

function toFlowEdges(edges: ApiGraphEdge[]): FlowEdge[] {
  return normalizeFlowEdges(edges) as FlowEdge[]
}

export function useEvaluationEngine(options: UseEvaluationEngineOptions) {
  const api = createApiClient()

  const evalError = ref<string | null>(null)
  const showReferenceDialog = ref(false)
  const referenceNodes = ref<FlowNode[]>([])
  const referenceEdges = ref<FlowEdge[]>([])
  const hintsResult = ref<HintsResult | null>(null)
  const hintsLoading = ref(false)
  const hintError = ref<string | null>(null)
  const feedbackResult = ref<string | null>(null)
  const feedbackLoading = ref(false)
  const showFeedbackDialog = ref(false)

  const formattedFeedback = computed(() => renderSafeMarkdown(feedbackResult.value))

  function hintsBody(): GraphHintsRequest {
    return {
      reference_graph_id: options.selectedRefId.value,
      student_graph: serializedGraph(options.nodes.value, options.edges.value),
      incorrect_edges: options.evalResult.value?.incorrect_edges ?? [],
      missing_edges: options.evalResult.value?.missing_edges ?? [],
    }
  }

  async function fetchHints(): Promise<void> {
    hintsLoading.value = true
    hintsResult.value = null
    hintError.value = null

    try {
      hintsResult.value = await api.endpoint('POST', '/graph/hints', {
        accessToken: options.auth.accessToken,
        body: hintsBody(),
      })
    } catch (error) {
      hintError.value = extractApiMessage(error, 'Ошибка получения подсказок')
    } finally {
      hintsLoading.value = false
    }
  }

  async function fetchFeedback(): Promise<void> {
    feedbackLoading.value = true
    feedbackResult.value = null
    showFeedbackDialog.value = true

    try {
      const response = await api.endpoint('POST', '/graph/feedback', {
        accessToken: options.auth.accessToken,
        body: hintsBody(),
      })
      feedbackResult.value = response.feedback
    } catch (error) {
      feedbackResult.value = `Ошибка получения отчета: ${extractApiMessage(error, '')}`
    } finally {
      feedbackLoading.value = false
    }
  }

  async function submitGraph(): Promise<void> {
    evalError.value = null
    options.evalResult.value = null

    if (!options.auth.userId) {
      evalError.value = 'Войдите в систему, чтобы сохранить и проверить решение.'
      options.notify('Нужна авторизация')
      await navigateTo('/login')
      return
    }

    try {
      const studentGraph = serializedGraph(options.nodes.value, options.edges.value)

      if (studentGraph.nodes.length >= 2 && studentGraph.edges.length === 0) {
        evalError.value = 'Добавьте связи между блоками. Без рёбер граф не может быть оценён.'
        options.notify('Нужны связи между блоками')
        return
      }

      if (options.assignmentTimer.isExpired.value) {
        evalError.value = 'Время на выполнение задания истекло.'
        options.notify('Время вышло')
        return
      }

      const response = await api.endpoint('POST', '/evaluate', {
        accessToken: options.auth.accessToken,
        timeout: 30_000,
        body: {
          assignment_id: options.assignmentId.value,
          reference_graph_id: options.selectedRefId.value,
          student_graph: studentGraph,
          student_id: Number(options.auth.userId),
          idempotency_key: evaluationIdempotencyKey(
            studentGraph,
            options.assignmentId.value,
            options.selectedRefId.value,
            Number(options.auth.userId),
          ),
        },
      })

      options.evalResult.value = response
      options.reviewMode.value = true

      if (options.assignmentId.value) {
        options.assignments.value = options.assignments.value.map((assignment) =>
          assignment.id === options.assignmentId.value
            ? {
                ...assignment,
                latest_score: Number(response.composite_score ?? response.f1_score ?? assignment.latest_score),
                progress_status: 'submitted',
              }
            : assignment,
        )
      }

      options.edges.value = (toPlainEdges(options.edges.value) as FlowEdge[]).map((edge) => {
        const isIncorrect = isIncorrectEdge(edge, response.incorrect_edges ?? [], options.nodes.value)

        return {
          ...edge,
          data: {
            ...edge.data,
            isCorrect: !isIncorrect,
            isIncorrect,
          },
        }
      })

      const missingLabels = new Set<string>()
      for (const missingEdge of response.missing_edges ?? []) {
        if (!options.nodes.value.some((node) => node.data.label.toLowerCase() === missingEdge.source.toLowerCase())) {
          missingLabels.add(missingEdge.source)
        }
        if (!options.nodes.value.some((node) => node.data.label.toLowerCase() === missingEdge.target.toLowerCase())) {
          missingLabels.add(missingEdge.target)
        }
      }

      const ghostNodes = placeGhostNodes(
        options.nodes.value,
        Array.from(missingLabels),
        (label): GraphNodeCategory => {
          const matched = options.dbPalette.value.find((item) => item.label.toLowerCase() === label.toLowerCase())
          return matched ? matched.category : 'SYMPTOM'
        },
      )

      options.nodes.value = [...(toPlainNodes(options.nodes.value) as FlowNode[]), ...ghostNodes]
      options.notify('Решение проверено!')
    } catch (error) {
      evalError.value = extractApiMessage(error, 'Ошибка отправки решения')
      options.notify('Ошибка API проверки')
    }
  }

  async function showReferenceGraph(): Promise<void> {
    if (!options.assignmentId.value) return

    options.loading.value = true

    try {
      const response = await api.endpoint('GET', `/assignments/${options.assignmentId.value}/reference`, {
        accessToken: options.auth.accessToken,
      })

      if (hasGraphPayload(response)) {
        const mappedNodes = response.nodes.map(toCanvasNode)
        const mappedEdges = toFlowEdges(response.edges)
        // Open the reference in a read-only viewer instead of overwriting the
        // user's own graph on the canvas — their work stays intact.
        referenceNodes.value = applyBlockLayout(mappedNodes, mappedEdges) as FlowNode[]
        referenceEdges.value = mappedEdges
        showReferenceDialog.value = true
      } else {
        options.notify('Задание не имеет сохраненного эталонного графа.')
      }
    } catch {
      options.notify('Ошибка загрузки эталонного графа')
    } finally {
      options.loading.value = false
    }
  }

  function onValidationError(message: string): void {
    options.notify(message)
  }

  function backToEditing(): void {
    options.reviewMode.value = false
    options.evalResult.value = null
    options.selectedNode.value = null

    options.nodes.value = (toPlainNodes(options.nodes.value) as FlowNode[])
      .filter((node) => !node.data.isGhost)
      .map((node) => ({
        ...node,
        data: {
          ...node.data,
          isCorrect: false,
          isIncorrect: false,
        },
      }))

    options.edges.value = (toPlainEdges(options.edges.value) as FlowEdge[]).map((edge) => ({
      ...edge,
      data: {
        ...edge.data,
        isCorrect: false,
        isIncorrect: false,
      },
    }))
  }

  // Confirmation lives in the toolbar dialog (ConstructorToolbar), so this
  // resets unconditionally.
  function resetCanvas(): void {
    options.resetGraph()
  }

  function clearHints(): void {
    hintsResult.value = null
    hintError.value = null
  }

  return {
    evalError,
    showReferenceDialog,
    referenceNodes,
    referenceEdges,
    hintsResult,
    hintsLoading,
    hintError,
    feedbackResult,
    feedbackLoading,
    showFeedbackDialog,
    formattedFeedback,
    metricValue,
    metricPercent,
    fetchHints,
    fetchFeedback,
    submitGraph,
    showReferenceGraph,
    onValidationError,
    backToEditing,
    resetCanvas,
    clearHints,
  }
}
