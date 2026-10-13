// feoPlanPending — единственное место, вычисляющее «занято сейчас в этой форме»
// (pendingFor) и накладывающее его на серверные consumed/residual одной строки
// плановой позиции (ПРАВИЛО №6: второй формулы для этого не заводим). Вынесено
// из useFeoPlannedRows.ts, чтобы формула была проверяема юнит-тестом без всего
// композабла (props/emit/showSnack) и чтобы у «шапочных» форм с ОДНОЙ позицией
// (ReqItemEditDialog.vue — диалог «Редактировать позицию») и у форм со МНОГИМИ
// позициями (useItemsFeo.ts::pendingByPlannedItem для ItemsTableFlat/Stages,
// PurchaseItemsEditor.vue) была ровно одна точка расчёта.
//
// Дефект (владелец, прод, 13.10.2026): в диалоге «Редактировать позицию»
// включённая плановая позиция показывала «план 352 400 · выбрано 0 · остаток
// 352 400» вместо «выбрано 317 400 (сумма текущей строки) · остаток 35 000».
// Причина — row.consumed/row.residual с сервера считаются с
// exclude_purchase_id (своя закупка уже исключена из чужих consumers, это
// верно и не трогается), но сумму САМОЙ редактируемой строки, когда она
// привязана к этой плановой позиции, никто не прибавлял обратно: у форм со
// списком строк это делает pendingByPlannedItem (карта по ВСЕЙ форме), а у
// однопозиционного диалога такой карты просто не было — проп не передавался.
import type { FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'

/** «Занято сейчас в этой форме» сверх серверных чисел для ОДНОЙ строки —
 *  только kind==='planned_item' имеет свой id в пространстве FeoPlannedItem
 *  (у plan_position/feo_article id это id FeoCategory, своей плановой позиции
 *  нет, pendingFor для них всегда 0). */
export function pendingForRow(
  row: Pick<FeoPlanPosition, 'kind' | 'id'>,
  pendingByPlannedItem: Record<number, number> | null | undefined,
): number {
  if (row.kind !== 'planned_item') return 0
  return pendingByPlannedItem?.[row.id] || 0
}

/** «Выбрано» строки — серверное consumed + то, что занято этой формой прямо сейчас. */
export function consumedForRow(
  row: Pick<FeoPlanPosition, 'kind' | 'id' | 'consumed'>,
  pendingByPlannedItem: Record<number, number> | null | undefined,
): number {
  return row.consumed + pendingForRow(row, pendingByPlannedItem)
}

/** «Остаток» строки — серверный residual минус то же самое занятое формой число
 *  (row.residual = planned_amount − consumed уже посчитан бэкендом без клампинга,
 *  см. backend/app/routers/feo_categories.py::spendable_remaining — здесь только
 *  вычитаем pendingFor отдельно, не пересчитываем через planned_amount). */
export function residualForRow(
  row: Pick<FeoPlanPosition, 'kind' | 'id' | 'residual'>,
  pendingByPlannedItem: Record<number, number> | null | undefined,
): number {
  return row.residual - pendingForRow(row, pendingByPlannedItem)
}
