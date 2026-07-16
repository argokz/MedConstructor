import type { Connection } from '@vue-flow/core'
import type { ComputedRef, Ref } from 'vue'
import type { FlowEdge, FlowNode, GraphEdgeRelation } from '~/types/graph'
import { toPlainEdges, toPlainNode, toPlainNodes } from '~/composables/useGraphPayload'
import { normalizeCategory, normalizeRelation } from '~/constants/clinicalOntology'

interface UseGraphInteractionsOptions {
  nodes: Ref<FlowNode[]>
  edges: Ref<FlowEdge[]>
  readOnly: ComputedRef<boolean>
  defaultRelation: Ref<GraphEdgeRelation>
  onValidationError: (message: string) => void
}

export function useGraphInteractions(options: UseGraphInteractionsOptions) {
  const store = useClinicalCaseStore()
  const selectedEdgeId = ref<string | null>(null)

  const selectedEdgeLabel = computed<GraphEdgeRelation>({
    get() {
      const edge = options.edges.value.find((item) => item.id === selectedEdgeId.value)
      return normalizeRelation(edge?.label, options.defaultRelation.value)
    },
    set(value) {
      if (!selectedEdgeId.value || options.readOnly.value) {
        return
      }

      setEdgeRelation(selectedEdgeId.value, value)
    },
  })

  function isValidConnection(connection: Connection): boolean {
    const sourceNode = options.nodes.value.find((node) => node.id === connection.source)
    const targetNode = options.nodes.value.find((node) => node.id === connection.target)

    if (!sourceNode || !targetNode) {
      return false
    }

    const sourceCategory = normalizeCategory(sourceNode.data.category)
    const targetCategory = normalizeCategory(targetNode.data.category)
    const sourceIsClinicalInput = sourceCategory === 'SYMPTOM' || sourceCategory === 'PATIENT_PROFILE'
    const targetIsAction = targetCategory === 'MEDICATION' || targetCategory === 'SURGERY'

    if (sourceIsClinicalInput && targetIsAction) {
      options.onValidationError('Клиническая валидация: нельзя связывать симптомы или профиль пациента напрямую с терапией/операцией, минуя диагноз!')
      return false
    }

    return true
  }

  function handleConnect(connection: Connection): void {
    if (options.readOnly.value || !isValidConnection(connection)) {
      return
    }

    options.edges.value = [
      ...(toPlainEdges(options.edges.value) as FlowEdge[]),
      {
        id: `e_${connection.source}_${connection.target}_${Date.now()}`,
        source: connection.source,
        target: connection.target,
        sourceHandle: connection.sourceHandle || 's',
        targetHandle: connection.targetHandle || 't',
        label: options.defaultRelation.value,
        type: 'custom',
      },
    ]
  }

  function handleEdgeClick(edge: FlowEdge): void {
    selectedEdgeId.value = edge.id
  }

  function handleNodeClick(node: FlowNode): void {
    store.selectedNode = node
  }

  function handlePaneClick(): void {
    selectedEdgeId.value = null
    store.selectedNode = null
  }

  function setEdgeRelation(edgeId: string, relation: GraphEdgeRelation): void {
    if (options.readOnly.value) {
      return
    }

    options.edges.value = (toPlainEdges(options.edges.value) as FlowEdge[]).map((edge) =>
      edge.id === edgeId ? { ...edge, label: relation } : edge,
    )
  }

  function deleteEdgeById(edgeId: string): void {
    if (options.readOnly.value) {
      return
    }

    options.edges.value = options.edges.value.filter((edge) => edge.id !== edgeId)
    if (selectedEdgeId.value === edgeId) {
      selectedEdgeId.value = null
    }
  }

  function deleteSelectedEdge(): void {
    if (!selectedEdgeId.value) {
      return
    }

    deleteEdgeById(selectedEdgeId.value)
  }

  /** Remove a node together with the edges it participates in. */
  function deleteNodeById(nodeId: string): void {
    if (options.readOnly.value) {
      return
    }

    options.nodes.value = (toPlainNodes(options.nodes.value) as FlowNode[]).filter((node) => node.id !== nodeId)
    options.edges.value = (toPlainEdges(options.edges.value) as FlowEdge[]).filter(
      (edge) => edge.source !== nodeId && edge.target !== nodeId,
    )
    if (store.selectedNode?.id === nodeId) {
      store.selectedNode = null
    }
  }

  function duplicateNodeById(nodeId: string): void {
    if (options.readOnly.value) {
      return
    }

    const source = options.nodes.value.find((node) => node.id === nodeId)
    if (!source) {
      return
    }

    options.nodes.value = [
      ...(toPlainNodes(options.nodes.value) as FlowNode[]),
      {
        ...(toPlainNode(source) as FlowNode),
        id: `dup_${Date.now()}`,
        position: { x: source.position.x + 40, y: source.position.y + 40 },
      },
    ]
  }

  return {
    deleteEdgeById,
    deleteNodeById,
    deleteSelectedEdge,
    duplicateNodeById,
    handleConnect,
    handleEdgeClick,
    handleNodeClick,
    handlePaneClick,
    isValidConnection,
    selectedEdgeId,
    selectedEdgeLabel,
    setEdgeRelation,
  }
}
