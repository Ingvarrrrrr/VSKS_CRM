// Состояние и логика диалога «Сопоставить с плановой позицией» (PlannedItemMapDialog.vue) —
// один из четырёх кусков панели «План vs факт» ФЭО, вынесенных из SubsidiesView.vue
// (см. usePlannedItems.ts — тонкий баррель, объединяющий этот файл с
// useFeoPlannedItemAddDialog.ts/useFeoPlannedItemEditDialog.ts/useFeoCategoryPlanDialog.ts;
// разнесены по файлам, т.к. один usePlannedItems.ts на все четыре диалога
// разрастался за 700 строк — Правило №5, модульность кода). Module-level
// singleton state, как остальные composables/subsidies/use*.ts в этом проекте.
import { ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import type { SubsidyDetailContext } from './useSubsidyDetail'
import type { FeoActualItem } from './types'

const showMapDialog = ref(false)
const mapTarget = ref<FeoActualItem | null>(null)
const mapCategoryId = ref<number | null>(null)
const mappingInProgress = ref(false)

type MapDialogCtx = Pick<SubsidyDetailContext, 'comparisonData' | 'ensureComparison' | 'refreshReqData'>

export function useFeoPlannedItemMap(ctx?: MapDialogCtx) {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success') {
    toast.addToast(text, color)
  }

  function openMapDialog(item: FeoActualItem, categoryId: number) {
    mapTarget.value = item
    mapCategoryId.value = categoryId
    showMapDialog.value = true
  }

  async function applyMapping(plannedItemId: number | null) {
    if (!mapTarget.value || !ctx) return
    mappingInProgress.value = true
    try {
      // Баг найден при приёмке (2026-08-11): при снятии сопоставления (plannedItemId=null)
      // `planned_item_id=${plannedItemId ?? ''}` слал ПУСТУЮ строку вместо отсутствия параметра —
      // бэкенд (Optional[int] = None) валит пустую строку 422 «ожидается целое число», «Снять
      // сопоставление» падало молча (mappingInProgress просто гасился в finally). Параметр нужно
      // не слать вовсе, когда planned_item_id=null — тогда FastAPI подставляет свой default None.
      const qs = `purchase_item_id=${mapTarget.value.purchase_item_id}` + (plannedItemId != null ? `&planned_item_id=${plannedItemId}` : '')
      const result = await apiFetch<{ moved_to_category_id?: number | null }>(`/feo-planned-items/map?${qs}`, {
        method: 'POST',
      })
      showMapDialog.value = false
      // Правка владельца (2026-08-18): «позиции в дашборде должны пересчитываться
      // сразу» — map/unmap двигает total_linked/qty_linked в /planned-purchase-totals
      // (шапка узла, «Не привязаны к плану»), а refreshComparison() один обновлял
      // только панель «план vs факт», не дашборд. refreshReqData(catId) — тот же
      // приём, что в saveReqItemEdit/doReqItemDelete: перечитывает totals/items/
      // plan-tree И делает delete comparisonData[catId] + ensureComparison(catId)
      // (см. её тело выше), так что оба источника обновляются одним вызовом.
      const movedToCategoryId = result?.moved_to_category_id ?? null
      if (mapCategoryId.value) await ctx.refreshReqData(mapCategoryId.value)
      // Перенос между категориями ФЭО (решение владельца 2026-08-18): бэкенд
      // POST /feo-planned-items/map при сопоставлении с плановой позицией из ДРУГОЙ
      // категории больше не отказывает 409, а переносит позицию закупки (и
      // зеркально — связанную позицию заявки) в категорию плановой позиции,
      // возвращая moved_to_category_id. refreshReqData(mapCategoryId) выше уже
      // перечитал totals/items/plan-tree по всей субсидии разом (эндпоинты не
      // фильтруются по категории) и инвалидировал comparisonData СТАРОЙ категории —
      // но НОВУЮ категорию она не трогала, и панель «план vs факт» там показывала
      // бы устаревшие числа до перезагрузки страницы. Инвалидируем и её тем же
      // приёмом, что saveReqItemEdit делает при ручной смене категории (см. выше):
      // без повторного похода за totals/items/plan-tree, только delete+ensureComparison.
      if (movedToCategoryId != null && movedToCategoryId !== mapCategoryId.value) {
        delete ctx.comparisonData.value[movedToCategoryId]
        await ctx.ensureComparison(movedToCategoryId)
      }
    } catch (e: any) {
      // Этап 3 (владелец, 2026-09-02): раньше здесь не было catch вовсе — ошибка
      // (в т.ч. новая 409 PLANNED_ITEM_CATEGORY_MISMATCH при несовпадении категорий,
      // см. app/services/plan_autoassign.py) улетала необработанной, диалог оставался
      // открытым без единого объяснения пользователю. Распаковываем detail.message
      // (правило проекта — не глотать generic-снэкбаром), диалог намеренно НЕ
      // закрываем — пусть человек попробует другую плановую позицию.
      showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось сопоставить с плановой позицией', 'error')
    } finally {
      mappingInProgress.value = false
    }
  }

  return { showMapDialog, mapTarget, mapCategoryId, mappingInProgress, openMapDialog, applyMapping }
}
