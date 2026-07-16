import { acceptHMRUpdate, defineStore, skipHydrate } from 'pinia'
import { computed, nextTick, ref, watch } from 'vue'
import { toPlainEdges, toPlainNodes } from '~/composables/useGraphPayload'
import type { ClinicalCaseEvaluation, ClinicalTaskSummary, FlowEdge, FlowNode } from '~/types/graph'

export type MedNode = FlowNode
export type MedEdge = FlowEdge

const MAX_HISTORY = 60

interface GraphSnapshot {
  nodes: MedNode[]
  edges: MedEdge[]
}

export const useClinicalCaseStore = defineStore('clinicalCase', () => {
  const currentTask = ref<ClinicalTaskSummary | null>(null)

  const nodes = ref<MedNode[]>([])
  const edges = ref<MedEdge[]>([])

  const reviewMode = ref(false)
  const evalResult = ref<ClinicalCaseEvaluation>(null)

  // Highlight node label / ID for AI feedback hover effects
  const activeHighlightNodeId = ref<string | null>(null)
  const selectedNode = ref<MedNode | null>(null)

  // --- Undo / redo history -------------------------------------------------
  // Snapshots hold plain clones (Vue Flow's augmented objects are stripped via
  // toPlainNode/Edge) so restores never corrupt the canvas. Auto-commit is
  // debounced so a drag produces a single history entry, and is suppressed
  // while restoring or in review mode.
  const history = ref<GraphSnapshot[]>([])
  const historyIndex = ref(-1)
  let isRestoring = false
  let commitTimer: ReturnType<typeof setTimeout> | null = null

  const canUndo = computed(() => historyIndex.value > 0)
  const canRedo = computed(() => historyIndex.value < history.value.length - 1)

  function snapshot(): GraphSnapshot {
    return {
      nodes: toPlainNodes(nodes.value) as MedNode[],
      edges: toPlainEdges(edges.value) as MedEdge[],
    }
  }

  function commitHistory(): void {
    const snap = snapshot()
    const prev = history.value[historyIndex.value]
    if (prev && JSON.stringify(prev) === JSON.stringify(snap)) {
      return
    }
    const next = history.value.slice(0, historyIndex.value + 1)
    next.push(snap)
    while (next.length > MAX_HISTORY) {
      next.shift()
    }
    history.value = next
    historyIndex.value = next.length - 1
  }

  function scheduleCommit(): void {
    if (isRestoring || reviewMode.value) {
      return
    }
    if (commitTimer) {
      clearTimeout(commitTimer)
    }
    commitTimer = setTimeout(commitHistory, 350)
  }

  function restore(index: number): void {
    const snap = history.value[index]
    if (!snap) {
      return
    }
    isRestoring = true
    nodes.value = toPlainNodes(snap.nodes) as MedNode[]
    edges.value = toPlainEdges(snap.edges) as MedEdge[]
    selectedNode.value = null
    historyIndex.value = index
    void nextTick(() => {
      isRestoring = false
    })
  }

  function undo(): void {
    if (canUndo.value) {
      restore(historyIndex.value - 1)
    }
  }

  function redo(): void {
    if (canRedo.value) {
      restore(historyIndex.value + 1)
    }
  }

  /** Reset the history stack to the current graph as the single baseline. */
  function resetHistory(): void {
    if (commitTimer) {
      clearTimeout(commitTimer)
      commitTimer = null
    }
    history.value = [snapshot()]
    historyIndex.value = 0
  }

  watch([nodes, edges], scheduleCommit, { deep: true })

  function resetGraph() {
    nodes.value = []
    edges.value = []
    reviewMode.value = false
    evalResult.value = null
    activeHighlightNodeId.value = null
    selectedNode.value = null
    resetHistory()
  }

  function setHighlightNodeByLabel(label: string) {
    if (!label) {
      activeHighlightNodeId.value = null
      return
    }
    // Find node with matching label
    const node = nodes.value.find(
      (n) => n.data.label.toLowerCase() === label.toLowerCase()
    )
    if (node) {
      activeHighlightNodeId.value = node.id
    } else {
      activeHighlightNodeId.value = null
    }
  }

  function clearHighlight() {
    activeHighlightNodeId.value = null
  }

  return {
    currentTask,
    nodes: skipHydrate(nodes),
    edges: skipHydrate(edges),
    reviewMode,
    evalResult,
    activeHighlightNodeId,
    selectedNode,
    resetGraph,
    setHighlightNodeByLabel,
    clearHighlight,
    canUndo,
    canRedo,
    undo,
    redo,
    resetHistory,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useClinicalCaseStore, import.meta.hot))
}
