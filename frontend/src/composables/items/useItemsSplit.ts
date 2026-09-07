// useItemsSplit — «Разбивка позиции по категориям ФЭО» dialog (владелец
// 2026-08-18). Закупка «Заказано» (statuses с tzFrozen=true) запрещает
// ДОБАВЛЕНИЕ новых позиций, но не запрещает разложить уже существующую
// позицию по нескольким категориям/плановым позициям — количество и сумма не
// меняются, только распределение. POST /purchases/{pid}/items/{item_id}/split
// (backend, не трогаем): Σ quantity частей ДОЛЖНА точно совпасть с quantity
// исходной позиции, иначе backend вернёт 409 с числами — этот же инвариант
// проверяется на лету здесь, чтобы 409 не был первым, что видит пользователь.
// Extracted from PurchaseItemsEditor.vue (monolith refactor, часть 3).
import { computed, reactive, ref, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { FeoNode } from '@/composables/useFeoLeaves'
import type { FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'
import type { ToastType } from '@/composables/useToast'

// EditorItem is structurally identical to the parent's; kept loose here (same
// convention as ItemsTableFlat.vue) since the parent owns the real shape.
type EditorItem = any

export interface SplitPart {
  quantity: number | null
  // UI-only: узел дерева ФЭО (может быть промежуточным, не только листом) —
  // тот же паттерн, что item.feo_node_id/feo_category_id у обычной позиции.
  feo_node_id: number | null
  feo_category_id: number | null
  feo_planned_item_id: number | null
}

export interface UseItemsSplitDeps {
  props: { purchaseId?: number | null }
  localItems: Ref<EditorItem[]>
  feoNodes: Ref<FeoNode[]>
  display: { smAndDown: { value: boolean }; mdAndDown: { value: boolean } }
  emit: { (event: 'reload-requested'): void }
  showSnack: (text: string, color?: ToastType, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void
}

export function useItemsSplit(deps: UseItemsSplitDeps) {
  const { props, localItems, feoNodes, display, emit, showSnack } = deps

  const splitDialog = reactive({
    show: false,
    idx: null as number | null,
    saving: false,
  })
  const splitParts = ref<SplitPart[]>([])

  const splitItem = computed<EditorItem | null>(() =>
    splitDialog.idx != null ? (localItems.value[splitDialog.idx] ?? null) : null
  )

  // Тот же приём адаптивной ширины диалога, что и reqItemEditDialogWidth в
  // SubsidiesView.vue (сессия 2026-08-18): 720 планшет/маленький ноутбук, 900
  // обычный десктоп, 1100 крупный монитор. mobile (объявлен в родителе) держит
  // :fullscreen, как у остальных диалогов этого файла.
  const splitDialogWidth = computed(() => {
    if (display.smAndDown.value) return 720
    if (display.mdAndDown.value) return 900
    return 1100
  })

  const splitDistributed = computed(() =>
    splitParts.value.reduce((s, p) => s + (Number(p.quantity) || 0), 0)
  )
  const splitRemaining = computed(() => {
    const total = Number(splitItem.value?.quantity ?? 0)
    // Округление до 4 знаков — в БД parts.quantity Numeric(15,4), сравнение «в лоб»
    // float'ов иначе почти никогда не даст точный 0.
    return Math.round((total - splitDistributed.value) * 10000) / 10000
  })
  const splitBalanced = computed(() => splitParts.value.length >= 2 && Math.abs(splitRemaining.value) < 0.0001)
  // Backend требует quantity части > 0 (см. split_purchase_item) — проверяем на
  // лету, чтобы не отправлять заведомо отклоняемый запрос (часть с пустым/нулевым
  // кол-вом при «сходящемся» остатке технически возможна, если другая часть
  // компенсирует разницу).
  const splitPartsValid = computed(() => splitParts.value.every(p => Number(p.quantity) > 0))
  const splitCanSave = computed(() => splitBalanced.value && splitPartsValid.value)

  function openSplitDialog(idx: number) {
    const item = localItems.value[idx]
    if (!item) return
    splitDialog.idx = idx
    splitParts.value = [
      {
        quantity: null,
        feo_node_id: item.feo_node_id ?? item.feo_category_id ?? null,
        feo_category_id: item.feo_category_id ?? null,
        feo_planned_item_id: null,
      },
      { quantity: null, feo_node_id: null, feo_category_id: null, feo_planned_item_id: null },
    ]
    splitDialog.show = true
  }

  // ⚠️ БАГ (найден живым тестом на локалке, сессия 2026-08-18): guard
  // `splitDialog.saving` защищает от закрытия ПОЛЬЗОВАТЕЛЕМ (кнопка «Отмена»/
  // клик вне диалога) во время сохранения — но saveSplit() ниже вызывает эту же
  // функцию ПОСЛЕ успешного запроса, ДО того как finally сбросит saving в false,
  // поэтому guard молча блокировал автозакрытие: сеть отвечала 200, снэкбар
  // «Позиция разбита на части» показывался, а диалог оставался открытым с
  // прежними значениями частей. Поэтому здесь guard не проверяется — вызывающая
  // сторона (saveSplit) сама решает, когда звать forceClose; пользовательский
  // путь (кнопка «Отмена») защищён отдельно через :disabled на этой кнопке и
  // :persistent на v-dialog (см. template), а не через эту функцию.
  function closeSplitDialog() {
    splitDialog.show = false
    splitDialog.idx = null
    splitParts.value = []
  }

  function addSplitPart() {
    splitParts.value.push({ quantity: null, feo_node_id: null, feo_category_id: null, feo_planned_item_id: null })
  }

  function removeSplitPart(i: number) {
    if (splitParts.value.length <= 2) return
    splitParts.value.splice(i, 1)
  }

  // Тот же паттерн, что onItemFeoChange: клик по нелистовому узлу дерева только
  // углубляет навигацию (feo_category_id остаётся null), клик по листу — фиксирует
  // категорию части. Смена категории части сбрасывает её плановую позицию (Ур.5),
  // если та принадлежала другой категории — иначе backend отклонит part с 409.
  function onSplitPartFeoChange(i: number, nodeId: number | null) {
    const part = splitParts.value[i]
    if (!part) return
    const isLeaf = nodeId != null && (feoNodes.value.find(n => n.id === nodeId)?.is_leaf ?? false)
    const newCategoryId = isLeaf ? nodeId : null
    if (part.feo_category_id !== newCategoryId) part.feo_planned_item_id = null
    part.feo_node_id = nodeId
    part.feo_category_id = newCategoryId
  }

  function splitPartPlannedSelection(i: number): FeoPlanSelection | null {
    const part = splitParts.value[i]
    if (!part || part.feo_planned_item_id == null) return null
    return { kind: 'planned_item', id: part.feo_planned_item_id }
  }

  // feo_planned_item_id (POST /split) — id конкретной FeoPlannedItem (Ур.5), НЕ
  // id категории/плановой строки уровня категории. FeoPlannedItemsSelect может
  // эмитить kind='plan_position'|'feo_article' (план на уровне самой категории,
  // без отдельной Ур.5 записи) — такие значения split-эндпоинту не передаём.
  function onSplitPartPlannedChange(i: number, val: FeoPlanSelection | null) {
    const part = splitParts.value[i]
    if (!part) return
    part.feo_planned_item_id = val && val.kind === 'planned_item' ? val.id : null
  }

  function splitPartAmount(i: number): number | null {
    const part = splitParts.value[i]
    const unitPrice = splitItem.value?.unit_price
    if (!part || part.quantity == null || unitPrice == null) return null
    return Math.round(Number(part.quantity) * Number(unitPrice) * 100) / 100
  }

  async function saveSplit() {
    const item = splitItem.value
    if (!item || props.purchaseId == null) return
    const itemId = (item as any).id
    if (itemId == null) {
      showSnack('Позиция ещё не сохранена — сохраните закупку и повторите', 'warning')
      return
    }
    if (!splitCanSave.value) return
    splitDialog.saving = true
    try {
      await apiFetch(`/purchases/${props.purchaseId}/items/${itemId}/split`, {
        method: 'POST',
        body: JSON.stringify({
          parts: splitParts.value.map(p => ({
            quantity: p.quantity,
            feo_category_id: p.feo_category_id,
            feo_planned_item_id: p.feo_planned_item_id,
          })),
        }),
      })
      showSnack('Позиция разбита на части', 'success')
      closeSplitDialog()
      // Тот же приём, что у bulkAddToCatalog/runCreatePlannedBulk: сервер
      // пересчитал/создал позиции — перезагружаем их у родителя, а не пытаемся
      // угадать результат локально.
      emit('reload-requested')
    } catch (e: any) {
      showSnack(e?.payload?.message ?? e?.detail ?? e?.message ?? 'Ошибка разбивки позиции', 'error')
    } finally {
      splitDialog.saving = false
    }
  }

  return {
    splitDialog, splitParts, splitItem, splitDialogWidth,
    splitDistributed, splitRemaining, splitBalanced, splitPartsValid, splitCanSave,
    openSplitDialog, closeSplitDialog, addSplitPart, removeSplitPart,
    onSplitPartFeoChange, splitPartPlannedSelection, onSplitPartPlannedChange, splitPartAmount,
    saveSplit,
  }
}
