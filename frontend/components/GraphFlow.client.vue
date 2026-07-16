<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import GraphCanvas from '~/components/features/graph-constructor/GraphCanvas.client.vue'
import GraphToolbar from '~/components/features/graph-constructor/GraphToolbar.vue'
import { applyAutoLayout, applyBlockLayout, getNodeDimensions } from '~/composables/useGraphLayout'
import { toPlainEdges, toPlainNodes } from '~/composables/useGraphPayload'
import { RELATION_OPTIONS } from '~/constants/clinicalOntology'
import { useClinicalCaseStore } from '~/stores/clinicalCase'
import type {
  FlowEdge,
  FlowNode,
  GraphCanvasActions,
  GraphEdgeRelation,
  PaletteItem,
} from '~/types/graph'

const props = defineProps<{
  palette: PaletteItem[]
  readOnly?: boolean
  previewMode?: boolean
}>()

const emit = defineEmits<{
  'validation-error': [message: string]
}>()

const nodes = defineModel<FlowNode[]>('nodes', { default: () => [] })
const edges = defineModel<FlowEdge[]>('edges', { default: () => [] })

const store = useClinicalCaseStore()
const canvasActions = ref<GraphCanvasActions | null>(null)
const defaultRelation = ref<GraphEdgeRelation>('DETERMINES')
const initialLayoutNodeSet = ref<string | null>(null)
const readOnlyState = computed(() => Boolean(props.readOnly))
const clinicalNodeSetSignature = computed(() =>
  nodes.value
    .filter((node) => node.type !== 'frame' && node.type !== 'group')
    .map((node) => node.id)
    .sort()
    .join('|'),
)

const {
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
} = useGraphInteractions({
  defaultRelation,
  edges,
  nodes,
  onValidationError: (message) => emit('validation-error', message),
  readOnly: readOnlyState,
})

const {
  addCustomNode,
  addPaletteItem: addPaletteItemAt,
  onCanvasDragOver,
  onCanvasDrop,
} = useGraphDragDrop({
  getCanvasActions: () => canvasActions.value,
  nodes,
  readOnly: readOnlyState,
})

function runAutoLayout(): void {
  const plainNodes = toPlainNodes(nodes.value) as FlowNode[]
  const plainEdges = toPlainEdges(edges.value) as FlowEdge[]
  nodes.value = applyAutoLayout(plainNodes, plainEdges, { spacious: true })
  void nextTick(() => {
    window.setTimeout(() => canvasActions.value?.fitView({ padding: 0.28, duration: 200 }), 60)
  })
}

function runBlockLayout(): void {
  const plainNodes = toPlainNodes(nodes.value) as FlowNode[]
  const plainEdges = toPlainEdges(edges.value) as FlowEdge[]
  nodes.value = applyBlockLayout(plainNodes, plainEdges)
  void nextTick(() => {
    window.setTimeout(() => canvasActions.value?.fitView({ padding: 0.2, duration: 200 }), 60)
  })
}

function runFitView(): void {
  canvasActions.value?.fitView({ padding: 0.28, duration: 200 })
}

function nodesOverlap(first: FlowNode, second: FlowNode): boolean {
  const firstSize = getNodeDimensions(first)
  const secondSize = getNodeDimensions(second)
  const padding = 24

  return !(
    first.position.x + firstSize.width + padding <= second.position.x ||
    second.position.x + secondSize.width + padding <= first.position.x ||
    first.position.y + firstSize.height + padding <= second.position.y ||
    second.position.y + secondSize.height + padding <= first.position.y
  )
}

function hasStackedClinicalNodes(): boolean {
  const clinicalNodes = nodes.value.filter((node) => node.type !== 'frame' && node.type !== 'group')
  if (clinicalNodes.length < 2) return false

  const coarsePositions = new Set(
    clinicalNodes.map((node) => `${Math.round(node.position.x / 24)}:${Math.round(node.position.y / 24)}`),
  )
  if (coarsePositions.size < clinicalNodes.length) return true

  for (let i = 0; i < clinicalNodes.length; i += 1) {
    for (let j = i + 1; j < clinicalNodes.length; j += 1) {
      if (nodesOverlap(clinicalNodes[i], clinicalNodes[j])) {
        return true
      }
    }
  }

  return false
}

function runInitialAutoLayoutIfNeeded(): void {
  const nodeSet = clinicalNodeSetSignature.value
  if (!nodeSet) {
    initialLayoutNodeSet.value = null
    return
  }

  if (props.previewMode || props.readOnly || !canvasActions.value || initialLayoutNodeSet.value === nodeSet) {
    return
  }

  if (!hasStackedClinicalNodes()) {
    return
  }

  initialLayoutNodeSet.value = nodeSet
  runAutoLayout()
}

/** Add a palette block at a sensible free spot and bring it into view. */
function addPaletteItem(item: PaletteItem): void {
  if (!item?.label || !item?.category) {
    return
  }

  addPaletteItemAt(item)
  void nextTick(() => canvasActions.value?.fitView({ padding: 0.25, duration: 180 }))
}

function refreshPreviewLayout(): void {
  if (!nodes.value.length) {
    return
  }

  nodes.value = applyAutoLayout(toPlainNodes(nodes.value) as FlowNode[], toPlainEdges(edges.value) as FlowEdge[], { spacious: true })
  void nextTick(() => {
    window.setTimeout(() => canvasActions.value?.fitView({ padding: 0.28, duration: 200 }), 80)
  })
}

function handleCanvasReady(actions: GraphCanvasActions): void {
  canvasActions.value = actions
  window.setTimeout(() => {
    if (props.previewMode || props.readOnly) {
      refreshPreviewLayout()
      return
    }

    runInitialAutoLayoutIfNeeded()
    actions.fitView({ padding: 0.2 })
  }, 80)
}

watch(clinicalNodeSetSignature, () => {
  window.setTimeout(runInitialAutoLayoutIfNeeded, 80)
})

defineExpose({
  addPaletteItem,
  runAutoLayout,
  runFitView,
})
</script>

<template>
  <div class="flow-wrap">
    <GraphToolbar
      v-if="!previewMode"
      v-model:default-relation="defaultRelation"
      v-model:selected-edge-label="selectedEdgeLabel"
      :nodes-count="nodes.length"
      :read-only="readOnly"
      :relations="RELATION_OPTIONS"
      :selected-edge-id="selectedEdgeId"
      @add-custom-node="addCustomNode"
      @auto-layout="runAutoLayout"
      @block-layout="runBlockLayout"
      @delete-selected-edge="deleteSelectedEdge"
      @fit-view="runFitView"
    />

    <GraphCanvas
      v-model:nodes="nodes"
      v-model:edges="edges"
      :active-highlight-node-id="store.activeHighlightNodeId"
      :is-valid-connection="isValidConnection"
      :preview-mode="previewMode"
      :read-only="readOnly"
      @canvas-drag-over="onCanvasDragOver"
      @canvas-drop="onCanvasDrop"
      @connect="handleConnect"
      @edge-click="handleEdgeClick"
      @edge-delete="deleteEdgeById"
      @edge-relation="setEdgeRelation"
      @node-click="handleNodeClick"
      @node-delete="deleteNodeById"
      @node-duplicate="duplicateNodeById"
      @pane-click="handlePaneClick"
      @ready="handleCanvasReady"
    />
  </div>
</template>

<style scoped>
.flow-wrap {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.flow-wrap :deep(.graph-canvas) {
  flex: 1 1 auto;
  min-height: 0;
}
</style>
