// Единое форматирование строки корректировки (before/after op) — приёмка
// 02.10.2026, п.8: RevisionDraftBar.vue/RevisionReviewPanel.vue/
// RevisionDiffTable.vue каждый по-своему дампили сырой JSON поля ("250 000,00
// ₽, null, null, null, one_time, null… → 1 189 896,00 ₽"). Правило №6 — ОДНА
// функция разбора диффа строки на всех трёх (плюс "было/станет" в диалоге
// рассинхронизации SubsidyRevisionReviewView.vue — тот же паттерн форматера).
// Подписи полей — те же, что уже используются в PlannedItemEditDialog.vue/
// FeoTreeRow.vue (не придумываем новые русских названий).
import { formatCurrency } from './format'
import type { RevisionOp } from './useSubsidyRevision'

const FIELD_LABELS: Record<string, string> = {
  amount: 'Сумма',
  planned_amount: 'Сумма',
  budget: 'Бюджет субсидии',
  quantity: 'Количество',
  planned_quantity: 'Количество',
  unit_price: 'Цена за единицу',
  unit: 'Ед. изм.',
  name: 'Наименование',
  code: 'Код',
  // То же название, что и у переключателя в диалоге позиции
  // (PlannedItemEditDialog.vue: «Тип платежа», кнопки «Разовый»/«Ежемесячный») —
  // раньше было подписано «Финансирование», человек это не связывал с полем формы.
  payment_mode: 'Тип платежа',
  planned_date: 'Дата потребности',
  monthly_start_date: 'Начало периода',
  monthly_end_date: 'Конец периода',
  monthly_amount: 'Платёж за месяц',
  months_count: 'Срок (мес.)',
  item_type: 'Тип',
  feo_quantity: 'Кол-во по ФЭО',
  feo_unit_price: 'Цена за единицу по ФЭО',
  feo_amount: 'Сумма по ФЭО',
  parent_id: 'Родительская категория',
  is_active: 'Активна',
}

const PAYMENT_MODE_LABELS: Record<string, string> = { one_time: 'Разовый', monthly: 'Ежемесячный' }

const MONEY_FIELDS = new Set([
  'amount', 'planned_amount', 'budget', 'unit_price', 'monthly_amount', 'feo_unit_price', 'feo_amount',
])

function formatFieldValue(key: string, v: unknown): string {
  if (v == null || v === '') return '—'
  if (key === 'payment_mode') return PAYMENT_MODE_LABELS[String(v)] || String(v)
  if (typeof v === 'boolean') return v ? 'да' : 'нет'
  if (typeof v === 'number') return MONEY_FIELDS.has(key) ? formatCurrency(v) : String(v)
  return String(v)
}

export interface FormattedOpChange {
  field: string
  label: string
  before: string
  after: string
  delta: string | null
}

type OpLike = Pick<RevisionOp, 'op_type' | 'before' | 'after'>

/** Только РЕАЛЬНО изменённые поля (пропускает null==null, служебные снимки
 * вида `_committed_amount`) — используется всеми тремя компонентами
 * (Правило №6, второй разбор диффа не заводим). */
export function formatOpChanges(op: OpLike): FormattedOpChange[] {
  const before = op.before || {}
  const after = op.after || {}
  const keys = op.op_type === 'delete'
    ? Object.keys(before)
    : Array.from(new Set([...Object.keys(before), ...Object.keys(after)]))
  const out: FormattedOpChange[] = []
  for (const key of keys) {
    if (key.startsWith('_')) continue // служебные снимки (_committed_amount и т.п.)
    const bVal = before[key]
    const aVal = after[key]
    if (op.op_type === 'update' || op.op_type === 'move') {
      if (JSON.stringify(bVal ?? null) === JSON.stringify(aVal ?? null)) continue
    } else if (bVal == null && aVal == null) {
      continue
    }
    // Служебные поля без русской подписи (is_feo_breakdown, is_internal_plan,
    // is_composite и т.п.) — не показываем вовсе, не дампим сырой ключ
    // (приёмка 02.10.2026, п.2). После бэкендового фикса (before/after строки
    // несут только РЕАЛЬНО изменённые поля группы) это по большей части уже
    // не должно срабатывать, но белый список остаётся второй линией защиты —
    // неопознанное поле не утечёт в интерфейс проверяющего текстом ключа.
    const label = FIELD_LABELS[key]
    if (!label) continue
    let delta: string | null = null
    if (typeof bVal === 'number' && typeof aVal === 'number' && MONEY_FIELDS.has(key)) {
      const d = aVal - bVal
      if (Math.abs(d) >= 0.005) delta = `${d > 0 ? '+' : ''}${formatCurrency(d)}`
    }
    out.push({ field: key, label, before: formatFieldValue(key, bVal), after: formatFieldValue(key, aVal), delta })
  }
  return out
}

/** Строка-сводка для create/update/move — "Сумма: 250 000 → 1 189 896
 * (+939 896); Количество: 1 → 2"; create — "Новая позиция: <имя>, сумма …";
 * delete — "Удаление: <имя>, было …". entityLabel — "Плановая позиция"/"Статья
 * ФЭО" и т.п. (op.path уже несёт это — передавать не обязательно). */
export function formatOpSummary(op: OpLike, entityName?: string | null): string {
  const changes = formatOpChanges(op)
  const primaryAmount = () => changes.find((c) => c.field === 'amount' || c.field === 'planned_amount' || c.field === 'budget')
  if (op.op_type === 'create') {
    const name = entityName || (op.after as any)?.name || 'без названия'
    const amount = primaryAmount()
    return amount ? `Новая позиция: ${name}, сумма ${amount.after}` : `Новая позиция: ${name}`
  }
  if (op.op_type === 'delete') {
    const name = entityName || (op.before as any)?.name || 'без названия'
    const amount = primaryAmount()
    return amount ? `Удаление: ${name}, было ${amount.before}` : `Удаление: ${name}`
  }
  if (!changes.length) return '—'
  return changes.map((c) => `${c.label}: ${c.before} → ${c.after}${c.delta ? ` (${c.delta})` : ''}`).join('; ')
}

/** Строка «прибавлено/снято/из свободных денег субсидии → сходится|не хватает»
 * (приёмка 02.10.2026, п.3 — «связка 1: прибавлено X, снято Y, баланс −Z — не
 * хватает Z» человек не понимал). Общий язык для шапки связки
 * (RevisionReviewPanel.vue) и общего баннера нехватки (SubsidyRevisionReviewView.vue)
 * — Правило №6, второй текст не заводим. `takenFromFree` бэкенд отдельно не
 * отдаёт — считаем единственной формулой здесь: added − removed − shortfall
 * (ровно то, что subsidy_revision_floor.compute_balance реально забрал из
 * remaining_free для этой связки/баланса в целом). */
export function formatBundleMoneyLine(added: number, removed: number, shortfall: number): string {
  const takenFromFree = Math.max(0, added - removed - shortfall)
  const tail = shortfall > 0.5 ? `не хватает ${formatCurrency(shortfall)}` : 'сходится'
  return `прибавлено ${formatCurrency(added)}, снято ${formatCurrency(removed)}, из свободных денег субсидии ${formatCurrency(takenFromFree)} → ${tail}`
}
