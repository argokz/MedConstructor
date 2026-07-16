function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function stringifyDetailItem(item: unknown): string {
  if (isRecord(item) && typeof item.msg === 'string') {
    return item.msg
  }

  if (typeof item === 'string') {
    return item
  }

  return JSON.stringify(item)
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (!isRecord(error)) return fallback

  const data = error.data
  if (isRecord(data)) {
    const detail = data.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map(stringifyDetailItem).join('; ')
  }

  return typeof error.message === 'string' ? error.message : fallback
}
