import { ref, computed } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { useVehicleErrorDialog } from './useVehicleErrorDialog'
import { useVehicleForm } from './useVehicleForm'
import type { Vehicle } from './vehicleDetailTypes'

// ─────────────────────────────────────────────────────────────────────────
// Загрузка / сохранение / удаление карточки ТС. Единственное место с
// apiFetch для самой сущности vehicle (GET/PATCH/DELETE) — вынесено из
// VehicleDetailView.vue без изменения поведения. Использует useVehicleForm
// для построения PATCH-дельты и заполнения формы после загрузки/сохранения.
// ─────────────────────────────────────────────────────────────────────────

export function useVehicleRecord() {
  const vehicleForm = useVehicleForm()
  const { showError } = useVehicleErrorDialog()
  const toast = useToast()

  function showSnack(text: string, color: ToastType = 'success') {
    toast.addToast(text, color)
  }

  const vehicle = ref<Vehicle | null>(null)
  const vehicleOriginal = ref<Vehicle | null>(null)
  const loadingVehicle = ref(false)
  const saving = ref(false)
  const deleting = ref(false)
  const deleteDialog = ref(false)

  const isDirty = computed(() => vehicleForm.isDirtyAgainst(vehicle.value))

  async function loadVehicle(id: number) {
    loadingVehicle.value = true
    vehicle.value = null
    try {
      const data = await apiFetch<Vehicle>(`/vehicles/${id}`)
      vehicle.value = data
      vehicleOriginal.value = JSON.parse(JSON.stringify(data))
      vehicleForm.fillForm(data)
    } catch (err: any) {
      showError(err)
    } finally {
      loadingVehicle.value = false
    }
  }

  async function save() {
    if (!vehicle.value) return
    const delta = vehicleForm.buildDelta(vehicle.value)
    if (Object.keys(delta).length === 0) return
    if (vehicleForm.historyComment.value.trim()) {
      delta._history_comment = vehicleForm.historyComment.value.trim()
    }
    saving.value = true
    try {
      const updated = await apiFetch<Vehicle>(`/vehicles/${vehicle.value.id}`, {
        method: 'PATCH',
        body: JSON.stringify(delta),
      })
      vehicle.value = updated
      vehicleOriginal.value = JSON.parse(JSON.stringify(updated))
      vehicleForm.fillForm(updated)
      vehicleForm.historyComment.value = ''
      showSnack('Сохранено')
    } catch (err: any) {
      showError(err)
    } finally {
      saving.value = false
    }
  }

  function resetForm() {
    vehicleForm.resetForm(vehicle.value)
  }

  async function doDelete(onDeleted: () => void) {
    if (!vehicle.value) return
    deleting.value = true
    try {
      await apiFetch(`/vehicles/${vehicle.value.id}`, { method: 'DELETE' })
      onDeleted()
    } catch (err: any) {
      deleteDialog.value = false
      showError(err)
    } finally {
      deleting.value = false
    }
  }

  return {
    ...vehicleForm,
    vehicle,
    vehicleOriginal,
    loadingVehicle,
    saving,
    deleting,
    deleteDialog,
    isDirty,
    loadVehicle,
    save,
    resetForm,
    doDelete,
    showSnack,
  }
}
