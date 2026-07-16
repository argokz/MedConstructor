<script setup lang="ts">
import PageHeader from '~/components/shared/ui/PageHeader.vue'
import '~/assets/css/benchmarks.css'
import { useBenchmarksData } from '~/composables/useBenchmarksData'
import { useBenchmarksFormatter } from '~/composables/useBenchmarksFormatter'

definePageMeta({
  middleware: 'teacher',
  keepalive: true,
})

const benchmarkData = useBenchmarksData()
const benchmarkUi = useBenchmarksFormatter(benchmarkData)

const {
  activeTab,
  busy,
  downloadArtifact,
  errorText,
  exportTables,
  notice,
  refreshSummary,
} = benchmarkData
const { reportArtifact } = benchmarkUi
</script>

<template>
  <v-container fluid class="bench-page pa-4 pa-md-6">
    <PageHeader
      title="Аналитика качества"
      subtitle="Поиск по протоколам, графовый оценщик, экспертная валидация и материалы для научной статьи."
    >
      <template #actions>
        <v-btn color="primary" variant="outlined" :loading="busy === 'summary'" prepend-icon="mdi-refresh" @click="refreshSummary">Обновить</v-btn>
        <v-btn color="secondary" variant="flat" :loading="busy === 'tables-export'" prepend-icon="mdi-table-arrow-down" @click="exportTables">Сформировать отчеты</v-btn>
        <v-btn color="success" variant="outlined" :disabled="!reportArtifact?.exists" :loading="busy === 'download-benchmark_report_latest.xlsx'" prepend-icon="mdi-file-excel-outline" @click="downloadArtifact('benchmark_report_latest.xlsx')">Скачать XLSX</v-btn>
      </template>
    </PageHeader>

    <v-alert v-if="errorText" type="error" variant="tonal" density="compact" class="mb-4" closable @click:close="errorText = ''">{{ errorText }}</v-alert>
    <v-alert v-if="notice" type="success" variant="tonal" density="compact" class="mb-4" closable @click:close="notice = ''">{{ notice }}</v-alert>

    <v-tabs v-model="activeTab" color="primary" bg-color="surface" class="border rounded-tabs" density="comfortable">
      <v-tab value="overview">Обзор</v-tab>
      <v-tab value="rag">RAG</v-tab>
      <v-tab value="graph">Графы</v-tab>
      <v-tab value="validation">Экспертиза</v-tab>
      <v-tab value="artifacts">Артефакты</v-tab>
    </v-tabs>

    <v-window v-model="activeTab" class="mt-4">
      <v-window-item value="overview"><BenchmarkOverviewTab :data="benchmarkData" :ui="benchmarkUi" /></v-window-item>
      <v-window-item value="rag"><BenchmarkRagTab :data="benchmarkData" :ui="benchmarkUi" /></v-window-item>
      <v-window-item value="graph"><BenchmarkGraphTab :data="benchmarkData" :ui="benchmarkUi" /></v-window-item>
      <v-window-item value="validation"><BenchmarkValidationTab :data="benchmarkData" :ui="benchmarkUi" /></v-window-item>
      <v-window-item value="artifacts"><BenchmarkArtifactsTab :data="benchmarkData" :ui="benchmarkUi" /></v-window-item>
    </v-window>
  </v-container>
</template>
