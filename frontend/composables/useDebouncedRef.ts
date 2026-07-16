import { ref, watch, onScopeDispose, type Ref } from 'vue'

/** Синхронизирует debouncedRef с source с задержкой (мс). */
export function useDebouncedRef<T>(source: Ref<T>, delayMs = 350) {
  const debounced = ref(source.value) as Ref<T>
  let timer: ReturnType<typeof setTimeout> | null = null

  watch(source, (value) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      debounced.value = value
      timer = null
    }, delayMs)
  })

  onScopeDispose(() => {
    if (timer) clearTimeout(timer)
  })

  return debounced
}
