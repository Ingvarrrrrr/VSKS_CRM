// Скачивание .docx и печать путевого листа (Phase 30.2: A5 легковой/автобус,
// A4 грузовой). Вынесено из FleetWaybillFormView.vue без изменения поведения.
import { ref, type Ref } from 'vue'
import type { WaybillForm } from './waybillFormTypes'

export function useWaybillDocxPrint(form: Ref<WaybillForm>, isLightVehicle: Ref<boolean>) {
  const downloadingDocx = ref(false)

  async function downloadDocx() {
    if (!form.value.id) return
    downloadingDocx.value = true
    try {
      const token = localStorage.getItem('auth_token')
      const res = await fetch(`/api/trips/${form.value.id}/waybill.docx`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Путевой_лист_${form.value.number || form.value.id}.docx`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('[wbf] docx download error', e)
    } finally {
      downloadingDocx.value = false
    }
  }

  function onPrint() {
    document.documentElement.dataset.printFormat = isLightVehicle.value ? 'a5' : 'a4'
    window.print()
  }

  return { downloadingDocx, downloadDocx, onPrint }
}
