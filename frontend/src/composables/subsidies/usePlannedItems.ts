// Баррель четырёх диалогов панели «План vs факт» ФЭО — добавить плановую
// позицию, править плановую позицию, править ручной план категории,
// сопоставить факт с плановой позицией. Раньше это был один файл на 700+ строк
// (Правило №5 — модульность кода запрещает такой размер); логика и состояние
// каждого диалога теперь в своём файле:
//   useFeoPlannedItemMap.ts       — PlannedItemMapDialog.vue
//   useFeoPlannedItemAddDialog.ts — PlannedItemAddDialog.vue (+ конвертация
//                                    ручного плана категории и «из закупки»)
//   useFeoPlannedItemEditDialog.ts — PlannedItemEditDialog.vue
//   useFeoCategoryPlanDialog.ts   — CategoryPlanEditDialog.vue
// usePlannedItems() объединяет их в один объект — SubsidiesView.vue и сами
// диалоги продолжают вызывать ровно её (Правило №6 — один способ получить
// состояние этих диалогов, не четыре разных импорта в потребителях).
import { useFeoPlannedItemMap } from './useFeoPlannedItemMap'
import { useFeoPlannedItemAddDialog } from './useFeoPlannedItemAddDialog'
import { useFeoPlannedItemEditDialog } from './useFeoPlannedItemEditDialog'
import { useFeoCategoryPlanDialog } from './useFeoCategoryPlanDialog'
import type { SubsidyDetailContext } from './useSubsidyDetail'

type PlannedItemsCtx = Pick<SubsidyDetailContext,
  'selectedId' | 'feoCategories' | 'loadFeo' | 'comparisonData' | 'refreshComparison' | 'ensureComparison' | 'refreshReqData' | 'factForPlanned'>

export function usePlannedItems(ctx?: PlannedItemsCtx) {
  return {
    ...useFeoPlannedItemMap(ctx),
    ...useFeoPlannedItemAddDialog(ctx),
    ...useFeoPlannedItemEditDialog(ctx),
    ...useFeoCategoryPlanDialog(ctx),
  }
}
