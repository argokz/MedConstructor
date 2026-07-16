<script setup lang="ts">
const props = defineProps<{
  data: { label: string; category: string; stageKey?: string; accent?: string }
}>()

// Stage blocks (from applyBlockLayout) carry an accent + stageKey and render as a
// clean labelled clinical block. Manual layout frames keep the dashed drop-zone look.
const isStage = computed(() => Boolean(props.data?.stageKey))
const accent = computed(() => props.data?.accent || 'rgb(var(--v-theme-primary))')
</script>

<template>
  <div
    class="flow-group-node"
    :class="{ 'flow-group-node--stage': isStage }"
    :style="isStage ? { '--accent': accent } : undefined"
  >
    <div class="flow-group-node__title">{{ data.label }}</div>
    <div v-if="!isStage" class="flow-group-node__hint">Перетащите блоки внутрь области</div>
  </div>
</template>

<style scoped>
.flow-group-node {
  width: 100%;
  height: 100%;
  min-width: 200px;
  min-height: 160px;
  border-radius: 12px;
  border: 2px dashed rgba(var(--v-theme-primary), 0.3);
  background: rgba(var(--v-theme-primary), 0.05);
  padding: 10px 12px;
  box-sizing: border-box;
}
.flow-group-node__title {
  font-size: 12px;
  font-weight: 700;
  color: rgb(var(--v-theme-primary));
  opacity: 0.8;
}
.flow-group-node__hint {
  margin-top: 6px;
  font-size: 11px;
  font-weight: 500;
  color: rgb(var(--v-theme-on-surface));
  opacity: 0.5;
}

/* Stage block: solid accent header strip, soft tinted body, no drop hint. */
.flow-group-node--stage {
  border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
  background: color-mix(in srgb, var(--accent) 7%, transparent);
  padding: 0;
}
.flow-group-node--stage .flow-group-node__title {
  display: inline-block;
  color: #fff;
  opacity: 1;
  background: var(--accent);
  padding: 5px 12px;
  border-radius: 12px 0 12px 0;
  letter-spacing: 0.3px;
  text-transform: uppercase;
  font-size: 11px;
}
</style>
