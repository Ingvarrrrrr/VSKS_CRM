// Действия жизненного цикла путевого листа: сохранение черновика, передача
// в работу / подтверждение осмотров / сдача / закрытие. Вынесено из
// FleetWaybillFormView.vue без изменения поведения.
import { ref, type Ref } from 'vue'
import type { Router } from 'vue-router'
import { apiFetch } from '@/api'
import type { WaybillForm } from './waybillFormTypes'

export function useWaybillWorkflow(
  form: Ref<WaybillForm>,
  buildPayload: () => Record<string, unknown>,
  mapServerToForm: (data: any) => Partial<WaybillForm>,
  router: Router,
  showError: (msg: string) => void,
) {
  const saving = ref(false)
  const actionLoading = ref(false)
  const signingLoading = ref(false)

  async function saveDraft() {
    if (!form.value.vehicle_id) {
      showError('Выберите транспортное средство для путевого листа')
      return
    }
    saving.value = true
    try {
      if (!form.value.id) {
        // Create
        const data = await apiFetch<any>('/trips/', {
          method: 'POST',
          body: buildPayload() as any,
        })
        Object.assign(form.value, mapServerToForm(data))
        router.replace(`/fleet/waybills/${form.value.id}`)
      } else {
        // Update
        await apiFetch(`/trips/${form.value.id}`, {
          method: 'PATCH',
          body: buildPayload() as any,
        })
      }
    } catch (e: any) {
      console.error('[wbf] save error', e)
      const code = e?.payload?.code || e?.detail?.code
      const msg = e?.payload?.message || e?.detail?.message
      if (code === 'VEHICLE_REQUIRED') {
        showError('Выберите транспортное средство для путевого листа')
      } else if (code === 'DRIVER_REQUIRED' || code === 'DRIVER_NOT_ELIGIBLE') {
        showError(msg || 'Укажите водителя с правом управления ТС')
      } else if (msg) {
        showError(msg)
      } else {
        showError('Ошибка сохранения путевого листа')
      }
    } finally {
      saving.value = false
    }
  }

  async function submitTechInspect() {
    if (!form.value.id) return
    actionLoading.value = true
    try {
      const data = await apiFetch<any>(`/trips/${form.value.id}/tech-inspect`, {
        method: 'POST',
        body: {
          mechanic_id: form.value.pre_mechanic_id,
          inspected_at: form.value.pre_mechanic_at,
          result: form.value.pre_mechanic_result,
        } as any,
      })
      if (data?.status) form.value.status = data.status
    } catch (e) {
      console.error('[wbf] tech-inspect error', e)
    } finally {
      actionLoading.value = false
    }
  }

  async function confirmTechInspect() {
    await submitTechInspect()
  }

  async function confirmMedInspect() {
    if (!form.value.id) return
    actionLoading.value = true
    try {
      const data = await apiFetch<any>(`/trips/${form.value.id}/med-inspect`, {
        method: 'POST',
        body: {
          doctor_id: form.value.pre_doctor_id,
          inspected_at: form.value.pre_doctor_at,
          result: form.value.pre_doctor_result,
        } as any,
      })
      if (data?.status) form.value.status = data.status
    } catch (e) {
      console.error('[wbf] med-inspect error', e)
    } finally {
      actionLoading.value = false
    }
  }

  async function driverSign() {
    if (!form.value.id) return
    signingLoading.value = true
    try {
      const data = await apiFetch<any>(`/trips/${form.value.id}/driver-sign`, {
        method: 'POST',
        body: {
          signature: form.value.driver_signature,
          signed_at: new Date().toISOString(),
        } as any,
      })
      if (data?.status) form.value.status = data.status
    } catch (e) {
      console.error('[wbf] driver-sign error', e)
    } finally {
      signingLoading.value = false
    }
  }

  async function closeWaybill() {
    if (!form.value.id) return
    actionLoading.value = true
    try {
      const data = await apiFetch<any>(`/trips/${form.value.id}/close`, { method: 'POST', body: {} as any })
      if (data?.status) form.value.status = data.status
    } catch (e) {
      console.error('[wbf] close error', e)
    } finally {
      actionLoading.value = false
    }
  }

  async function handlePrimaryAction() {
    const s = form.value.status
    if (!form.value.id || s === 'created') {
      await saveDraft()
      return
    }
    if (s === 'tech_inspect')  { await confirmTechInspect(); return }
    if (s === 'med_inspect')   { await confirmMedInspect();  return }
    if (s === 'in_progress')   { await driverSign();         return }
    if (s === 'on_review')     { await closeWaybill();       return }
    await saveDraft()
  }

  return {
    saving,
    actionLoading,
    signingLoading,
    saveDraft,
    handlePrimaryAction,
    submitTechInspect,
    confirmTechInspect,
    confirmMedInspect,
    driverSign,
    closeWaybill,
  }
}
