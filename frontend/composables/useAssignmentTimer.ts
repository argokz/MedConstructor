import { computed, onMounted, onUnmounted, ref } from 'vue'

export function useAssignmentTimer(deadlineIso?: () => string | null | undefined) {
  const now = ref(Date.now())
  let timerId: ReturnType<typeof setInterval> | null = null

  onMounted(() => {
    timerId = setInterval(() => {
      now.value = Date.now()
    }, 1000)
  })

  onUnmounted(() => {
    if (timerId) clearInterval(timerId)
  })

  const deadlineMs = computed(() => {
    const raw = deadlineIso?.()
    if (!raw) return null
    const value = new Date(raw).getTime()
    return Number.isFinite(value) ? value : null
  })

  const remainingMs = computed(() => {
    if (deadlineMs.value == null) return null
    return Math.max(0, deadlineMs.value - now.value)
  })

  const isExpired = computed(() => deadlineMs.value != null && remainingMs.value === 0)

  const label = computed(() => {
    if (deadlineMs.value == null) return null
    const total = remainingMs.value ?? 0
    const minutes = Math.floor(total / 60000)
    const seconds = Math.floor((total % 60000) / 1000)
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  })

  return {
    remainingMs,
    isExpired,
    label,
    deadlineMs,
  }
}
