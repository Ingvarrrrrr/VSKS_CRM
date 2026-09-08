// useStaffDeptImport.ts — импорт отделов из Excel. Дословный перенос
// из StaffView.vue.
import { ref } from 'vue'
import type { ToastType } from '@/composables/useToast'

export function useStaffDeptImport(options: {
  showSnack: (text: string, color?: ToastType) => void
  loadDeptTree: () => Promise<void>
}) {
  const { showSnack, loadDeptTree } = options

  const deptImportDialog = ref(false)
  const deptImportFile = ref<File | null>(null)
  const deptImporting = ref(false)
  const deptImportResult = ref<any>(null)

  async function downloadDeptTemplate() {
    const token = localStorage.getItem('auth_token')
    const res = await fetch('/api/departments/import/template', { headers: { Authorization: `Bearer ${token}` } })
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'Шаблон_импорта_отделов.xlsx'; a.click()
    URL.revokeObjectURL(url)
  }

  async function doDeptImport() {
    if (!deptImportFile.value) return
    deptImporting.value = true
    deptImportResult.value = null
    try {
      const fd = new FormData()
      fd.append('file', deptImportFile.value)
      const token = localStorage.getItem('auth_token')
      const res = await fetch('/api/departments/import/excel', {
        method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: fd,
      })
      deptImportResult.value = await res.json()
      await loadDeptTree()
    } catch (e) { showSnack('Ошибка импорта', 'error') }
    finally { deptImporting.value = false }
  }

  return { deptImportDialog, deptImportFile, deptImporting, deptImportResult, downloadDeptTemplate, doDeptImport }
}
