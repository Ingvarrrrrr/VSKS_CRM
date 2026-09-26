// Подписи полей для ленты истории ФЭО (feo_item/feo_category) — волна 3, 26.09.
//
// Правило №6 (один показатель — один источник истины): backend/app/errors.py
// уже держит словарь field_labels для ЭТИХ ЖЕ полей (там он используется для
// текста ошибок валидации 422). Здесь — НЕ вторая копия того же механизма на
// том же языке, а неизбежное зеркало через границу Python/TypeScript (бэкенд
// не отдаёт подписи полей через API, а заводить для этого отдельный эндпоинт
// ради одной ленты истории — тяжелее, чем поддерживать два синхронных списка).
// При добавлении нового поля в любой из двух списков — проверить и обновить
// оба (см. комментарий у field_labels в backend/app/errors.py).
export const FEO_HISTORY_FIELD_LABELS: Record<string, string> = {
  // ── Общие для FeoPlannedItem и FeoCategory ──
  name: 'Наименование',
  is_active: 'Активна',
  description: 'Пояснение',
  code: 'Код',
  appendix: 'Приложение',
  unit: 'Ед. изм.',
  parent_id: 'Родительская категория',
  feo_category_id: 'Категория ФЭО',

  // ── FeoPlannedItem ──
  quantity: 'Количество',
  item_type: 'Тип (товар/услуга/работа)',
  amount: 'Сумма (план)',
  unit_price: 'Цена за единицу',
  notes: 'Примечание',
  payment_mode: 'Тип платежа',
  planned_date: 'Дата потребности',
  monthly_start_date: 'Начало периода (ежемесячно)',
  monthly_end_date: 'Конец периода (ежемесячно)',
  months_count: 'Количество месяцев',
  monthly_amount: 'Платёж за месяц',
  auto_created: 'Заведена автоматически',
  sort_order: 'Порядок в списке',
  is_feo_breakdown: 'Происхождение: по ФЭО',
  is_internal_plan: 'Происхождение: внутренний план',
  feo_quantity: 'Количество по ФЭО',
  feo_unit_price: 'Цена за единицу по ФЭО',
  feo_amount: 'Сумма по ФЭО',

  // ── FeoCategory ──
  budget: 'Финансирование по ФЭО',
  feo_unit: 'Ед. изм. по ФЭО',
  planned_quantity: 'Плановое количество',
  planned_amount: 'Плановая цена за единицу',
  plan_source: 'Способ расчёта плана',
  manual_plan_amount: 'Плановая сумма (вручную)',
}

export function feoHistoryFieldLabel(field: string): string {
  return FEO_HISTORY_FIELD_LABELS[field] ?? field
}
