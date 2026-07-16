<script setup lang="ts">
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const open = ref(false)
const tab = ref<'student' | 'teacher' | 'expert'>('student')

type Section = { key: 'student' | 'teacher' | 'expert'; label: string; icon: string; steps: { icon: string; title: string; text: string }[] }

const sections: Section[] = [
  {
    key: 'student',
    label: 'Студент',
    icon: 'mdi-school-outline',
    steps: [
      { icon: 'mdi-clipboard-text-outline', title: '1. Откройте задание', text: 'На «Панели» выберите назначенное вам клиническое задание и прочитайте условие — описание пациента и жалоб.' },
      { icon: 'mdi-graph-outline', title: '2. Постройте граф', text: 'В «Конструкторе» добавляйте узлы: данные пациента, симптомы, обследования, диагноз, лечение, мониторинг. Соединяйте их стрелками: определяет, требует подтверждения, показано, противопоказано, исключает.' },
      { icon: 'mdi-arrow-decision-outline', title: '3. Стройте цепочку рассуждения', text: 'Ведите логику от данных пациента к диагнозу и от диагноза к лечению. Не пропускайте диагностический шаг и обязательно учитывайте противопоказания и опасные альтернативы.' },
      { icon: 'mdi-check-circle-outline', title: '4. Отправьте решение', text: 'Система сравнит ваш граф с эталоном и даст обратную связь: какие узлы и связи пропущены, где нарушена цепочка и есть ли небезопасные действия.' },
    ],
  },
  {
    key: 'teacher',
    label: 'Преподаватель',
    icon: 'mdi-account-tie-outline',
    steps: [
      { icon: 'mdi-auto-fix', title: '1. Сгенерируйте задание', text: 'В «Генераторе задач» выберите клинический протокол — система создаст клинический сценарий и черновик эталонного графа на основе протокола.' },
      { icon: 'mdi-clipboard-check-outline', title: '2. Проверьте эталон', text: 'В «Ревизии задания» слева — условие (Паспорт задания), справа — эталонное решение в клинических блоках. Устраните предупреждения автоаудита, особенно критические и отсутствие противопоказаний.' },
      { icon: 'mdi-publish', title: '3. Опубликуйте', text: 'Подтвердите ответственность за эталон и опубликуйте — задание станет доступно студентам. Назначьте его группам или специальностям.' },
      { icon: 'mdi-chart-box-outline', title: '4. Контроль и аналитика', text: '«Проверка» — сдачи студентов, оценки, комментарии. «Метрики» — бенчмарки RAG, оценки графов и экспертная валидация.' },
    ],
  },
  {
    key: 'expert',
    label: 'Эксперт',
    icon: 'mdi-stethoscope',
    steps: [
      { icon: 'mdi-clipboard-pulse-outline', title: 'Слепая валидация', text: 'В разделе «Слепая валидация» оцените каждый клинический граф по качеству от 0 до 100. Вы НЕ видите оценку системы и тип ошибки — это сохраняет независимость вашего суждения.' },
      { icon: 'mdi-numeric', title: 'Шкала оценки', text: '90–100 — клинически полно, безопасно, логично; 75–89 — мелкие пропуски; 60–74 — важные пробелы; 40–59 — серьёзный дефект рассуждения; 0–39 — небезопасно или пропущено критическое.' },
      { icon: 'mdi-content-save-outline', title: 'Сохраняйте и переходите далее', text: 'Поставьте балл, при желании отметьте клиническую приемлемость и комментарий, затем «Сохранить и далее». Прогресс отображается сверху.' },
      { icon: 'mdi-shield-check-outline', title: 'Экспертная оценка материалов', text: 'В «Экспертной оценке» можно проверять эталоны, задания и сдачи студентов, ставить оценки и метки для калибровки системы.' },
    ],
  },
]

function show() {
  const role = auth.user?.role
  tab.value = role === 'teacher' || role === 'expert' ? role : 'student'
  open.value = true
}
</script>

<template>
  <v-btn icon="mdi-help-circle-outline" variant="text" size="small" aria-label="Помощь" @click="show" />

  <v-dialog v-model="open" max-width="720" scrollable>
    <v-card rounded="lg">
      <v-card-title class="d-flex align-center">
        <v-icon icon="mdi-lifebuoy" color="primary" class="mr-2" />
        Как работать с системой
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Закрыть помощь" @click="open = false" />
      </v-card-title>

      <v-tabs v-model="tab" color="primary" density="comfortable" grow>
        <v-tab v-for="s in sections" :key="s.key" :value="s.key" :prepend-icon="s.icon" class="text-none">
          {{ s.label }}
        </v-tab>
      </v-tabs>

      <v-divider />

      <v-card-text style="max-height: 60vh">
        <v-window v-model="tab">
          <v-window-item v-for="s in sections" :key="s.key" :value="s.key">
            <v-list lines="three" bg-color="transparent">
              <v-list-item v-for="(step, i) in s.steps" :key="i" class="px-0">
                <template #prepend>
                  <v-avatar color="primary" variant="tonal" size="40">
                    <v-icon :icon="step.icon" />
                  </v-avatar>
                </template>
                <v-list-item-title class="font-weight-bold">{{ step.title }}</v-list-item-title>
                <v-list-item-subtitle class="help-text">{{ step.text }}</v-list-item-subtitle>
              </v-list-item>
            </v-list>
          </v-window-item>
        </v-window>
      </v-card-text>

      <v-divider />
      <v-card-actions class="px-4 py-3">
        <v-icon icon="mdi-information-outline" size="small" class="mr-2 text-medium-emphasis" />
        <span class="text-caption text-medium-emphasis">Автоматическая оценка поддерживает, но не заменяет решение преподавателя и эксперта.</span>
        <v-spacer />
        <v-btn color="primary" variant="tonal" @click="open = false">Понятно</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.help-text {
  -webkit-line-clamp: unset !important;
  white-space: normal;
  opacity: 0.9;
}
</style>
