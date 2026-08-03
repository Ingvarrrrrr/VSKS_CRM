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
// остальные — по позициям закупок «из заявок» (plannedItemsByCat)
export const KPI_MODE: Record<KpiKey, 'items' | 'nodes'> = {
  budget: 'nodes', plan_schedule: 'items', work: 'items', ordered: 'items',
  contracts: 'items', delivered: 'items', delivered_unpaid: 'items', paid: 'items', free: 'nodes',
}

export const KPI_LABELS: Record<KpiKey, string> = {
  budget: 'Бюджет (ФЭО)', plan_schedule: 'Запланировано', work: 'Ведётся работа',
  ordered: 'Заказано', contracts: 'Заключено договоров', delivered: 'Поставлено',
  delivered_unpaid: 'Поставлено, не оплачено', paid: 'Оплачено', free: 'Свободно / Превышение',
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
    case 'contracts': {
      if (item.contract_id == null || item.contract_status !== 'active') return false
      // framework_cumulative: сумма набирается по закупкам, поэтому статус важен (dashboard.py:380-393)
      if (item.contract_type === 'framework_cumulative') {
        return KPI_CONTRACTS_STATUSES.includes(item.purchase_status)
      }
      // single / framework_with_amount: в сумму входит max_amount договора целиком,
      // независимо от этапа закупки (dashboard.py:360-369)
      return true
    }
    case 'delivered':         return KPI_DELIVERED_STATUSES.includes(item.purchase_status)
    case 'delivered_unpaid':  return item.purchase_status === 'delivered'
    case 'paid':              return item.purchase_status === 'paid'
    default:                  return false
  }
}
