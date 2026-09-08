import { ref } from 'vue'

// ─────────────────────────────────────────────────────────────────────────
// Диалог ошибки карточки ТС — общее состояние (по образцу useToast.ts:
// module-level singleton), чтобы showError() можно было вызывать из любого
// композабла карточки (useVehicleRecord и т.п.), а сам диалог рисовать один
// раз во view (VehicleErrorDialog.vue).
// ─────────────────────────────────────────────────────────────────────────

const errorDialogShow = ref(false)
const errorMsg = ref('')
const errorCode = ref('')
const errorCorrelationId = ref('')

export function useVehicleErrorDialog() {
  function showError(err: any) {
    const payload = err?.payload ?? err?.detail ?? err
    errorMsg.value = payload?.message ?? payload?.detail ?? String(err)
    errorCode.value = payload?.code ?? ''
    errorCorrelationId.value = payload?.correlation_id ?? ''
    errorDialogShow.value = true
  }

  return {
    errorDialogShow,
    errorMsg,
    errorCode,
    errorCorrelationId,
    showError,
  }
}
