<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import { computed } from 'vue'
import { categoryMeta } from '~/constants/clinicalOntology'
import type { NodeDataDto } from '~/types/graph'

const props = defineProps<{
  id: string
  data: NodeDataDto
  selected?: boolean
  isHighlighted?: boolean
}>()

const meta = computed(() => categoryMeta(props.data.category))

const categoryColor = computed(() => (props.data.isGhost ? '#90a4ae' : meta.value.color))

const nodeShapeStyle = computed(() => {
  if (props.data.isGhost) {
    return {
      borderRadius: '8px',
      backgroundColor: '#f8fafc',
      borderStyle: 'dashed',
      borderColor: categoryColor.value,
    }
  }

  return {
    borderRadius: meta.value.radius,
    backgroundColor: meta.value.bg,
    borderStyle: 'solid',
    borderColor: categoryColor.value,
  }
})
</script>

<template>
  <div
    class="med-flow-node"
    :class="{
      'is-ghost': data.isGhost,
      'is-correct': data.isCorrect,
      'is-incorrect': data.isIncorrect,
      'is-highlighted': isHighlighted,
      'is-selected': selected,
    }"
    :style="nodeShapeStyle"
  >
    <!-- Inputs handle -->
    <Handle id="t" class="handle-in" type="target" :position="Position.Top" :style="{ background: categoryColor }" />

    <div class="med-flow-node__body">
      <div class="med-flow-node__header" :style="{ color: categoryColor }">
        <i class="mdi med-flow-node__icon" :class="meta.icon"/>
        <span class="med-flow-node__badge">{{ data.isGhost ? 'Пропущено' : meta.short }}</span>

        <!-- Verification Badges -->
        <span v-if="data.isCorrect" class="status-icon ml-auto">
          <i class="mdi mdi-check-circle status-icon--success"/>
        </span>
        <span v-else-if="data.isIncorrect" class="status-icon ml-auto">
          <i class="mdi mdi-alert-circle status-icon--error"/>
        </span>
        <span v-else-if="data.isGhost" class="status-icon ml-auto">
          <i class="mdi mdi-ghost status-icon--ghost"/>
        </span>
      </div>

      <div class="med-flow-node__title">{{ data.label }}</div>

      <!-- Metadata subtexts -->
      <div v-if="data.dosage || data.route" class="med-flow-node__meta mt-1">
        <div v-if="data.dosage" class="meta-item"><i class="mdi mdi-medical-bag opacity-60 mr-1"/>{{ data.dosage }}</div>
        <div v-if="data.route" class="meta-item"><i class="mdi mdi-transit-connection opacity-60 mr-1"/>{{ data.route }}</div>
      </div>
      <div v-if="data.expected_value" class="med-flow-node__meta mt-1">
        <div class="meta-item"><i class="mdi mdi-flask-outline opacity-60 mr-1"/>{{ data.expected_value }}</div>
      </div>
      <div v-if="data.stage" class="med-flow-node__meta mt-1">
        <div class="meta-item"><i class="mdi mdi-chart-line opacity-60 mr-1"/>{{ data.stage }}</div>
      </div>
    </div>

    <!-- Outputs handle -->
    <Handle id="s" class="handle-out" type="source" :position="Position.Bottom" :style="{ background: categoryColor }" />
  </div>
</template>

<style scoped>
.med-flow-node {
  min-width: 160px;
  max-width: 240px;
  border-radius: 12px;
  border: 2px solid;
  background-color: #ffffff;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  transition: border-color 0.18s ease, box-shadow 0.18s ease, opacity 0.18s ease;
  position: relative;
  overflow: visible;
  cursor: grab;
  user-select: none;
}

.med-flow-node:hover {
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.08);
}

.med-flow-node:active {
  cursor: grabbing;
}

.med-flow-node__body {
  padding: 12px;
}

.med-flow-node__header {
  display: flex;
  align-items: center;
  margin-bottom: 6px;
}

.med-flow-node__icon {
  font-size: 16px;
  margin-right: 4px;
}

.med-flow-node__badge {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 800;
}

.med-flow-node__title {
  font-size: 13px;
  font-weight: 700;
  line-height: 1.4;
  color: #1e293b;
}

.med-flow-node__meta {
  font-size: 10px;
  color: #475569;
  font-weight: 500;
  background-color: rgba(255, 255, 255, 0.4);
  padding: 2px 4px;
  border-radius: 4px;
}

.meta-item {
  display: flex;
  align-items: center;
  margin-top: 2px;
}

.status-icon .mdi {
  font-size: 16px;
}

.status-icon--success {
  color: #4caf50;
}

.status-icon--error {
  color: #f44336;
}

.status-icon--ghost {
  color: #90a4ae;
}

.handle-in,
.handle-out {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  border: 2px solid #ffffff;
  transition: width 0.15s ease, height 0.15s ease, box-shadow 0.15s ease;
}

/* Larger connection affordance on hover: easier to start/finish an edge.
   Grown via width/height (not transform) so Vue Flow's positioning
   translate(-50%, …) keeps the handle centered on the node border. */
.med-flow-node:hover .handle-in,
.med-flow-node:hover .handle-out {
  width: 15px;
  height: 15px;
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.15);
}

/* --- State Modifiers --- */

/* Selected node: clear focus ring so the inspector target is obvious. */
.med-flow-node.is-selected {
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.35), 0 8px 18px rgba(0, 0, 0, 0.1);
}

/* Ghost / Missing node */
.med-flow-node.is-ghost {
  border-style: dashed !important;
  opacity: 0.65;
  background-color: rgba(236, 239, 241, 0.5);
  box-shadow: none;
}
.med-flow-node.is-ghost:hover {
  opacity: 0.9;
}

/* Correct evaluation node */
.med-flow-node.is-correct {
  border-color: #4caf50 !important;
  box-shadow: 0 0 10px rgba(76, 175, 80, 0.2);
}

/* Incorrect evaluation node */
.med-flow-node.is-incorrect {
  border-color: #f44336 !important;
  box-shadow: 0 0 10px rgba(244, 67, 54, 0.2);
}

/* Interactive hover-highlight pulse from AI Judge feedback */
.med-flow-node.is-highlighted {
  box-shadow: 0 0 25px rgba(251, 192, 45, 0.6);
  border-color: #fbc02d !important;
  animation: glow-pulse 1.2s infinite alternate;
  z-index: 100;
}

@keyframes glow-pulse {
  from {
    box-shadow: 0 0 15px rgba(251, 192, 45, 0.4);
  }
  to {
    box-shadow: 0 0 30px rgba(251, 192, 45, 0.8);
  }
}
</style>
