// Единственная функция создания отдела (Правило владельца, 28.10.2026 —
// раньше было две разные формы: оранжевая кнопка в шапке StaffView.vue не
// передавала org_id (отдел уходил в орг по умолчанию пользователя, «ни хрена
// не сохранилось»), зелёная кнопка в Иерархии (HierarchyNewDeptDialog) org_id
// передавала, но без поля субсидии. Теперь и StaffView.vue (кнопка в шапке +
// кнопка «Добавить отдел» на вкладке «Отделы»), и HierarchyView.vue (кнопка
// «Добавить отдел») используют этот композабл + components/departments/
// DeptCreateDialog.vue — один POST /departments/, одна форма.
//
// Открывается БЕЗ переключения вкладки — там, где стоит пользователь
// (ПРАВИЛО владельца: оранжевая кнопка не должна прыгать на вкладку «Отделы»).
import { ref, computed, watch } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import { filterSubsidiesByOrg } from './subsidiesForOrg'

export interface DeptCreateOptions {
  showSnack: (text: string, color?: ToastType) => void
  // Вызывается после успешного создания — обновить дерево отделов/граф
  // иерархии в том месте, которое вызвало диалог (StaffView или HierarchyView).
  onCreated: (dept: any) => void | Promise<void>
}

export function useDeptCreate(options: DeptCreateOptions) {
  const { showSnack, onCreated } = options

  const show = ref(false)
  const saving = ref(false)
  const loadingLists = ref(false)
  const orgs = ref<{ id: number; name: string }[]>([])
  const subsidiesAll = ref<any[]>([])
  const form = ref({ name: '', org_id: null as number | null, subsidy_id: null as number | null })

  const subsidyOptions = computed(() => filterSubsidiesByOrg(subsidiesAll.value, form.value.org_id))

  // Субсидия другой организации не может остаться выбранной при смене орг.
  watch(() => form.value.org_id, () => {
    if (form.value.subsidy_id && !subsidyOptions.value.some((s: any) => s.id === form.value.subsidy_id)) {
      form.value.subsidy_id = null
    }
  })

  async function open(defaultOrgId?: number | null) {
    form.value = { name: '', org_id: defaultOrgId ?? null, subsidy_id: null }
    show.value = true
    loadingLists.value = true
    try {
      const [orgsList, subsList] = await Promise.all([
        apiFetch<any[]>('/organizations/'),
        apiFetch<any[]>('/subsidies/'),
      ])
      orgs.value = orgsList || []
      subsidiesAll.value = subsList || []
      if (form.value.org_id === null && orgs.value.length === 1) form.value.org_id = orgs.value[0]?.id ?? null
    } catch {
      orgs.value = []
      subsidiesAll.value = []
    } finally {
      loadingLists.value = false
    }
  }

  async function create() {
    const name = form.value.name.trim()
    if (!name || !form.value.org_id) return
    saving.value = true
    try {
      const dept = await apiFetch<any>('/departments/', {
        method: 'POST',
        body: JSON.stringify({ name, org_id: form.value.org_id, subsidy_id: form.value.subsidy_id }),
      })
      show.value = false
      showSnack(`Отдел «${name}» создан`)
      await onCreated(dept)
    } catch (e: any) {
      showSnack(e?.detail || 'Ошибка создания отдела', 'error')
    } finally {
      saving.value = false
    }
  }

  return { show, saving, loadingLists, orgs, subsidyOptions, form, open, create }
}
