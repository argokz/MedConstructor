<script setup lang="ts">
import type { BenchmarksData } from '~/composables/useBenchmarksData'
import type { BenchmarksFormatter } from '~/composables/useBenchmarksFormatter'

const props = defineProps<{
  data: BenchmarksData
  ui: BenchmarksFormatter
}>()

const validationTab = ref('cardiology')

const {
  analyzeExpertCsv,
  auditGeneration,
  busy,
  cardiologyCaseCount,
  cardiologyExpertCount,
  cardiologyOnlyDisagreements,
  cardiologyOnlyFailed,
  cardiologySeed,
  cardiologyUseEmbeddings,
  demoImportRefreshTimestamps,
  details,
  downloadArtifact,
  expertAnalyzeDelimiter,
  expertDelimiter,
  expertFile,
  expertOnlyDisagreements,
  expertShuffle,
  expertShuffleSeed,
  generationAuditLimit,
  importCardiologyDemo,
  runCardiologySyntheticBenchmark,
  summary,
  exportExpertPackage,
  exportTables,
} = props.data
const {
  baselineComparisonHeaders,
  cardiologyBaselineRows,
  cardiologyExpertByExpertRows,
  cardiologyExpertByPatternRows,
  cardiologyExpertItemRows,
  cardiologyExpertRatingHeaders,
  cardiologyGraphRows,
  cardiologyMetricTiles,
  cardiologyPatternRows,
  cardiologyPatternSummaryHeaders,
  cardiologyRatingRows,
  cardiologyRealBaselineRows,
  cardiologyRecommendationHeaders,
  cardiologyRecommendationRows,
  cardiologyReferenceQualityRows,
  cardiologyTaskHeaders,
  cardiologyTaskRows,
  cleanText,
  compactValue,
  csvArtifacts,
  expertBaselineRows,
  expertByExpertHeaders,
  expertByExpertRows,
  expertItemHeaders,
  expertItemRows,
  expertMetricTiles,
  expertPatternHeaders,
  expertPatternRows,
  expertSkippedRows,
  formatDate,
  formatNumber,
  formatPercent,
  formatSize,
  generationHeaders,
  generationRows,
  graphQualityHeaders,
  graphResultHeaders,
  historyHeaders,
  historyRows,
  problemHeaders,
  problemRows,
  problemSummary,
  reportArtifact,
  runTypeLabel,
  severityColor,
  severityText,
  shortText,
  skippedRowsHeaders,
  patternLabel,
  modelLabel,
  yesNoText,
} = props.ui
</script>

<template>
  <div>
    <v-tabs v-model="validationTab" bg-color="surface" class="border rounded-tabs mb-4" density="comfortable">
      <v-tab value="cardiology" prepend-icon="mdi-heart-pulse">Кардиология</v-tab>
      <v-tab value="expert" prepend-icon="mdi-account-check-outline">Эксперты</v-tab>
      <v-tab value="problems" prepend-icon="mdi-alert-decagram-outline">Проблемы</v-tab>
    </v-tabs>

    <v-window v-model="validationTab">
      <v-window-item value="cardiology">
          <v-row>
            <v-col cols="12" lg="4">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Кардиологический набор для проверки</v-card-title>
                <v-card-text class="d-flex flex-column ga-3">
                  <v-text-field
                    v-model.number="cardiologyCaseCount"
                    label="Количество клинических задач"
                    type="number"
                    :min="1"
                    :max="12"
                    density="compact"
                    variant="outlined"
                  />
                  <v-text-field
                    v-model.number="cardiologyExpertCount"
                    label="Количество экспертных оценок"
                    type="number"
                    :min="1"
                    :max="100"
                    density="compact"
                    variant="outlined"
                  />
                  <v-text-field
                    v-model.number="cardiologySeed"
                    label="Зерно генерации"
                    type="number"
                    density="compact"
                    variant="outlined"
                  />
                  <v-switch
                    v-model="cardiologyUseEmbeddings"
                    label="Семантические embeddings"
                    color="primary"
                    density="compact"
                    hide-details
                  />
                  <v-switch
                    v-model="demoImportRefreshTimestamps"
                    label="Обновить время демо-сдач"
                    color="primary"
                    density="compact"
                    hide-details
                  />
                </v-card-text>
                <v-card-actions class="px-4 pb-4">
                  <v-btn
                    color="primary"
                    variant="flat"
                    :loading="busy === 'cardiology-run'"
                    prepend-icon="mdi-play"
                    @click="runCardiologySyntheticBenchmark"
                  >
                    Запустить
                  </v-btn>
                  <v-btn
                    color="success"
                    variant="tonal"
                    :disabled="!summary?.cardiology?.summary"
                    :loading="busy === 'cardiology-demo-import'"
                    prepend-icon="mdi-account-school-outline"
                    @click="importCardiologyDemo"
                  >
                    В демо-кабинеты
                  </v-btn>
                  <v-spacer />
                  <v-chip size="small" color="info" variant="tonal">
                    {{ formatDate(summary?.cardiology?.generated_at || null) }}
                  </v-chip>
                </v-card-actions>
              </v-card>
            </v-col>
        
            <v-col cols="12" lg="8">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Метрики кардиологического набора</v-card-title>
                <v-card-text>
                  <v-alert type="info" variant="tonal" density="compact" rounded="lg" class="mb-3">
                    Синтетическая (проверочная) валидация: оценки смоделированы, а не получены от реальных экспертов.
                    Реальная слепая валидация ведётся отдельно (панель кардиологов, 36 вариантов); её результаты появятся после сбора реальных оценок.
                  </v-alert>
                  <div class="metric-grid wide mb-4">
                    <v-tooltip
                      v-for="metric in cardiologyMetricTiles"
                      :key="metric.label"
                      :text="metric.hint"
                      location="top"
                    >
                      <template #activator="{ props }">
                    <MetricCard v-bind="props" :title="metric.label" :value="metric.value" :color="metric.tone" />
                      </template>
                    </v-tooltip>
                  </div>
                  <div class="d-flex flex-wrap ga-2">
                    <v-chip size="small" color="primary" variant="tonal">
                      Оценок {{ summary?.cardiology?.summary?.rating_count ?? '—' }}
                    </v-chip>
                    <v-chip size="small" color="success" variant="tonal">
                      Эталоны приняты {{ formatPercent(summary?.cardiology?.summary?.reference_accepted_rate) }}
                    </v-chip>
                    <v-chip size="small" color="warning" variant="tonal">
                      Средний штраф безопасности {{ formatNumber(summary?.cardiology?.summary?.system_avg_safety_penalty) }}
                    </v-chip>
                    <v-chip size="small" color="info" variant="tonal">
                      Время расчета {{ formatNumber(summary?.cardiology?.summary?.total_runtime_ms, 1) }} мс
                    </v-chip>
                  </div>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Клинические задачи набора</v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="cardiologyTaskHeaders"
                    :items="cardiologyTaskRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="8"
                  >
                    <template #item.task_quality_score="{ item }">{{ formatNumber(item.task_quality_score) }}</template>
                    <template #item.task_quality_accepted="{ item }">
                      <StatusChip :status="item.task_quality_accepted ? 'accepted' : 'failed'" :text="yesNoText(item.task_quality_accepted)" />
                    </template>
                    <template #item.protocol_focus="{ item }">
                      <ExpandableText
                        :text="cleanText(item.protocol_focus)"
                        title="Клинический фокус задания"
                        :lines="2"
                        :min-length="90"
                      />
                    </template>
                    <template #item.expected_sections="{ item }">{{ compactValue(item.expected_sections, 5) }}</template>
                    <template #item.red_flags="{ item }">{{ compactValue(item.red_flags, 3) }}</template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12" lg="6">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Типовые ошибки и распознавание</v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="cardiologyPatternSummaryHeaders"
                    :items="cardiologyPatternRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="10"
                  >
                    <template #item.expected_pattern="{ item }">{{ patternLabel(item.expected_pattern) }}</template>
                    <template #item.mean_model_score="{ item }">{{ formatNumber(item.mean_model_score) }}</template>
                    <template #item.mean_expert_score="{ item }">{{ formatNumber(item.mean_expert_score) }}</template>
                    <template #item.mean_gap_model_minus_expert="{ item }">
                      <v-chip
                        size="small"
                        :color="Math.abs(Number(item.mean_gap_model_minus_expert || 0)) >= 0.2 ? 'warning' : 'success'"
                        variant="tonal"
                      >
                        {{ formatNumber(item.mean_gap_model_minus_expert) }}
                      </v-chip>
                    </template>
                    <template #item.pattern_pass_rate="{ item }">{{ formatPercent(item.pattern_pass_rate) }}</template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12" lg="6">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Качество эталонных графов</v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="graphQualityHeaders"
                    :items="cardiologyReferenceQualityRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="8"
                  >
                    <template #item.accepted="{ item }">
                      <StatusChip :status="item.accepted ? 'accepted' : 'failed'" :text="yesNoText(item.accepted)" />
                    </template>
                    <template #item.quality_score="{ item }">{{ formatNumber(item.quality_score) }}</template>
                    <template #item.warnings="{ item }">{{ shortText(item.warnings, 120) }}</template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12" lg="6">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Сравнение методов оценки</v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="baselineComparisonHeaders"
                    :items="cardiologyBaselineRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="10"
                  >
                    <template #item.model="{ item }">{{ modelLabel(item.model) }}</template>
                    <template #item.spearman="{ item }">{{ formatNumber(item.spearman) }}</template>
                    <template #item.mae="{ item }">{{ formatNumber(item.mae) }}</template>
                    <template #item.delta_spearman_vs_composite="{ item }">{{ formatNumber(item.delta_spearman_vs_composite) }}</template>
                    <template #item.delta_mae_vs_composite="{ item }">{{ formatNumber(item.delta_mae_vs_composite) }}</template>
                    <template #item.description="{ item }">{{ shortText(item.description, 160) }}</template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12" lg="6">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Сравнение с оценками кардиологов</v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="baselineComparisonHeaders"
                    :items="cardiologyRealBaselineRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="10"
                  >
                    <template #item.model="{ item }">{{ modelLabel(item.model) }}</template>
                    <template #item.spearman="{ item }">{{ formatNumber(item.spearman) }}</template>
                    <template #item.mae="{ item }">{{ formatNumber(item.mae) }}</template>
                    <template #item.delta_spearman_vs_composite="{ item }">{{ formatNumber(item.delta_spearman_vs_composite) }}</template>
                    <template #item.delta_mae_vs_composite="{ item }">{{ formatNumber(item.delta_mae_vs_composite) }}</template>
                    <template #item.description="{ item }">{{ shortText(item.description, 160) }}</template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1 d-flex align-center flex-wrap ga-3">
                  Варианты студенческих решений
                  <v-spacer />
                  <v-switch
                    v-model="cardiologyOnlyFailed"
                    label="Только проблемные"
                    color="warning"
                    density="compact"
                    hide-details
                  />
                </v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="graphResultHeaders"
                    :items="cardiologyGraphRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="10"
                  >
                    <template #item.pattern_passed="{ item }">
                      <StatusChip :status="item.pattern_passed ? 'accepted' : 'failed'" :text="item.pattern_passed ? 'Распознано' : 'Не распознано'" />
                    </template>
                    <template #item.expected_pattern="{ item }">{{ patternLabel(item.expected_pattern) }}</template>
                    <template #item.composite_score="{ item }">{{ formatNumber(item.composite_score) }}</template>
                    <template #item.weighted_edge_f1="{ item }">{{ formatNumber(item.weighted_edge_f1) }}</template>
                    <template #item.node_coverage="{ item }">{{ formatNumber(item.node_coverage) }}</template>
                    <template #item.category_accuracy="{ item }">{{ formatNumber(item.category_accuracy) }}</template>
                    <template #item.directed_path_completeness="{ item }">{{ formatNumber(item.directed_path_completeness) }}</template>
                    <template #item.safety_penalty="{ item }">{{ formatNumber(item.safety_penalty) }}</template>
                    <template #item.safety_findings="{ item }">
                      <ExpandableText
                        :text="cleanText(item.safety_findings)"
                        title="Комментарий по безопасности"
                        :lines="2"
                        :min-length="90"
                      />
                    </template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1 d-flex align-center flex-wrap ga-3">
                  Рекомендации по расхождениям
                  <v-spacer />
                  <v-switch
                    v-model="cardiologyOnlyDisagreements"
                    label="Расхождение ≥ 0.20"
                    color="warning"
                    density="compact"
                    hide-details
                  />
                </v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="cardiologyRecommendationHeaders"
                    :items="cardiologyRecommendationRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="10"
                  >
                    <template #item.expected_pattern="{ item }">{{ patternLabel(item.expected_pattern) }}</template>
                    <template #item.model_score="{ item }">{{ formatNumber(item.model_score) }}</template>
                    <template #item.expert_mean_score="{ item }">{{ formatNumber(item.expert_mean_score) }}</template>
                    <template #item.score_gap_model_minus_expert="{ item }">
                      <v-chip
                        size="small"
                        :color="Math.abs(Number(item.score_gap_model_minus_expert || 0)) >= 0.2 ? 'warning' : 'success'"
                        variant="tonal"
                      >
                        {{ formatNumber(item.score_gap_model_minus_expert) }}
                      </v-chip>
                    </template>
                    <template #item.system_recommendation="{ item }">
                      <ExpandableText
                        :text="cleanText(item.system_recommendation)"
                        title="Рекомендация системы"
                        :lines="3"
                        :min-length="120"
                      />
                    </template>
                    <template #item.safety_findings="{ item }">
                      <ExpandableText
                        :text="cleanText(item.safety_findings)"
                        title="Риски решения"
                        :lines="2"
                        :min-length="90"
                      />
                    </template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12" lg="6">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Решения с экспертной оценкой</v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="expertItemHeaders"
                    :items="cardiologyExpertItemRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="10"
                  >
                    <template #item.expected_pattern="{ item }">{{ patternLabel(item.expected_pattern) }}</template>
                    <template #item.model_score="{ item }">{{ formatNumber(item.model_score) }}</template>
                    <template #item.expert_mean_score="{ item }">{{ formatNumber(item.expert_mean_score) }}</template>
                    <template #item.score_gap_model_minus_expert="{ item }">{{ formatNumber(item.score_gap_model_minus_expert) }}</template>
                    <template #item.expert_score_std="{ item }">{{ formatNumber(item.expert_score_std) }}</template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12" lg="6">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Согласие по экспертам</v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="expertByExpertHeaders"
                    :items="cardiologyExpertByExpertRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="10"
                  >
                    <template #item.pearson="{ item }">{{ formatNumber(item.pearson) }}</template>
                    <template #item.model="{ item }">{{ modelLabel(item.model) }}</template>
                    <template #item.spearman="{ item }">{{ formatNumber(item.spearman) }}</template>
                    <template #item.mae="{ item }">{{ formatNumber(item.mae) }}</template>
                    <template #item.rmse="{ item }">{{ formatNumber(item.rmse) }}</template>
                    <template #item.bias="{ item }">{{ formatNumber(item.bias) }}</template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12" lg="6">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Эксперты по типам ошибок</v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="expertPatternHeaders"
                    :items="cardiologyExpertByPatternRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="10"
                  >
                    <template #item.expected_pattern="{ item }">{{ patternLabel(item.expected_pattern) }}</template>
                    <template #item.pearson="{ item }">{{ formatNumber(item.pearson) }}</template>
                    <template #item.model="{ item }">{{ modelLabel(item.model) }}</template>
                    <template #item.spearman="{ item }">{{ formatNumber(item.spearman) }}</template>
                    <template #item.mae="{ item }">{{ formatNumber(item.mae) }}</template>
                    <template #item.rmse="{ item }">{{ formatNumber(item.rmse) }}</template>
                    <template #item.bias="{ item }">{{ formatNumber(item.bias) }}</template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12" lg="6">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Примеры экспертных оценок</v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="cardiologyExpertRatingHeaders"
                    :items="cardiologyRatingRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="10"
                  >
                    <template #item.expected_pattern="{ item }">{{ patternLabel(item.expected_pattern) }}</template>
                    <template #item.model_score="{ item }">{{ formatNumber(item.model_score) }}</template>
                    <template #item.expert_score="{ item }">{{ formatNumber(item.expert_score) }}</template>
                    <template #item.confidence="{ item }">{{ formatNumber(item.confidence) }}</template>
                    <template #item.expert_comment="{ item }">{{ shortText(item.expert_comment, 160) }}</template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
      </v-window-item>

      <v-window-item value="expert">
          <v-row>
            <v-col cols="12" lg="4">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Экспорт пакета</v-card-title>
                <v-card-text class="d-flex flex-column ga-3">
                  <v-switch
                    v-model="expertShuffle"
                    label="Перемешать задания"
                    color="primary"
                    density="compact"
                    hide-details
                  />
                  <v-text-field
                    v-model.number="expertShuffleSeed"
                    label="Зерно перемешивания"
                    type="number"
                    density="compact"
                    variant="outlined"
                  />
                  <v-select
                    v-model="expertDelimiter"
                    label="Разделитель CSV"
                    :items="[
                      { title: 'Запятая', value: ',' },
                      { title: 'Точка с запятой', value: ';' },
                    ]"
                    density="compact"
                    variant="outlined"
                  />
                </v-card-text>
                <v-card-actions class="px-4 pb-4">
                  <v-btn
                    color="primary"
                    variant="flat"
                    :loading="busy === 'expert-export'"
                    prepend-icon="mdi-package-variant-closed"
                    @click="exportExpertPackage"
                  >
                    Сформировать пакет
                  </v-btn>
                </v-card-actions>
              </v-card>
            </v-col>
        
            <v-col cols="12" lg="4">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Анализ оценок</v-card-title>
                <v-card-text class="d-flex flex-column ga-3">
                  <v-file-input
                    v-model="expertFile"
                    label="CSV файл"
                    accept=".csv,text/csv"
                    prepend-icon="mdi-paperclip"
                    density="compact"
                    variant="outlined"
                    clearable
                  />
                  <v-select
                    v-model="expertAnalyzeDelimiter"
                    label="Разделитель"
                    :items="[
                      { title: 'Автоматически', value: 'auto' },
                      { title: 'Запятая', value: ',' },
                      { title: 'Точка с запятой', value: ';' },
                    ]"
                    density="compact"
                    variant="outlined"
                  />
                </v-card-text>
                <v-card-actions class="px-4 pb-4">
                  <v-btn
                    color="success"
                    variant="flat"
                    :loading="busy === 'expert-analyze'"
                    prepend-icon="mdi-chart-scatter-plot"
                    @click="analyzeExpertCsv"
                  >
                    Проанализировать
                  </v-btn>
                </v-card-actions>
              </v-card>
            </v-col>
        
            <v-col cols="12" lg="4">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Корреляции</v-card-title>
                <v-card-text>
                  <div class="metric-grid">
                    <v-tooltip
                      v-for="metric in expertMetricTiles"
                      :key="metric.label"
                      :text="metric.hint"
                      :aria-label="metric.hint"
                      location="top"
                    >
                      <template #activator="{ props }">
                        <MetricCard v-bind="props" :title="metric.label" :value="metric.value" :color="metric.tone" />
                      </template>
                    </v-tooltip>
                  </div>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Сравнение методов оценки</v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="baselineComparisonHeaders"
                    :items="expertBaselineRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="10"
                  >
                    <template #item.model="{ item }">{{ modelLabel(item.model) }}</template>
                    <template #item.spearman="{ item }">{{ formatNumber(item.spearman) }}</template>
                    <template #item.mae="{ item }">{{ formatNumber(item.mae) }}</template>
                    <template #item.delta_spearman_vs_composite="{ item }">{{ formatNumber(item.delta_spearman_vs_composite) }}</template>
                    <template #item.delta_mae_vs_composite="{ item }">{{ formatNumber(item.delta_mae_vs_composite) }}</template>
                    <template #item.description="{ item }">{{ shortText(item.description, 180) }}</template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1 d-flex align-center flex-wrap ga-3">
                  Оценки по решениям
                  <v-spacer />
                  <v-switch
                    v-model="expertOnlyDisagreements"
                    label="Расхождение ≥ 0.15"
                    color="warning"
                    density="compact"
                    hide-details
                  />
                </v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="expertItemHeaders"
                    :items="expertItemRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="10"
                  >
                    <template #item.expected_pattern="{ item }">{{ patternLabel(item.expected_pattern) }}</template>
                    <template #item.model_score="{ item }">{{ formatNumber(item.model_score) }}</template>
                    <template #item.expert_mean_score="{ item }">{{ formatNumber(item.expert_mean_score) }}</template>
                    <template #item.score_gap_model_minus_expert="{ item }">
                      <v-chip
                        size="small"
                        :color="Math.abs(Number(item.score_gap_model_minus_expert || 0)) >= 0.15 ? 'warning' : 'success'"
                        variant="tonal"
                      >
                        {{ formatNumber(item.score_gap_model_minus_expert) }}
                      </v-chip>
                    </template>
                    <template #item.expert_score_std="{ item }">{{ formatNumber(item.expert_score_std) }}</template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12" lg="6">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Корреляция по паттернам</v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="expertPatternHeaders"
                    :items="expertPatternRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="10"
                  >
                    <template #item.expected_pattern="{ item }">{{ patternLabel(item.expected_pattern) }}</template>
                    <template #item.pearson="{ item }">{{ formatNumber(item.pearson) }}</template>
                    <template #item.model="{ item }">{{ modelLabel(item.model) }}</template>
                    <template #item.spearman="{ item }">{{ formatNumber(item.spearman) }}</template>
                    <template #item.mae="{ item }">{{ formatNumber(item.mae) }}</template>
                    <template #item.rmse="{ item }">{{ formatNumber(item.rmse) }}</template>
                    <template #item.bias="{ item }">{{ formatNumber(item.bias) }}</template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12" lg="6">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Корреляция по экспертам</v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="expertByExpertHeaders"
                    :items="expertByExpertRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="10"
                  >
                    <template #item.pearson="{ item }">{{ formatNumber(item.pearson) }}</template>
                    <template #item.model="{ item }">{{ modelLabel(item.model) }}</template>
                    <template #item.spearman="{ item }">{{ formatNumber(item.spearman) }}</template>
                    <template #item.mae="{ item }">{{ formatNumber(item.mae) }}</template>
                    <template #item.rmse="{ item }">{{ formatNumber(item.rmse) }}</template>
                    <template #item.bias="{ item }">{{ formatNumber(item.bias) }}</template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Пропущенные строки CSV</v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="skippedRowsHeaders"
                    :items="expertSkippedRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="10"
                  />
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
      </v-window-item>

      <v-window-item value="problems">
          <v-row>
            <v-col cols="12" lg="4">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Слабые места</v-card-title>
                <v-card-text>
                  <div class="metric-grid">
                    <v-sheet class="metric-tile tone-error">
                      <div class="text-caption text-medium-emphasis">Критично</div>
                      <div class="text-h6 font-weight-bold">{{ problemSummary.critical }}</div>
                    </v-sheet>
                    <v-sheet class="metric-tile tone-warning">
                      <div class="text-caption text-medium-emphasis">Предупреждения</div>
                      <div class="text-h6 font-weight-bold">{{ problemSummary.warning }}</div>
                    </v-sheet>
                    <v-sheet class="metric-tile tone-info">
                      <div class="text-caption text-medium-emphasis">Информация</div>
                      <div class="text-h6 font-weight-bold">{{ problemSummary.info }}</div>
                    </v-sheet>
                    <v-sheet class="metric-tile tone-primary">
                      <div class="text-caption text-medium-emphasis">Всего</div>
                      <div class="text-h6 font-weight-bold">{{ problemSummary.total }}</div>
                    </v-sheet>
                  </div>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12" lg="4">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Аудит заданий</v-card-title>
                <v-card-text class="d-flex flex-column ga-3">
                  <v-text-field
                    v-model.number="generationAuditLimit"
                    label="Лимит записей аудита"
                    type="number"
                    :min="1"
                    :max="1000"
                    density="compact"
                    variant="outlined"
                  />
                  <div class="d-flex flex-wrap ga-2">
                    <v-chip size="small" color="primary" variant="tonal">
                      N {{ details?.generation?.summary?.n ?? '—' }}
                    </v-chip>
                    <v-chip size="small" color="success" variant="tonal">
                      Принято {{ formatPercent(details?.generation?.summary?.accepted_rate) }}
                    </v-chip>
                    <v-chip size="small" color="warning" variant="tonal">
                      Замечания {{ formatPercent(details?.generation?.summary?.warning_rate) }}
                    </v-chip>
                    <v-chip size="small" color="warning" variant="tonal">
                      Замечания к заданиям {{ formatPercent(details?.generation?.summary?.assignment_warning_rate) }}
                    </v-chip>
                    <v-chip size="small" color="info" variant="tonal">
                      Качество заданий {{ formatNumber(details?.generation?.summary?.avg_assignment_quality_score) }}
                    </v-chip>
                  </div>
                </v-card-text>
                <v-card-actions class="px-4 pb-4">
                  <v-btn
                    color="primary"
                    variant="flat"
                    :loading="busy === 'generation-audit'"
                    prepend-icon="mdi-clipboard-check-outline"
                    @click="auditGeneration"
                  >
                    Запустить аудит
                  </v-btn>
                </v-card-actions>
              </v-card>
            </v-col>
        
            <v-col cols="12" lg="4">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Отчёт</v-card-title>
                <v-card-text class="d-flex flex-column ga-2">
                  <v-chip size="small" color="secondary" variant="tonal">
                    CSV: {{ csvArtifacts.length }}
                  </v-chip>
                  <v-chip size="small" :color="reportArtifact?.exists ? 'success' : 'warning'" variant="tonal">
                    XLSX: {{ reportArtifact?.exists ? formatSize(reportArtifact.size_bytes) : '—' }}
                  </v-chip>
                </v-card-text>
                <v-card-actions class="px-4 pb-4">
                  <v-btn
                    color="secondary"
                    variant="flat"
                    :loading="busy === 'tables-export'"
                    prepend-icon="mdi-file-excel-outline"
                    @click="exportTables"
                  >
                    Пересобрать
                  </v-btn>
                  <v-spacer />
                  <v-btn
                    color="success"
                    variant="outlined"
                    :disabled="!reportArtifact?.exists"
                    :loading="busy === 'download-benchmark_report_latest.xlsx'"
                    icon="mdi-download"
                    aria-label="Скачать XLSX-отчет"
                    @click="downloadArtifact('benchmark_report_latest.xlsx')"
                  />
                </v-card-actions>
              </v-card>
            </v-col>
        
            <v-col cols="12">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Автоматически найденные проблемы</v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="problemHeaders"
                    :items="problemRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="15"
                  >
                    <template #item.severity="{ item }">
                      <v-chip size="small" :color="severityColor(item.severity)" variant="tonal">
                        {{ severityText(item.severity) }}
                      </v-chip>
                    </template>
                    <template #item.reason="{ item }">
                      <ExpandableText :text="cleanText(item.reason)" title="Причина проблемы" :lines="2" :min-length="90" />
                    </template>
                    <template #item.recommendation="{ item }">
                      <ExpandableText :text="cleanText(item.recommendation)" title="Рекомендация" :lines="2" :min-length="90" />
                    </template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">Аудит сохранённых эталонов и заданий</v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="generationHeaders"
                    :items="generationRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="10"
                  >
                    <template #item.accepted="{ item }">
                      <StatusChip :status="item.accepted ? 'accepted' : 'failed'" :text="yesNoText(item.accepted)" />
                    </template>
                    <template #item.assignment_quality_score="{ item }">{{ formatNumber(item.assignment_quality_score) }}</template>
                    <template #item.assignment_warnings="{ item }">
                      <ExpandableText :text="cleanText(item.assignment_warnings)" title="Замечания к заданию" :lines="2" :min-length="90" />
                    </template>
                    <template #item.quality_score="{ item }">{{ formatNumber(item.quality_score) }}</template>
                    <template #item.warnings="{ item }">
                      <ExpandableText :text="cleanText(item.warnings)" title="Замечания к графу" :lines="2" :min-length="90" />
                    </template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
        
            <v-col cols="12">
              <v-card class="panel" elevation="0">
                <v-card-title class="text-subtitle-1">История запусков</v-card-title>
                <v-card-text>
                  <v-data-table
                    :headers="historyHeaders"
                    :items="historyRows"
                    density="compact"
                    class="border rounded-lg detail-table"
                    :items-per-page="10"
                  >
                    <template #item.generated_at="{ item }">{{ formatDate(item.generated_at) }}</template>
                    <template #item.run_type="{ item }">{{ runTypeLabel(item.run_type) }}</template>
                    <template #item.rag_recall_at_1="{ item }">{{ formatPercent(item.rag_recall_at_1) }}</template>
                    <template #item.rag_mrr="{ item }">{{ formatNumber(item.rag_mrr) }}</template>
                    <template #item.graph_composite_score="{ item }">{{ formatNumber(item.graph_composite_score) }}</template>
                    <template #item.graph_pattern_pass_rate="{ item }">{{ formatPercent(item.graph_pattern_pass_rate) }}</template>
                    <template #item.expert_spearman="{ item }">{{ formatNumber(item.expert_spearman) }}</template>
                  </v-data-table>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
      </v-window-item>
    </v-window>
  </div>
</template>
