import { useAuthStore } from '~/stores/auth'

export default defineNuxtRouteMiddleware(async (to) => {
  const auth = useAuthStore()
  const isLogin = to.path === '/login'

  if (!auth.user && auth.accessToken) {
    await auth.fetchMe()
  }

  if (!auth.user && !isLogin) {
    return navigateTo('/login')
  }

  if (auth.user && isLogin) {
    return navigateTo('/dashboard')
  }
})
