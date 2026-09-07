// useItemsFeo — per-item ФЭО/план хелперы: категория «Не определена» на лету
// (pickUnallocatedForItem/_injectUnallocatedNode), мультивыбор-пропагация
// изменений ФЭО/тип/план на выделенные строки (_propagateToSelected,
// onItemFeoChange/onItemPlannedChange/onItemTypeChange), производный выбор
// для FeoPlannedItemsSelect (plannedSelectionFor), карты «занято сейчас в этой
// форме» (pendingByPlannedItem/pendingItemsByPlannedItem), агрегат плана по
// категории для мигрированных категорий-листьев (plannedAggregateForCategory),
// «остаток на статье» (categoryResidualFor) и фронт-зеркало backend-гейта
// «ТЗ не дороже и не больше плана» (planForItem/planExcessFor). Extracted from
// PurchaseItemsEditor.vue (monolith refactor, часть 3).
import { computed, type ComputedRef, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { FeoNode, FeoLeaf } from '@/composables/useFeoLeaves'
import type { FeoPlanPosition, FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'
import type { ToastType } from '@/composables/useToast'

// EditorItem is structurally identical to the parent's; kept loose here (same
// convention as ItemsTableFlat.vue) since the parent owns the real shape and
// this composable only reads/writes the FEO/plan-related fields it uses.
type EditorItem = any

// Владелец (2026-08-26): «Остаток на статье» под суммой позиции — см. подробный
// комментарий у categoryResidualFor ниже.
export interface CategoryResidualInfo {
  /** true — у текущего пользователя есть feo_budget.view_leaf, ниже заполнены
   *  «занято»/финансирование/остаток. false — их НЕЛЬЗЯ показывать (владелец,
   *  2026-09-03: «обычному пользователю не надо знать, сколько денег осталось в
   *  организации»); заполнено только excessAmount, из него одного бюджет не
   *  вычислить. */
  canViewBudget: boolean
  /** «Занято по статье» (владелец, сессия 2026-08-31) = Σ planned_amount плановых
   *  позиций статьи + unlinkedActual (см. ниже). Раньше — только плановые позиции;
   *  переименовано вслед за подписью «Уже запланировано по статье» → «Занято по статье»,
   *  т.к. теперь включает и непривязанные фактические позиции. null, если canViewBudget=false. */
  alreadyPlanned: number | null
  /** Из alreadyPlanned выше — часть, НЕ привязанная ни к одной плановой позиции
   *  (backend unlinked_actual_amount: позиции закупок статьи с feo_planned_item_id
   *  IS NULL, из плана закупок и дальше). Показывается отдельной строкой, только
   *  когда > 0 — владелец: «на это необходимо указывать» (стоит привязать к плану).
   *  null, если canViewBudget=false. */
  unlinkedActual: number | null
  /** FeoCategory.budget («финансирование по ФЭО») либо null, если для категории его
   *  нет ИЛИ canViewBudget=false. */
  feoBudget: number | null
  /** feoBudget − alreadyPlanned, либо null если feoBudget неизвестен. */
  residualBeforeItem: number | null
  /** feoBudget − alreadyPlanned − сумма ЭТОЙ позиции, либо null если feoBudget неизвестен. */
  residualWithItem: number | null
  /** true — у позиции уже введена (посчитана) ненулевая сумма. */
  hasItemTotal: boolean
  /** Размер превышения СТАТЬИ ЭТОЙ КОНКРЕТНОЙ ПОЗИЦИЕЙ (не состояние статьи целиком!) —
   *  заполнен ТОЛЬКО когда canViewBudget=false. См. полный комментарий в исходном
   *  месте (git history PurchaseItemsEditor.vue) — источник: props.feoExcessAmount/
   *  feoExcessCategoryId, клипуется суммой позиции. */
  excessAmount: number | null
}

export interface TzPlanExcess {
  plan: FeoPlanPosition
  qtyOver: boolean
  priceOver: boolean
  totalOver: boolean
}

export interface UseItemsFeoDeps {
  props: {
    subsidyId?: number | null
    plannedItems?: FeoPlanPosition[]
    feoExcessAmount?: number | null
    feoExcessCategoryId?: number | null
  }
  localItems: Ref<EditorItem[]>
  selectedItemIdxs: Ref<number[]>
  feoNodes: Ref<FeoNode[]>
  feoLeaves: Ref<FeoLeaf[]>
  canViewLeafBudget: ComputedRef<boolean>
  emitUpdate: () => void
  showSnack: (text: string, color?: ToastType, opts?: { actionText?: string; onAction?: () => void; duration?: number }) => void
}

export function useItemsFeo(deps: UseItemsFeoDeps) {
  const { props, localItems, selectedItemIdxs, feoNodes, feoLeaves, canViewLeafBudget, emitUpdate, showSnack } = deps

  async function pickUnallocatedForItem(idx: number, parentId: number | null) {
    if (!props.subsidyId) return
    try {
      const body: Record<string, unknown> = { subsidy_id: props.subsidyId }
      if (parentId != null) body.parent_id = parentId
      const cat = await apiFetch<{ id: number; name: string; parent_id: number | null }>('/feo-categories/unallocated', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      _injectUnallocatedNode(cat)
      _propagateToSelected(idx, it => {
        it.feo_node_id = cat.id
        it.feo_category_id = cat.id
      })
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Ошибка получения категории «Не определена»', 'error')
    }
  }

  /**
   * Добавляет новый узел «Не определена» в feoNodes, если его там ещё нет.
   * Если у узла есть parent_id — помечает родителя not-leaf (у него появился ребёнок).
   */
  function _injectUnallocatedNode(cat: { id: number; name: string; parent_id?: number | null }) {
    const existing = feoNodes.value.find(n => n.id === cat.id)
    if (!existing) {
      const parentNode = cat.parent_id != null ? feoNodes.value.find(n => n.id === cat.parent_id) : null
      const newNode = { id: cat.id, name: cat.name, parent_id: cat.parent_id ?? null, level: parentNode ? parentNode.level + 1 : 1, is_leaf: true } as any
      const updated = [...feoNodes.value, newNode]
      // Если у нового узла есть родитель — снимаем с него is_leaf
      if (cat.parent_id != null) {
        const parentIdx = updated.findIndex(n => n.id === cat.parent_id)
        if (parentIdx !== -1) updated[parentIdx] = { ...updated[parentIdx], is_leaf: false }
      }
      feoNodes.value = updated
    }
  }

  // Inline-пропагация на выбранные: при мультивыборе изменение ФЭО/Тип в одной
  // позиции применяется ко всем выбранным. Если строка не входит в выделение
  // (или выделена одна) — меняется только она.
  function _propagateToSelected(idx: number, apply: (it: any) => void) {
    const sel = selectedItemIdxs.value
    const targets = sel.length > 1 && sel.includes(idx) ? sel : [idx]
    for (const i of targets) {
      const it = localItems.value[i]
      if (it) apply(it)
    }
    emitUpdate()
  }

  function onItemFeoChange(idx: number, nodeId: number | null) {
    // FeoCascadeSelect эмитит выбранный УЗЕЛ на каждом уровне (а не только лист).
    // feo_node_id — позиция каскада (любой узел); пропагируем её на все выбранные
    // строки, чтобы смена ЛЮБОГО уровня в одной позиции отражалась во всех сразу.
    // feo_category_id (сохраняемый лист) выставляем только когда узел — лист.
    const isLeaf = nodeId != null && (feoNodes.value.find(n => n.id === nodeId)?.is_leaf ?? false)
    const newCategoryId = isLeaf ? nodeId : null
    _propagateToSelected(idx, it => {
      // F-PLAN: смена категории ФЭО делает привязанную плановую позицию (Ур.5)
      // невалидной — она принадлежит другой категории и «расходовала» бы её план.
      // Сбрасываем feo_planned_item_id, если он ссылается на позицию из старой категории.
      // ⚠️ id-коллизия: feo_planned_item_id живёт в пространстве id FeoPlannedItem —
      // сравнивать только со строками kind='planned_item', иначе можно случайно
      // «попасть» в id категории (kind='plan_position'/'feo_article') с тем же числом.
      if (it.feo_planned_item_id != null) {
        const plannedCategoryId = (props.plannedItems || [])
          .find(p => p.kind === 'planned_item' && p.id === it.feo_planned_item_id)?.category_id
        if (plannedCategoryId !== newCategoryId) it.feo_planned_item_id = null
      }
      it.feo_node_id = nodeId
      it.feo_category_id = newCategoryId
    })
  }

  // F-PLAN2: производный выбор для FeoPlannedItemsSelect по фактическим полям позиции —
  // { kind:'planned_item', id: feo_planned_item_id } если задан; иначе, если категория
  // позиции сама является плановой позицией/статьёй ФЭО с планом (kind='plan_position'
  // | 'feo_article'), — её собственный ключ; иначе null.
  function plannedSelectionFor(item: EditorItem): FeoPlanSelection | null {
    if (item.feo_planned_item_id != null) return { kind: 'planned_item', id: item.feo_planned_item_id }
    if (item.feo_category_id != null) {
      const row = (props.plannedItems || [])
        .find(p => p.category_id === item.feo_category_id && (p.kind === 'plan_position' || p.kind === 'feo_article'))
      if (row) return { kind: row.kind, id: item.feo_category_id }
    }
    return null
  }

  // Жалоба владельца (сессия 2026-08-19): «включаю переключатель — должно стать выбрано
  // 1 500, остаток 0... а сейчас включаю-выключаю, там по-прежнему план 1 500, выбрано 0».
  // row.consumed/row.residual в FeoPlanPosition приходят С СЕРВЕРА
  // (/feo-categories/plan-positions, exclude_purchase_id — своя закупка НЕ учтена, это
  // осознанно и трогать НЕЛЬЗЯ, см. комментарий в useFeoPlannedResiduals.ts), но выбор,
  // сделанный ПРЯМО СЕЙЧАС в этой форме (переключатель включён/выключен на строке),
  // в них не отражён вовсе — карта ниже суммирует «занято сейчас в этой форме» по
  // каждой плановой позиции и передаётся в FeoPlannedItemsSelect (проп
  // pendingByPlannedItem), который добавляет её поверх серверных чисел. Строки с
  // over_plan===true НЕ считаем — они сознательно сверх плана и не расходуют его (тот
  // же признак, что и в pendingByPlannedItem-соседях: plannedSelectionFor/EditorItem.
  // over_plan). Сумма строки — total_price, тот же источник, что и totalNmck/прочие
  // суммы в этом файле. Реактивность: computed от localItems — переключение
  // switch(row) меняет it.feo_planned_item_id внутри localItems, карта пересчитывается сама.
  const pendingByPlannedItem = computed((): Record<number, number> => {
    const map: Record<number, number> = {}
    for (const it of localItems.value) {
      const pid = (it as any).feo_planned_item_id
      if (pid == null) continue
      if ((it as any).over_plan === true) continue
      map[pid] = (map[pid] || 0) + Number((it as any).total_price || 0)
    }
    return map
  })

  // Расшифровка «Кто расходует план» (владелец, 2026-08-20): диалог
  // FeoPlannedItemsSelect.vue::openConsumers должен показать, ЧТО именно даёт число
  // pendingByPlannedItem, а не только саму сумму — иначе «выбрано Y» в строке списка
  // нечем объяснить (боевой случай: 14 футболок, план 15 793,40, «выбрано 11 281» —
  // потому что на ту же плановую позицию ссылается ЕЩЁ ОДНА строка ЭТОЙ ЖЕ формы на
  // 10 шт, ещё не сохранённая на сервер). Та же фильтрация (pid != null, !over_plan),
  // но список позиций {name, quantity, unit, amount} вместо суммы.
  const pendingItemsByPlannedItem = computed((): Record<number, { name: string; quantity: number | null; unit: string | null; amount: number }[]> => {
    const map: Record<number, { name: string; quantity: number | null; unit: string | null; amount: number }[]> = {}
    for (const it of localItems.value) {
      const pid = (it as any).feo_planned_item_id
      if (pid == null) continue
      if ((it as any).over_plan === true) continue
      if (!map[pid]) map[pid] = []
      map[pid].push({
        name: (it as any).item_name || 'без названия',
        quantity: (it as any).quantity ?? null,
        unit: (it as any).unit ?? null,
        amount: Number((it as any).total_price || 0),
      })
    }
    return map
  })

  // Шаг 5 «ТЗ не дороже и не больше плана» (владелец, 2026-08-07, план
  // zany-fluttering-mountain.md): фронт-зеркало backend-гейта
  // assert_tz_not_over_plan (app/services/feo_plan.py) — подсвечивает
  // превышение ДО отправки, чтобы 409 не был первым, что видит пользователь.
  // Источник плана — та же строка, что выбрана для FeoPlannedItemsSelect
  // (plannedSelectionFor): planned_quantity / unit_price (цена за единицу) /
  // planned_amount (итоговая плановая сумма) — те же поля, что читает бэкенд
  // из FeoPlannedItem.quantity/amount либо FeoCategory.planned_quantity/
  // planned_amount (см. FeoPlanPosition в useFeoPlannedResiduals.ts).
  // Фолбэк для МИГРИРОВАННЫХ категорий-листьев (2026-08-12, зеркалит backend-фолбэк
  // в assert_tz_not_over_plan / app/services/feo_plan.py): план переехал из
  // planned_quantity/planned_amount самой категории в отдельные плановые позиции
  // (kind='planned_item') внутри неё. У такой категории оба поля плана категории
  // = null, поэтому /feo-categories/plan-positions НЕ эмитит для неё строку
  // 'plan_position'/'feo_article', plannedSelectionFor(item) возвращает null
  // (строки для выбора нет), и без этого фолбэка planForItem/planExcessFor тоже
  // всегда возвращали null — предупреждение «ТЗ превышает план» тихо переставало
  // работать. Складываем ровно те поля, которые читает planExcessFor
  // (planned_quantity / unit_price / planned_amount) плюс остальные, требуемые
  // типом FeoPlanPosition, из активных 'planned_item' той же категории: сумма
  // плана Σ planned_amount, количество Σ planned_quantity, цена за единицу =
  // сумма/количество при количестве > 0.
  function plannedAggregateForCategory(categoryId: number): FeoPlanPosition | null {
    const rows = (props.plannedItems || []).filter(
      p => p.kind === 'planned_item' && p.category_id === categoryId
    )
    if (!rows.length) return null
    const plannedAmount = rows.reduce((s, r) => s + (r.planned_amount ?? 0), 0)
    const consumed = rows.reduce((s, r) => s + (r.consumed ?? 0), 0)
    const consumedQty = rows.reduce((s, r) => s + (r.consumed_quantity ?? 0), 0)
    const residual = rows.reduce((s, r) => s + (r.residual ?? 0), 0)
    const residualQty = rows.reduce((s, r) => s + (r.residual_quantity ?? 0), 0)
    return {
      id: categoryId,
      name: rows[0].name,
      path: rows[0].path,
      category_id: categoryId,
      kind: 'plan_position',
      // Владелец (2026-08-26, заявка №45/Минтруд_2026): этот агрегат складывает
      // НЕСВЯЗАННЫЕ FeoPlannedItem внутри статьи (разные товары/цены/единицы) —
      // planned_quantity/unit_price делением суммы на суммарное количество были бы
      // ВЫДУМАННОЙ величиной. planned_amount — РЕАЛЬНАЯ сумма (Σ planned_amount уже
      // существующих плановых позиций статьи), её оставляем и подписываем «Уже
      // запланировано по статье» (см. categoryResidualFor ниже). planned_quantity/
      // unit_price = null убирают выдуманные подписи «план: N шт»/«план: N ₽» под
      // количеством/ценой ЭТОГО фолбэка (guard `!= null` в шаблонах таблиц) — то, что
      // не задано по-настоящему, не показываем.
      planned_quantity: null,
      unit: rows[0].unit,
      planned_amount: plannedAmount,
      unit_price: null,
      consumed,
      consumed_quantity: consumedQty,
      residual,
      residual_quantity: residualQty,
      key: `plan_position:${categoryId}`,
    }
  }

  // Владелец (2026-08-26): «Остаток на статье» под суммой позиции — ТОЛЬКО когда
  // planForItem вернулся из фолбэка plannedAggregateForCategory (нет ни конкретной
  // выбранной плановой позиции, ни собственной строки категории 'plan_position'/
  // 'feo_article' с сервера — см. planForItem выше). Для настоящей плановой позиции
  // (kind='planned_item' выбран построчно) старые подписи/проверка превышения не
  // трогаются (регресс запрещён владельцем).
  //
  // «Финансирование по ФЭО» статьи — поле FeoCategory.budget, уже загруженное для
  // формы через useFeoLeaves (feoLeaves, GET /feo-categories/leaves, budget =
  // «собственная (ручная) сумма финансирования узла», единственное доступное на
  // клиенте число для этого понятия — ответ /feo-categories/plan-positions его не
  // отдаёт вовсе). Если категория не входит в feoLeaves (например, план стоит не
  // на листе, а на направлении/подкатегории) — feoBudget = null, остаток статьи не
  // считаем (не выдумываем число).
  function categoryResidualFor(item: EditorItem): CategoryResidualInfo | null {
    if (item.feo_planned_item_id != null) return null
    if (item.feo_category_id == null) return null
    const sel = plannedSelectionFor(item)
    if (sel) {
      const row = (props.plannedItems || []).find(p => p.key === `${sel.kind}:${sel.id}`)
      if (row) return null // настоящая строка категории 'plan_position'/'feo_article' с сервера — старые подписи
    }
    const agg = plannedAggregateForCategory(item.feo_category_id)
    if (!agg) return null
    const itemTotal = Number(item.total_price) || 0
    const hasItemTotal = itemTotal > 0

    if (!canViewLeafBudget.value) {
      // Владелец (2026-09-03, повторно): без feo_budget.view_leaf нельзя показывать
      // ни «занято», ни состояние статьи целиком — ТОЛЬКО то, на сколько СВОЯ сумма
      // ЭТОЙ позиции не поместилась в статью. Сырой перебор статьи (props.feoExcessAmount,
      // из независимого от права канала — см. CategoryResidualInfo.excessAmount выше)
      // клипуется суммой позиции: min(itemTotal, rawExcess). Пустая позиция (сумма
      // 0) строки не даёт вовсе.
      const rawExcess =
        props.feoExcessCategoryId != null && props.feoExcessCategoryId === item.feo_category_id
          ? props.feoExcessAmount ?? null
          : null
      const excessAmount =
        rawExcess != null && rawExcess > 0.005 && hasItemTotal ? Math.min(itemTotal, rawExcess) : null
      if (excessAmount == null || excessAmount <= 0.005) return null
      return {
        canViewBudget: false,
        alreadyPlanned: null,
        unlinkedActual: null,
        feoBudget: null,
        residualBeforeItem: null,
        residualWithItem: null,
        hasItemTotal,
        excessAmount,
      }
    }

    // unlinked_actual_amount — свойство КАТЕГОРИИ целиком (не отдельной плановой позиции),
    // бэкенд повторяет одно и то же число на каждой строке /plan-positions этой категории —
    // берём с любой одной строки (первая, попавшаяся в agg.category_id), а НЕ суммируем по
    // всем 'planned_item' строкам категории (иначе задвоили бы его столько раз, сколько
    // плановых позиций в статье — см. комментарий у поля в useFeoPlannedResiduals.ts).
    const unlinkedRow = (props.plannedItems || []).find(p => p.category_id === item.feo_category_id)
    const unlinkedActual = unlinkedRow?.unlinked_actual_amount ?? 0
    const alreadyPlanned = (agg.planned_amount ?? 0) + unlinkedActual
    const feoBudget = feoLeaves.value.find(l => l.id === item.feo_category_id)?.budget ?? null
    const residualBeforeItem = feoBudget != null ? feoBudget - alreadyPlanned : null
    const residualWithItem = residualBeforeItem != null ? residualBeforeItem - itemTotal : null
    return {
      canViewBudget: true,
      alreadyPlanned, unlinkedActual, feoBudget, residualBeforeItem, residualWithItem,
      hasItemTotal, excessAmount: null,
    }
  }

  function planForItem(item: EditorItem): FeoPlanPosition | null {
    const sel = plannedSelectionFor(item)
    if (sel) {
      const row = (props.plannedItems || []).find(p => p.key === `${sel.kind}:${sel.id}`)
      if (row) return row
    }
    // sel === null (нет агрегатной строки категории) ИЛИ позиция не привязана к
    // конкретной plannedItem (feo_planned_item_id не задан) — пробуем агрегат
    // по 'planned_item' той же категории (см. plannedAggregateForCategory выше).
    if (item.feo_planned_item_id == null && item.feo_category_id != null) {
      return plannedAggregateForCategory(item.feo_category_id)
    }
    return null
  }

  function planExcessFor(item: EditorItem): TzPlanExcess | null {
    // over_plan=true — позиция сознательно сверх плана (согласуется отдельно,
    // через превышение ФЭО категории) — не подсвечиваем как нарушение.
    if (item.over_plan) return null
    const plan = planForItem(item)
    if (!plan) return null
    const qty = Number(item.quantity) || 0
    const price = Number(item.unit_price) || 0
    const total = item.total_price != null ? Number(item.total_price) : qty * price
    // Владелец (2026-09-02, «Логистические услуги»): для kind='planned_item' без
    // unit_price количество ОРИЕНТИРОВОЧНОЕ и НЕ ограничивает закупку (см.
    // assert_tz_not_over_plan / feo_plan.py — planned_qty там сознательно остаётся
    // None в этой ветке). У 'plan_position'/'feo_article' (FeoCategory) такой
    // семантики нет — там planned_quantity всегда жёсткий предел. Без этого условия
    // фронт подсвечивал бы «превышение по количеству», которого бэкенд не блокирует —
    // тот же класс бага, что был с ценой за единицу.
    const qtyLimited = plan.kind !== 'planned_item' || plan.unit_price != null
    const qtyOver = qtyLimited && plan.planned_quantity != null && qty > plan.planned_quantity
    const priceOver = plan.unit_price != null && price > plan.unit_price
    const totalOver = plan.planned_amount != null && total > plan.planned_amount
    if (!qtyOver && !priceOver && !totalOver) return null
    return { plan, qtyOver, priceOver, totalOver }
  }

  function onItemPlannedChange(idx: number, val: FeoPlanSelection | null) {
    _propagateToSelected(idx, it => {
      if (!val) {
        it.feo_planned_item_id = null
        return
      }
      if (val.kind === 'planned_item') {
        it.feo_planned_item_id = val.id
        it.over_plan = false
      } else {
        it.feo_planned_item_id = null
        it.feo_category_id = val.id
        it.over_plan = false
      }
    })
  }

  function onItemTypeChange(idx: number, val: string) {
    _propagateToSelected(idx, it => { it.item_type = val })
  }

  return {
    pickUnallocatedForItem, _injectUnallocatedNode, _propagateToSelected,
    onItemFeoChange, plannedSelectionFor, pendingByPlannedItem, pendingItemsByPlannedItem,
    plannedAggregateForCategory, categoryResidualFor, planForItem, planExcessFor,
    onItemPlannedChange, onItemTypeChange,
  }
}
