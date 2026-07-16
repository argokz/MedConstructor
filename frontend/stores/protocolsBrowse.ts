import { defineStore } from 'pinia'

export interface ProtocolListItem {
  id: number
  title: string
  year?: number | null
  version?: string | null
  mkb_categories?: string[] | null
}

export const useProtocolsBrowseStore = defineStore('protocolsBrowse', () => {
  const sections = ref<string[]>([])
  const sectionsLoaded = ref(false)
  const selectedSection = ref<string | null>(null)
  const searchQuery = ref('')
  const page = ref(1)
  const protocols = ref<ProtocolListItem[]>([])
  const total = ref(0)
  const scrollTop = ref(0)
  const initialized = ref(false)

  return {
    sections,
    sectionsLoaded,
    selectedSection,
    searchQuery,
    page,
    protocols,
    total,
    scrollTop,
    initialized,
  }
})
