import { defineStore } from 'pinia'
import type { TokenResponse, UserPublic } from '~/types/api'
import { createApiClient } from '~/utils/apiClient'

function cookieOptions() {
  const secure =
    import.meta.client && typeof window !== 'undefined'
      ? window.location.protocol === 'https:'
      : false
  return {
    maxAge: 60 * 60 * 24 * 14,
    sameSite: 'lax' as const,
    secure,
    path: '/medical/',
  }
}

export const useAuthStore = defineStore('auth', () => {
  const accessToken = useCookie<string | null>('mc_access', cookieOptions())
  const user = ref<UserPublic | null>(null)
  let fetchMeRequest: Promise<void> | null = null

  const userId = computed(() => (user.value ? String(user.value.id) : null))

  async function fetchMe(options: { force?: boolean } = {}) {
    if (!accessToken.value) {
      user.value = null
      return
    }

    if (user.value && !options.force) {
      return
    }

    if (fetchMeRequest) {
      return await fetchMeRequest
    }

    fetchMeRequest = (async () => {
      try {
        user.value = await createApiClient({ accessToken: accessToken.value }).get<UserPublic>('/auth/me')
      } catch {
        user.value = null
        accessToken.value = null
      } finally {
        fetchMeRequest = null
      }
    })()

    return await fetchMeRequest
  }

  async function login(email: string, password: string) {
    const res = await createApiClient().post<TokenResponse, { email: string; password: string }>(
      '/auth/login',
      { email, password },
    )
    accessToken.value = res.access_token
    await fetchMe({ force: true })
  }

  async function register(email: string, password: string, full_name?: string) {
    await createApiClient().post<UserPublic, { email: string; password: string; full_name: string | null }>(
      '/auth/register',
      { email, password, full_name: full_name || null },
    )
    await login(email, password)
  }

  async function logout() {
    accessToken.value = null
    user.value = null
    await navigateTo('/login', { replace: true })
  }

  return { accessToken, user, userId, login, logout, register, fetchMe }
})
