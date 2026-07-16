import { defineStore } from 'pinia'

export const useTeacherGeneratorStore = defineStore('teacherGenerator', () => {
  const currentStep = ref(1)
  const protocols = ref<any[]>([])
  const protocolsLoaded = ref(false)
  const selectedProtocols = ref<number[]>([])
  const scenarios = ref<any[]>([])
  const selectedScenario = ref<any | null>(null)
  const referenceGraph = ref<any | null>(null)
  const generationContext = ref<any | null>(null)
  const timeLimitMinutes = ref<number | null>(45)

  return {
    currentStep,
    protocols,
    protocolsLoaded,
    selectedProtocols,
    scenarios,
    selectedScenario,
    referenceGraph,
    generationContext,
    timeLimitMinutes,
  }
})
