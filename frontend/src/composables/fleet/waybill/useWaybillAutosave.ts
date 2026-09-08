// Автосохранение путевого листа (дебаунс 1500мс). Watcher-ы, которые решают
// КОГДА вызывать scheduleAutosave, остаются во view (FleetWaybillFormView.vue)
// — здесь только сам механизм дебаунса и PATCH-запрос, как это сделано для
// PurchaseDatesSection и других уже разрезанных форм в проекте.
import type { Ref } from 'vue'
import { apiFetch } from '@/api'
import type { WaybillForm } from './waybillFormTypes'

export function useWaybillAutosave(form: Ref<WaybillForm>, buildPayload: () => Record<string, unknown>) {
  let autosaveTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleAutosave() {
    if (autosaveTimer) clearTimeout(autosaveTimer)
    autosaveTimer = setTimeout(() => { autosave() }, 1500)
  }

  async function autosave() {
    if (!form.value.id) return // new, not yet created
    try {
      await apiFetch(`/trips/${form.value.id}`, {
        method: 'PATCH',
        body: buildPayload() as any,
      })
    } catch (e) {
      console.warn('[wbf] autosave error', e)
    }
  }

  return { scheduleAutosave, autosave }
}
