// ─────────────────────────────────────────────────────────────────────────
// Общие типы карточки ТС (VehicleDetailView.vue и разбитые из неё компоненты
// components/fleet/vehicle-detail/* + композаблы composables/fleet/*).
// Единственный источник — не дублировать интерфейсы по файлам (ПРАВИЛО №6).
// ─────────────────────────────────────────────────────────────────────────

export interface OdometerRow {
  id: number
  date: string
  odometer_km: number
  delta_km?: number | null
  source?: string | null
  note?: string | null
}

export interface ChecklistItem { id: number; key: string; status: string; note?: string }

export interface Checklist {
  id: number
  vehicle_id: number
  type: string
  overall_state?: string
  fuel_level?: string
  paint_condition?: string
  notes?: string
  created_at: string
  items?: ChecklistItem[]
}

export interface FieldHistoryItem {
  id: number
  vehicle_id: number
  field_key: string
  old_value: string | null
  new_value: string | null
  changed_at: string
  changed_by_user_id: number | null
  comment: string | null
}

export interface TimelineEvent {
  date: string
  dotClass: 'ok' | 'warn' | 'info' | 'alert'
  title: string
  body?: string
}

export interface OrgItem {
  id: number
  name: string
  inn?: string | null
  contractor_id?: number | null
}

export interface Vehicle {
  id: number
  owner_org_id: number
  owner_org_name?: string | null
  assigned_org_id: number | null
  assigned_org_name?: string | null
  assigned_text: string | null
  brand: string | null
  model: string | null
  color: string | null
  plate: string
  vin: string | null
  type: string | null
  state: string | null
  registered_at: string | null
  insurance_until: string | null
  fuel_type: string | null
  fuel_norm_summer: number | null
  fuel_norm_winter: number | null
  current_odometer_km: number | null
  next_to_km: number | null
  year_of_manufacture: number | null
  last_to_mileage_km: number | null
  last_to_date: string | null
  pts_number: string | null
  sts_number: string | null
  tech_inspection_until: string | null
  purchase_info: string | null
  assignment_basis: string | null
  assignment_doc_number: string | null
  assignment_doc_date: string | null
  engine_power_hp: number | null
  engine_volume_l: number | null
  has_tracker: boolean
  akb_ok: boolean
  has_radio: boolean
  mirrors_ok: boolean
  has_keys: boolean
  has_first_aid_kit: boolean
  has_spare_wheel: boolean
  has_extinguisher: boolean
  props: Record<string, string> | null
  created_at: string
  updated_at: string

  // ── Autoblock: полный реестр полей ТС (§1 контракта) ──
  body_type: string | null
  pts_category: string | null
  insurance_company: string | null
  insurance_policy_number: string | null
  ownership_basis: string | null
  ownership_doc_number: string | null
  ownership_doc_date: string | null
  owner_since: string | null
  location_city: string | null
  location_address: string | null
  home_base_city: string | null
  responsible_name: string | null
  pts_kind: string | null
  sts_issued_at: string | null
  tech_inspection_status: string | null
  tech_inspection_last_date: string | null
  pass_zo: string | null
  pass_zo_until: string | null
  pass_ho: string | null
  pass_ho_until: string | null
  pass_dnr: string | null
  pass_dnr_until: string | null
  pass_lnr: string | null
  pass_lnr_until: string | null
  pass_moscow: string | null
  pass_moscow_until: string | null
  has_spare_tires: boolean
  tires_condition: string | null
  has_mirrors: boolean
  first_aid_kit_until: string | null
  extinguisher_check_date: string | null
  tracker_paid_until: string | null
  has_tachograph: boolean
  tachograph_check_date: string | null
  repair_required: boolean
  tech_condition_info: string | null

  // ── Вычисляемые read-only (не колонки) ──
  owner_inn?: string | null
  operator_inn?: string | null
}

export interface TransferHistoryItem {
  id: number
  vehicle_id: number
  from_owner_org_id: number | null
  to_owner_org_id: number | null
  from_assigned_org_id: number | null
  to_assigned_org_id: number | null
  from_assigned_text: string | null
  to_assigned_text: string | null
  basis: string | null
  doc_number: string | null
  doc_date: string | null
  comment: string | null
  changed_at: string
  changed_by_user_id: number | null
}

export interface VehicleForm {
  plate: string
  brand: string
  model: string
  color: string
  vin: string
  type: string | null
  state: string | null
  registered_at: string
  owner_org_id: number | null
  assigned_org_id: number | null
  assigned_text: string
  insurance_until: string
  next_to_km: number | null
  fuel_type: string | null
  fuel_norm_summer: number | null
  fuel_norm_winter: number | null
  year_of_manufacture: number | null
  last_to_mileage_km: number | null
  last_to_date: string
  pts_number: string
  sts_number: string
  tech_inspection_until: string
  purchase_info: string
  assignment_basis: string
  assignment_doc_number: string
  assignment_doc_date: string
  engine_power_hp: number | null
  engine_volume_l: number | null
  has_tracker: boolean
  akb_ok: boolean
  has_radio: boolean
  mirrors_ok: boolean
  has_keys: boolean
  has_first_aid_kit: boolean
  has_spare_wheel: boolean
  has_extinguisher: boolean
  props_tires_type: string
  props_branding: string
  props_paint_condition: string
  props_defect_description: string
  props_note: string

  // ── Autoblock: новые поля (§1 контракта) ──
  body_type: string
  pts_category: string
  insurance_company: string
  insurance_policy_number: string
  ownership_basis: string
  ownership_doc_number: string
  ownership_doc_date: string
  owner_since: string
  location_city: string
  location_address: string
  home_base_city: string
  responsible_name: string
  pts_kind: string | null
  sts_issued_at: string
  tech_inspection_status: string
  tech_inspection_last_date: string
  pass_zo: string
  pass_zo_until: string
  pass_ho: string
  pass_ho_until: string
  pass_dnr: string
  pass_dnr_until: string
  pass_lnr: string
  pass_lnr_until: string
  pass_moscow: string
  pass_moscow_until: string
  has_spare_tires: boolean
  tires_condition: string
  has_mirrors: boolean
  first_aid_kit_until: string
  extinguisher_check_date: string
  tracker_paid_until: string
  has_tachograph: boolean
  tachograph_check_date: string
  repair_required: boolean
  tech_condition_info: string
}
