<script setup lang="ts">
import type { BenchmarksData } from '~/composables/useBenchmarksData'
import type { BenchmarksFormatter } from '~/composables/useBenchmarksFormatter'

const props = defineProps<{
  data: BenchmarksData
  ui: BenchmarksFormatter
}>()

const {
  busy,
  createGraphSeed,
  graphLimit,
  graphOnlyFailed,
  graphTarget,
  graphUseEmbeddings,
  runGraphBenchmark,
  summary,
} = props.data
const {
  formatNumber,
  formatPercent,
  graphDetailRows,
  graphMetricTiles,
  graphQualityHeaders,
  graphQualityRows,
  graphResultHeaders,
  patternHeaders,
  patternLabel,
  variantLabel,
  patternRows,
  cleanText,
  statusColor,
  yesNoText,
} = props.ui
</script>

<template>
  <v-row>
    <v-col cols="12" lg="4">
      <v-card class="panel" elevation="0">
        <v-card-title class="text-subtitle-1">Проверка графового оценщика</v-card-title>
        <v-card-text class="d-flex flex-column ga-3">
          <v-text-field
            v-model.number="graphTarget"
            label="Количество эталонных кейсов"
            type="number"
            :min="1"
            :max="20"
            density="compact"
            variant="outlined"
          />
          <v-text-field
            v-model.number="graphLimit"
            label="Лимит вариантов"
            type="number"
            :min="1"
            :max="200"
            density="compact"
            variant="outlined"
            clearable
          />
          <v-switch
            v-model="graphUseEmbeddings"
            label="Семантическое сопоставление блоков"
            color="primary"
            density="compact"
            hide-details
          />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-btn
            variant="outlined"
            color="primary"
            :loading="busy === 'graph-seed'"
            prepend-icon="mdi-database-plus-outline"
            @click="createGraphSeed"
          >
            Обновить набор
          </v-btn>
          <v-spacer />
          <v-btn
            color="primary"
            variant="flat"
            :loading="busy === 'graph-run'"
            prepend-icon="mdi-play"
            @click="runGraphBenchmark"
          >
            Запустить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-col>

    <v-col cols="12" lg="8">
      <v-card class="panel" elevation="0">
        <v-card-title class="text-subtitle-1">Последний результат проверки графов</v-card-title>
        <v-card-text>
          <div class="metric-grid wide mb-4">
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
          <div class="d-flex flex-wrap ga-2 mb-3">
            <v-chip size="small" color="success" variant="tonal">
              Валидная схема {{ formatPercent(summary?.graph.reference_quality?.schema_valid_rate) }}
            </v-chip>
            <v-chip size="small" color="primary" variant="tonal">
              Принятые эталоны {{ formatPercent(summary?.graph.reference_quality?.accepted_rate) }}
            </v-chip>
            <v-chip size="small" color="warning" variant="tonal">
              Замечания {{ formatPercent(summary?.graph.reference_quality?.warning_rate) }}
            </v-chip>
            <v-chip size="small" color="error" variant="tonal">
              Критичные {{ formatPercent(summary?.graph.reference_quality?.critical_rate) }}
            </v-chip>
          </div>
          <v-data-table
            :headers="patternHeaders"
            :items="patternRows"
            density="compact"
            class="border rounded-lg"
            hide-default-footer
          >
            <template #item.expected_pattern="{ item }">{{ patternLabel(item.expected_pattern) }}</template>
            <template #item.pass_rate="{ item }">{{ formatPercent(item.pass_rate) }}</template>
          </v-data-table>
        </v-card-text>
      </v-card>
    </v-col>

    <v-col cols="12">
      <v-card class="panel" elevation="0">
        <v-card-title class="text-subtitle-1 d-flex align-center flex-wrap ga-3">
          Варианты студенческих ошибок
          <v-spacer />
          <v-switch
            v-model="graphOnlyFailed"
            label="Только проблемные"
            color="warning"
            density="compact"
            hide-details
          />
        </v-card-title>
        <v-card-text>
          <v-data-table
            :headers="graphResultHeaders"
            :items="graphDetailRows"
            density="compact"
            class="border rounded-lg detail-table"
            :items-per-page="10"
          >
            <template #item.pattern_passed="{ item }">
              <StatusChip :status="item.pattern_passed ? 'accepted' : 'failed'" :text="item.pattern_passed ? 'Распознано' : 'Не распознано'" />
            </template>
            <template #item.variant_id="{ item }">{{ variantLabel(item.variant_id) }}</template>
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
        <v-card-title class="text-subtitle-1">Качество эталонных графов</v-card-title>
        <v-card-text>
          <v-data-table
            :headers="graphQualityHeaders"
            :items="graphQualityRows"
            density="compact"
            class="border rounded-lg detail-table"
            :items-per-page="10"
          >
            <template #item.accepted="{ item }">
              <StatusChip :status="item.accepted ? 'accepted' : 'failed'" :text="yesNoText(item.accepted)" />
            </template>
            <template #item.quality_score="{ item }">{{ formatNumber(item.quality_score) }}</template>
            <template #item.has_diagnosis="{ item }">
              <v-icon :icon="item.has_diagnosis ? 'mdi-check' : 'mdi-alert-circle-outline'" :color="statusColor(item.has_diagnosis)" />
            </template>
            <template #item.has_diagnostic_step="{ item }">
              <v-icon :icon="item.has_diagnostic_step ? 'mdi-check' : 'mdi-alert-circle-outline'" :color="statusColor(item.has_diagnostic_step)" />
            </template>
            <template #item.has_start_to_diagnosis_path="{ item }">
              <v-icon :icon="item.has_start_to_diagnosis_path ? 'mdi-check' : 'mdi-alert-circle-outline'" :color="statusColor(item.has_start_to_diagnosis_path)" />
            </template>
            <template #item.has_diagnosis_to_action_path="{ item }">
              <v-icon :icon="item.has_diagnosis_to_action_path ? 'mdi-check' : 'mdi-alert-circle-outline'" :color="statusColor(item.has_diagnosis_to_action_path)" />
            </template>
          </v-data-table>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>
</template>
