import { applyAutoLayout } from '~/composables/useGraphLayout'
import { normalizeFlowEdges } from '~/composables/useGraphPayload'

export function prepareGraphForDisplay(
  graph?: { nodes?: any[]; edges?: any[] } | null,
  options?: { spacious?: boolean },
) {
  const mappedNodes = (graph?.nodes || []).map((node) => ({
    ...node,
    type: node.type === 'frame' ? 'frame' : 'med',
  }))
  const mappedEdges = normalizeFlowEdges(graph?.edges || [])
  const nodes = applyAutoLayout(mappedNodes, mappedEdges, {
    spacious: options?.spacious !== false,
  })
  return { nodes, edges: mappedEdges }
}
