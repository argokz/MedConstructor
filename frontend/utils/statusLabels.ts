const STATUS_LABELS: Record<string, string> = {
  accepted: 'Принято',
  active: 'Активно',
  admin: 'Администратор',
  ai_generated: 'AI-черновик',
  archived: 'Архив',
  completed: 'Выполнено',
  draft: 'Черновик',
  error: 'Ошибка',
  expert: 'Эксперт',
  failed: 'Ошибка',
  inactive: 'Неактивно',
  in_progress: 'В процессе',
  needs_revision: 'Нужна доработка',
  needs_review: 'Нужна проверка',
  needs_teacher_review: 'Требует проверки',
  no: 'Нет',
  not_started: 'Не выполнено',
  published: 'Опубликовано',
  rejected: 'Отклонено',
  review_ready: 'Требует проверки',
  revision_requested: 'На доработку',
  student: 'Студент',
  submitted: 'На проверке',
  success: 'Успешно',
  teacher: 'Преподаватель',
  teacher_approved: 'Подтверждён преподавателем',
  warning: 'Предупреждение',
  yes: 'Да',
}

export function statusLabel(status?: string | null): string {
  const rawStatus = status?.trim()
  if (!rawStatus) return '—'

  return STATUS_LABELS[rawStatus.toLowerCase()] ?? rawStatus
}
