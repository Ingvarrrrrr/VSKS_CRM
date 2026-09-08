// Состояние формы путевого листа: сам form, сериализация с/на сервер,
// вычисляемые поля (выбранные ТС/водитель, пробег, readonly-флаги, сводка
// для аside, подпись типа ТС для печати). Вынесено из FleetWaybillFormView.vue
// без изменения поведения.
import { ref, computed, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { Vehicle, Driver, WaybillForm } from './waybillFormTypes'

export function useWaybillForm(vehicles: Ref<Vehicle[]>, drivers: Ref<Driver[]>, isNew: boolean) {
  const loading = ref(!isNew)

  const form = ref<WaybillForm>({
    number: '',
    status: 'created',
    date_start: '',
    date_end: '',
    waybill_type: 'passenger',
    purpose: '',
    route_stops: [
      { ord: 1, kind: 'start', name: '', description: '' },
      { ord: 2, kind: 'end',   name: '', description: '' },
    ],
  })

  const selectedVehicle = computed(() =>
    vehicles.value.find(v => v.id === form.value.vehicle_id)
  )
  const selectedDriver = computed(() =>
    drivers.value.find(d => d.id === form.value.driver_user_id)
  )

  const actualMileage = computed<number | undefined>(() => {
    const s = form.value.odometer_start
    const f = form.value.odometer_finish
    if (s !== undefined && f !== undefined && f >= s) return f - s
    return undefined
  })

  const formReadonly = computed(() =>
    form.value.status === 'closed' || form.value.status === 'on_review'
  )
  const preInspectReadonly = computed(() =>
    ['in_progress', 'closing', 'on_review', 'closed'].includes(form.value.status)
  )
  const postInspectReadonly = computed(() =>
    ['closed'].includes(form.value.status)
  )

  const primaryActionLabel = computed(() => {
    if (isNew || form.value.status === 'created') return 'Передать в работу'
    if (form.value.status === 'tech_inspect')     return 'Подтвердить тех. осмотр'
    if (form.value.status === 'med_inspect')      return 'Подтвердить медосмотр'
    if (form.value.status === 'in_progress')      return 'Сдать путевой'
    if (form.value.status === 'on_review')        return 'Закрыть'
    return 'Сохранить'
  })

  const asideWaybill = computed(() => ({
    id: form.value.id ?? 0,
    number: form.value.number || 'Новый',
    date: form.value.date_start,
    valid_from: form.value.date_start,
    valid_to: form.value.date_end,
    fill_percent: form.value.fill_percent,
    planned_mileage_km: form.value.planned_mileage_km,
    planned_duration_h: form.value.planned_duration_h,
    tech_inspect_ok: form.value.tech_inspect_ok,
    med_inspect_ok: form.value.med_inspect_ok,
    status_history: form.value.status_history,
    related_docs: form.value.related_docs,
  }))

  // Phase 30.2: печать A5 (легковой/автобус) / A4 (грузовой)
  const isLightVehicle = computed(() => {
    const t = form.value.waybill_type || ''
    return t !== 'truck' // passenger, bus → A5; truck → A4
  })

  function mapServerToForm(data: any): Partial<WaybillForm> {
    return {
      id: data.id,
      number: data.number,
      status: data.status,
      date_start: data.date_start ?? data.valid_from ?? '',
      date_end: data.date_end ?? data.valid_to ?? '',
      waybill_type: data.waybill_type ?? 'passenger',
      vehicle_id: data.vehicle_id,
      driver_user_id: data.driver_user_id,
      purpose: data.purpose ?? '',
      route_stops: data.route_stops?.length
        ? data.route_stops
        : [
            { ord: 1, kind: 'start', name: '', description: '' },
            { ord: 2, kind: 'end',   name: '', description: '' },
          ],
      planned_mileage_km: data.planned_mileage_km,
      planned_duration: data.planned_duration,
      work_hours_norm: data.work_hours_norm,
      odometer_start: data.odometer_start,
      odometer_finish: data.odometer_finish,
      fuel_remaining_start: data.fuel_remaining_start,
      fuel_issued_l: data.fuel_issued_l,
      fuel_remaining_finish: data.fuel_remaining_finish,
      cargo_description: data.cargo_description,
      cargo_weight_t: data.cargo_weight_t,
      passengers_count: data.passengers_count,
      pre_mechanic_id: data.pre_mechanic_id,
      pre_mechanic_at: data.pre_mechanic_at,
      pre_mechanic_result: data.pre_mechanic_result,
      pre_doctor_id: data.pre_doctor_id,
      pre_doctor_at: data.pre_doctor_at,
      pre_doctor_result: data.pre_doctor_result,
      post_mechanic_id: data.post_mechanic_id,
      post_mechanic_at: data.post_mechanic_at,
      post_mechanic_result: data.post_mechanic_result,
      post_doctor_id: data.post_doctor_id,
      post_doctor_at: data.post_doctor_at,
      post_doctor_result: data.post_doctor_result,
      driver_signature: data.driver_signature,
      tech_inspect_ok: data.tech_inspect_ok,
      med_inspect_ok: data.med_inspect_ok,
      fill_percent: data.fill_percent,
      planned_duration_h: data.planned_duration_h,
      status_history: data.status_history,
      related_docs: data.related_docs,
    }
  }

  async function loadWaybill(idParam: string) {
    loading.value = true
    try {
      const data = await apiFetch<any>(`/trips/${idParam}`)
      Object.assign(form.value, mapServerToForm(data))
    } catch (e) {
      console.error('[wbf] load error', e)
    } finally {
      loading.value = false
    }
  }

  function buildPayload(): Record<string, unknown> {
    return {
      date_start: form.value.date_start || undefined,
      date_end: form.value.date_end || undefined,
      waybill_type: form.value.waybill_type,
      vehicle_id: form.value.vehicle_id,
      driver_user_id: form.value.driver_user_id,
      purpose: form.value.purpose,
      planned_mileage_km: form.value.planned_mileage_km,
      planned_duration: form.value.planned_duration,
      work_hours_norm: form.value.work_hours_norm,
      odometer_start: form.value.odometer_start,
      odometer_finish: form.value.odometer_finish,
      fuel_remaining_start: form.value.fuel_remaining_start,
      fuel_issued_l: form.value.fuel_issued_l,
      fuel_remaining_finish: form.value.fuel_remaining_finish,
      cargo_description: form.value.cargo_description,
      cargo_weight_t: form.value.cargo_weight_t,
      passengers_count: form.value.passengers_count,
      pre_mechanic_id: form.value.pre_mechanic_id,
      pre_mechanic_at: form.value.pre_mechanic_at,
      pre_mechanic_result: form.value.pre_mechanic_result,
      pre_doctor_id: form.value.pre_doctor_id,
      pre_doctor_at: form.value.pre_doctor_at,
      pre_doctor_result: form.value.pre_doctor_result,
      post_mechanic_id: form.value.post_mechanic_id,
      post_mechanic_at: form.value.post_mechanic_at,
      post_mechanic_result: form.value.post_mechanic_result,
      post_doctor_id: form.value.post_doctor_id,
      post_doctor_at: form.value.post_doctor_at,
      post_doctor_result: form.value.post_doctor_result,
    }
  }

  return {
    loading,
    form,
    selectedVehicle,
    selectedDriver,
    actualMileage,
    formReadonly,
    preInspectReadonly,
    postInspectReadonly,
    primaryActionLabel,
    asideWaybill,
    isLightVehicle,
    mapServerToForm,
    loadWaybill,
    buildPayload,
  }
}
