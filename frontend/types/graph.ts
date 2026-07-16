import type { EdgeType, GraphEvaluationResponse, NodeType } from '~/types/api'

export type GraphNodeCategory = NodeType | 'DISEASE' | 'layout' | '__frame__' | string
export type GraphEdgeRelation = EdgeType
export type GraphNodeType = 'med' | 'frame' | 'group' | string

export interface GraphPosition {
  x: number
  y: number
}

export interface NodeDataDto {
  label: string
  category: GraphNodeCategory
  dosage?: string
  route?: string
  expected_value?: string
  stage?: string
  stageKey?: string
  accent?: string
  isGhost?: boolean
  isCorrect?: boolean
  isIncorrect?: boolean
  [key: string]: unknown
}

export interface FlowNode {
  id: string
  type: GraphNodeType
  position: GraphPosition
  data: NodeDataDto
  style?: Record<string, string | number>
  selectable?: boolean
  draggable?: boolean
  [key: string]: unknown
}

export interface FlowEdgeData {
  isIncorrect?: boolean
  isCorrect?: boolean
  [key: string]: unknown
}

export interface FlowEdge {
  id: string
  source: string
  target: string
  label?: GraphEdgeRelation | string
  type?: string
  sourceHandle?: string | null
  targetHandle?: string | null
  animated?: boolean
  data?: FlowEdgeData
  style?: Record<string, string | number>
  isIncorrect?: boolean
  [key: string]: unknown
}

export interface PaletteItem {
  label: string
  category: GraphNodeCategory
  dosage?: string
  route?: string
  expected_value?: string
  stage?: string
  isSearchResult?: boolean
}

export interface RelationOption {
  title: string
  value: GraphEdgeRelation
}

export interface GraphCanvasState {
  nodes: FlowNode[]
  edges: FlowEdge[]
  selectedNodeId: string | null
  selectedEdgeId: string | null
  defaultRelation: GraphEdgeRelation
}

export interface GraphCanvasActions {
  fitView: (options?: { padding?: number; duration?: number }) => void
  getCanvasRect: () => DOMRect | null
  screenToFlowCoordinate: (position: GraphPosition) => GraphPosition
}

export interface ClinicalTaskSummary {
  id: number
  title: string
  description?: string
  reference_graph_id: number
}

export type ClinicalCaseEvaluation = GraphEvaluationResponse | null
