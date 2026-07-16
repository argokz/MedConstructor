<script setup lang="ts">
defineProps<{
  eyebrow?: string | null
  title: string
  subtitle?: string | null
}>()
</script>

<template>
  <div class="page-header mb-4">
    <div class="page-header__content">
      <div v-if="eyebrow" class="text-overline text-primary font-weight-bold">
        {{ eyebrow }}
      </div>
      <h1 class="text-h5 text-md-h4 font-weight-bold mb-1">
        {{ title }}
      </h1>
      <p v-if="subtitle" class="text-body-2 text-medium-emphasis mb-0">
        {{ subtitle }}
      </p>
    </div>
    <div v-if="$slots.actions" class="page-header__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.page-header__content {
  min-width: 0;
}

.page-header__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}

@media (max-width: 720px) {
  .page-header {
    align-items: stretch;
    flex-direction: column;
  }

  .page-header__actions {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
