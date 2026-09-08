// useVehicleCreateDialog.ts — диалог «Добавить ТС»: форма, проверка дубликата
// VIN, создание. Дословный перенос из VehicleListView.vue. `show` управляется
// снаружи (v-model на VehicleCreateDialog.vue), здесь — только поля формы.
import { reactive } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'

export function useVehicleCreateDialog(options: { onError: (err: any) => void }) {
  const router = useRouter()

  const createDialog = reactive({
    loading: false,
    vin: '',
    plate: '',
    brand: '',
    model: '',
    owner_org_id: null as number | null,
    type: null as string | null,
    state: 'working' as string,
    // VIN duplicate check state
    vinChecking: false,
    vinDuplicate: null as null | { id: number; plate: string; brand: string; model: string; message: string },
    forceCreate: false,
  })

  function resetCreateDialog() {
    createDialog.loading = false
    createDialog.vin = ''
    createDialog.plate = ''
    createDialog.brand = ''
    createDialog.model = ''
    createDialog.owner_org_id = null
    createDialog.type = null
    createDialog.state = 'working'
    createDialog.vinChecking = false
    createDialog.vinDuplicate = null
    createDialog.forceCreate = false
  }

  async function doCreate(): Promise<boolean> {
    if (!createDialog.plate || !createDialog.owner_org_id) return false
    createDialog.loading = true
    try {
      const created = await apiFetch<{ id: number }>('/vehicles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vin: createDialog.vin?.replace(/\s+/g, '').toUpperCase() || null,
          plate: createDialog.plate,
          brand: createDialog.brand || null,
          model: createDialog.model || null,
          owner_org_id: createDialog.owner_org_id,
          type: createDialog.type || null,
          state: createDialog.state,
          force: createDialog.forceCreate,
        }),
      })
      resetCreateDialog()
      router.push(`/property/vehicles/${created.id}`)
      return true
    } catch (err: any) {
      createDialog.loading = false
      const payload = err?.payload ?? err?.detail ?? err
      if (payload?.code === 'DUPLICATE_VIN' && payload?.vehicle_id) {
        createDialog.vinDuplicate = {
          id: payload.vehicle_id,
          plate: payload.plate || '',
          brand: payload.brand || '',
          model: payload.model || '',
          message: payload.message || 'Дубликат VIN',
        }
        options.onError(err)
      } else {
        options.onError(err)
      }
      return false
    }
  }

  let vinDebounce: ReturnType<typeof setTimeout> | null = null

  function onVinChange() {
    createDialog.vinDuplicate = null
    createDialog.forceCreate = false
    if (vinDebounce) clearTimeout(vinDebounce)
  }

  async function checkVinDuplicate() {
    const vin = (createDialog.vin || '').replace(/\s+/g, '').toUpperCase()
    if (!vin || vin.length < 5) {
      createDialog.vinDuplicate = null
      return
    }
    createDialog.vinChecking = true
    try {
      const res = await apiFetch<{ items: any[]; total: number }>(`/vehicles?vin=${encodeURIComponent(vin)}&limit=1`)
      const items = res?.items ?? []
      if (items.length) {
        const v = items[0]
        createDialog.vinDuplicate = {
          id: v.id,
          plate: v.plate || '',
          brand: v.brand || '',
          model: v.model || '',
          message: `ТС с VIN ${vin} уже есть`,
        }
      } else {
        createDialog.vinDuplicate = null
      }
    } catch { /* ignore */ }
    finally { createDialog.vinChecking = false }
  }

  return {
    createDialog,
    resetCreateDialog,
    doCreate,
    onVinChange,
    checkVinDuplicate,
  }
}
