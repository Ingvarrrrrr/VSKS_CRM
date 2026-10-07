// Инлайн-правка колонки «Тип» в панели «План vs факт» (FeoLevel5Panel.vue) —
// владелец, 21.09, раздел W2 плана corrections-21-09.md: колонка «Тип» стала
// редактируемой на месте (маленький v-select), вместо диалога правки —
// FeoLevel5Panel.vue уже показывал подсказку «укажите тип», но сменить его
// можно было только через полноценный диалог PlannedItemEditDialog.vue.
//
// Переиспользует putPlannedItemFull/buildPlannedItemFullPayload
// (useFeoLevel5.ts) — тот же единственный «сеттер» PUT /feo-planned-items/{id},
// что и у стека отмены (registerEditUndo/registerMoveUndo) и у самого диалога
// правки — второй апдейт здесь не заводим (Правило №6, «переиспользуй, не
// заводи второй механизм»).
//
// Вынесено в отдельный файл — useFeoLevel5.ts уже 900+ строк, новая логика не
// дописывается в разросшийся файл (Правило №5, модульность кода).
//
// sync_product_kind: true отправляется всегда (владелец, 21.09, раздел W2) —
// плановая позиция не хранит product_id (см. докстринг
// FeoPlannedItemCreate.product_id, backend/app/schemas/feo.py — «транзитное
// поле запроса»), GET .../comparison, из которого приходят строки этой
// панели, его не отдаёт, но product_id и не нужен: backend
// (update_planned_item → app.services.item_types.resolve_product_for_planned_item)
// сам подбирает товар каталога по ТОЧНОМУ совпадению имени, когда product_id
// в теле запроса нет.
import { ref } from 'vue'
import { useToast, type ToastType } from '@/composables/useToast'
import { buildPlannedItemFullPayload, putPlannedItemFull } from './useFeoLevel5'
import { withPreservedScroll } from './usePreserveScroll'
import type { FeoPlannedItem } from './types'
import type { Ref } from 'vue'

// Module-level — id позиции, чья строка сейчас сохраняется (одновременно
// возможна только одна активная inline-правка, как и у reorderingPlannedItemId/
// movingPlannedItemId в useFeoLevel5.ts).
const savingItemTypeId = ref<number | null>(null)

export interface FeoLevel5ItemTypeCtx {
  refreshComparison: (categoryId: number) => Promise<void>
  refreshReqData: (catId?: number) => Promise<void>
  // selectedId добавлен волной 3B (доп. пробел «инлайн „Тип“ шлёт запрос
  // напрямую под флагом») — нужен putPlannedItemFull, чтобы решить
  // direct/revision через feoWriteAdapter.ts. FeoLevel5Panel.vue зовёт
  // useFeoLevel5ItemType(ctx) полным SubsidyDetailContext — selectedId уже есть.
  selectedId: Ref<number | null>
  // Контейнер прокрутки дерева (usePreserveScroll.ts) — тот же жёсткий прыжок
  // наверх страницы, что и у удаления/правки/добавления плановой позиции.
  feoTableArea: Ref<HTMLElement | null>
}

export function useFeoLevel5ItemType(ctx: FeoLevel5ItemTypeCtx) {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success') {
    toast.addToast(text, color)
  }

  async function saveInlineItemType(item: FeoPlannedItem, newType: string | null) {
    const normalized = newType || null
    if ((item.item_type ?? null) === normalized) return
    savingItemTypeId.value = item.id
    try {
      const payload = buildPlannedItemFullPayload(item, { item_type: normalized, sync_product_kind: true })
      // Волна 3B: в revision только {item_type} уходит в черновик (не весь
      // снимок) — см. аналогичный приём у moveOnePlannedItem в useFeoLevel5.ts.
      // sync_product_kind НЕ включаем (приёмка 02.10, п.1) — служебный флаг
      // запроса, указывающий backend подставить товар каталога, не поле
      // сущности FeoPlannedItem; direct-режим получает его как раньше — только
      // в полном payload выше, не в revisionFields.
      const res = await putPlannedItemFull(item.id, payload, ctx.selectedId.value ?? undefined, { item_type: normalized })
      if (!res.ok) {
        showSnack(res.error, 'error')
        return
      }
      if (res.mode === 'revision') {
        showSnack('Смена типа добавлена в корректировку')
        return
      }
      item.item_type = normalized
      if (res.item.product_kind_synced && res.item.product_name) {
        showSnack(`Тип «${normalized}» записан в товар каталога «${res.item.product_name}»`)
      }
      // Строка панели показывает item_type_effective (может быть унаследован от
      // покупок), но эта функция вызывается только когда !item_type_inherited
      // (см. FeoLevel5Panel.vue) — тогда item_type_effective ровно совпадает со
      // своим item_type, поэтому безопасно обновить сразу, не дожидаясь ответа
      // refreshComparison (без «моргания» старым значением до её завершения).
      item.item_type_effective = normalized
      // Тот же путь обновления, что и после диалога правки (saveEditPlannedItem,
      // useFeoPlannedItemEditDialog.ts): refreshComparison один не обновляет
      // planTreeByCat, от которого зависят числа узла/родителей и контроль по
      // типам (typeExcessFor) — нужны оба вызова.
      await withPreservedScroll(ctx.feoTableArea.value, () =>
        Promise.all([ctx.refreshComparison(item.feo_category_id), ctx.refreshReqData()]))
    } finally {
      savingItemTypeId.value = null
    }
  }

  return { savingItemTypeId, saveInlineItemType }
}
