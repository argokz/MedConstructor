<script setup lang="ts">
import MarkdownIt from 'markdown-it'

const route = useRoute()
const { v1 } = useApi()

const md = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true
})

const protocol = ref<any>(null)
const loading = ref(true)
const error = ref<string | null>(null)

const fetchProtocol = async () => {
  loading.value = true
  try {
    protocol.value = await $fetch(v1(`/protocols/${route.params.id}`))
  } catch (e: any) {
    console.error('Failed to fetch protocol', e)
    error.value = e?.message || 'Не удалось загрузить протокол'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchProtocol()
})

// Format text content slightly to make it more readable
const formattedContent = computed(() => {
  if (!protocol.value?.text_content) return ''
  // Use markdown-it to parse
  return md.render(protocol.value.text_content)
})
</script>

<template>
  <v-container class="pa-0 pa-md-4 h-100 d-flex flex-column align-center" fluid>
    <div class="w-100 px-4 px-md-0 mb-4" style="max-width: 900px; margin-top: 1rem;">
      <v-btn to="/protocols" variant="text" prepend-icon="mdi-arrow-left" class="text-none font-weight-medium px-2 rounded-lg" color="primary">
        Назад к списку
      </v-btn>
    </div>

    <v-card 
      class="surface-card flex-grow-1 w-100 d-flex flex-column overflow-hidden rounded-0 rounded-md-xl" 
      elevation="0"
      border
      style="max-width: 900px;"
    >
      <div v-if="loading" class="d-flex justify-center align-center flex-grow-1" style="min-height: 400px;">
        <v-progress-circular indeterminate color="primary" size="48" width="4" />
      </div>
      
      <div v-else-if="error" class="d-flex flex-column justify-center align-center flex-grow-1 text-medium-emphasis p-8">
        <v-icon icon="mdi-alert-circle-outline" size="64" color="error" class="mb-4" />
        <div class="text-h6 text-error">{{ error }}</div>
      </div>
      
      <template v-else-if="protocol">
        <!-- Header -->
        <v-card-item class="protocol-header pa-6 pa-md-8 border-b">
          <v-card-title class="text-h4 font-weight-black text-wrap line-height-tight mb-4">
            {{ protocol.title }}
          </v-card-title>
          
          <div class="d-flex flex-wrap align-center gap-3 text-body-2 mb-4">
            <v-chip v-if="protocol.year" color="primary" variant="flat" size="small" class="font-weight-bold">
              {{ protocol.year }}
            </v-chip>
            <v-chip v-if="protocol.version" variant="tonal" size="small">
              {{ protocol.version }}
            </v-chip>
            <div class="font-weight-medium opacity-60">
              ID протокола: {{ protocol.external_id || protocol.id }}
            </div>
          </div>
          <div v-if="protocol.mkb_categories?.length || protocol.medical_sections?.length">
            <div class="d-flex flex-wrap gap-2">
              <v-chip v-for="sec in protocol.medical_sections" :key="sec" size="small" color="secondary" variant="tonal" prepend-icon="mdi-folder">
                {{ sec }}
              </v-chip>
              <v-chip v-for="cat in protocol.mkb_categories" :key="cat" size="small" color="primary" variant="tonal" class="text-uppercase font-weight-bold">
                {{ cat }}
              </v-chip>
            </div>
          </div>
        </v-card-item>

        <!-- Sticky Action Bar (Desktop) or Floating (Mobile) -->
        <div class="px-6 px-md-8 py-3 border-b d-flex align-center justify-space-between sticky-action-bar">
          <div class="text-body-2 font-weight-bold text-primary d-none d-sm-block">
            <v-icon icon="mdi-sparkles" size="small" class="mr-2 text-primary" />
            Изучите этот протокол с помощью ИИ
          </div>
          <v-btn 
            color="primary" 
            variant="elevated" 
            :to="`/rag?protocol=${protocol.id}`" 
            prepend-icon="mdi-brain"
            rounded="pill"
            class="ml-auto flex-grow-1 flex-sm-grow-0 font-weight-bold text-none"
            elevation="2"
          >
            Задать вопрос ИИ
          </v-btn>
        </div>

        <!-- Protocol Content -->
        <v-card-text class="flex-grow-1 overflow-auto pa-6 pa-md-10 protocol-content">
          <!-- MarkdownIt is configured with raw HTML disabled. -->
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div v-html="formattedContent" />
        </v-card-text>
      </template>
    </v-card>
  </v-container>
</template>

<style scoped>
.surface-card {
  background-color: rgba(var(--v-theme-surface), 0.9) !important;
  backdrop-filter: blur(10px);
}
.protocol-header {
  background-color: rgb(var(--v-theme-surface));
}
.sticky-action-bar {
  position: sticky;
  top: 0;
  z-index: 10;
  background-color: rgba(var(--v-theme-surface), 0.95) !important;
  backdrop-filter: blur(8px);
  border-bottom: 1px solid rgba(var(--v-theme-primary), 0.08) !important;
}
.line-height-tight {
  line-height: 1.25 !important;
  letter-spacing: -0.02em !important;
}
.gap-2 { gap: 0.5rem; }
.gap-3 { gap: 0.75rem; }

/* Markdown Content Typography specifically optimized for reading */
.protocol-content {
  font-family: var(--serif-font-family);
  line-height: 1.7;
  font-size: 1.15rem;
  color: #1e293b;
}

.protocol-content :deep(h1),
.protocol-content :deep(h2),
.protocol-content :deep(h3),
.protocol-content :deep(h4) {
  font-family: var(--app-font-family);
  font-weight: 700;
  margin-top: 2rem;
  margin-bottom: 1rem;
  color: #0f172a;
  line-height: 1.3;
}

.protocol-content :deep(h1) { font-size: 2rem; border-bottom: 1px solid rgba(var(--v-border-color), 0.1); padding-bottom: 0.5rem; }
.protocol-content :deep(h2) { font-size: 1.75rem; }
.protocol-content :deep(h3) { font-size: 1.4rem; }

.protocol-content :deep(p) {
  margin-bottom: 1.5rem;
}

.protocol-content :deep(ul),
.protocol-content :deep(ol) {
  margin-bottom: 1.5rem;
  padding-left: 2rem;
}

.protocol-content :deep(li) {
  margin-bottom: 0.5rem;
}

.protocol-content :deep(strong) {
  font-weight: 700;
  color: #000;
}

.protocol-content :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 12px;
  margin: 2rem auto;
  display: block;
  box-shadow: 0 4px 20px rgba(0,0,0,0.05);
}

.protocol-content :deep(table) {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  margin: 2rem 0;
  overflow-x: auto;
  display: block;
  font-family: var(--app-font-family);
  font-size: 0.95rem;
}

.protocol-content :deep(th), 
.protocol-content :deep(td) {
  border: 1px solid rgba(var(--v-border-color), 0.1);
  padding: 12px 16px;
}

.protocol-content :deep(th) {
  background-color: rgba(var(--v-theme-surface-variant), 0.8);
  font-weight: 600;
  text-align: left;
}

.protocol-content :deep(tr:first-child th:first-child) { border-top-left-radius: 8px; }
.protocol-content :deep(tr:first-child th:last-child) { border-top-right-radius: 8px; }
</style>
