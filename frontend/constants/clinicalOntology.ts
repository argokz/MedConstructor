import type { EdgeType } from '~/types/api'

/**
 * Single source of truth for the clinical graph ontology presentation:
 * node categories (colors, icons, shapes, RU labels) and edge relations
 * (colors, dash patterns, RU labels). Every component that renders or
 * edits graph elements must read from here instead of keeping local maps.
 */

export interface CategoryMeta {
  /** Canonical uppercase key. */
  value: string
  /** Accent color: border, icon, handles, minimap. */
  color: string
  /** Soft tinted node background. */
  bg: string
  /** Node shape (border-radius). */
  radius: string
  icon: string
  /** Short badge inside the node. */
  short: string
  /** Singular title for selects. */
  title: string
  /** Plural title for palette group headers. */
  plural: string
}

const CATEGORY_LIST: CategoryMeta[] = [
  {
    value: 'PATIENT_PROFILE',
    color: '#0284c7',
    bg: '#f0f9ff',
    radius: '24px',
    icon: 'mdi-card-account-details-outline',
    short: 'Профиль',
    title: 'Профиль пациента',
    plural: 'Профиль пациента',
  },
  {
    value: 'SYMPTOM',
    color: '#d97706',
    bg: '#fffbeb',
    radius: '12px 0 12px 0',
    icon: 'mdi-alert-circle-outline',
    short: 'Симптом',
    title: 'Симптом',
    plural: 'Симптомы',
  },
  {
    value: 'EXAM',
    color: '#0d9488',
    bg: '#f0fdfa',
    radius: '8px',
    icon: 'mdi-eye-outline',
    short: 'Осмотр',
    title: 'Объективный осмотр',
    plural: 'Объективный осмотр',
  },
  {
    value: 'LAB_TEST',
    color: '#2563eb',
    bg: '#eff6ff',
    radius: '4px',
    icon: 'mdi-test-tube',
    short: 'Лаб. тест',
    title: 'Лабораторный тест',
    plural: 'Лабораторные тесты',
  },
  {
    value: 'INSTRUMENTAL_TEST',
    color: '#7c3aed',
    bg: '#faf5ff',
    radius: '8px',
    icon: 'mdi-radiology-box',
    short: 'Инстр. тест',
    title: 'Инструментальный тест',
    plural: 'Инструментальные тесты',
  },
  {
    value: 'DIAGNOSIS',
    color: '#dc2626',
    bg: '#fef2f2',
    radius: '0px',
    icon: 'mdi-stethoscope',
    short: 'Диагноз',
    title: 'Диагноз',
    plural: 'Диагнозы',
  },
  {
    value: 'DISEASE',
    color: '#dc2626',
    bg: '#fef2f2',
    radius: '0px',
    icon: 'mdi-stethoscope',
    short: 'Заболевание',
    title: 'Заболевание',
    plural: 'Заболевания',
  },
  {
    value: 'MEDICATION',
    color: '#16a34a',
    bg: '#f0fdf4',
    radius: '20px',
    icon: 'mdi-pill',
    short: 'Препарат',
    title: 'Лекарство',
    plural: 'Лекарства',
  },
  {
    value: 'SURGERY',
    color: '#ea580c',
    bg: '#fff7ed',
    radius: '20px',
    icon: 'mdi-box-cutter',
    short: 'Операция',
    title: 'Хирургическая операция',
    plural: 'Хирургия',
  },
  {
    value: 'MONITORING',
    color: '#0891b2',
    bg: '#ecfeff',
    radius: '8px',
    icon: 'mdi-monitor-heart',
    short: 'Мониторинг',
    title: 'Мониторинг',
    plural: 'Мониторинг',
  },
]

const FALLBACK_CATEGORY: CategoryMeta = {
  value: 'UNKNOWN',
  color: '#64748b',
  bg: '#ffffff',
  radius: '8px',
  icon: 'mdi-help-circle-outline',
  short: 'Узел',
  title: 'Узел',
  plural: 'Прочее',
}

const CATEGORY_BY_KEY = new Map(CATEGORY_LIST.map((meta) => [meta.value, meta]))

export function normalizeCategory(category: unknown): string {
  return typeof category === 'string' ? category.toUpperCase().trim() : ''
}

export function categoryMeta(category: unknown): CategoryMeta {
  return CATEGORY_BY_KEY.get(normalizeCategory(category)) ?? FALLBACK_CATEGORY
}

/** Plural human title for palette groups / filters; falls back to the raw key. */
export function categoryPluralTitle(key: string): string {
  if (key === '__frame__') return 'Оформление'
  const normalized = normalizeCategory(key)
  if (normalized === 'LAYOUT') return 'Оформление холста'
  return CATEGORY_BY_KEY.get(normalized)?.plural ?? key
}

/** Options for "node category" selects (DISEASE is an input alias of DIAGNOSIS and is not offered). */
export const CATEGORY_OPTIONS = CATEGORY_LIST
  .filter((meta) => meta.value !== 'DISEASE')
  .map((meta) => ({ value: meta.value, title: meta.title }))

/** Legend entries: one per distinct visual category. */
export const CATEGORY_LEGEND = CATEGORY_LIST
  .filter((meta) => meta.value !== 'DISEASE')
  .map((meta) => ({ color: meta.color, label: meta.title }))

export interface RelationMeta {
  value: EdgeType
  /** Short RU label (edge badge, context menu). */
  short: string
  /** Full RU + code label for selects. */
  title: string
  color: string
  /** SVG stroke-dasharray. */
  dash: string
  /** Slightly thicker stroke for emphasis. */
  bold: boolean
  /** Legend explanation. */
  description: string
}

export const RELATIONS: RelationMeta[] = [
  {
    value: 'DETERMINES',
    short: 'Обуславливает',
    title: 'Обуславливает (DETERMINES)',
    color: '#475569',
    dash: '0',
    bold: false,
    description: 'указывает на необходимость следующего шага',
  },
  {
    value: 'REQUIRES_CONFIRMATION',
    short: 'Подтверждает',
    title: 'Подтверждает / требует подтверждения (REQUIRES_CONFIRMATION)',
    color: '#3b82f6',
    dash: '5,3',
    bold: false,
    description: 'результат подтверждает диагноз (диагноз требует подтверждения)',
  },
  {
    value: 'EXCLUDES',
    short: 'Исключает',
    title: 'Исключает (EXCLUDES)',
    color: '#f43f5e',
    dash: '2,2',
    bold: false,
    description: 'исключение дифференциального диагноза',
  },
  {
    value: 'INDICATED_FOR',
    short: 'Показано при',
    title: 'Показано при (INDICATED_FOR)',
    color: '#10b981',
    dash: '0',
    bold: true,
    description: 'лечение показано при диагнозе',
  },
  {
    value: 'CONTRAINDICATED_DUE_TO',
    short: 'Противопоказано',
    title: 'Противопоказано из-за (CONTRAINDICATED_DUE_TO)',
    color: '#f97316',
    dash: '8,4',
    bold: true,
    description: 'фактор делает действие небезопасным',
  },
]

export const RELATION_VALUES: readonly EdgeType[] = RELATIONS.map((relation) => relation.value)

const RELATION_BY_VALUE = new Map(RELATIONS.map((relation) => [relation.value, relation]))

export function relationMeta(label: unknown): RelationMeta | null {
  if (typeof label !== 'string') return null
  return RELATION_BY_VALUE.get(label.toUpperCase().trim() as EdgeType) ?? null
}

export function normalizeRelation(label: unknown, fallback: EdgeType): EdgeType {
  return relationMeta(label)?.value ?? fallback
}

/** Options for "relation" selects. */
export const RELATION_OPTIONS = RELATIONS.map((relation) => ({
  title: relation.title,
  value: relation.value,
}))

/** Edge stroke color for an unlabeled / unknown relation. */
export const RELATION_FALLBACK_COLOR = '#64748b'
/** Dash pattern for an edge whose relation is not chosen yet. */
export const RELATION_UNSET_DASH = '5,5'
