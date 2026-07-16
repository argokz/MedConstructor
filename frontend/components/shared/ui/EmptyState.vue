<script setup lang="ts">
withDefaults(defineProps<{
  icon: string
  title: string
  text?: string | null
  color?: string
}>(), {
  color: 'primary',
  text: null,
})
</script>

<template>
  <div class="empty-state">
    <v-icon :icon="icon" size="48" :color="color" />
    <div class="font-weight-bold mt-2">{{ title }}</div>
    <div v-if="text" class="text-body-2 text-medium-emphasis">{{ text }}</div>
    <div v-if="$slots.action" class="mt-4">
      <slot name="action" />
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  min-height: 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 24px;
}
</style>
