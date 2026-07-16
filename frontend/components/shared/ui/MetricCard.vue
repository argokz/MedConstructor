<script setup lang="ts">
withDefaults(defineProps<{
  title: string
  value: string | number
  icon?: string | null
  color?: string
  subtitle?: string | null
}>(), {
  color: 'primary',
  icon: null,
  subtitle: null,
})
</script>

<template>
  <v-card class="metric-card" elevation="0">
    <div class="d-flex align-start justify-space-between ga-3">
      <div class="min-w-0">
        <div class="text-caption text-medium-emphasis">{{ title }}</div>
        <div class="text-h4 font-weight-bold" :class="`text-${color}`">{{ value }}</div>
        <div v-if="subtitle" class="text-caption text-medium-emphasis mt-1">{{ subtitle }}</div>
      </div>
      <v-avatar v-if="icon" :color="color" variant="tonal" rounded="lg" size="38">
        <v-icon :icon="icon" />
      </v-avatar>
    </div>
  </v-card>
</template>

<style scoped>
.metric-card {
  min-height: 108px;
  padding: 18px;
  border: 1px solid rgba(var(--v-border-color), 0.12);
  border-radius: 8px !important;
  background: rgba(var(--v-theme-surface), 0.94) !important;
}

.min-w-0 {
  min-width: 0;
}
</style>
