<script setup lang="ts">
import { useAuthStore } from '~/stores/auth'
import { applyAutoLayout } from '~/composables/useGraphLayout'
import { normalizeFlowEdges } from '~/composables/useGraphPayload'

definePageMeta({
  middleware: 'teacher',
  keepalive: true,
})

const { v1 } = useApi()
const auth = useAuthStore()
const gen = useTeacherGeneratorStore()

const loading = ref(false)

async function fetchProtocols() {
  if (gen.protocolsLoaded) return
  try {
    const res = await $fetch<{ items: any[] }>(v1('/protocols?limit=5000'))
    gen.protocols = res.items || []
    gen.protocolsLoaded = true
  } catch (e) {
    console.error(e)
  }
}

onMounted(() => {
  fetchProtocols()
  fetchPalette()
})

// Step 2: Scenarios — persisted in store via keepalive + gen store

async function generateScenarios() {
  if (!gen.selectedProtocols.length) return
  loading.value = true
  try {
    const res = await $fetch<any>(v1('/rag/scenarios'), {
      method: 'POST',
      body: { protocol_ids: gen.selectedProtocols },
      headers: auth.accessToken ? { Authorization: `Bearer ${auth.accessToken}` } : {},
    })
    gen.scenarios = res.scenarios || []
    gen.currentStep = 2
  } catch (e: any) {
    alert(e.message || 'Ошибка генерации сценариев')
  } finally {
    loading.value = false
  }
}

// Step 3: Graph
const nodes = ref<any[]>([])
const edges = ref<any[]>([])
const palette = ref<any[]>([])
const generationContext = ref<any[]>([])
const validationWarnings = ref<string[]>([])

async function fetchPalette() {
  try {
    const r = await $fetch<{ items: any[] }>(v1('/concepts/palette?per_category=10'))
    palette.value = (r.items || []).map((i) => ({ label: i.label, category: i.category.toUpperCase() }))
  } catch (e) {
    console.error(e)
  }
}

async function selectScenario(scenario: any) {
  gen.selectedScenario = scenario
  loading.value = true
  try {
    const res = await $fetch<any>(v1('/rag/reference-graph'), {
      method: 'POST',
      body: { 
        protocol_ids: gen.selectedProtocols,
        scenario_title: scenario.title,
        scenario_description: scenario.description
      },
      headers: auth.accessToken ? { Authorization: `Bearer ${auth.accessToken}` } : {},
    })
    
    const graph = res.graph
    generationContext.value = res.generation_context || []
    validationWarnings.value = res.validation_warnings || []
    if (graph && graph.nodes) {
      const mappedNodes = graph.nodes.map((n: any) => ({
        ...n,
        type: n.type === 'frame' ? 'frame' : 'med'
      }))
      const mappedEdges = normalizeFlowEdges(graph.edges || [])
      nodes.value = applyAutoLayout(mappedNodes, mappedEdges)
      edges.value = mappedEdges
    }
    gen.currentStep = 3
  } catch (e: any) {
    alert(e.message || 'Ошибка генерации графа')
  } finally {
    loading.value = false
  }
}

const tableHeaders = [
  { title: 'ID', key: 'id', sortable: true },
  { title: 'Название', key: 'title', sortable: true },
  { title: 'Версия', key: 'version', sortable: true },
  { title: 'Год', key: 'year', sortable: true },
  { title: 'МКБ Категории', key: 'mkb_categories', sortable: false },
  { title: 'Разделы', key: 'medical_sections', sortable: false },
]

// Step 4: Save draft for human review
async function publishAssignment() {
  if (!gen.selectedScenario) return
  loading.value = true
  try {
    const graphData = {
      nodes: nodes.value,
      edges: edges.value
    }
    
    const created = await $fetch<{ id: number }>(v1('/assignments/from-rag'), {
      method: 'POST',
      body: {
        title: gen.selectedScenario.title,
        description: gen.selectedScenario.description,
        time_limit_minutes: gen.timeLimitMinutes,
        graph_data: graphData,
        generation_context: generationContext.value,
        validation_warnings: validationWarnings.value,
      },
      headers: auth.accessToken ? { Authorization: `Bearer ${auth.accessToken}` } : {},
    })
    
    alert('Черновик сохранен. Проверьте и доработайте эталонный граф перед публикацией.')
    navigateTo(`/teacher/assignments/${created.id}`)
  } catch (e: any) {
    alert(e.message || 'Ошибка сохранения черновика')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <v-container class="mt-4 max-w-6xl">
    <div class="d-flex align-center mb-6">
      <v-icon icon="mdi-auto-fix" color="primary" size="large" class="mr-3" />
      <h1 class="text-h5 font-weight-bold">Генератор клинических задач (ИИ)</h1>
    </div>

    <!-- Instructions -->
    <v-alert
      color="info"
      variant="tonal"
      class="mb-6 rounded-lg text-body-2"
      icon="mdi-information-outline"
    >
      <p class="font-weight-bold mb-2">Как работает генератор:</p>
      <ol class="pl-4">
        <li class="mb-1"><strong>Выбор протоколов:</strong> Выберите один или несколько клинических протоколов МЗ РК из базы. ИИ изучит их содержимое.</li>
        <li class="mb-1"><strong>Генерация сценариев:</strong> ИИ предложит несколько вариантов клинических случаев (анамнез, жалобы, объективные данные).</li>
        <li class="mb-1"><strong>Эталонный граф:</strong> После выбора сценария, ИИ автоматически построит эталонный граф (правильный ответ). Вы сможете отредактировать его на холсте.</li>
        <li><strong>Публикация:</strong> Сначала сохраните AI-черновик, затем на странице ревизии проверьте и подтвердите эталонный граф. Только после этого задание можно опубликовать студентам.</li>
      </ol>
    </v-alert>

    <v-stepper v-model="gen.currentStep" class="elevation-1 rounded-lg">
      <v-stepper-header>
        <v-stepper-item title="Протоколы" :value="1" :complete="gen.currentStep > 1" />
        <v-divider />
        <v-stepper-item title="Сценарии" :value="2" :complete="gen.currentStep > 2" />
        <v-divider />
        <v-stepper-item title="Эталонный граф" :value="3" />
      </v-stepper-header>

      <v-stepper-window>
        <!-- Step 1 -->
        <v-stepper-window-item :value="1">
          <v-card flat>
            <v-card-text>
              <p class="text-body-1 mb-4">Выберите протоколы, на основе которых нужно создать задание:</p>
              
              <v-data-table
                v-model="gen.selectedProtocols"
                :items="gen.protocols"
                :headers="tableHeaders"
                item-value="id"
                show-select
                class="border rounded-lg"
              >
                <template #item.title="{ item }">
                  <strong>{{ item.title }}</strong>
                  <div class="text-caption text-slate-500">{{ item.version || 'Не указана' }}</div>
                </template>
                <template #item.mkb_categories="{ item }">
                  <div class="d-flex flex-wrap gap-1 my-1">
                    <v-chip v-for="(cat, idx) in item.mkb_categories" :key="idx" size="small" variant="tonal" color="primary">
                      {{ cat }}
                    </v-chip>
                  </div>
                </template>
                <template #item.medical_sections="{ item }">
                  <div class="d-flex flex-wrap gap-1 my-1">
                    <v-chip v-for="(sec, idx) in item.medical_sections" :key="idx" size="small" variant="tonal" color="secondary">
                      {{ sec }}
                    </v-chip>
                  </div>
                </template>
              </v-data-table>
            </v-card-text>
            <v-card-actions class="px-4 pb-4">
              <v-spacer />
              <v-btn
                color="primary"
                variant="flat"
                :disabled="!gen.selectedProtocols.length"
                :loading="loading"
                @click="generateScenarios"
              >
                Далее: Сгенерировать сценарии
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-stepper-window-item>

        <!-- Step 2 -->
        <v-stepper-window-item :value="2">
          <v-card flat>
            <v-card-text>
              <p class="text-body-1 mb-4">ИИ сгенерировал следующие сценарии. Выберите один из них:</p>
              
              <v-row>
                <v-col v-for="(sc, i) in gen.scenarios" :key="i" cols="12" md="6">
                  <v-card variant="outlined" hover class="h-100 d-flex flex-column" :disabled="loading" @click="selectScenario(sc)">
                    <v-card-title class="text-subtitle-1 font-weight-bold text-primary" style="white-space: normal;">
                      {{ sc.title }}
                    </v-card-title>
                    <v-card-text class="text-body-2 flex-grow-1">
                      {{ sc.description }}
                    </v-card-text>
                    <v-card-actions>
                      <v-btn color="primary" variant="text" block :loading="loading && gen.selectedScenario?.title === sc.title">
                        Выбрать этот сценарий
                      </v-btn>
                    </v-card-actions>
                  </v-card>
                </v-col>
              </v-row>
            </v-card-text>
            <v-card-actions class="px-4 pb-4">
              <v-btn variant="text" @click="gen.currentStep = 1">Назад</v-btn>
            </v-card-actions>
          </v-card>
        </v-stepper-window-item>

        <!-- Step 3 -->
        <v-stepper-window-item :value="3">
          <v-card flat>
            <v-card-text class="pa-0">
              <v-sheet class="pa-4 bg-blue-grey-lighten-5 border-b">
                <div class="d-flex align-center gap-2 mb-2">
                  <h3 class="text-subtitle-1 font-weight-bold">{{ gen.selectedScenario?.title }}</h3>
                  <v-chip v-if="generationContext.length" color="success" size="small" variant="tonal">
                    Проверен по протоколу
                  </v-chip>
                </div>
                <p class="text-body-2">{{ gen.selectedScenario?.description }}</p>
                <v-text-field
                  v-model.number="gen.timeLimitMinutes"
                  class="mt-3"
                  label="Лимит времени для студента (минуты)"
                  type="number"
                  min="5"
                  max="1440"
                  variant="outlined"
                  density="comfortable"
                  hint="ИИ и преподаватель могут задать ограничение по времени на выполнение"
                  persistent-hint
                  clearable
                />
                <v-alert v-if="validationWarnings.length" type="warning" variant="tonal" density="compact" class="mt-3">
                  {{ validationWarnings.join('; ') }}
                </v-alert>
                <v-expansion-panels v-if="generationContext.length" class="mt-3" variant="accordion">
                  <v-expansion-panel title="Источники протокола">
                    <v-expansion-panel-text>
                      <div v-for="(src, i) in generationContext" :key="i" class="text-caption mb-2">
                        <strong>{{ src.protocol_title }}</strong> — {{ src.section || 'секция' }}
                      </div>
                    </v-expansion-panel-text>
                  </v-expansion-panel>
                </v-expansion-panels>
              </v-sheet>
              
              <div style="height: 60vh; width: 100%; position: relative;">
                <ClientOnly>
                  <GraphFlow v-model:nodes="nodes" v-model:edges="edges" :palette="palette" />
                </ClientOnly>
              </div>
            </v-card-text>
            
            <v-card-actions class="pa-4 bg-white border-t">
              <v-btn variant="text" @click="gen.currentStep = 2">Назад</v-btn>
              <v-btn variant="outlined" color="primary" :loading="loading" :disabled="!gen.selectedScenario" @click="selectScenario(gen.selectedScenario)">
                Перегенерировать
              </v-btn>
              <v-spacer />
              <v-btn
                color="success"
                variant="flat"
                size="large"
                :loading="loading"
                @click="publishAssignment"
              >
                <v-icon start>mdi-check-circle</v-icon>
                Сохранить черновик
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-stepper-window-item>
      </v-stepper-window>
    </v-stepper>
  </v-container>
</template>

<style scoped>
.max-w-6xl {
  max-width: 1200px;
  margin: 0 auto;
}
</style>
