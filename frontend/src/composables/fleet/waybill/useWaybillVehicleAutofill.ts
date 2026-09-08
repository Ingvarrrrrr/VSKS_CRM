// Автоподстановка полей путевого листа при выборе ТС (новый путевой,
// query ?vehicle_id=..., ручной выбор в форме). Вынесено из
// FleetWaybillFormView.vue без изменения поведения.
import type { Ref } from 'vue'
import { apiFetch } from '@/api'
import type { Vehicle, WaybillForm } from './waybillFormTypes'

export function useWaybillVehicleAutofill(
  form: Ref<WaybillForm>,
  vehicles: Ref<Vehicle[]>,
  scheduleAutosave: () => void,
) {
  async function autoPopulateFromVehicle(vehicleId: number) {
    try {
      const veh = await apiFetch<Vehicle>(`/vehicles/${vehicleId}`)
      // ensure vehicle is in the autocomplete list
      if (!vehicles.value.find(v => v.id === veh.id)) {
        vehicles.value = [veh, ...vehicles.value]
      }
      form.value.vehicle_id = veh.id

      // date_start = now in datetime-local format
      const now = new Date()
      const pad = (n: number) => String(n).padStart(2, '0')
      form.value.date_start = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`

      // waybill_type by vehicle.type
      const lightTypes = ['car_light', 'suv', 'minivan']
      if (lightTypes.includes(veh.type || '')) {
        form.value.waybill_type = 'passenger'
      } else if ((veh.type || '').startsWith('truck')) {
        form.value.waybill_type = 'truck'
      }

      // odometer_start from vehicle
      if (veh.current_mileage_km != null && !form.value.odometer_start) {
        form.value.odometer_start = veh.current_mileage_km
      }

      // fuel_remaining_start from last closed trip
      try {
        const fuelData = await apiFetch<{
          fuel_remaining_l: number | null
          from_waybill_number: string | null
          from_date: string | null
        }>(`/trips/last-fuel?vehicle_id=${vehicleId}`)
        if (fuelData.fuel_remaining_l != null) {
          form.value.fuel_remaining_start = fuelData.fuel_remaining_l
        }
      } catch (e) {
        console.warn('[wbf] last-fuel fetch error', e)
      }
    } catch (e) {
      console.warn('[wbf] auto-populate vehicle error', e)
    }
  }

  function onVehicleSelect(selectedVehicle: Vehicle | undefined) {
    if (selectedVehicle && !form.value.odometer_start) {
      form.value.odometer_start = selectedVehicle.current_mileage_km
    }
    scheduleAutosave()
  }

  return { autoPopulateFromVehicle, onVehicleSelect }
}
