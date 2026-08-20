// useWishLive.ts — «живое» обновление открытой заявки (сессия 2026-08-20, Задача 2
// фронтенд-плана «кто согласовал за кого + живое обновление заявки»).
//
// Работает ТОЛЬКО пока открыт диалог заявки (см. isOpen): setInterval 20с +
// visibilitychange + focus (образцы: useApprovalsBadge.ts — интервал и очистка;
// useChat.ts:262-272 — visibilitychange/focus). На каждый тик перечитывает
// GET /wishes/{id}/approvers и GET /wishes/{id} и обновляет ТОЛЬКО список
// согласующих и перечисленные шапочные поля заявки — сама форма (wishForm),
// куда автосохраняются правки ФЭО с задержкой, этим композаблом НИКОГДА не
// трогается, иначе он затирал бы несохранённые правки пользователя.
import { onUnmounted, watch, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'

const LIVE_INTERVAL_MS = 20_000

export interface WishLiveApprover {
  id: number
  user_id: number | null
  full_name?: string | null
  status: string
  comment?: string | null
  decided_at: string | null
  decided_by_user_id?: number | null
  decided_by_name?: string | null
  is_on_behalf?: boolean
}

export interface WishLiveHeader {
  status: string
  rejected_by_name?: string | null
  rejected_at?: string | null
  approved_by?: number
  purchase_id?: number
  purchases?: { id: number; registry_number?: string | null }[]
}

// Шапочные поля заявки, которые composable вправе трогать в editingWish —
// намеренно короткий и жёсткий список: не items, не execution_deadline,
// не contractor_* и т.д., чтобы не пересечься с автосейвом ФЭО или другими
// правками формы.
const HEADER_KEYS: (keyof WishLiveHeader)[] = [
  'status', 'rejected_by_name', 'rejected_at', 'approved_by', 'purchase_id', 'purchases',
]

export interface UseWishLiveOptions<A extends WishLiveApprover, W extends WishLiveHeader> {
  wishId: Ref<number | null>
  isOpen: Ref<boolean>
  approvers: Ref<A[]>
  wish: Ref<W | null>
  currentUserId: number
  // Существующие флаги автосейва ФЭО (feoAutosaveSaving / feoAutosavePending) —
  // пока true, тик молча пропускается, чтобы не гонять пользователя с сетевым
  // запросом ровно в момент, когда у него есть несохранённые правки.
  isAutosaveBusy: () => boolean
  showSnack: (text: string, color?: ToastType, opts?: { duration?: number }) => void
  // Форматирование ФИО «Фамилия И.О.» — переиспользуем существующий shortName
  // файла-вызывающего, а не заводим свою копию.
  shortName?: (full?: string | null) => string
  // Дёрнуть после обнаруженного ЧУЖОГО изменения: обновить список заявок и бейдж
  // «мои согласования» (loadWishes/loadAllWishes + refreshMyPendingApprovals).
  onExternalChange?: () => void
  intervalMs?: number
}

export function useWishLive<A extends WishLiveApprover, W extends WishLiveHeader>(
  options: UseWishLiveOptions<A, W>,
) {
  const {
    wishId, isOpen, approvers, wish, currentUserId, isAutosaveBusy, showSnack,
    onExternalChange, intervalMs = LIVE_INTERVAL_MS,
  } = options
  const shortName = options.shortName || ((full?: string | null) => full || '')

  let timer: ReturnType<typeof setInterval> | null = null
  let inFlight = false
  let running = false
  // Гонка устаревшего ответа (QA, сессия 2026-08-20): тик читает GET
  // approvers/wish, а ровно пока запрос летит, пользователь мог сам принять
  // решение (decideApprover) и уже применить СВЕЖИЙ ответ сервера в те же
  // approvers/wish refs. Если после этого прилетает более старый ответ тика,
  // он тупо перезатирает свежие данные устаревшим снимком — строка «откатывается»
  // в pending, кнопки решения возвращаются, повторный клик даёт 400. Монотонный
  // счётчик: тик запоминает версию на старте запроса и, если к моменту ответа
  // версия уже другая (кто-то применил более свежие локальные данные, пока тик
  // летел), просто отбрасывает свой устаревший ответ — следующий тик (20с)
  // подтянет актуальное состояние. Вызывающий обязан звать markLocalUpdate()
  // сразу после того, как применяет собственный свежий ответ сервера к тем же
  // approvers/wish refs (см. WishesView.vue::decideApprover).
  let localVersion = 0
  function markLocalUpdate() { localVersion++ }

  function buildChangeMessage(freshWish: W, changedApprover: A | null): string | null {
    // Отклонение одним согласующим отклоняет заявку целиком (см. backend
    // wish_approvals.py::decide_wish_approval) — причина берётся из комментария
    // решившего, отдельное поле заголовка для этого не нужно.
    if (changedApprover && changedApprover.status === 'rejected') {
      const reason = changedApprover.comment ? changedApprover.comment : 'без указания причины'
      return `Заявка отклонена: ${reason}`
    }
    if (freshWish.status === 'converted') {
      const p = freshWish.purchases && freshWish.purchases[0]
      const label = p?.registry_number || (freshWish.purchase_id ? `№${freshWish.purchase_id}` : '')
      return `Заявка согласована и перенесена в закупку${label ? ' ' + label : ''}`
    }
    if (changedApprover && changedApprover.status === 'approved') {
      const who = shortName(changedApprover.decided_by_name) || changedApprover.decided_by_name || 'коллега'
      return `Пока вы работали, ${who} согласовал(а) заявку`
    }
    return null
  }

  async function tick() {
    const wid = wishId.value
    if (!wid || !isOpen.value) return
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
    if (isAutosaveBusy()) return
    if (inFlight) return
    inFlight = true
    const versionAtStart = localVersion
    try {
      const [freshApprovers, freshWish] = await Promise.all([
        apiFetch<A[]>(`/wishes/${wid}/approvers`),
        apiFetch<W>(`/wishes/${wid}`),
      ])
      // Пока запрос летел, диалог могли закрыть или открыть другую заявку —
      // применять устаревший ответ к текущему состоянию нельзя.
      if (wishId.value !== wid || !isOpen.value) return
      // Пока запрос летел, пользователь сам принял решение (или иначе обновил
      // approvers/wish локально) и applied его свежее — этот ответ тика старше,
      // отбрасываем целиком (и approvers, и шапку), следующий тик подтянет факт.
      if (localVersion !== versionAtStart) return

      // Baseline — то, что СЕЙЧАС видно в этих же реактивных refs. Собственные
      // решения пользователя (decideApprover) кладут туда свежий ответ сервера
      // сразу же, до следующего тика — поэтому свои действия здесь не
      // всплывают повторно снэкбаром.
      const prevById = new Map(approvers.value.map(a => [a.id, a]))
      let changedApprover: A | null = null
      for (const fresh of freshApprovers) {
        if (fresh.status !== 'approved' && fresh.status !== 'rejected') continue
        if (fresh.decided_by_user_id === currentUserId) continue // своё решение — не наше дело
        const prev = prevById.get(fresh.id)
        if (!prev || prev.status !== fresh.status || prev.decided_at !== fresh.decided_at) {
          changedApprover = fresh
          break
        }
      }
      const prevWishStatus = wish.value?.status
      const wishStatusChanged = !!prevWishStatus && prevWishStatus !== freshWish.status

      approvers.value = freshApprovers
      if (wish.value) {
        const merged: any = { ...wish.value }
        for (const k of HEADER_KEYS) merged[k] = (freshWish as any)[k]
        wish.value = merged
      }

      if (changedApprover || wishStatusChanged) {
        const msg = buildChangeMessage(freshWish, changedApprover)
        if (msg) showSnack(msg, 'info', { duration: 8000 })
        onExternalChange?.()
      }
    } catch (e: any) {
      console.warn('[wish-live] tick failed:', e?.payload?.message || e?.message)
    } finally {
      inFlight = false
    }
  }

  const onVisibility = () => {
    if (typeof document !== 'undefined' && !document.hidden) tick()
  }
  const onFocus = () => { tick() }

  function start() {
    if (running) return
    running = true
    if (!timer) timer = setInterval(tick, intervalMs)
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', onVisibility)
    if (typeof window !== 'undefined') window.addEventListener('focus', onFocus)
  }

  function stop() {
    running = false
    if (timer) { clearInterval(timer); timer = null }
    if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', onVisibility)
    if (typeof window !== 'undefined') window.removeEventListener('focus', onFocus)
  }

  watch(isOpen, (v) => { if (v) start(); else stop() }, { immediate: true })
  onUnmounted(stop)

  return { start, stop, markLocalUpdate }
}
