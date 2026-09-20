// Материализация «ручного плана ФЭО» категории (planned_quantity/planned_amount
// прямо на FeoCategory, без отдельных записей FeoPlannedItem) в настоящую
// FeoPlannedItem — headless-логика, вынесенная отдельным файлом (Правило №5:
// useFeoPlannedItemAddDialog.ts уже 750+ строк, новая ответственность — новый
// файл). Единственное место, шлющее PUT очистки ручного плана категории и POST
// создания позиции ПО ЭТОЙ ПРИЧИНЕ (Правило №6):
//  - useFeoPlannedItemAddDialog.ts::clearCategoryManualPlan — диалоговый путь
//    («Завести плановую позицию», кнопка в FeoLevel5Panel.vue), с тостами и
//    ctx.loadFeo;
//  - usePlanToRequest.ts::materializeSelectedManualPlans — headless путь
//    (владелец, задача «выбрать категорию/смету целиком»): POST
//    /feo-planned-items/plan-to-wish/candidates умеет работать только с
//    реальными planned_item_id, ручного плана категории (синтетический id
//    = −category.id) не знает, поэтому перед отправкой такие позиции
//    материализуются здесь же — той же операцией.
import { apiFetch } from '@/api'
import { createPlannedItemRaw } from './useFeoPlannedItemAddDialog'
import type { FeoCategory } from './types'

// Снимок категории, достаточный для очистки/материализации ручного плана —
// подмножество полей FeoCategory (FeoNode их все содержит тоже — структурная
// типизация позволяет передавать сюда и узел дерева).
export type ManualPlanCategory = Pick<FeoCategory,
  'id' | 'subsidy_id' | 'name' | 'code' | 'appendix' | 'is_active' | 'budget'
  | 'feo_quantity' | 'feo_unit' | 'feo_amount' | 'description' | 'unit'
  | 'planned_quantity' | 'planned_amount'>

// Сырая очистка ручного плана категории (planned_quantity/planned_amount) —
// PUT является ПОЛНОЙ заменой (как и везде в проекте у /feo-categories/{id}),
// поэтому шлём все поля категории как есть, только planned_quantity/
// planned_amount — в null.
export async function clearCategoryManualPlanRaw(cat: ManualPlanCategory): Promise<void> {
  await apiFetch(`/feo-categories/${cat.id}`, {
    method: 'PUT',
    body: JSON.stringify({
      subsidy_id: cat.subsidy_id, name: cat.name, code: cat.code ?? null, appendix: cat.appendix ?? null,
      is_active: cat.is_active, budget: cat.budget ?? null,
      feo_quantity: cat.feo_quantity ?? null, feo_unit: cat.feo_unit ?? null, feo_amount: cat.feo_amount ?? null,
      description: cat.description ?? null, unit: cat.unit ?? null,
      planned_quantity: null, planned_amount: null,
    }),
  })
}

// Headless материализация: создать FeoPlannedItem с теми же кол-во/цена, что и
// в ручном плане категории (planned_quantity/planned_amount), затем очистить
// эти поля на самой категории — иначе они и дальше заслоняют только что
// созданную запись при расчёте плана листа (backend суммирует плановые
// позиции, только когда qty×amt категории не заданы, см. докстринг
// openConvertManualPlanToItem в useFeoPlannedItemAddDialog.ts — та же логика,
// без диалога/формы/тостов).
export async function materializeManualPlanAsItem(node: ManualPlanCategory): Promise<number> {
  const qty = node.planned_quantity != null ? Number(node.planned_quantity) : null
  const unitPrice = node.planned_amount != null ? Number(node.planned_amount) : null
  const amount = (qty != null && qty > 0 && unitPrice != null && unitPrice > 0) ? qty * unitPrice : null
  const created = await createPlannedItemRaw({
    feo_category_id: node.id,
    name: node.name,
    quantity: qty ?? 1,
    unit: node.unit || null,
    amount,
    unit_price: unitPrice,
    feo_quantity: null, feo_unit_price: null, feo_amount: null,
    is_active: true,
    payment_mode: 'one_time',
    planned_date: null, monthly_start_date: null, monthly_end_date: null, months_count: null, monthly_amount: null,
    // Ручной план ФЭО по определению без построчной ФЭО-разбивки — та же
    // семантика, что и в openConvertManualPlanToItem.
    is_feo_breakdown: false, is_internal_plan: true,
    allow_duplicate_name: true,
  })
  await clearCategoryManualPlanRaw(node)
  return created.id
}
