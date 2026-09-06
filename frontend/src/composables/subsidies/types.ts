// Общие типы карточки субсидии, вынесенные из SubsidiesView.vue при разбиении на
// компоненты (components/subsidies/*) и композаблы (composables/subsidies/*).
// Единственный источник этих интерфейсов — SubsidiesView.vue раньше объявлял их
// локально; теперь оба импортируют отсюда (Правило №6 — один показатель/тип,
// один источник истины).

export interface SubsidyRow {
  id: number; name: string; year: number; budget: number
  calculated_budget?: number
  description?: string; planned: number; paid: number; contracted: number
  plan_schedule: number; ordered: number
  feo_filled?: boolean
  feo_budget_total?: number
  contractor_id?: number
  contractor_name?: string
  contractor_inn?: string
  basis_doc_number?: string
  basis_doc_date?: string
  // Phase 31-05: canonical budget fields
  remaining?: number | null
  planned_amount?: number | null
  budget_discrepancy?: number | null
  require_planned_dates?: boolean
  // Phase 32: dashboard KPI fields
  work: number
  contracts: number
  delivered: number
  delivered_unpaid: number
  // Владелец (2026-08-30): предупреждение «сумма заказанного приближается к
  // потолку субсидии» — см. app/services/feo_plan.py calculate_ceiling_forecast*.
  ceiling_warn_percent?: number | null
  ceiling_total?: number | null
  ceiling_committed_total?: number | null
  ceiling_committed_percent?: number | null
  ceiling_near_warning?: boolean
  ceiling_exceeded?: boolean
  // C4: черновые субсидии — статус/автор/утвердивший.
  status?: string
  created_by?: number | null
  approved_by?: number | null
  approved_at?: string | null
}

// C4: участник (соредактор) черновой субсидии — калька wish_member без
// consent-флоу, см. backend/app/routers/subsidy_members.py.
export interface SubsidyMember {
  id: number
  subsidy_id: number
  user_id: number
  added_by_id: number | null
  username?: string | null
  full_name?: string | null
  added_by_name?: string | null
  created_at?: string | null
}

export interface FeoCategory {
  id: number; parent_id: number | null; subsidy_id: number
  level: number; name: string; code: string | null; appendix: string | null
  is_active: boolean; budget: number | null; planned_quantity: number | null; planned_amount: number | null; unit: string | null
  feo_quantity: number | null; feo_unit: string | null
  description: string | null; feo_amount: number | null
  // План zany-fluttering-mountain.md, п.1/п.5: способ расчёта плана — переключатель
  // «по плановым позициям» / «по вручную заданной сумме».
  plan_source?: 'planned_items' | 'manual_sum'
  manual_plan_amount?: number | null
}

export interface FeoNode extends FeoCategory {
  depth: number
  hasChildren: boolean
  children: FeoNode[]
}

// ── Approvers types ───────────────────────────────
export interface SubsidyApprover {
  id: number
  subsidy_id: number
  role_name: string
  full_name: string
  order_num: number
  is_default: boolean
  can_initiate: boolean
  show_feo_path: boolean
  user_id?: number | null
}

// ── Events (Мероприятия) ──────────────────────────
export interface EventItem {
  id: number; subsidy_id: number; name: string; is_active: boolean
  region?: string; date_from?: string; date_to?: string
  order_decree?: string; planned_indicators?: string; actual_indicators?: string
  media_link_1?: string; media_link_2?: string; media_link_3?: string
}

export interface SubsidyDeleteImpact {
  feo_categories: number
  planned_items: number
  purchases: number
  contracts: number
}
