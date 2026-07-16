<script setup lang="ts">
import type { GraphNodeCategory, PaletteItem } from '~/types/graph'

interface CategoryOption {
  value: string
  title: string
}

interface PaletteGroup {
  cat: GraphNodeCategory
  items: PaletteItem[]
}

const paletteSearch = defineModel<string>('paletteSearch', { required: true })
const activePaletteCategory = defineModel<string>('activePaletteCategory', { required: true })
const paletteScope = defineModel<'assignment' | 'full'>('paletteScope', { required: true })

withDefaults(defineProps<{
  paletteLoading: boolean
  paletteSearchLoading: boolean
  paletteHint: string
  paletteFilterCategories: CategoryOption[]
  paletteGroups: PaletteGroup[]
  hasPaletteItems: boolean
  categoryTitle: (key: string) => string
  mobile?: boolean
}>(), {
  mobile: false,
})

const emit = defineEmits<{
  'drag-start': [event: DragEvent, item: PaletteItem]
  'add-palette-item': [item: PaletteItem]
}>()
</script>

<template>
  <v-sheet class="node-palette d-flex flex-column h-100 pa-3" :class="{ 'node-palette--mobile': mobile }" elevation="0">
    <div class="d-flex align-center justify-space-between mb-1">
      <h3 class="panel-title text-subtitle-2 font-weight-bold d-flex align-center mb-0">
        <v-icon icon="mdi-palette-swatch-outline" color="primary" size="18" class="mr-1" />
        Палитра блоков
      </h3>
      <v-btn-toggle
        v-model="paletteScope"
        mandatory
        density="compact"
        color="primary"
        variant="outlined"
        divided
      >
        <v-btn value="assignment" size="x-small">Задание</v-btn>
        <v-btn value="full" size="x-small">Каталог</v-btn>
      </v-btn-toggle>
    </div>

    <p class="text-caption text-slate-600 mb-2 palette-hint">
      {{ paletteHint }}
    </p>

    <v-text-field
      v-model="paletteSearch"
      density="compact"
      variant="outlined"
      placeholder="Найти блок по названию..."
      hide-details
      clearable
      class="select-light mb-2"
      prepend-inner-icon="mdi-magnify"
      :loading="paletteSearchLoading"
    />

    <div class="palette-chip-row mb-2">
      <v-chip
        v-for="cat in paletteFilterCategories"
        :key="cat.value"
        size="small"
        :color="activePaletteCategory === cat.value ? 'primary' : undefined"
        :variant="activePaletteCategory === cat.value ? 'flat' : 'tonal'"
        @click="activePaletteCategory = cat.value"
      >
        {{ cat.title }}
      </v-chip>
    </div>

    <div class="palette-groups flex-grow-1">
      <template v-if="hasPaletteItems">
        <section
          v-for="group in paletteGroups"
          :key="group.cat"
          class="palette-group mb-3"
        >
          <div class="palette-group-title text-caption font-weight-bold text-slate-500 mb-2">
            {{ categoryTitle(group.cat) }}
            <span class="text-slate-400">({{ group.items.length }})</span>
          </div>

          <div class="palette-group-items">
            <v-tooltip
              v-for="(item, index) in group.items"
              :key="group.cat + '-' + index + '-' + item.label"
              location="right"
              max-width="420"
              open-delay="300"
              content-class="palette-label-tooltip"
              :aria-label="item.label"
            >
              <template #activator="{ props: tooltipProps }">
                <v-sheet
                  v-bind="tooltipProps"
                  class="palette-item d-flex ga-2 pa-2 rounded border cursor-grab"
                  :class="{ 'palette-item--search': item.isSearchResult }"
                  :draggable="true"
                  role="button"
                  tabindex="0"
                  @dragstart="emit('drag-start', $event, item)"
                  @click="emit('add-palette-item', item)"
                  @keydown.enter.prevent="emit('add-palette-item', item)"
                  @keydown.space.prevent="emit('add-palette-item', item)"
                >
                  <v-icon
                    :icon="item.category === '__frame__' ? 'mdi-select-group' : 'mdi-drag'"
                    size="16"
                    color="primary"
                    class="palette-item-icon flex-shrink-0 mt-1"
                  />
                  <div class="palette-item-content">
                    <div class="palette-item-label text-body-2 font-weight-bold text-slate-800">{{ item.label }}</div>
                    <div class="palette-item-category text-caption text-slate-500">
                      {{ item.category === '__frame__' ? 'Оформление' : categoryTitle(item.category) }}
                    </div>
                  </div>
                </v-sheet>
              </template>
              <div class="palette-tooltip-body">
                <div class="font-weight-bold mb-1">{{ item.label }}</div>
                <div class="text-caption">
                  {{ item.category === '__frame__' ? 'Оформление' : categoryTitle(item.category) }}
                </div>
              </div>
            </v-tooltip>
          </div>
        </section>
      </template>

      <div v-else-if="!paletteLoading" class="empty-palette-state pa-4 text-center rounded">
        <v-icon icon="mdi-database-search-outline" size="32" class="d-block mb-2 mx-auto" />
        <p class="text-body-2 font-weight-bold mb-1">Блоки не найдены</p>
        <p class="text-caption mb-0">
          Попробуйте другой запрос, смените категорию или откройте полный каталог.
        </p>
      </div>

      <div v-else class="d-flex justify-center py-6">
        <v-progress-circular indeterminate color="primary" size="32" />
      </div>
    </div>

    <p class="palette-footer text-caption text-slate-500 mt-2 mb-0">
      Перетащите блок на холст или нажмите, чтобы добавить. Связи: от нижней точки к верхней.
    </p>
  </v-sheet>
</template>

<style scoped>
.node-palette {
  min-height: 0;
  overflow: hidden;
  background: #ffffff !important;
}

.node-palette--mobile {
  max-height: 82dvh;
  border-radius: 16px 16px 0 0;
}

.panel-title {
  color: #0f172a !important;
}

.palette-hint {
  line-height: 1.3;
}

.select-light :deep(.v-field) {
  border-radius: 8px;
  background-color: #f8fafc !important;
  /* Pin height so the loading bar / clear icon never reflows the field
     when categories or search state change. */
  height: 36px;
  min-height: 36px;
}

.select-light :deep(.v-input__control) {
  min-height: 36px;
}

.select-light :deep(.v-field__input) {
  min-height: 36px;
  padding-top: 0;
  padding-bottom: 0;
  align-items: center;
}

.select-light :deep(.v-field__prepend-inner),
.select-light :deep(.v-field__clearable) {
  padding-top: 6px;
}

.select-light :deep(.v-field__loader) {
  position: absolute;
  bottom: 0;
}

.palette-chip-row {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: thin;
  /* Stable height so switching the active chip (flat vs tonal) cannot nudge
     the surrounding layout. */
  min-height: 28px;
  align-items: center;
}

.palette-chip-row :deep(.v-chip) {
  flex: 0 0 auto;
  height: 24px;
}

.palette-groups {
  overflow-y: auto;
  min-height: 0;
  padding-right: 4px;
  scrollbar-width: thin;
  /* Reserve the scrollbar gutter so items don't reflow horizontally when the
     list becomes scrollable after blocks load. */
  scrollbar-gutter: stable;
}

.palette-group-items {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.palette-group-title {
  line-height: 1.2;
}

.palette-footer {
  line-height: 1.3;
}

.node-palette:not(.node-palette--mobile) .palette-footer {
  display: none;
}

.palette-group {
  margin-bottom: 8px !important;
}

.palette-item {
  cursor: grab;
  align-items: flex-start;
  background-color: #ffffff;
  border-color: rgba(15, 23, 42, 0.1);
  transition: background-color 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
  user-select: none;
}

.palette-item-content {
  min-width: 0;
  flex: 1 1 auto;
}

.palette-item-label {
  line-height: 1.28;
  overflow-wrap: anywhere;
  white-space: normal;
}

.palette-item-category {
  margin-top: 2px;
  line-height: 1.2;
}

.palette-item--search {
  border-color: rgba(37, 99, 235, 0.25);
  background-color: #f8fbff;
}

.palette-item:hover {
  background-color: #f1f5f9;
  transform: translateX(3px);
  border-color: #3b82f6;
}

.palette-item:active {
  cursor: grabbing;
}

.palette-item:focus-visible {
  outline: 3px solid rgba(37, 99, 235, 0.25);
  border-color: #2563eb;
}

.empty-palette-state {
  background: #f8fafc;
  border: 1px dashed rgba(100, 116, 139, 0.35);
  color: #64748b;
}

:global(.palette-label-tooltip) {
  max-width: min(420px, calc(100vw - 24px)) !important;
  padding: 10px 12px !important;
  border-radius: 8px !important;
  background: #0f172a !important;
  color: #ffffff !important;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.24) !important;
  opacity: 1 !important;
}

:global(.palette-label-tooltip .palette-tooltip-body) {
  white-space: normal;
  overflow-wrap: anywhere;
  line-height: 1.35;
}
</style>
