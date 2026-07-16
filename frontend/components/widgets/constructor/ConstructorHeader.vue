<script setup lang="ts">
import type { ComputedRef } from 'vue'
import type { AssignmentProgressStatus, AssignmentPublic, UserRole } from '~/types/api'

interface AssignmentTimerView {
  isExpired: ComputedRef<boolean>
  label: ComputedRef<string | null>
}

const assignmentId = defineModel<number | null>('assignmentId', { required: true })
const showAssignmentDialog = defineModel<boolean>('showAssignmentDialog', { required: true })

withDefaults(defineProps<{
  assignments: AssignmentPublic[]
  assignmentsLoading: boolean
  selectedAssignment: AssignmentPublic | null
  assignmentDescription: string
  assignmentTimer: AssignmentTimerView
  authRole?: UserRole | null
  reviewMode: boolean
  nodesCount: number
  loading: boolean
  hintsLoading: boolean
  compact?: boolean
}>(), {
  authRole: null,
  compact: false,
})

const emit = defineEmits<{
  'refresh-assignments': []
  'start-assignment': []
  'submit-graph': []
  'show-reference-graph': []
  'fetch-hints': []
  'reset-canvas': []
}>()

const assignmentMenuProps = {
  contentClass: 'assignment-select-menu',
  location: 'bottom start',
  maxHeight: 460,
  maxWidth: 760,
  minWidth: 320,
} as const

function statusColor(status: AssignmentProgressStatus | null): string {
  if (status === 'completed') return 'success'
  if (status === 'submitted') return 'info'
  if (status === 'in_progress') return 'primary'
  return 'warning'
}

function statusText(status: AssignmentProgressStatus | null): string {
  if (status === 'completed') return 'Выполнено'
  if (status === 'submitted') return 'На проверке'
  if (status === 'in_progress') return 'В процессе'
  if (status === 'needs_revision') return 'Нужна доработка'
  return 'Не выполнено'
}
</script>

<template>
  <v-sheet class="constructor-header pa-3" rounded="0" elevation="0">
    <v-row no-gutters align="center" class="ga-3">
      <v-col cols="12" md="5" xl="4" class="min-w-0">
        <div class="d-flex align-center ga-2 mb-2">
          <v-icon icon="mdi-clipboard-text-play-outline" color="primary" size="20" />
          <span class="text-subtitle-2 font-weight-bold text-truncate">Клиническое задание</span>
          <v-chip size="x-small" color="primary" variant="tonal" prepend-icon="mdi-format-list-bulleted">
            {{ assignments.length }} заданий
          </v-chip>
          <v-spacer />
          <v-tooltip location="bottom" aria-label="Обновить список заданий">
            <template #activator="{ props: tooltipProps }">
              <v-btn
                v-bind="tooltipProps"
                icon="mdi-refresh"
                size="small"
                variant="text"
                aria-label="Обновить список заданий"
                :loading="assignmentsLoading"
                @click="emit('refresh-assignments')"
              />
            </template>
            Обновить список заданий
          </v-tooltip>
        </div>

        <v-autocomplete
          v-model="assignmentId"
          :items="assignments"
          item-title="title"
          item-value="id"
          label="Выберите задание"
          density="compact"
          variant="outlined"
          :loading="assignmentsLoading"
          hide-details
          auto-select-first
          class="select-light"
          prepend-inner-icon="mdi-clipboard-search-outline"
          :menu-props="assignmentMenuProps"
        >
          <template #item="{ props: itemProps, item }">
            <v-list-item
              v-bind="itemProps"
              class="assignment-option"
              lines="three"
            >
              <template #title>
                <div class="assignment-option-title">{{ item.raw.title }}</div>
              </template>
              <template #subtitle>
                <div class="assignment-option-description">
                  {{ item.raw.description || 'Без описания' }}
                </div>
              </template>
            </v-list-item>
          </template>
          <template #selection="{ item }">
            <span class="assignment-selection" :title="item.raw.title">{{ item.raw.title }}</span>
          </template>
        </v-autocomplete>
      </v-col>

      <v-col class="min-w-0">
        <div class="d-flex align-center ga-2 flex-wrap">
          <v-chip
            v-if="selectedAssignment?.progress_status"
            size="small"
            :color="statusColor(selectedAssignment.progress_status)"
            variant="tonal"
          >
            {{ statusText(selectedAssignment.progress_status) }}
          </v-chip>
          <v-chip
            v-if="selectedAssignment?.time_limit_minutes"
            size="small"
            :color="assignmentTimer.isExpired.value ? 'error' : 'warning'"
            variant="tonal"
            prepend-icon="mdi-timer-outline"
          >
            {{ assignmentTimer.label.value ? `Осталось ${assignmentTimer.label.value}` : `Лимит ${selectedAssignment.time_limit_minutes} мин` }}
          </v-chip>
          <v-btn
            v-if="authRole === 'student' && selectedAssignment && selectedAssignment.progress_status !== 'in_progress'"
            size="small"
            color="primary"
            variant="tonal"
            prepend-icon="mdi-play-circle-outline"
            @click="emit('start-assignment')"
          >
            Начать
          </v-btn>
          <v-btn
            size="small"
            variant="text"
            color="primary"
            prepend-icon="mdi-arrow-expand"
            :disabled="!selectedAssignment?.description"
            @click="showAssignmentDialog = true"
          >
            Описание
          </v-btn>
        </div>

        <div v-if="!compact" class="assignment-summary text-body-2 mt-2">
          {{ assignmentDescription }}
        </div>
      </v-col>

      <v-col cols="12" xl="auto">
        <div class="d-flex align-center justify-xl-end ga-2 flex-wrap">
          <v-btn
            class="action-btn"
            color="success"
            variant="flat"
            size="small"
            rounded="pill"
            :disabled="reviewMode || !nodesCount"
            prepend-icon="mdi-check-circle-outline"
            @click="emit('submit-graph')"
          >
            Проверить решение
          </v-btn>
          <v-btn
            class="action-btn"
            color="primary"
            variant="flat"
            size="small"
            rounded="pill"
            :disabled="!assignmentId"
            :loading="loading"
            prepend-icon="mdi-file-tree"
            @click="emit('show-reference-graph')"
          >
            Эталонный граф
          </v-btn>
          <v-btn
            class="action-btn"
            variant="tonal"
            size="small"
            rounded="pill"
            color="primary"
            :loading="hintsLoading"
            :disabled="!nodesCount"
            prepend-icon="mdi-lightbulb-on-outline"
            @click="emit('fetch-hints')"
          >
            Подсказки
          </v-btn>

          <v-menu location="bottom end">
            <template #activator="{ props: menuProps }">
              <v-btn
                v-bind="menuProps"
                icon="mdi-dots-horizontal"
                variant="text"
                density="comfortable"
                aria-label="Дополнительные действия"
              />
            </template>
            <v-list density="compact" min-width="230">
              <v-list-item prepend-icon="mdi-trash-can-outline" title="Очистить холст" @click="emit('reset-canvas')" />
            </v-list>
          </v-menu>
        </div>
      </v-col>
    </v-row>

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
  </v-sheet>
</template>

<style scoped>
.constructor-header {
  background: #ffffff !important;
  border-bottom: 1px solid rgba(15, 23, 42, 0.1);
}

.assignment-selection {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: normal;
  line-height: 1.25;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.assignment-summary {
  display: -webkit-box;
  max-height: 44px;
  overflow: hidden;
  color: #475569;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.assignment-dialog-text {
  max-height: 70vh;
  overflow-y: auto;
  white-space: pre-line;
  line-height: 1.65;
  color: #334155;
}

.select-light :deep(.v-field) {
  border-radius: 8px;
  background-color: #f8fafc !important;
  min-height: 48px;
}

.min-w-0 {
  min-width: 0;
}

:global(.assignment-select-menu) {
  max-width: min(760px, calc(100vw - 24px)) !important;
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 10px !important;
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.18) !important;
}

:global(.assignment-select-menu .v-list) {
  padding: 6px;
}

:global(.assignment-select-menu .assignment-option) {
  align-items: flex-start;
  min-height: 92px;
  margin-bottom: 4px;
  border-radius: 8px !important;
}

:global(.assignment-select-menu .assignment-option-title) {
  white-space: normal;
  overflow-wrap: anywhere;
  color: #0f172a;
  font-weight: 700;
  line-height: 1.35;
}

:global(.assignment-select-menu .assignment-option-description) {
  display: -webkit-box;
  overflow: hidden;
  color: #64748b;
  font-size: 0.86rem;
  line-height: 1.35;
  overflow-wrap: anywhere;
  white-space: normal;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}
</style>
