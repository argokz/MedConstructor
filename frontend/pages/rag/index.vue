<script setup lang="ts">
import EmptyState from '~/components/shared/ui/EmptyState.vue'
import PageHeader from '~/components/shared/ui/PageHeader.vue'
import type { RagAskRequest, RagAskResponse, RagSource } from '~/types/api'
import { createApiClient } from '~/utils/apiClient'
import { renderSafeMarkdown } from '~/utils/markdown'

definePageMeta({ keepalive: true })

const route = useRoute()
const router = useRouter()
const chat = useRagChatStore()
const api = createApiClient()

const loading = ref(false)
const resultsRef = ref<HTMLElement | null>(null)
const stickToBottom = ref(true)

const renderedAnswer = computed(() => {
  if (!chat.result?.answer) return ''
  if (loading.value) return ''
  return renderSafeMarkdown(chat.result.answer)
})

const syncProtocolFromRoute = async () => {
  const rawProtocol = Array.isArray(route.query.protocol) ? route.query.protocol[0] : route.query.protocol
  const qId = rawProtocol ? Number.parseInt(rawProtocol, 10) : null
  if (qId === chat.protocolId) return

  chat.protocolId = qId
  if (!qId) {
    chat.protocolInfo = null
    return
  }
  try {
    chat.protocolInfo = await api.endpoint('GET', `/protocols/${qId}`, {})
  } catch (e) {
    console.error('Failed to fetch protocol info for RAG', e)
    chat.protocolInfo = null
  }
}

onMounted(syncProtocolFromRoute)
onActivated(syncProtocolFromRoute)

const scrollResultsToBottom = (behavior: ScrollBehavior = 'smooth') => {
  if (!stickToBottom.value || !resultsRef.value) return
  resultsRef.value.scrollTo({ top: resultsRef.value.scrollHeight, behavior })
}

const onResultsScroll = () => {
  if (!resultsRef.value) return
  const el = resultsRef.value
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight
  stickToBottom.value = distance < 80
}

watch(() => chat.streamingAnswer, () => {
  nextTick(() => scrollResultsToBottom('auto'))
})

const askQuestion = async () => {
  if (!chat.question.trim()) return

  loading.value = true
  chat.error = null
  chat.result = null
  chat.streamingAnswer = ''
  stickToBottom.value = true

  const payload: RagAskRequest = { question: chat.question }
  if (chat.protocolId) payload.protocol_id = chat.protocolId

  try {
    const response = await fetch(api.url('/rag/ask/stream'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })

    if (!response.ok || !response.body) {
      throw new Error(`HTTP ${response.status}`)
    }

    chat.result = { answer: '', sources: [] }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const event = JSON.parse(line.slice(6)) as { type?: string; content?: unknown }
        if (event.type === 'sources') {
          chat.result!.sources = Array.isArray(event.content) ? event.content as RagSource[] : []
        } else if (event.type === 'token') {
          chat.streamingAnswer += typeof event.content === 'string' ? event.content : ''
          chat.result!.answer = chat.streamingAnswer
        } else if (event.type === 'error') {
          throw new Error(typeof event.content === 'string' ? event.content : 'Ошибка запроса к ИИ')
        }
      }
    }
  } catch (error) {
    console.error('RAG stream failed, falling back', error)
    try {
      chat.result = await api.endpoint('POST', '/rag/ask', { body: payload }) as RagAskResponse
      chat.streamingAnswer = chat.result?.answer || ''
    } catch (fallbackError) {
      chat.error = fallbackError instanceof Error ? fallbackError.message : 'Ошибка запроса к ИИ'
    }
  } finally {
    loading.value = false
    nextTick(() => scrollResultsToBottom('smooth'))
  }
}

const clearProtocolFilter = () => {
  chat.protocolId = null
  chat.protocolInfo = null
  void router.replace({ query: {} })
}

onDeactivated(() => {
  if (resultsRef.value) chat.scrollTop = resultsRef.value.scrollTop
})

onActivated(() => {
  nextTick(() => {
    if (resultsRef.value && chat.scrollTop > 0) {
      resultsRef.value.scrollTop = chat.scrollTop
      const el = resultsRef.value
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight
      stickToBottom.value = distance < 80
    }
  })
})
</script>

<template>
  <v-container class="rag-page pa-3 pa-sm-4 pa-md-8" fluid>
    <div class="rag-shell">
      <v-card class="surface-card mb-4 mb-md-6 pa-4 pa-md-6 rounded-xl flex-shrink-0" elevation="0" border>
        <PageHeader
          title="Медицинский ИИ"
          subtitle="Анализ клинических протоколов и поиск первоисточников"
        >
          <template #actions>
            <v-avatar color="primary" variant="tonal" rounded="lg" size="44">
              <v-icon icon="mdi-brain" size="26" />
            </v-avatar>
          </template>
        </PageHeader>

        <v-alert
          v-if="chat.protocolInfo"
          type="info"
          variant="tonal"
          class="mb-4"
          rounded="lg"
          closable
          @click:close="clearProtocolFilter"
        >
          <template #prepend>
            <v-icon icon="mdi-file-document-outline" />
          </template>
          <div class="font-weight-medium text-caption text-uppercase tracking-wider mb-1">Локальный поиск:</div>
          <div class="font-weight-medium text-wrap">{{ chat.protocolInfo.title }}</div>
        </v-alert>

        <v-textarea
          v-model="chat.question"
          placeholder="Задайте клинический вопрос..."
          variant="solo-filled"
          auto-grow
          rows="2"
          max-rows="5"
          flat
          hide-details
          class="chat-input"
          rounded="xl"
          @keydown.enter.exact.prevent="askQuestion"
        >
          <template #append-inner>
            <v-btn
              color="primary"
              icon="mdi-arrow-up"
              size="small"
              class="ml-2"
              :loading="loading"
              :disabled="!chat.question.trim()"
              @click="askQuestion"
            />
          </template>
        </v-textarea>
      </v-card>

      <div
        ref="resultsRef"
        class="rag-results smooth-scroll"
        @scroll.passive="onResultsScroll"
      >
        <v-card v-if="chat.error" class="surface-card pa-4 mb-4 rounded-xl" border="error">
          <v-alert type="error" variant="tonal" rounded="lg">{{ chat.error }}</v-alert>
        </v-card>

        <v-card
          v-if="loading && !chat.result"
          class="surface-card pa-8 mb-8 rounded-xl d-flex flex-column align-center justify-center text-medium-emphasis"
          elevation="0"
          border
        >
          <v-progress-circular indeterminate color="primary" size="44" width="3" class="mb-4" />
          <div>ИИ анализирует протоколы...</div>
        </v-card>

        <v-card v-else-if="chat.result" class="surface-card pa-4 pa-md-8 rounded-xl" elevation="0" border>
          <div class="d-flex align-center mb-4 mb-md-6">
            <v-avatar color="primary" size="36" class="mr-3">
              <v-icon icon="mdi-robot-outline" color="white" size="20" />
            </v-avatar>
            <div class="text-h6 font-weight-bold">Ответ ИИ</div>
            <v-chip v-if="loading" size="x-small" color="primary" variant="tonal" class="ml-3">
              печатает...
            </v-chip>
          </div>

          <div
            v-if="loading"
            class="text-body-1 ai-answer-stream mb-6"
          >{{ chat.streamingAnswer }}<span class="cursor-blink">|</span></div>
          <!-- Content is rendered by renderSafeMarkdown with raw HTML disabled. -->
          <!-- eslint-disable vue/no-v-html -->
          <div
            v-else
            class="text-body-1 ai-answer mb-6"
            v-html="renderedAnswer"
          />
          <!-- eslint-enable vue/no-v-html -->

          <v-divider class="mb-4 mb-md-6 opacity-20" />

          <div class="text-subtitle-1 font-weight-bold mb-3 d-flex align-center">
            <v-icon icon="mdi-book-open-page-variant-outline" class="mr-2" opacity="0.6" size="small" />
            <span class="text-medium-emphasis">Использованные источники</span>
          </div>

          <EmptyState
            v-if="!chat.result.sources?.length"
            icon="mdi-book-search-outline"
            title="Источники не найдены"
            text="Специфические источники не найдены."
          />

          <div v-else class="d-flex flex-column gap-3">
            <v-card
              v-for="(source, i) in chat.result.sources"
              :key="i"
              variant="tonal"
              color="surface-variant"
              class="rounded-lg source-card"
            >
              <div class="pa-3 pa-md-4">
                <div class="d-flex align-start gap-2">
                  <v-chip size="x-small" color="primary" variant="flat" class="font-weight-bold px-2 flex-shrink-0">
                    {{ source.id }}
                  </v-chip>
                  <div class="text-body-2 font-weight-medium line-height-tight flex-grow-1 text-wrap">
                    {{ source.protocol_title }}
                  </div>
                  <v-btn
                    :to="`/protocols/${source.protocol_id}`"
                    icon="mdi-open-in-new"
                    size="x-small"
                    variant="text"
                    color="primary"
                    class="flex-shrink-0"
                  />
                </div>
                <div class="source-text mt-2 text-body-2 ps-3 border-s-sm border-primary smooth-scroll">
                  {{ source.text }}
                </div>
              </div>
            </v-card>
          </div>
        </v-card>
      </div>
    </div>
  </v-container>
</template>

<style scoped>
.rag-page {
  min-height: calc(100dvh - 64px);
  display: flex;
  justify-content: center;
}

.rag-shell {
  width: 100%;
  max-width: 900px;
  display: flex;
  flex-direction: column;
  min-height: calc(100dvh - 96px);
  max-height: calc(100dvh - 96px);
}

.rag-results {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding-bottom: 2rem;
  contain: layout style;
}

.surface-card {
  background-color: rgba(var(--v-theme-surface), 0.92) !important;
  backdrop-filter: blur(8px);
}

.chat-input :deep(.v-field) {
  border-radius: 20px;
  background-color: rgba(var(--v-theme-surface-variant), 0.75) !important;
  padding-right: 8px;
}

.chat-input :deep(.v-field__input) {
  padding-top: 14px;
  padding-bottom: 14px;
}

.ai-answer-stream {
  white-space: pre-wrap;
  line-height: 1.7;
  font-size: 1.05rem;
  color: rgb(var(--v-theme-on-surface));
  word-break: break-word;
}

.ai-answer {
  line-height: 1.7;
  font-size: 1.05rem;
  color: rgb(var(--v-theme-on-surface));
  word-break: break-word;
}

.cursor-blink {
  animation: blink 1s step-end infinite;
  opacity: 0.7;
}

@keyframes blink {
  50% { opacity: 0; }
}

.source-card {
  background-color: rgba(var(--v-theme-surface-variant), 0.45) !important;
  border: 1px solid rgba(var(--v-border-color), 0.06);
}

.source-text {
  max-height: 180px;
  overflow-y: auto;
  line-height: 1.5;
  color: rgb(var(--v-theme-on-surface));
}

.ai-answer :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 1rem;
  display: block;
  overflow-x: auto;
}

.ai-answer :deep(th),
.ai-answer :deep(td) {
  border: 1px solid rgba(var(--v-border-color), 0.2);
  padding: 8px 12px;
}

.ai-answer :deep(th) {
  background-color: rgba(var(--v-theme-on-surface), 0.04);
  font-weight: bold;
}

.smooth-scroll {
  scroll-behavior: smooth;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
}

.gap-3 { gap: 0.75rem; }
.tracking-wider { letter-spacing: 0.05em; }
.line-height-tight { line-height: 1.3; }
.min-w-0 { min-width: 0; }

@media (max-width: 599px) {
  .rag-shell {
    max-height: none;
    min-height: auto;
  }

  .rag-results {
    overflow: visible;
  }

  .source-text {
    max-height: 140px;
  }
}
</style>
