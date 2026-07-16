export function useApi() {
  const config = useRuntimeConfig()

  function resolveAbsoluteBase(): string {
    const publicBase = String(config.public.apiBase || '/medical-api').replace(/\/$/, '')
    const internalBase = String(config.public.internalApiBase || 'http://127.0.0.1:8012').replace(/\/$/, '')

    // SSR: всегда напрямую на FastAPI (Nitro не проксирует /medical-api)
    if (import.meta.server) {
      return internalBase
    }

    const host = window.location.hostname
    const isLocal = host === 'localhost' || host === '127.0.0.1'

    if (publicBase.startsWith('http://') || publicBase.startsWith('https://')) {
      if (isLocal) return publicBase
      if (publicBase.includes('127.0.0.1') || publicBase.includes('localhost')) {
        return `${window.location.origin}/medical-api`
      }
      return publicBase
    }

    // Локально без nginx: node :3008 не знает /medical-api — идём на :8012
    if (isLocal) {
      return internalBase
    }

    // Продакшен: nginx проксирует /medical-api на backend
    return `${window.location.origin}${publicBase.startsWith('/') ? publicBase : `/${publicBase}`}`
  }

  const v1 = (path: string) => {
    const base = resolveAbsoluteBase()
    return `${base}/api/v1${path.startsWith('/') ? path : `/${path}`}`
  }

  return { base: resolveAbsoluteBase, v1 }
}
