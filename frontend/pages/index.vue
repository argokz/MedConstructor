<script setup lang="ts">
import { useDisplay } from 'vuetify'
import type { PaletteItem } from '~/types/graph'

interface GraphFlowExposed {
  addPaletteItem: (item: PaletteItem) => void
  runAutoLayout: () => void
  runFitView: () => void
}

const mobilePaletteOpen = ref(false)
const mobileEvalOpen = ref(false)
const graphFlowRef = ref<GraphFlowExposed | null>(null)

// Only one layout shell (and thus a single Vue Flow canvas) is mounted at a
// time. `mounted` keeps SSR/first hydration on the desktop shell — matching
// Vuetify's SSR display default — and the switch to the mobile shell happens
// as a post-hydration client update, so there's no hydration mismatch and we
// never pay for two live canvases.
const { lgAndUp } = useDisplay()
const mounted = ref(false)
const isMobileShell = computed(() => mounted.value && !lgAndUp.value)
onMounted(() => {
  mounted.value = true
})

const {
  auth,
  nodes,
  edges,
  reviewMode,
  evalResult,
  selectedNode,
  snackbar,
  snackText,
  loading,
  dbPalette,
  paletteLoading,
  paletteSearchLoading,
  paletteSearch,
  paletteScope,
  activePaletteCategory,
  assignmentsLoading,
  showAssignmentDialog,
  metricValue,
  metricPercent,
  paletteGroups,
  hasPaletteItems,
  paletteHint,
  selectedAssignment,
  assignmentDescription,
  assignmentTimer,
  paletteFilterCategories,
  categoryTitle,
  CATEGORIES_OPTIONS,
  assignmentId,
  assignments,
  hintsResult,
  hintsLoading,
  feedbackLoading,
  showFeedbackDialog,
  formattedFeedback,
  fetchAssignments,
  startCurrentAssignment,
  onDragStart,
  addPaletteItemToCanvas,
  fetchHints,
  fetchFeedback,
  submitGraph,
  showReferenceGraph,
  showReferenceDialog,
  referenceNodes,
  referenceEdges,
  onValidationError,
  backToEditing,
  resetCanvas,
  deleteSelectedNode,
  canUndo,
  canRedo,
  undo,
  redo,
  updateSelectedNodeData,
  highlightNodeByLabel,
  clearHighlight,
  setPaletteAddHandler,
} = useConstructorWorkspace()

// Palette clicks are routed straight to the canvas component instead of a
// global window event.
onMounted(() => {
  setPaletteAddHandler((item) => graphFlowRef.value?.addPaletteItem(item))
})

onUnmounted(() => {
  setPaletteAddHandler(null)
})

function runCanvasAutoLayout(): void {
  graphFlowRef.value?.runAutoLayout()
}

function runCanvasFitView(): void {
  graphFlowRef.value?.runFitView()
}
</script>

<template>
  <div class="constructor-route">
    <v-container v-if="!isMobileShell" fluid class="constructor-page pa-0 fill-height d-flex">
      <v-row no-gutters class="fill-height constructor-row flex-nowrap">
        <v-col cols="auto" class="constructor-palette-col border-e">
          <div class="constructor-left-stack">
            <AssignmentCard
              v-model:assignment-id="assignmentId"
              v-model:show-assignment-dialog="showAssignmentDialog"
              :assignments="assignments"
              :assignments-loading="assignmentsLoading"
              :selected-assignment="selectedAssignment"
              :assignment-description="assignmentDescription"
              :assignment-timer="assignmentTimer"
              :auth-role="auth.user?.role"
              @refresh-assignments="fetchAssignments"
              @start-assignment="startCurrentAssignment()"
            />

            <div class="constructor-palette-stack">
              <NodePalette
                v-model:palette-search="paletteSearch"
                v-model:active-palette-category="activePaletteCategory"
                v-model:palette-scope="paletteScope"
                :palette-loading="paletteLoading"
                :palette-search-loading="paletteSearchLoading"
                :palette-hint="paletteHint"
                :palette-filter-categories="paletteFilterCategories"
                :palette-groups="paletteGroups"
                :has-palette-items="hasPaletteItems"
                :category-title="categoryTitle"
                @drag-start="onDragStart"
                @add-palette-item="addPaletteItemToCanvas"
              />
            </div>
          </div>
        </v-col>

      <v-col class="fill-height d-flex flex-column min-w-0">
        <ConstructorToolbar
          :assignment-id="assignmentId"
          :review-mode="reviewMode"
          :nodes-count="nodes.length"
          :edges-count="edges.length"
          :loading="loading"
          :hints-loading="hintsLoading"
          :can-undo="canUndo"
          :can-redo="canRedo"
          @submit-graph="submitGraph"
          @show-reference-graph="showReferenceGraph"
          @fetch-hints="fetchHints"
          @auto-layout="runCanvasAutoLayout"
          @fit-view="runCanvasFitView"
          @reset-canvas="resetCanvas"
          @undo="undo"
          @redo="redo"
          @add-custom-node="addPaletteItemToCanvas"
        />

        <div class="constructor-canvas flex-grow-1 position-relative">
          <ClientOnly>
            <GraphFlow
              ref="graphFlowRef"
              v-model:nodes="nodes"
              v-model:edges="edges"
              :palette="dbPalette"
              :read-only="reviewMode"
              @validation-error="onValidationError"
            />
            <template #fallback>
              <div class="d-flex align-center justify-center fill-height canvas-fallback">
                <v-progress-circular indeterminate color="primary" size="64" />
              </div>
            </template>
          </ClientOnly>
        </div>
      </v-col>

      <v-col cols="auto" class="constructor-eval-col border-s">
        <EvaluationPanel
          v-model:show-feedback-dialog="showFeedbackDialog"
          :selected-node="selectedNode"
          :review-mode="reviewMode"
          :eval-result="evalResult"
          :hints-result="hintsResult"
          :categories-options="CATEGORIES_OPTIONS"
          :feedback-loading="feedbackLoading"
          :formatted-feedback="formattedFeedback"
          :metric-value="metricValue"
          :metric-percent="metricPercent"
          @update-node-data="updateSelectedNodeData"
          @delete-selected-node="deleteSelectedNode"
          @back-to-editing="backToEditing"
          @fetch-feedback="fetchFeedback"
          @highlight-node="highlightNodeByLabel"
          @clear-highlight="clearHighlight"
        />
      </v-col>
    </v-row>
  </v-container>

  <div v-else class="constructor-mobile-shell d-flex flex-column fill-height">
    <AssignmentCard
      v-model:assignment-id="assignmentId"
      v-model:show-assignment-dialog="showAssignmentDialog"
      mobile
      :assignments="assignments"
      :assignments-loading="assignmentsLoading"
      :selected-assignment="selectedAssignment"
      :assignment-description="assignmentDescription"
      :assignment-timer="assignmentTimer"
      :auth-role="auth.user?.role"
      @refresh-assignments="fetchAssignments"
      @start-assignment="startCurrentAssignment()"
    />

    <ConstructorToolbar
      compact
      :assignment-id="assignmentId"
      :review-mode="reviewMode"
      :nodes-count="nodes.length"
      :edges-count="edges.length"
      :loading="loading"
      :hints-loading="hintsLoading"
      :can-undo="canUndo"
      :can-redo="canRedo"
      @submit-graph="submitGraph"
      @show-reference-graph="showReferenceGraph"
      @fetch-hints="fetchHints"
      @auto-layout="runCanvasAutoLayout"
      @fit-view="runCanvasFitView"
      @reset-canvas="resetCanvas"
      @undo="undo"
      @redo="redo"
      @add-custom-node="addPaletteItemToCanvas"
    />

    <div class="constructor-canvas flex-grow-1 position-relative">
      <ClientOnly>
        <GraphFlow
          ref="graphFlowRef"
          v-model:nodes="nodes"
          v-model:edges="edges"
          :palette="dbPalette"
          :read-only="reviewMode"
          @validation-error="onValidationError"
        />
        <template #fallback>
          <div class="d-flex align-center justify-center fill-height canvas-fallback">
            <v-progress-circular indeterminate color="primary" size="64" />
          </div>
        </template>
      </ClientOnly>
    </div>

    <div class="constructor-bottom-nav d-flex align-stretch">
      <v-btn
        variant="text"
        stacked
        height="64"
        class="flex-grow-1 rounded-0"
        prepend-icon="mdi-palette-swatch-outline"
        @click="mobilePaletteOpen = true"
      >
        Палитра
      </v-btn>
      <v-btn
        variant="text"
        stacked
        height="64"
        class="flex-grow-1 rounded-0"
        prepend-icon="mdi-shield-check-outline"
        @click="mobileEvalOpen = true"
      >
        Проверка
      </v-btn>
    </div>

    <v-bottom-sheet v-model="mobilePaletteOpen">
      <NodePalette
        v-model:palette-search="paletteSearch"
        v-model:active-palette-category="activePaletteCategory"
        v-model:palette-scope="paletteScope"
        mobile
        :palette-loading="paletteLoading"
        :palette-search-loading="paletteSearchLoading"
        :palette-hint="paletteHint"
        :palette-filter-categories="paletteFilterCategories"
        :palette-groups="paletteGroups"
        :has-palette-items="hasPaletteItems"
        :category-title="categoryTitle"
        @drag-start="onDragStart"
        @add-palette-item="addPaletteItemToCanvas"
      />
    </v-bottom-sheet>

    <v-bottom-sheet v-model="mobileEvalOpen">
      <EvaluationPanel
        v-model:show-feedback-dialog="showFeedbackDialog"
        mobile
        :selected-node="selectedNode"
        :review-mode="reviewMode"
        :eval-result="evalResult"
        :hints-result="hintsResult"
        :categories-options="CATEGORIES_OPTIONS"
        :feedback-loading="feedbackLoading"
        :formatted-feedback="formattedFeedback"
        :metric-value="metricValue"
        :metric-percent="metricPercent"
        @update-node-data="updateSelectedNodeData"
        @delete-selected-node="deleteSelectedNode"
        @back-to-editing="backToEditing"
        @fetch-feedback="fetchFeedback"
        @highlight-node="highlightNodeByLabel"
        @clear-highlight="clearHighlight"
      />
    </v-bottom-sheet>
  </div>

    <v-dialog v-model="showReferenceDialog" fullscreen scrim transition="dialog-bottom-transition">
      <v-card class="reference-dialog-card d-flex flex-column">
        <v-toolbar density="comfortable" color="primary" flat>
          <v-icon icon="mdi-file-tree" class="ml-4" />
          <v-toolbar-title class="font-weight-bold">Эталонный граф — только просмотр</v-toolbar-title>
          <v-spacer />
          <v-btn variant="text" prepend-icon="mdi-close" @click="showReferenceDialog = false">Закрыть</v-btn>
        </v-toolbar>
        <div class="reference-dialog-body flex-grow-1 position-relative">
          <ClientOnly>
            <GraphFlow
              v-if="showReferenceDialog"
              v-model:nodes="referenceNodes"
              v-model:edges="referenceEdges"
              :palette="dbPalette"
              read-only
              preview-mode
            />
          </ClientOnly>
        </div>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar" timeout="3000" location="bottom right" rounded="pill" color="success">
      {{ snackText }}
    </v-snackbar>
  </div>
</template>

<style scoped>
.constructor-route {
  height: calc(100dvh - var(--v-layout-top, 64px));
  min-height: 0;
  overflow: hidden;
}

.constructor-page,
.constructor-mobile-shell {
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: #f1f5f9;
  color: #334155;
}

.constructor-palette-col {
  width: clamp(340px, 26vw, 460px);
  min-width: 340px;
  min-height: 0;
  overflow: hidden;
  background: #ffffff;
  border-color: rgba(15, 23, 42, 0.1) !important;
}

.constructor-eval-col {
  width: 360px;
  min-width: 360px;
  min-height: 0;
  overflow: hidden;
  background: #ffffff;
  border-color: rgba(15, 23, 42, 0.1) !important;
}

.constructor-canvas {
  min-height: 0;
  overflow: hidden;
  background: #f8fafc;
}

.constructor-left-stack {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.constructor-palette-stack {
  flex: 1 1 0;
  min-height: 0;
  /* Flex container so the palette fills the remaining height via flex rather
     than relying on the child's height:100% resolving against a definite
     parent — the latter resolves late during hydration and briefly lets the
     222-item palette grow with its content (a large load-time shift). */
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.constructor-palette-stack > :deep(.node-palette) {
  flex: 1 1 0;
  min-height: 0;
}

.canvas-fallback {
  background-color: #f8f9fa;
}

.constructor-bottom-nav {
  flex: 0 0 auto;
  background: #ffffff;
  border-top: 1px solid rgba(15, 23, 42, 0.1);
}

.min-w-0 {
  min-width: 0;
}

.reference-dialog-card {
  height: 100%;
  min-height: 0;
  background: #f8fafc;
}

.reference-dialog-body {
  min-height: 0;
  overflow: hidden;
  padding: 12px;
}
</style>
