// Единственный источник обхода поддерева категорий ФЭО по parent_id — раньше
// collectSubtreeIds жила только как локальная функция в SubsidiesView.vue и уже
// использовалась в четырёх местах (feoParentOptions, feoDeleteChildrenCount,
// drag&drop категорий). Вынесена сюда параметризованной по списку категорий,
// чтобы компоненты диалогов ФЭО (FeoCategoryDialog/FeoCategoryDeleteDialog) не
// заводили свою копию (Правило №6).
import type { FeoActualItem, FeoCategory, FeoLeftGroupInfo } from './types'

// Нормализация имени для сопоставления позиций «из заявок» с категориями/друг другом —
// используется useFeoLevel5.ts (fallbackAbsorbedByCategory/stagesWithDiff) и
// useFeoReqItems.ts (mergedReqByCat/allReqGroupsByCat) — единственный источник (Правило №6).
export function normName(s: string | null | undefined): string {
  return (s || '').trim().toLowerCase().replace(/\s+/g, ' ')
}

export function collectSubtreeIds(categories: FeoCategory[], nodeId: number): number[] {
  const ids = [nodeId]
  const find = (pid: number) => {
    for (const c of categories) {
      if (c.parent_id === pid) { ids.push(c.id); find(c.id) }
    }
  }
  find(nodeId)
  return ids
}

// ── Левая группа колонок панели «план vs факт»: ДВА состояния, не «план» ──────
// Правка владельца (2026-08-09): левая группа у строк ФАКТА — это НЕ план (план —
// только строка самой плановой позиции, помечена чипом «план»). До заключения
// договора показываем, как товар завели в заявке/ТЗ (stage 'purchase' в
// _build_item_stages, backend/app/routers/feo_planned_items.py — снимок
// PurchaseItem.item_name/quantity/unit_price/total_price); как только появилась
// договорная позиция — номенклатуру, количество и цену подрядчика (stage
// 'contract' — ContractItem). Источник — уже загруженный actual.stages, второй
// запрос/расчёт не делает. Фолбэк на actual.* — на случай отсутствия stages
// (защитный код: 'purchase' стадия в _build_item_stages есть всегда, но панель
// не должна показывать пустые клетки, если что-то разошлось).
//
// Функция ЧИСТАЯ (не зависит от состояния дерева) — используется и в самом дереве
// ФЭО (SubsidiesView.vue), и в PlannedItemAddDialog.vue (openCreatePlannedFromActual)
// — один источник, не две копии (Правило №6).
export function leftGroupInfo(actual: FeoActualItem): FeoLeftGroupInfo {
  const stages = actual.stages || []
  const contract = stages.find(s => s.key === 'contract')
  const purchase = stages.find(s => s.key === 'purchase')
  const chosen = contract || purchase
  if (chosen) {
    return {
      name: chosen.name || '',
      quantity: chosen.quantity,
      unit: chosen.unit,
      unitPrice: chosen.unit_price,
      total: chosen.total,
      isContract: !!contract,
    }
  }
  return {
    name: actual.item_name,
    quantity: actual.quantity,
    unit: actual.unit,
    unitPrice: actual.unit_price,
    total: actual.total_price,
    isContract: false,
  }
}
