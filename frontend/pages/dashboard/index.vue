<script setup lang="ts">
import type { AssignmentPublic, JsonValue, StudentAttemptPublic, UserPublic } from '~/types/api'
import EmptyState from '~/components/shared/ui/EmptyState.vue'
import ExpandableText from '~/components/shared/ui/ExpandableText.vue'
import MetricCard from '~/components/shared/ui/MetricCard.vue'
import PageHeader from '~/components/shared/ui/PageHeader.vue'
import StatusChip from '~/components/shared/ui/StatusChip.vue'
import { getApiErrorMessage } from '~/utils/apiError'
import { createApiClient } from '~/utils/apiClient'

definePageMeta({ keepalive: true })

type AssignmentRow = AssignmentPublic
type AttemptRow = StudentAttemptPublic
type UserRow = Pick<UserPublic, 'id' | 'role'>

const auth = useAuthStore()
const api = createApiClient()

const loading = ref(true)
const errorText = ref('')
const assignments = ref<AssignmentRow[]>([])
const attempts = ref<AttemptRow[]>([])
const users = ref<UserRow[]>([])
const groupsCount = ref(0)
const specialtiesCount = ref(0)

const isTeacherLike = computed(() => auth.user?.role === 'teacher' || auth.user?.role === 'admin')
const isReviewerLike = computed(() => auth.user?.role === 'teacher' || auth.user?.role === 'expert' || auth.user?.role === 'admin')
const isAdmin = computed(() => auth.user?.role === 'admin')

function metricField(row: AttemptRow, key: string): JsonValue | undefined {
  return row.metrics?.[key]
}

function jsonText(value: JsonValue | undefined): string | null {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

const averageScore = computed(() => {
  const scores = attempts.value
    .map((row) => Number(metricField(row, 'composite_score') ?? metricField(row, 'f1_score')))
    .filter((value) => Number.isFinite(value))
  if (!scores.length) return null
  return scores.reduce((sum, value) => sum + value, 0) / scores.length
})

const pendingAssignments = computed(() =>
  assignments.value.filter((assignment) => assignment.progress_status !== 'completed')
)

const needsReviewCount = computed(() =>
  attempts.value.filter((attempt) =>
    attempt.review_status === 'needs_review' || attempt.review_status === 'revision_requested'
  ).length
)

const riskyAttemptsCount = computed(() =>
  attempts.value.filter((attempt) => Number(metricField(attempt, 'safety_penalty') ?? 0) > 0).length
)

const metricPercent = (value: unknown) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `${Math.round(n * 100)}%`
}

const variantText = (row: AttemptRow) => {
  const variant = jsonText(metricField(row, 'benchmark_variant_id'))
  const pattern = jsonText(metricField(row, 'expected_pattern_ru')) || jsonText(metricField(row, 'expected_pattern'))
  if (variant && pattern) return `${variant} · ${pattern}`
  return variant || pattern || '—'
}

const recommendationText = (row: AttemptRow) => (
  jsonText(metricField(row, 'system_recommendation')) || row.teacher_comment || '—'
)

const statusText = (value?: string | null) => {
  if (value === 'accepted') return 'Принято'
  if (value === 'revision_requested') return 'Нужна доработка'
  return 'Ожидает проверки'
}

const formatDate = (value?: string | null) => {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ru-RU')
}

const assignmentStatusText = (value?: string | null) => {
  if (value === 'published') return 'Опубликовано'
  if (value === 'teacher_approved') return 'Эталон подтверждён'
  if (value === 'needs_teacher_review') return 'На проверке'
  if (value === 'ai_generated') return 'AI-черновик'
  if (value === 'review_ready') return 'На проверке'
  if (value === 'archived') return 'Архив'
  return 'Черновик'
}

const learningStatusText = (value?: string | null) => {
  if (value === 'completed') return 'Выполнено'
  if (value === 'submitted') return 'На проверке'
  if (value === 'in_progress') return 'В процессе'
  if (value === 'needs_revision') return 'Нужна доработка'
  return 'Не выполнено'
}

const assignmentActionText = (assignment: AssignmentRow) => {
  if (assignment.progress_status === 'completed') return 'Открыть'
  if (assignment.progress_status === 'submitted') return 'Смотреть'
  if (assignment.progress_status === 'in_progress' || assignment.progress_status === 'needs_revision') return 'Продолжить'
  return 'Начать'
}

const assignmentActionLink = (assignment: AssignmentRow) => {
  if ((assignment.progress_status === 'completed' || assignment.progress_status === 'submitted') && assignment.latest_attempt_id) {
    return `/student/attempts/${assignment.latest_attempt_id}`
  }
  return `/?assignment=${assignment.id}&start=1`
}

const teacherAttemptHeaders = [
  { title: 'Студент', key: 'student' },
  { title: 'Задание', key: 'assignment_title' },
  { title: 'Вариант', key: 'variant' },
  { title: 'Оценка', key: 'score' },
  { title: 'Рекомендация', key: 'recommendation' },
  { title: 'Статус', key: 'review_status' },
  { title: 'Дата', key: 'created_at' },
  { title: '', key: 'actions', sortable: false, align: 'end' as const },
]

const assignmentHeaders = [
  { title: 'Задание', key: 'title' },
  { title: 'Статус', key: 'status' },
  { title: 'Автор', key: 'creator' },
  { title: 'Описание и клинический контекст', key: 'description', sortable: false },
  { title: 'Эталон', key: 'reference_graph_id' },
  { title: '', key: 'actions', sortable: false, align: 'end' as const },
]

async function loadDashboard() {
  loading.value = true
  errorText.value = ''
  try {
    const assignmentRequest = api.endpoint('GET', '/assignments', { accessToken: auth.accessToken })
    const attemptRequest = isReviewerLike.value
      ? api.endpoint('GET', '/attempts', { accessToken: auth.accessToken })
      : api.endpoint('GET', '/attempts/me', { accessToken: auth.accessToken })
    const [assignmentRes, attemptRes] = await Promise.all([assignmentRequest, attemptRequest])
    assignments.value = assignmentRes.items
    attempts.value = attemptRes.items

    if (isAdmin.value) {
      const [userRes, groupRes, specialtyRes] = await Promise.all([
        api.endpoint('GET', '/admin/users', { accessToken: auth.accessToken }),
        api.endpoint('GET', '/admin/groups', { accessToken: auth.accessToken }),
        api.endpoint('GET', '/admin/specialties', { accessToken: auth.accessToken }),
      ])
      users.value = userRes.items
      groupsCount.value = groupRes.items.length
      specialtiesCount.value = specialtyRes.items.length
    }
  } catch (error) {
    errorText.value = getApiErrorMessage(error, 'Не удалось загрузить рабочую панель')
  } finally {
    loading.value = false
  }
}

onMounted(loadDashboard)
onActivated(() => {
  if (!assignments.value.length && !attempts.value.length) {
    loadDashboard()
  }
})
</script>

<template>
  <v-container fluid class="dashboard-page pa-3 pa-md-6">
    <PageHeader
      :eyebrow="auth.user?.role === 'student' ? 'Студент' : auth.user?.role === 'teacher' ? 'Преподаватель' : auth.user?.role === 'expert' ? 'Эксперт' : 'Администратор'"
      :title="auth.user?.full_name || auth.user?.email || 'Пользователь'"
      :subtitle="auth.user?.role === 'student'
        ? 'Ваши задания, прогресс и последние проверки.'
        : auth.user?.role === 'teacher'
          ? 'Проверка сдач, генерация заданий и контроль качества.'
          : auth.user?.role === 'expert'
            ? 'Независимая оценка эталонных графов, заданий и решений студентов.'
            : 'Пользователи, права доступа и структура учебного процесса.'"
    >
      <template #actions>
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="loadDashboard">
          Обновить
        </v-btn>
      </template>
    </PageHeader>

    <v-alert v-if="errorText" type="error" variant="tonal" rounded="lg" class="mb-4" closable @click:close="errorText = ''">
      {{ errorText }}
    </v-alert>

    <v-row class="mb-2">
      <v-col cols="12" sm="6" lg="3">
        <MetricCard title="Доступные задания" :value="assignments.length" icon="mdi-clipboard-text-outline" />
      </v-col>
      <v-col cols="12" sm="6" lg="3">
        <MetricCard title="Сдачи" :value="attempts.length" icon="mdi-file-check-outline" color="secondary" />
      </v-col>
      <v-col cols="12" sm="6" lg="3">
        <MetricCard title="Средний результат" :value="averageScore == null ? '—' : metricPercent(averageScore)" icon="mdi-chart-line" color="success" />
      </v-col>
      <v-col cols="12" sm="6" lg="3">
        <MetricCard
          :title="isAdmin ? 'Пользователи' : 'Клинические риски'"
          :value="isAdmin ? users.length : riskyAttemptsCount"
          :icon="isAdmin ? 'mdi-account-multiple-outline' : 'mdi-alert-octagon-outline'"
          :color="isAdmin ? 'primary' : 'warning'"
        />
      </v-col>
    </v-row>

    <v-row v-if="loading">
      <v-col v-for="n in 4" :key="n" cols="12" md="6">
        <v-skeleton-loader type="article" class="rounded-lg" />
      </v-col>
    </v-row>

    <template v-else>
      <v-row v-if="auth.user?.role === 'student'">
        <v-col cols="12" lg="7">
          <v-card class="panel" elevation="0">
            <v-card-title class="d-flex align-center">
              Задания
              <v-spacer />
              <v-chip size="small" color="primary" variant="tonal">{{ pendingAssignments.length }} в работе</v-chip>
            </v-card-title>
            <v-card-text>
              <EmptyState
                v-if="!assignments.length"
                icon="mdi-clipboard-search-outline"
                title="Заданий пока нет"
                text="Когда преподаватель назначит задание, оно появится здесь."
              />
              <v-list v-else lines="three" bg-color="transparent">
                <v-list-item v-for="assignment in assignments" :key="assignment.id" class="task-row rounded-lg mb-2">
                  <template #prepend>
                    <v-avatar color="primary" variant="tonal" rounded="lg">
                      <v-icon icon="mdi-graph-outline" />
                    </v-avatar>
                  </template>
                  <v-list-item-title class="font-weight-bold">{{ assignment.title }}</v-list-item-title>
                  <v-list-item-subtitle>
                    <div>{{ assignment.description || 'Описание задания не указано' }}</div>
                    <div class="d-flex align-center ga-2 mt-2 flex-wrap">
                      <StatusChip :status="assignment.progress_status" :text="learningStatusText(assignment.progress_status)" />
                      <v-chip v-if="assignment.latest_score != null" size="small" color="success" variant="tonal">
                        {{ metricPercent(assignment.latest_score) }}
                      </v-chip>
                    </div>
                  </v-list-item-subtitle>
                  <template #append>
                    <v-btn :to="assignmentActionLink(assignment)" color="primary" variant="flat" rounded="pill">
                      {{ assignmentActionText(assignment) }}
                    </v-btn>
                  </template>
                </v-list-item>
              </v-list>
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12" lg="5">
          <v-card class="panel" elevation="0">
            <v-card-title>Последние результаты</v-card-title>
            <v-card-text>
              <EmptyState
                v-if="!attempts.length"
                icon="mdi-chart-line-variant"
                color="secondary"
                title="Проверок пока нет"
                text="Результаты появятся после отправки графа на проверку."
              />
              <v-list v-else bg-color="transparent">
                <v-list-item v-for="attempt in attempts.slice(0, 8)" :key="attempt.id" class="rounded-lg">
                  <v-list-item-title class="font-weight-bold">{{ attempt.assignment_title || 'Задание' }}</v-list-item-title>
                  <v-list-item-subtitle>
                    {{ formatDate(attempt.created_at) }}
                    <span v-if="attempt.teacher_comment"> · есть комментарий</span>
                  </v-list-item-subtitle>
                  <template #append>
                    <div class="d-flex align-center ga-2">
                      <StatusChip :status="attempt.review_status" :text="statusText(attempt.review_status)" />
                      <v-chip color="success" variant="tonal" size="small">
                        {{ metricPercent(metricField(attempt, 'composite_score') ?? metricField(attempt, 'f1_score')) }}
                      </v-chip>
                      <v-btn
                        :to="`/student/attempts/${attempt.id}`"
                        icon="mdi-open-in-new"
                        size="x-small"
                        variant="text"
                        color="primary"
                        aria-label="Открыть результат"
                      />
                    </div>
                  </template>
                </v-list-item>
              </v-list>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <v-row v-else>
        <v-col cols="12" lg="8">
          <v-card class="panel" elevation="0">
            <v-card-title>Последние сдачи</v-card-title>
            <v-card-text>
              <v-data-table
                :headers="teacherAttemptHeaders"
                :items="attempts"
                density="comfortable"
                :items-per-page="10"
              >
                <template #[`item.student`]="{ item }">
                  <div class="font-weight-bold">{{ item.student_name || item.student_email || `Студент #${item.student_id}` }}</div>
                  <div class="text-caption text-medium-emphasis">{{ item.student_email }}</div>
                </template>
                <template #[`item.assignment_title`]="{ item }">{{ item.assignment_title || 'Без задания' }}</template>
                <template #[`item.variant`]="{ item }">
                  <div class="text-body-2">{{ variantText(item) }}</div>
                </template>
                <template #[`item.score`]="{ item }">
                  <v-chip color="success" variant="tonal" size="small">
                    {{ metricPercent(metricField(item, 'composite_score') ?? metricField(item, 'f1_score')) }}
                  </v-chip>
                </template>
                <template #[`item.recommendation`]="{ item }">
                  <ExpandableText
                    :text="recommendationText(item)"
                    title="Рекомендация по сдаче"
                    :lines="2"
                    :min-length="90"
                  />
                </template>
                <template #[`item.review_status`]="{ item }">
                  <StatusChip :status="item.review_status" :text="statusText(item.review_status)" />
                </template>
                <template #[`item.created_at`]="{ item }">{{ formatDate(item.created_at) }}</template>
                <template #[`item.actions`]="{ item }">
                  <v-btn
                    :to="`/student/attempts/${item.id}`"
                    icon="mdi-open-in-new"
                    size="small"
                    variant="text"
                    color="primary"
                    aria-label="Открыть сдачу студента"
                  />
                </template>
              </v-data-table>
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12" lg="4">
          <v-card class="panel mb-4" elevation="0">
            <v-card-title>Быстрые действия</v-card-title>
            <v-card-text class="d-flex flex-column ga-3">
              <v-btn v-if="isTeacherLike" to="/teacher/generator" color="primary" variant="flat" prepend-icon="mdi-auto-fix">
                Создать задание
              </v-btn>
              <v-btn v-if="isTeacherLike" to="/teacher/review" color="success" variant="tonal" prepend-icon="mdi-clipboard-check-outline">
                Проверить/разобрать · {{ needsReviewCount }}
              </v-btn>
              <v-btn v-if="auth.user?.role === 'expert' || isAdmin" to="/expert/review" color="success" variant="tonal" prepend-icon="mdi-stethoscope">
                Экспертная оценка
              </v-btn>
              <v-btn to="/" color="secondary" variant="tonal" prepend-icon="mdi-graph-outline">
                Открыть конструктор
              </v-btn>
              <v-btn v-if="isTeacherLike" to="/teacher/benchmarks" variant="tonal" prepend-icon="mdi-chart-box-outline">
                Метрики качества
              </v-btn>
              <v-btn v-if="isAdmin" to="/admin" variant="tonal" prepend-icon="mdi-shield-account-outline">
                Администрирование
              </v-btn>
            </v-card-text>
          </v-card>

          <v-card v-if="isAdmin" class="panel" elevation="0">
            <v-card-title>Структура</v-card-title>
            <v-card-text>
              <div class="structure-grid">
                <div>
                  <div class="text-caption text-medium-emphasis">Группы</div>
                  <div class="text-h6 font-weight-bold">{{ groupsCount }}</div>
                </div>
                <div>
                  <div class="text-caption text-medium-emphasis">Специальности</div>
                  <div class="text-h6 font-weight-bold">{{ specialtiesCount }}</div>
                </div>
                <div>
                  <div class="text-caption text-medium-emphasis">Преподаватели</div>
                  <div class="text-h6 font-weight-bold">{{ users.filter((u) => u.role === 'teacher').length }}</div>
                </div>
                <div>
                  <div class="text-caption text-medium-emphasis">Эксперты</div>
                  <div class="text-h6 font-weight-bold">{{ users.filter((u) => u.role === 'expert').length }}</div>
                </div>
                <div>
                  <div class="text-caption text-medium-emphasis">Студенты</div>
                  <div class="text-h6 font-weight-bold">{{ users.filter((u) => u.role === 'student').length }}</div>
                </div>
              </div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <v-row v-if="isTeacherLike" class="mt-2">
        <v-col cols="12">
          <v-card class="panel" elevation="0">
            <v-card-title class="d-flex align-center">
              Клинические задачи
              <v-spacer />
              <v-chip size="small" color="primary" variant="tonal">{{ assignments.length }}</v-chip>
            </v-card-title>
            <v-card-text>
              <v-data-table
                :headers="assignmentHeaders"
                :items="assignments"
                density="comfortable"
                class="readable-table"
                :items-per-page="10"
              >
                <template #[`item.title`]="{ item }">
                  <div class="assignment-title-cell font-weight-bold">{{ item.title }}</div>
                </template>
                <template #[`item.status`]="{ item }">
                  <StatusChip :status="item.status" :text="assignmentStatusText(item.status)" />
                </template>
                <template #[`item.creator`]="{ item }">
                  <div>{{ item.created_by_name || item.created_by_email || '—' }}</div>
                  <div class="text-caption text-medium-emphasis">{{ item.created_by_email }}</div>
                </template>
                <template #[`item.description`]="{ item }">
                  <ExpandableText
                    :text="item.description"
                    :title="item.title"
                    :lines="3"
                    :min-length="130"
                    empty-text="Описание не указано"
                  />
                </template>
                <template #[`item.reference_graph_id`]="{ item }">
                  <v-chip size="small" color="secondary" variant="tonal">#{{ item.reference_graph_id }}</v-chip>
                </template>
                <template #[`item.actions`]="{ item }">
                  <div class="d-flex justify-end ga-1">
                    <v-tooltip
                      text="Проверить и доработать эталонный граф"
                      aria-label="Проверить и доработать эталонный граф"
                    >
                      <template #activator="{ props }">
                        <v-btn
                          v-bind="props"
                          :to="`/teacher/assignments/${item.id}`"
                          icon="mdi-pencil-ruler-outline"
                          size="small"
                          variant="text"
                          color="warning"
                          aria-label="Проверить и доработать эталонный граф"
                        />
                      </template>
                    </v-tooltip>
                    <v-tooltip
                      text="Открыть задание в конструкторе"
                      aria-label="Открыть задание в конструкторе"
                    >
                      <template #activator="{ props }">
                        <v-btn
                          v-bind="props"
                          :to="`/?assignment=${item.id}`"
                          icon="mdi-graph-outline"
                          size="small"
                          variant="text"
                          color="primary"
                          aria-label="Открыть задание в конструкторе"
                        />
                      </template>
                    </v-tooltip>
                    <v-tooltip
                      text="Перейти к проверке сдач"
                      aria-label="Перейти к проверке сдач"
                    >
                      <template #activator="{ props }">
                        <v-btn
                          v-bind="props"
                          to="/teacher/review"
                          icon="mdi-clipboard-check-outline"
                          size="small"
                          variant="text"
                          color="success"
                          aria-label="Перейти к проверке сдач"
                        />
                      </template>
                    </v-tooltip>
                  </div>
                </template>
              </v-data-table>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </template>
  </v-container>
</template>

<style scoped>
.dashboard-page {
  max-width: 1440px;
  margin: 0 auto;
}

.panel {
  border: 1px solid rgba(var(--v-border-color), 0.12);
  border-radius: 8px !important;
  background: rgba(var(--v-theme-surface), 0.94) !important;
}

.task-row {
  border: 1px solid rgba(var(--v-border-color), 0.08);
  background: rgba(var(--v-theme-surface-variant), 0.34);
}

.structure-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.structure-grid > div {
  border: 1px solid rgba(var(--v-border-color), 0.1);
  border-radius: 8px;
  padding: 12px;
  background: rgba(var(--v-theme-surface-variant), 0.4);
}

.assignment-title-cell {
  max-width: 34ch;
  line-height: 1.35;
  overflow-wrap: anywhere;
  white-space: normal;
}

.dashboard-page :deep(.readable-table .v-data-table__td) {
  vertical-align: top;
  white-space: normal;
}

</style>
