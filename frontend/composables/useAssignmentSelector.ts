import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import type { AssignmentProgressPublic, AssignmentPublic, GraphNode } from '~/types/api'
import type { FlowNode } from '~/types/graph'
import { createApiClient } from '~/utils/apiClient'
import { useAssignmentTimer } from '~/composables/useAssignmentTimer'
import type { useAuthStore } from '~/stores/auth'
import type { useClinicalCaseStore } from '~/stores/clinicalCase'

type AuthStore = ReturnType<typeof useAuthStore>
type ClinicalCaseStore = ReturnType<typeof useClinicalCaseStore>

interface UseAssignmentSelectorOptions {
  auth: AuthStore
  store: ClinicalCaseStore
  nodes: Ref<FlowNode[]>
  notify: (message: string) => void
}

interface AssignmentSelectorState {
  assignmentId: Ref<number | null>
  assignments: Ref<AssignmentPublic[]>
  assignmentsLoading: Ref<boolean>
  showAssignmentDialog: Ref<boolean>
  selectedAssignment: ComputedRef<AssignmentPublic | null>
  selectedRefId: ComputedRef<number>
  assignmentDescription: ComputedRef<string>
  assignmentTimer: ReturnType<typeof useAssignmentTimer>
  fetchAssignments: () => Promise<void>
  fetchInitialNodes: (id: number) => Promise<void>
  startCurrentAssignment: (id?: number | null) => Promise<void>
}

function readSingleQueryValue(value: unknown): string | null {
  if (Array.isArray(value)) {
    return typeof value[0] === 'string' ? value[0] : null
  }

  return typeof value === 'string' ? value : null
}

function readRouteAssignmentId(value: unknown): number | null {
  const raw = readSingleQueryValue(value)
  if (!raw) return null

  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : null
}

function shouldAutoStart(value: unknown): boolean {
  return readSingleQueryValue(value) === '1'
}

function toInitialFlowNode(node: GraphNode, index: number): FlowNode {
  return {
    id: String(node.id),
    type: 'med',
    position: {
      x: 100,
      y: 100 + index * 100,
    },
    data: {
      label: node.data.label,
      category: node.data.category,
    },
  }
}

function updateAssignmentProgress(
  assignment: AssignmentPublic,
  progress: AssignmentProgressPublic,
): AssignmentPublic {
  return {
    ...assignment,
    deadline_at: progress.deadline_at,
    completed_at: progress.completed_at,
    latest_attempt_id: progress.latest_attempt_id,
    latest_score: progress.latest_score,
    progress_status: progress.status,
    started_at: progress.started_at,
    submitted_at: progress.submitted_at,
  }
}

function extractApiMessage(error: unknown, fallback: string): string {
  if (typeof error === 'object' && error !== null) {
    const record = error as Record<string, unknown>
    const data = record.data
    if (typeof data === 'object' && data !== null) {
      const detail = (data as Record<string, unknown>).detail
      if (typeof detail === 'string') return detail
    }
    if (typeof record.message === 'string') return record.message
  }

  return fallback
}

export function useAssignmentSelector(options: UseAssignmentSelectorOptions): AssignmentSelectorState {
  const route = useRoute()
  const api = createApiClient()

  const assignmentId = ref<number | null>(null)
  const assignments = ref<AssignmentPublic[]>([])
  const assignmentsLoading = ref(false)
  const showAssignmentDialog = ref(false)
  const suppressAssignmentWatcher = ref(false)
  let assignmentsRequest: Promise<void> | null = null

  const selectedAssignment = computed(() =>
    assignments.value.find((assignment) => assignment.id === assignmentId.value) ?? null,
  )
  const selectedRefId = computed(() => selectedAssignment.value?.reference_graph_id ?? 1)
  const assignmentDescription = computed(() =>
    selectedAssignment.value?.description || 'Выберите задание из списка, чтобы увидеть виньетку.',
  )
  const assignmentTimer = useAssignmentTimer(() => selectedAssignment.value?.deadline_at)

  async function fetchAssignments(): Promise<void> {
    if (assignmentsRequest) {
      return await assignmentsRequest
    }

    assignmentsRequest = (async () => {
      assignmentsLoading.value = true

      try {
        const response = await api.endpoint('GET', '/assignments', {
          accessToken: options.auth.accessToken,
        })

        assignments.value = response.items ?? []
        const routeAssignmentId = readRouteAssignmentId(route.query.assignment)

        if (routeAssignmentId && assignments.value.some((item) => item.id === routeAssignmentId)) {
          assignmentId.value = routeAssignmentId
          return
        }

        if (assignments.value.length && assignmentId.value == null) {
          assignmentId.value = assignments.value[0].id
        }
      } catch {
        assignments.value = []
      } finally {
        assignmentsLoading.value = false
        assignmentsRequest = null
      }
    })()

    return await assignmentsRequest
  }

  async function fetchInitialNodes(id: number): Promise<void> {
    try {
      const response = await api.endpoint('GET', `/assignments/${id}/initial-nodes`, {
        accessToken: options.auth.accessToken,
      })

      options.nodes.value = response.map(toInitialFlowNode)
    } catch (error) {
      console.error('Ошибка загрузки начальных узлов', error)
    }
  }

  async function startCurrentAssignment(id = assignmentId.value): Promise<void> {
    if (!id || options.auth.user?.role !== 'student') return

    try {
      const progress = await api.endpoint('POST', `/assignments/${id}/start`, {
        accessToken: options.auth.accessToken,
      })

      assignments.value = assignments.value.map((assignment) =>
        assignment.id === id ? updateAssignmentProgress(assignment, progress) : assignment,
      )
    } catch (error) {
      options.notify(extractApiMessage(error, 'Не удалось начать задание'))
    }
  }

  watch(assignmentId, async (newValue, oldValue) => {
    if (suppressAssignmentWatcher.value) return
    if (!newValue || newValue === oldValue) return

    if (import.meta.client && options.nodes.value.length > 0) {
      const confirmed = confirm('При смене задания текущий граф будет очищен. Продолжить?')
      if (!confirmed) {
        assignmentId.value = oldValue
        return
      }
    }

    options.store.resetGraph()
    await fetchInitialNodes(newValue)

    if (shouldAutoStart(route.query.start)) {
      await startCurrentAssignment(newValue)
    }

    // Baseline the undo history on the freshly loaded graph so the first undo
    // can't wipe the assignment's pre-placed nodes.
    options.store.resetHistory()
  })

  return {
    assignmentId,
    assignments,
    assignmentsLoading,
    showAssignmentDialog,
    selectedAssignment,
    selectedRefId,
    assignmentDescription,
    assignmentTimer,
    fetchAssignments,
    fetchInitialNodes,
    startCurrentAssignment,
  }
}
