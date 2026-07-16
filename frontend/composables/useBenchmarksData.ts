import { onMounted, ref } from 'vue'
import { useAuthStore } from '~/stores/auth'
import type {
  BenchmarkAnalyzeDelimiter,
  BenchmarkCsvDelimiter,
  BenchmarkDetails,
  BenchmarkSummary,
} from '~/types/api'
import { getApiErrorMessage } from '~/utils/apiError'
import { createApiClient } from '~/utils/apiClient'

export type BenchmarkTab = 'overview' | 'rag' | 'graph' | 'validation' | 'artifacts'

export function useBenchmarksData() {
  const auth = useAuthStore()
  const api = createApiClient()

  const activeTab = ref<BenchmarkTab>('overview')
  const summary = ref<BenchmarkSummary | null>(null)
  const details = ref<BenchmarkDetails | null>(null)
  const busy = ref<string | null>(null)
  const notice = ref('')
  const errorText = ref('')

  const ragTarget = ref(50)
  const ragLimit = ref<number | null>(null)
  const graphTarget = ref(20)
  const graphLimit = ref<number | null>(null)
  const graphUseEmbeddings = ref(false)
  const cardiologyCaseCount = ref(12)
  const cardiologyExpertCount = ref(30)
  const cardiologySeed = ref(20260617)
  const cardiologyUseEmbeddings = ref(false)
  const cardiologyOnlyFailed = ref(false)
  const cardiologyOnlyDisagreements = ref(false)
  const expertShuffle = ref(true)
  const expertShuffleSeed = ref(20260617)
  const expertDelimiter = ref<BenchmarkCsvDelimiter>(',')
  const expertAnalyzeDelimiter = ref<BenchmarkAnalyzeDelimiter>('auto')
  const expertFile = ref<File | File[] | null>(null)
  const ragOnlyMisses = ref(false)
  const graphOnlyFailed = ref(false)
  const expertOnlyDisagreements = ref(false)
  const generationAuditLimit = ref(100)
  const demoImportRefreshTimestamps = ref(true)

  async function withBusy<T>(key: string, task: () => Promise<T>, successMessage?: string): Promise<T | undefined> {
    busy.value = key
    errorText.value = ''
    notice.value = ''
    try {
      const result = await task()
      if (successMessage) notice.value = successMessage
      return result
    } catch (error) {
      errorText.value = getApiErrorMessage(error, 'Операция не выполнена')
      return undefined
    } finally {
      busy.value = null
    }
  }

  async function loadBenchmarkData() {
    const [summaryResult, detailsResult] = await Promise.all([
      api.endpoint('GET', '/benchmarks/summary', {
        accessToken: auth.accessToken,
      }),
      api.endpoint('GET', '/benchmarks/details', {
        accessToken: auth.accessToken,
      }),
    ])
    summary.value = summaryResult
    details.value = detailsResult
  }

  async function refreshSummary() {
    await withBusy('summary', loadBenchmarkData)
  }

  async function createRagSeed() {
    await withBusy('rag-seed', async () => {
      await api.endpoint('POST', '/benchmarks/rag/seed', {
        accessToken: auth.accessToken,
        body: { target: ragTarget.value },
      })
      await loadBenchmarkData()
    }, 'Набор RAG-запросов обновлен')
  }

  async function runRagBenchmark(ablation = false) {
    await withBusy(ablation ? 'rag-ablation' : 'rag-run', async () => {
      await api.endpoint('POST', '/benchmarks/rag/run', {
        accessToken: auth.accessToken,
        body: {
          limit: ragLimit.value || null,
          ablation,
        },
      })
      await loadBenchmarkData()
    }, ablation ? 'Сравнение режимов RAG завершено' : 'Проверка RAG-поиска завершена')
  }

  async function createGraphSeed() {
    await withBusy('graph-seed', async () => {
      await api.endpoint('POST', '/benchmarks/graph/seed', {
        accessToken: auth.accessToken,
        body: { target: graphTarget.value },
      })
      await loadBenchmarkData()
    }, 'Набор эталонных графов обновлен')
  }

  async function runGraphBenchmark() {
    await withBusy('graph-run', async () => {
      await api.endpoint('POST', '/benchmarks/graph/run', {
        accessToken: auth.accessToken,
        body: {
          limit: graphLimit.value || null,
          use_embeddings: graphUseEmbeddings.value,
        },
      })
      await loadBenchmarkData()
    }, 'Проверка графового оценщика завершена')
  }

  async function runCardiologySyntheticBenchmark() {
    await withBusy('cardiology-run', async () => {
      await api.endpoint('POST', '/benchmarks/cardiology/synthetic/run', {
        accessToken: auth.accessToken,
        body: {
          case_count: cardiologyCaseCount.value,
          expert_count: cardiologyExpertCount.value,
          seed: cardiologySeed.value,
          use_embeddings: cardiologyUseEmbeddings.value,
        },
      })
      await loadBenchmarkData()
    }, 'Кардиологический набор проверен')
  }

  async function importCardiologyDemo() {
    await withBusy('cardiology-demo-import', async () => {
      await api.endpoint('POST', '/benchmarks/cardiology/synthetic/import-demo', {
        accessToken: auth.accessToken,
        body: {
          refresh_timestamps: demoImportRefreshTimestamps.value,
        },
      })
      await loadBenchmarkData()
    }, 'Кардиологические задачи и сдачи добавлены в демо-кабинеты')
  }

  async function exportExpertPackage() {
    await withBusy('expert-export', async () => {
      await api.endpoint('POST', '/benchmarks/expert/export', {
        accessToken: auth.accessToken,
        body: {
          shuffle: expertShuffle.value,
          shuffle_seed: expertShuffleSeed.value,
          delimiter: expertDelimiter.value,
        },
      })
      await loadBenchmarkData()
    }, 'Пакет экспертной оценки создан')
  }

  async function exportTables() {
    await withBusy('tables-export', async () => {
      await api.endpoint('POST', '/benchmarks/tables/export', {
        accessToken: auth.accessToken,
        body: {},
      })
      await loadBenchmarkData()
    }, 'CSV/XLSX отчеты обновлены')
  }

  async function auditGeneration() {
    await withBusy('generation-audit', async () => {
      await api.endpoint('POST', '/benchmarks/generation/audit', {
        accessToken: auth.accessToken,
        body: { limit: generationAuditLimit.value },
      })
      await loadBenchmarkData()
    }, 'Аудит сохраненных заданий завершен')
  }

  function selectedExpertFile() {
    if (Array.isArray(expertFile.value)) return expertFile.value[0] || null
    return expertFile.value
  }

  async function analyzeExpertCsv() {
    const file = selectedExpertFile()
    if (!file) {
      errorText.value = 'Выберите CSV с оценками экспертов'
      return
    }
    await withBusy('expert-analyze', async () => {
      const csvText = await file.text()
      await api.endpoint('POST', '/benchmarks/expert/analyze', {
        accessToken: auth.accessToken,
        body: {
          csv_text: csvText,
          delimiter: expertAnalyzeDelimiter.value,
        },
      })
      await loadBenchmarkData()
    }, 'Экспертные оценки проанализированы')
  }

  async function downloadArtifact(name: string) {
    await withBusy(`download-${name}`, async () => {
      const headers = new Headers()
      if (auth.accessToken) {
        headers.set('Authorization', `Bearer ${auth.accessToken}`)
      }
      const response = await fetch(api.url(`/benchmarks/files/${encodeURIComponent(name)}`), {
        headers,
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = name
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    })
  }

  onMounted(() => {
    refreshSummary().catch(() => undefined)
  })

  return {
    activeTab,
    analyzeExpertCsv,
    auditGeneration,
    busy,
    cardiologyCaseCount,
    cardiologyExpertCount,
    cardiologyOnlyDisagreements,
    cardiologyOnlyFailed,
    cardiologySeed,
    cardiologyUseEmbeddings,
    createGraphSeed,
    createRagSeed,
    demoImportRefreshTimestamps,
    details,
    downloadArtifact,
    errorText,
    expertAnalyzeDelimiter,
    expertDelimiter,
    expertFile,
    expertOnlyDisagreements,
    expertShuffle,
    expertShuffleSeed,
    exportExpertPackage,
    exportTables,
    generationAuditLimit,
    graphLimit,
    graphOnlyFailed,
    graphTarget,
    graphUseEmbeddings,
    importCardiologyDemo,
    loadBenchmarkData,
    notice,
    ragLimit,
    ragOnlyMisses,
    ragTarget,
    refreshSummary,
    runCardiologySyntheticBenchmark,
    runGraphBenchmark,
    runRagBenchmark,
    summary,
  }
}

export type BenchmarksData = ReturnType<typeof useBenchmarksData>
