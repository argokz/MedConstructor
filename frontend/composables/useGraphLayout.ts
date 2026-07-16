import dagre from 'dagre'
import type { FlowEdge, FlowNode } from '~/types/graph'

type NodeBBox = {
  id: string
  x: number
  y: number
  width: number
  height: number
}

type LayoutOptions = {
  spacious?: boolean
}

const DEFAULT_NODESEP = 80
const DEFAULT_RANKSEP = 120
const SPACIOUS_NODESEP = 120
const SPACIOUS_RANKSEP = 180

export function getNodeDimensions(node: FlowNode): { width: number; height: number } {
  if (node.type === 'frame' || node.type === 'group') {
    const w = Number.parseInt(String(node.style?.width ?? '280'), 10) || 280
    const h = Number.parseInt(String(node.style?.height ?? '220'), 10) || 220
    return { width: w, height: h }
  }

  const label = node.data?.label ?? ''
  const hasMeta = Boolean(
    node.data?.dosage || node.data?.route || node.data?.expected_value || node.data?.stage
  )
  const lineCount = Math.max(1, Math.ceil(label.length / 26))
  const width = Math.min(300, Math.max(200, label.length * 7))
  const height = 88 + lineCount * 18 + (hasMeta ? 20 : 0)
  return { width, height }
}

function boxesOverlap(a: NodeBBox, b: NodeBBox, padding = 16): boolean {
  return !(
    a.x + a.width + padding <= b.x ||
    b.x + b.width + padding <= a.x ||
    a.y + a.height + padding <= b.y ||
    b.y + b.height + padding <= a.y
  )
}

function resolveCollisions(bboxes: NodeBBox[], nodeSep: number): NodeBBox[] {
  const result = bboxes.map((b) => ({ ...b }))

  for (let pass = 0; pass < 12; pass++) {
    let moved = false
    for (let i = 0; i < result.length; i++) {
      for (let j = i + 1; j < result.length; j++) {
        if (!boxesOverlap(result[i], result[j], 24)) continue

        const dy = result[j].y - result[i].y
        if (Math.abs(dy) < result[i].height) {
          result[j].y = result[i].y + result[i].height + nodeSep
          moved = true
        }

        const dx = result[j].x - result[i].x
        if (boxesOverlap(result[i], result[j], 24) && Math.abs(dx) < result[i].width) {
          result[j].x = result[i].x + result[i].width + nodeSep
          moved = true
        }
      }
    }
    if (!moved) break
  }

  return result
}

export function applyAutoLayout(
  nodes: FlowNode[],
  edges: FlowEdge[],
  options: LayoutOptions = {},
): FlowNode[] {
  const spacious = options.spacious !== false
  const nodeSep = spacious ? SPACIOUS_NODESEP : DEFAULT_NODESEP
  const rankSep = spacious ? SPACIOUS_RANKSEP : DEFAULT_RANKSEP

  const layoutNodes = nodes.filter((n) => n.type !== 'frame' && n.type !== 'group')
  const frameNodes = nodes.filter((n) => n.type === 'frame' || n.type === 'group')

  if (layoutNodes.length === 0) return [...nodes]

  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'TB', nodesep: nodeSep, ranksep: rankSep, marginx: 40, marginy: 40 })
  g.setDefaultEdgeLabel(() => ({}))

  const dims = new Map<string, { width: number; height: number }>()
  for (const node of layoutNodes) {
    const { width, height } = getNodeDimensions(node)
    dims.set(node.id, { width, height })
    g.setNode(node.id, { width, height })
  }

  for (const edge of edges) {
    if (g.hasNode(edge.source) && g.hasNode(edge.target)) {
      g.setEdge(edge.source, edge.target)
    }
  }

  dagre.layout(g)

  let bboxes: NodeBBox[] = layoutNodes.map((node) => {
    const dNode = g.node(node.id)
    const { width, height } = dims.get(node.id)!
    return {
      id: node.id,
      x: dNode.x - width / 2,
      y: dNode.y - height / 2,
      width,
      height,
    }
  })

  bboxes = resolveCollisions(bboxes, nodeSep)

  const positioned = layoutNodes.map((node) => {
    const bbox = bboxes.find((b) => b.id === node.id)!
    return {
      ...node,
      position: { x: bbox.x, y: bbox.y },
    }
  })

  return [...positioned, ...frameNodes]
}

// --- Stage-block layout: groups clinical nodes into labelled blocks by clinical
// stage. Frames are derived from node positions, so they always wrap their nodes
// regardless of re-render. Use for read-only reference/solution graphs.

const STAGE_ORDER: { key: string; label: string; accent: string; categories: string[] }[] = [
  { key: 'patient', label: 'Данные пациента', accent: '#6366f1', categories: ['PATIENT_PROFILE'] },
  { key: 'symptom', label: 'Симптомы', accent: '#f59e0b', categories: ['SYMPTOM'] },
  { key: 'workup', label: 'Обследование', accent: '#06b6d4', categories: ['EXAM', 'LAB_TEST', 'INSTRUMENTAL_TEST'] },
  { key: 'diagnosis', label: 'Диагноз', accent: '#ec4899', categories: ['DIAGNOSIS'] },
  { key: 'treatment', label: 'Лечение', accent: '#10b981', categories: ['MEDICATION', 'SURGERY'] },
  { key: 'monitoring', label: 'Мониторинг', accent: '#8b5cf6', categories: ['MONITORING'] },
]

const STAGE_BY_CATEGORY: Record<string, number> = (() => {
  const map: Record<string, number> = {}
  STAGE_ORDER.forEach((stage, index) => {
    for (const category of stage.categories) map[category] = index
  })
  return map
})()

export function applyBlockLayout(nodes: FlowNode[], _edges: FlowEdge[] = []): FlowNode[] {
  const clinical = nodes.filter((n) => n.type !== 'frame' && n.type !== 'group')
  if (clinical.length === 0) return [...nodes]

  const FRAME_PAD_X = 32
  const FRAME_HEADER = 40
  const FRAME_PAD_BOTTOM = 22
  const NODE_GAP_X = 64
  const NODE_GAP_Y = 40
  const BAND_GAP = 96
  const MAX_COLS = 3

  const buckets = new Map<number, FlowNode[]>()
  const OTHER = STAGE_ORDER.length
  for (const node of clinical) {
    const category = String(node.data?.category || '').toUpperCase()
    const stage = category in STAGE_BY_CATEGORY ? STAGE_BY_CATEGORY[category] : OTHER
    if (!buckets.has(stage)) buckets.set(stage, [])
    buckets.get(stage)!.push(node)
  }

  const positioned: FlowNode[] = []
  const frames: FlowNode[] = []
  let cursorY = 0

  const orderedStages = [...buckets.keys()].sort((a, b) => a - b)
  for (const stage of orderedStages) {
    const stageNodes = buckets.get(stage)!
    const stageDef = stage < STAGE_ORDER.length ? STAGE_ORDER[stage] : null
    const label = stageDef ? stageDef.label : 'Прочее'
    const accent = stageDef ? stageDef.accent : '#94a3b8'

    let bandWidth = 0
    let rowTop = cursorY + FRAME_HEADER
    let rowHeight = 0
    let colX = FRAME_PAD_X
    let col = 0
    for (const node of stageNodes) {
      const { width, height } = getNodeDimensions(node)
      if (col === MAX_COLS) {
        col = 0
        colX = FRAME_PAD_X
        rowTop += rowHeight + NODE_GAP_Y
        rowHeight = 0
      }
      positioned.push({ ...node, position: { x: colX, y: rowTop } })
      colX += width + NODE_GAP_X
      bandWidth = Math.max(bandWidth, colX - NODE_GAP_X + FRAME_PAD_X)
      rowHeight = Math.max(rowHeight, height)
      col += 1
    }

    const bandBottom = rowTop + rowHeight + FRAME_PAD_BOTTOM
    frames.push({
      id: `frame_stage_${stage}`,
      type: 'frame',
      position: { x: 0, y: cursorY },
      data: { label, category: 'layout', stageKey: stageDef?.key || 'other', accent },
      style: { width: `${Math.max(bandWidth, 240)}px`, height: `${bandBottom - cursorY}px` },
      selectable: false,
      draggable: false,
    })
    cursorY = bandBottom + BAND_GAP
  }

  // Frames first so they render behind the clinical nodes.
  return [...frames, ...positioned]
}

export function getGraphBounds(nodes: FlowNode[]): { maxX: number; maxY: number; minX: number; minY: number } {
  if (!nodes.length) return { minX: 0, minY: 0, maxX: 400, maxY: 300 }

  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity

  for (const node of nodes) {
    const { width, height } = getNodeDimensions(node)
    minX = Math.min(minX, node.position.x)
    minY = Math.min(minY, node.position.y)
    maxX = Math.max(maxX, node.position.x + width)
    maxY = Math.max(maxY, node.position.y + height)
  }

  return { minX, minY, maxX, maxY }
}

export function placeGhostNodes(
  existingNodes: FlowNode[],
  labels: string[],
  categoryResolver: (label: string) => string
): FlowNode[] {
  const bounds = getGraphBounds(existingNodes)
  const startX = bounds.maxX + DEFAULT_NODESEP
  const startY = bounds.minY
  const colWidth = 240
  const rowHeight = 120

  return labels.map((label, index) => ({
    id: `ghost_${label}_${Date.now()}_${index}`,
    type: 'med',
    position: {
      x: startX + (index % 2) * colWidth,
      y: startY + Math.floor(index / 2) * rowHeight,
    },
    data: {
      label,
      category: categoryResolver(label),
      isGhost: true,
    },
  }))
}
