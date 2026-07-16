import { useAuthStore } from '~/stores/auth'

export default defineNuxtRouteMiddleware(async () => {
  const auth = useAuthStore()
  if (!auth.user && auth.accessToken) {
    await auth.fetchMe()
  }
  if (!auth.user || (auth.user.role !== 'teacher' && auth.user.role !== 'admin')) {
    return navigateTo('/')
  }
})
