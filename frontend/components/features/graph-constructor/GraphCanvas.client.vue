<script setup lang="ts">
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import {
  MarkerType,
  VueFlow,
  useVueFlow,
  type Connection,
  type EdgeMouseEvent,
  type NodeMouseEvent,
} from '@vue-flow/core'
import { getCurrentInstance, markRaw, onBeforeUnmount, onMounted, type Component } from 'vue'
import CustomEdge from '~/components/CustomEdge.vue'
import FlowGroupNode from '~/components/FlowGroupNode.vue'
import GraphLegend from '~/components/features/graph-constructor/GraphLegend.vue'
import MedFlowNode from '~/components/MedFlowNode.vue'
import { toPlainEdges, toPlainNodes } from '~/composables/useGraphPayload'
import { toPng } from 'html-to-image'
import { categoryMeta, RELATIONS } from '~/constants/clinicalOntology'
import type { FlowEdge, FlowEdgeData, FlowNode, GraphCanvasActions, GraphEdgeRelation, NodeDataDto } from '~/types/graph'

const props = defineProps<{
  activeHighlightNodeId?: string | null
  isValidConnection: (connection: Connection) => boolean
  previewMode?: boolean
  readOnly?: boolean
}>()

const nodes = defineModel<FlowNode[]>('nodes', { required: true })
const edges = defineModel<FlowEdge[]>('edges', { required: true })

const emit = defineEmits<{
  'canvas-drag-over': [event: DragEvent]
  'canvas-drop': [event: DragEvent]
  'connect': [connection: Connection]
  'edge-click': [edge: FlowEdge]
  'edge-delete': [edgeId: string]
  'edge-relation': [edgeId: string, relation: GraphEdgeRelation]
  'node-click': [node: FlowNode]
  'node-delete': [nodeId: string]
  'node-duplicate': [nodeId: string]
  'pane-click': []
  'ready': [actions: GraphCanvasActions]
}>()

const canvasRef = ref<HTMLElement | null>(null)
const editable = computed(() => !props.readOnly && !props.previewMode)
const instance = getCurrentInstance()
const flowId = `clinical-flow-${instance?.uid ?? Math.random().toString(36).slice(2)}`

const {
  fitView,
  getNodes,
  getSelectedEdges,
  getSelectedNodes,
  onConnect,
  onEdgeClick,
  onEdgeContextMenu,
  onNodeClick,
  onNodeContextMenu,
  onPaneClick,
  onPaneReady,
  removeSelectedElements,
  screenToFlowCoordinate,
} = useVueFlow({ id: flowId })

// --- Fullscreen + PNG export (useful for large read-only reference graphs) ---
const isFullscreen = ref(false)
const isExporting = ref(false)

async function toggleFullscreen(): Promise<void> {
  const el = canvasRef.value
  if (!el) return
  if (document.fullscreenElement) {
    await document.exitFullscreen().catch(() => {})
  } else {
    await el.requestFullscreen().catch(() => {})
  }
}

function syncFullscreen(): void {
  isFullscreen.value = document.fullscreenElement === canvasRef.value
  // Refit after the canvas resizes into / out of fullscreen.
  setTimeout(() => fitView({ padding: 0.18 }), 120)
}

async function downloadPng(): Promise<void> {
  // Vue Flow's DOM nests `.vue-flow__transformationpane` *inside*
  // `.vue-flow__viewport`: the outer viewport is a plain, untransformed
  // container (`overflow: clip`), while the pan/zoom `transform:
  // translate(...) scale(zoom)` actually lives on the inner transformation
  // pane. Exporting the outer viewport (as before) left that inner transform
  // untouched, so the snapshot was rendered at whatever tiny zoom level was
  // on screen — small and soft. Export the transformation pane directly so
  // overriding its transform actually resets the content to scale 1.
  const transformPane = canvasRef.value?.querySelector('.vue-flow__transformationpane') as HTMLElement | null
  const flowNodes = getNodes.value
  if (!transformPane || isExporting.value || !flowNodes.length) return
  isExporting.value = true
  try {
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    for (const node of flowNodes) {
      const x = node.computedPosition?.x ?? node.position.x
      const y = node.computedPosition?.y ?? node.position.y
      const width = node.dimensions?.width || 220
      const height = node.dimensions?.height || 110
      minX = Math.min(minX, x)
      minY = Math.min(minY, y)
      maxX = Math.max(maxX, x + width)
      maxY = Math.max(maxY, y + height)
    }
    if (!Number.isFinite(minX)) return

    const pad = 56
    const imageWidth = Math.ceil(maxX - minX + pad * 2)
    const imageHeight = Math.ceil(maxY - minY + pad * 2)

    await nextTick()
    const skip = [
      'vue-flow__minimap', 'vue-flow__controls', 'vue-flow__background',
      'vue-flow__handle', 'graph-legend', 'graph-toolbar', 'graph-canvas__tools',
    ]
    const dataUrl = await toPng(transformPane, {
      backgroundColor: '#ffffff',
      width: imageWidth,
      height: imageHeight,
      pixelRatio: 3,
      cacheBust: true,
      style: {
        transform: `translate(${pad - minX}px, ${pad - minY}px) scale(1)`,
        transformOrigin: 'top left',
        opacity: '1',
      },
      filter: (node) =>
        !(node instanceof HTMLElement && skip.some((c) => node.classList?.contains(c))),
    })
    const link = document.createElement('a')
    link.download = 'эталонный-граф.png'
    link.href = dataUrl
    link.click()
  } finally {
    isExporting.value = false
  }
}

onMounted(() => document.addEventListener('fullscreenchange', syncFullscreen))
onUnmounted(() => document.removeEventListener('fullscreenchange', syncFullscreen))

// --- Context menu (right click on node / edge) ------------------------------
interface ContextMenuState {
  kind: 'node' | 'edge'
  id: string
  isFrame: boolean
  x: number
  y: number
}

const contextMenu = ref<ContextMenuState | null>(null)
const contextMenuOpen = computed({
  get: () => contextMenu.value !== null,
  set: (open: boolean) => {
    if (!open) contextMenu.value = null
  },
})

function openContextMenu(event: MouseEvent, kind: 'node' | 'edge', id: string, isFrame = false): void {
  if (!editable.value) return
  event.preventDefault()
  contextMenu.value = { kind, id, isFrame, x: event.clientX, y: event.clientY }
}

onNodeContextMenu((event: NodeMouseEvent) => {
  const mouse = event.event
  if (mouse instanceof MouseEvent) {
    openContextMenu(mouse, 'node', event.node.id, event.node.type === 'frame')
  }
})

onEdgeContextMenu((event: EdgeMouseEvent) => {
  const mouse = event.event
  if (mouse instanceof MouseEvent) {
    openContextMenu(mouse, 'edge', event.edge.id)
  }
})

function contextDuplicateNode(): void {
  if (contextMenu.value?.kind === 'node') emit('node-duplicate', contextMenu.value.id)
  contextMenu.value = null
}

function contextDeleteNode(): void {
  if (contextMenu.value?.kind === 'node') emit('node-delete', contextMenu.value.id)
  contextMenu.value = null
}

function contextDeleteEdge(): void {
  if (contextMenu.value?.kind === 'edge') emit('edge-delete', contextMenu.value.id)
  contextMenu.value = null
}

function contextSetRelation(relation: GraphEdgeRelation): void {
  if (contextMenu.value?.kind === 'edge') emit('edge-relation', contextMenu.value.id, relation)
  contextMenu.value = null
}

// --- Keyboard: Delete/Backspace removes selection, Escape clears it ---------
// Deterministic handling that works for multi-selection and does not depend on
// the pane holding focus, unlike Vue Flow's built-in deleteKeyCode which we
// disable. Removes the selected nodes/edges + any edges orphaned by a removed
// node, writing clean clones back to the model.
function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable
}

function onCanvasKeydown(event: KeyboardEvent): void {
  if (!editable.value || isEditableTarget(event.target)) return

  if (event.key === 'Escape') {
    contextMenu.value = null
    removeSelectedElements()
    emit('pane-click')
    return
  }

  if (event.key !== 'Delete' && event.key !== 'Backspace') return

  const nodeIds = new Set(getSelectedNodes.value.map((node) => node.id))
  const edgeIds = new Set(getSelectedEdges.value.map((edge) => edge.id))
  if (!nodeIds.size && !edgeIds.size) return

  event.preventDefault()

  if (nodeIds.size) {
    nodes.value = (toPlainNodes(nodes.value) as FlowNode[]).filter((node) => !nodeIds.has(node.id))
  }
  edges.value = (toPlainEdges(edges.value) as FlowEdge[]).filter(
    (edge) => !edgeIds.has(edge.id) && !nodeIds.has(edge.source) && !nodeIds.has(edge.target),
  )
}

onMounted(() => window.addEventListener('keydown', onCanvasKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onCanvasKeydown))

const nodeTypes: Record<string, Component> = {
  frame: markRaw(FlowGroupNode),
  med: markRaw(MedFlowNode),
}

const edgeTypes: Record<string, Component> = {
  custom: markRaw(CustomEdge),
}

const defaultEdgeOptions = {
  markerEnd: MarkerType.ArrowClosed,
  type: 'custom',
}

const connectionLineStyle = {
  stroke: '#2563eb',
  strokeWidth: 2.5,
  strokeDasharray: '6,4',
}

function minimapNodeColor(node: { type?: string; data?: NodeDataDto }): string {
  if (node.type === 'frame' || node.type === 'group') return 'rgba(100, 116, 139, 0.12)'
  return categoryMeta(node.data?.category).color
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function toNodeData(value: unknown): NodeDataDto {
  if (!isRecord(value)) {
    return { category: '', label: '' }
  }

  return {
    ...value,
    category: typeof value.category === 'string' ? value.category : '',
    label: typeof value.label === 'string' ? value.label : '',
  }
}

function toEdgeData(value: unknown): FlowEdgeData | undefined {
  return isRecord(value) ? { ...value } : undefined
}

function toFlowEdge(event: EdgeMouseEvent): FlowEdge {
  const edge = event.edge

  return {
    data: toEdgeData(edge.data),
    id: edge.id,
    label: typeof edge.label === 'string' ? edge.label : undefined,
    source: edge.source,
    sourceHandle: edge.sourceHandle,
    target: edge.target,
    targetHandle: edge.targetHandle,
    type: edge.type,
  }
}

function toFlowNode(event: NodeMouseEvent): FlowNode {
  const node = event.node

  return {
    data: toNodeData(node.data),
    id: node.id,
    position: { x: node.position.x, y: node.position.y },
    type: node.type || 'med',
  }
}

onConnect((connection: Connection) => {
  emit('connect', connection)
})

onEdgeClick((event: EdgeMouseEvent) => {
  emit('edge-click', toFlowEdge(event))
})

onNodeClick((event: NodeMouseEvent) => {
  emit('node-click', toFlowNode(event))
})

onPaneClick(() => {
  contextMenu.value = null
  emit('pane-click')
})

onPaneReady(() => {
  emit('ready', {
    fitView: (options) => {
      void fitView(options)
    },
    getCanvasRect: () => canvasRef.value?.getBoundingClientRect() ?? null,
    screenToFlowCoordinate: (position) => {
      const flowPosition = screenToFlowCoordinate(position)
      return { x: flowPosition.x, y: flowPosition.y }
    },
  })
})
</script>

<template>
  <div ref="canvasRef" class="graph-canvas">
    <slot name="toolbar" />

    <div class="graph-canvas__tools">
      <v-btn
        icon
        size="small"
        variant="flat"
        color="white"
        class="graph-canvas__tool-btn"
        :title="isFullscreen ? 'Выйти из полноэкранного режима' : 'Во весь экран'"
        aria-label="Во весь экран"
        @click="toggleFullscreen"
      >
        <v-icon :icon="isFullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'" />
      </v-btn>
      <v-btn
        icon
        size="small"
        variant="flat"
        color="white"
        class="graph-canvas__tool-btn"
        :loading="isExporting"
        title="Скачать граф (PNG)"
        aria-label="Скачать граф"
        @click="downloadPng"
      >
        <v-icon icon="mdi-download" />
      </v-btn>
    </div>

    <VueFlow
      :id="flowId"
      v-model:nodes="nodes"
      v-model:edges="edges"
      class="vue-flow"
      :class="{ 'vue-flow--preview': previewMode || readOnly }"
      :default-edge-options="defaultEdgeOptions"
      :edge-types="edgeTypes"
      :edges-updatable="!readOnly"
      :elevate-edges-on-select="true"
      :elements-selectable="true"
      :is-valid-connection="isValidConnection"
      :max-zoom="2"
      :min-zoom="0.08"
      :node-types="nodeTypes"
      :nodes-connectable="!readOnly"
      :nodes-draggable="!previewMode"
      :snap-grid="[16, 16]"
      :snap-to-grid="!previewMode"
      :connection-radius="32"
      :connection-line-style="connectionLineStyle"
      :pan-on-drag="true"
      :selection-on-drag="false"
      :delete-key-code="null"
      :selection-key-code="editable ? 'Shift' : null"
      :multi-selection-key-code="editable ? 'Shift' : null"
      @dragenter="emit('canvas-drag-over', $event)"
      @dragover="emit('canvas-drag-over', $event)"
      @drop="emit('canvas-drop', $event)"
    >
      <template #node-med="nodeProps">
        <MedFlowNode
          v-bind="nodeProps"
          :is-highlighted="activeHighlightNodeId === nodeProps.id"
        />
      </template>

      <Background :gap="20" pattern-color="rgba(100, 116, 139, 0.12)" />
      <MiniMap
        v-if="!readOnly && !previewMode"
        pannable
        zoomable
        class="minimap-light"
        :mask-color="'rgba(241, 245, 249, 0.6)'"
        :node-color="minimapNodeColor"
        :node-stroke-color="minimapNodeColor"
      />
      <Controls position="bottom-right" />
    </VueFlow>

    <v-menu
      v-model="contextMenuOpen"
      :target="contextMenu ? [contextMenu.x, contextMenu.y] : undefined"
      location-strategy="connected"
      :close-on-content-click="true"
    >
      <v-list density="compact" min-width="300" class="context-menu-list pa-1">
        <template v-if="contextMenu?.kind === 'node'">
          <v-list-item
            v-if="!contextMenu.isFrame"
            prepend-icon="mdi-content-copy"
            title="Дублировать блок"
            @click="contextDuplicateNode"
          />
          <v-list-item
            base-color="error"
            prepend-icon="mdi-delete-outline"
            :title="contextMenu.isFrame ? 'Удалить рамку' : 'Удалить блок и его связи'"
            @click="contextDeleteNode"
          />
        </template>

        <template v-else-if="contextMenu?.kind === 'edge'">
          <v-list-subheader class="text-caption font-weight-bold">Тип связи</v-list-subheader>
          <v-list-item
            v-for="rel in RELATIONS"
            :key="rel.value"
            class="relation-context-item rounded"
            @click="contextSetRelation(rel.value)"
          >
            <template #prepend>
              <span class="relation-swatch mr-2" :style="{ background: rel.color }" />
            </template>
            <v-list-item-title class="relation-context-title">
              {{ rel.title }}
            </v-list-item-title>
            <v-list-item-subtitle class="relation-context-subtitle">
              {{ rel.description }}
            </v-list-item-subtitle>
          </v-list-item>
          <v-divider class="my-1" />
          <v-list-item
            base-color="error"
            prepend-icon="mdi-delete-outline"
            title="Удалить связь"
            @click="contextDeleteEdge"
          />
        </template>
      </v-list>
    </v-menu>

    <GraphLegend v-if="readOnly || previewMode" />
  </div>
</template>

<style scoped>
.graph-canvas {
  position: relative;
  min-width: 0;
  height: 100%;
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 12px;
  background: #ffffff;
}

.graph-canvas:fullscreen {
  border-radius: 0;
  border: none;
}

.graph-canvas__tools {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 6;
  display: flex;
  gap: 6px;
}

.graph-canvas__tool-btn {
  border: 1px solid rgba(100, 116, 139, 0.22);
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.08);
  color: rgb(var(--v-theme-primary)) !important;
}

.vue-flow {
  width: 100%;
  height: 100%;
}

.vue-flow--preview :deep(.vue-flow__edges) {
  z-index: 2;
}

.vue-flow--preview :deep(.vue-flow__nodes) {
  z-index: 3;
}

.vue-flow--preview :deep(.vue-flow__edge-path) {
  stroke-linecap: round;
}

.minimap-light :deep(.vue-flow__minimap) {
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.08);
}

.relation-swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex: 0 0 auto;
}

.context-menu-list {
  max-width: min(440px, calc(100vw - 24px));
}

.relation-context-item {
  align-items: flex-start;
  min-height: 54px;
}

.relation-context-title {
  white-space: normal;
  overflow-wrap: anywhere;
  line-height: 1.25;
  font-size: 0.86rem;
  font-weight: 700;
}

.relation-context-subtitle {
  white-space: normal;
  overflow-wrap: anywhere;
  line-height: 1.25;
  font-size: 0.76rem;
}
</style>
