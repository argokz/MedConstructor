import { storeToRefs } from 'pinia'
import { computed, onActivated, onMounted, onUnmounted, ref, watch } from 'vue'
import type { ConceptSuggestion } from '~/types/api'
import type { FlowNode, GraphNodeCategory, NodeDataDto, PaletteItem } from '~/types/graph'
import { toPlainNode, toPlainNodes } from '~/composables/useGraphPayload'
import { CATEGORY_OPTIONS, categoryPluralTitle } from '~/constants/clinicalOntology'
import { createApiClient } from '~/utils/apiClient'
import { useAuthStore } from '~/stores/auth'
import { useClinicalCaseStore } from '~/stores/clinicalCase'

interface PalettePanel {
  cat: GraphNodeCategory
  items: PaletteItem[]
}

interface CategoryOption {
  value: string
  title: string
}

const PALETTE_FRAME_ITEM: PaletteItem = { label: 'Рамка группы', category: '__frame__' }

const CATEGORIES_OPTIONS: CategoryOption[] = CATEGORY_OPTIONS

const categoryTitle = categoryPluralTitle

function normalizePaletteCategory(category: string): GraphNodeCategory {
  return category.toUpperCase().trim()
}

function preparePaletteItem(item: PaletteItem): PaletteItem {
  const dragItem: PaletteItem = { ...item }

  if (dragItem.category === 'MEDICATION') {
    dragItem.dosage = dragItem.dosage || ''
    dragItem.route = dragItem.route || ''
  } else if (dragItem.category === 'LAB_TEST' || dragItem.category === 'INSTRUMENTAL_TEST') {
    dragItem.expected_value = dragItem.expected_value || ''
  } else if (dragItem.category === 'DISEASE') {
    dragItem.stage = dragItem.stage || ''
  }

  return dragItem
}

function toSearchPaletteItem(suggestion: ConceptSuggestion): PaletteItem {
  const normalized = normalizePaletteCategory(suggestion.category)
  return {
    category: normalized === 'DISEASE' ? 'DIAGNOSIS' : normalized,
    isSearchResult: true,
    label: suggestion.name,
  }
}

export function useConstructorWorkspace() {
  const auth = useAuthStore()
  const store = useClinicalCaseStore()
  const api = createApiClient()
  const { nodes, edges, reviewMode, evalResult, selectedNode, canUndo, canRedo } = storeToRefs(store)

  const snackbar = ref(false)
  const snackText = ref('')
  const loading = ref(false)
  const leftDrawer = ref(false)
  const rightDrawer = ref(false)
  const dbPalette = ref<PaletteItem[]>([])
  const paletteTotal = ref(0)
  const paletteLoading = ref(false)
  const paletteSearchLoading = ref(false)
  const paletteSearch = ref('')
  const paletteSearchActive = ref(false)
  const paletteSearchResults = ref<PaletteItem[]>([])
  const paletteScope = ref<'assignment' | 'full'>('assignment')
  const assignmentPaletteCategories = ref<string[]>([])
  const activePaletteCategory = ref('ALL')
  let paletteSearchTimer: ReturnType<typeof setTimeout> | null = null
  let paletteRequest: Promise<void> | null = null
  let paletteRequestKey: string | null = null
  let loadedAssignmentPaletteId: number | null = null
  let fullPaletteLoaded = false
  let constructorDataRequest: Promise<void> | null = null

  function notify(message: string): void {
    snackText.value = message
    snackbar.value = true
  }

  const assignmentSelector = useAssignmentSelector({
    auth,
    nodes,
    notify,
    store,
  })

  const evaluation = useEvaluationEngine({
    assignmentId: assignmentSelector.assignmentId,
    assignmentTimer: assignmentSelector.assignmentTimer,
    assignments: assignmentSelector.assignments,
    auth,
    dbPalette,
    edges,
    evalResult,
    loading,
    nodes,
    notify,
    resetGraph: store.resetGraph,
    reviewMode,
    selectedNode,
    selectedRefId: assignmentSelector.selectedRefId,
  })

  const paletteFilterCategories = computed<CategoryOption[]>(() => {
    const categories = paletteScope.value === 'assignment' && assignmentPaletteCategories.value.length
      ? [...assignmentPaletteCategories.value]
      : Array.from(new Set(dbPalette.value.map((item) => item.category))).sort()

    return [
      { value: 'ALL', title: 'Все' },
      { value: '__frame__', title: 'Оформление' },
      ...categories.map((category) => ({ value: category, title: categoryTitle(category) })),
    ]
  })

  const displayedPaletteItems = computed<PaletteItem[]>(() => {
    if (activePaletteCategory.value === '__frame__') {
      return [PALETTE_FRAME_ITEM]
    }

    const source = paletteSearchActive.value && paletteSearch.value.trim().length >= 2
      ? paletteSearchResults.value
      : dbPalette.value

    if (activePaletteCategory.value === 'ALL') {
      return source
    }

    return source.filter((item) => item.category === activePaletteCategory.value)
  })

  const paletteGroups = computed<PalettePanel[]>(() => {
    const items = displayedPaletteItems.value
    if (!items.length) {
      return []
    }

    if (activePaletteCategory.value !== 'ALL' && activePaletteCategory.value !== '__frame__') {
      return [{ cat: activePaletteCategory.value as GraphNodeCategory, items }]
    }

    if (activePaletteCategory.value === '__frame__') {
      return [{ cat: '__frame__', items }]
    }

    const grouped = new Map<string, PaletteItem[]>()
    for (const item of items) {
      const bucket = grouped.get(item.category) ?? []
      bucket.push(item)
      grouped.set(item.category, bucket)
    }

    const categoryOrder = paletteFilterCategories.value
      .map((category) => category.value)
      .filter((value) => value !== 'ALL' && value !== '__frame__')

    return categoryOrder
      .filter((category) => grouped.has(category))
      .map((category) => ({
        cat: category as GraphNodeCategory,
        items: grouped.get(category) ?? [],
      }))
  })

  const hasPaletteItems = computed(() => displayedPaletteItems.value.length > 0)

  const paletteHint = computed(() => {
    if (paletteSearchActive.value && paletteSearch.value.trim().length >= 2) {
      return `Результаты поиска: ${displayedPaletteItems.value.length}`
    }

    if (paletteScope.value === 'assignment') {
      return `Показаны блоки, релевантные текущему заданию (${dbPalette.value.length})`
    }

    if (paletteTotal.value > dbPalette.value.length) {
      return `Каталог клинических блоков: показано ${dbPalette.value.length} из ${paletteTotal.value}`
    }

    return `Каталог клинических блоков (${dbPalette.value.length})`
  })

  function mapPaletteItems(items: Array<{ label: string; category: string }>): PaletteItem[] {
    return items.map((item) => {
      const category = normalizePaletteCategory(item.category)
      return {
        category: category === 'DISEASE' ? 'DIAGNOSIS' : category,
        label: item.label,
      }
    })
  }

  function suggestApiCategory(category: string): string | undefined {
    const normalized = category.toLowerCase()
    if (normalized === 'diagnosis' || normalized === 'disease') return 'disease'
    if (normalized === '__frame__') return undefined
    return normalized
  }

  async function fetchAssignmentPalette(id: number): Promise<void> {
    if (loadedAssignmentPaletteId === id && paletteScope.value === 'assignment') {
      return
    }

    const requestKey = `assignment:${id}`
    if (paletteRequest && paletteRequestKey === requestKey) {
      return await paletteRequest
    }

    paletteRequestKey = requestKey
    paletteRequest = (async () => {
      paletteLoading.value = true

      try {
        const response = await api.endpoint('GET', `/assignments/${id}/palette`, {
          accessToken: auth.accessToken,
          query: { per_category: 30 },
        })

        dbPalette.value = mapPaletteItems(response.items ?? [])
        paletteTotal.value = dbPalette.value.length
        assignmentPaletteCategories.value = (response.categories ?? []).map((category) =>
          normalizePaletteCategory(category),
        )
        loadedAssignmentPaletteId = id
        fullPaletteLoaded = false
      } catch (error) {
        console.error('Failed to load assignment palette', error)
        dbPalette.value = []
        paletteTotal.value = 0
        assignmentPaletteCategories.value = []
        loadedAssignmentPaletteId = null
      } finally {
        paletteLoading.value = false
        paletteRequest = null
        paletteRequestKey = null
      }
    })()

    return await paletteRequest
  }

  async function fetchFullPalette(): Promise<void> {
    if (fullPaletteLoaded && paletteScope.value === 'full') {
      return
    }

    const requestKey = 'full'
    if (paletteRequest && paletteRequestKey === requestKey) {
      return await paletteRequest
    }

    paletteRequestKey = requestKey
    paletteRequest = (async () => {
      paletteLoading.value = true

      try {
        const response = await api.endpoint('GET', '/concepts/palette', {
          query: { per_category: 30 },
        })

        dbPalette.value = mapPaletteItems(response.items ?? [])
        paletteTotal.value = response.total ?? dbPalette.value.length
        assignmentPaletteCategories.value = Array.from(new Set(dbPalette.value.map((item) => item.category))).sort()
        fullPaletteLoaded = true
        loadedAssignmentPaletteId = null
      } catch (error) {
        console.error('Failed to load palette', error)
        dbPalette.value = []
        paletteTotal.value = 0
        assignmentPaletteCategories.value = []
        fullPaletteLoaded = false
      } finally {
        paletteLoading.value = false
        paletteRequest = null
        paletteRequestKey = null
      }
    })()

    return await paletteRequest
  }

  async function refreshPalette(): Promise<void> {
    if (paletteScope.value === 'full') {
      await fetchFullPalette()
      return
    }

    const assignmentId = assignmentSelector.assignmentId.value
    if (assignmentId) {
      await fetchAssignmentPalette(assignmentId)
    }
  }

  async function runPaletteSearch(query: string): Promise<void> {
    paletteSearchLoading.value = true
    paletteSearchActive.value = true

    try {
      const apiCategory = activePaletteCategory.value !== 'ALL' && activePaletteCategory.value !== '__frame__'
        ? suggestApiCategory(activePaletteCategory.value)
        : undefined

      const response = await api.endpoint('GET', '/concepts/suggest', {
        query: {
          q: query,
          limit: 50,
          ...(apiCategory ? { category: apiCategory } : {}),
        },
      })

      let items = response.map(toSearchPaletteItem)

      if (paletteScope.value === 'assignment' && !apiCategory) {
        const allowed = new Set(assignmentPaletteCategories.value.map((category) => category.toUpperCase()))
        items = items.filter((item) => allowed.has(normalizePaletteCategory(item.category)))
      }

      paletteSearchResults.value = items
    } catch {
      paletteSearchResults.value = []
    } finally {
      paletteSearchLoading.value = false
    }
  }

  function schedulePaletteSearch(query: string): void {
    if (paletteSearchTimer) {
      clearTimeout(paletteSearchTimer)
    }

    const trimmed = query.trim()
    if (trimmed.length < 2) {
      paletteSearchActive.value = false
      paletteSearchResults.value = []
      return
    }

    paletteSearchTimer = setTimeout(() => {
      void runPaletteSearch(trimmed)
    }, 300)
  }

  async function loadConstructorData(): Promise<void> {
    if (constructorDataRequest) {
      return await constructorDataRequest
    }

    constructorDataRequest = (async () => {
      if (!auth.user && auth.accessToken) {
        await auth.fetchMe()
      }
      if (!assignmentSelector.assignments.value.length) {
        await assignmentSelector.fetchAssignments()
      }
      await refreshPalette()
    })().finally(() => {
      constructorDataRequest = null
    })

    return await constructorDataRequest
  }

  watch(
    () => assignmentSelector.assignmentId.value,
    (assignmentId) => {
      paletteSearch.value = ''
      paletteSearchActive.value = false
      paletteSearchResults.value = []
      activePaletteCategory.value = 'ALL'

      if (assignmentId && paletteScope.value === 'assignment') {
        void fetchAssignmentPalette(assignmentId)
      }
    },
  )

  watch(paletteScope, () => {
    paletteSearch.value = ''
    paletteSearchActive.value = false
    paletteSearchResults.value = []
    void refreshPalette()
  })

  watch(paletteSearch, (query) => {
    schedulePaletteSearch(query)
  })

  watch(activePaletteCategory, () => {
    if (paletteSearch.value.trim().length >= 2) {
      void runPaletteSearch(paletteSearch.value.trim())
    }
  })

  function onDragStart(event: DragEvent, item: PaletteItem): void {
    if (!event.dataTransfer) return

    const dragItem = preparePaletteItem(item)
    const payload = JSON.stringify(dragItem)
    event.dataTransfer.setData('application/vueflow', payload)
    event.dataTransfer.setData('application/json', payload)
    event.dataTransfer.setData('text/plain', payload)
    event.dataTransfer.effectAllowed = 'move'
  }

  // The canvas registers its "add block" action here (see pages/index.vue), so
  // palette clicks reach it through a direct call instead of a global event bus.
  let paletteAddHandler: ((item: PaletteItem) => void) | null = null

  function setPaletteAddHandler(handler: ((item: PaletteItem) => void) | null): void {
    paletteAddHandler = handler
  }

  function addPaletteItemToCanvas(item: PaletteItem): void {
    if (reviewMode.value || !paletteAddHandler) return

    const prepared = preparePaletteItem(item)
    paletteAddHandler(prepared)
    selectedNode.value = null
    notify(`Добавлен блок: ${prepared.label}`)
  }

  function deleteSelectedNode(): void {
    if (!selectedNode.value) return

    const id = selectedNode.value.id
    nodes.value = (toPlainNodes(nodes.value) as FlowNode[]).filter((node) => node.id !== id)
    edges.value = edges.value.filter((edge) => edge.source !== id && edge.target !== id)
    selectedNode.value = null
  }

  function duplicateSelectedNode(): void {
    if (reviewMode.value || !selectedNode.value) return

    const source = selectedNode.value
    const clone = {
      ...(toPlainNode(source) as FlowNode),
      id: `dup_${Date.now()}`,
      position: { x: source.position.x + 40, y: source.position.y + 40 },
    }
    nodes.value = [...(toPlainNodes(nodes.value) as FlowNode[]), clone]
  }

  function isEditableTarget(target: EventTarget | null): boolean {
    if (!(target instanceof HTMLElement)) return false
    const tag = target.tagName
    return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable
  }

  function onEditorKeydown(event: KeyboardEvent): void {
    if (reviewMode.value || isEditableTarget(event.target)) return

    const meta = event.ctrlKey || event.metaKey
    const key = event.key.toLowerCase()

    if (meta && key === 'z') {
      event.preventDefault()
      if (event.shiftKey) store.redo()
      else store.undo()
      return
    }
    if (meta && key === 'y') {
      event.preventDefault()
      store.redo()
      return
    }
    if (meta && key === 'd') {
      event.preventDefault()
      duplicateSelectedNode()
    }
  }

  // Deleting a node (Delete key handled by Vue Flow, undo/redo, or button) can
  // leave selectedNode pointing at a removed node — clear it so the inspector
  // panel doesn't show a ghost.
  watch(nodes, (list) => {
    if (selectedNode.value && !list.some((node) => node.id === selectedNode.value!.id)) {
      selectedNode.value = null
    }
  })

  function updateSelectedNodeData(field: keyof NodeDataDto, value: string): void {
    if (!selectedNode.value) return

    const updatedNode: FlowNode = {
      ...selectedNode.value,
      data: {
        ...selectedNode.value.data,
        [field]: value,
      },
    }

    selectedNode.value = updatedNode
    nodes.value = nodes.value.map((node) => (node.id === updatedNode.id ? updatedNode : node))
  }

  function closeDrawersOnClickOutside(event: MouseEvent): void {
    if (!leftDrawer.value && !rightDrawer.value) return

    const target = event.target
    if (!(target instanceof HTMLElement)) return

    if (!target.closest('.side-panel') && !target.closest('.canvas-header-actions')) {
      leftDrawer.value = false
      rightDrawer.value = false
    }
  }

  function clearPaletteSearchTimer(): void {
    if (paletteSearchTimer) {
      clearTimeout(paletteSearchTimer)
      paletteSearchTimer = null
    }
  }

  onActivated(() => {
    if (!dbPalette.value.length || !assignmentSelector.assignments.value.length) {
      void loadConstructorData()
    }
  })

  async function startCurrentAssignment(): Promise<void> {
    await assignmentSelector.startCurrentAssignment()
    store.resetHistory()
  }

  onMounted(() => {
    void loadConstructorData()
    document.addEventListener('mousedown', closeDrawersOnClickOutside)
    window.addEventListener('keydown', onEditorKeydown)
  })

  onUnmounted(() => {
    clearPaletteSearchTimer()
    document.removeEventListener('mousedown', closeDrawersOnClickOutside)
    window.removeEventListener('keydown', onEditorKeydown)
  })

  return {
    auth,
    store,
    nodes,
    edges,
    reviewMode,
    evalResult,
    selectedNode,
    snackbar,
    snackText,
    evalError: evaluation.evalError,
    loading,
    leftDrawer,
    rightDrawer,
    dbPalette,
    paletteLoading,
    paletteSearchLoading,
    paletteSearch,
    paletteSearchActive,
    paletteScope,
    activePaletteCategory,
    assignmentsLoading: assignmentSelector.assignmentsLoading,
    showAssignmentDialog: assignmentSelector.showAssignmentDialog,
    PALETTE_FRAME_ITEM,
    metricValue: evaluation.metricValue,
    metricPercent: evaluation.metricPercent,
    paletteGroups,
    hasPaletteItems,
    paletteHint,
    selectedAssignment: assignmentSelector.selectedAssignment,
    assignmentDescription: assignmentSelector.assignmentDescription,
    assignmentTimer: assignmentSelector.assignmentTimer,
    paletteFilterCategories,
    categoryTitle,
    CATEGORIES_OPTIONS,
    assignmentId: assignmentSelector.assignmentId,
    assignments: assignmentSelector.assignments,
    selectedRefId: assignmentSelector.selectedRefId,
    hintsResult: evaluation.hintsResult,
    hintsLoading: evaluation.hintsLoading,
    hintError: evaluation.hintError,
    feedbackResult: evaluation.feedbackResult,
    feedbackLoading: evaluation.feedbackLoading,
    showFeedbackDialog: evaluation.showFeedbackDialog,
    formattedFeedback: evaluation.formattedFeedback,
    refreshPalette,
    loadConstructorData,
    fetchAssignments: assignmentSelector.fetchAssignments,
    startCurrentAssignment,
    fetchInitialNodes: assignmentSelector.fetchInitialNodes,
    onDragStart,
    addPaletteItemToCanvas,
    setPaletteAddHandler,
    fetchHints: evaluation.fetchHints,
    fetchFeedback: evaluation.fetchFeedback,
    submitGraph: evaluation.submitGraph,
    showReferenceGraph: evaluation.showReferenceGraph,
    onValidationError: evaluation.onValidationError,
    backToEditing: evaluation.backToEditing,
    resetCanvas: evaluation.resetCanvas,
    deleteSelectedNode,
    duplicateSelectedNode,
    updateSelectedNodeData,
    canUndo,
    canRedo,
    undo: store.undo,
    redo: store.redo,
    showReferenceDialog: evaluation.showReferenceDialog,
    referenceNodes: evaluation.referenceNodes,
    referenceEdges: evaluation.referenceEdges,
    highlightNodeByLabel: store.setHighlightNodeByLabel,
    clearHighlight: store.clearHighlight,
    closeDrawersOnClickOutside,
  }
}
