// useVehicleListErrorDialog.ts — диалог ошибки реестра ТС. Дословный перенос
// из VehicleListView.vue.
//
// Не переиспользует module-level singleton composables/fleet/useVehicleErrorDialog.ts:
// тот композабл специально держит ОБЩЕЕ состояние диалога для карточки ТС
// (vehicle-detail), чтобы showError() можно было звать из разных композаблов
// одной карточки. Реестр ТС — отдельная страница с собственным жизненным
// циклом; подключение к общему singleton расшарило бы видимость диалога между
// список/карточка (поведение изменилось бы). Здесь состояние локальное,
// как и было в исходном VehicleListView.vue.
import { reactive } from 'vue'

export function useVehicleListErrorDialog() {
  const errorDialog = reactive({ show: false, message: '', code: '', correlationId: '' })

  function showError(err: any) {
    const payload = err?.payload ?? err?.detail ?? err
    const message = payload?.message ?? payload?.detail ?? String(err)
    const code = payload?.code ?? ''
    const correlationId = payload?.correlation_id ?? ''
    errorDialog.message = message
    errorDialog.code = code
    errorDialog.correlationId = correlationId
    errorDialog.show = true
  }

  function copyError() {
    const text = [
      errorDialog.message,
      errorDialog.code ? `Код: ${errorDialog.code}` : '',
      errorDialog.correlationId ? `ID: ${errorDialog.correlationId}` : '',
    ].filter(Boolean).join('\n')
    navigator.clipboard.writeText(text).catch(() => {})
  }

  return { errorDialog, showError, copyError }
}
