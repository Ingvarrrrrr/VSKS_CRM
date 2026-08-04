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
// - contracts считается по Contract.max_amount, но договор попадает в сумму, только если у него
//   есть привязанная закупка в статусе из KPI_CONTRACTS_STATUSES (backend/app/routers/dashboard.py:356-382,
//   единое правило для single/framework_with_amount/framework_cumulative) — закупки в «Желаниях»,
//   плане или вообще без договора в сумму не входят;
// - work/ordered/delivered/delivered_unpaid/paid считаются по позициям закупок в определённых
//   статусах — заявки в статусе «Желания» (wishes) в PLANNED_STATUSES не входят и не учитываются;
// - plan_schedule/budget/free — 0 совпадений означает, что в дереве действительно пусто/сошлось.
export const KPI_EMPTY_REASONS: Record<KpiKey, string> = {
  budget: 'ни одной категории с заданным финансированием ФЭО',
  plan_schedule: 'нет ни ручных плановых позиций, ни позиций из заявок',
  work: 'нет закупок в этих статусах, привязанных к категориям ФЭО (заявки в статусе «Желания» сюда не входят)',
  ordered: 'нет закупок в этих статусах, привязанных к категориям ФЭО (заявки в статусе «Желания» сюда не входят)',
  contracts: 'нет активных договоров с закупкой, дошедшей до стадии «Договор заключён» (contracted/ordered/delivered/paid)',
  delivered: 'нет закупок в этих статусах, привязанных к категориям ФЭО (заявки в статусе «Желания» сюда не входят)',
  delivered_unpaid: 'нет закупок в этих статусах, привязанных к категориям ФЭО (заявки в статусе «Желания» сюда не входят)',
  paid: 'нет закупок в этих статусах, привязанных к категориям ФЭО (заявки в статусе «Желания» сюда не входят)',
  free: 'остаток распределён точно по лимитам — расхождений нет',
}

export const KPI_WORK_STATUSES = ['work_in_progress', 'contracted', 'ordered', 'delivered', 'paid']
export const KPI_ORDERED_STATUSES = ['contracted', 'delivered', 'paid']
export const KPI_CONTRACTS_STATUSES = ['contracted', 'ordered', 'delivered', 'paid']
export const KPI_DELIVERED_STATUSES = ['delivered', 'paid']

// Состав метрики сверен с backend/app/routers/dashboard.py — не менять «по здравому смыслу»
export function kpiItemMatches(key: KpiKey, item: KpiMatchableItem): boolean {
  switch (key) {
    case 'plan_schedule':     return true
    case 'work':              return KPI_WORK_STATUSES.includes(item.purchase_status)
    case 'ordered':           return KPI_ORDERED_STATUSES.includes(item.purchase_status) && !!item.purchase_contract_type
    case 'contracts':
      // Единое правило для всех типов договора: договор привязан, активен, и хотя бы одна
      // его закупка дошла до стадии «Договор заключён» (dashboard.py:356-382 — EXISTS-проверка
      // для single/framework_with_amount, JOIN+фильтр статуса для framework_cumulative).
      if (item.contract_id == null || item.contract_status !== 'active') return false
      return KPI_CONTRACTS_STATUSES.includes(item.purchase_status)
    case 'delivered':         return KPI_DELIVERED_STATUSES.includes(item.purchase_status)
    case 'delivered_unpaid':  return item.purchase_status === 'delivered'
    case 'paid':              return item.purchase_status === 'paid'
    default:                  return false
  }
}
