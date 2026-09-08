// useVehicleListTemplate.ts — скачивание Excel-шаблона импорта ТС (шапка
// реестра). Дословный перенос из VehicleListView.vue.
//
// Тот же подход, что в VehicleImportDialog.vue (downloadTemplate): обычный
// fetch + blob, а не apiFetch — apiFetch не умеет бинарные ответы. Логика не
// продублирована один-в-один по коду, но использует тот же эндпоинт и тот же
// разбор Content-Disposition — переиспользуем идею, а не плодим третий вариант.
import { ref } from 'vue'

export function useVehicleListTemplate(options: { onError: (err: any) => void }) {
  const loadingTemplate = ref(false)

  async function downloadTemplate() {
    loadingTemplate.value = true
    try {
      const token = localStorage.getItem('auth_token')
      const res = await fetch('/api/vehicles/import-template', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) {
        let detail = `HTTP ${res.status}`
        try {
          const errBody = await res.json()
          detail = errBody?.detail || errBody?.message || errBody?.payload?.message || detail
        } catch {
          // тело ответа не JSON — оставляем причину по умолчанию (HTTP-статус)
        }
        throw new Error(detail)
      }
      const blob = await res.blob()

      let filename = 'Шаблон_импорта_транспорта.xlsx'
      const cd = res.headers.get('Content-Disposition') || ''
      const utf8Match = cd.match(/filename\*=UTF-8''([^;]+)/i)
      const plainMatch = cd.match(/filename="?([^";]+)"?/i)
      if (utf8Match) {
        try { filename = decodeURIComponent(utf8Match[1]) } catch { /* оставляем дефолт */ }
      } else if (plainMatch) {
        filename = plainMatch[1]
      }

      const blobUrl = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(blobUrl)
    } catch (err: any) {
      options.onError(new Error(err?.message || 'Не удалось скачать шаблон'))
    } finally {
      loadingTemplate.value = false
    }
  }

  return { loadingTemplate, downloadTemplate }
}
