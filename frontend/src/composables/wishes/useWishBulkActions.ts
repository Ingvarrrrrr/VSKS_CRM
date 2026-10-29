// useWishBulkActions.ts — массовые действия над заявками (Удалить / Отправить
// на согласование / Передать в план закупок), общие для всех вкладок списка
// заявок (My/Incoming/All). Задача владельца, 29.10.2026.
//
// ПРАВИЛО №6: второй механизм решений НЕ заводим — применимость действия к
// конкретной заявке проверяется ТЕМИ ЖЕ предикатами, что у одиночных кнопок
// (canDeleteWish/canSubmitWish/canConvertWish, useWishActions.ts), а
// исполнение идёт через СУЩЕСТВУЮЩИЕ одиночные эндпоинты (DELETE /wishes/{id},
// POST /wishes/{id}/submit, POST /wishes/{id}/convert) — по образцу массового
// удаления в реестре договоров (useContractsSelection.ts: «без второго
// bulk-delete endpoint — сервера для этого нет»). Фронт вызывает одиночные
// эндпоинты последовательно, по одной заявке — проверки доступа/статуса на
// них уже покрывают ПРАВИЛО №8 (вход, владение, валидный HTTP-код), заводить
// отдельный bulk-роут не требуется.
import { reactive, ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { Wish, ExcessWarning } from './wishTypes'
import type { WishesContext } from './useWishesContext'
import { canDeleteWish, canSubmitWish, canConvertWish } from './useWishActions'
import { formatExcessWarningsText } from './excessWarningsText'

export type BulkWishAction = 'delete' | 'submit' | 'convert'

export interface BulkActionFailure {
  id: number
  title: string
  reason: string
}

// Доработка владельца (ревью 29.10.2026): массовая «Передать в план» не должна
// глушить excess_warnings — то же предупреждение, что одиночная кнопка
// convertWish показывает через ctx.showExcessWarnings (useWishesContext.ts).
// Построение текста — formatExcessWarningsText (excessWarningsText.ts),
// ПРАВИЛО №6: один источник у кнопки и у массового действия, второй расчёт
// здесь не заводим.
export interface BulkActionExcessWarning {
  id: number
  title: string
  text: string
}

export interface BulkActionDialogState {
  show: boolean
  action: BulkWishAction | null
  running: boolean
  progress: number
  total: number
  done: number
  failures: BulkActionFailure[]
  excessWarnings: BulkActionExcessWarning[]
}

function excessWarningsSummary(warnings: ExcessWarning[]): string {
  const { duplicateText, categoryParts } = formatExcessWarningsText(warnings)
  return [duplicateText, categoryParts.join('; ')].filter(Boolean).join(' ')
}

export function useWishBulkActions(options: {
  ctx: WishesContext
  showSnack: (text: string, color?: ToastType) => void
  reloadActiveTab: () => Promise<void>
}) {
  const { ctx, showSnack, reloadActiveTab } = options

  // Выбор — number[] заявок, сбрасывается при смене вкладки/перезагрузке
  // списка (вызывающая сторона, WishesView.vue, чистит selected в watch(activeTab)).
  const selected = ref<number[]>([])
  const clearSelection = () => { selected.value = [] }

  const bulkDialog = reactive<BulkActionDialogState>({
    show: false,
    action: null,
    running: false,
    progress: 0,
    total: 0,
    done: 0,
    failures: [],
    excessWarnings: [],
  })

  // items — текущий список активной вкладки (WishMyTab/WishIncomingTab/WishAllTab)
  // передаётся вызовом, а не хранится здесь — composable не знает, какая вкладка активна.
  let pendingItems: Wish[] = []

  function openBulkConfirm(action: BulkWishAction, items: Wish[]) {
    const items_ = items.filter(w => selected.value.includes(w.id))
    if (!items_.length) return
    pendingItems = items_
    bulkDialog.action = action
    bulkDialog.failures = []
    bulkDialog.excessWarnings = []
    bulkDialog.progress = 0
    bulkDialog.done = 0
    bulkDialog.total = items_.length
    bulkDialog.show = true
  }

  function closeBulkDialog() {
    bulkDialog.show = false
  }

  // Доработка ревью (29.10.2026): причина отказа — конкретная по действию, не
  // общее «неприменимо к статусу». Для 'convert' сначала проверяется право
  // (isManagerOrAdmin) — у остальных двух действий отдельного права нет, его
  // проверяет сам canDeleteWish (владелец аккаунта/автор черновика).
  function applicabilityReason(action: BulkWishAction, w: Wish): string | null {
    if (action === 'delete') {
      return canDeleteWish(w, ctx) ? null : 'удалить можно только свой черновик'
    }
    if (action === 'submit') {
      return canSubmitWish(w) ? null : 'отправить на согласование можно только черновик'
    }
    if (!ctx.isManagerOrAdmin.value) return 'нужны права руководителя'
    return canConvertWish(w, ctx) ? null : 'в план передаётся только согласованная заявка'
  }

  async function runBulkAction() {
    const action = bulkDialog.action
    if (!action) return
    bulkDialog.running = true
    bulkDialog.failures = []
    bulkDialog.excessWarnings = []
    bulkDialog.progress = 0
    let ok = 0
    for (const w of pendingItems) {
      const blockedReason = applicabilityReason(action, w)
      if (blockedReason) {
        bulkDialog.failures.push({ id: w.id, title: w.title || `Заявка №${w.id}`, reason: blockedReason })
        bulkDialog.progress++
        continue
      }
      try {
        if (action === 'delete') {
          await apiFetch(`/wishes/${w.id}`, { method: 'DELETE' })
        } else if (action === 'submit') {
          await apiFetch(`/wishes/${w.id}/submit`, { method: 'POST' })
        } else {
          // Превышение плана (excess_warnings) НЕ блокирует перенос (владелец) —
          // но должно быть видно, одиночная кнопка показывает его через
          // ctx.showExcessWarnings; здесь собираем в отдельный блок итогов,
          // не теряем (доработка ревью 29.10.2026).
          const res = await apiFetch<{ excess_warnings?: ExcessWarning[] }>(
            `/wishes/${w.id}/convert`, { method: 'POST', body: JSON.stringify({}) },
          )
          if (res?.excess_warnings?.length) {
            bulkDialog.excessWarnings.push({
              id: w.id,
              title: w.title || `Заявка №${w.id}`,
              text: excessWarningsSummary(res.excess_warnings),
            })
          }
        }
        ok++
      } catch (e: any) {
        // Причина — текст с сервера (detail), не общее «ошибка» (ПРАВИЛО фронта).
        const reason = e?.payload?.message || e?.message || 'неизвестная причина'
        bulkDialog.failures.push({ id: w.id, title: w.title || `Заявка №${w.id}`, reason })
      } finally {
        bulkDialog.progress++
      }
    }
    bulkDialog.done = ok
    bulkDialog.running = false
    selected.value = []
    await reloadActiveTab()
    // Окно не закрывается само, если есть что показать — ошибки или
    // превышение плана (доработка ревью 29.10.2026).
    if (!bulkDialog.failures.length && !bulkDialog.excessWarnings.length) {
      showSnack(`Готово: ${ok} из ${bulkDialog.total}`, 'success')
      bulkDialog.show = false
    } else {
      showSnack(`Выполнено ${ok} из ${bulkDialog.total} — подробности в окне`, 'warning')
    }
  }

  return {
    selected, clearSelection,
    bulkDialog, openBulkConfirm, closeBulkDialog, runBulkAction,
  }
}

export type UseWishBulkActionsReturn = ReturnType<typeof useWishBulkActions>
