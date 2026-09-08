// useFeoPlannedRows — ядро FeoPlannedItemsSelect.vue (рефакторинг монолита,
// 2026-09-08): выбранная категория/список её плановых позиций, «занято сейчас
// в этой форме» поверх серверных consumed/residual (pendingByPlannedItem),
// единый источник текста/цвета остатка (planResidualDisplay), проверка
// нехватки места под конкретную сумму (shortfall/isShort), выбор строки
// (selectItem/onItemRadioClick/detachGhost) и удаление плановой позиции
// (deletePlannedItem). Вынесено ДОСЛОВНО — вся арифметика (consumedFor/
// residualFor/shortfall) не пересчитывается заново, только перенесена
// (ПРАВИЛО №6 — один источник истины).
import { computed } from 'vue'
import { apiFetch } from '@/api'
import type { FeoNode } from '@/composables/useFeoLeaves'
import type { FeoPlanPosition, FeoPlanSelection, FeoPlanKind } from '@/composables/useFeoPlannedResiduals'
import { formatPlanResidual, type PlanResidualDisplay } from '@/utils/numberFormat'
import type { ToastType } from '@/composables/useToast'

/** Готовый набор подписей строки для FeoPlannedItemRow.vue — построен ОДИН раз
 *  (rowDisplayProps ниже), чтобы разметка dense-меню и развёрнутого списка не
 *  считала одно и то же по отдельности (ПРАВИЛО №6). */
export interface FeoPlannedRowDisplay {
  qtyLabel: string
  plannedLabel: string
  consumedLabel: string
  residualDisplay: PlanResidualDisplay
  shortfallLabel: string | null
}

export interface PendingItemEntry {
  name: string
  quantity: number | null
  unit: string | null
  amount: number
}

export interface UseFeoPlannedRowsProps {
  modelValue: FeoPlanSelection | null
  categoryId: number | null
  nodes: FeoNode[]
  items: FeoPlanPosition[]
  amount?: number | null
  readonly?: boolean
  dense?: boolean
  purchaseId?: number | null
  wishId?: number | null
  pendingByPlannedItem?: Record<number, number> | null
  pendingItemsByPlannedItem?: Record<number, PendingItemEntry[]> | null
}

export interface UseFeoPlannedRowsDeps {
  props: UseFeoPlannedRowsProps
  emit: {
    (event: 'update:modelValue', val: FeoPlanSelection | null): void
    (event: 'planned-item-deleted'): void
  }
  showSnack: (text: string, color?: ToastType) => void
}

const KIND_CHIP_COLOR: Record<FeoPlanKind, string> = {
  plan_position: 'teal',
  feo_article: 'grey',
  planned_item: 'indigo',
}
const KIND_CHIP_LABEL: Record<FeoPlanKind, string> = {
  plan_position: 'плановая позиция',
  feo_article: 'статья ФЭО с планом',
  planned_item: 'детализация',
}

export function useFeoPlannedRows(deps: UseFeoPlannedRowsDeps) {
  const { props, emit, showSnack } = deps

  const selectedNode = computed((): FeoNode | undefined =>
    props.categoryId != null ? props.nodes.find(n => n.id === props.categoryId) : undefined
  )

  const categoryName = computed((): string => selectedNode.value?.name?.trim() ?? '—')

  const selectedKey = computed((): string | null =>
    props.modelValue ? `${props.modelValue.kind}:${props.modelValue.id}` : null
  )

  // БАГ 1 (сессия 2026-08-05): раньше фильтрация шла обходом props.nodes
  // (collectDescendantIds), а nodes приходит из useFeoLeaves → filterFundedNodes,
  // который ВЫРЕЗАЕТ конечные категории без собственного budget — даже если у них
  // заполнены planned_quantity/planned_amount (плановая позиция). Из-за этого
  // «В этой категории нет плановых позиций» показывалось для категорий, у которых
  // план ЕСТЬ, просто их лист не прошёл фильтр finansирования. Бэкенд
  // GET /feo-categories/plan-positions теперь отдаёт на каждой строке ancestor_ids
  // (id всех предков ДО корня) — матчим напрямую по нему, без обхода дерева.
  const filteredItems = computed((): FeoPlanPosition[] => {
    if (props.categoryId == null) return []
    const cid = props.categoryId
    return props.items.filter(r => r.category_id === cid || (r.ancestor_ids || []).includes(cid))
  })

  // modelValue ссылается на строку, которой больше нет среди актуальных (отфильтрованных
  // по категории/потомкам) items — либо позицию удалили из плана закупок, либо она
  // принадлежит категории вне текущей ветки дерева.
  const ghostRow = computed((): boolean => {
    if (!props.modelValue) return false
    return !filteredItems.value.some(r => r.key === selectedKey.value)
  })

  function fmt(v: number | null | undefined): string {
    if (v == null) return '—'
    return v.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' ₽'
  }

  function fmtNum(v: number | null | undefined): string {
    if (v == null) return '—'
    return v.toLocaleString('ru-RU')
  }

  function fmtQty(row: FeoPlanPosition): string {
    const qty = row.planned_quantity != null ? row.planned_quantity.toLocaleString('ru-RU') : '—'
    return `${qty} ${row.unit || ''}`.trim()
  }

  // «Занято прямо сейчас в этой форме» поверх серверных consumed/residual — см. проп
  // pendingByPlannedItem выше. Только planned_item (row.id живёт в пространстве id
  // FeoPlannedItem у этого kind; у plan_position/feo_article своей плановой позиции нет,
  // поэтому pendingFor для них всегда 0 и consumedFor/residualFor равны серверным числам).
  function pendingFor(row: FeoPlanPosition): number {
    if (row.kind !== 'planned_item') return 0
    return props.pendingByPlannedItem?.[row.id] || 0
  }

  function consumedFor(row: FeoPlanPosition): number {
    return row.consumed + pendingFor(row)
  }

  // Расшифровка «Кто расходует план» — сами позиции ЭТОЙ формы, дающие pendingFor(row)
  // (см. проп pendingItemsByPlannedItem). Тот же guard kind!=='planned_item' → [].
  function pendingItemsFor(row: FeoPlanPosition): PendingItemEntry[] {
    if (row.kind !== 'planned_item') return []
    return props.pendingItemsByPlannedItem?.[row.id] || []
  }

  function residualFor(row: FeoPlanPosition): number {
    // row.residual с сервера уже = planned_amount − consumed (backend/app/routers/
    // feo_categories.py::spendable_remaining, без клампинга) — вычитаем pendingFor
    // отдельно, а не пересчитываем через planned_amount (может быть null у legacy строк).
    return row.residual - pendingFor(row)
  }

  // Единый источник числа И цвета для «остаток/превышение» строки (владелец,
  // сессия 2026-08-21: «Подсвечено должно быть везде такое несоответствие» —
  // раньше класс .feo-planned-shortfall вешался по isShort()/props.amount (другому
  // условию — «войдёт ли ЭТА сумма»), а число печаталось из residualFor(row)
  // (или вовсе сырого row.residual в развёрнутом списке) — при отрицательном
  // остатке цвет мог не загореться. formatPlanResidual берёт residualFor(row)
  // ОДИН раз и производит из него и текст, и класс — расхождение больше невозможно.
  function planResidualDisplay(row: FeoPlanPosition) {
    return formatPlanResidual(residualFor(row))
  }

  function shortfall(row: FeoPlanPosition): number {
    if (props.amount == null) return 0
    // Строка row уже выбрана (selectedKey === row.key) — её собственная сумма (props.amount,
    // сумма ЭТОЙ редактируемой позиции) уже учтена в consumedFor(row) через
    // pendingByPlannedItem (карта считается по ВСЕЙ форме, включая текущую строку). Добавлять
    // props.amount поверх ещё раз значило бы посчитать одну и ту же сумму дважды. Для остальных
    // (пока не выбранных) строк props.amount — гипотетическая проверка «войдёт ли эта сумма,
    // если переключить сюда».
    const alreadySelected = selectedKey.value === row.key
    return residualFor(row) - (alreadySelected ? 0 : props.amount)
  }

  function isShort(row: FeoPlanPosition): boolean {
    return props.amount != null && shortfall(row) < 0
  }

  function kindChipColor(kind: FeoPlanKind): string { return KIND_CHIP_COLOR[kind] }
  function kindChipLabel(kind: FeoPlanKind): string { return KIND_CHIP_LABEL[kind] }

  /** Строит набор подписей для одной строки — единая точка для dense-меню и
   *  развёрнутого списка (оба рендерят FeoPlannedItemRow.vue с этими пропами). */
  function rowDisplayProps(row: FeoPlanPosition): FeoPlannedRowDisplay {
    return {
      qtyLabel: fmtQty(row),
      plannedLabel: fmt(row.planned_amount),
      consumedLabel: fmt(consumedFor(row)),
      residualDisplay: planResidualDisplay(row),
      shortfallLabel: isShort(row) ? fmt(Math.abs(shortfall(row))) : null,
    }
  }

  // Разбито на структурированный computed (было — готовая строка denseSummaryLabel)
  // специально ради подсветки: шаблону нужен отдельный элемент для «остаток/
  // превышение», чтобы повесить на него planResidualDisplay(row).cssClass.
  const denseSummaryRow = computed((): FeoPlanPosition | undefined =>
    selectedKey.value != null ? filteredItems.value.find(r => r.key === selectedKey.value) : undefined
  )
  const denseResidualDisplay = computed(() =>
    denseSummaryRow.value ? planResidualDisplay(denseSummaryRow.value) : null
  )

  function selectItem(row: FeoPlanPosition) {
    if (props.readonly) return
    emit('update:modelValue', { kind: row.kind, id: row.id })
  }

  // БАГ 2 (сессия 2026-08-05, добор 2026-08-05): изначально <input type="radio"> лежал
  // ВНУТРИ <label class="feo-tree-row">, а обработчик висел на самом <input>. Клик по
  // <label> браузер сам транслирует во ВТОРОЙ синтетический клик по вложенному <input> —
  // onItemRadioClick срабатывал дважды за один клик пользователя: первый раз выбирал
  // строку, второй тут же видел selectedKey === row.key и снимал выбор. Внешне — «клик
  // ничего не делает». Исправлено: обёртка теперь <div role="switch">, обработчик висит
  // на самом div (ровно один клик = ровно один вызов). Индикатор выбора (сессия
  // 2026-08-06, владелец: «точка выбора не садится на позицию — сделай переключатель»)
  // заменён с input[type=radio] на <v-switch> — чисто визуальный, pointer-events:none
  // в CSS, своих событий не порождает. Источник правды — Vue-состояние (props.modelValue),
  // а не DOM-состояние переключателя. Доступность: role="switch" + aria-checked + tabindex
  // + Enter/Space.
  function onItemRadioClick(row: FeoPlanPosition, event?: Event) {
    if (props.readonly) return
    event?.preventDefault()
    if (selectedKey.value === row.key) {
      emit('update:modelValue', null)
    } else {
      selectItem(row)
    }
  }

  function detachGhost() {
    if (props.readonly) return
    emit('update:modelValue', null)
  }

  // Жалоба владельца (сессия 2026-08-19): «Я не увидел здесь возможности удалять ненужные
  // плановые позиции... где эта корзиночка?» — DELETE /feo-planned-items/{id}, с
  // purchase_id ТЕКУЩЕЙ закупки (props.purchaseId) и/или wish_id ТЕКУЩЕЙ заявки
  // (props.wishId, дефект 2, владелец 2026-08-20 — «случайно создали плановую позицию
  // неправильно, надо удалить» ПРЯМО ИЗ ФОРМЫ ЗАЯВКИ, ещё до появления закупки), если они
  // известны: бэкенд снимает «свои» ссылки (эта закупка + заявка, которая её породила,
  // и/или сама эта заявка) молча, а если позицию держит ЧУЖАЯ закупка/заявка — отвечает
  // 409 со списком держателей и ничего не меняет (см.
  // backend/app/routers/feo_planned_items.py::delete_planned_item). Формулировка
  // подтверждения — по образцу deleteHeadPlannedItem в CreateOrderView.vue (та же
  // корзинка, но в ШАПКЕ карточки, коммит 5901986), дополнена количеством (дефект 2, п.в:
  // называть позицию по имени/кол-ву/сумме, не по id). Кнопка есть только у
  // kind==='planned_item' — строки уровня категории (plan_position/feo_article) это сама
  // категория ФЭО дерева, их «удаление» другое, куда более опасное действие.
  async function deletePlannedItem(row: FeoPlanPosition) {
    if (props.readonly || row.kind !== 'planned_item') return
    const msg = `Удалить плановую позицию «${row.name}»? Кол-во ${fmtQty(row)}, ` +
      `план ${fmt(row.planned_amount)}, сейчас выбрано ${fmt(consumedFor(row))}.`
    if (!confirm(msg)) return
    try {
      const qsParts: string[] = []
      if (props.purchaseId != null) qsParts.push(`purchase_id=${props.purchaseId}`)
      if (props.wishId != null) qsParts.push(`wish_id=${props.wishId}`)
      const qs = qsParts.length ? `?${qsParts.join('&')}` : ''
      await apiFetch(`/feo-planned-items/${row.id}${qs}`, { method: 'DELETE', suppressErrorDialog: true })
      // Удалённая позиция была выбрана в этой строке — снять выбор, чтобы не остался
      // «призрак» (см. ghostRow computed выше — он и без этого поймал бы несоответствие,
      // но снимаем явно, не дожидаясь перезагрузки родителем).
      if (selectedKey.value === row.key) {
        emit('update:modelValue', null)
      }
      emit('planned-item-deleted')
      showSnack('Плановая позиция удалена')
    } catch (e: any) {
      showSnack(e?.payload?.message ?? e?.detail ?? e?.message ?? 'Не удалось удалить плановую позицию', 'error')
    }
  }

  return {
    selectedNode, categoryName, selectedKey, filteredItems, ghostRow,
    fmt, fmtNum, fmtQty, pendingFor, consumedFor, pendingItemsFor, residualFor,
    planResidualDisplay, shortfall, isShort, kindChipColor, kindChipLabel, rowDisplayProps,
    denseSummaryRow, denseResidualDisplay, selectItem, onItemRadioClick, detachGhost,
    deletePlannedItem,
  }
}

export type UseFeoPlannedRows = ReturnType<typeof useFeoPlannedRows>
