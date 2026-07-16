<script setup lang="ts">
import type { GraphEvaluationResponse, GraphHintsResponse } from '~/types/api'
import type { FlowNode, NodeDataDto } from '~/types/graph'

interface CategoryOption {
  value: string
  title: string
}

const showFeedbackDialog = defineModel<boolean>('showFeedbackDialog', { required: true })

withDefaults(defineProps<{
  selectedNode: FlowNode | null
  reviewMode: boolean
  evalResult: GraphEvaluationResponse | null
  hintsResult: GraphHintsResponse | null
  categoriesOptions: CategoryOption[]
  feedbackLoading: boolean
  formattedFeedback: string
  metricValue: (value?: number | null) => number
  metricPercent: (value?: number | null) => number
  mobile?: boolean
}>(), {
  mobile: false,
})

const emit = defineEmits<{
  'update-node-data': [field: keyof NodeDataDto, value: string]
  'delete-selected-node': []
  'back-to-editing': []
  'fetch-feedback': []
  'highlight-node': [label: string]
  'clear-highlight': []
}>()

function updateNodeField(field: keyof NodeDataDto, value: string | null): void {
  emit('update-node-data', field, value ?? '')
}
</script>

<template>
  <v-sheet class="evaluation-panel d-flex flex-column h-100 pa-4" :class="{ 'evaluation-panel--mobile': mobile }" elevation="0">
    <v-sheet v-if="selectedNode && !reviewMode" class="panel-section pa-4 mb-3" rounded="lg" elevation="1">
      <h3 class="panel-title text-subtitle-1 font-weight-bold mb-3 d-flex align-center">
        <v-icon icon="mdi-cog-outline" color="primary" size="20" class="mr-1" />
        Параметры узла
      </h3>

      <v-text-field
        :model-value="selectedNode.data.label"
        label="Название узла"
        variant="outlined"
        density="comfortable"
        class="mb-3 select-light"
        @update:model-value="(value) => updateNodeField('label', value)"
      />

      <v-select
        :model-value="selectedNode.data.category"
        :items="categoriesOptions"
        item-title="title"
        item-value="value"
        label="Тип узла"
        variant="outlined"
        density="comfortable"
        class="mb-4 select-light"
        @update:model-value="(value) => updateNodeField('category', value)"
      />

      <template v-if="selectedNode.data.category === 'MEDICATION'">
        <v-text-field
          :model-value="selectedNode.data.dosage"
          label="Дозировка"
          variant="outlined"
          density="comfortable"
          class="mb-3 select-light"
          placeholder="Например: 500 мг"
          @update:model-value="(value) => updateNodeField('dosage', value)"
        />
        <v-text-field
          :model-value="selectedNode.data.route"
          label="Путь введения"
          variant="outlined"
          density="comfortable"
          class="mb-3 select-light"
          placeholder="Например: Внутрь"
          @update:model-value="(value) => updateNodeField('route', value)"
        />
      </template>
      <template v-else-if="selectedNode.data.category === 'LAB_TEST' || selectedNode.data.category === 'INSTRUMENTAL_TEST'">
        <v-text-field
          :model-value="selectedNode.data.expected_value"
          label="Ожидаемое значение/отклонение"
          variant="outlined"
          density="comfortable"
          class="mb-3 select-light"
          placeholder="Например: Повышен"
          @update:model-value="(value) => updateNodeField('expected_value', value)"
        />
      </template>
      <template v-else-if="selectedNode.data.category === 'DIAGNOSIS' || selectedNode.data.category === 'DISEASE'">
        <v-text-field
          :model-value="selectedNode.data.stage"
          label="Стадия / Степень"
          variant="outlined"
          density="comfortable"
          class="mb-3 select-light"
          placeholder="Например: Острая фаза"
          @update:model-value="(value) => updateNodeField('stage', value)"
        />
      </template>

      <v-btn color="error" variant="flat" block rounded="pill" @click="emit('delete-selected-node')">
        <v-icon icon="mdi-delete-outline" size="18" class="mr-1" />
        Удалить узел
      </v-btn>
    </v-sheet>

    <v-sheet
      v-if="reviewMode && evalResult"
      class="panel-section pa-4 mb-3 d-flex flex-column flex-grow-1 overflow-auto"
      rounded="lg"
      elevation="1"
    >
      <div class="d-flex align-center mb-3">
        <h3 class="panel-title text-subtitle-1 font-weight-bold text-success d-flex align-center">
          <v-icon icon="mdi-shield-check-outline" size="20" class="mr-1" />
          Оценка эксперта
        </h3>
        <v-btn size="x-small" color="primary" variant="outlined" rounded="pill" class="ml-auto" @click="emit('back-to-editing')">
          Вернуться
        </v-btn>
      </div>

      <div v-if="evalResult.composite_score != null" class="text-center mb-4">
        <v-progress-circular
          :model-value="(evalResult.composite_score || 0) * 100"
          size="80"
          width="8"
          color="success"
        >
          <span class="text-subtitle-2 font-weight-bold">{{ Math.round((evalResult.composite_score || 0) * 100) }}%</span>
        </v-progress-circular>
        <div class="text-caption mt-1 font-weight-bold text-slate-600">Итоговая оценка</div>
      </div>

      <div class="metrics-grid d-flex justify-space-between mb-4 flex-wrap ga-2">
        <div class="metric-ring text-center">
          <v-progress-circular :model-value="evalResult.precision * 100" size="56" width="5" color="info">
            <span class="text-caption font-weight-bold">{{ Math.round(evalResult.precision * 100) }}%</span>
          </v-progress-circular>
          <div class="text-caption mt-1 font-weight-bold text-slate-600">Точность</div>
        </div>
        <div class="metric-ring text-center">
          <v-progress-circular :model-value="evalResult.recall * 100" size="56" width="5" color="warning">
            <span class="text-caption font-weight-bold">{{ Math.round(evalResult.recall * 100) }}%</span>
          </v-progress-circular>
          <div class="text-caption mt-1 font-weight-bold text-slate-600">Полнота</div>
        </div>
        <div class="metric-ring text-center">
          <v-progress-circular :model-value="(evalResult.edge_f1 ?? evalResult.f1_score) * 100" size="56" width="5" color="primary">
            <span class="text-caption font-weight-bold">{{ Math.round((evalResult.edge_f1 ?? evalResult.f1_score) * 100) }}%</span>
          </v-progress-circular>
          <div class="text-caption mt-1 font-weight-bold text-slate-600">Edge F1</div>
        </div>
        <div v-if="evalResult.node_coverage != null" class="metric-ring text-center">
          <v-progress-circular :model-value="evalResult.node_coverage * 100" size="56" width="5" color="teal">
            <span class="text-caption font-weight-bold">{{ Math.round(evalResult.node_coverage * 100) }}%</span>
          </v-progress-circular>
          <div class="text-caption mt-1 font-weight-bold text-slate-600">Узлы</div>
        </div>
        <div v-if="evalResult.chain_completeness != null" class="metric-ring text-center">
          <v-progress-circular :model-value="evalResult.chain_completeness * 100" size="56" width="5" color="deep-purple">
            <span class="text-caption font-weight-bold">{{ Math.round(evalResult.chain_completeness * 100) }}%</span>
          </v-progress-circular>
          <div class="text-caption mt-1 font-weight-bold text-slate-600">Цепочка</div>
        </div>
        <div v-if="evalResult.weighted_edge_f1 != null" class="metric-ring text-center">
          <v-progress-circular :model-value="metricValue(evalResult.weighted_edge_f1)" size="56" width="5" color="indigo">
            <span class="text-caption font-weight-bold">{{ metricPercent(evalResult.weighted_edge_f1) }}%</span>
          </v-progress-circular>
          <div class="text-caption mt-1 font-weight-bold text-slate-600">Взв. F1</div>
        </div>
        <div v-if="evalResult.category_accuracy != null" class="metric-ring text-center">
          <v-progress-circular :model-value="metricValue(evalResult.category_accuracy)" size="56" width="5" color="cyan">
            <span class="text-caption font-weight-bold">{{ metricPercent(evalResult.category_accuracy) }}%</span>
          </v-progress-circular>
          <div class="text-caption mt-1 font-weight-bold text-slate-600">Категории</div>
        </div>
        <div v-if="evalResult.safety_penalty != null" class="metric-ring text-center">
          <v-progress-circular :model-value="metricValue(evalResult.safety_penalty)" size="56" width="5" color="error">
            <span class="text-caption font-weight-bold">{{ metricPercent(evalResult.safety_penalty) }}%</span>
          </v-progress-circular>
          <div class="text-caption mt-1 font-weight-bold text-slate-600">Риск</div>
        </div>
        <div v-if="evalResult.unsafe_extra_action != null" class="metric-ring text-center">
          <v-progress-circular :model-value="metricValue(evalResult.unsafe_extra_action)" size="56" width="5" color="error">
            <span class="text-caption font-weight-bold">{{ metricPercent(evalResult.unsafe_extra_action) }}%</span>
          </v-progress-circular>
          <div class="text-caption mt-1 font-weight-bold text-slate-600">Лишн. риск</div>
        </div>
        <div v-if="evalResult.missing_critical_action != null" class="metric-ring text-center">
          <v-progress-circular :model-value="metricValue(evalResult.missing_critical_action)" size="56" width="5" color="deep-orange">
            <span class="text-caption font-weight-bold">{{ metricPercent(evalResult.missing_critical_action) }}%</span>
          </v-progress-circular>
          <div class="text-caption mt-1 font-weight-bold text-slate-600">Проп. крит.</div>
        </div>
        <div v-if="evalResult.diagnostic_evidence_gap != null" class="metric-ring text-center">
          <v-progress-circular :model-value="metricValue(evalResult.diagnostic_evidence_gap)" size="56" width="5" color="amber">
            <span class="text-caption font-weight-bold">{{ metricPercent(evalResult.diagnostic_evidence_gap) }}%</span>
          </v-progress-circular>
          <div class="text-caption mt-1 font-weight-bold text-slate-600">Диагн. опора</div>
        </div>
      </div>

      <div v-if="evalResult.clinical_connectivity_gap != null" class="ai-commentary pa-3 rounded border mb-3 text-body-2">
        <div class="d-flex align-center justify-space-between">
          <span class="font-weight-bold">Разрывы клинической цепочки</span>
          <span class="font-weight-bold text-deep-orange">{{ metricPercent(evalResult.clinical_connectivity_gap) }}%</span>
        </div>
      </div>

      <div class="ai-commentary pa-3 rounded border mb-4 text-body-2">
        {{ evalResult.message }}
      </div>

      <div v-if="evalResult.score_caps?.length" class="mb-3">
        <div class="text-caption font-weight-bold text-slate-600 mb-1">Клинические ограничения оценки:</div>
        <div class="feedback-list">
          <div
            v-for="(cap, index) in evalResult.score_caps"
            :key="'cap' + index"
            class="feedback-item incorrect-item pa-2 mb-1 rounded border text-caption text-slate-800"
          >
            <v-icon icon="mdi-gauge-low" color="error" size="14" class="mr-1" />
            <strong>{{ cap.code }}</strong>
            <span class="text-slate-500 ml-1">до {{ Math.round(Number(cap.cap || 0) * 100) }}%</span>
          </div>
        </div>
      </div>

      <v-btn block color="primary" variant="tonal" rounded="pill" class="mb-4" :loading="feedbackLoading" @click="emit('fetch-feedback')">
        <v-icon icon="mdi-robot-outline" size="18" class="mr-1" />
        Подробный отчет ИИ
      </v-btn>

      <div v-if="evalResult.missing_edges?.length" class="mb-3">
        <div class="text-caption font-weight-bold text-slate-600 mb-1">Пропущенные клинические связи:</div>
        <div class="feedback-list">
          <div
            v-for="(edge, index) in evalResult.missing_edges"
            :key="'m' + index"
            class="feedback-item pa-2 mb-1 rounded border text-caption text-slate-800"
            @mouseenter="emit('highlight-node', edge.source)"
            @mouseleave="emit('clear-highlight')"
          >
            <v-icon icon="mdi-alert-circle-outline" color="warning" size="14" class="mr-1" />
            <strong>{{ edge.source }}</strong> &rarr; <strong>{{ edge.target }}</strong>
            <span class="text-slate-500 ml-1">({{ edge.relation }})</span>
          </div>
        </div>
      </div>

      <div v-if="evalResult.missing_nodes?.length" class="mb-3">
        <div class="text-caption font-weight-bold text-slate-600 mb-1">Пропущенные клинические понятия:</div>
        <div class="feedback-list">
          <div
            v-for="(nodeLabel, index) in evalResult.missing_nodes"
            :key="'mn' + index"
            class="feedback-item pa-2 mb-1 rounded border text-caption text-slate-800"
            @mouseenter="emit('highlight-node', nodeLabel)"
            @mouseleave="emit('clear-highlight')"
          >
            <v-icon icon="mdi-vector-point-minus" color="warning" size="14" class="mr-1" />
            <strong>{{ nodeLabel }}</strong>
          </div>
        </div>
      </div>

      <div v-if="evalResult.safety_findings?.length" class="mb-3">
        <div class="text-caption font-weight-bold text-slate-600 mb-1">Клинически опасные ошибки:</div>
        <div class="feedback-list">
          <div
            v-for="(finding, index) in evalResult.safety_findings"
            :key="'sf' + index"
            class="feedback-item incorrect-item pa-2 mb-1 rounded border text-caption text-slate-800"
            @mouseenter="emit('highlight-node', finding.source)"
            @mouseleave="emit('clear-highlight')"
          >
            <v-icon icon="mdi-alert-octagon-outline" color="error" size="14" class="mr-1" />
            <strong>{{ finding.source }}</strong> &rarr; <strong>{{ finding.target }}</strong>
            <span class="text-slate-500 ml-1">({{ finding.relation }})</span>
          </div>
        </div>
      </div>

      <div v-if="evalResult.diagnostic_evidence_findings?.length" class="mb-3">
        <div class="text-caption font-weight-bold text-slate-600 mb-1">Пропущенная диагностическая опора:</div>
        <div class="feedback-list">
          <div
            v-for="(finding, index) in evalResult.diagnostic_evidence_findings"
            :key="'df' + index"
            class="feedback-item pa-2 mb-1 rounded border text-caption text-slate-800"
            @mouseenter="emit('highlight-node', finding.source)"
            @mouseleave="emit('clear-highlight')"
          >
            <v-icon icon="mdi-stethoscope" color="warning" size="14" class="mr-1" />
            <strong>{{ finding.source }}</strong> &rarr; <strong>{{ finding.target }}</strong>
            <span class="text-slate-500 ml-1">({{ finding.relation }})</span>
          </div>
        </div>
      </div>

      <div v-if="evalResult.clinical_connectivity_findings?.length" class="mb-3">
        <div class="text-caption font-weight-bold text-slate-600 mb-1">Разрывы клинической цепочки:</div>
        <div class="feedback-list">
          <div
            v-for="(finding, index) in evalResult.clinical_connectivity_findings"
            :key="'cf' + index"
            class="feedback-item incorrect-item pa-2 mb-1 rounded border text-caption text-slate-800"
            @mouseenter="emit('highlight-node', finding.node)"
            @mouseleave="emit('clear-highlight')"
          >
            <v-icon icon="mdi-vector-link-off" color="deep-orange" size="14" class="mr-1" />
            <strong>{{ finding.node }}</strong>
            <span class="text-slate-500 ml-1">({{ finding.kind }})</span>
          </div>
        </div>
      </div>

      <div v-if="evalResult.incorrect_edges?.length" class="mb-3">
        <div class="text-caption font-weight-bold text-slate-600 mb-1">Неверные клинические связи:</div>
        <div class="feedback-list">
          <div
            v-for="(edge, index) in evalResult.incorrect_edges"
            :key="'x' + index"
            class="feedback-item incorrect-item pa-2 mb-1 rounded border text-caption text-slate-800"
          >
            <v-icon icon="mdi-close-circle-outline" color="error" size="14" class="mr-1" />
            <strong>{{ edge.source }}</strong> &rarr; <strong>{{ edge.target }}</strong>
            <span class="text-slate-500 ml-1">({{ edge.relation }})</span>
          </div>
        </div>
      </div>
    </v-sheet>

    <v-sheet v-if="hintsResult" class="panel-section panel-section--hints pa-4 mb-3" rounded="lg" elevation="1">
      <h3 class="panel-title text-subtitle-1 font-weight-bold mb-2 text-slate-800 d-flex align-center">
        <v-icon icon="mdi-lightbulb-on" color="warning" size="20" class="mr-1" />
        Подсказки
      </h3>
      <p class="text-caption text-slate-700 mb-2">{{ hintsResult.summary }}</p>
      <ul class="pl-4 text-slate-700">
        <li v-for="(hint, index) in hintsResult.hints" :key="'h' + index" class="text-caption mb-1">
          {{ hint.text }}
        </li>
      </ul>
    </v-sheet>

    <v-sheet
      v-if="!selectedNode && !reviewMode && !hintsResult"
      class="panel-section pa-4 d-flex align-center justify-center flex-grow-1 text-center"
      rounded="lg"
      elevation="1"
    >
      <div>
        <v-icon icon="mdi-cursor-default-click-outline" color="primary" size="36" class="mb-2 opacity-80" />
        <p class="text-caption text-slate-600 font-weight-bold">
          Выберите любой узел на холсте, чтобы настроить его свойства, или нажмите "Проверить решение" для получения экспертной оценки.
        </p>
      </div>
    </v-sheet>

    <v-dialog v-model="showFeedbackDialog" max-width="750">
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center bg-primary text-white px-4 py-3">
          <v-icon icon="mdi-robot-outline" size="20" class="mr-2" />
          Подробный отчет ИИ
          <v-spacer />
          <v-btn
            icon="mdi-close"
            variant="text"
            color="white"
            aria-label="Закрыть подробный отчет ИИ"
            @click="showFeedbackDialog = false"
          />
        </v-card-title>
        <v-card-text class="pa-5 markdown-body">
          <div v-if="feedbackLoading" class="text-center py-5">
            <v-progress-circular indeterminate color="primary" size="48" class="mb-3" />
            <div class="text-slate-600">ИИ анализирует ваше решение...</div>
          </div>
          <!-- Content is rendered by renderSafeMarkdown with raw HTML disabled. -->
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div v-else v-html="formattedFeedback" />
        </v-card-text>
      </v-card>
    </v-dialog>
  </v-sheet>
</template>

<style scoped>
.evaluation-panel {
  min-height: 0;
  overflow-y: auto;
  background: #ffffff !important;
  scrollbar-width: thin;
}

.evaluation-panel--mobile {
  max-height: 82dvh;
  border-radius: 16px 16px 0 0;
}

.panel-section {
  background: #ffffff !important;
  border: 1px solid rgba(15, 23, 42, 0.1) !important;
  box-shadow: 0 4px 18px rgba(15, 23, 42, 0.03) !important;
}

.panel-section--hints {
  background-color: #f1f5f9 !important;
}

.panel-title {
  color: #0f172a !important;
}

.select-light :deep(.v-field) {
  border-radius: 8px;
  background-color: #f8fafc !important;
}

.ai-commentary {
  background-color: #f0f9ff;
  border-color: #bae6fd;
  color: #0369a1;
  line-height: 1.4;
}

.feedback-item {
  background-color: #fef9c3;
  border-color: #fef08a;
  transition: background-color 0.2s ease, transform 0.2s ease;
  cursor: pointer;
}

.feedback-item:hover {
  background-color: #fef08a;
  transform: translateX(4px);
}

.incorrect-item {
  background-color: #fee2e2;
  border-color: #fecaca;
}

.incorrect-item:hover {
  background-color: #fecaca;
}

.markdown-body {
  max-height: 70vh;
  overflow-y: auto;
  font-family: inherit;
  line-height: 1.6;
  color: #334155;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  color: #0f172a;
  margin-top: 1.5rem;
  margin-bottom: 0.5rem;
}

.markdown-body :deep(p) {
  margin-bottom: 1rem;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 2rem;
  margin-bottom: 1rem;
}

.markdown-body :deep(strong) {
  font-weight: 600;
  color: #1e293b;
}
</style>
