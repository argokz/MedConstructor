<script setup lang="ts">
import type { BenchmarksData } from '~/composables/useBenchmarksData'
import type { BenchmarksFormatter } from '~/composables/useBenchmarksFormatter'

const props = defineProps<{
  data: BenchmarksData
  ui: BenchmarksFormatter
}>()

const {
  busy,
  createRagSeed,
  ragLimit,
  ragOnlyMisses,
  ragTarget,
  runRagBenchmark,
} = props.data
const {
  ablationHeaders,
  ablationRows,
  compactValue,
  cleanText,
  formatNumber,
  formatPercent,
  modeLabel,
  ragAblationDetailRows,
  ragDetailRows,
  ragMetricTiles,
  ragResultHeaders,
} = props.ui
</script>

<template>
  <v-row>
    <v-col cols="12" lg="4">
      <v-card class="panel" elevation="0">
        <v-card-title class="text-subtitle-1">Проверка поиска по протоколам</v-card-title>
        <v-card-text class="d-flex flex-column ga-3">
          <v-text-field
            v-model.number="ragTarget"
            label="Размер набора запросов"
            type="number"
            :min="1"
            :max="200"
            density="compact"
            variant="outlined"
          />
          <v-text-field
            v-model.number="ragLimit"
            label="Лимит запуска"
            type="number"
            :min="1"
            :max="500"
            density="compact"
            variant="outlined"
            clearable
          />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-btn
            variant="outlined"
            color="primary"
            :loading="busy === 'rag-seed'"
            prepend-icon="mdi-database-plus-outline"
            @click="createRagSeed"
          >
            Обновить набор
          </v-btn>
          <v-spacer />
          <v-btn
            color="primary"
            variant="flat"
            :loading="busy === 'rag-run'"
            prepend-icon="mdi-play"
            @click="runRagBenchmark(false)"
          >
            Запустить
          </v-btn>
          <v-btn
            color="secondary"
            variant="flat"
            :loading="busy === 'rag-ablation'"
            prepend-icon="mdi-compare-horizontal"
            @click="runRagBenchmark(true)"
          >
            Сравнить режимы
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-col>

    <v-col cols="12" lg="8">
      <v-card class="panel" elevation="0">
        <v-card-title class="text-subtitle-1">Последний результат поиска</v-card-title>
        <v-card-text>
          <div class="metric-grid wide mb-4">
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
          <v-data-table
            :headers="ablationHeaders"
            :items="ablationRows"
            density="compact"
            class="border rounded-lg"
            hide-default-footer
          >
            <template #item.mode="{ item }">{{ modeLabel(item.mode) }}</template>
            <template #item.recall_at_1="{ item }">{{ formatPercent(item.recall_at_1) }}</template>
            <template #item.recall_at_5="{ item }">{{ formatPercent(item.recall_at_5) }}</template>
            <template #item.mrr="{ item }">{{ formatNumber(item.mrr) }}</template>
            <template #item.section_hit_rate="{ item }">{{ formatPercent(item.section_hit_rate) }}</template>
            <template #item.key_phrase_hit_rate="{ item }">{{ formatPercent(item.key_phrase_hit_rate) }}</template>
            <template #item.p50="{ item }">{{ formatNumber(item.p50, 1) }}</template>
          </v-data-table>
        </v-card-text>
      </v-card>
    </v-col>

    <v-col cols="12">
      <v-card class="panel" elevation="0">
        <v-card-title class="text-subtitle-1 d-flex align-center flex-wrap ga-3">
          Проверка отдельных запросов
          <v-spacer />
          <v-switch
            v-model="ragOnlyMisses"
            label="Только ошибки"
            color="error"
            density="compact"
            hide-details
          />
        </v-card-title>
        <v-card-text>
          <v-data-table
            :headers="ragResultHeaders"
            :items="ragDetailRows"
            density="compact"
            class="border rounded-lg detail-table"
            :items-per-page="10"
          >
            <template #item.id="{ item }">
              <div class="text-body-2">{{ item.query || item.id }}</div>
            </template>
            <template #item.hit_rank="{ item }">
              <v-chip
                size="small"
                :color="item.miss ? 'error' : item.hit_rank === 1 ? 'success' : 'warning'"
                variant="tonal"
              >
                {{ item.hit_rank ?? 'не найдено' }}
              </v-chip>
            </template>
            <template #item.latency_ms="{ item }">{{ formatNumber(item.latency_ms, 1) }}</template>
            <template #item.section_hit_score="{ item }">{{ formatPercent(item.section_hit_score) }}</template>
            <template #item.key_phrase_hit_score="{ item }">{{ formatPercent(item.key_phrase_hit_score) }}</template>
            <template #item.expected_protocol_ids="{ item }">{{ compactValue(item.expected_protocol_ids) }}</template>
            <template #item.retrieved_protocol_ids="{ item }">{{ compactValue(item.retrieved_protocol_ids, 6) }}</template>
            <template #item.top_protocol_title="{ item }">
              <div class="text-body-2 font-weight-medium">{{ item.top_protocol_title || '—' }}</div>
              <div class="text-caption text-medium-emphasis">{{ item.top_section || '—' }}</div>
            </template>
            <template #item.top_preview="{ item }">
              <ExpandableText
                :text="cleanText(item.top_preview)"
                title="Фрагмент найденного протокола"
                :lines="3"
                :min-length="120"
              />
            </template>
          </v-data-table>
        </v-card-text>
      </v-card>
    </v-col>

    <v-col cols="12">
      <v-card class="panel" elevation="0">
        <v-card-title class="text-subtitle-1">Сравнение режимов по каждому запросу</v-card-title>
        <v-card-text>
          <v-data-table
            :headers="ragResultHeaders.filter((header) => header.key !== 'top_preview')"
            :items="ragAblationDetailRows"
            density="compact"
            class="border rounded-lg detail-table"
            :items-per-page="10"
          >
            <template #item.id="{ item }">
              <div class="text-body-2">{{ item.query || item.id }}</div>
            </template>
            <template #item.hit_rank="{ item }">
              <v-chip
                size="small"
                :color="item.miss ? 'error' : item.hit_rank === 1 ? 'success' : 'warning'"
                variant="tonal"
              >
                {{ item.hit_rank ?? 'не найдено' }}
              </v-chip>
            </template>
            <template #item.latency_ms="{ item }">{{ formatNumber(item.latency_ms, 1) }}</template>
            <template #item.section_hit_score="{ item }">{{ formatPercent(item.section_hit_score) }}</template>
            <template #item.key_phrase_hit_score="{ item }">{{ formatPercent(item.key_phrase_hit_score) }}</template>
            <template #item.expected_protocol_ids="{ item }">{{ compactValue(item.expected_protocol_ids) }}</template>
            <template #item.retrieved_protocol_ids="{ item }">{{ compactValue(item.retrieved_protocol_ids, 6) }}</template>
            <template #item.top_protocol_title="{ item }">
              <div class="text-body-2 font-weight-medium">{{ item.top_protocol_title || '—' }}</div>
              <div class="text-caption text-medium-emphasis">{{ modeLabel(item.mode) }} · {{ item.top_section || '—' }}</div>
            </template>
          </v-data-table>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>
</template>
