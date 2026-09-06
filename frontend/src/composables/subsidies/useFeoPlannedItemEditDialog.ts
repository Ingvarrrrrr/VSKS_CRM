// Состояние и логика диалога «Редактировать плановую позицию» (PlannedItemEditDialog.vue) —
// один из четырёх кусков панели «План vs факт» ФЭО, вынесенных из SubsidiesView.vue
// (см. usePlannedItems.ts — баррель, объединяющий этот файл с остальными тремя;
// разнесены по файлам, чтобы не собирать один composable на 700+ строк —
// Правило №5, модульность кода). Module-level singleton state.
import { computed, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { numOrNull } from '@/utils/numberFormat'
import type { SubsidyDetailContext } from './useSubsidyDetail'
import type { FeoPlannedItem } from './types'

const editPlannedDialog = ref({
  show: false, saving: false,
  id: 0, feo_category_id: 0,
  name: '', quantity: '' as string | number, unit: '', amount: '' as string | number,
  // Цена за единицу (владелец, 2026-09-02) — то же необязательное поле, что и в
  // диалоге создания (FeoPlannedItemsSelect.vue::createForm.unitPrice). ПРОБЕЛ,
  // из-за которого владелец видел «опять делит»: это окно правки поля не имело
  // вовсе, а PUT ниже — полная замена, так что при сохранении любой другой правки
  // цена молча обнулялась бы, даже если была задана. См. editAmountIsComputed.
  unitPrice: '' as string | number,
  payment_mode: 'one_time' as 'one_time' | 'monthly',
  planned_date: '' as string,
  monthly_start_date: '' as string,
  months_count: null as number | null,
  monthly_amount: null as number | null,
  // Блок 1 (план zany-fluttering-mountain.md, 2026-08-14): PUT — полная замена
  // (FeoPlannedItemCreate), поле обязано доехать до payload неизменным, иначе
  // любое сохранение этого диалога молча стирало бы уже выбранный тип (см.
  // «выбранное на предыдущем этапе не смеет меняться само»). Своего v-select
  // тут нет — правка типа только через диалог создания/импорт.
  item_type: null as string | null,
  // Происхождение (владелец, 2026-09-01) — ДВЕ НЕЗАВИСИМЫЕ галочки, тот же
  // смысл, что и в диалоге создания (PlannedItemAddDialog.vue). Всегда шлются
  // явно в PUT-payload (см. saveEditPlannedItem) — backend читает их через
  // model_fields_set, поэтому «не трогать» здесь недостижимо и не нужно:
  // это и есть штатное место правки признака (задача владельца, п.5).
  is_feo_breakdown: false as boolean,
  is_internal_plan: false as boolean,
})

// Тот же режим «цена задана → сумма считается сама», что и в диалоге создания
// (FeoPlannedItemsSelect.vue::createAmountIsComputed/recalcCreateAmountFromUnitPrice/
// createPriceCaption) — формулировки специально СЛОВО В СЛОВО те же, чтобы не
// разъезжались между двумя окнами правки одной и той же сущности.
const editAmountIsComputed = computed(() => editPlannedDialog.value.unitPrice !== '' && editPlannedDialog.value.unitPrice != null && Number(editPlannedDialog.value.unitPrice) !== 0)
function recalcEditAmountFromUnitPrice() {
  if (!editAmountIsComputed.value) return
  const price = Number(editPlannedDialog.value.unitPrice)
  const qty = editPlannedDialog.value.quantity !== '' && Number(editPlannedDialog.value.quantity) > 0 ? Number(editPlannedDialog.value.quantity) : 1
  editPlannedDialog.value.amount = Math.round(qty * price * 100) / 100
}
watch([() => editPlannedDialog.value.quantity, () => editPlannedDialog.value.unitPrice], () => recalcEditAmountFromUnitPrice())
const editPriceCaption = computed((): string =>
  editAmountIsComputed.value
    ? 'С ценой за единицу закупка по этой позиции проверяется и по цене, и по количеству, и по сумме — превысить нельзя ничего из трёх.'
    : 'Без цены за единицу количество считается ориентировочным и не ограничивает закупку — под контролем только общая сумма плана.'
)

type EditDialogCtx = Pick<SubsidyDetailContext, 'refreshComparison' | 'refreshReqData'>

export function useFeoPlannedItemEditDialog(ctx?: EditDialogCtx) {
  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success') {
    toast.addToast(text, color)
  }

  function openEditPlannedItem(item: FeoPlannedItem) {
    editPlannedDialog.value.id = item.id
    editPlannedDialog.value.feo_category_id = item.feo_category_id
    editPlannedDialog.value.name = item.name
    editPlannedDialog.value.quantity = item.quantity != null ? parseFloat(String(item.quantity)) : ''
    editPlannedDialog.value.unit = item.unit || ''
    editPlannedDialog.value.amount = item.amount != null ? parseFloat(String(item.amount)) : ''
    editPlannedDialog.value.unitPrice = item.unit_price != null ? parseFloat(String(item.unit_price)) : ''
    editPlannedDialog.value.payment_mode = item.payment_mode ?? 'one_time'
    editPlannedDialog.value.planned_date = item.planned_date ?? ''
    editPlannedDialog.value.monthly_start_date = item.monthly_start_date ?? ''
    editPlannedDialog.value.item_type = item.item_type ?? null
    editPlannedDialog.value.months_count = item.months_count ?? null
    editPlannedDialog.value.monthly_amount = item.monthly_amount ?? null
    editPlannedDialog.value.is_feo_breakdown = item.is_feo_breakdown ?? false
    editPlannedDialog.value.is_internal_plan = item.is_internal_plan ?? false
    editPlannedDialog.value.show = true
  }

  async function saveEditPlannedItem() {
    if (!ctx) return
    editPlannedDialog.value.saving = true
    try {
      const d = editPlannedDialog.value
      const isMonthly = d.payment_mode === 'monthly'
      await apiFetch(`/feo-planned-items/${d.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          feo_category_id: d.feo_category_id,
          name: d.name,
          quantity: numOrNull(d.quantity),
          unit: d.unit || null,
          amount: isMonthly ? null : numOrNull(d.amount),
          // PUT — полная замена (см. коммент у editPlannedDialog.unitPrice выше и
          // у item.unit_price = data.unit_price в feo_planned_items.py) — без явной
          // передачи цена за единицу молча обнулится, даже если правили что-то другое.
          // numOrNull — тот же хелпер, что и в savePlannedItem (см. @/utils/
          // numberFormat.ts) — было три места, каждое приводило '' к null по-своему.
          unit_price: numOrNull(d.unitPrice),
          notes: null,
          is_active: true,
          payment_mode: d.payment_mode,
          planned_date: !isMonthly && d.planned_date ? d.planned_date : null,
          monthly_start_date: isMonthly && d.monthly_start_date ? d.monthly_start_date : null,
          months_count: isMonthly ? numOrNull(d.months_count) : null,
          monthly_amount: isMonthly ? numOrNull(d.monthly_amount) : null,
          item_type: d.item_type,
          is_feo_breakdown: d.is_feo_breakdown,
          is_internal_plan: d.is_internal_plan,
        }),
      })
      editPlannedDialog.value.show = false
      // См. комментарий у deletePlannedItem (SubsidiesView.vue) — refreshComparison
      // один не обновляет planTreeByCat, от которого зависят числа узла/родителей и
      // плашка превышения.
      await Promise.all([ctx.refreshComparison(d.feo_category_id), ctx.refreshReqData()])
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.detail || e?.message || 'Ошибка сохранения', 'error')
    } finally {
      editPlannedDialog.value.saving = false
    }
  }

  return { editPlannedDialog, editAmountIsComputed, editPriceCaption, openEditPlannedItem, saveEditPlannedItem }
}
