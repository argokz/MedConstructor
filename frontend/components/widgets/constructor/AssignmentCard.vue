<script setup lang="ts">
import type { ComputedRef } from 'vue'
import type { AssignmentProgressStatus, AssignmentPublic, AssignmentStatus, UserRole } from '~/types/api'
import { statusLabel } from '~/utils/statusLabels'

interface AssignmentTimerView {
  isExpired: ComputedRef<boolean>
  label: ComputedRef<string | null>
}

const assignmentId = defineModel<number | null>('assignmentId', { required: true })
const showAssignmentDialog = defineModel<boolean>('showAssignmentDialog', { required: true })

const props = withDefaults(defineProps<{
  assignments: AssignmentPublic[]
  assignmentsLoading: boolean
  selectedAssignment: AssignmentPublic | null
  assignmentDescription: string
  assignmentTimer: AssignmentTimerView
  authRole?: UserRole | null
  mobile?: boolean
}>(), {
  authRole: null,
  mobile: false,
})

const emit = defineEmits<{
  'refresh-assignments': []
  'start-assignment': []
}>()

const assignmentPickerOpen = ref(false)
const assignmentSearch = ref('')

const filteredAssignments = computed(() => {
  const query = assignmentSearch.value.trim().toLowerCase()
  if (!query) return props.assignments

  return props.assignments.filter((assignment) => {
    const haystack = [
      assignment.title,
      assignment.description || '',
      assignment.protocol_id || '',
      assignment.protocol_external_id || '',
      assignment.protocol_title || '',
      assignment.protocol_year || '',
      assignment.protocol_category || '',
      ...(assignment.protocol_sections || []),
    ].join(' ').toLowerCase()
    return haystack.includes(query)
  })
})

const selectedAssignmentTitle = computed(() => props.selectedAssignment?.title || 'Выберите задание')
const selectedAssignmentSubtitle = computed(() => props.selectedAssignment?.description || 'Откройте список заданий и выберите клинический кейс.')
const selectedProtocolLabel = computed(() => {
  const assignment = props.selectedAssignment
  if (!assignment) return null
  if (assignment.protocol_external_id) return `Протокол МЗ РК #${assignment.protocol_external_id}`
  if (assignment.protocol_id) return `Протокол #${assignment.protocol_id}`
  if (assignment.protocol_title) return 'Протокол'
  return null
})
const selectedProtocolTooltip = computed(() => {
  const assignment = props.selectedAssignment
  if (!assignment) return ''
  return [
    assignment.protocol_title,
    assignment.protocol_year ? String(assignment.protocol_year) : null,
    assignment.protocol_category,
  ].filter(Boolean).join(' · ')
})

function chooseAssignment(assignment: AssignmentPublic): void {
  assignmentId.value = assignment.id
  assignmentPickerOpen.value = false
}

function progressColor(status: AssignmentProgressStatus | null): string {
  if (status === 'completed') return 'success'
  if (status === 'submitted') return 'info'
  if (status === 'in_progress') return 'primary'
  if (status === 'needs_revision') return 'error'
  return 'warning'
}

function progressText(status: AssignmentProgressStatus | null): string {
  if (status === 'completed') return 'Выполнено'
  if (status === 'submitted') return 'На проверке'
  if (status === 'in_progress') return 'В процессе'
  if (status === 'needs_revision') return 'Нужна доработка'
  return 'Не выполнено'
}

function assignmentStatusText(status: AssignmentStatus | null): string | null {
  return status ? statusLabel(status) : null
}

function referenceStatusText(status: string | null): string | null {
  return status ? statusLabel(status) : null
}
</script>

<template>
  <v-sheet
    class="assignment-card pa-3"
    :class="{ 'assignment-card--mobile': mobile }"
    elevation="0"
  >
    <div class="d-flex align-center ga-2 mb-2">
      <v-icon icon="mdi-clipboard-text-play-outline" color="primary" size="18" />
      <h2 class="assignment-title text-subtitle-2 font-weight-bold mb-0">Клиническое задание</h2>
      <v-spacer />
      <v-chip size="x-small" color="primary" variant="tonal" prepend-icon="mdi-format-list-bulleted">
        {{ assignments.length }}
      </v-chip>
      <v-btn
        size="small"
        density="compact"
        variant="tonal"
        color="primary"
        prepend-icon="mdi-arrow-expand"
        :disabled="!assignmentDescription"
        @click="showAssignmentDialog = true"
      >
        Открыть
      </v-btn>
      <v-tooltip
        location="bottom"
        text="Обновить список заданий"
        aria-label="Обновить список заданий"
        content-class="constructor-tooltip"
      >
        <template #activator="{ props: tooltipProps }">
          <v-btn
            v-bind="tooltipProps"
            icon="mdi-refresh"
            size="small"
            density="compact"
            variant="text"
            aria-label="Обновить список заданий"
            :loading="assignmentsLoading"
            @click="emit('refresh-assignments')"
          />
        </template>
      </v-tooltip>
    </div>

    <button
      type="button"
      class="assignment-picker-trigger mb-2"
      :disabled="assignmentsLoading"
      @click="assignmentPickerOpen = true"
    >
      <v-icon icon="mdi-clipboard-search-outline" color="primary" size="20" class="flex-shrink-0 mt-1" />
      <span class="assignment-picker-trigger-text">
        <span class="assignment-picker-label">Выберите задание</span>
        <span class="assignment-picker-title">{{ selectedAssignmentTitle }}</span>
        <span class="assignment-picker-description">{{ selectedAssignmentSubtitle }}</span>
      </span>
      <v-progress-circular v-if="assignmentsLoading" indeterminate color="primary" size="20" width="2" />
      <v-icon v-else icon="mdi-chevron-right" color="primary" size="20" class="flex-shrink-0" />
    </button>

    <div class="d-flex align-center ga-1 flex-wrap mb-2">
      <v-chip
        v-if="selectedAssignment?.progress_status"
        size="x-small"
        :color="progressColor(selectedAssignment.progress_status)"
        variant="tonal"
      >
        {{ progressText(selectedAssignment.progress_status) }}
      </v-chip>
      <v-chip
        v-if="authRole !== 'student' && assignmentStatusText(selectedAssignment?.status || null)"
        size="x-small"
        color="primary"
        variant="tonal"
      >
        {{ assignmentStatusText(selectedAssignment?.status || null) }}
      </v-chip>
      <v-chip
        v-if="referenceStatusText(selectedAssignment?.reference_status || null)"
        size="x-small"
        color="secondary"
        variant="tonal"
      >
        Эталон: {{ referenceStatusText(selectedAssignment?.reference_status || null) }}
      </v-chip>
      <v-tooltip
        v-if="selectedProtocolLabel"
        location="bottom"
        :text="selectedProtocolTooltip || selectedProtocolLabel"
        content-class="constructor-tooltip"
      >
        <template #activator="{ props: tooltipProps }">
          <v-chip
            v-bind="tooltipProps"
            size="x-small"
            color="info"
            variant="tonal"
            prepend-icon="mdi-book-open-page-variant-outline"
          >
            {{ selectedProtocolLabel }}
          </v-chip>
        </template>
      </v-tooltip>
      <v-chip
        v-if="selectedAssignment?.protocol_year"
        size="x-small"
        color="info"
        variant="tonal"
      >
        {{ selectedAssignment.protocol_year }}
      </v-chip>
      <v-chip
        v-if="selectedAssignment?.protocol_category"
        size="x-small"
        color="info"
        variant="tonal"
      >
        {{ selectedAssignment.protocol_category }}
      </v-chip>
      <v-chip
        v-if="selectedAssignment?.time_limit_minutes"
        size="x-small"
        :color="assignmentTimer.isExpired.value ? 'error' : 'warning'"
        variant="tonal"
        prepend-icon="mdi-timer-outline"
      >
        {{ assignmentTimer.label.value ? `Осталось ${assignmentTimer.label.value}` : `Лимит ${selectedAssignment.time_limit_minutes} мин` }}
      </v-chip>
    </div>

    <div
      v-if="authRole === 'student' && selectedAssignment && selectedAssignment.progress_status !== 'in_progress'"
      class="assignment-actions d-flex align-center ga-2 mt-2"
    >
      <v-btn
        size="small"
        color="primary"
        variant="tonal"
        prepend-icon="mdi-play-circle-outline"
        @click="emit('start-assignment')"
      >
        Начать
      </v-btn>
    </div>

    <v-dialog v-model="showAssignmentDialog" max-width="760">
      <v-card rounded="lg" class="assignment-dialog">
        <v-card-title class="d-flex align-center px-5 py-4">
          <v-icon icon="mdi-clipboard-text-play-outline" color="primary" class="mr-2" />
          {{ selectedAssignment?.title || 'Клиническое задание' }}
          <v-spacer />
          <v-btn
            icon="mdi-close"
            variant="text"
            density="comfortable"
            aria-label="Закрыть описание задания"
            @click="showAssignmentDialog = false"
          />
        </v-card-title>
        <v-divider />
        <v-card-text class="assignment-dialog-text pa-5">
          {{ assignmentDescription }}
        </v-card-text>
      </v-card>
    </v-dialog>

    <v-dialog v-model="assignmentPickerOpen" max-width="940" scrollable>
      <v-card rounded="lg" class="assignment-picker-dialog">
        <v-card-title class="d-flex align-center px-5 py-4">
          <v-icon icon="mdi-clipboard-text-search-outline" color="primary" class="mr-2" />
          Выберите задание
          <v-spacer />
          <v-btn
            icon="mdi-close"
            variant="text"
            density="comfortable"
            aria-label="Закрыть выбор задания"
            @click="assignmentPickerOpen = false"
          />
        </v-card-title>
        <v-divider />
        <div class="pa-4 pb-2">
          <v-text-field
            v-model="assignmentSearch"
            autofocus
            clearable
            density="comfortable"
            hide-details
            label="Поиск по названию и описанию"
            prepend-inner-icon="mdi-magnify"
            variant="outlined"
          />
        </div>
        <v-card-text class="assignment-picker-list pa-4">
          <v-card
            v-for="assignment in filteredAssignments"
            :key="assignment.id"
            class="assignment-picker-item mb-3"
            :class="{ 'assignment-picker-item--active': assignment.id === assignmentId }"
            elevation="0"
            role="button"
            tabindex="0"
            @click="chooseAssignment(assignment)"
            @keydown.enter.prevent="chooseAssignment(assignment)"
            @keydown.space.prevent="chooseAssignment(assignment)"
          >
            <div class="assignment-picker-item-head">
              <div class="assignment-picker-item-title">{{ assignment.title }}</div>
              <v-chip
                v-if="assignment.progress_status"
                size="small"
                :color="progressColor(assignment.progress_status)"
                variant="tonal"
              >
                {{ progressText(assignment.progress_status) }}
              </v-chip>
            </div>
            <div class="assignment-picker-item-description">
              {{ assignment.description || 'Без описания' }}
            </div>
            <div class="assignment-picker-item-meta">
              <v-chip v-if="assignmentStatusText(assignment.status || null)" size="x-small" color="primary" variant="tonal">
                {{ assignmentStatusText(assignment.status || null) }}
              </v-chip>
              <v-chip v-if="assignment.time_limit_minutes" size="x-small" color="warning" variant="tonal">
                Лимит {{ assignment.time_limit_minutes }} мин
              </v-chip>
              <v-chip v-if="referenceStatusText(assignment.reference_status || null)" size="x-small" color="secondary" variant="tonal">
                Эталон: {{ referenceStatusText(assignment.reference_status || null) }}
              </v-chip>
              <v-chip v-if="assignment.protocol_external_id || assignment.protocol_id || assignment.protocol_title" size="x-small" color="info" variant="tonal" prepend-icon="mdi-book-open-page-variant-outline">
                {{ assignment.protocol_external_id ? `Протокол МЗ РК #${assignment.protocol_external_id}` : assignment.protocol_id ? `Протокол #${assignment.protocol_id}` : 'Протокол' }}
              </v-chip>
              <v-chip v-if="assignment.protocol_year" size="x-small" color="info" variant="tonal">
                {{ assignment.protocol_year }}
              </v-chip>
              <v-chip v-if="assignment.protocol_category" size="x-small" color="info" variant="tonal">
                {{ assignment.protocol_category }}
              </v-chip>
            </div>
          </v-card>

          <div v-if="!filteredAssignments.length" class="assignment-picker-empty">
            <v-icon icon="mdi-clipboard-search-outline" size="40" color="primary" />
            <div class="font-weight-bold mt-2">Задания не найдены</div>
            <div class="text-body-2 text-medium-emphasis">Измените запрос или обновите список заданий.</div>
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>
  </v-sheet>
</template>

<style scoped>
.assignment-card {
  flex: 0 0 auto;
  min-height: 0;
  background: #ffffff !important;
  border-bottom: 1px solid rgba(15, 23, 42, 0.1);
}

.assignment-card--mobile {
  max-height: 34dvh;
  overflow-y: auto;
}

.assignment-title {
  color: #0f172a;
}

.assignment-dialog-text {
  max-height: 70vh;
  overflow-y: auto;
  color: #334155;
  line-height: 1.65;
  white-space: pre-line;
}

.assignment-picker-trigger {
  display: flex;
  align-items: flex-start;
  width: 100%;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid rgba(15, 23, 42, 0.16);
  border-radius: 10px;
  background: #f8fafc;
  color: #0f172a;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s ease, background-color 0.2s ease, box-shadow 0.2s ease;
}

.assignment-picker-trigger:hover {
  border-color: #2563eb;
  background: #ffffff;
  box-shadow: 0 8px 22px rgba(37, 99, 235, 0.12);
}

.assignment-picker-trigger:disabled {
  cursor: progress;
  opacity: 0.72;
}

.assignment-picker-trigger-text {
  display: flex;
  min-width: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 2px;
}

.assignment-picker-label {
  color: #64748b;
  font-size: 0.68rem;
  font-weight: 700;
}

.assignment-picker-title {
  overflow-wrap: anywhere;
  font-size: 0.88rem;
  font-weight: 800;
  line-height: 1.25;
}

.assignment-picker-description {
  display: -webkit-box;
  overflow: hidden;
  color: #64748b;
  font-size: 0.76rem;
  line-height: 1.3;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.assignment-picker-list {
  max-height: min(68vh, 680px);
  overflow-y: auto;
}

.assignment-picker-item {
  padding: 14px 16px;
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 10px !important;
  background: #ffffff !important;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.assignment-picker-item:hover,
.assignment-picker-item:focus-visible,
.assignment-picker-item--active {
  border-color: #2563eb;
  box-shadow: 0 10px 26px rgba(37, 99, 235, 0.12);
}

.assignment-picker-item--active {
  background: #eff6ff !important;
}

.assignment-picker-item-head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  justify-content: space-between;
}

.assignment-picker-item-title {
  color: #0f172a;
  font-weight: 800;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.assignment-picker-item-description {
  margin-top: 8px;
  color: #475569;
  line-height: 1.55;
  white-space: pre-line;
  overflow-wrap: anywhere;
}

.assignment-picker-item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.assignment-picker-empty {
  min-height: 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: #64748b;
}
</style>
