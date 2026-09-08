import { reactive, ref } from 'vue'
import type { Vehicle, VehicleForm } from './vehicleDetailTypes'

// ─────────────────────────────────────────────────────────────────────────
// Форма редактирования карточки ТС: реактивная модель, заполнение из
// загруженного Vehicle, сброс и построение PATCH-дельты (отправляются
// только реально изменённые поля). Вынесено из VehicleDetailView.vue без
// изменения поведения — apiFetch здесь не вызывается, PATCH делает
// useVehicleRecord.ts, используя buildDelta() отсюда.
// ─────────────────────────────────────────────────────────────────────────

export function useVehicleForm() {
  const form = reactive<VehicleForm>({
    plate: '',
    brand: '',
    model: '',
    color: '',
    vin: '',
    type: null,
    state: null,
    registered_at: '',
    owner_org_id: null,
    assigned_org_id: null,
    assigned_text: '',
    insurance_until: '',
    next_to_km: null,
    fuel_type: null,
    fuel_norm_summer: null,
    fuel_norm_winter: null,
    year_of_manufacture: null,
    last_to_mileage_km: null,
    last_to_date: '',
    pts_number: '',
    sts_number: '',
    tech_inspection_until: '',
    purchase_info: '',
    assignment_basis: '',
    assignment_doc_number: '',
    assignment_doc_date: '',
    engine_power_hp: null,
    engine_volume_l: null,
    has_tracker: false,
    akb_ok: false,
    has_radio: false,
    mirrors_ok: false,
    has_keys: false,
    has_first_aid_kit: false,
    has_spare_wheel: false,
    has_extinguisher: false,
    props_tires_type: '',
    props_branding: '',
    props_paint_condition: '',
    props_defect_description: '',
    props_note: '',

    body_type: '',
    pts_category: '',
    insurance_company: '',
    insurance_policy_number: '',
    ownership_basis: '',
    ownership_doc_number: '',
    ownership_doc_date: '',
    owner_since: '',
    location_city: '',
    location_address: '',
    home_base_city: '',
    responsible_name: '',
    pts_kind: null,
    sts_issued_at: '',
    tech_inspection_status: '',
    tech_inspection_last_date: '',
    pass_zo: '',
    pass_zo_until: '',
    pass_ho: '',
    pass_ho_until: '',
    pass_dnr: '',
    pass_dnr_until: '',
    pass_lnr: '',
    pass_lnr_until: '',
    pass_moscow: '',
    pass_moscow_until: '',
    has_spare_tires: false,
    tires_condition: '',
    has_mirrors: false,
    first_aid_kit_until: '',
    extinguisher_check_date: '',
    tracker_paid_until: '',
    has_tachograph: false,
    tachograph_check_date: '',
    repair_required: false,
    tech_condition_info: '',
  })

  const historyComment = ref('')

  // ─────────────── isDirty ───────────────

  function formSnapshot(): string {
    return JSON.stringify({ ...form })
  }

  const originalSnapshot = ref('')

  function isDirtyAgainst(vehicle: Vehicle | null): boolean {
    if (!vehicle) return false
    return formSnapshot() !== originalSnapshot.value
  }

  // ─────────────── Populate form from vehicle ───────────────

  function toDateInput(v: string | null): string {
    if (!v) return ''
    try { return v.slice(0, 10) } catch { return '' }
  }

  function fillForm(v: Vehicle) {
    form.plate                  = v.plate ?? ''
    form.brand                  = v.brand ?? ''
    form.model                  = v.model ?? ''
    form.color                  = v.color ?? ''
    form.vin                    = v.vin ?? ''
    form.type                   = v.type ?? null
    form.state                  = v.state ?? null
    form.registered_at          = toDateInput(v.registered_at)
    form.owner_org_id           = v.owner_org_id ?? null
    form.assigned_org_id        = v.assigned_org_id ?? null
    form.assigned_text          = v.assigned_text ?? ''
    form.insurance_until        = toDateInput(v.insurance_until)
    form.next_to_km             = v.next_to_km ?? null
    form.fuel_type              = v.fuel_type ?? null
    form.fuel_norm_summer       = v.fuel_norm_summer ?? null
    form.fuel_norm_winter       = v.fuel_norm_winter ?? null
    form.year_of_manufacture    = v.year_of_manufacture ?? null
    form.last_to_mileage_km     = v.last_to_mileage_km ?? null
    form.last_to_date           = toDateInput(v.last_to_date)
    form.pts_number             = v.pts_number ?? ''
    form.sts_number             = v.sts_number ?? ''
    form.tech_inspection_until  = toDateInput(v.tech_inspection_until)
    form.purchase_info          = v.purchase_info ?? ''
    form.assignment_basis       = v.assignment_basis ?? ''
    form.assignment_doc_number  = v.assignment_doc_number ?? ''
    form.assignment_doc_date    = toDateInput(v.assignment_doc_date)
    form.engine_power_hp        = v.engine_power_hp ?? null
    form.engine_volume_l        = v.engine_volume_l ?? null
    form.has_tracker            = !!v.has_tracker
    form.akb_ok                 = !!v.akb_ok
    form.has_radio              = !!v.has_radio
    form.mirrors_ok             = !!v.mirrors_ok
    form.has_keys               = !!v.has_keys
    form.has_first_aid_kit      = !!v.has_first_aid_kit
    form.has_spare_wheel        = !!v.has_spare_wheel
    form.has_extinguisher       = !!v.has_extinguisher
    form.props_tires_type        = v.props?.tires_type ?? ''
    form.props_branding          = v.props?.branding ?? ''
    form.props_paint_condition   = v.props?.paint_condition ?? ''
    form.props_defect_description = v.props?.defect_description ?? ''
    form.props_note              = v.props?.note ?? ''

    form.body_type               = v.body_type ?? ''
    form.pts_category            = v.pts_category ?? ''
    form.insurance_company       = v.insurance_company ?? ''
    form.insurance_policy_number = v.insurance_policy_number ?? ''
    form.ownership_basis         = v.ownership_basis ?? ''
    form.ownership_doc_number    = v.ownership_doc_number ?? ''
    form.ownership_doc_date      = toDateInput(v.ownership_doc_date)
    form.owner_since             = toDateInput(v.owner_since)
    form.location_city           = v.location_city ?? ''
    form.location_address        = v.location_address ?? ''
    form.home_base_city          = v.home_base_city ?? ''
    form.responsible_name        = v.responsible_name ?? ''
    form.pts_kind                = v.pts_kind ?? null
    form.sts_issued_at           = toDateInput(v.sts_issued_at)
    form.tech_inspection_status  = v.tech_inspection_status ?? ''
    form.tech_inspection_last_date = toDateInput(v.tech_inspection_last_date)
    form.pass_zo                 = v.pass_zo ?? ''
    form.pass_zo_until           = toDateInput(v.pass_zo_until)
    form.pass_ho                 = v.pass_ho ?? ''
    form.pass_ho_until           = toDateInput(v.pass_ho_until)
    form.pass_dnr                = v.pass_dnr ?? ''
    form.pass_dnr_until          = toDateInput(v.pass_dnr_until)
    form.pass_lnr                = v.pass_lnr ?? ''
    form.pass_lnr_until          = toDateInput(v.pass_lnr_until)
    form.pass_moscow             = v.pass_moscow ?? ''
    form.pass_moscow_until       = toDateInput(v.pass_moscow_until)
    form.has_spare_tires         = !!v.has_spare_tires
    form.tires_condition         = v.tires_condition ?? ''
    form.has_mirrors             = !!v.has_mirrors
    form.first_aid_kit_until     = toDateInput(v.first_aid_kit_until)
    form.extinguisher_check_date = toDateInput(v.extinguisher_check_date)
    form.tracker_paid_until      = toDateInput(v.tracker_paid_until)
    form.has_tachograph          = !!v.has_tachograph
    form.tachograph_check_date   = toDateInput(v.tachograph_check_date)
    form.repair_required         = !!v.repair_required
    form.tech_condition_info     = v.tech_condition_info ?? ''

    originalSnapshot.value = formSnapshot()
  }

  function resetForm(vehicle: Vehicle | null) {
    if (vehicle) fillForm(vehicle)
  }

  // ─────────────── Build PATCH delta ───────────────

  function buildDelta(vehicle: Vehicle | null): Record<string, any> {
    if (!vehicle) return {}
    const v = vehicle
    const delta: Record<string, any> = {}

    const strField = (key: keyof VehicleForm, orig: string | null) => {
      const cur = (form[key] as string) || null
      const origNorm = orig || null
      if (cur !== origNorm) delta[key] = cur
    }
    const numField = (key: keyof VehicleForm, orig: number | null) => {
      const cur = (form[key] as number | null) ?? null
      if (cur !== orig) delta[key] = cur
    }
    const boolField = (key: keyof VehicleForm, orig: boolean) => {
      const cur = form[key] as boolean
      if (cur !== orig) delta[key] = cur
    }
    const dateField = (key: keyof VehicleForm, orig: string | null) => {
      const cur = (form[key] as string) || null
      const origNorm = orig ? orig.slice(0, 10) : null
      if (cur !== origNorm) delta[key] = cur
    }

    strField('plate', v.plate)
    strField('brand', v.brand)
    strField('model', v.model)
    strField('color', v.color)
    strField('vin', v.vin)
    strField('type', v.type)
    strField('state', v.state)
    strField('assigned_text', v.assigned_text)
    strField('fuel_type', v.fuel_type)
    strField('pts_number', v.pts_number)
    strField('sts_number', v.sts_number)
    strField('purchase_info', v.purchase_info)
    strField('assignment_basis', v.assignment_basis)
    strField('assignment_doc_number', v.assignment_doc_number)
    dateField('registered_at', v.registered_at)
    dateField('insurance_until', v.insurance_until)
    dateField('last_to_date', v.last_to_date)
    dateField('tech_inspection_until', v.tech_inspection_until)
    dateField('assignment_doc_date', v.assignment_doc_date)
    numField('next_to_km', v.next_to_km)
    numField('fuel_norm_summer', v.fuel_norm_summer)
    numField('fuel_norm_winter', v.fuel_norm_winter)
    numField('owner_org_id', v.owner_org_id ?? null)
    numField('assigned_org_id', v.assigned_org_id)
    numField('year_of_manufacture', v.year_of_manufacture)
    numField('last_to_mileage_km', v.last_to_mileage_km)
    numField('engine_power_hp', v.engine_power_hp)
    numField('engine_volume_l', v.engine_volume_l)
    boolField('has_tracker', v.has_tracker)
    boolField('akb_ok', v.akb_ok)
    boolField('has_radio', v.has_radio)
    boolField('mirrors_ok', v.mirrors_ok)
    boolField('has_keys', v.has_keys)
    boolField('has_first_aid_kit', v.has_first_aid_kit)
    boolField('has_spare_wheel', v.has_spare_wheel)
    boolField('has_extinguisher', v.has_extinguisher)

    // ── Autoblock: новые поля (§1 контракта) ──
    strField('purchase_info', v.purchase_info)
    strField('assignment_doc_number', v.assignment_doc_number)
    dateField('assignment_doc_date', v.assignment_doc_date)
    strField('body_type', v.body_type)
    strField('pts_category', v.pts_category)
    strField('insurance_company', v.insurance_company)
    strField('insurance_policy_number', v.insurance_policy_number)
    strField('ownership_basis', v.ownership_basis)
    strField('ownership_doc_number', v.ownership_doc_number)
    dateField('ownership_doc_date', v.ownership_doc_date)
    dateField('owner_since', v.owner_since)
    strField('location_city', v.location_city)
    strField('location_address', v.location_address)
    strField('home_base_city', v.home_base_city)
    strField('responsible_name', v.responsible_name)
    strField('pts_kind', v.pts_kind)
    dateField('sts_issued_at', v.sts_issued_at)
    strField('tech_inspection_status', v.tech_inspection_status)
    dateField('tech_inspection_last_date', v.tech_inspection_last_date)
    strField('pass_zo', v.pass_zo)
    dateField('pass_zo_until', v.pass_zo_until)
    strField('pass_ho', v.pass_ho)
    dateField('pass_ho_until', v.pass_ho_until)
    strField('pass_dnr', v.pass_dnr)
    dateField('pass_dnr_until', v.pass_dnr_until)
    strField('pass_lnr', v.pass_lnr)
    dateField('pass_lnr_until', v.pass_lnr_until)
    strField('pass_moscow', v.pass_moscow)
    dateField('pass_moscow_until', v.pass_moscow_until)
    boolField('has_spare_tires', v.has_spare_tires)
    strField('tires_condition', v.tires_condition)
    boolField('has_mirrors', v.has_mirrors)
    dateField('first_aid_kit_until', v.first_aid_kit_until)
    dateField('extinguisher_check_date', v.extinguisher_check_date)
    dateField('tracker_paid_until', v.tracker_paid_until)
    boolField('has_tachograph', v.has_tachograph)
    dateField('tachograph_check_date', v.tachograph_check_date)
    boolField('repair_required', v.repair_required)
    strField('tech_condition_info', v.tech_condition_info)

    // JSONB props — send full object if any prop field changed
    const origProps: Record<string, any> = v.props ?? {}
    const newProps: Record<string, any> = {
      ...origProps,
      tires_type:         form.props_tires_type || undefined,
      branding:           form.props_branding || undefined,
      paint_condition:    form.props_paint_condition || undefined,
      defect_description: form.props_defect_description || undefined,
      note:               form.props_note || undefined,
    }
    // Remove undefined keys
    Object.keys(newProps).forEach(k => { if (newProps[k] === undefined) delete newProps[k] })

    const propsChanged = (
      (form.props_tires_type || null) !== (origProps.tires_type || null) ||
      (form.props_branding || null) !== (origProps.branding || null) ||
      (form.props_paint_condition || null) !== (origProps.paint_condition || null) ||
      (form.props_defect_description || null) !== (origProps.defect_description || null) ||
      (form.props_note || null) !== (origProps.note || null)
    )
    if (propsChanged) {
      delta.props = newProps
    }

    return delta
  }

  return {
    form,
    historyComment,
    fillForm,
    resetForm,
    buildDelta,
    isDirtyAgainst,
  }
}
