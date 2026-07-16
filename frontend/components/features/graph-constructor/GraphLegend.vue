<script setup lang="ts">
import { CATEGORY_LEGEND, RELATIONS } from '~/constants/clinicalOntology'

// Compact ontology legend for read-only / preview graphs, where the palette and
// toolbar (which normally explain node colors and relation types) are hidden.
const expanded = ref(false)

const categories = CATEGORY_LEGEND

const relations = RELATIONS.map((relation) => ({
  label: relation.short,
  meaning: relation.description,
}))
</script>

<template>
  <div class="graph-legend">
    <button class="graph-legend__toggle" type="button" @click="expanded = !expanded">
      <v-icon :icon="expanded ? 'mdi-chevron-down' : 'mdi-information-outline'" size="16" />
      Легенда
    </button>

    <div v-if="expanded" class="graph-legend__body">
      <div class="graph-legend__section-title">Категории узлов</div>
      <div class="graph-legend__cats">
        <div v-for="c in categories" :key="c.label" class="graph-legend__cat">
          <span class="graph-legend__dot" :style="{ background: c.color }" />
          {{ c.label }}
        </div>
      </div>
      <div class="graph-legend__section-title mt-2">Типы связей</div>
      <div v-for="r in relations" :key="r.label" class="graph-legend__rel">
        <span class="graph-legend__rel-label">{{ r.label }}</span> — {{ r.meaning }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.graph-legend {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 5;
  font-size: 11px;
}
.graph-legend__toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(100, 116, 139, 0.25);
  background: rgba(255, 255, 255, 0.92);
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
  cursor: pointer;
}
.graph-legend__body {
  margin-top: 6px;
  max-width: 260px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(100, 116, 139, 0.2);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 6px 20px rgba(15, 23, 42, 0.08);
}
.graph-legend__section-title {
  font-weight: 700;
  color: #475569;
  margin-bottom: 5px;
}
.graph-legend__cats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 3px 10px;
}
.graph-legend__cat {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #334155;
}
.graph-legend__dot {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex: 0 0 auto;
}
.graph-legend__rel {
  color: #334155;
  line-height: 1.5;
}
.graph-legend__rel-label {
  font-weight: 600;
  color: #1e293b;
}
</style>
