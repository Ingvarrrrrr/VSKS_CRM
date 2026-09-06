// Состояние и логика диалога «Редактировать план категории» (ручной план ФЭО
// на самой категории, CategoryPlanEditDialog.vue) — один из четырёх кусков
// панели «План vs факт» ФЭО, вынесенных из SubsidiesView.vue (см.
// usePlannedItems.ts — баррель, объединяющий этот файл с остальными тремя;
// разнесены по файлам, чтобы не собирать один composable на 700+ строк —
// Правило №5, модульность кода). Module-level singleton state.
//
// Жалоба владельца (2026-08-11): «Great Wall POER могу редактировать, а Микроавтобус
// плановый — не могу». Причина — у синтетической строки «ручной план ФЭО» в панели
// (displayPlannedRowsFor, planned.isManual, id = -node.id) карандаш раньше отсутствовал,
// был только «Завести плановую позицию» (это про другое — заводит именованную
// FeoPlannedItem, план листа сам не трогает). Этот диалог — лёгкий редактор ровно тех
// полей, что и формируют синтетическую строку: planned_quantity/planned_amount/unit
// НА САМОЙ КАТЕГОРИИ (PUT /feo-categories/{id}), а НЕ полный feoEditForm (там полей
// больше, чем нужно для этой задачи — легче промахнуться не в то поле).
// ⚠️ Семантика (см. displayPlannedRowsFor в SubsidiesView.vue): FeoCategory.planned_amount —
// ЦЕНА ЗА ЕДИНИЦУ, а не сумма (в отличие от FeoPlannedItem.amount, которое сумма). Подписи
// полей ниже — «Плановое количество» / «Плановая цена за единицу» — и расчётная сумма
// рядом, чтобы это не перепуталось снова (уже дважды ломало боевые числа).
import { computed, ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import type { SubsidyDetailContext } from './useSubsidyDetail'
import type { FeoNode } from './types'

export const CATEGORY_UNIT_OPTIONS = ['шт.', 'усл.', 'компл.', 'уп.', 'м.', 'кг.', 'л.', 'п.м.', 'кв.м.', 'час.', 'мес.', 'год']

// «Ед. изм.» — число (напр. 5500000 вместо «шт») — след старого импорта со сдвигом
// колонок (на проде таких 35 категорий). Распознаём как «подозрительно», если строка
// целиком — число (с необязательным десятичным разделителем), но не молчим и не правим
// сами — только подсвечиваем и предлагаем заменить (см. isCategoryUnitSuspicious ниже).
export function isNumericLikeUnit(u: string | null | undefined): boolean {
  const s = String(u ?? '').trim()
  if (!s) return false
  return /^-?\d+([.,]\d+)?$/.test(s.replace(/\s+/g, ''))
}

const editCategoryPlanDialog = ref({
  show: false, saving: false,
  nodeId: 0, categoryName: '',
  quantity: '' as string | number,
  unitPrice: '' as string | number,
  unit: '' as string,
})

const isCategoryUnitSuspicious = computed(() => isNumericLikeUnit(editCategoryPlanDialog.value.unit))

const editCategoryPlanSum = computed<number | null>(() => {
  const q = editCategoryPlanDialog.value.quantity !== '' ? Number(editCategoryPlanDialog.value.quantity) : null
  const p = editCategoryPlanDialog.value.unitPrice !== '' ? Number(editCategoryPlanDialog.value.unitPrice) : null
  if (q != null && p != null && !isNaN(q) && !isNaN(p) && q > 0 && p > 0) return q * p
  return null
})

type CategoryPlanCtx = Pick<SubsidyDetailContext, 'selectedId' | 'feoCategories' | 'loadFeo'>

export function useFeoCategoryPlanDialog(ctx?: CategoryPlanCtx) {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success') {
    toast.addToast(text, color)
  }

  function openEditCategoryPlan(node: FeoNode) {
    editCategoryPlanDialog.value.nodeId = node.id
    editCategoryPlanDialog.value.categoryName = node.name
    editCategoryPlanDialog.value.quantity = node.planned_quantity != null ? parseFloat(String(node.planned_quantity)) : ''
    editCategoryPlanDialog.value.unitPrice = node.planned_amount != null ? parseFloat(String(node.planned_amount)) : ''
    editCategoryPlanDialog.value.unit = node.unit || ''
    editCategoryPlanDialog.value.show = true
  }

  async function saveEditCategoryPlan() {
    if (!ctx) return
    const nodeId = editCategoryPlanDialog.value.nodeId
    const cat = ctx.feoCategories.value.find(c => c.id === nodeId)
    if (!nodeId || !cat) { editCategoryPlanDialog.value.show = false; return }
    editCategoryPlanDialog.value.saving = true
    try {
      const qtyRaw = String(editCategoryPlanDialog.value.quantity ?? '').trim()
      const amtRaw = String(editCategoryPlanDialog.value.unitPrice ?? '').trim()
      const qty = qtyRaw === '' ? null : Number(qtyRaw)
      const unitPrice = amtRaw === '' ? null : Number(amtRaw)
      const unit = editCategoryPlanDialog.value.unit.trim() || null
      const res = await apiFetch<any>(`/feo-categories/${nodeId}`, {
        method: 'PUT',
        body: JSON.stringify({
          subsidy_id: cat.subsidy_id, name: cat.name, code: cat.code ?? null, appendix: cat.appendix ?? null,
          is_active: cat.is_active, budget: cat.budget ?? null,
          feo_quantity: cat.feo_quantity ?? null, feo_unit: cat.feo_unit ?? null, feo_amount: cat.feo_amount ?? null,
          description: cat.description ?? null,
          planned_quantity: qty, planned_amount: unitPrice, unit,
        }),
      })
      // Оптимистично патчим локально (строка панели — displayPlannedRowsFor читает node
      // напрямую из feoCategories), НО «Плановая сумма» в шапке (feoPlannedDisplayFor)
      // читает готовое число с бэкенда (planTreeByCat, см. feoPlannedDisplayRaw) — этот
      // локальный патч его не трогает. startInlineAmt/startInlineQty останавливаются
      // здесь и из-за этого шапка у них не обновляется без reload — тот же полный
      // updateFeoCategory() (диалог «Редактировать») дальше зовёт loadFeo(), и здесь
      // тоже зовём — иначе не выполняется приёмка «шапка обновилась без перезагрузки».
      cat.planned_quantity = qty
      cat.planned_amount = unitPrice
      cat.unit = unit
      ctx.feoCategories.value = [...ctx.feoCategories.value]
      editCategoryPlanDialog.value.show = false
      showSnack('План категории сохранён')
      if (res?.warning) showSnack(res.warning, 'warning')
      if (ctx.selectedId.value) await ctx.loadFeo(ctx.selectedId.value)
    } catch (e: any) {
      showSnack(e.detail || 'Ошибка сохранения', 'error')
    } finally {
      editCategoryPlanDialog.value.saving = false
    }
  }

  return {
    editCategoryPlanDialog, isCategoryUnitSuspicious, editCategoryPlanSum, CATEGORY_UNIT_OPTIONS,
    openEditCategoryPlan, saveEditCategoryPlan,
  }
}
