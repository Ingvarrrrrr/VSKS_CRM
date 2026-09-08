// useStaffCreateUser.ts — диалог «Добавить сотрудника». Дословный перенос
// из StaffView.vue.
import { reactive, nextTick, watch } from 'vue'
import { apiFetch } from '@/api'
import { unformatPhone } from '@/utils/phoneFormat'
import type { ToastType } from '@/composables/useToast'
import type { UserItem } from './staffTypes'
import { normalizeDepartment, randomAvatarId } from './staffLabels'

export function useStaffCreateUser(options: {
  users: { value: UserItem[] }
  loadDicts: (orgId?: number | null) => Promise<void>
  assignableOrganizations: { value: any[] }
  currentOrgId: number | null
  showSnack: (text: string, color?: ToastType) => void
  loadDeptTree: () => Promise<void>
  refreshHierarchy: () => void
  // Диалог владеет собственной <v-form ref="createFormRef">; сюда пробрасывается
  // его validate() через defineExpose (см. StaffCreateUserDialog.vue).
  validateForm: () => Promise<{ valid: boolean } | undefined> | { valid: boolean } | undefined
}) {
  const { users, loadDicts, assignableOrganizations, currentOrgId, showSnack, loadDeptTree, refreshHierarchy, validateForm } = options

  const createDialog = reactive({
    show: false, last_name: '', first_name: '', middle_name: '', email: '', password: '', password_confirm: '',
    role: 'employee', city: '', department: '', position: '', phone: '', work_phone: '', telegram_id: '', avatar: '', saving: false,
    org_id: null as number | null, subsidy_id: null as number | null,
  }) as any

  // Pre-load dicts when superadmin picks an org in createDialog
  watch(() => createDialog.org_id, (id) => { if (id) loadDicts(id) })

  // Владелец, 2026-09-01: «плюсик» из отдела/орг-контекста (HierarchyView) обязан
  // предзаполнить организацию и отдел, а не открывать пустую форму — иначе
  // новый сотрудник (напр. Новичкова, добавленная через «+» в «Администрации»
  // ВСКС) создаётся без орг/отдела и требует ручной правки. ctx — опционален:
  // кнопка «Добавить сотрудника» в шапке StaffView/HierarchyView не привязана
  // ни к какому отделу, там предзаполнять нечем (остаётся currentOrgId/пусто).
  function openCreateUser(ctx?: { orgId?: number; departmentName?: string }) {
    createDialog.last_name = ''
    createDialog.first_name = ''
    createDialog.middle_name = ''
    createDialog.email = ''
    createDialog.password = ''
    createDialog.password_confirm = ''
    createDialog.role = 'employee'
    createDialog.city = ''
    createDialog.department = ctx?.departmentName || ''
    createDialog.position = ''
    createDialog.phone = ''
    createDialog.work_phone = ''
    createDialog.telegram_id = ''
    createDialog.avatar = ''
    createDialog.org_id = ctx?.orgId ?? currentOrgId
    createDialog.subsidy_id = null
    createDialog.saving = false
    createDialog.show = true
    // Грузим орг, в которые пользователь реально может создавать сотрудника
    // (assignable = свои + управляемые). Для менеджера с >1 орг это включит пикер
    // (canPickOrg). Если протухший createDialog.org_id не входит в список — сбрасываем.
    apiFetch<any[]>('/organizations/assignable').then(r => {
      assignableOrganizations.value = r
      if (createDialog.org_id && !r.some(o => o.id === createDialog.org_id)) {
        createDialog.org_id = r.length ? r[0].id : null
      }
    }).catch(() => {})
  }

  async function saveUser() {
    // Подсветить «стрелочками» (красные поля + сообщения) все незаполненные/невалидные
    // поля и проскроллить к первому проблемному, вместо общего непонятного снэкбара.
    const res = await validateForm()
    if (res && res.valid === false) {
      await nextTick()
      const firstErr = document.querySelector('.v-dialog--active .v-input--error, .v-dialog .v-input--error') as HTMLElement | null
      firstErr?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      firstErr?.querySelector('input, textarea')?.dispatchEvent(new Event('focus'))
      showSnack('Заполните выделенные поля', 'error')
      return
    }
    if (createDialog.password !== createDialog.password_confirm) {
      showSnack('Пароли не совпадают', 'error')
      return
    }
    if (!createDialog.email) {
      showSnack('Email обязателен', 'error')
      return
    }
    createDialog.saving = true
    try {
      const u = await apiFetch<UserItem>('/users/', {
        method: 'POST',
        body: {
          email: createDialog.email,
          last_name: createDialog.last_name || null,
          first_name: createDialog.first_name || null,
          middle_name: createDialog.middle_name || null,
          password: createDialog.password,
          role: createDialog.role,
          city: createDialog.city || null,
          department: normalizeDepartment(createDialog.department) || null,
          position: createDialog.position || null,
          phone: unformatPhone(createDialog.phone) || null,
          work_phone: unformatPhone(createDialog.work_phone) || null,
          telegram_id: createDialog.telegram_id || null,
          avatar: createDialog.avatar || randomAvatarId(),
          org_id: createDialog.org_id ?? null,
        },
      })
      users.value = [...users.value, u]
      createDialog.show = false
      showSnack('Сотрудник создан')
      // Reload dept tree if department was specified
      if (createDialog.department) {
        await loadDeptTree()
      }
      refreshHierarchy()
    } catch (e: any) {
      showSnack(e?.payload?.detail || e?.payload?.message || e?.message || 'Ошибка', 'error')
    } finally {
      createDialog.saving = false
    }
  }

  return { createDialog, openCreateUser, saveUser }
}
