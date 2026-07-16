<script setup lang="ts">
import { CATEGORY_OPTIONS } from '~/constants/clinicalOntology'
import type { GraphEdgeRelation, GraphNodeCategory, PaletteItem, RelationOption } from '~/types/graph'

const props = defineProps<{
  nodesCount: number
  readOnly?: boolean
  relations: RelationOption[]
  selectedEdgeId: string | null
}>()

const defaultRelation = defineModel<GraphEdgeRelation>('defaultRelation', { required: true })
const selectedEdgeLabel = defineModel<GraphEdgeRelation>('selectedEdgeLabel', { required: true })

const emit = defineEmits<{
  'add-custom-node': [item: PaletteItem]
  'auto-layout': []
  'block-layout': []
  'delete-selected-edge': []
  'fit-view': []
}>()

const showCustomNodeDialog = ref(false)
const customNodeLabel = ref('')
const customNodeCategory = ref<GraphNodeCategory>('MEDICATION')

const categoryOptions = CATEGORY_OPTIONS

function relationTitle(value: GraphEdgeRelation): string {
  return props.relations.find((relation) => relation.value === value)?.title ?? value
}

function selectDefaultRelation(value: GraphEdgeRelation): void {
  if (!props.readOnly) {
    defaultRelation.value = value
  }
}

function selectEdgeRelation(value: GraphEdgeRelation): void {
  if (!props.readOnly) {
    selectedEdgeLabel.value = value
  }
}

function submitCustomNode(): void {
  const label = customNodeLabel.value.trim()

  if (!label || props.readOnly) {
    return
  }

  emit('add-custom-node', {
    category: customNodeCategory.value,
    label,
  })
  showCustomNodeDialog.value = false
  customNodeLabel.value = ''
}
</script>

<template>
  <div class="graph-toolbar">
    <div class="graph-toolbar-row">
      <v-btn-group density="compact" class="graph-toolbar-buttons" divided>
        <v-tooltip
          location="top"
          text="Свой блок"
          aria-label="Свой блок"
          content-class="constructor-tooltip"
          :disabled="readOnly"
        >
          <template #activator="{ props: tooltipProps }">
            <span v-bind="tooltipProps" class="toolbar-tooltip-activator">
              <v-btn
                color="primary"
                icon="mdi-plus"
                size="small"
                variant="tonal"
                aria-label="Создать свой блок"
                :disabled="readOnly"
                @click="showCustomNodeDialog = true"
              />
            </span>
          </template>
        </v-tooltip>

        <v-tooltip
          location="top"
          text="Выровнять граф"
          aria-label="Выровнять граф"
          content-class="constructor-tooltip"
          :disabled="!nodesCount"
        >
          <template #activator="{ props: tooltipProps }">
            <span v-bind="tooltipProps" class="toolbar-tooltip-activator">
              <v-btn
                color="secondary"
                icon="mdi-vector-polyline"
                size="small"
                variant="tonal"
                aria-label="Выровнять граф"
                :disabled="!nodesCount"
                @click="emit('auto-layout')"
              />
            </span>
          </template>
        </v-tooltip>

        <v-tooltip
          location="top"
          text="Разложить по клиническим этапам"
          aria-label="По этапам"
          content-class="constructor-tooltip"
          :disabled="!nodesCount"
        >
          <template #activator="{ props: tooltipProps }">
            <span v-bind="tooltipProps" class="toolbar-tooltip-activator">
              <v-btn
                color="primary"
                icon="mdi-view-agenda-outline"
                size="small"
                variant="tonal"
                aria-label="Разложить по этапам"
                :disabled="!nodesCount"
                @click="emit('block-layout')"
              />
            </span>
          </template>
        </v-tooltip>

        <v-tooltip
          location="top"
          text="Подогнать вид"
          aria-label="Подогнать вид"
          content-class="constructor-tooltip"
          :disabled="!nodesCount"
        >
          <template #activator="{ props: tooltipProps }">
            <span v-bind="tooltipProps" class="toolbar-tooltip-activator">
              <v-btn
                icon="mdi-fit-to-screen"
                size="small"
                variant="tonal"
                aria-label="Подогнать вид графа"
                :disabled="!nodesCount"
                @click="emit('fit-view')"
              />
            </span>
          </template>
        </v-tooltip>
      </v-btn-group>

      <div class="graph-toolbar-field">
        <div class="text-caption font-weight-bold toolbar-label">Тип связи для новых рёбер</div>
        <v-menu location="bottom start" max-width="520">
          <template #activator="{ props: menuProps }">
            <v-btn
              v-bind="menuProps"
              class="relation-picker-button"
              color="primary"
              variant="tonal"
              size="small"
              append-icon="mdi-menu-down"
              :disabled="readOnly"
            >
              {{ relationTitle(defaultRelation) }}
            </v-btn>
          </template>
          <v-list density="compact" class="relation-picker-menu pa-1">
            <v-list-item
              v-for="relation in relations"
              :key="relation.value"
              class="relation-picker-item rounded"
              :active="defaultRelation === relation.value"
              @click="selectDefaultRelation(relation.value)"
            >
              <v-list-item-title class="relation-picker-title">
                {{ relation.title }}
              </v-list-item-title>
            </v-list-item>
          </v-list>
        </v-menu>
      </div>

      <div v-if="selectedEdgeId" class="graph-toolbar-field">
        <div class="text-caption font-weight-bold toolbar-label">Выбранное ребро</div>
        <v-menu location="bottom start" max-width="520">
          <template #activator="{ props: menuProps }">
            <v-btn
              v-bind="menuProps"
              class="relation-picker-button"
              color="primary"
              variant="tonal"
              size="small"
              append-icon="mdi-menu-down"
              :disabled="readOnly"
            >
              {{ relationTitle(selectedEdgeLabel) }}
            </v-btn>
          </template>
          <v-list density="compact" class="relation-picker-menu pa-1">
            <v-list-item
              v-for="relation in relations"
              :key="relation.value"
              class="relation-picker-item rounded"
              :active="selectedEdgeLabel === relation.value"
              @click="selectEdgeRelation(relation.value)"
            >
              <v-list-item-title class="relation-picker-title">
                {{ relation.title }}
              </v-list-item-title>
            </v-list-item>
          </v-list>
        </v-menu>
      </div>

      <v-btn
        v-if="selectedEdgeId"
        class="delete-edge-btn"
        color="error"
        prepend-icon="mdi-delete-outline"
        size="small"
        variant="tonal"
        :disabled="readOnly"
        @click="emit('delete-selected-edge')"
      >
        Удалить связь
      </v-btn>
    </div>

    <v-dialog v-model="showCustomNodeDialog" max-width="400">
      <v-card rounded="xl">
        <v-card-title class="font-weight-bold mt-2">Создать свой блок</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="customNodeLabel"
            autofocus
            class="mb-3"
            density="comfortable"
            label="Название"
            variant="outlined"
          />
          <v-select
            v-model="customNodeCategory"
            :items="categoryOptions"
            density="comfortable"
            item-title="title"
            item-value="value"
            label="Категория"
            variant="outlined"
          />
        </v-card-text>
        <v-card-actions class="pb-4 pr-4">
          <v-spacer />
          <v-btn variant="text" @click="showCustomNodeDialog = false">Отмена</v-btn>
          <v-btn
            color="primary"
            rounded="pill"
            variant="flat"
            :disabled="!customNodeLabel.trim()"
            @click="submitCustomNode"
          >
            Добавить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.graph-toolbar {
  flex: 0 0 auto;
  width: 100%;
  padding: 8px 12px 10px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.1);
  background: #ffffff !important;
  color: #1e293b;
  pointer-events: auto;
}

.graph-toolbar-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 42px;
  flex-wrap: nowrap;
}

.graph-toolbar-buttons {
  flex: 0 0 auto;
}

.graph-toolbar-field {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1 1 0;
}

.toolbar-label {
  color: #334155;
  opacity: 1;
  white-space: nowrap;
}

.toolbar-tooltip-activator {
  display: inline-flex;
}

.relation-picker-button {
  justify-content: flex-start;
  height: auto !important;
  min-height: 36px;
  width: 100%;
  max-width: 100%;
  padding: 6px 10px !important;
  letter-spacing: 0;
}

.relation-picker-button :deep(.v-btn__content) {
  justify-content: flex-start;
  min-width: 0;
  flex: 1 1 auto;
  white-space: normal;
  overflow-wrap: anywhere;
  line-height: 1.2;
  text-align: left;
}

.relation-picker-menu {
  width: min(520px, calc(100vw - 24px));
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 10px !important;
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.18) !important;
}

.relation-picker-item {
  min-height: 42px;
}

.relation-picker-title {
  white-space: normal;
  overflow-wrap: anywhere;
  line-height: 1.3;
  font-weight: 700;
}

.delete-edge-btn {
  flex: 0 0 auto;
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

@media (max-width: 720px) {
  .graph-toolbar-row {
    align-items: stretch;
    flex-wrap: wrap;
  }

  .graph-toolbar-field {
    grid-template-columns: 1fr;
    width: 100%;
  }

  .toolbar-label {
    white-space: normal;
  }
}
</style>
