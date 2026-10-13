// Состояние и логика диалога «Редактировать часть позиции» (владелец,
// 13.10.2026, «План закупок» → «План vs факт» → строка «Как запланировано»,
// kind==='planned_only' в FeoLevel5Panel.vue). Module-level singleton — тот
// же приём, что и у usePlannedItems.ts/useFeoPlannedItemEditDialog.ts
// (открывает FeoLevel5Panel.vue, диалог смонтирован ОДИН раз в
// FeoTreeTable.vue, по образцу FeoRowDrillDialog.vue — Правило №6/№5, второй
// копии диалога/состояния не заводим).
//
// Эндпоинт — PATCH /feo-planned-items/{id}/parts/{key}
// (app/routers/feo_planned_items.py::update_planned_item_part, тело —
// app/services/feo_planned_item_parts_edit.py): права и гейт корректировки
// утверждённой субсидии те же, что у PUT /feo-planned-items/{id} — отдельного
// адаптера feoWriteAdapter.ts здесь не заводим (часть — не весь план узла,
// revision-режим для неё владелец не просил; на утверждённой субсидии в
// revision-режиме сервер вернёт 409 "subsidy_revision_required", снэкбар
// покажет текст как есть).
import { ref, watch } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { withPreservedScroll } from './usePreserveScroll'
import type { SubsidyDetailContext } from './useSubsidyDetail'
import type { FeoPlannedItem } from './types'

type Part = NonNullable<FeoPlannedItem['parts']>[number]

const partEditDialog = ref({
  show: false,
  saving: false,
  error: '' as string,
  itemId: 0,
  categoryId: 0,
  partKey: '',
  itemName: '' as string,
  // Кол-во/цена заданы оба → сумма считается сервером (кол-во × цена, тот же
  // принцип, что и у editAmountIsComputed в useFeoPlannedItemEditDialog.ts);
  // можно ввести только сумму — задача владельца, п. «можно ввести только
  // сумму».
  quantity: '' as string | number,
  unit: '' as string,
  unitPrice: '' as string | number,
  amount: '' as string | number,
})

// Живой пересчёт суммы в поле (кол-во × цена), ровно та же формула, что
// применяет сервер при сохранении (update_planned_item_part) — тот же приём,
// что и recalcEditAmountFromUnitPrice в useFeoPlannedItemEditDialog.ts
// (Правило №6, формула словами одна и та же в обоих местах, хотя написана
// дважды — вычисление тривиально и не стоит общего модуля).
watch([() => partEditDialog.value.quantity, () => partEditDialog.value.unitPrice], () => {
  const d = partEditDialog.value
  if (d.quantity === '' || d.quantity == null || d.unitPrice === '' || d.unitPrice == null) return
  const qty = Number(d.quantity)
  const price = Number(d.unitPrice)
  if (!Number.isFinite(qty) || !Number.isFinite(price)) return
  d.amount = Math.round(qty * price * 100) / 100
})

type PartEditCtx = Pick<SubsidyDetailContext, 'refreshComparison' | 'refreshReqData' | 'feoTableArea'>

export function useFeoPlannedItemPartEditDialog(ctx?: PartEditCtx) {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success') {
    toast.addToast(text, color)
  }

  function openEditPlannedItemPart(itemId: number, categoryId: number, itemName: string, part: Part) {
    partEditDialog.value.itemId = itemId
    partEditDialog.value.categoryId = categoryId
    partEditDialog.value.itemName = itemName
    partEditDialog.value.partKey = part.key
    partEditDialog.value.quantity = part.qty != null ? parseFloat(String(part.qty)) : ''
    partEditDialog.value.unit = part.unit || ''
    partEditDialog.value.unitPrice = part.unit_price != null ? parseFloat(String(part.unit_price)) : ''
    partEditDialog.value.amount = part.amount != null ? parseFloat(String(part.amount)) : ''
    partEditDialog.value.error = ''
    partEditDialog.value.show = true
  }

  async function saveEditPlannedItemPart() {
    if (!ctx) return
    const d = partEditDialog.value
    d.error = ''
    d.saving = true
    try {
      const body: Record<string, unknown> = {
        quantity: d.quantity === '' ? null : Number(d.quantity),
        unit: d.unit || null,
        unit_price: d.unitPrice === '' ? null : Number(d.unitPrice),
        amount: d.amount === '' ? null : Number(d.amount),
      }
      await apiFetch<FeoPlannedItem>(
        `/feo-planned-items/${d.itemId}/parts/${encodeURIComponent(d.partKey)}`,
        { method: 'PATCH', body: JSON.stringify(body) },
      )
      d.show = false
      showSnack('Часть позиции сохранена')
      // withPreservedScroll (usePreserveScroll.ts, Правило №6) — та же защита
      // от «подброса» страницы наверх, что и у остальных правок панели
      // «План vs факт» (см. saveEditPlannedItem, useFeoPlannedItemEditDialog.ts).
      await withPreservedScroll(ctx.feoTableArea.value, () =>
        Promise.all([ctx.refreshComparison(d.categoryId), ctx.refreshReqData()]))
    } catch (e: any) {
      // Ошибка «заполните/проверьте X» — у этого маленького диалога ровно
      // одно денежное поле «Сумма», ошибка 409 превышения плана показывается
      // ТЕКСТОМ прямо под ним же (см. FeoPlannedItemPartEditDialog.vue,
      // partEditDialog.error + PointerArrow — «ошибка → стрелка к полю»,
      // см. Lessons.md), а не только тостом-снэкбаром.
      const msg = e?.payload?.message || e?.detail || e?.message || 'Ошибка сохранения'
      d.error = typeof msg === 'string' ? msg : 'Ошибка сохранения'
      showSnack(d.error, 'error')
    } finally {
      d.saving = false
    }
  }

  return { partEditDialog, openEditPlannedItemPart, saveEditPlannedItemPart }
}
