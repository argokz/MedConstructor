const ICON_BUTTON_LABELS: Record<string, string> = {
  'mdi-arrow-up': 'Отправить сообщение',
  'mdi-arrow-expand': 'Развернуть',
  'mdi-clipboard-check-outline': 'Перейти к проверке сдач',
  'mdi-close': 'Закрыть',
  'mdi-delete-outline': 'Удалить',
  'mdi-dots-horizontal': 'Дополнительные действия',
  'mdi-download': 'Скачать',
  'mdi-eye-outline': 'Просмотреть',
  'mdi-fit-to-screen': 'Подогнать вид',
  'mdi-graph-outline': 'Открыть задание в конструкторе',
  'mdi-open-in-new': 'Открыть в новой странице',
  'mdi-pencil-ruler-outline': 'Проверить и доработать эталонный граф',
  'mdi-plus': 'Добавить',
  'mdi-refresh': 'Обновить',
  'mdi-redo-variant': 'Вернуть действие',
  'mdi-tune': 'Настроить',
  'mdi-undo-variant': 'Отменить действие',
  'mdi-vector-polyline': 'Выровнять граф',
}

const FLOW_CONTROL_LABELS: Array<[selector: string, label: string]> = [
  ['.vue-flow__controls-zoomin', 'Увеличить масштаб графа'],
  ['.vue-flow__controls-zoomout', 'Уменьшить масштаб графа'],
  ['.vue-flow__controls-fitview', 'Подогнать граф по размеру экрана'],
  ['.vue-flow__controls-interactive', 'Переключить интерактивность графа'],
]

function setAccessibleName(element: HTMLElement, label: string): void {
  if (!element.hasAttribute('aria-label')) {
    element.setAttribute('aria-label', label)
  }

  if (!element.hasAttribute('title')) {
    element.setAttribute('title', label)
  }
}

function normalizeWhitespace(value: string | null | undefined): string {
  return value?.replace(/\s+/g, ' ').trim() ?? ''
}

function normalizeTooltips(root: ParentNode): void {
  root.querySelectorAll<HTMLElement>('.v-tooltip[role="tooltip"]').forEach((tooltip) => {
    if (tooltip.hasAttribute('aria-label')) {
      return
    }

    const label = normalizeWhitespace(tooltip.textContent)
    if (label) {
      tooltip.setAttribute('aria-label', label)
    }
  })
}

function normalizeVueFlowControls(root: ParentNode): void {
  FLOW_CONTROL_LABELS.forEach(([selector, label]) => {
    root.querySelectorAll<HTMLElement>(`button${selector}`).forEach((button) => {
      setAccessibleName(button, label)
    })
  })
}

function iconNameFromButton(button: HTMLElement): string | null {
  const icon = button.querySelector<HTMLElement>('[class*="mdi-"]')
  const classNames = icon?.className

  if (typeof classNames !== 'string') {
    return null
  }

  return classNames.split(/\s+/).find((className) => className.startsWith('mdi-') && className !== 'mdi') ?? null
}

function hasReadableName(button: HTMLElement): boolean {
  return Boolean(
    normalizeWhitespace(button.getAttribute('aria-label'))
      || normalizeWhitespace(button.getAttribute('aria-labelledby'))
      || normalizeWhitespace(button.getAttribute('title'))
      || normalizeWhitespace(button.textContent),
  )
}

function normalizeIconButtons(root: ParentNode): void {
  root.querySelectorAll<HTMLElement>('button.v-btn--icon').forEach((button) => {
    if (hasReadableName(button)) {
      return
    }

    const iconName = iconNameFromButton(button)
    const label = iconName ? ICON_BUTTON_LABELS[iconName] : null
    if (label) {
      setAccessibleName(button, label)
    }
  })
}

export default defineNuxtPlugin(() => {
  const normalize = (): void => {
    normalizeTooltips(document)
    normalizeVueFlowControls(document)
    normalizeIconButtons(document)
  }

  let frameId = 0
  const scheduleNormalize = (): void => {
    if (frameId) {
      window.cancelAnimationFrame(frameId)
    }

    frameId = window.requestAnimationFrame(() => {
      frameId = 0
      normalize()
    })
  }

  const observer = new MutationObserver(scheduleNormalize)

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', normalize, { once: true })
  } else {
    normalize()
  }

  observer.observe(document.body, {
    childList: true,
    subtree: true,
  })
})
