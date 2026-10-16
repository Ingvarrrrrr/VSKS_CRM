// Копирование/перенос закупок между субсидиями (владелец, сессия 16.10.2026).
// Один composable на оба окна — диалог одной закупки
// (PurchaseCopyToSubsidyDialog.vue, карточка закупки) и диалог переноса всей
// субсидии (SubsidyTransferPurchasesDialog.vue, список субсидий). ПРАВИЛО №6 —
// запрос/состояние строк/применение написаны один раз здесь, компоненты —
// только разметка и подсказки под конкретный сценарий.
//
// Контракт backend/app/routers/purchase_transfer.py (пишет параллельный
// исполнитель): POST /purchase-transfer/preview, POST /purchase-transfer/apply,
// GET /purchase-transfer/links/{purchase_id}.
import { computed, reactive, ref } from 'vue'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'

export interface PurchaseTransferBrief {
  id: number
  registry_number: string | null
  subject: string | null
  contractor_name: string | null
  contractor_inn: string | null
  employee_name: string | null
  purchase_method: string | null
  status: string | null
  amount: number | null
  feo_category_name: string | null
  copied_from_registry_number: string | null
}

export type PurchaseTransferRowState = 'same' | 'amount_only' | 'none'
export type PurchaseTransferAction = 'skip' | 'copy' | 'merge'

export interface PurchaseTransferRow {
  source: PurchaseTransferBrief
  state: PurchaseTransferRowState
  match: PurchaseTransferBrief | null
  default_action: PurchaseTransferAction | null
}

export interface PurchaseTransferPreview {
  source_subsidy: { id: number; name: string }
  target_subsidy: { id: number; name: string }
  rows: PurchaseTransferRow[]
  target_purchases: PurchaseTransferBrief[]
}

export interface PurchaseTransferApplyResult {
  copied: Array<{ source_id: number; source_registry_number: string; new_id: number; new_registry_number: string }>
  merged: Array<{ source_id: number; target_id: number; target_registry_number: string }>
  skipped: number
  /** Закупки, которые не скопировались (например, чек уже лежит в другой закупке). */
  warnings?: string[]
}

export interface PurchaseTransferLinkRef {
  id: number
  registry_number: string
  subsidy_id: number
  subsidy_name: string
}

export interface PurchaseTransferLinks {
  copied_from: PurchaseTransferLinkRef | null
  copies: PurchaseTransferLinkRef[]
}

// Состояние строки в UI: действие (null = пользователь ещё не выбрал — такая
// строка не уходит в /apply вовсе, см. apply() ниже) и выбранная вручную пара
// в целевой субсидии (для merge; по умолчанию — найденный match, если был).
interface RowUiState {
  action: PurchaseTransferAction | null
  targetPurchaseId: number | null
}

export function usePurchaseTransfer() {
  const loadingPreview = ref(false)
  const applying = ref(false)
  const preview = ref<PurchaseTransferPreview | null>(null)
  const previewError = ref('')
  const rowState = reactive<Record<number, RowUiState>>({})

  function rowOf(sourcePurchaseId: number): RowUiState {
    if (!rowState[sourcePurchaseId]) {
      rowState[sourcePurchaseId] = { action: null, targetPurchaseId: null }
    }
    return rowState[sourcePurchaseId]
  }

  function resetRowStateFromPreview(result: PurchaseTransferPreview) {
    for (const key of Object.keys(rowState)) delete rowState[Number(key)]
    for (const row of result.rows) {
      rowState[row.source.id] = {
        action: row.default_action,
        targetPurchaseId: row.match?.id ?? null,
      }
    }
  }

  async function loadPreview(
    sourceSubsidyId: number,
    targetSubsidyId: number,
    purchaseIds?: number[],
  ): Promise<PurchaseTransferPreview> {
    loadingPreview.value = true
    previewError.value = ''
    try {
      const body: Record<string, unknown> = {
        source_subsidy_id: sourceSubsidyId,
        target_subsidy_id: targetSubsidyId,
      }
      if (purchaseIds?.length) body.purchase_ids = purchaseIds
      const result = await apiFetch<PurchaseTransferPreview>('/purchase-transfer/preview', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      preview.value = result
      resetRowStateFromPreview(result)
      return result
    } catch (e: any) {
      previewError.value = describeApiError(e, { fallback: 'Не удалось сравнить закупки между субсидиями' })
      throw e
    } finally {
      loadingPreview.value = false
    }
  }

  function setAction(sourcePurchaseId: number, action: PurchaseTransferAction | null) {
    rowOf(sourcePurchaseId).action = action
  }

  function setTargetPurchase(sourcePurchaseId: number, targetPurchaseId: number | null) {
    rowOf(sourcePurchaseId).targetPurchaseId = targetPurchaseId
  }

  function actionOf(sourcePurchaseId: number): PurchaseTransferAction | null {
    return rowState[sourcePurchaseId]?.action ?? null
  }

  function targetPurchaseIdOf(sourcePurchaseId: number): number | null {
    return rowState[sourcePurchaseId]?.targetPurchaseId ?? null
  }

  // Поиск по парам в целевой субсидии — номер реестра, поставщик/сотрудник,
  // сумма. Используется v-autocomplete в обоих диалогах (ПРАВИЛО №6 — фильтр
  // один, не дублируется построчно).
  function searchTargetPurchases(query: string): PurchaseTransferBrief[] {
    const list = preview.value?.target_purchases ?? []
    const q = query.trim().toLowerCase()
    if (!q) return list
    return list.filter(b => {
      const amountStr = b.amount != null ? String(b.amount) : ''
      return (
        (b.registry_number || '').toLowerCase().includes(q) ||
        (b.contractor_name || '').toLowerCase().includes(q) ||
        (b.employee_name || '').toLowerCase().includes(q) ||
        amountStr.includes(q)
      )
    })
  }

  // Сводка «будет скопировано / дополнено / пропущено» — только по строкам
  // с явно выбранным действием (null — «не выбрано», в счётчик не входит, см.
  // pendingCount).
  const summary = computed(() => {
    let copy = 0, merge = 0, skip = 0
    for (const row of preview.value?.rows ?? []) {
      const action = rowState[row.source.id]?.action ?? null
      if (action === 'copy') copy++
      else if (action === 'merge') merge++
      else if (action === 'skip') skip++
    }
    return { copy, merge, skip }
  })

  const pendingCount = computed(() => {
    let n = 0
    for (const row of preview.value?.rows ?? []) {
      if ((rowState[row.source.id]?.action ?? null) === null) n++
    }
    return n
  })

  // Строки amount_only без выбранного действия — подсветить и не пускать в
  // /apply без явного решения.
  const amountOnlyUndecided = computed(() =>
    (preview.value?.rows ?? []).filter(
      row => row.state === 'amount_only' && (rowState[row.source.id]?.action ?? null) === null,
    ),
  )

  async function apply(
    targetSubsidyId: number,
    opts?: { onlySourceIds?: number[] },
  ): Promise<PurchaseTransferApplyResult> {
    if (!preview.value) throw new Error('usePurchaseTransfer.apply() вызван до loadPreview()')
    applying.value = true
    try {
      const rows = opts?.onlySourceIds
        ? preview.value.rows.filter(r => opts.onlySourceIds!.includes(r.source.id))
        : preview.value.rows
      const items = rows
        .map(row => {
          const st = rowState[row.source.id]
          const action = st?.action ?? null
          if (action === null) return null // не выбрано — строка не переносится и не считается пропущенной
          const item: Record<string, unknown> = { source_purchase_id: row.source.id, action }
          if (action === 'merge') {
            const targetId = st?.targetPurchaseId ?? row.match?.id ?? null
            if (!targetId) return null // merge без выбранной пары — тоже не отправляем
            item.target_purchase_id = targetId
          }
          return item
        })
        .filter((x): x is Record<string, unknown> => x !== null)
      return await apiFetch<PurchaseTransferApplyResult>('/purchase-transfer/apply', {
        method: 'POST',
        body: JSON.stringify({ target_subsidy_id: targetSubsidyId, items }),
      })
    } finally {
      applying.value = false
    }
  }

  const linksCache = reactive<Record<number, PurchaseTransferLinks>>({})
  const loadingLinks = ref(false)

  async function loadLinks(purchaseId: number): Promise<PurchaseTransferLinks> {
    loadingLinks.value = true
    try {
      const result = await apiFetch<PurchaseTransferLinks>(`/purchase-transfer/links/${purchaseId}`)
      linksCache[purchaseId] = result
      return result
    } finally {
      loadingLinks.value = false
    }
  }

  return {
    loadingPreview,
    applying,
    loadingLinks,
    preview,
    previewError,
    rowState,
    linksCache,
    summary,
    pendingCount,
    amountOnlyUndecided,
    loadPreview,
    apply,
    loadLinks,
    setAction,
    setTargetPurchase,
    actionOf,
    targetPurchaseIdOf,
    searchTargetPurchases,
  }
}
