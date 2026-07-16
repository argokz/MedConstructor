<script setup lang="ts">
import type { BenchmarksData } from '~/composables/useBenchmarksData'
import type { BenchmarksFormatter } from '~/composables/useBenchmarksFormatter'

const props = defineProps<{
  data: BenchmarksData
  ui: BenchmarksFormatter
}>()

const { busy, downloadArtifact } = props.data
const {
  artifactLabel,
  artifactHeaders,
  artifacts,
  csvArtifacts,
  formatDate,
  formatSize,
} = props.ui
</script>

<template>
  <v-card class="panel" elevation="0">
    <v-card-title class="text-subtitle-1 d-flex align-center flex-wrap ga-3">
      Материалы и экспорт для статьи
      <v-spacer />
      <v-chip size="small" color="secondary" variant="tonal">
        CSV-файлы: {{ csvArtifacts.length }}
      </v-chip>
    </v-card-title>
    <v-card-text>
      <v-data-table
        :headers="artifactHeaders"
        :items="artifacts"
        density="compact"
        class="border rounded-lg"
        :items-per-page="20"
      >
        <template #item.name="{ item }">
          <div class="font-weight-bold">{{ artifactLabel(item.name) }}</div>
          <div class="text-caption text-medium-emphasis">{{ item.name }}</div>
        </template>
        <template #item.size_bytes="{ item }">{{ formatSize(item.size_bytes) }}</template>
        <template #item.updated_at="{ item }">{{ formatDate(item.updated_at) }}</template>
        <template #item.actions="{ item }">
          <v-tooltip text="Скачать" aria-label="Скачать отчет">
            <template #activator="{ props }">
              <v-btn
                v-bind="props"
                icon="mdi-download"
                variant="text"
                size="small"
                color="primary"
                aria-label="Скачать отчет"
                :disabled="!item.exists"
                :loading="busy === `download-${item.name}`"
                @click="downloadArtifact(item.name)"
              />
            </template>
          </v-tooltip>
        </template>
      </v-data-table>
    </v-card-text>
  </v-card>
</template>
