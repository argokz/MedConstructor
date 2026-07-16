<script setup lang="ts">
import { CATEGORY_OPTIONS } from '~/constants/clinicalOntology'
import type { GraphNodeCategory, PaletteItem } from '~/types/graph'

const props = withDefaults(defineProps<{
  assignmentId: number | null
  reviewMode: boolean
  nodesCount: number
  edgesCount: number
  loading: boolean
  hintsLoading: boolean
  canUndo?: boolean
  canRedo?: boolean
  compact?: boolean
}>(), {
  canUndo: false,
  canRedo: false,
  compact: false,
})

const hasMissingRelations = computed(() => props.nodesCount >= 2 && props.edgesCount === 0)
const showResetDialog = ref(false)

const showCustomNodeDialog = ref(false)
const customNodeLabel = ref('')
const customNodeCategory = ref<GraphNodeCategory>('EXAM')
const categoryOptions = CATEGORY_OPTIONS

function submitCustomNode(): void {
  const label = customNodeLabel.value.trim()
  if (!label) {
    return
  }
  emit('add-custom-node', { label, category: customNodeCategory.value })
  customNodeLabel.value = ''
  showCustomNodeDialog.value = false
}

function confirmReset(): void {
  showResetDialog.value = false
  emit('reset-canvas')
}

const emit = defineEmits<{
  'submit-graph': []
  'show-reference-graph': []
  'fetch-hints': []
  'auto-layout': []
  'fit-view': []
  'reset-canvas': []
  'undo': []
  'redo': []
  'add-custom-node': [item: PaletteItem]
}>()
</script>

<template>
  <v-sheet class="constructor-toolbar px-4 py-3" elevation="0">
    <div class="toolbar-actions d-flex align-center ga-2 flex-wrap">
      <v-btn-group density="compact" divided class="undo-redo-group">
        <v-tooltip
          location="bottom"
          text="Отменить (Ctrl+Z)"
          aria-label="Отменить (Ctrl+Z)"
          content-class="constructor-tooltip"
          :disabled="reviewMode || !canUndo"
        >
          <template #activator="{ props: tp }">
            <span v-bind="tp" class="toolbar-tooltip-activator">
              <v-btn
                icon="mdi-undo-variant"
                size="small"
                variant="text"
                aria-label="Отменить действие"
                :disabled="reviewMode || !canUndo"
                @click="emit('undo')"
              />
            </span>
          </template>
        </v-tooltip>
        <v-tooltip
          location="bottom"
          text="Вернуть (Ctrl+Y)"
          aria-label="Вернуть (Ctrl+Y)"
          content-class="constructor-tooltip"
          :disabled="reviewMode || !canRedo"
        >
          <template #activator="{ props: tp }">
            <span v-bind="tp" class="toolbar-tooltip-activator">
              <v-btn
                icon="mdi-redo-variant"
                size="small"
                variant="text"
                aria-label="Вернуть действие"
                :disabled="reviewMode || !canRedo"
                @click="emit('redo')"
              />
            </span>
          </template>
        </v-tooltip>
      </v-btn-group>

      <v-btn
        class="action-btn"
        color="success"
        variant="flat"
        size="small"
        rounded="pill"
        :disabled="reviewMode || !nodesCount || hasMissingRelations"
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
      <v-btn
        class="action-btn"
        variant="tonal"
        size="small"
        rounded="pill"
        color="secondary"
        :disabled="!nodesCount"
        prepend-icon="mdi-vector-polyline"
        @click="emit('auto-layout')"
      >
        Авторазложить
      </v-btn>
      <v-btn
        class="action-btn"
        variant="tonal"
        size="small"
        rounded="pill"
        color="primary"
        :disabled="reviewMode"
        prepend-icon="mdi-plus-box-outline"
        @click="showCustomNodeDialog = true"
      >
        Свой блок
      </v-btn>
      <v-btn
        v-if="!compact"
        class="action-btn"
        variant="tonal"
        size="small"
        rounded="pill"
        :disabled="!nodesCount"
        prepend-icon="mdi-fit-to-screen"
        @click="emit('fit-view')"
      >
        Подогнать вид
      </v-btn>

      <v-spacer v-if="!compact" />

      <v-btn
        class="action-btn"
        color="error"
        variant="tonal"
        size="small"
        rounded="pill"
        prepend-icon="mdi-trash-can-outline"
        :disabled="reviewMode || (!nodesCount && !edgesCount)"
        @click="showResetDialog = true"
      >
        Очистить холст
      </v-btn>
    </div>

    <v-dialog v-model="showCustomNodeDialog" max-width="440">
      <v-card rounded="xl">
        <v-card-title class="font-weight-bold mt-2">Добавить свой блок</v-card-title>
        <v-card-text class="d-flex flex-column ga-3">
          <v-text-field
            v-model="customNodeLabel"
            label="Название блока"
            placeholder="Например: Аускультация сердца"
            variant="outlined"
            density="comfortable"
            autofocus
            hide-details
            @keyup.enter="submitCustomNode"
          />
          <v-select
            v-model="customNodeCategory"
            :items="categoryOptions"
            item-title="title"
            item-value="value"
            label="Категория"
            variant="outlined"
            density="comfortable"
            hide-details
          />
        </v-card-text>
        <v-card-actions class="pb-4 pr-4">
          <v-spacer />
          <v-btn variant="text" @click="showCustomNodeDialog = false">Отмена</v-btn>
          <v-btn
            color="primary"
            rounded="pill"
            variant="flat"
            prepend-icon="mdi-plus"
            :disabled="!customNodeLabel.trim()"
            @click="submitCustomNode"
          >
            Добавить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="showResetDialog" max-width="420">
      <v-card rounded="xl">
        <v-card-title class="font-weight-bold mt-2">Очистить холст?</v-card-title>
        <v-card-text class="text-body-2">
          Все блоки и связи будут удалены, история изменений сброшена. Действие нельзя отменить через Ctrl+Z.
        </v-card-text>
        <v-card-actions class="pb-4 pr-4">
          <v-spacer />
          <v-btn variant="text" @click="showResetDialog = false">Отмена</v-btn>
          <v-btn color="error" rounded="pill" variant="flat" prepend-icon="mdi-trash-can-outline" @click="confirmReset">
            Очистить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

  </v-sheet>
</template>

<style scoped>
.constructor-toolbar {
  background: #ffffff !important;
  border-bottom: 1px solid rgba(15, 23, 42, 0.1);
}

.toolbar-actions {
  min-height: 42px;
}

.toolbar-tooltip-activator {
  display: inline-flex;
}

.action-btn {
  letter-spacing: 0;
}

:global(.constructor-tooltip) {
  z-index: 2600 !important;
  padding: 6px 10px !important;
  border-radius: 6px !important;
  background: #0f172a !important;
  color: #ffffff !important;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.25) !important;
  font-size: 0.78rem !important;
  font-weight: 600 !important;
  opacity: 1 !important;
}
</style>
