// ordersLabels.ts — чистые функции/константы для меток, цветов и статусов
// закупок. Дословный перенос из OrdersView.vue, без изменения поведения.
// Единый источник цвета/подписи статуса закупки: frontend/src/constants/purchaseStatus.ts (Правило №6)
import { PURCHASE_STATUS_ORDER, purchaseStatusLabel, purchaseStatusColor, purchaseMethodLabel as sharedMethodLabel } from '@/constants/purchaseStatus'
import { toAmount } from '@/types/purchaseAmounts'
import type { Purchase } from './ordersTypes'

export const FRAMEWORK_TYPES = new Set(['framework_cumulative', 'framework_with_amount'])
export function isItemFramework(item: Purchase) { return FRAMEWORK_TYPES.has(item.purchase_contract_type || '') }

export function purchaseTypeLabel(item: Purchase): string {
  if (item.purchase_method === 'advance') return 'Авансовый'
  if (isItemFramework(item)) return 'Рамочный'
  if (item.purchase_basis === 'invoice') return 'По счёту'
  if (item.purchase_method === 'single' || item.purchase_contract_type === 'single') return 'Разовый'
  if (item.purchase_method === 'competitive') return 'Конкурентный'
  return 'Разовый'
}
export function purchaseMethodLabel(m?: string): string {
  // Единый источник подписи: frontend/src/constants/purchaseStatus.ts (Правило №6)
  if (!m) return '—'
  return sharedMethodLabel(m)
}
export function purchaseTypeColor(item: Purchase): string {
  if (item.purchase_method === 'advance') return 'purple'
  if (isItemFramework(item)) return 'indigo'
  if (item.purchase_basis === 'invoice') return 'grey'
  if (item.purchase_method === 'competitive') return 'cyan'
  return 'green'
}
export function advancePersonLabel(item: Purchase): string {
  return item.responsible_person || `#${item.assigned_user_id}` || '—'
}

// QA-правка (2026-08-21, дефект 4): чип «Превышение ФЭО» раньше красился красным
// и грозил блокировкой для ЛЮБОГО item.feo_excess — но с тех пор как согласованное
// превышение перестало гасить сам feo_excess (владелец, п.4 в _compute_purchase_feo_excess),
// это стало вводить в заблуждение: уже согласованное превышение никого не блокирует.
// Правка владельца (2026-09-03, «перекос ветки — предупреждение, не блокировка»):
// текст «закупка не пойдёт дальше "Ведётся работа"» тоже стал неправдой —
// assert_no_unapproved_excess (feo_plan.py) больше НЕ блокирует движение закупки
// перекосом ОТДЕЛЬНОЙ категории (excess_amount/excess_over_feo), только жёсткий
// потолок ФЭО в целом (PLAN_OVER_SUBSIDY_CEILING) остаётся непроходимым. Чип
// остаётся видимым (перекос обязан быть виден), но текст больше не обещает
// несуществующую блокировку. Различаем по feo_excess_state: not_requested —
// красный (заметно, но без утверждения про блокировку); pending — на согласовании
// (жёлтый); approved — согласовано (спокойный зелёный).
export function feoExcessChip(item: Purchase): { color: string; text: string; title: string } {
  const hint = item.feo_excess_hint ? item.feo_excess_hint + ' — ' : ''
  const state = item.feo_excess_state || 'not_requested'
  if (state === 'approved') {
    return {
      color: 'green-darken-1',
      text: 'Превышение ФЭО согласовано',
      title: `${hint}превышение плана ФЭО согласовано`,
    }
  }
  if (state === 'pending') {
    return {
      color: 'amber-darken-2',
      text: 'Превышение ФЭО на согласовании',
      title: `${hint}превышение плана ФЭО отправлено на согласование`,
    }
  }
  return {
    color: 'red',
    text: 'Превышение ФЭО',
    title: `${hint}план по этой категории ФЭО превышает её финансирование — ориентир, не блокировка; при желании перенесите позиции в другую категорию или согласуйте превышение`,
  }
}

export const STATUS_ORDER = PURCHASE_STATUS_ORDER
export const STATUS_LABEL: Record<string, string> = Object.fromEntries(
  PURCHASE_STATUS_ORDER.map(s => [s, purchaseStatusLabel(s)])
)
export function statusLabelFor(item: Purchase, status?: string): string {
  const s = status || item.status
  if (s === 'contracted' && isItemFramework(item)) return 'Заказ'
  return STATUS_LABEL[s] || s
}
export const STATUS_COLOR: Record<string, string> = Object.fromEntries(
  PURCHASE_STATUS_ORDER.map(s => [s, purchaseStatusColor(s)])
)
export const APPROVAL_STATUS_COLOR: Record<string, string> = {
  in_progress: 'orange', approved: 'green', rejected: 'error',
}
export const APPROVAL_STATUS_LABEL: Record<string, string> = {
  in_progress: 'На согласовании', approved: 'Согласовано', rejected: 'Отклонено',
}
export const statusItems = STATUS_ORDER.map(v => ({ value: v, label: STATUS_LABEL[v] ?? v, color: STATUS_COLOR[v] ?? 'grey' }))

export function transitionRequired(item: Purchase): Record<string, { field: keyof Purchase; label: string }[]> {
  const fw = isItemFramework(item)
  return {
  contracted: [
    { field: 'contract_number', label: fw ? 'Номер заказа' : 'Номер договора' },
    { field: 'contract_date', label: fw ? 'Дата заказа' : 'Дата договора' },
  ],
  delivered: [
    { field: 'acceptance_doc_name', label: 'Наименование закрывающего документа' },
    { field: 'acceptance_doc_date', label: 'Дата закрывающего документа' },
    { field: 'acceptance_doc_number', label: 'Номер закрывающего документа' },
    { field: 'acceptance_doc_amount', label: 'Сумма закрывающего документа' },
  ],
  paid: [
    { field: 'payment_doc_number', label: 'Номер платёжного поручения' },
    { field: 'payment_doc_date', label: 'Дата платёжного поручения' },
    { field: 'payment_amount', label: 'Сумма платежа' },
  ],
}}

export const nextStatus = (current: string): string | null => {
  const idx = STATUS_ORDER.indexOf(current)
  return idx >= 0 && idx < STATUS_ORDER.length - 1 ? (STATUS_ORDER[idx + 1] ?? null) : null
}

// Все категории ФЭО, к которым относится закупка через свои позиции —
// COALESCE(item.feo_category_id, purchase.feo_category_id) на каждую позицию,
// как считает дерево ФЭО (см. backend/app/services/feo_plan.py, cat_col).
// Позиция без своей категории наследует категорию закупки; закупка без позиций
// (или все позиции без own-категории) — просто своя категория.
export function purchaseFeoCategoryIds(o: Purchase): number[] {
  const ids = new Set<number>()
  if (o.items && o.items.length > 0) {
    for (const it of o.items) {
      const cid = it.feo_category_id ?? o.feo_category_id
      if (cid != null) ids.add(cid)
    }
  } else if (o.feo_category_id != null) {
    ids.add(o.feo_category_id)
  }
  return [...ids]
}

// Владелец, 2026-08-13: «закупка остановлена {ФИО}, {дата}» — stopped_at приходит
// полным ISO-таймстампом (не YYYY-MM-DD, как formatDate ниже ожидает), поэтому
// отдельная функция без ручного split.
export function stoppedPurchaseLine(p: { stopped_by_name?: string | null; stopped_at?: string | null }): string {
  const who = p.stopped_by_name || 'неизвестно кем'
  const when = p.stopped_at ? new Date(p.stopped_at).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }) : ''
  return `остановил ${who}${when ? ', ' + when : ''}`
}

export const itemDisplayName = (p: Purchase) => {
  if (p.items && p.items.length > 0) {
    return p.items.length === 1
      ? p.items[0]!.item_name
      : `${p.items[0]!.item_name} (+${p.items.length - 1})`
  }
  return p.item_name || '—'
}

export const formatDate = (d: string) => {
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}

// ПРАВИЛО №6 (2026-09-05/06): «сумма закупки» больше не считается на фронте —
// читаем готовое amounts.effective (единый расчёт по стадии, см.
// backend/app/services/purchase_amounts.py). Фолбэк на null оставлен только
// для defensive-случая, когда бэкенд ещё не проставил amounts (не должно
// случаться на GET /api/purchases, см. _purchase_to_full).
export const effectivePrice = (item: Purchase): number | null => toAmount(item.amounts?.effective)

export const orderTypeOptions = [
  { label: 'Разовый', value: 'one_time' },
  { label: 'Рамочный', value: 'framework' },
  { label: 'Авансовый', value: 'advance' },
  { label: 'По счёту', value: 'invoice' },
]

export function getOrderTypeKey(o: Purchase): string {
  if (o.purchase_method === 'advance') return 'advance'
  if (o.purchase_contract_type === 'single' || o.purchase_method === 'single') return 'one_time'
  if ((o.purchase_contract_type || '').startsWith('framework')) return 'framework'
  if (o.purchase_basis === 'invoice') return 'invoice'
  return 'one_time'
}
