<script setup lang="ts">
import { BaseEdge, EdgeLabelRenderer, type EdgeProps, getSmoothStepPath } from '@vue-flow/core'
import { computed } from 'vue'
import { toPlainEdges } from '~/composables/useGraphPayload'
import {
  RELATION_FALLBACK_COLOR,
  RELATION_UNSET_DASH,
  RELATIONS,
  relationMeta,
} from '~/constants/clinicalOntology'
import { useClinicalCaseStore } from '~/stores/clinicalCase'
import type { FlowEdge, FlowEdgeData, GraphEdgeRelation } from '~/types/graph'

const props = defineProps<EdgeProps<FlowEdgeData>>()

const store = useClinicalCaseStore()

const pathParams = computed(() => getSmoothStepPath({ ...props, borderRadius: 10 }))
const pathString = computed(() => pathParams.value[0])
const labelX = computed(() => pathParams.value[1])
const labelY = computed(() => pathParams.value[2])
const relation = computed(() => relationMeta(props.label))
const labelOffset = computed(() => {
  const dx = props.targetX - props.sourceX
  const dy = props.targetY - props.sourceY
  const length = Math.hypot(dx, dy) || 1
  const offset = 18

  return {
    x: (-dy / length) * offset,
    y: (dx / length) * offset,
  }
})

const edgeColor = computed(() => {
  if (props.data?.isIncorrect) return '#ef5350'
  if (props.data?.isCorrect) return '#4caf50'
  if (props.selected) return '#eab308'
  return relation.value?.color ?? RELATION_FALLBACK_COLOR
})

const edgeStyle = computed(() => {
  const bold = relation.value?.bold ?? false
  const width = props.selected ? (bold ? '4px' : '3.5px') : (bold ? '3px' : '2.5px')
  const dash = relation.value ? relation.value.dash : RELATION_UNSET_DASH

  return {
    // Inline `fill: none` so PNG export (html-to-image) never fills the edge path
    // black — the CSS class rule is not reliably applied to the cloned SVG.
    fill: 'none',
    stroke: edgeColor.value,
    strokeWidth: width,
    strokeDasharray: dash,
    transition: 'stroke 0.25s, stroke-width 0.25s',
  }
})

function selectRelation(relValue: GraphEdgeRelation) {
  // Reassign the whole array with plain clones (never mutate Vue Flow's
  // augmented edge objects in place) so the change hits the undo history
  // and the canvas reconciles cleanly.
  store.edges = (toPlainEdges(store.edges) as FlowEdge[]).map((edge) =>
    edge.id === props.id ? { ...edge, label: relValue } : edge,
  )
}

const labelRussian = computed(() => {
  if (relation.value) return relation.value.short
  return typeof props.label === 'string' ? props.label : ''
})
</script>

<template>
  <g class="custom-edge-group">
    <BaseEdge :id="id" :path="pathString" :style="edgeStyle" :marker-end="markerEnd" />
  </g>

  <EdgeLabelRenderer>
    <div
      class="edge-label-host nodrag nopan"
      :style="{
        transform: `translate(-50%, -50%) translate(${labelX + labelOffset.x}px, ${labelY + labelOffset.y}px)`,
      }"
    >
      <div v-if="!label" class="relation-picker">
        <v-menu location="bottom center" density="compact">
          <template #activator="{ props: menuProps }">
            <v-btn
              v-bind="menuProps"
              size="x-small"
              color="warning"
              variant="flat"
              rounded
              class="relation-picker-btn text-none"
            >
              Выбрать связь <i class="mdi mdi-chevron-down ml-1" />
            </v-btn>
          </template>
          <v-list class="relation-menu pa-1" density="compact">
            <v-list-item
              v-for="rel in RELATIONS"
              :key="rel.value"
              :value="rel.value"
              class="relation-menu-item text-caption py-1 rounded"
              @click="selectRelation(rel.value)"
            >
              <template #prepend>
                <span class="relation-swatch mr-2" :style="{ background: rel.color }" />
              </template>
              <v-list-item-title class="relation-menu-title">{{ rel.title }}</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-menu>
      </div>

      <div
        v-else
        class="relation-badge"
        :class="{
          'is-incorrect': data?.isIncorrect,
          'is-correct': data?.isCorrect,
          'is-selected': selected,
        }"
        :style="{ borderColor: edgeColor, color: edgeColor }"
      >
        <v-menu location="bottom center" density="compact">
          <template #activator="{ props: menuProps }">
            <span v-bind="menuProps" class="relation-text font-weight-bold text-caption cursor-pointer">
              {{ labelRussian }}
            </span>
          </template>
          <v-list class="relation-menu pa-1" density="compact">
            <v-list-item
              v-for="rel in RELATIONS"
              :key="rel.value"
              :value="rel.value"
              class="relation-menu-item text-caption py-1 rounded"
              @click="selectRelation(rel.value)"
            >
              <template #prepend>
                <span class="relation-swatch mr-2" :style="{ background: rel.color }" />
              </template>
              <v-list-item-title class="relation-menu-title">{{ rel.title }}</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-menu>
      </div>
    </div>
  </EdgeLabelRenderer>
</template>

<style scoped>
.edge-label-host {
  position: absolute;
  pointer-events: all;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: center;
}

.relation-picker-btn {
  box-shadow: 0 0 0 4px #ffffff, 0 4px 10px rgba(0, 0, 0, 0.15) !important;
  font-weight: 700 !important;
}

.relation-badge {
  background-color: #ffffff;
  border: 2px solid;
  border-radius: 6px;
  padding: 4px 10px;
  box-shadow: 0 0 0 4px #ffffff, 0 6px 16px rgba(15, 23, 42, 0.16);
  font-size: 11px;
  letter-spacing: 0.02em;
  white-space: nowrap;
  text-align: center;
  transition: all 0.2s ease;
  user-select: none;
}

.relation-badge:hover {
  transform: scale(1.04);
  box-shadow: 0 0 0 4px #ffffff, 0 8px 18px rgba(15, 23, 42, 0.2);
}

.relation-badge.is-correct {
  background-color: #e8f5e9;
  border-color: #4caf50;
  color: #2e7d32 !important;
}

.relation-badge.is-incorrect {
  background-color: #ffebee;
  border-color: #ef5350;
  color: #c62828 !important;
}

.relation-badge.is-selected {
  box-shadow: 0 0 10px rgba(251, 192, 45, 0.4);
}

.relation-text {
  cursor: pointer;
}

.relation-swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex: 0 0 auto;
}

.relation-menu {
  width: min(520px, calc(100vw - 24px));
}

.relation-menu-item {
  align-items: flex-start;
  min-height: 40px;
}

.relation-menu-title {
  white-space: normal;
  overflow-wrap: anywhere;
  line-height: 1.25;
  font-weight: 700;
}
</style>
