import { defineStore } from 'pinia'

export const useRagChatStore = defineStore('ragChat', () => {
  const question = ref('')
  const protocolId = ref<number | null>(null)
  const protocolInfo = ref<{ id: number; title: string } | null>(null)
  const result = ref<{ answer: string; sources: any[] } | null>(null)
  const streamingAnswer = ref('')
  const error = ref<string | null>(null)
  const scrollTop = ref(0)

  return {
    question,
    protocolId,
    protocolInfo,
    result,
    streamingAnswer,
    error,
    scrollTop,
  }
})
