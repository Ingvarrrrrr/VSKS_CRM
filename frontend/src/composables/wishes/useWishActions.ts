// useWishActions.ts — действия над одной заявкой, вызываемые как из строк таблиц
// (My/Incoming/All), так и из карточки заявки: отправка/удаление/одобрение/отклонение,
// распределение по закупкам (kanban), остановка, копирование, «оформить как авансовый
// отчёт», создание закупки (convert), скачивание Excel/служебной записки.
// Дословный перенос из WishesView.vue при разбиении файла на компоненты/композаблы.
import { ref } from 'vue'
import { numOrNull } from '@/utils/numberFormat'
import type { WishesContext } from './useWishesContext'
import type { Wish } from './wishTypes'
import type { UseWishFormReturn } from './useWishForm'

export function useWishActions(deps: {
  ctx: WishesContext
  apiFetch: typeof import('@/api').apiFetch
  form: UseWishFormReturn
  flushFeoAutosave: () => Promise<boolean>
  reloadActiveTab: () => Promise<void>
  loadAllWishes: () => Promise<void>
  // Полностью оркестрованное открытие карточки (форма + участники + согласующие +
  // снимки автосейва ФЭО) — используется copyWish, чтобы открыть копию заявки ТАК ЖЕ,
  // как обычный клик по строке (WishFormDialog.vue::openEdit), а не только форму.
  openEditDialog: (wish: Wish) => Promise<void>
}) {
  const { ctx, apiFetch, form, flushFeoAutosave, reloadActiveTab, loadAllWishes, openEditDialog } = deps
  const { showSnack, showExcessWarnings, showPurchaseSync } = ctx
  const {
    editingWishId, editingWish, wishDialog, isWishEditable,
    wishPayloadSnapshotJson, wishFormSavedSnapshot, saveWish,
    handleMissingDatesError, handleMissingFeoCategoryError,
  } = form

  // Submit
  const submittingId = ref<number | null>(null)
  async function submitWish(wish: Wish) {
    submittingId.value = wish.id
    try {
      await apiFetch(`/wishes/${wish.id}/submit`, { method: 'POST' })
      showSnack('Заявка отправлена')
      await reloadActiveTab()
    } catch (e: any) {
      const handled = await handleMissingDatesError(e, wish)
      if (!handled) {
        showSnack(`Ошибка при отправке: ${e?.payload?.message || e?.message || 'неизвестная ошибка'}`, 'error')
      }
    } finally {
      submittingId.value = null
    }
  }

  // Delete
  const deletingId = ref<number | null>(null)
  async function deleteWish(wish: Wish) {
    deletingId.value = wish.id
    try {
      await apiFetch(`/wishes/${wish.id}`, { method: 'DELETE' })
      showSnack('Заявка удалена')
      await reloadActiveTab()
    } catch (e: any) {
      showSnack(`Ошибка при удалении: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
    } finally {
      deletingId.value = null
    }
  }

  // Approve
  const approvingId = ref<number | null>(null)
  async function approveWish(wish: Wish) {
    if (wishDialog.value && editingWishId.value === wish.id) {
      const flushedFeo = await flushFeoAutosave()
      if (!flushedFeo) return
      if (isWishEditable.value) {
        const currentSnapshot = wishPayloadSnapshotJson()
        if (currentSnapshot && currentSnapshot !== wishFormSavedSnapshot.value) {
          const saved = await saveWish(false)
          if (!saved) return
        }
      }
    }

    approvingId.value = wish.id
    try {
      const res = await apiFetch<{
        status?: string
        convert_warning?: string | null
        excess_warnings?: import('./wishTypes').ExcessWarning[]
        purchases?: { id: number; registry_number?: string | null }[]
        purchase_sync?: import('./wishTypes').PurchaseSync | null
      }>(`/wishes/${wish.id}/approve`, { method: 'POST' })
      const _convertedPurchase = res?.status === 'converted' ? (res.purchases || [])[0] : null
      if (res?.convert_warning) showSnack(res.convert_warning, 'warning')
      else if (_convertedPurchase)
        showSnack(`Заявка одобрена и перенесена в закупку ${_convertedPurchase.registry_number || `№${_convertedPurchase.id}`}`)
      else showSnack('Заявка одобрена')
      showExcessWarnings(res?.excess_warnings, 'Заявка одобрена, закупка создана.')
      showPurchaseSync(res?.purchase_sync)
      form.wishConvertError.value = null
      await reloadActiveTab()
    } catch (e: any) {
      const handled = (await handleMissingDatesError(e, wish)) || (await handleMissingFeoCategoryError(e, wish))
      if (!handled) {
        showSnack(`Ошибка при одобрении: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
      }
    } finally {
      approvingId.value = null
    }
  }

  // ── Reject dialog ──
  const rejectDialog = ref(false)
  const rejectingWish = ref(false)
  const rejectionReason = ref('')
  const rejectingWishItem = ref<Wish | null>(null)
  function openRejectDialog(wish: Wish) {
    rejectingWishItem.value = wish
    rejectionReason.value = ''
    rejectDialog.value = true
  }
  async function rejectWish() {
    if (!rejectionReason.value.trim() || !rejectingWishItem.value) return
    if (editingWishId.value === rejectingWishItem.value.id) {
      const flushedFeo = await flushFeoAutosave()
      if (!flushedFeo) return
    }
    rejectingWish.value = true
    try {
      await apiFetch(`/wishes/${rejectingWishItem.value.id}/reject`, {
        method: 'POST',
        body: JSON.stringify({ rejection_reason: rejectionReason.value }),
      })
      showSnack('Заявка отклонена')
      rejectDialog.value = false
      await reloadActiveTab()
    } catch (e: any) {
      showSnack(`Ошибка при отклонении: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
    } finally {
      rejectingWish.value = false
    }
  }

  // ── Kanban distribution (Phase 13) ─────────────────────────────────────
  const kanbanDialog = ref(false)
  const kanbanWish = ref<Wish | null>(null)
  const kanbanItems = ref<any[]>([])
  async function openKanbanDialog(wish: Wish) {
    if (editingWishId.value === wish.id) {
      const flushedFeo = await flushFeoAutosave()
      if (!flushedFeo) return
    }
    kanbanWish.value = wish
    kanbanItems.value = []
    kanbanDialog.value = true
    try {
      const full = await apiFetch<Wish & { items?: any[] }>(`/wishes/${wish.id}`)
      const items: any[] = Array.isArray(full.items) ? full.items : []

      let products: any[] = []
      try { products = await apiFetch<any[]>('/products/?limit=10000') } catch {}
      const byId = new Map<number, any>(products.map((p: any) => [p.id, p]))
      const byName = new Map<string, any>(
        products.map((p: any) => [(p.name || '').trim().toLowerCase(), p])
      )

      kanbanItems.value = items.map((it: any) => {
        let prod = it.product_id ? byId.get(it.product_id) : null
        if (!prod && it.item_name) {
          prod = byName.get(it.item_name.trim().toLowerCase()) || null
        }
        return {
          ...it,
          product_id: it.product_id ?? prod?.id ?? null,
          _photo_url: (prod?.has_photo ? `/api/products/${prod.id}/photo` : (prod?.photo_url ?? prod?.photo_link)) ?? it._photo_url ?? null,
          _product_category: prod?.category || it._product_category || '',
        }
      })
    } catch (e: any) {
      showSnack(e?.message || 'Ошибка загрузки заявки', 'error')
    }
  }
  async function onKanbanApproved(result: { purchase_ids: number[]; count: number }) {
    showSnack(`Одобрено. Создано закупок: ${result.count}`)
    kanbanDialog.value = false
    await reloadActiveTab()
  }

  // ── Service note / Excel download (Phase 13 / D-07) ────────────────────
  const downloadingServiceNoteId = ref<number | null>(null)
  const downloadingExcelId = ref<number | null>(null)
  async function downloadServiceNote(wish: Wish) {
    downloadingServiceNoteId.value = wish.id
    try {
      const token = localStorage.getItem('auth_token') || ''
      const resp = await fetch(`/api/wishes/${wish.id}/documents/service_note`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`)
      }
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const _sanitized = (wish.title || '').replace(/[\\/:*?"<>|\r\n]+/g, '').replace(/\s+/g, '_').slice(0, 50)
      a.download = _sanitized ? `Служебная_записка_${_sanitized}.docx` : `Служебная_записка_заявка_${wish.id}.docx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      showSnack(e?.message || 'Ошибка скачивания служебной записки', 'error')
    } finally {
      downloadingServiceNoteId.value = null
    }
  }
  async function downloadWishExcel(wish: Wish, withPhotos: boolean = true) {
    downloadingExcelId.value = wish.id
    try {
      const token = localStorage.getItem('auth_token') || ''
      const resp = await fetch(`/api/wishes/${wish.id}/export.xlsx?with_photos=${withPhotos}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const _wishTitle = (wish.title || '').replace(/[\\/:*?"<>|\r\n]+/g, '').replace(/\s+/g, '_').slice(0, 50)
      const _suffix = withPhotos ? '' : '_без_фото'
      a.download = _wishTitle ? `Заявка_${_wishTitle}_${wish.id}${_suffix}.xlsx` : `Заявка_${wish.id}${_suffix}.xlsx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      showSnack(e?.message || 'Ошибка скачивания Excel', 'error')
    } finally {
      downloadingExcelId.value = null
    }
  }

  // ── Остановка заявки (владелец, 2026-08-13): «Останавливать могут все» ──
  const stopDialog = ref(false)
  const stoppingWish = ref(false)
  const stopReason = ref('')
  const stoppingWishItem = ref<Wish | null>(null)
  function openStopDialog(wish: Wish) {
    stoppingWishItem.value = wish
    stopReason.value = ''
    stopDialog.value = true
  }
  async function confirmStopWish() {
    if (!stoppingWishItem.value) return
    stoppingWish.value = true
    try {
      const body: Record<string, string> = {}
      if (stopReason.value.trim()) body.reason = stopReason.value.trim()
      const updated = await apiFetch<Wish>(`/wishes/${stoppingWishItem.value.id}/stop`, {
        method: 'POST',
        body: JSON.stringify(body),
      })
      showSnack(
        updated?.stopped_partial ? 'Заявка остановлена частично' : 'Заявка остановлена',
        updated?.stopped_partial ? 'warning' : 'success',
      )
      stopDialog.value = false
      if (editingWish.value && editingWish.value.id === stoppingWishItem.value.id) {
        editingWish.value = { ...editingWish.value, ...updated }
      }
      await reloadActiveTab()
    } catch (e: any) {
      showSnack(`Не удалось остановить заявку: ${e?.payload?.message || e?.message || 'неизвестная ошибка'}`, 'error')
    } finally {
      stoppingWish.value = false
    }
  }

  // ── Копирование заявки ──
  const copyingId = ref<number | null>(null)
  async function copyWish(wish: Wish) {
    copyingId.value = wish.id
    try {
      const created = await apiFetch<Wish>(`/wishes/${wish.id}/copy`, { method: 'POST' })
      showSnack('Заявка скопирована — дозаполните недостающее')
      wishDialog.value = false
      await reloadActiveTab()
      if (created?.id) await openEditDialog(created)
    } catch (e: any) {
      showSnack(`Не удалось скопировать заявку: ${e?.payload?.message || e?.message || 'неизвестная ошибка'}`, 'error')
    } finally {
      copyingId.value = null
    }
  }

  // ── «Оформить как авансовый отчёт» ──
  const convertToAdvanceDialog = ref(false)
  const convertingToAdvanceWish = ref<Wish | null>(null)
  const convertingToAdvanceLoading = ref(false)
  function openConvertToAdvanceDialog(wish: Wish) {
    convertingToAdvanceWish.value = wish
    convertToAdvanceDialog.value = true
  }
  async function confirmConvertToAdvance() {
    if (!convertingToAdvanceWish.value) return
    convertingToAdvanceLoading.value = true
    try {
      const result = await apiFetch<{
        wish_id: number
        purchase_id: number
        registry_number?: string | null
        purchase_method?: string
        status: string
        cancelled_purchases?: string[]
      }>(`/wishes/${convertingToAdvanceWish.value.id}/convert-to-advance-report`, { method: 'POST' })
      convertToAdvanceDialog.value = false
      wishDialog.value = false
      const cancelledNote = result.cancelled_purchases?.length
        ? ` Старая закупка ${result.cancelled_purchases.join(', ')} отменена.`
        : ''
      showSnack(`Авансовый отчёт ${result.registry_number || `№${result.purchase_id}`} создан.${cancelledNote}`, 'success')
      await reloadActiveTab()
      ctx.router.push(`/advance-reports/${result.purchase_id}/edit`)
    } catch (e: any) {
      showSnack(
        `Не удалось оформить авансовый отчёт: ${e?.payload?.message || e?.message || 'неизвестная ошибка'}`,
        'error',
      )
    } finally {
      convertingToAdvanceLoading.value = false
    }
  }

  // ── Convert dialog (создать закупку из заявки) ──
  const convertDialog = ref(false)
  const convertingWishLoading = ref(false)
  const convertingWish = ref<Wish | null>(null)
  const convertForm = ref({
    approved_quantity: null as number | null,
    approved_price: null as number | null,
    subsidy_id: null as number | null,
  })
  // Владелец: при наличии позиций сумма закупки считается ИЗ позиций (как и
  // везде в проекте, ПРАВИЛО №6 — один источник истины) — поле «Утверждённая
  // цена» в этом случае скрывается в пользу подсказки, см. convertingWishItemsCount/
  // convertingWishItemsSum ниже и WishActionDialogs.vue.
  const convertingWishItemsCount = ref(0)
  const convertingWishItemsSum = ref(0)
  async function openConvertDialog(wish: Wish) {
    convertingWish.value = wish
    let items: any[] = Array.isArray((wish as any).items) ? (wish as any).items : []
    if (items.length === 0) {
      try {
        const fresh = await apiFetch<any>(`/wishes/${wish.id}`)
        if (Array.isArray(fresh?.items)) items = fresh.items
      } catch {}
    }
    const sumQty = items.reduce((s, i) => s + Number(i.quantity || 0), 0)
    const sumPrice = items.reduce((s, i) => s + Number(i.total_price || 0), 0)
    convertingWishItemsCount.value = items.length
    convertingWishItemsSum.value = sumPrice
    convertForm.value = {
      approved_quantity: sumQty > 0 ? sumQty : (wish.quantity != null ? Number(wish.quantity) : null),
      approved_price: sumPrice > 0 ? sumPrice : (wish.total_amount ?? (wish.estimated_price != null ? Number(wish.estimated_price) : null)),
      subsidy_id: wish.subsidy_id ?? null,
    }
    convertDialog.value = true
  }
  async function convertWish() {
    if (!convertingWish.value) return
    convertingWishLoading.value = true
    try {
      const body: any = {}
      const approvedQty = numOrNull(convertForm.value.approved_quantity)
      const approvedPrice = numOrNull(convertForm.value.approved_price)
      if (approvedQty != null) body.approved_quantity = approvedQty
      // Владелец: при наличии позиций сумма закупки = сумма позиций — поле
      // «Утверждённая цена» скрыто в UI (см. WishActionDialogs.vue), а сюда
      // approved_price не отправляем вовсе, чтобы не расходиться с бэкендом
      // (он тоже игнорирует это поле при непустых items).
      if (convertingWishItemsCount.value === 0 && approvedPrice != null) body.approved_price = approvedPrice
      if (convertForm.value.subsidy_id != null) body.subsidy_id = convertForm.value.subsidy_id
      const result = await apiFetch<{
        wish_id: number
        purchase_id: number
        status: string
        registry_number?: string | null
        already_converted?: boolean
        excess_warnings?: import('./wishTypes').ExcessWarning[]
        purchase_sync?: import('./wishTypes').PurchaseSync | null
      }>(
        `/wishes/${convertingWish.value.id}/convert`,
        { method: 'POST', body: JSON.stringify(body) }
      )
      if (result.already_converted) {
        showSnack(`Закупка уже создана: ${result.registry_number || `№${result.purchase_id}`}`)
      } else {
        showSnack('Закупка создана')
        showExcessWarnings(result.excess_warnings, 'Закупка создана.')
      }
      showPurchaseSync(result.purchase_sync)
      convertDialog.value = false
      await loadAllWishes()
      ctx.router.push(`/orders/${result.purchase_id}/edit`)
    } catch (e: any) {
      const handled = convertingWish.value
        ? await handleMissingFeoCategoryError(e, convertingWish.value)
        : false
      if (handled) {
        convertDialog.value = false
      } else {
        showSnack(`Ошибка при создании закупки: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
      }
    } finally {
      convertingWishLoading.value = false
    }
  }

  return {
    submittingId, submitWish,
    deletingId, deleteWish,
    approvingId, approveWish,
    rejectDialog, rejectingWish, rejectionReason, rejectingWishItem, openRejectDialog, rejectWish,
    kanbanDialog, kanbanWish, kanbanItems, openKanbanDialog, onKanbanApproved,
    downloadingServiceNoteId, downloadingExcelId, downloadServiceNote, downloadWishExcel,
    stopDialog, stoppingWish, stopReason, stoppingWishItem, openStopDialog, confirmStopWish,
    copyingId, copyWish,
    convertToAdvanceDialog, convertingToAdvanceWish, convertingToAdvanceLoading,
    openConvertToAdvanceDialog, confirmConvertToAdvance,
    convertDialog, convertingWishLoading, convertingWish, convertForm,
    convertingWishItemsCount, convertingWishItemsSum, openConvertDialog, convertWish,
  }
}

export type UseWishActionsReturn = ReturnType<typeof useWishActions>
