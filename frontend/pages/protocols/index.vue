<script setup lang="ts">
definePageMeta({ keepalive: true })

const { v1 } = useApi()
const browse = useProtocolsBrowseStore()

const loading = ref(false)
const refreshing = ref(false)
const itemsPerPage = 20
const listRef = ref<HTMLElement | null>(null)
const sectionsDrawer = ref(false)

const debouncedSearch = useDebouncedRef(toRef(browse, 'searchQuery'), 350)

let fetchSeq = 0

const fetchSections = async () => {
  if (browse.sectionsLoaded) return
  try {
    browse.sections = await $fetch<string[]>(v1('/protocols/sections'))
    browse.sectionsLoaded = true
  } catch (e) {
    console.error('Failed to fetch sections', e)
  }
}

const fetchProtocols = async () => {
  const seq = ++fetchSeq
  const isInitial = browse.protocols.length === 0
  if (isInitial) loading.value = true
  else refreshing.value = true

  try {
    const skip = (browse.page - 1) * itemsPerPage
    const query = new URLSearchParams({
      skip: skip.toString(),
      limit: itemsPerPage.toString(),
    })

    if (browse.selectedSection) {
      query.append('section', browse.selectedSection)
    }
    if (debouncedSearch.value) {
      query.append('q', debouncedSearch.value)
    }

    const res = await $fetch<{ items: any[]; total: number }>(v1(`/protocols?${query.toString()}`))
    if (seq !== fetchSeq) return

    browse.protocols = res.items
    browse.total = res.total
    browse.initialized = true
  } catch (e) {
    if (seq === fetchSeq) console.error('Failed to fetch protocols', e)
  } finally {
    if (seq === fetchSeq) {
      loading.value = false
      refreshing.value = false
    }
  }
}

const selectSection = (section: string | null) => {
  browse.selectedSection = section
  browse.page = 1
  sectionsDrawer.value = false
}

watch(debouncedSearch, () => {
  browse.page = 1
  fetchProtocols()
})

watch(() => browse.selectedSection, () => {
  browse.page = 1
  fetchProtocols()
})

watch(() => browse.page, () => {
  fetchProtocols()
  listRef.value?.scrollTo({ top: 0, behavior: 'smooth' })
})

onMounted(() => {
  fetchSections()
  if (!browse.initialized) fetchProtocols()
})

onDeactivated(() => {
  if (listRef.value) browse.scrollTop = listRef.value.scrollTop
})

onActivated(() => {
  nextTick(() => {
    if (listRef.value && browse.scrollTop > 0) {
      listRef.value.scrollTop = browse.scrollTop
    }
  })
})

const pageCount = computed(() => Math.max(1, Math.ceil(browse.total / itemsPerPage)))
</script>

<template>
  <v-container fluid class="protocols-page pa-3 pa-sm-4 pa-md-8">
    <v-row class="protocols-layout">
      <!-- Desktop sidebar -->
      <v-col cols="12" md="3" class="d-none d-md-flex flex-column protocols-sidebar">
        <v-card class="surface-card d-flex flex-column h-100 rounded-xl" elevation="0" border>
          <v-card-title class="text-subtitle-1 font-weight-bold px-5 pt-5 pb-2">Разделы медицины</v-card-title>
          <v-card-text class="pa-2 overflow-auto flex-grow-1 smooth-scroll">
            <v-list density="compact" bg-color="transparent" nav>
              <v-list-item
                title="Все протоколы"
                :active="browse.selectedSection === null"
                color="primary"
                rounded="lg"
                class="mb-1"
                prepend-icon="mdi-format-list-bulleted"
                @click="selectSection(null)"
              />
              <v-divider class="my-2" />
              <v-list-item
                v-for="section in browse.sections"
                :key="section"
                :title="section"
                :active="browse.selectedSection === section"
                color="primary"
                rounded="lg"
                class="mb-1"
                prepend-icon="mdi-folder-outline"
                @click="selectSection(section)"
              />
            </v-list>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Main content -->
      <v-col cols="12" md="9" class="d-flex flex-column protocols-main">
        <div class="protocols-toolbar mb-4 mb-md-6">
          <div class="protocols-toolbar__head">
            <h1 class="text-h5 text-md-h4 font-weight-bold mb-1 text-wrap">
              {{ browse.selectedSection || 'Клинические протоколы' }}
            </h1>
            <div class="text-body-2 font-weight-medium text-medium-emphasis">
              Найдено: {{ browse.total }}
            </div>
          </div>

          <div class="protocols-toolbar__controls">
            <v-btn
              class="d-md-none flex-shrink-0"
              variant="tonal"
              color="primary"
              prepend-icon="mdi-filter-variant"
              @click="sectionsDrawer = true"
            >
              Раздел
            </v-btn>

            <v-text-field
              v-model="browse.searchQuery"
              prepend-inner-icon="mdi-magnify"
              placeholder="Поиск по названию..."
              variant="solo-filled"
              density="comfortable"
              hide-details
              clearable
              flat
              rounded="lg"
              class="search-input flex-grow-1"
            />
          </div>
        </div>

        <v-progress-linear
          v-if="refreshing"
          indeterminate
          color="primary"
          height="2"
          class="mb-2 flex-shrink-0"
          rounded
        />

        <div ref="listRef" class="protocols-list smooth-scroll flex-grow-1">
          <div v-if="loading" class="protocols-skeleton">
            <v-skeleton-loader
              v-for="n in 6"
              :key="n"
              type="article"
              class="mb-4 rounded-xl"
            />
          </div>

          <div v-else-if="browse.protocols.length === 0" class="protocols-empty">
            <v-icon icon="mdi-file-search-outline" size="56" color="surface-variant" class="mb-3" />
            <div class="text-h6">Протоколы не найдены</div>
            <div class="text-body-2 text-medium-emphasis">Попробуйте изменить поисковый запрос</div>
          </div>

          <v-row v-else class="protocols-grid">
            <v-col
              v-for="protocol in browse.protocols"
              :key="protocol.id"
              cols="12"
              sm="6"
              xl="6"
            >
              <v-card
                class="protocol-card rounded-xl h-100 d-flex flex-column"
                elevation="0"
                border
                hover
                :to="`/protocols/${protocol.id}`"
              >
                <v-card-item class="pb-2">
                  <v-card-title class="text-subtitle-1 text-sm-h6 font-weight-bold text-wrap line-height-normal mb-2">
                    {{ protocol.title }}
                  </v-card-title>
                  <v-card-subtitle class="d-flex align-center flex-wrap gap-2 opacity-100">
                    <v-chip v-if="protocol.year" size="small" color="primary" variant="tonal" class="font-weight-bold">
                      {{ protocol.year }}
                    </v-chip>
                    <span class="text-caption font-weight-medium text-medium-emphasis">
                      {{ protocol.version || 'Версия не указана' }}
                    </span>
                  </v-card-subtitle>
                </v-card-item>

                <v-spacer />

                <v-card-text v-if="protocol.mkb_categories?.length" class="pt-2">
                  <div class="d-flex flex-wrap gap-1">
                    <v-chip
                      v-for="(cat, i) in protocol.mkb_categories.slice(0, 3)"
                      :key="i"
                      size="x-small"
                      color="secondary"
                      variant="outlined"
                      class="text-uppercase font-weight-medium"
                    >
                      {{ cat }}
                    </v-chip>
                    <v-chip
                      v-if="protocol.mkb_categories.length > 3"
                      size="x-small"
                      variant="text"
                      class="font-weight-bold text-medium-emphasis"
                    >
                      +{{ protocol.mkb_categories.length - 3 }}
                    </v-chip>
                  </div>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
        </div>

        <div v-if="browse.total > itemsPerPage" class="protocols-pagination pt-3 pt-md-4">
          <v-pagination
            v-model="browse.page"
            :length="pageCount"
            :total-visible="$vuetify.display.smAndDown ? 5 : 7"
            density="comfortable"
            color="primary"
            rounded="circle"
          />
        </div>
      </v-col>
    </v-row>

    <v-navigation-drawer
      v-model="sectionsDrawer"
      temporary
      location="left"
      width="300"
      class="d-md-none"
    >
      <v-toolbar density="compact" color="surface">
        <v-toolbar-title class="text-subtitle-1 font-weight-bold">Разделы</v-toolbar-title>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" @click="sectionsDrawer = false" />
      </v-toolbar>
      <v-list nav density="comfortable" class="smooth-scroll">
        <v-list-item
          title="Все протоколы"
          :active="browse.selectedSection === null"
          color="primary"
          rounded="lg"
          prepend-icon="mdi-format-list-bulleted"
          @click="selectSection(null)"
        />
        <v-divider class="my-2" />
        <v-list-item
          v-for="section in browse.sections"
          :key="section"
          :title="section"
          :active="browse.selectedSection === section"
          color="primary"
          rounded="lg"
          prepend-icon="mdi-folder-outline"
          @click="selectSection(section)"
        />
      </v-list>
    </v-navigation-drawer>
  </v-container>
</template>

<style scoped>
.protocols-page {
  max-width: 1400px;
  margin: 0 auto;
  min-height: calc(100dvh - 64px);
}

.protocols-layout {
  min-height: calc(100dvh - 96px);
}

.protocols-sidebar {
  max-height: calc(100dvh - 96px);
  position: sticky;
  top: 80px;
}

.protocols-main {
  min-height: 0;
  max-height: calc(100dvh - 96px);
}

.protocols-toolbar {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.protocols-toolbar__controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
}

.protocols-list {
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 200px;
  padding-right: 4px;
  contain: layout style;
}

.protocols-skeleton,
.protocols-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 280px;
  padding: 2rem 1rem;
}

.protocols-grid {
  margin-top: 0;
}

.protocol-card {
  background-color: rgb(var(--v-theme-surface)) !important;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
  border: 1px solid rgba(var(--v-border-color), 0.08) !important;
  will-change: transform;
}

.protocol-card:hover {
  transform: translateY(-2px);
  border-color: rgba(var(--v-theme-primary), 0.25) !important;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06) !important;
}

.surface-card {
  background-color: rgba(var(--v-theme-surface), 0.88) !important;
  backdrop-filter: blur(8px);
}

.search-input :deep(.v-field) {
  border-radius: 12px;
  background-color: rgba(var(--v-theme-surface), 0.9) !important;
}

.line-height-normal {
  line-height: 1.4 !important;
}

.smooth-scroll {
  scroll-behavior: smooth;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
}

@media (min-width: 960px) {
  .protocols-toolbar {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
  }

  .protocols-toolbar__controls {
    max-width: 420px;
    flex-shrink: 0;
  }
}

@media (max-width: 599px) {
  .protocols-main {
    max-height: none;
  }

  .protocols-list {
    max-height: none;
  }
}
</style>
