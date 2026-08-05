// ── KPI drill-down: клик по карточке подсвечивает в дереве ФЭО состав суммы ──────
// Вынесено из SubsidiesView.vue, чтобы логику можно было покрыть тестом на паритет
// с backend/app/routers/dashboard.py (см. frontend/src/constants/__tests__/kpiMetrics.spec.ts).

// Минимальный интерфейс входа — структурно совместим с FeoReqItem из SubsidiesView.vue.
export interface KpiMatchableItem {
  purchase_status: string
  purchase_contract_type?: string | null
  contract_id?: number | null
  contract_status?: string | null
  contract_type?: string | null
  // Anti-doublecount (задвоение плана ФЭО): позиция привязана к плановой позиции
  // (feo_planned_items) — расходует её план, а не складывается с ним поверх. Влияет
  // только на 'plan_schedule' — «Запланировано» должно совпадать 1:1 с деревом ФЭО,
  // где такие позиции уже исключены (см. backend/app/routers/subsidies.py
  // _calculate_feo_planned_tree_bulk).
  feo_planned_item_id?: number | null
}

export type KpiKey = 'budget' | 'plan_schedule' | 'work' | 'ordered' | 'contracts'
  | 'delivered' | 'delivered_unpaid' | 'paid' | 'free'

// budget/free считаются по узлам дерева (feo_categories.budget / feoFinDiff);
// work/ordered/contracts/delivered/delivered_unpaid/paid — по позициям закупок «из заявок» (plannedItemsByCat);
// plan_schedule — 'mixed': сумма карточки складывается ИЗ ОБОИХ источников (ручные листья ФЭО + позиции заявок),
// поэтому подсветка обязана покрывать и узлы (isManualPosLeaf), и позиции (plannedItemsByCat) одновременно
export const KPI_MODE: Record<KpiKey, 'items' | 'nodes' | 'mixed'> = {
  budget: 'nodes', plan_schedule: 'mixed', work: 'items', ordered: 'items',
  contracts: 'items', delivered: 'items', delivered_unpaid: 'items', paid: 'items', free: 'nodes',
}

export const KPI_LABELS: Record<KpiKey, string> = {
  budget: 'Бюджет (ФЭО)', plan_schedule: 'Запланировано', work: 'Ведётся работа',
  ordered: 'Заказано', contracts: 'Заключено договоров', delivered: 'Поставлено',
  delivered_unpaid: 'Поставлено, не оплачено', paid: 'Оплачено', free: 'Свободно / Превышение',
}

// Пояснение для баннера, когда у активной метрики 0 совпадений в дереве ФЭО (kpiHasMatches === false).
// Причины разные по метрикам — нельзя писать один универсальный текст:
// - contracts считается по Contract.max_amount, но правило РАЗНОЕ по типу договора
//   (backend/app/routers/dashboard.py:370-401, правка 2026-08-04): single требует привязанную
//   закупку в статусе из KPI_CONTRACTS_STATUSES; framework_with_amount считается БЕЗУСЛОВНО при
//   status='active' — рамочный договор с суммой подписывается заранее, закупки по нему делаются
//   позже, поэтому в дереве позиций закупок ему может быть НЕЧЕМ подсветиться (0 совпадений
//   в дереве — это нормально для framework_with_amount без единой закупки, при этом сумма в
//   виджете «Заключено договоров» ненулевая); framework_cumulative считается по закупкам —
//   заявки в «Желаниях», плане или вообще без договора в сумму не входят;
// - work/ordered/delivered/delivered_unpaid/paid считаются по позициям закупок в определённых
//   статусах — заявки в статусе «Желания» (wishes) в PLANNED_STATUSES не входят и не учитываются;
// - plan_schedule/budget/free — 0 совпадений означает, что в дереве действительно пусто/сошлось.
export const KPI_EMPTY_REASONS: Record<KpiKey, string> = {
  budget: 'ни одной категории с заданным финансированием ФЭО',
  plan_schedule: 'нет ни ручных плановых позиций, ни позиций из заявок',
  work: 'нет закупок в этих статусах, привязанных к категориям ФЭО (заявки в статусе «Желания» сюда не входят)',
  ordered: 'нет закупок в этих статусах, привязанных к категориям ФЭО (заявки в статусе «Желания» сюда не входят)',
  contracts: 'нет активных договоров с закупкой, дошедшей до стадии «Договор заключён» (contracted/ordered/delivered/paid) — ' +
    'ИСКЛЮЧЕНИЕ: рамочный договор с суммой (framework_with_amount) входит в виджет и без единой закупки, ' +
    'поэтому 0 совпадений в дереве позиций для него не означает 0 в сумме виджета',
  delivered: 'нет закупок в этих статусах, привязанных к категориям ФЭО (заявки в статусе «Желания» сюда не входят)',
  delivered_unpaid: 'нет закупок в этих статусах, привязанных к категориям ФЭО (заявки в статусе «Желания» сюда не входят)',
  paid: 'нет закупок в этих статусах, привязанных к категориям ФЭО (заявки в статусе «Желания» сюда не входят)',
  free: 'остаток распределён точно по лимитам — расхождений нет',
}

export const KPI_WORK_STATUSES = ['work_in_progress', 'contracted', 'ordered', 'delivered', 'paid']
// «Заказано» = реально дошедшие до статуса «Заказано» и дальше (ordered/delivered/paid) —
// НЕ 'contracted' (договор заключён, но ещё не заказано). Правка 2026-08-04: раньше здесь был
// 'contracted' вместо 'ordered' (формула отстала на месяц от появления статуса 'ordered' в системе).
export const KPI_ORDERED_STATUSES = ['ordered', 'delivered', 'paid']
export const KPI_CONTRACTS_STATUSES = ['contracted', 'ordered', 'delivered', 'paid']
export const KPI_DELIVERED_STATUSES = ['delivered', 'paid']

// Состав метрики сверен с backend/app/routers/dashboard.py — не менять «по здравому смыслу»
export function kpiItemMatches(key: KpiKey, item: KpiMatchableItem): boolean {
  switch (key) {
    case 'plan_schedule':     return item.feo_planned_item_id == null
    case 'work':              return KPI_WORK_STATUSES.includes(item.purchase_status)
    // Правка 2026-08-04: purchase_contract_type больше не участвует — total_ordered на бэке
    // считает COALESCE(contract_price, planned_total_price) без ветвления по типу договора
    // (раньше закупки с purchase_contract_type IS NULL тихо выпадали из суммы).
    case 'ordered':           return KPI_ORDERED_STATUSES.includes(item.purchase_status)
    case 'contracts':
      // Предикат для подсветки ПОЗИЦИЙ дерева (применяется только к уже существующим item'ам —
      // для них хотя бы одна закупка есть по определению). Backend-сумма виджета «Заключено
      // договоров» правило имеет РАЗНОЕ по типу договора (dashboard.py:370-401, правка
      // 2026-08-04): single требует EXISTS закупки в «договорном» статусе, framework_with_amount
      // считается безусловно при status='active' (может не иметь ни одной закупки — тогда
      // подсветить в дереве нечем, см. KPI_EMPTY_REASONS.contracts), framework_cumulative —
      // JOIN+фильтр статуса. Здесь же — единый фильтр по статусу для подсветки существующих items.
      if (item.contract_id == null || item.contract_status !== 'active') return false
      return KPI_CONTRACTS_STATUSES.includes(item.purchase_status)
    case 'delivered':         return KPI_DELIVERED_STATUSES.includes(item.purchase_status)
    case 'delivered_unpaid':  return item.purchase_status === 'delivered'
    case 'paid':              return item.purchase_status === 'paid'
    default:                  return false
  }
}
