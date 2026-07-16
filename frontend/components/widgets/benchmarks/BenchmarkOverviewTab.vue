<script setup lang="ts">
import type { BenchmarksData } from '~/composables/useBenchmarksData'
import type { BenchmarksFormatter } from '~/composables/useBenchmarksFormatter'

const props = defineProps<{
  data: BenchmarksData
  ui: BenchmarksFormatter
}>()

const { summary } = props.data
const {
  expertMetricTiles,
  formatDate,
  formatNumber,
  formatPercent,
  graphChartRows,
  graphMetricTiles,
  historyChartRows,
  metricGuideItems,
  ragAblationChartRows,
  ragMetricTiles,
  researchSummaryTiles,
  researchWorkflow,
} = props.ui
</script>

<template>
  <v-row>
    <v-col cols="12">
      <v-card class="panel" elevation="0">
        <v-card-title class="text-subtitle-1">Научная сводка качества системы</v-card-title>
        <v-card-text>
          <div class="metric-grid wide mb-4">
            <v-tooltip
              v-for="metric in researchSummaryTiles"
              :key="metric.label"
              :text="metric.hint"
              :aria-label="metric.hint"
              location="top"
            >
              <template #activator="{ props }">
                <MetricCard
                  v-bind="props"
                  :title="metric.label"
                  :value="metric.value"
                  :subtitle="metric.subtitle"
                  :color="metric.tone"
                />
              </template>
            </v-tooltip>
          </div>

          <v-row>
            <v-col cols="12" lg="5">
              <div class="text-caption text-medium-emphasis mb-2">Логика исследования</div>
              <v-timeline density="compact" side="end" truncate-line="both" class="research-timeline">
                <v-timeline-item
                  v-for="step in researchWorkflow"
                  :key="step.title"
                  dot-color="primary"
                  size="x-small"
                >
                  <div class="font-weight-bold">{{ step.title }}</div>
                  <div class="text-body-2 text-medium-emphasis">{{ step.text }}</div>
                  <div class="text-caption text-primary mt-1">{{ step.metric }}</div>
                </v-timeline-item>
              </v-timeline>
            </v-col>

            <v-col cols="12" lg="7">
              <div class="text-caption text-medium-emphasis mb-2">Как читать метрики</div>
              <v-expansion-panels density="compact" variant="accordion">
                <v-expansion-panel
                  v-for="item in metricGuideItems"
                  :key="item.metric"
                  rounded="lg"
                >
                  <v-expansion-panel-title class="font-weight-bold">
                    {{ item.metric }}
                  </v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <div class="text-body-2 mb-2">{{ item.purpose }}</div>
                    <div class="text-body-2 mb-2">{{ item.interpretation }}</div>
                    <div class="text-body-2 text-primary">{{ item.impact }}</div>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </v-col>

    <v-col cols="12" lg="4">
      <v-card class="panel" elevation="0">
        <v-card-title class="text-subtitle-1 d-flex align-center">
          <v-icon icon="mdi-brain" color="primary" class="mr-2" />
          RAG
        </v-card-title>
        <v-card-text>
          <div class="metric-grid">
            <v-tooltip
              v-for="metric in ragMetricTiles"
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
          <div class="text-caption text-medium-emphasis mt-3">
            Набор запросов: {{ summary?.rag.seed_cases ?? '—' }} · {{ formatDate(summary?.rag.generated_at || null) }}
          </div>
        </v-card-text>
      </v-card>
    </v-col>

    <v-col cols="12" lg="4">
      <v-card class="panel" elevation="0">
        <v-card-title class="text-subtitle-1 d-flex align-center">
          <v-icon icon="mdi-graph-outline" color="secondary" class="mr-2" />
          Графы
        </v-card-title>
        <v-card-text>
          <div class="metric-grid">
            <v-tooltip
              v-for="metric in graphMetricTiles"
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
          <div class="text-caption text-medium-emphasis mt-3">
            Эталонных кейсов: {{ summary?.graph.seed_cases ?? '—' }} · {{ formatDate(summary?.graph.generated_at || null) }}
          </div>
        </v-card-text>
      </v-card>
    </v-col>

    <v-col cols="12" lg="4">
      <v-card class="panel" elevation="0">
        <v-card-title class="text-subtitle-1 d-flex align-center">
          <v-icon icon="mdi-account-check-outline" color="success" class="mr-2" />
          Эксперты
        </v-card-title>
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
          <div class="text-caption text-medium-emphasis mt-3">
            Пропущено строк CSV: {{ summary?.expert?.skipped_row_count ?? '—' }}
          </div>
        </v-card-text>
      </v-card>
    </v-col>

    <v-col cols="12" lg="4">
      <v-card class="panel" elevation="0">
        <v-card-title class="text-subtitle-1">Сравнение режимов RAG-поиска</v-card-title>
        <v-card-text>
          <div v-for="row in ragAblationChartRows" :key="row.label" class="chart-row">
            <div class="chart-label">{{ row.label }}</div>
            <div class="chart-track">
              <div class="chart-fill primary" :style="{ width: `${Math.min(100, Math.max(0, row.value * 100))}%` }" />
            </div>
            <div class="chart-value">{{ formatPercent(row.value) }}</div>
            <div class="text-caption text-medium-emphasis">{{ row.caption }}</div>
          </div>
        </v-card-text>
      </v-card>
    </v-col>

    <v-col cols="12" lg="4">
      <v-card class="panel" elevation="0">
        <v-card-title class="text-subtitle-1">Качество графового оценщика</v-card-title>
        <v-card-text>
          <div v-for="row in graphChartRows" :key="row.label" class="chart-row">
            <div class="chart-label">{{ row.label }}</div>
            <div class="chart-track">
              <div class="chart-fill secondary" :style="{ width: `${Math.min(100, Math.max(0, row.value * 100))}%` }" />
            </div>
            <div class="chart-value">{{ row.caption }}</div>
          </div>
        </v-card-text>
      </v-card>
    </v-col>

    <v-col cols="12" lg="4">
      <v-card class="panel" elevation="0">
        <v-card-title class="text-subtitle-1">История</v-card-title>
        <v-card-text>
          <div v-if="!historyChartRows.length" class="text-body-2 text-medium-emphasis">—</div>
          <div v-for="row in historyChartRows" :key="`${row.label}-${row.caption}`" class="chart-row">
            <div class="chart-label">{{ row.label }}</div>
            <div class="chart-track">
              <div class="chart-fill success" :style="{ width: `${Math.min(100, Math.max(0, row.value * 100))}%` }" />
            </div>
            <div class="chart-value">{{ formatNumber(row.value) }}</div>
            <div class="text-caption text-medium-emphasis">{{ row.caption }}</div>
          </div>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>
</template>
