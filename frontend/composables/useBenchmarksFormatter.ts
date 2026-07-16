import { computed } from 'vue'
import type { BenchmarksData } from '~/composables/useBenchmarksData'
import type { BenchmarkRow } from '~/types/api'

type MetricTile = {
  label: string
  value: string
  tone: string
  hint: string
  subtitle?: string
}

type MetricGuideItem = {
  metric: string
  purpose: string
  interpretation: string
  impact: string
}

type ResearchWorkflowStep = {
  title: string
  text: string
  metric: string
}

function isRecord(value: unknown): value is BenchmarkRow {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function asRecord(value: unknown): BenchmarkRow {
  return isRecord(value) ? value : {}
}

function asRows(value: unknown): BenchmarkRow[] {
  return Array.isArray(value) ? value.filter(isRecord) : []
}

function nullableString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

const MODE_LABELS: Record<string, string> = {
  dense_only: 'Только векторный поиск',
  dense_rerank: 'Векторный поиск + переранжирование',
  full: 'Полный режим поиска',
}

const PATTERN_LABELS: Record<string, string> = {
  all_metrics_high: 'Корректное решение без критичных ошибок',
  category_accuracy_drop: 'Неверная категория клинического блока',
  critical_relation_penalty: 'Ошибка в критически важной связи',
  directed_path_zero: 'Нет направленной клинической цепочки',
  missing_critical_action_penalty: 'Пропущено критически важное действие',
  recall_and_node_coverage_drop: 'Не хватает важных клинических блоков',
  unsafe_extra_action_cap: 'Добавлено потенциально опасное лишнее действие',
  safe_reference: 'Эталонное безопасное решение',
  missing_diagnosis: 'Не указан ключевой диагноз',
  missing_diagnostic_step: 'Пропущен диагностический шаг',
  missing_treatment: 'Пропущено лечение или действие',
}

const VARIANT_LABELS: Record<string, string> = {
  correct_reference_solution: 'Корректное решение',
  missing_key_diagnostic_step: 'Пропущен диагностический шаг',
  wrong_node_category: 'Неверная категория блока',
  missing_critical_action: 'Пропущено критическое действие',
  broken_reasoning_chain: 'Разорвана клиническая цепочка',
  unsafe_extra_action: 'Лишнее опасное действие',
  contraindication_reversed_to_indication: 'Противопоказание заменено показанием',
}

const MODEL_LABELS: Record<string, string> = {
  composite_v4_3: 'Композитная оценка (v4.3)',
  composite_v4_2: 'Композитная оценка (v4.2)',
  composite_v4_1: 'Композитная оценка (v4.1)',
  edge_f1_baseline: 'Базовый Edge F1',
  weighted_edge_f1_only: 'Только взвешенный Edge F1',
  node_coverage_only: 'Только покрытие узлов',
  category_accuracy_only: 'Только точность категорий',
  directed_path_only: 'Только направленная цепочка',
  safety_adjusted_weighted_edge_f1: 'Edge F1 с поправкой на безопасность',
}

const RUN_TYPE_LABELS: Record<string, string> = {
  tables_export: 'Экспорт отчетов',
  cardiology_synthetic: 'Кардиологический набор',
  rag: 'Проверка поиска по протоколам',
  rag_ablation: 'Сравнение режимов поиска',
  graph: 'Проверка графов',
  expert: 'Экспертная оценка',
  generation_audit: 'Аудит заданий',
}

const SEVERITY_LABELS: Record<string, string> = {
  critical: 'Критично',
  warning: 'Предупреждение',
  info: 'Информация',
}

const ARTIFACT_LABELS: Record<string, string> = {
  'benchmark_report_latest.xlsx': 'Сводный XLSX-отчет для статьи',
  'rag_results.csv': 'RAG: результаты по запросам',
  'rag_ablation.csv': 'RAG: сравнение режимов поиска',
  'graph_results.csv': 'Графы: результаты вариантов',
  'graph_reference_quality.csv': 'Графы: качество эталонов',
  'cardiology_tasks.csv': 'Кардиология: задания',
  'cardiology_results.csv': 'Кардиология: варианты решений',
  'cardiology_recommendations.csv': 'Кардиология: рекомендации',
  'cardiology_real_expert_validation_v2_latest.json': 'Кардиология: основная валидация пяти экспертов',
  'cardiology_real_expert_ratings_latest.csv': 'Кардиология: 365 обезличенных экспертных оценок',
  'cardiology_real_reference_audit_v2_latest.csv': 'Кардиология: аудит эталонов по основной панели',
  'cardiology_protocol_grounding.csv': 'Кардиология: происхождение заданий по протоколам',
  'expert_items.csv': 'Эксперты: решения',
  'expert_by_pattern.csv': 'Эксперты: анализ по типам ошибок',
  'expert_by_expert.csv': 'Эксперты: согласованность по экспертам',
  'benchmark_history.csv': 'История запусков',
}

function labelFromMap(value: unknown, labels: Record<string, string>): string {
  const key = String(value ?? '').trim()
  if (!key) return '—'
  return labels[key] ?? key.replaceAll('_', ' ')
}

function stripMarkdown(value: string): string {
  return value
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/<\/?details[^>]*>/gi, ' ')
    .replace(/<\/?summary[^>]*>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/[#*_`>~-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function articleMetric(value: string, target: 'higher' | 'lower' | 'context'): string {
  if (target === 'higher') return `${value}. Чем выше значение, тем надежнее результат.`
  if (target === 'lower') return `${value}. Чем ниже значение, тем лучше.`
  return value
}

export function useBenchmarksFormatter(data: BenchmarksData) {
  const artifactHeaders = [
    { title: 'Отчет', key: 'name', sortable: true },
    { title: 'Размер файла', key: 'size_bytes', sortable: true },
    { title: 'Обновлен', key: 'updated_at', sortable: true },
    { title: '', key: 'actions', sortable: false, align: 'end' as const },
  ]

  const patternHeaders = [
    { title: 'Проверяемая ситуация', key: 'expected_pattern', sortable: true },
    { title: 'Вариантов', key: 'n', sortable: true },
    { title: 'Распознано', key: 'pass_rate', sortable: true },
  ]

  const ablationHeaders = [
    { title: 'Режим поиска', key: 'mode', sortable: true },
    { title: 'Точность top-1', key: 'recall_at_1', sortable: true },
    { title: 'Точность top-5', key: 'recall_at_5', sortable: true },
    { title: 'Качество ранжирования', key: 'mrr', sortable: true },
    { title: 'Раздел протокола', key: 'section_hit_rate', sortable: true },
    { title: 'Ключевые фразы', key: 'key_phrase_hit_rate', sortable: true },
    { title: 'P50, мс', key: 'p50', sortable: true },
  ]

  const ragResultHeaders = [
    { title: 'Запрос', key: 'id', sortable: true },
    { title: 'Позиция', key: 'hit_rank', sortable: true },
    { title: 'Задержка, мс', key: 'latency_ms', sortable: true },
    { title: 'Раздел', key: 'section_hit_score', sortable: true },
    { title: 'Фразы', key: 'key_phrase_hit_score', sortable: true },
    { title: 'Ожидаемые протоколы', key: 'expected_protocol_ids', sortable: false },
    { title: 'Найденные протоколы', key: 'retrieved_protocol_ids', sortable: false },
    { title: 'Лучший источник', key: 'top_protocol_title', sortable: true },
    { title: 'Фрагмент', key: 'top_preview', sortable: false },
  ]

  const graphResultHeaders = [
    { title: 'Задача', key: 'case_id', sortable: true },
    { title: 'Вариант', key: 'variant_id', sortable: true },
    { title: 'Проверяемая ситуация', key: 'expected_pattern', sortable: true },
    { title: 'Распознано', key: 'pattern_passed', sortable: true },
    { title: 'Итог', key: 'composite_score', sortable: true },
    { title: 'Связи', key: 'weighted_edge_f1', sortable: true },
    { title: 'Покрытие', key: 'node_coverage', sortable: true },
    { title: 'Категории', key: 'category_accuracy', sortable: true },
    { title: 'Цепочка', key: 'directed_path_completeness', sortable: true },
    { title: 'Безопасность', key: 'safety_penalty', sortable: true },
    { title: 'Комментарий', key: 'safety_findings', sortable: false },
  ]

  const graphQualityHeaders = [
    { title: 'Задача', key: 'title', sortable: true },
    { title: 'Принят', key: 'accepted', sortable: true },
    { title: 'Качество', key: 'quality_score', sortable: true },
    { title: 'Замечания', key: 'warning_count', sortable: true },
    { title: 'Критичные', key: 'critical_count', sortable: true },
    { title: 'Диагноз', key: 'has_diagnosis', sortable: true },
    { title: 'Диагностика', key: 'has_diagnostic_step', sortable: true },
    { title: 'Жалобы → диагноз', key: 'has_start_to_diagnosis_path', sortable: true },
    { title: 'Диагноз → действие', key: 'has_diagnosis_to_action_path', sortable: true },
  ]

  const cardiologyTaskHeaders = [
    { title: 'Задание', key: 'title', sortable: true },
    { title: 'Протокол', key: 'source_protocol_title', sortable: true },
    { title: 'Раздел', key: 'expected_sections', sortable: false },
    { title: 'Клинический фокус', key: 'protocol_focus', sortable: false },
    { title: 'Качество', key: 'task_quality_score', sortable: true },
    { title: 'Принято', key: 'task_quality_accepted', sortable: true },
    { title: 'Чек-лист', key: 'checklist_count', sortable: true },
    { title: 'Варианты', key: 'variant_count', sortable: true },
  ]

  const cardiologyPatternSummaryHeaders = [
    { title: 'Проверяемая ситуация', key: 'expected_pattern', sortable: true },
    { title: 'Вариантов', key: 'n', sortable: true },
    { title: 'Система', key: 'mean_model_score', sortable: true },
    { title: 'Эксперты', key: 'mean_expert_score', sortable: true },
    { title: 'Расхождение', key: 'mean_gap_model_minus_expert', sortable: true },
    { title: 'Распознано', key: 'pattern_pass_rate', sortable: true },
  ]

  const cardiologyExpertRatingHeaders = [
    { title: 'Эксперт', key: 'expert_id', sortable: true },
    { title: 'Стаж', key: 'experience_years', sortable: true },
    { title: 'Задача', key: 'case_id', sortable: true },
    { title: 'Проверяемая ситуация', key: 'expected_pattern', sortable: true },
    { title: 'Система', key: 'model_score', sortable: true },
    { title: 'Эксперт', key: 'expert_score', sortable: true },
    { title: 'Уверенность', key: 'confidence', sortable: true },
    { title: 'Комментарий', key: 'expert_comment', sortable: false },
  ]

  const cardiologyRecommendationHeaders = [
    { title: 'Задача', key: 'case_id', sortable: true },
    { title: 'Проверяемая ситуация', key: 'expected_pattern', sortable: true },
    { title: 'Система', key: 'model_score', sortable: true },
    { title: 'Эксперты', key: 'expert_mean_score', sortable: true },
    { title: 'Расхождение', key: 'score_gap_model_minus_expert', sortable: true },
    { title: 'Рекомендация', key: 'system_recommendation', sortable: false },
    { title: 'Риски', key: 'safety_findings', sortable: false },
  ]

  const expertItemHeaders = [
    { title: 'Задача', key: 'case_id', sortable: true },
    { title: 'Проверяемая ситуация', key: 'expected_pattern', sortable: true },
    { title: 'Система', key: 'model_score', sortable: true },
    { title: 'Эксперты', key: 'expert_mean_score', sortable: true },
    { title: 'Расхождение', key: 'score_gap_model_minus_expert', sortable: true },
    { title: 'Разброс', key: 'expert_score_std', sortable: true },
    { title: 'Оценок', key: 'expert_rating_count', sortable: true },
  ]

  const expertPatternHeaders = [
    { title: 'Проверяемая ситуация', key: 'expected_pattern', sortable: true },
    { title: 'Оценок', key: 'n', sortable: true },
    { title: 'Пирсон', key: 'pearson', sortable: true },
    { title: 'Спирмен', key: 'spearman', sortable: true },
    { title: 'Средняя ошибка', key: 'mae', sortable: true },
    { title: 'RMSE', key: 'rmse', sortable: true },
    { title: 'Смещение', key: 'bias', sortable: true },
  ]

  const expertByExpertHeaders = [
    { title: 'Эксперт', key: 'expert_id', sortable: true },
    { title: 'Оценок', key: 'n', sortable: true },
    { title: 'Пирсон', key: 'pearson', sortable: true },
    { title: 'Спирмен', key: 'spearman', sortable: true },
    { title: 'Средняя ошибка', key: 'mae', sortable: true },
    { title: 'RMSE', key: 'rmse', sortable: true },
    { title: 'Смещение', key: 'bias', sortable: true },
  ]

  const baselineComparisonHeaders = [
    { title: 'Метод оценки', key: 'model', sortable: true },
    { title: 'Источник метрики', key: 'metric_source', sortable: true },
    { title: 'Спирмен', key: 'spearman', sortable: true },
    { title: '95% CI ρ', key: 'spearman_ci', sortable: false },
    { title: 'Средняя ошибка', key: 'mae', sortable: true },
    { title: '95% CI MAE', key: 'mae_ci', sortable: false },
    { title: 'Разница ранга', key: 'delta_spearman_vs_composite', sortable: true },
    { title: 'Разница ошибки', key: 'delta_mae_vs_composite', sortable: true },
    { title: 'Пояснение', key: 'description', sortable: false },
  ]

  const skippedRowsHeaders = [
    { title: 'Строка CSV', key: 'row', sortable: true },
    { title: 'Причина пропуска', key: 'reason', sortable: true },
  ]

  const problemHeaders = [
    { title: 'Раздел', key: 'system', sortable: true },
    { title: 'Важность', key: 'severity', sortable: true },
    { title: 'Объект', key: 'item_id', sortable: true },
    { title: 'Метрика', key: 'metric', sortable: true },
    { title: 'Значение', key: 'value', sortable: true },
    { title: 'Причина', key: 'reason', sortable: false },
    { title: 'Что сделать', key: 'recommendation', sortable: false },
  ]

  const generationHeaders = [
    { title: 'Эталон / задание', key: 'title', sortable: true },
    { title: 'Заданий', key: 'assignment_count', sortable: true },
    { title: 'Качество задания', key: 'assignment_quality_score', sortable: true },
    { title: 'Принято', key: 'accepted', sortable: true },
    { title: 'Качество графа', key: 'quality_score', sortable: true },
    { title: 'Замечания', key: 'warning_count', sortable: true },
    { title: 'Критичные', key: 'critical_count', sortable: true },
    { title: 'Узлы', key: 'node_count', sortable: true },
    { title: 'Связи', key: 'edge_count', sortable: true },
    { title: 'Замечания к заданию', key: 'assignment_warnings', sortable: false },
    { title: 'Замечания к графу', key: 'warnings', sortable: false },
  ]

  const historyHeaders = [
    { title: 'Время', key: 'generated_at', sortable: true },
    { title: 'Запуск', key: 'run_type', sortable: true },
    { title: 'RAG top-1', key: 'rag_recall_at_1', sortable: true },
    { title: 'Ранг RAG', key: 'rag_mrr', sortable: true },
    { title: 'Итог графа', key: 'graph_composite_score', sortable: true },
    { title: 'Ошибки графа', key: 'graph_pattern_pass_rate', sortable: true },
    { title: 'Эксперты', key: 'expert_spearman', sortable: true },
    { title: 'Кардио ошибки', key: 'cardiology_pattern_pass_rate', sortable: true },
    { title: 'Кардио эксперты', key: 'cardiology_expert_spearman', sortable: true },
  ]

  const formatPercent = (value: unknown) => {
    const numberValue = Number(value)
    if (!Number.isFinite(numberValue)) return '—'
    return `${(numberValue * 100).toFixed(1)}%`
  }

  const formatNumber = (value: unknown, digits = 3) => {
    const numberValue = Number(value)
    if (!Number.isFinite(numberValue)) return '—'
    return numberValue.toFixed(digits)
  }

  const formatRange = (low: unknown, high: unknown, digits = 3) => {
    if (low === null || low === undefined || high === null || high === undefined) return '—'
    return `${formatNumber(low, digits)}-${formatNumber(high, digits)}`
  }

  const formatSize = (bytes: number) => {
    if (!bytes) return '—'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  }

  const formatDate = (value: unknown) => {
    const text = nullableString(value)
    if (!text) return '—'
    const date = new Date(text)
    if (Number.isNaN(date.getTime())) return text
    return date.toLocaleString('ru-RU')
  }

  const compactValue = (value: unknown, limit = 4) => {
    if (Array.isArray(value)) {
      const rendered = value.slice(0, limit).map(String).join('; ')
      return value.length > limit ? `${rendered}; +${value.length - limit}` : rendered
    }
    if (value === null || value === undefined || value === '') return '—'
    return String(value)
  }

  const shortText = (value: unknown, length = 150) => {
    const text = stripMarkdown(compactValue(value, 999))
    return text.length > length ? `${text.slice(0, length)}...` : text
  }

  const cleanText = (value: unknown) => stripMarkdown(compactValue(value, 999))
  const modeLabel = (value: unknown) => labelFromMap(value, MODE_LABELS)
  const patternLabel = (value: unknown) => labelFromMap(value, PATTERN_LABELS)
  const variantLabel = (value: unknown) => labelFromMap(value, VARIANT_LABELS)
  const modelLabel = (value: unknown) => labelFromMap(value, MODEL_LABELS)
  const runTypeLabel = (value: unknown) => labelFromMap(value, RUN_TYPE_LABELS)
  const severityText = (value: unknown) => labelFromMap(value, SEVERITY_LABELS)
  const yesNoText = (value: unknown) => value ? 'Да' : 'Нет'
  const artifactLabel = (value: unknown) => labelFromMap(value, ARTIFACT_LABELS)

  const statusColor = (value: unknown) => value ? 'success' : 'error'
  const severityColor = (value: unknown) => {
    if (value === 'critical') return 'error'
    if (value === 'warning') return 'warning'
    return 'info'
  }

  const ragMetricTiles = computed(() => {
    const summary = asRecord(data.summary.value?.rag.summary)
    const recall = asRecord(summary.recall)
    const latency = asRecord(summary.latency_ms)
    return [
      { label: 'Recall@1', value: formatPercent(recall.recall_at_1), tone: 'primary', hint: 'Доля вопросов, где нужный протокол найден первым результатом.' },
      { label: 'Recall@5', value: formatPercent(recall.recall_at_5), tone: 'success', hint: 'Доля вопросов, где нужный протокол попал в первые пять найденных источников.' },
      { label: 'Качество ранжирования', value: formatNumber(summary.mrr), tone: 'secondary', hint: 'MRR: средняя обратная позиция правильного протокола. Чем ближе к 1, тем выше правильный источник.' },
      { label: 'Попадание в раздел', value: formatPercent(summary.section_hit_rate), tone: 'info', hint: 'Насколько найденные фрагменты совпадают с ожидаемыми разделами протокола.' },
      { label: 'Ключевые фразы', value: formatPercent(summary.key_phrase_hit_rate), tone: 'warning', hint: 'Доля ожидаемых клинических терминов, найденных в извлеченных фрагментах.' },
      { label: 'P95 задержка', value: `${formatNumber(latency.p95, 1)} мс`, tone: 'accent', hint: 'Время ответа, быстрее которого выполняются 95% запросов.' },
    ] satisfies MetricTile[]
  })

  const graphMetricTiles = computed(() => {
    const summary = asRecord(data.summary.value?.graph.summary)
    const averages = asRecord(summary.averages)
    return [
      { label: 'Паттерны ошибок', value: formatPercent(summary.pattern_pass_rate), tone: 'success', hint: 'Доля контрольных вариантов, где оценщик обнаружил ожидаемый тип ошибки.' },
      { label: 'Итоговая оценка', value: formatNumber(averages.composite_score), tone: 'primary', hint: 'Сводный балл графа с учетом связей, покрытия узлов, направления цепочки и клинической безопасности.' },
      { label: 'Качество связей', value: formatNumber(averages.weighted_edge_f1), tone: 'secondary', hint: 'Взвешенный Edge F1: совпадают ли причинно-следственные связи с эталоном, с большим весом для клинически важных связей.' },
      { label: 'Покрытие узлов', value: formatNumber(averages.node_coverage), tone: 'info', hint: 'Какая доля важных понятий эталона присутствует в решении студента.' },
      { label: 'Направленная цепочка', value: formatNumber(averages.directed_path_completeness), tone: 'warning', hint: 'Сохранился ли путь от жалоб и обследований к диагнозу и действиям.' },
      { label: 'Штраф безопасности', value: formatNumber(averages.safety_penalty), tone: 'error', hint: 'Накопленный штраф за опасные лишние действия или пропуск критически важных действий.' },
    ] satisfies MetricTile[]
  })

  const cardiologyMetricTiles = computed(() => {
    const summary = asRecord(data.summary.value?.cardiology?.summary)
    return [
      { label: 'Задачи', value: String(summary.case_count ?? '—'), tone: 'primary', hint: 'Количество клинических задач, созданных из кардиологических протоколов.' },
      { label: 'Варианты решений', value: String(summary.variant_count ?? '—'), tone: 'secondary', hint: 'Количество правильных и ошибочных графов, проверенных системой.' },
      { label: 'Качество задач', value: formatNumber(summary.task_quality_avg), tone: 'success', hint: 'Средняя полнота задания: есть клиническое описание, фокус протокола, чек-лист и red flags.' },
      { label: 'Паттерны ошибок', value: formatPercent(summary.pattern_pass_rate), tone: 'warning', hint: 'Доля типовых ошибок, которые автоматическая оценка распознала ожидаемым образом.' },
      { label: 'Спирмен с экспертами', value: formatNumber(summary.expert_spearman), tone: 'info', hint: 'Насколько порядок оценок системы совпадает с экспертным ранжированием решений.' },
      { label: 'Средняя ошибка', value: formatNumber(summary.expert_mae), tone: 'error', hint: 'MAE: средняя абсолютная ошибка между оценкой системы и экспертной оценкой на шкале 0-1.' },
    ] satisfies MetricTile[]
  })

  const expertMetricTiles = computed(() => {
    const summary = asRecord(data.summary.value?.expert)
    const corr = asRecord(summary.correlation_with_mean_expert)
    const interRater = asRecord(summary.inter_rater)
    return [
      { label: 'Объекты', value: String(summary.item_count ?? '—'), tone: 'primary', hint: 'Количество решений, по которым есть экспертная оценка.' },
      { label: 'Оценки', value: String(summary.rating_count ?? '—'), tone: 'secondary', hint: 'Общее количество индивидуальных экспертных оценок.' },
      { label: 'Эксперты', value: String(summary.expert_count ?? '—'), tone: 'info', hint: 'Количество экспертов, участвовавших в оценивании.' },
      { label: 'Пирсон', value: formatNumber(corr.pearson), tone: 'success', hint: 'Линейная корреляция между оценкой системы и средней экспертной оценкой.' },
      { label: 'Спирмен', value: formatNumber(corr.spearman), tone: 'warning', hint: 'Ранговая корреляция: совпадает ли порядок хороших и плохих решений.' },
      { label: 'Согласие экспертов', value: formatNumber(interRater.mean_pairwise_spearman), tone: 'accent', hint: 'Средняя согласованность экспертов между собой по ранжированию решений.' },
    ] satisfies MetricTile[]
  })

  const ablationRows = computed(() => {
    const byMode = data.summary.value?.rag_ablation.summary_by_mode || {}
    return Object.entries(byMode).map(([mode, rawData]) => {
      const row = asRecord(rawData)
      const recall = asRecord(row.recall)
      const latency = asRecord(row.latency_ms)
      return {
        mode,
        recall_at_1: recall.recall_at_1,
        recall_at_5: recall.recall_at_5,
        mrr: row.mrr,
        section_hit_rate: row.section_hit_rate,
        key_phrase_hit_rate: row.key_phrase_hit_rate,
        p50: latency.p50,
      }
    })
  })

  const patternRows = computed(() => asRows(asRecord(data.summary.value?.graph.summary).by_expected_pattern))
  const artifacts = computed(() => data.summary.value?.artifacts || [])
  const csvArtifacts = computed(() => artifacts.value.filter((artifact) => artifact.name.endsWith('.csv')))
  const reportArtifact = computed(() => artifacts.value.find((artifact) => artifact.name === 'benchmark_report_latest.xlsx'))

  const ragDetailRows = computed(() => (
    data.ragOnlyMisses.value
      ? data.details.value?.rag.misses || []
      : data.details.value?.rag.results || []
  ))

  const ragAblationDetailRows = computed(() => data.details.value?.rag.ablation_results || [])

  const graphDetailRows = computed(() => {
    const rows = data.details.value?.graph.results || []
    if (!data.graphOnlyFailed.value) return rows
    return rows.filter((row) => !row.pattern_passed || Number(row.composite_score ?? 1) < 0.75 || Number(row.safety_penalty ?? 0) > 0)
  })

  const graphQualityRows = computed(() => data.details.value?.graph.reference_quality || [])

  const cardiologyTaskRows = computed(() => data.details.value?.cardiology?.tasks || [])
  const cardiologyPatternRows = computed(() => data.details.value?.cardiology?.pattern_summary || [])
  const cardiologyReferenceQualityRows = computed(() => data.details.value?.cardiology?.reference_quality || [])

  const cardiologyGraphRows = computed(() => {
    const rows = data.details.value?.cardiology?.results || []
    if (!data.cardiologyOnlyFailed.value) return rows
    return rows.filter((row) => !row.pattern_passed || Number(row.safety_penalty ?? 0) > 0 || Number(row.composite_score ?? 1) < 0.75)
  })

  const cardiologyExpertItemRows = computed(() => data.details.value?.cardiology?.expert_items || [])
  const cardiologyExpertByExpertRows = computed(() => data.details.value?.cardiology?.expert_by_expert || [])
  const cardiologyExpertByPatternRows = computed(() => data.details.value?.cardiology?.expert_by_pattern || [])
  const withBaselineRanges = (rows: BenchmarkRow[]): BenchmarkRow[] => rows.map((row): BenchmarkRow => ({
    ...row,
    spearman_ci: formatRange(row.spearman_ci_low, row.spearman_ci_high),
    mae_ci: formatRange(row.mae_ci_low, row.mae_ci_high),
  }))
  const cardiologyBaselineRows = computed(() => withBaselineRanges(data.details.value?.cardiology?.baseline_comparison || []))
  const cardiologyRealBaselineRows = computed(() => withBaselineRanges(data.details.value?.cardiology?.real_baseline_comparison || []))
  const cardiologyRatingRows = computed(() => (data.details.value?.cardiology?.expert_ratings || []).slice(0, 300))
  const cardiologyRecommendationRows = computed(() => {
    const rows = data.details.value?.cardiology?.recommendations || []
    if (!data.cardiologyOnlyDisagreements.value) return rows
    return rows.filter((row) => Math.abs(Number(row.score_gap_model_minus_expert ?? 0)) >= 0.2)
  })

  const expertItemRows = computed(() => {
    const rows = data.details.value?.expert.items || []
    if (!data.expertOnlyDisagreements.value) return rows
    return rows.filter((row) => Math.abs(Number(row.score_gap_model_minus_expert ?? 0)) >= 0.15)
  })

  const expertPatternRows = computed(() => data.details.value?.expert.by_expected_pattern || [])
  const expertByExpertRows = computed(() => data.details.value?.expert.by_expert || [])
  const expertBaselineRows = computed(() => withBaselineRanges(data.details.value?.expert.baseline_comparison || []))
  const expertSkippedRows = computed(() => data.details.value?.expert.skipped_rows || [])
  const problemRows = computed(() => data.details.value?.problems || [])
  const generationRows = computed(() => data.details.value?.generation.items || [])
  const historyRows = computed(() => [...(data.details.value?.history || [])].reverse())

  const problemSummary = computed(() => ({
    total: problemRows.value.length,
    critical: problemRows.value.filter((row) => row.severity === 'critical').length,
    warning: problemRows.value.filter((row) => row.severity === 'warning').length,
    info: problemRows.value.filter((row) => row.severity === 'info').length,
  }))

  const ragAblationChartRows = computed(() => {
    const byMode = data.summary.value?.rag_ablation.summary_by_mode || {}
    return Object.entries(byMode).map(([mode, rawRow]) => {
      const row = asRecord(rawRow)
      const recall = asRecord(row.recall)
      return {
        label: modeLabel(mode),
        value: Number(recall.recall_at_1 ?? 0),
        caption: `ранг ${formatNumber(row.mrr)}`,
      }
    })
  })

  const graphChartRows = computed(() => {
    const summary = asRecord(data.summary.value?.graph.summary)
    const averages = asRecord(summary.averages)
    return [
      { label: 'Итоговый балл', value: Number(averages.composite_score ?? 0), caption: formatNumber(averages.composite_score) },
      { label: 'Качество связей', value: Number(averages.weighted_edge_f1 ?? 0), caption: formatNumber(averages.weighted_edge_f1) },
      { label: 'Покрытие узлов', value: Number(averages.node_coverage ?? 0), caption: formatNumber(averages.node_coverage) },
      { label: 'Клиническая цепочка', value: Number(averages.directed_path_completeness ?? 0), caption: formatNumber(averages.directed_path_completeness) },
    ]
  })

  const historyChartRows = computed(() => historyRows.value.slice(0, 8).map((row) => ({
    label: runTypeLabel(row.run_type),
    value: Number(row.graph_composite_score ?? row.rag_mrr ?? 0),
    caption: formatDate(nullableString(row.generated_at)),
  })))

  const researchSummaryTiles = computed(() => {
    const ragSummary = asRecord(data.summary.value?.rag.summary)
    const ragRecall = asRecord(ragSummary.recall)
    const graphSummary = asRecord(data.summary.value?.graph.summary)
    const graphAverages = asRecord(graphSummary.averages)
    const cardiologySummary = asRecord(data.summary.value?.cardiology?.summary)
    const expertSummary = asRecord(data.summary.value?.expert)
    const expertCorr = asRecord(expertSummary.correlation_with_mean_expert)

    return [
      {
        label: 'Поиск протокола top-1',
        value: formatPercent(ragRecall.recall_at_1),
        tone: 'primary',
        subtitle: 'Поиск по протоколам',
        hint: articleMetric('Доля клинических запросов, где правильный протокол найден первым', 'higher'),
      },
      {
        label: 'Ранжирование источников',
        value: formatNumber(ragSummary.mrr),
        tone: 'secondary',
        subtitle: 'MRR',
        hint: articleMetric('Показывает, насколько высоко система ставит правильный источник', 'higher'),
      },
      {
        label: 'Итог графового оценщика',
        value: formatNumber(graphAverages.composite_score),
        tone: 'success',
        subtitle: 'Сводный балл',
        hint: articleMetric('Сводная оценка совпадения решения с эталоном по узлам, связям, направлению и безопасности', 'higher'),
      },
      {
        label: 'Распознавание ошибок',
        value: formatPercent(graphSummary.pattern_pass_rate),
        tone: 'warning',
        subtitle: 'Распознавание ошибок',
        hint: articleMetric('Доля контрольных ошибочных вариантов, где система нашла ожидаемую ошибку', 'higher'),
      },
      {
        label: 'Согласие с экспертами',
        value: formatNumber(cardiologySummary.expert_spearman ?? expertCorr.spearman),
        tone: 'info',
        subtitle: 'Корреляция Спирмена',
        hint: articleMetric('Насколько ранжирование системы совпадает с ранжированием экспертов', 'higher'),
      },
      {
        label: 'Средняя ошибка оценки',
        value: formatNumber(cardiologySummary.expert_mae ?? expertSummary.mae),
        tone: 'error',
        subtitle: 'MAE',
        hint: articleMetric('Среднее абсолютное расхождение между системой и экспертами на шкале 0-1', 'lower'),
      },
    ] satisfies MetricTile[]
  })

  const metricGuideItems: MetricGuideItem[] = [
    {
      metric: 'Recall@1 / Recall@5: точность поиска',
      purpose: 'Проверяют RAG-поиск: нашла ли система нужный клинический протокол в первом результате или среди первых пяти.',
      interpretation: 'Высокие значения показывают, что студент или преподаватель получает релевантный источник для построения задания и эталона.',
      impact: 'Если Recall падает, нужно улучшать индексацию протоколов, чанкинг, формулировки запросов или переранжирование.',
    },
    {
      metric: 'MRR: качество ранжирования',
      purpose: 'Оценивает порядок выдачи источников, а не только факт попадания.',
      interpretation: 'Значение около 1 означает, что правильный протокол почти всегда стоит первым.',
      impact: 'Влияет на доверие к RAG-ответам и скорость экспертной проверки.',
    },
    {
      metric: 'Composite score: итоговая оценка графа',
      purpose: 'Сводный балл графового решения по клиническим блокам, связям, направлению цепочки и безопасности.',
      interpretation: 'Используется как итоговая автоматическая оценка качества решения.',
      impact: 'Главная метрика для сравнения студенческих решений, эталонов и вариантов с типовыми ошибками.',
    },
    {
      metric: 'Edge F1: качество связей',
      purpose: 'Проверяет качество причинно-следственных связей между блоками графа.',
      interpretation: 'Высокий Edge F1 означает, что студент не просто добавил правильные блоки, а связал их клинически корректно.',
      impact: 'Сильно влияет на оценку клинического мышления.',
    },
    {
      metric: 'Node coverage: покрытие клинических блоков',
      purpose: 'Показывает, покрыты ли важные понятия эталонного решения.',
      interpretation: 'Низкое покрытие означает пропуск симптомов, диагноза, диагностики или лечебных действий.',
      impact: 'Помогает объяснить студенту, чего не хватило в графе.',
    },
    {
      metric: 'Directed path completeness: полнота клинической цепочки',
      purpose: 'Проверяет наличие направленной клинической цепочки: жалобы и данные → диагноз → действие.',
      interpretation: 'Даже правильные блоки не дают полного балла, если клинический путь разорван.',
      impact: 'Защищает от формального набора блоков без логики рассуждения.',
    },
    {
      metric: 'Safety penalty: штраф безопасности',
      purpose: 'Фиксирует опасные лишние действия или пропуск критически важных действий.',
      interpretation: 'Это штрафная метрика: чем она выше, тем рискованнее решение.',
      impact: 'Показывает клиническую безопасность автоматической оценки.',
    },
    {
      metric: 'Spearman / MAE',
      purpose: 'Сравнивают автоматическую оценку с экспертами.',
      interpretation: 'Spearman показывает совпадение порядка решений, MAE показывает среднюю ошибку балла.',
      impact: 'Ключевой блок валидности оценщика для научной публикации.',
    },
  ]

  const researchWorkflow: ResearchWorkflowStep[] = [
    {
      title: '1. Источники и RAG',
      text: 'Сначала проверяется, насколько надежно система находит нужные клинические протоколы и разделы.',
      metric: 'Recall@1, Recall@5, MRR, попадание в раздел',
    },
    {
      title: '2. Эталонный граф',
      text: 'Затем оценивается полнота эталона: есть ли диагноз, диагностические шаги, лечение и связная клиническая цепочка.',
      metric: 'Качество эталона, критичные замечания, путь диагноз → действие',
    },
    {
      title: '3. Студенческие варианты',
      text: 'Система проверяет правильные и ошибочные решения, чтобы доказать распознавание типовых ошибок.',
      metric: 'Сводный балл, качество связей, покрытие узлов, штраф безопасности',
    },
    {
      title: '4. Экспертная валидизация',
      text: 'Автоматические баллы сравниваются с оценками экспертов, чтобы подтвердить научную валидность оценщика.',
      metric: 'Spearman, Pearson, MAE, согласие экспертов',
    },
    {
      title: '5. Артефакты для статьи',
      text: 'Все таблицы экспортируются в XLSX/CSV и подходят для разделов Methods, Results и Supplementary Materials.',
      metric: 'Сводный XLSX, CSV по RAG, графам, экспертам и истории запусков',
    },
  ]

  return {
    ablationHeaders,
    ablationRows,
    artifactHeaders,
    artifactLabel,
    artifacts,
    baselineComparisonHeaders,
    cardiologyBaselineRows,
    cardiologyExpertByExpertRows,
    cardiologyExpertByPatternRows,
    cardiologyExpertItemRows,
    cardiologyExpertRatingHeaders,
    cardiologyGraphRows,
    cardiologyMetricTiles,
    cardiologyPatternRows,
    cardiologyPatternSummaryHeaders,
    cardiologyRatingRows,
    cardiologyRealBaselineRows,
    cardiologyRecommendationHeaders,
    cardiologyRecommendationRows,
    cardiologyReferenceQualityRows,
    cardiologyTaskHeaders,
    cardiologyTaskRows,
    cleanText,
    compactValue,
    csvArtifacts,
    expertBaselineRows,
    expertByExpertHeaders,
    expertByExpertRows,
    expertItemHeaders,
    expertItemRows,
    expertMetricTiles,
    expertPatternHeaders,
    expertPatternRows,
    expertSkippedRows,
    formatDate,
    formatNumber,
    formatPercent,
    formatSize,
    generationHeaders,
    generationRows,
    graphChartRows,
    graphDetailRows,
    graphMetricTiles,
    graphQualityHeaders,
    graphQualityRows,
    graphResultHeaders,
    historyChartRows,
    historyHeaders,
    historyRows,
    modeLabel,
    patternHeaders,
    patternLabel,
    variantLabel,
    modelLabel,
    patternRows,
    problemHeaders,
    problemRows,
    problemSummary,
    ragAblationChartRows,
    ragAblationDetailRows,
    ragDetailRows,
    ragMetricTiles,
    ragResultHeaders,
    reportArtifact,
    researchSummaryTiles,
    researchWorkflow,
    runTypeLabel,
    severityColor,
    severityText,
    shortText,
    skippedRowsHeaders,
    statusColor,
    metricGuideItems,
    yesNoText,
  }
}

export type BenchmarksFormatter = ReturnType<typeof useBenchmarksFormatter>
