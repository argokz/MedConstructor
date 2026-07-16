import type { EdgeType, GraphNodeData, GraphSchema } from '~/types/api'

/** Serialize a Vue Flow graph to the backend GraphSchema.
 * `frame`/`group` nodes are visual-only canvas helpers and are excluded from grading.
 */
type SerializedNodeData = GraphNodeData & Record<string, unknown>

function serializeNodeData(node: any): SerializedNodeData {
  const sourceData = node.data ?? {}
  const data: SerializedNodeData = {
    label: String(sourceData.label ?? node.label ?? '').trim() || 'unnamed',
    category: (String(sourceData.category ?? 'concept').trim() || 'concept') as GraphNodeData['category'],
  }

  if (sourceData.description != null && String(sourceData.description).trim() !== '') {
    data.description = String(sourceData.description).trim()
  }

  const protocolRefs = Array.isArray(sourceData.protocol_refs)
    ? sourceData.protocol_refs
    : Array.isArray(sourceData.protocolRefs)
      ? sourceData.protocolRefs
      : null
  if (protocolRefs) {
    data.protocol_refs = protocolRefs
  }

  if (sourceData.is_critical != null) {
    data.is_critical = Boolean(sourceData.is_critical)
  } else if (sourceData.isCritical != null) {
    data.is_critical = Boolean(sourceData.isCritical)
  }

  if (sourceData.source != null && String(sourceData.source).trim() !== '') {
    data.source = String(sourceData.source).trim()
  }

  if (sourceData.confidence != null && Number.isFinite(Number(sourceData.confidence))) {
    data.confidence = Number(sourceData.confidence)
  }

  return data
}

export function serializeStudentGraph(nodes: unknown[], edges: unknown[]): GraphSchema {
  const raw = nodes as any[]
  const conceptIds = new Set(
    raw.filter((n) => n.type !== 'frame' && n.type !== 'group').map((n) => String(n.id))
  )

  const cleanNodes = raw
    .filter((n) => n.type !== 'frame' && n.type !== 'group')
    .map((n) => ({
      id: String(n.id),
      type: n.type ?? 'default',
      position: {
        x: Number(n.position?.x ?? 0),
        y: Number(n.position?.y ?? 0),
      },
      data: serializeNodeData(n),
    }))

  const cleanEdges = (edges as any[])
    .filter((e) => conceptIds.has(String(e.source)) && conceptIds.has(String(e.target)))
    .map((e) => ({
      id: String(e.id),
      type: e.type != null && String(e.type).trim() !== '' ? String(e.type).trim() : 'custom',
      source: String(e.source),
      target: String(e.target),
      label:
        e.label != null && String(e.label).trim() !== ''
          ? String(e.label).trim() as EdgeType
          : 'DETERMINES',
      sourceHandle: e.sourceHandle || 's',
      targetHandle: e.targetHandle || 't',
    }))

  return { nodes: cleanNodes, edges: cleanEdges }
}

export function normalizeFlowEdge(edge: any, index = 0) {
  const source = String(edge?.source ?? '')
  const target = String(edge?.target ?? '')
  const id = String(edge?.id ?? `e_${source}_${target}_${index}`)
  return {
    ...edge,
    id,
    source,
    target,
    label:
      edge?.label != null && String(edge.label).trim() !== ''
        ? String(edge.label).trim()
        : 'DETERMINES',
    type: 'custom',
    sourceHandle: edge?.sourceHandle || 's',
    targetHandle: edge?.targetHandle || 't',
  }
}

export function normalizeFlowEdges(edges: unknown[]) {
  return (edges as any[]).map((edge, index) => normalizeFlowEdge(edge, index))
}

/**
 * Produce a plain node object safe to feed back into Vue Flow's `v-model`.
 *
 * Vue Flow augments the nodes in its internal store with non-serializable,
 * computed fields (`computedPosition`, `handleBounds`, `dimensions`, `events`,
 * `dragging`, `selected`, …). Spreading those augmented objects back into the
 * model (e.g. during auto-layout or when appending a dropped block) can corrupt
 * Vue Flow's reconciliation and drop nodes. Always re-assign the model with the
 * output of this helper so only the canonical fields survive.
 */
export function toPlainNode(node: any) {
  const plain: Record<string, unknown> = {
    id: String(node.id),
    type: node.type ?? 'med',
    position: {
      x: Number(node.position?.x ?? 0),
      y: Number(node.position?.y ?? 0),
    },
    data: { ...(node.data ?? {}) },
  }
  if (node.style) plain.style = { ...node.style }
  if (node.class != null) plain.class = node.class
  if (node.selectable != null) plain.selectable = node.selectable
  if (node.draggable != null) plain.draggable = node.draggable
  if (node.parentNode != null) plain.parentNode = node.parentNode
  if (node.width != null) plain.width = node.width
  if (node.height != null) plain.height = node.height
  return plain
}

export function toPlainNodes(nodes: unknown[]) {
  return (nodes as any[]).map((node) => toPlainNode(node))
}

/** Plain edge object safe to feed back into Vue Flow's `v-model` (see `toPlainNode`). */
export function toPlainEdge(edge: any) {
  const plain: Record<string, unknown> = {
    id: String(edge.id),
    source: String(edge.source),
    target: String(edge.target),
    type: edge.type ?? 'custom',
    sourceHandle: edge.sourceHandle ?? 's',
    targetHandle: edge.targetHandle ?? 't',
  }
  if (edge.label != null) plain.label = edge.label
  if (edge.data) plain.data = { ...edge.data }
  if (edge.style) plain.style = { ...edge.style }
  if (edge.animated != null) plain.animated = edge.animated
  if (edge.markerEnd != null) plain.markerEnd = edge.markerEnd
  return plain
}

export function toPlainEdges(edges: unknown[]) {
  return (edges as any[]).map((edge) => toPlainEdge(edge))
}
