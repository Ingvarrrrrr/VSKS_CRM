// useWishesContext.ts — общий контекст модуля «Заявки» (WishesView.vue и его
// компоненты/композаблы в components/wishes и composables/wishes).
//
// Владелец CLAUDE.md ПРАВИЛО №6 (один показатель — один источник истины): справочники
// (subsidies/allFeoCategories/users/events/assignableIds/allOrgs), проверка прав can()
// и общие форматтеры/лейблы статусов живут ЗДЕСЬ один раз, вместо копии в каждом новом
// файле. Создаётся ОДИН раз в WishesView.vue (provideWishesContext), читается через
// useWishesContext() в дочерних компонентах (provide/inject, типизированный ключ).
//
// Разбиение WishesView.vue (5962 строки) на компоненты — рефакторинг БЕЗ изменения
// поведения, см. задание сессии. Все функции ниже — дословный перенос из
// WishesView.vue, изменены только место объявления и способ доступа (не глобальные
// переменные модуля, а поля возвращаемого объекта).
import { computed, inject, provide, ref, type ComputedRef, type InjectionKey, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { formatMoney } from '@/utils/formatMoney'
import { useToast, type ToastType } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import type {
  Subsidy, FeoCategory, EventItem, User, Wish, WishPurchaseSummary,
  ExcessWarning, PurchaseSync,
} from './wishTypes'

// Phase 31-06: GALA-orange for unseen-changes badges
export const GALA_ORANGE = '#fb923c'

export const statusColor: Record<string, string> = {
  draft: 'grey',
  submitted: 'blue',
  approved: 'green',
  rejected: 'red',
  converted: 'purple',
}
export const statusLabel: Record<string, string> = {
  draft: 'Черновик',
  submitted: 'На согласовании',
  approved: 'Согласовано',
  rejected: 'Не согласовано',
  converted: 'Передано в исполнение',
}

// Priority
export const priorityColor: Record<string, string> = {
  low: 'grey',
  medium: 'blue',
  high: 'orange',
  urgent: 'red',
}
export const priorityLabel: Record<string, string> = {
  low: 'Низкий',
  medium: 'Средний',
  high: 'Высокий',
  urgent: 'Срочный',
}
export const priorityOptions = [
  { title: 'Низкий', value: 'low' },
  { title: 'Средний', value: 'medium' },
  { title: 'Высокий', value: 'high' },
  { title: 'Срочный', value: 'urgent' },
]

const ADMIN_ROLES = ['superadmin', 'account_owner', 'org_admin', 'admin']
const MANAGER_ROLES = ['superadmin', 'account_owner', 'org_admin', 'admin', 'manager']

// «От кого»: Фамилия И.О. вместо полного ФИО
export function shortName(full?: string | null): string {
  if (!full) return ''
  const parts = full.trim().split(/\s+/)
  if (parts.length < 2) return parts[0] ?? ''
  return parts[0] + ' ' + parts.slice(1, 3).map(p => (p[0] ?? '').toUpperCase() + '.').join('')
}
// Участники заявки (WishMember) без дублирования автора — автор выделен отдельно
export function wishCoAuthors(w: { creator_name?: string | null; member_names?: string[] }): string[] {
  const author = shortName(w.creator_name)
  const seen = new Set<string>([author])
  const out: string[] = []
  for (const n of w.member_names || []) {
    const s = shortName(n)
    if (s && !seen.has(s)) { seen.add(s); out.push(s) }
  }
  return out
}
// «Кому»: назначенный или цепочка согласующих (Фамилия И.О.)
export function wishRecipients(w: { assigned_to_name?: string | null; approver_names?: string[] }): string {
  if (w.assigned_to_name) return shortName(w.assigned_to_name)
  return (w.approver_names || []).map(shortName).join(' → ')
}

export function formatPrice(price: number) {
  return price.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 })
}

// Владелец, 2026-08-13: столбец «сумма заявки» на /wishes. Бэк батчем считает
// items_total (Σ total_price позиций) и в списке, и в карточке — используем его;
// если поле почему-то не пришло (переходный момент/старый кэш), считаем сами из
// items. ⚠️ НЕ используем total_amount как фолбэк — по подтверждению бэкенда это
// мёртвое поле (никогда не заполнялось), оставлено в типе как есть, но не трогается.
export function wishItemsTotal(w: Wish): number | null {
  if (w.items_total != null) {
    const n = Number(w.items_total)
    if (Number.isFinite(n)) return n
  }
  if (Array.isArray(w.items) && w.items.length) {
    const sum = w.items.reduce((s, i) => s + (Number(i.total_price) || 0), 0)
    if (sum > 0) return sum
  }
  return null
}

export function formatDate(dateStr: string) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

// Задача 1 (сессия 2026-08-20): строка решения в цепочке согласования
// («Согласовал: ... вместо ... · 20.08.2026 14:49») требует времени, а не
// только даты — своего хелпера с временем в файле не было, минимальный,
// без сторонних библиотек.
export function formatDateTime(dateStr?: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const date = d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
  const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  return `${date} ${time}`
}

// Владелец, 2026-08-13: «остановка заявки» — крупная подпись под алертом.
export function stoppedByLine(w: { stopped_by_name?: string | null; stopped_at?: string | null; stopped_reason?: string | null }): string {
  const who = w.stopped_by_name || 'неизвестно кем'
  const when = w.stopped_at ? formatDate(w.stopped_at) : ''
  let line = `остановил${when ? ' ' + who + ',' : ' ' + who} ${when}`.trim()
  if (w.stopped_reason) line += ` — ${w.stopped_reason}`
  return line
}

// Владелец, 2026-08-19: «нужно, чтобы было видно, кто отклонил» — строка для
// шапки диалога и tooltip'а статуса «Не согласована» в списке.
export function rejectedByLine(w: { rejected_by_name?: string | null; rejected_at?: string | null; rejection_reason?: string | null }): string {
  const who = w.rejected_by_name || 'неизвестно кем'
  const when = w.rejected_at ? formatDate(w.rejected_at) : ''
  let line = `Отклонил: ${who}${when ? ', ' + when : ''}`
  if (w.rejection_reason) line += ` — ${w.rejection_reason}`
  return line
}

// Подпись пункта меню: «№123 — Заключён договор — 45 000 ₽» (+ «остановлена»).
export function purchaseMenuLabel(p: WishPurchaseSummary): string {
  const num = p.registry_number || (p.purchase_number != null ? `№${p.purchase_number}` : `№${p.id}`)
  const parts = [num, p.status_label || p.status].filter(Boolean)
  const amt = Number(p.amount)
  if (p.amount != null && !Number.isNaN(amt)) parts.push(formatPrice(amt))
  return parts.join(' — ')
}

export function wishPurchasesLabel(w: Wish): string {
  const n = (w.purchases || w.purchase_ids || []).length
  return n > 1 ? `Закупки (${n})` : 'Закупка'
}

export interface WishesContext {
  router: ReturnType<typeof useRouter>
  can: (action: string) => boolean
  userRole: string
  currentUserId: number
  isAdmin: ComputedRef<boolean>
  isManagerOrAdmin: ComputedRef<boolean>
  isSaas: ComputedRef<boolean>
  subsidies: Ref<Subsidy[]>
  allFeoCategories: Ref<FeoCategory[]>
  users: Ref<User[]>
  events: Ref<EventItem[]>
  assignableAll: Ref<boolean>
  assignableIds: Ref<Set<number>>
  allOrgs: Ref<{ id: number; name: string; root_org_id?: number | null; parent_org_id?: number | null }[]>
  requiresConsent: (userId: number | null | undefined) => boolean
  showSnack: (text: string, color?: ToastType, opts?: { duration?: number }) => void
  clearStaleSuccessToasts: () => void
  formatPrice: typeof formatPrice
  formatDate: typeof formatDate
  formatDateTime: typeof formatDateTime
  formatMoney: typeof formatMoney
  shortName: typeof shortName
  wishCoAuthors: typeof wishCoAuthors
  wishRecipients: typeof wishRecipients
  wishItemsTotal: typeof wishItemsTotal
  stoppedByLine: typeof stoppedByLine
  rejectedByLine: typeof rejectedByLine
  purchaseMenuLabel: typeof purchaseMenuLabel
  wishPurchasesLabel: typeof wishPurchasesLabel
  goToPurchase: (id: number) => void
  goToWishPurchases: (w: Wish) => void
  goToMatchedPurchase: (item: any) => void
  showExcessWarnings: (warnings: ExcessWarning[] | null | undefined, actionPrefix: string) => void
  showPurchaseSync: (sync: PurchaseSync | null | undefined) => void
  feoCategoryNameById: (id?: number | null) => string
}

export const WISHES_CONTEXT_KEY: InjectionKey<WishesContext> = Symbol('wishes-context')

// Создаётся ОДИН раз в WishesView.vue (родитель). Владелец (2026-08-19): «менять
// позиции может только тот, кто имеет право» — см. canEditWishFeo (useWishForm.ts),
// тот же паттерн, что и PaymentRegistryView.vue.
export function provideWishesContext(): WishesContext {
  const router = useRouter()
  const authStore = useAuthStore()
  function can(action: string) {
    return authStore.hasAction?.(action) ?? true
  }

  const userRole = localStorage.getItem('user_role') || ''
  const currentUserId = Number(localStorage.getItem('user_id') || '0')
  const isAdmin = computed(() => ADMIN_ROLES.includes(userRole))
  const isManagerOrAdmin = computed(() => MANAGER_ROLES.includes(userRole))
  const isSaas = computed(() => ['superadmin', 'account_owner'].includes(userRole))

  const subsidies = ref<Subsidy[]>([])
  const allFeoCategories = ref<FeoCategory[]>([])
  const users = ref<User[]>([])
  const events = ref<EventItem[]>([])
  const allOrgs = ref<{ id: number; name: string; root_org_id?: number | null; parent_org_id?: number | null }[]>([])

  // Кому текущий может ставить задачи без согласия (для пометки в пикере участников).
  // assignableAll=true → SaaS-роль, согласование не нужно ни для кого.
  const assignableAll = ref(false)
  const assignableIds = ref<Set<number>>(new Set())
  function requiresConsent(userId: number | null | undefined): boolean {
    if (!userId || assignableAll.value) return false
    if (userId === currentUserId) return false
    return !assignableIds.value.has(userId)
  }

  // Snackbar — единый механизм (useToast + ToastContainer, смонтирован в App.vue).
  // По умолчанию уведомление НЕ исчезает само (duration=0): результат действия
  // пользователя (согласование, сохранение, ошибка) должен быть прочитан, а не
  // пропасть за 3-4 секунды. Стек не затирает предыдущие — новые тосты копятся.
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success', opts?: { duration?: number }) {
    toast.addToast(text, color, opts)
  }
  // Владелец (2026-09-04, п.5 задачи заявки №54): «уведомления от предыдущей заявки
  // остаются на экране и читаются как отчёт о текущей» — см. подробный комментарий
  // в исходном WishesView.vue. Тосты — общий модульный стек, сам механизм не трогаем;
  // локально для «Заявок» при открытии ЛЮБОЙ карточки убираем уже показанные
  // success-тосты (они точно относятся к другому, уже завершённому действию).
  function clearStaleSuccessToasts() {
    for (const t of [...toast.toasts.value]) {
      if (t.type === 'success') toast.removeToast(t.id)
    }
  }

  function goToPurchase(id: number) {
    router.push(`/orders/${id}/edit`)
  }
  // Конвертация разбивает заявку на несколько закупок: одна → сразу в карточку,
  // несколько → выпадающий список (см. purchaseMenuLabel/goToPurchase) в шаблоне —
  // эта функция остаётся фолбэком для одной закупки / случая без w.purchases.
  // Пункт 4 (владелец, 2026-08-13): «переход в закупки, исполняемые на основании
  // заявки; несколько — выпадающий список». Навигация — тем же путём, что и везде
  // в проекте (router.push(`/orders/{id}/edit`), см. DashboardView/PlanView и др.).
  function goToWishPurchases(w: Wish) {
    const purchases = w.purchases || []
    if (purchases.length === 1) { router.push(`/orders/${purchases[0]!.id}/edit`); return }
    const ids = w.purchase_ids || []
    if (ids.length > 1) router.push({ path: '/orders', query: { wish_id: String(w.id) } })
    else router.push(`/orders/${w.purchase_id}/edit`)
  }
  function goToMatchedPurchase(item: any) {
    const pid = item?.purchase_match?.purchase_id
    if (!pid) return
    router.push(`/orders/${pid}/edit`)
  }

  function feoCategoryNameById(id?: number | null): string {
    if (id == null) return ''
    return allFeoCategories.value.find(c => c.id === id)?.name || `#${id}`
  }

  // Предупреждение о превышении ФЭО (задача владельца 2026-08-12: «согласовали —
  // всё равно конвертировать в закупку, но заметно показать, из-за чего
  // превышение»). Бэкенд отдаёт его ключом excess_warnings в ответе эндпоинтов
  // согласования/конвертации заявки (decide/approve/convert) — пустой массив,
  // пока превышения нет.
  function showExcessWarnings(warnings: ExcessWarning[] | null | undefined, actionPrefix: string) {
    if (!warnings || !warnings.length) return
    const parts = warnings.map(w => {
      const itemsText = (w.items || []).map(i => `${i.name} — ${formatPrice(i.amount)}`).join(', ')
      return `Категория «${w.category_name}»: план превышает ФЭО на ${formatPrice(w.excess_amount)}${itemsText ? ` (позиции: ${itemsText})` : ''}`
    })
    // Владелец (2026-09-03): «перебор в ветке не блокирует, но виден как пометка» —
    // раньше здесь текст утверждал, что закупка «не пойдёт дальше "Ведётся работа"»
    // (это было правдой ДО правки assert_no_unapproved_excess). Теперь перекос
    // ОТДЕЛЬНОЙ категории ФЭО НЕ блокирует движение закупки вообще (суммарный
    // потолок ФЭО в целом — единственный жёсткий контроль) — текст обязан
    // отражать это, иначе врёт пользователю о несуществующей блокировке.
    showSnack(
      `${actionPrefix} ${parts.join('; ')}. Это ориентир, не блокировка — закупка продолжает двигаться по стадиям. `
      + `При желании перенесите позиции в другую категорию или согласуйте превышение в панели субсидии.`,
      'warning',
    )
  }

  const _SYNC_FIELD_LABELS: Record<string, string> = {
    quantity: 'количество', unit_price: 'цена', total_price: 'сумма',
  }
  // Задача владельца (сессия 2026-08-21, план «Превышение плана видно везде; закупка
  // знает свою заявку и обновляется вместе с ней»): «повторное согласование обновляет
  // закупку из заявки» + «перед применением показать, что именно изменится».
  function showPurchaseSync(sync: PurchaseSync | null | undefined) {
    if (!sync) return
    const label = sync.registry_number || `№${sync.purchase_id}`
    if (sync.blocked_reason) {
      showSnack(`Закупка ${label} НЕ обновлена из заявки: ${sync.blocked_reason}`, 'warning')
      return
    }
    const parts: string[] = []
    if (sync.subject_before != null && sync.subject_after != null && sync.subject_before !== sync.subject_after) {
      parts.push(`предмет: «${sync.subject_before}» → «${sync.subject_after}»`)
    }
    const added = sync.items_added || []
    const removed = sync.items_removed || []
    const changed = sync.items_changed || []
    const keptManual = sync.items_kept_manual || []
    if (added.length) parts.push(`добавлено позиций: ${added.length} (${added.map(i => i.name).join(', ')})`)
    if (removed.length) parts.push(`убрано позиций: ${removed.length} (${removed.map(i => i.name).join(', ')})`)
    if (changed.length) parts.push(`изменено позиций: ${changed.length} (${changed.map(i => i.name).join(', ')})`)
    if (keptManual.length) parts.push(`оставлены как есть (заведены в закупке): ${keptManual.length} (${keptManual.map(i => i.name).join(', ')})`)
    if (!parts.length) {
      showSnack(`Закупка ${label} сверена с заявкой — изменений в составе нет`, 'info')
    } else {
      showSnack(`Закупка ${label} обновлена из заявки — ${parts.join('; ')}.`, 'info')
    }

    const conflicted = sync.items_conflicted || []
    if (conflicted.length) {
      const conflictText = conflicted
        .map(c => `${c.name} (${_SYNC_FIELD_LABELS[c.field] || c.field}: в закупке ${c.in_purchase ?? '—'}, в заявке ${c.in_wish ?? '—'})`)
        .join('; ')
      showSnack(
        `Закупка ${label}: значения правили прямо в закупке — из заявки НЕ перезаписаны: ${conflictText}. Сверьте вручную.`,
        'warning',
      )
    }
  }

  const ctx: WishesContext = {
    router, can, userRole, currentUserId, isAdmin, isManagerOrAdmin, isSaas,
    subsidies, allFeoCategories, users, events, assignableAll, assignableIds, allOrgs,
    requiresConsent, showSnack, clearStaleSuccessToasts,
    formatPrice, formatDate, formatDateTime, formatMoney,
    shortName, wishCoAuthors, wishRecipients, wishItemsTotal,
    stoppedByLine, rejectedByLine, purchaseMenuLabel, wishPurchasesLabel,
    goToPurchase, goToWishPurchases, goToMatchedPurchase,
    showExcessWarnings, showPurchaseSync, feoCategoryNameById,
  }
  provide(WISHES_CONTEXT_KEY, ctx)
  return ctx
}

export function useWishesContext(): WishesContext {
  const ctx = inject(WISHES_CONTEXT_KEY)
  if (!ctx) throw new Error('useWishesContext() called without provideWishesContext() in an ancestor (WishesView.vue)')
  return ctx
}

// Реэкспорт apiFetch не требуется — потребители импортируют его напрямую из '@/api'.
export { apiFetch }
