import type { ComputedRef, Ref } from 'vue'
import type { FlowNode, GraphCanvasActions, GraphPosition, NodeDataDto, PaletteItem } from '~/types/graph'
import { toPlainNodes } from '~/composables/useGraphPayload'

interface UseGraphDragDropOptions {
  nodes: Ref<FlowNode[]>
  readOnly: ComputedRef<boolean>
  getCanvasActions: () => GraphCanvasActions | null
}

function parsePaletteItem(raw: string): PaletteItem | null {
  try {
    const parsed = JSON.parse(raw) as Partial<PaletteItem>
    if (typeof parsed.label !== 'string' || typeof parsed.category !== 'string') {
      return null
    }
    return {
      category: parsed.category,
      dosage: typeof parsed.dosage === 'string' ? parsed.dosage : undefined,
      expected_value: typeof parsed.expected_value === 'string' ? parsed.expected_value : undefined,
      label: parsed.label,
      route: typeof parsed.route === 'string' ? parsed.route : undefined,
      stage: typeof parsed.stage === 'string' ? parsed.stage : undefined,
    }
  } catch {
    return null
  }
}

function getDropPayload(event: DragEvent): PaletteItem | null {
  const raw =
    event.dataTransfer?.getData('application/vueflow') ||
    event.dataTransfer?.getData('application/json') ||
    event.dataTransfer?.getData('text/plain')

  return raw ? parsePaletteItem(raw) : null
}

function makeNodeData(item: PaletteItem): NodeDataDto {
  return {
    category: item.category,
    dosage: item.dosage || '',
    expected_value: item.expected_value || '',
    label: item.label,
    route: item.route || '',
    stage: item.stage || '',
  }
}

export function useGraphDragDrop(options: UseGraphDragDropOptions) {
  function onCanvasDragOver(event: DragEvent): void {
    event.preventDefault()
    event.stopPropagation()

    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'move'
    }
  }

  function canvasCenterPosition(): GraphPosition {
    const actions = options.getCanvasActions()
    const rect = actions?.getCanvasRect()

    if (!actions || !rect) {
      return {
        x: 160 + (options.nodes.value.length % 4) * 36,
        y: 140 + (options.nodes.value.length % 4) * 28,
      }
    }

    const safeX = rect.left + Math.min(Math.max(rect.width * 0.55, 260), rect.width - 160)
    const safeY = rect.top + Math.min(Math.max(rect.height * 0.4, 180), rect.height - 120)
    const position = actions.screenToFlowCoordinate({ x: safeX, y: safeY })

    return {
      x: position.x + (options.nodes.value.length % 4) * 36,
      y: position.y + (options.nodes.value.length % 4) * 28,
    }
  }

  function addPaletteItem(item: PaletteItem, position = canvasCenterPosition()): void {
    if (options.readOnly.value) {
      return
    }

    if (item.category === '__frame__') {
      options.nodes.value = [
        ...(toPlainNodes(options.nodes.value) as FlowNode[]),
        {
          data: { category: 'layout', label: item.label },
          id: `frame_${Date.now()}_${options.nodes.value.length}`,
          position,
          style: { height: '220px', width: '320px' },
          type: 'frame',
        },
      ]
      return
    }

    options.nodes.value = [
      ...(toPlainNodes(options.nodes.value) as FlowNode[]),
      {
        data: makeNodeData(item),
        id: `n_${Date.now()}_${options.nodes.value.length}`,
        position,
        type: 'med',
      },
    ]
  }

  function onCanvasDrop(event: DragEvent): void {
    if (options.readOnly.value) {
      return
    }

    event.preventDefault()
    event.stopPropagation()

    const item = getDropPayload(event)
    const actions = options.getCanvasActions()

    if (!item || !actions) {
      return
    }

    addPaletteItem(item, actions.screenToFlowCoordinate({ x: event.clientX, y: event.clientY }))
  }

  function addCustomNode(item: PaletteItem): void {
    if (!item.label.trim() || options.readOnly.value) {
      return
    }

    const maxX = options.nodes.value.reduce((value, node) => Math.max(value, node.position.x), 0)

    options.nodes.value = [
      ...(toPlainNodes(options.nodes.value) as FlowNode[]),
      {
        data: makeNodeData(item),
        id: `custom_${Date.now()}`,
        position: { x: maxX + 120, y: 100 },
        type: 'med',
      },
    ]
  }

  return {
    addCustomNode,
    addPaletteItem,
    onCanvasDragOver,
    onCanvasDrop,
  }
}
