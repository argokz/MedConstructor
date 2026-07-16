<script setup lang="ts">
import type { AssignmentPublic, SpecialtyPublic, StudentGroupPublic, UserPublic, UserRole } from '~/types/api'
import EmptyState from '~/components/shared/ui/EmptyState.vue'
import MetricCard from '~/components/shared/ui/MetricCard.vue'
import PageHeader from '~/components/shared/ui/PageHeader.vue'
import { getApiErrorMessage } from '~/utils/apiError'
import { createApiClient } from '~/utils/apiClient'

definePageMeta({
  middleware: 'admin',
  keepalive: true,
})

type Role = UserRole
type Specialty = SpecialtyPublic
type StudentGroup = StudentGroupPublic
type UserRow = UserPublic
type AssignmentRow = AssignmentPublic

const auth = useAuthStore()
const api = createApiClient()

const activeTab = ref('users')
const loading = ref(false)
const busy = ref<string | null>(null)
const errorText = ref('')
const notice = ref('')

const users = ref<UserRow[]>([])
const specialties = ref<Specialty[]>([])
const groups = ref<StudentGroup[]>([])
const assignments = ref<AssignmentRow[]>([])

const newSpecialty = reactive({ name: '', code: '', description: '' })
const newGroup = reactive({ name: '', specialty_id: null as number | null, year: new Date().getFullYear() })
const newUser = reactive({
  email: '',
  password: '',
  full_name: '',
  role: 'student' as Role,
  specialty_id: null as number | null,
  group_id: null as number | null,
})

const selectedAssignmentId = ref<number | null>(null)
const selectedSpecialtyTargets = ref<number[]>([])
const selectedGroupTargets = ref<number[]>([])

const roleItems = [
  { title: 'Студент', value: 'student' },
  { title: 'Преподаватель', value: 'teacher' },
  { title: 'Эксперт', value: 'expert' },
  { title: 'Администратор', value: 'admin' },
]

const specialtyItems = computed(() => specialties.value.map((item) => ({
  title: item.code ? `${item.name} (${item.code})` : item.name,
  value: item.id,
})))

const groupItems = computed(() => groups.value.map((item) => ({
  title: item.name,
  value: item.id,
})))

const selectedAssignment = computed(() =>
  assignments.value.find((item) => item.id === selectedAssignmentId.value) || null
)

const userHeaders = [
  { title: 'Пользователь', key: 'email' },
  { title: 'Роль', key: 'role' },
  { title: 'Специальность', key: 'specialty_id' },
  { title: 'Группа', key: 'group_id' },
  { title: '', key: 'actions', sortable: false, align: 'end' as const },
]

const assignmentHeaders = [
  { title: 'Задание', key: 'title' },
  { title: 'Назначено', key: 'targets' },
  { title: '', key: 'actions', sortable: false, align: 'end' as const },
]

function specialtyName(id?: number | null) {
  if (!id) return 'Не указана'
  return specialties.value.find((item) => item.id === id)?.name || `#${id}`
}

function groupName(id?: number | null) {
  if (!id) return 'Не указана'
  return groups.value.find((item) => item.id === id)?.name || `#${id}`
}

function assignmentTargetText(row: AssignmentRow) {
  if (!row.targets?.length) return 'Все студенты'
  return row.targets
    .map((target) => target.group_id ? groupName(target.group_id) : specialtyName(target.specialty_id))
    .join(', ')
}

async function withBusy(key: string, task: () => Promise<void>, success?: string) {
  busy.value = key
  errorText.value = ''
  notice.value = ''
  try {
    await task()
    if (success) notice.value = success
  } catch (error) {
    errorText.value = getApiErrorMessage(error, 'Операция не выполнена')
  } finally {
    busy.value = null
  }
}

async function loadAdminData() {
  loading.value = true
  errorText.value = ''
  try {
    const [usersRes, specRes, groupRes, assignmentRes] = await Promise.all([
      api.endpoint('GET', '/admin/users', { accessToken: auth.accessToken }),
      api.endpoint('GET', '/admin/specialties', { accessToken: auth.accessToken }),
      api.endpoint('GET', '/admin/groups', { accessToken: auth.accessToken }),
      api.endpoint('GET', '/assignments', { accessToken: auth.accessToken }),
    ])
    users.value = usersRes.items
    specialties.value = specRes.items
    groups.value = groupRes.items
    assignments.value = assignmentRes.items
    if (!selectedAssignmentId.value && assignments.value.length) {
      pickAssignment(assignments.value[0])
    }
  } catch (error) {
    errorText.value = getApiErrorMessage(error, 'Не удалось загрузить админские данные')
  } finally {
    loading.value = false
  }
}

function pickAssignment(row: AssignmentRow) {
  selectedAssignmentId.value = row.id
  selectedSpecialtyTargets.value = row.targets.filter((t) => t.specialty_id).map((t) => Number(t.specialty_id))
  selectedGroupTargets.value = row.targets.filter((t) => t.group_id).map((t) => Number(t.group_id))
}

async function createSpecialty() {
  if (!newSpecialty.name.trim()) return
  await withBusy('specialty', async () => {
    await api.endpoint('POST', '/admin/specialties', {
      accessToken: auth.accessToken,
      body: {
        name: newSpecialty.name,
        code: newSpecialty.code || null,
        description: newSpecialty.description || null,
      },
    })
    newSpecialty.name = ''
    newSpecialty.code = ''
    newSpecialty.description = ''
    await loadAdminData()
  }, 'Специальность создана')
}

async function createGroup() {
  if (!newGroup.name.trim()) return
  await withBusy('group', async () => {
    await api.endpoint('POST', '/admin/groups', {
      accessToken: auth.accessToken,
      body: {
        name: newGroup.name,
        specialty_id: newGroup.specialty_id,
        year: newGroup.year || null,
      },
    })
    newGroup.name = ''
    await loadAdminData()
  }, 'Группа создана')
}

async function createUser() {
  if (!newUser.email.trim() || !newUser.password.trim()) return
  await withBusy('user', async () => {
    await api.endpoint('POST', '/admin/users', {
      accessToken: auth.accessToken,
      body: {
        email: newUser.email,
        password: newUser.password,
        full_name: newUser.full_name || null,
        role: newUser.role,
        specialty_id: newUser.specialty_id,
        group_id: newUser.group_id,
      },
    })
    newUser.email = ''
    newUser.password = ''
    newUser.full_name = ''
    newUser.role = 'student'
    await loadAdminData()
  }, 'Пользователь создан')
}

async function promoteUser(row: UserRow, role: Role) {
  await withBusy(`role-${row.id}`, async () => {
    await api.endpoint('PATCH', `/admin/users/${row.id}`, {
      accessToken: auth.accessToken,
      body: { role },
    })
    await loadAdminData()
  }, 'Права обновлены')
}

function updateUserRole(row: UserRow, value: unknown) {
  if (value === 'student' || value === 'teacher' || value === 'expert' || value === 'admin') {
    promoteUser(row, value)
  }
}

async function deleteUser(row: UserRow) {
  if (!confirm(`Удалить пользователя ${row.email}?`)) return
  await withBusy(`delete-user-${row.id}`, async () => {
    await api.endpoint('DELETE', `/admin/users/${row.id}`, {
      accessToken: auth.accessToken,
    })
    await loadAdminData()
  }, 'Пользователь удалён')
}

async function saveTargets() {
  if (!selectedAssignment.value) return
  await withBusy('targets', async () => {
    const assignment = selectedAssignment.value
    if (!assignment) return
    const row = await api.endpoint('PUT', `/assignments/${assignment.id}/targets`, {
      accessToken: auth.accessToken,
      body: {
        specialty_ids: selectedSpecialtyTargets.value,
        group_ids: selectedGroupTargets.value,
      },
    })
    assignments.value = assignments.value.map((item) => item.id === row.id ? row : item)
    pickAssignment(row)
  }, 'Назначение задания обновлено')
}

async function deleteAssignment(row: AssignmentRow) {
  if (!confirm(`Удалить задание "${row.title}"?`)) return
  await withBusy(`delete-assignment-${row.id}`, async () => {
    await api.endpoint('DELETE', `/assignments/${row.id}`, {
      accessToken: auth.accessToken,
    })
    selectedAssignmentId.value = null
    await loadAdminData()
  }, 'Задание удалено')
}

onMounted(loadAdminData)
</script>

<template>
  <v-container fluid class="admin-page pa-3 pa-md-6">
    <PageHeader
      eyebrow="Панель управления"
      title="Администрирование учебного процесса"
      subtitle="Пользователи, права доступа, группы, специальности и назначение заданий."
    >
      <template #actions>
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="loadAdminData">
          Обновить
        </v-btn>
      </template>
    </PageHeader>

    <v-alert v-if="errorText" type="error" variant="tonal" class="mb-4" rounded="lg" closable @click:close="errorText = ''">
      {{ errorText }}
    </v-alert>
    <v-alert v-if="notice" type="success" variant="tonal" class="mb-4" rounded="lg" closable @click:close="notice = ''">
      {{ notice }}
    </v-alert>

    <v-row class="mb-2">
      <v-col cols="12" sm="6" lg="3">
        <MetricCard title="Пользователи" :value="users.length" icon="mdi-account-multiple-outline" />
      </v-col>
      <v-col cols="12" sm="6" lg="3">
        <MetricCard title="Специальности" :value="specialties.length" icon="mdi-school-outline" color="secondary" />
      </v-col>
      <v-col cols="12" sm="6" lg="3">
        <MetricCard title="Группы" :value="groups.length" icon="mdi-account-group-outline" color="success" />
      </v-col>
      <v-col cols="12" sm="6" lg="3">
        <MetricCard title="Задания" :value="assignments.length" icon="mdi-clipboard-check-outline" color="warning" />
      </v-col>
    </v-row>

    <v-tabs v-model="activeTab" class="mb-4 rounded-tabs" color="primary">
      <v-tab value="users" prepend-icon="mdi-account-multiple-outline">Пользователи</v-tab>
      <v-tab value="structure" prepend-icon="mdi-school-outline">Структура</v-tab>
      <v-tab value="assignments" prepend-icon="mdi-clipboard-check-outline">Задания</v-tab>
    </v-tabs>

    <v-window v-model="activeTab">
      <v-window-item value="users">
        <v-row>
          <v-col cols="12" lg="4">
            <v-card class="panel" elevation="0">
              <v-card-title>Новый пользователь</v-card-title>
              <v-card-text class="d-flex flex-column ga-3">
                <v-text-field v-model="newUser.email" label="Email / логин" variant="outlined" density="comfortable" />
                <v-text-field v-model="newUser.password" label="Пароль" type="password" variant="outlined" density="comfortable" />
                <v-text-field v-model="newUser.full_name" label="ФИО" variant="outlined" density="comfortable" />
                <v-select v-model="newUser.role" :items="roleItems" label="Роль" variant="outlined" density="comfortable" />
                <v-select v-model="newUser.specialty_id" :items="specialtyItems" label="Специальность" variant="outlined" density="comfortable" clearable />
                <v-select v-model="newUser.group_id" :items="groupItems" label="Группа" variant="outlined" density="comfortable" clearable />
              </v-card-text>
              <v-card-actions class="px-4 pb-4">
                <v-btn color="primary" variant="flat" :loading="busy === 'user'" @click="createUser">Создать</v-btn>
              </v-card-actions>
            </v-card>
          </v-col>

          <v-col cols="12" lg="8">
            <v-card class="panel" elevation="0">
              <v-card-title>Пользователи</v-card-title>
              <v-card-text>
                <v-data-table :headers="userHeaders" :items="users" :loading="loading" density="comfortable" class="rounded-lg">
                  <template #[`item.email`]="{ item }">
                    <div class="font-weight-bold">{{ item.email }}</div>
                    <div class="text-caption text-medium-emphasis">{{ item.full_name || 'ФИО не указано' }}</div>
                  </template>
                  <template #[`item.role`]="{ item }">
                    <v-select
                      :model-value="item.role"
                      :items="roleItems"
                      density="compact"
                      variant="outlined"
                      hide-details
                      style="min-width: 150px"
                      :loading="busy === `role-${item.id}`"
                      @update:model-value="updateUserRole(item, $event)"
                    />
                  </template>
                  <template #[`item.specialty_id`]="{ item }">{{ specialtyName(item.specialty_id) }}</template>
                  <template #[`item.group_id`]="{ item }">{{ groupName(item.group_id) }}</template>
                  <template #[`item.actions`]="{ item }">
                    <v-btn
                      icon="mdi-delete-outline"
                      variant="text"
                      color="error"
                      size="small"
                      :disabled="item.id === auth.user?.id"
                      :loading="busy === `delete-user-${item.id}`"
                      @click="deleteUser(item)"
                    />
                  </template>
                </v-data-table>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
      </v-window-item>

      <v-window-item value="structure">
        <v-row>
          <v-col cols="12" md="6">
            <v-card class="panel" elevation="0">
              <v-card-title>Специальности</v-card-title>
              <v-card-text class="d-flex flex-column ga-3">
                <v-text-field v-model="newSpecialty.name" label="Название" variant="outlined" density="comfortable" />
                <v-text-field v-model="newSpecialty.code" label="Код" variant="outlined" density="comfortable" />
                <v-textarea v-model="newSpecialty.description" label="Описание" variant="outlined" density="comfortable" rows="2" auto-grow />
                <v-btn color="primary" variant="flat" :loading="busy === 'specialty'" @click="createSpecialty">
                  Создать специальность
                </v-btn>
                <v-divider />
                <EmptyState
                  v-if="!specialties.length"
                  icon="mdi-school-outline"
                  title="Специальности пока не созданы"
                  text="Создайте специальность, чтобы привязывать к ней группы и студентов."
                />
                <v-list v-else density="compact">
                  <v-list-item v-for="item in specialties" :key="item.id" :title="item.name" :subtitle="item.code || 'Без кода'" prepend-icon="mdi-school-outline" />
                </v-list>
              </v-card-text>
            </v-card>
          </v-col>

          <v-col cols="12" md="6">
            <v-card class="panel" elevation="0">
              <v-card-title>Группы</v-card-title>
              <v-card-text class="d-flex flex-column ga-3">
                <v-text-field v-model="newGroup.name" label="Название группы" variant="outlined" density="comfortable" />
                <v-select v-model="newGroup.specialty_id" :items="specialtyItems" label="Специальность" variant="outlined" density="comfortable" clearable />
                <v-text-field v-model.number="newGroup.year" label="Год набора" type="number" variant="outlined" density="comfortable" />
                <v-btn color="primary" variant="flat" :loading="busy === 'group'" @click="createGroup">
                  Создать группу
                </v-btn>
                <v-divider />
                <EmptyState
                  v-if="!groups.length"
                  icon="mdi-account-group-outline"
                  title="Группы пока не созданы"
                  text="Группа нужна для массового назначения заданий студентам."
                />
                <v-list v-else density="compact">
                  <v-list-item
                    v-for="item in groups"
                    :key="item.id"
                    :title="item.name"
                    :subtitle="`${specialtyName(item.specialty_id)} · ${item.year || 'год не указан'}`"
                    prepend-icon="mdi-account-group-outline"
                  />
                </v-list>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
      </v-window-item>

      <v-window-item value="assignments">
        <v-row>
          <v-col cols="12" lg="7">
            <v-card class="panel" elevation="0">
              <v-card-title>Задания</v-card-title>
              <v-card-text>
                <v-data-table :headers="assignmentHeaders" :items="assignments" :loading="loading" density="comfortable">
                  <template #[`item.title`]="{ item }">
                    <div class="font-weight-bold">{{ item.title }}</div>
                    <div class="text-caption text-medium-emphasis">{{ item.description || 'Описание не указано' }}</div>
                  </template>
                  <template #[`item.targets`]="{ item }">
                    <v-chip size="small" variant="tonal" color="primary">{{ assignmentTargetText(item) }}</v-chip>
                  </template>
                  <template #[`item.actions`]="{ item }">
                    <v-btn icon="mdi-tune" variant="text" color="primary" size="small" @click="pickAssignment(item)" />
                    <v-btn
                      icon="mdi-delete-outline"
                      variant="text"
                      color="error"
                      size="small"
                      :loading="busy === `delete-assignment-${item.id}`"
                      @click="deleteAssignment(item)"
                    />
                  </template>
                </v-data-table>
              </v-card-text>
            </v-card>
          </v-col>

          <v-col cols="12" lg="5">
            <v-card class="panel sticky-panel" elevation="0">
              <v-card-title>Назначение задания</v-card-title>
              <v-card-text class="d-flex flex-column ga-3">
                <v-select
                  v-model="selectedAssignmentId"
                  :items="assignments.map((item) => ({ title: item.title, value: item.id }))"
                  label="Задание"
                  variant="outlined"
                  density="comfortable"
                  @update:model-value="(id) => { const row = assignments.find((item) => item.id === id); if (row) pickAssignment(row) }"
                />
                <v-select
                  v-model="selectedSpecialtyTargets"
                  :items="specialtyItems"
                  label="Назначить специальностям"
                  variant="outlined"
                  density="comfortable"
                  multiple
                  chips
                />
                <v-select
                  v-model="selectedGroupTargets"
                  :items="groupItems"
                  label="Назначить группам"
                  variant="outlined"
                  density="comfortable"
                  multiple
                  chips
                />
                <v-alert type="info" variant="tonal" density="compact" rounded="lg">
                  Если ничего не выбрать, задание будет доступно всем студентам.
                </v-alert>
              </v-card-text>
              <v-card-actions class="px-4 pb-4">
                <v-btn color="primary" variant="flat" :loading="busy === 'targets'" :disabled="!selectedAssignment" @click="saveTargets">
                  Сохранить назначение
                </v-btn>
              </v-card-actions>
            </v-card>
          </v-col>
        </v-row>
      </v-window-item>
    </v-window>
  </v-container>
</template>

<style scoped>
.admin-page {
  max-width: 1440px;
  margin: 0 auto;
}

.panel {
  border: 1px solid rgba(var(--v-border-color), 0.12);
  border-radius: 8px !important;
  background: rgba(var(--v-theme-surface), 0.94) !important;
}

.rounded-tabs {
  background: rgba(var(--v-theme-surface), 0.86);
  border: 1px solid rgba(var(--v-border-color), 0.1);
}

.sticky-panel {
  position: sticky;
  top: 84px;
}

@media (max-width: 720px) {
  .sticky-panel {
    position: static;
  }
}
</style>
