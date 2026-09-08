// useProductsImport.ts — импорт товаров из Excel + скачивание шаблона.
// Дословный перенос из ProductsView.vue.
import { reactive } from 'vue'
import type { ToastType } from '@/composables/useToast'

export function useProductsImport(options: {
  load: () => Promise<void>
  showSnack: (text: string, color?: ToastType) => void
}) {
  const { load, showSnack } = options

  const importDialog = reactive({
    show: false, step: 1, file: null as File | null, fileList: [] as File[],
    loading: false, result: null as { created: number; skipped: number; errors: { row: number; name: string; message: string }[] } | null,
  })

  function closeImportDialog() {
    importDialog.show = false
    importDialog.step = 1
    importDialog.file = null
    importDialog.fileList = []
    importDialog.result = null
    if (importDialog.result?.created) load()
  }

  async function downloadTemplate() {
    const token = localStorage.getItem('auth_token')
    const res = await fetch('/api/products/import/template', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) { showSnack('Ошибка загрузки шаблона', 'error'); return }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'Шаблон_импорта_товаров.xlsx'; a.click()
    URL.revokeObjectURL(url)
  }

  async function doImport() {
    if (!importDialog.file) return
    importDialog.loading = true
    try {
      const fd = new FormData()
      fd.append('file', importDialog.file)
      const token = localStorage.getItem('auth_token')
      const res = await fetch('/api/products/import', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        showSnack(err.detail || 'Ошибка импорта', 'error')
        return
      }
      importDialog.result = await res.json()
      importDialog.step = 2
      showSnack(`Импорт завершён: создано ${importDialog.result!.created}`)
      await load()
    } catch {
      showSnack('Ошибка импорта', 'error')
    } finally {
      importDialog.loading = false
    }
  }

  return { importDialog, closeImportDialog, downloadTemplate, doImport }
}
