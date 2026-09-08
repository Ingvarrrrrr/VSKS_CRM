// useStaffUserImport.ts — импорт сотрудников из Excel. Дословный перенос
// из StaffView.vue.
import { reactive } from 'vue'
import type { ToastType } from '@/composables/useToast'

export function useStaffUserImport(options: {
  showSnack: (text: string, color?: ToastType) => void
  loadUsers: () => Promise<void>
}) {
  const { showSnack, loadUsers } = options

  const userImportDialog = reactive({
    show: false, file: null as File | null, loading: false,
    result: null as { created: number; skipped: number; errors: { row: number; error: string }[] } | null,
  })

  async function downloadUserTemplate() {
    const token = localStorage.getItem('auth_token')
    const resp = await fetch('/api/users/import/template', {
      headers: { Authorization: `Bearer ${token}` },
    })
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'Шаблон_импорта_сотрудников.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  }

  async function doUserImport() {
    if (!userImportDialog.file) return
    userImportDialog.loading = true
    userImportDialog.result = null
    try {
      const token = localStorage.getItem('auth_token')
      const fd = new FormData()
      fd.append('file', userImportDialog.file)
      const resp = await fetch('/api/users/import/excel', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.message || err.detail || `Ошибка ${resp.status}`)
      }
      userImportDialog.result = await resp.json()
      if (userImportDialog.result!.created > 0) {
        showSnack(`Импортировано ${userImportDialog.result!.created} пользователей`)
        loadUsers()
      }
    } catch (e: any) {
      showSnack(e.message || 'Ошибка импорта', 'error')
    } finally {
      userImportDialog.loading = false
    }
  }

  return { userImportDialog, downloadUserTemplate, doUserImport }
}
