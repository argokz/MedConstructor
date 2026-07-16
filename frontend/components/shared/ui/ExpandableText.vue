<script setup lang="ts">
const props = withDefaults(defineProps<{
  text?: string | number | null
  title?: string
  emptyText?: string
  lines?: number
  minLength?: number
}>(), {
  text: null,
  title: 'Полный текст',
  emptyText: '—',
  lines: 3,
  minLength: 120,
})

const dialogOpen = ref(false)

const normalizedText = computed(() => {
  if (props.text === null || props.text === undefined || props.text === '') return ''
  return String(props.text).trim()
})

const canExpand = computed(() =>
  normalizedText.value.length > props.minLength || normalizedText.value.includes('\n'),
)
</script>

<template>
  <div class="expandable-text">
    <span v-if="!normalizedText" class="text-medium-emphasis">{{ emptyText }}</span>
    <template v-else>
      <span
        class="expandable-text__preview"
        :style="{ '--line-count': String(lines) }"
      >
        {{ normalizedText }}
      </span>
      <v-btn
        v-if="canExpand"
        class="expandable-text__button mt-1"
        color="primary"
        density="compact"
        size="small"
        variant="text"
        aria-label="Открыть полный текст"
        @click="dialogOpen = true"
      >
        Читать полностью
      </v-btn>
    </template>

    <v-dialog v-model="dialogOpen" max-width="860">
      <v-card rounded="lg">
        <v-card-title class="d-flex align-center px-5 py-4">
          {{ title }}
          <v-spacer />
          <v-btn
            icon="mdi-close"
            variant="text"
            density="comfortable"
            aria-label="Закрыть полный текст"
            @click="dialogOpen = false"
          />
        </v-card-title>
        <v-divider />
        <v-card-text class="expandable-text__dialog pa-5">
          {{ normalizedText || emptyText }}
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.expandable-text {
  min-width: 0;
  max-width: min(68ch, 100%);
}

.expandable-text__preview {
  display: -webkit-box;
  overflow: hidden;
  line-height: 1.45;
  overflow-wrap: anywhere;
  white-space: pre-line;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: var(--line-count);
}

.expandable-text__button {
  padding-inline: 0 !important;
  letter-spacing: 0;
}

.expandable-text__dialog {
  max-height: 72vh;
  overflow-y: auto;
  color: #334155;
  line-height: 1.65;
  overflow-wrap: anywhere;
  white-space: pre-line;
}
</style>
