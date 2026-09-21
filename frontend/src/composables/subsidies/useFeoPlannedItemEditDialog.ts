// Состояние и логика диалога «Редактировать плановую позицию» (PlannedItemEditDialog.vue) —
// один из четырёх кусков панели «План vs факт» ФЭО, вынесенных из SubsidiesView.vue
// (см. usePlannedItems.ts — баррель, объединяющий этот файл с остальными тремя;
// разнесены по файлам, чтобы не собирать один composable на 700+ строк —
// Правило №5, модульность кода). Module-level singleton state.
import { computed, ref, watch } from 'vue'
import { debounce } from 'lodash-es'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { numOrNull } from '@/utils/numberFormat'
import { pushFeoUndo } from './useFeoUndoStack'
import { buildPlannedItemFullPayload, putPlannedItemFull } from './useFeoLevel5'
import { fetchMonthlySchedulePreview } from './feoMonthlySchedulePreview'
import type { SubsidyDetailContext } from './useSubsidyDetail'
import type { FeoPlannedItem } from './types'

// Снимок «до» — payload, собранный из ИСХОДНОЙ позиции в момент открытия
// диалога (openEditPlannedItem ниже), нужен только стеку отмены (удали за
// собой при saveEditPlannedItem — регистрация ниже). Module-level переменная —
// тот же приём, что и _pendingBudgetSave в useFeoTreeDnd.ts: между открытием
// диалога и сохранением всегда ровно одна активная правка (второй диалог этой
// сущности не может открыться поверх первого).
let editPlannedBeforeSnapshot: Record<string, unknown> | null = null

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
  // Конец периода (владелец, Волна 3, п.3) — см. тот же комментарий в
  // useFeoPlannedItemAddDialog.ts/plannedItemForm.monthly_end_date. Открытие
  // диалога правки (openEditPlannedItem ниже) подставляет уже сохранённое
  // значение — легаси-позиции (заполнен months_count, monthly_end_date NULL)
  // остаются в старом режиме, пока человек сам не введёт конец периода.
  monthly_end_date: '' as string,
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
  // Раздельные числа по ФЭО (владелец, 2026-09-14) — второй, независимый
  // комплект, показывается в форме только когда ОБЕ галочки происхождения
  // стоят разом (см. editShowBothOriginFields ниже) — тот же смысл, что и в
  // диалоге создания (useFeoPlannedItemAddDialog.ts). quantity/unitPrice/
  // amount выше остаются «планом» (единственный источник дерева/контроля
  // превышения). ПОЛНАЯ замена в PUT — как и у unitPrice выше.
  feoQuantity: '' as string | number,
  feoUnitPrice: '' as string | number,
  feoAmount: '' as string | number,
  // Порядок позиции в категории (владелец, п.25 волны 2, 2026-09-13). PUT —
  // полная замена (см. коммент у update_planned_item в feo_planned_items.py:
  // item.sort_order = data.sort_order, БЕЗ model_fields_set-guard, в отличие
  // от item_type/is_feo_breakdown) — раньше это окно вообще не хранило и не
  // отправляло sort_order, поле молча уходило как null, а сортировка листа
  // (sort_order.nulls_last(), id) выкидывала отредактированную позицию в
  // конец списка. Читаем текущее значение при открытии и шлём его же обратно
  // неизменным — правка названия/суммы не должна двигать позицию.
  sort_order: null as number | null,
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

// Раздельные поля «По ФЭО»/«Внутренний план» видны, только когда ОБЕ галочки
// происхождения стоят одновременно (задача владельца, п.3) — тот же принцип,
// что и в диалоге создания (editShowBothOriginFields, useFeoPlannedItemAddDialog.ts).
const editShowBothOriginFields = computed(() =>
  editPlannedDialog.value.is_feo_breakdown && editPlannedDialog.value.is_internal_plan,
)

// Тот же режим «цена задана → сумма считается сама», что и у основного
// комплекта (editAmountIsComputed выше) — применён ко второму, ФЭО-комплекту.
const editFeoAmountIsComputed = computed(() =>
  editPlannedDialog.value.feoUnitPrice !== '' && editPlannedDialog.value.feoUnitPrice != null && Number(editPlannedDialog.value.feoUnitPrice) !== 0,
)
function recalcEditFeoAmountFromUnitPrice() {
  if (!editFeoAmountIsComputed.value) return
  const price = Number(editPlannedDialog.value.feoUnitPrice)
  const qty = editPlannedDialog.value.feoQuantity !== '' && Number(editPlannedDialog.value.feoQuantity) > 0 ? Number(editPlannedDialog.value.feoQuantity) : 1
  editPlannedDialog.value.feoAmount = Math.round(qty * price * 100) / 100
}
watch([() => editPlannedDialog.value.feoQuantity, () => editPlannedDialog.value.feoUnitPrice], () => recalcEditFeoAmountFromUnitPrice())

// Расшифровка периода ежемесячного платежа (владелец, Волна 3, п.2-3) — тот же
// принцип, что и в useFeoPlannedItemAddDialog.ts::addPlannedMonthlySchedule:
// «6 мес. 20 дн.» + итог, посчитанные СЕРВЕРОМ по единственной формуле
// compute_monthly_schedule (Правило №6) — не дублируем расчёт остатка дней.
const editMonthlySchedule = ref<{ label: string; total: number | null } | null>(null)

async function refreshEditMonthlySchedule() {
  const d = editPlannedDialog.value
  if (d.payment_mode !== 'monthly') {
    editMonthlySchedule.value = null
    return
  }
  editMonthlySchedule.value = await fetchMonthlySchedulePreview(
    d.monthly_start_date, d.monthly_end_date, d.monthly_amount,
  )
}

// Debounce + недописанная дата не бьёт по серверу — см. докстринг
// feoMonthlySchedulePreview.ts (владелец, 2026-09-14, тот же дефект что и в
// диалоге создания, вынесено в общий модуль — Правило №6, второй watch с той
// же дырой не заводим).
const debouncedRefreshEditMonthlySchedule = debounce(refreshEditMonthlySchedule, 400)

watch(
  [
    () => editPlannedDialog.value.payment_mode,
    () => editPlannedDialog.value.monthly_start_date,
    () => editPlannedDialog.value.monthly_end_date,
    () => editPlannedDialog.value.monthly_amount,
  ],
  () => { void debouncedRefreshEditMonthlySchedule() },
)

// Легаси-позиция (месяцы заведены целым числом months_count, БЕЗ периода) —
// показываем «было: N мес.» без блокирующей валидации, чтобы «не сломать»
// старые позиции (задача владельца): их можно продолжать сохранять как есть,
// период можно ввести дополнительно в любой момент, тогда он станет главным.
const editLegacyMonthsLabel = computed<string | null>(() => {
  const d = editPlannedDialog.value
  if (d.payment_mode !== 'monthly' || d.monthly_end_date) return null
  return d.months_count ? `Задано по старому формату: ${d.months_count} мес. (без периода)` : null
})

// Кнопка «Сохранить» не блокируется для легаси-позиций (months_count без
// периода уже сохранён и продолжает работать) — блокируется только НОВЫЙ
// ввод периода наполовину (одна дата задана, вторая — нет).
const editPlannedItemDisabled = computed(() => {
  const d = editPlannedDialog.value
  if (d.payment_mode !== 'monthly') return false
  const hasAnyPeriodInput = !!d.monthly_start_date || !!d.monthly_end_date
  if (!hasAnyPeriodInput && d.months_count) return false // легаси не трогаем
  return !d.monthly_start_date || !d.monthly_end_date
})

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
    editPlannedDialog.value.monthly_end_date = item.monthly_end_date ?? ''
    editPlannedDialog.value.item_type = item.item_type ?? null
    editPlannedDialog.value.months_count = item.months_count ?? null
    editPlannedDialog.value.monthly_amount = item.monthly_amount ?? null
    editPlannedDialog.value.is_feo_breakdown = item.is_feo_breakdown ?? false
    editPlannedDialog.value.is_internal_plan = item.is_internal_plan ?? false
    editPlannedDialog.value.feoQuantity = item.feo_quantity != null ? parseFloat(String(item.feo_quantity)) : ''
    editPlannedDialog.value.feoUnitPrice = item.feo_unit_price != null ? parseFloat(String(item.feo_unit_price)) : ''
    editPlannedDialog.value.feoAmount = item.feo_amount != null ? parseFloat(String(item.feo_amount)) : ''
    editPlannedDialog.value.sort_order = item.sort_order ?? null
    editMonthlySchedule.value = null
    editPlannedDialog.value.show = true
    // Снимок «до» для стека отмены (владелец, п.4 волны 4, 2026-09-13):
    // «изменили — отмена возвращает прежние значения» — buildPlannedItemFullPayload
    // переиспользует ЕДИНСТВЕННЫЙ существующий сборщик полного payload позиции
    // (useFeoLevel5.ts, тот же, что и у registerDeleteUndo/registerMoveUndo там —
    // Правило №6, второй набор полей не заводим).
    editPlannedBeforeSnapshot = buildPlannedItemFullPayload(item)
    void refreshEditMonthlySchedule()
  }

  async function saveEditPlannedItem() {
    if (!ctx) return
    editPlannedDialog.value.saving = true
    try {
      const d = editPlannedDialog.value
      const isMonthly = d.payment_mode === 'monthly'
      const body = {
        feo_category_id: d.feo_category_id,
        name: d.name,
        // Волна 3, п.2 («двоится Количество») — для monthly-режима «Кол-во»
        // всегда 1 (поле скрыто в форме, см. PlannedItemEditDialog.vue); срок
        // живёт отдельно (monthly_start_date/monthly_end_date ниже). Backend
        // тоже фиксирует это в _apply_payment_fields — дублируем здесь, чтобы
        // не полагаться на то, что d.quantity не «протекло» из one_time-режима.
        quantity: isMonthly ? 1 : numOrNull(d.quantity),
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
        // Конец периода (владелец, Волна 3, п.3) — задан → основной режим,
        // months_count пересчитывается сервером (compute_monthly_schedule) и
        // ручной ввод игнорируется. НЕ задан → легаси-позиция, months_count
        // передаётся как есть (см. докстринг FeoPlannedItem.monthly_end_date:
        // «старые позиции должны продолжать работать»).
        monthly_end_date: isMonthly && d.monthly_end_date ? d.monthly_end_date : null,
        months_count: (isMonthly && !d.monthly_end_date) ? numOrNull(d.months_count) : null,
        monthly_amount: isMonthly ? numOrNull(d.monthly_amount) : null,
        item_type: d.item_type,
        // Синхронизация типа с товаром каталога (владелец, 21.09, раздел W2) —
        // диалог правки product_id не знает (плановая позиция его не хранит,
        // см. докстринг FeoPlannedItemCreate.product_id в backend/app/schemas/
        // feo.py), поэтому backend (update_planned_item → resolve_product_for_planned_item
        // в app/services/item_types.py) подбирает товар сам по точному
        // совпадению имени. sync_product_kind=true шлётся всегда — на бэкенде
        // это no-op, если item_type не менялся/товар уже с тем же типом.
        sync_product_kind: true,
        is_feo_breakdown: d.is_feo_breakdown,
        is_internal_plan: d.is_internal_plan,
        // Раздельные числа по ФЭО (владелец, 2026-09-14) — ПОЛНАЯ замена, как
        // и у unit_price выше: без явной отправки уже введённые feo_quantity/
        // feo_unit_price/feo_amount молча обнулятся.
        feo_quantity: numOrNull(d.feoQuantity),
        feo_unit_price: numOrNull(d.feoUnitPrice),
        feo_amount: numOrNull(d.feoAmount),
        // См. коммент у editPlannedDialog.sort_order выше — без явной отправки
        // текущего значения позиция улетает в конец списка (сортировка
        // sort_order.nulls_last(), id в feo_planned_items_reports.py).
        sort_order: d.sort_order,
      }
      const saved = await apiFetch<FeoPlannedItem>(`/feo-planned-items/${d.id}`, { method: 'PUT', body: JSON.stringify(body) })
      editPlannedDialog.value.show = false
      registerEditUndo(d.id, d.feo_category_id, d.name, editPlannedBeforeSnapshot, body)
      editPlannedBeforeSnapshot = null
      if (saved.product_kind_synced && saved.product_name) {
        showSnack(`Тип «${d.item_type}» записан в товар каталога «${saved.product_name}»`)
      }
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

  // Стек отмены: «изменили — отмена возвращает прежние значения». before/after —
  // ПОЛНЫЕ снимки (PUT здесь всегда полная замена — см. комментарии выше), не
  // diff: undo/redo шлют целиком один из двух через putPlannedItemFull
  // (useFeoLevel5.ts, тот же раритетный сеттер, что и у registerDeleteUndo). Без
  // снимка «до» (диалог открывали раньше, чем появился этот стек, — не должно
  // случаться, но на всякий случай) — undo честно не регистрируется вовсе,
  // лучше отсутствие кнопки, чем откат «в никуда».
  function registerEditUndo(
    itemId: number, categoryId: number, name: string,
    before: Record<string, unknown> | null, after: Record<string, unknown>,
  ) {
    if (!before || !ctx) return
    pushFeoUndo({
      label: `изменение позиции «${name}»`,
      undo: async () => {
        const res = await putPlannedItemFull(itemId, before)
        if (res.ok) await Promise.all([ctx.refreshComparison(categoryId), ctx.refreshReqData()])
        return res.ok ? { ok: true } : { ok: false, error: res.error }
      },
      redo: async () => {
        const res = await putPlannedItemFull(itemId, after)
        if (res.ok) await Promise.all([ctx.refreshComparison(categoryId), ctx.refreshReqData()])
        return res.ok ? { ok: true } : { ok: false, error: res.error }
      },
    })
  }

  return {
    editPlannedDialog, editAmountIsComputed, editPriceCaption, openEditPlannedItem, saveEditPlannedItem,
    editMonthlySchedule, editLegacyMonthsLabel, editPlannedItemDisabled,
    editShowBothOriginFields, editFeoAmountIsComputed,
  }
}
