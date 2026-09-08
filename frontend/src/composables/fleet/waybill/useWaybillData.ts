// Справочники для формы путевого листа: ТС, водители, все пользователи
// (механики/медработники берутся из общего списка — как и в исходном
// FleetWaybillFormView.vue). Вынесено без изменения поведения.
import { ref, computed } from 'vue'
import { apiFetch } from '@/api'
import type { Vehicle, Driver, UserOption } from './waybillFormTypes'

export function useWaybillData() {
  const vehicles = ref<Vehicle[]>([])
  const drivers  = ref<Driver[]>([])
  const allUsers = ref<UserOption[]>([])

  const mechanicUsers = computed(() => allUsers.value)
  const doctorUsers   = computed(() => allUsers.value)

  async function loadVehicles() {
    try {
      // GET /api/vehicles отдаёт { items, total } (пагинация), а не голый массив —
      // найдено при проверке консоли на этой странице (2026-09-03): vehicles.value
      // становился объектом, и .find() валился с "is not a function", ломая
      // выбор ТС и подстановку в шапку путевого листа.
      const data = await apiFetch<Vehicle[] | { items: Vehicle[] }>('/vehicles/')
      vehicles.value = Array.isArray(data) ? data : (data?.items ?? [])
    } catch (e) {
      console.warn('[wbf] vehicles error', e)
    }
  }

  async function loadDrivers() {
    try {
      const data = await apiFetch<Driver[]>('/users/?can_drive=true&limit=200')
      drivers.value = data
    } catch (e) {
      console.warn('[wbf] drivers error', e)
    }
  }

  async function loadUsers() {
    try {
      const data = await apiFetch<any[]>('/users/')
      allUsers.value = data.map(u => ({
        id: u.id,
        fullName: u.full_name ?? u.fullName ?? `User #${u.id}`,
        role: u.role,
      }))
    } catch (e) {
      console.warn('[wbf] users error', e)
    }
  }

  return {
    vehicles,
    drivers,
    allUsers,
    mechanicUsers,
    doctorUsers,
    loadVehicles,
    loadDrivers,
    loadUsers,
  }
}
