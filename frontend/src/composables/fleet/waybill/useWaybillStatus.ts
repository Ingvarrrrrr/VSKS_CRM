// Метки/варианты статуса путевого листа — общий источник для WaybillTopbar
// и оркестратора (не дублировать, ПРАВИЛО №6). Вынесено из
// FleetWaybillFormView.vue без изменения поведения.

export function statusLabel(s: string): string {
  const map: Record<string, string> = {
    created:      'Создан',
    tech_inspect: 'Тех. осмотр',
    med_inspect:  'Медосмотр',
    in_progress:  'В работе',
    closing:      'Закрытие',
    on_review:    'На проверке',
    closed:       'Закрыт',
    overdue:      'Просрочен',
  }
  return map[s] ?? s
}

export function statusVariant(s: string): 'ok' | 'warn' | 'alert' | 'info' | 'muted' {
  const map: Record<string, 'ok' | 'warn' | 'alert' | 'info' | 'muted'> = {
    created:      'info',
    tech_inspect: 'warn',
    med_inspect:  'warn',
    in_progress:  'ok',
    closing:      'warn',
    on_review:    'warn',
    closed:       'muted',
    overdue:      'alert',
  }
  return map[s] ?? 'muted'
}
