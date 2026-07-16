<script setup lang="ts">
definePageMeta({ layout: 'auth' })

const auth = useAuthStore()
const email = ref('')
const password = ref('')
const fullName = ref('')
const registerMode = ref(false)
const errorMsg = ref<string | null>(null)
const loading = ref(false)
const runtimeConfig = useRuntimeConfig()
const appBase = runtimeConfig.app.baseURL
const brandLogoSrc = `${appBase}brand/logo-podpis.png`

async function submit() {
  errorMsg.value = null
  loading.value = true
  try {
    if (registerMode.value) {
      await auth.register(email.value, password.value, fullName.value || undefined)
    } else {
      await auth.login(email.value, password.value)
    }
    await navigateTo('/dashboard')
  } catch (e: any) {
    const d = e?.data?.detail
    errorMsg.value = typeof d === 'string' ? d : e?.message || 'Ошибка'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-shell">
    <v-card class="login-card glass" rounded="xl" elevation="8">
      <div class="login-brand">
        <img :src="brandLogoSrc" alt="MedConstructor" class="login-brand-logo">
      </div>
      <div class="text-h6 mb-4">{{ registerMode ? 'Регистрация студента' : 'Вход' }}</div>
      <v-text-field v-model="email" label="Email" type="email" variant="solo-filled" flat density="comfortable" />
      <v-text-field
        v-model="password"
        label="Пароль"
        type="password"
        variant="solo-filled"
        flat
        density="comfortable"
        class="mt-2"
      />
      <v-text-field
        v-if="registerMode"
        v-model="fullName"
        label="ФИО (необязательно)"
        variant="solo-filled"
        flat
        density="comfortable"
        class="mt-2"
      />
      <v-alert v-if="errorMsg" type="error" variant="tonal" class="mt-4" rounded="lg">{{ errorMsg }}</v-alert>
      <v-btn
        color="primary"
        block
        size="large"
        rounded="lg"
        class="mt-6"
        :loading="loading"
        @click="submit"
      >
        {{ registerMode ? 'Зарегистрироваться' : 'Войти' }}
      </v-btn>
      <v-btn variant="text" block class="mt-2" @click="registerMode = !registerMode">
        {{ registerMode ? 'Уже есть аккаунт' : 'Регистрация студента' }}
      </v-btn>
    </v-card>
  </div>
</template>

<style scoped>
.login-shell {
  width: 100%;
  max-width: 28rem;
}

.login-card {
  width: 100%;
  padding: 1rem;
}

@media (min-width: 600px) {
  .login-card {
    padding: 1.5rem;
  }
}

.glass {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.02));
  border: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(10px);
}

.login-brand {
  display: flex;
  justify-content: center;
  margin-bottom: 1.25rem;
}

.login-brand-logo {
  width: min(14rem, 70vw);
  height: auto;
  object-fit: contain;
}
</style>
