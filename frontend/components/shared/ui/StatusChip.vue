<script setup lang="ts">
import { statusLabel } from '~/utils/statusLabels'

type StatusTone = 'success' | 'error' | 'warning' | 'info' | 'primary' | 'secondary' | 'grey'

const props = withDefaults(defineProps<{
  status?: string | null
  text?: string | null
  size?: 'x-small' | 'small' | 'default' | 'large' | 'x-large'
  variant?: 'flat' | 'text' | 'elevated' | 'tonal' | 'outlined' | 'plain'
}>(), {
  status: null,
  text: null,
  size: 'small',
  variant: 'tonal',
})

const chipColor = computed<StatusTone>(() => {
  const status = (props.status || '').toLowerCase()

  if (['accepted', 'completed', 'published', 'teacher_approved', 'success', 'active', 'yes'].includes(status)) return 'success'
  if (['error', 'failed', 'rejected', 'danger', 'no'].includes(status)) return 'error'
  if (['revision_requested', 'needs_revision', 'not_started', 'draft', 'warning'].includes(status)) return 'warning'
  if (['submitted', 'ai_generated', 'review_ready', 'needs_teacher_review', 'needs_review', 'in_progress', 'info'].includes(status)) return 'info'
  if (['admin', 'teacher', 'expert', 'student', 'primary'].includes(status)) return 'primary'
  if (['archived', 'inactive', 'grey'].includes(status)) return 'grey'

  return 'grey'
})

const chipText = computed(() => props.text || statusLabel(props.status))
</script>

<template>
  <v-chip :size="size" :variant="variant" :color="chipColor">
    {{ chipText }}
  </v-chip>
</template>
