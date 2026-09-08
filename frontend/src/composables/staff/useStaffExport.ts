// useStaffExport.ts — колонки/строки для RegistryExportButton вкладок
// «Отделы» и «Иерархия». Дословный перенос из StaffView.vue.
import { flatDepts } from './useStaffDepartments'
import { ROLE_LABELS } from './staffLabels'
import type { UserItem } from './staffTypes'

export function useStaffExport(options: {
  deptTree: { value: any[] }
  users: { value: UserItem[] }
}) {
  const { deptTree, users } = options

  function getDeptExportColumns() {
    return [
      { key: 'dept', title: 'Отдел' },
      { key: 'head', title: 'Начальник отдела' },
      { key: 'employee', title: 'Сотрудник' },
      { key: 'position', title: 'Должность' },
    ]
  }
  function getDeptExportRows() {
    const rows: Array<Record<string, any>> = []
    for (const d of flatDepts(deptTree.value)) {
      const members = d.members || []
      if (members.length === 0) {
        rows.push({ dept: d.name, head: d.head_user_name || '', employee: '', position: '' })
      } else {
        for (const m of members) {
          rows.push({
            dept: d.name,
            head: d.head_user_name || '',
            employee: m.user_name || '',
            position: m.position || m.user_role || '',
          })
        }
      }
    }
    return rows
  }

  function getHierarchyExportColumns() {
    return [
      { key: 'full_name', title: 'ФИО' },
      { key: 'role', title: 'Роль' },
      { key: 'position', title: 'Должность' },
      { key: 'department', title: 'Отдел' },
    ]
  }
  function getHierarchyExportRows() {
    return users.value.map((u: any) => ({
      full_name: u.full_name || u.username,
      role: ROLE_LABELS[u.role] || u.role,
      position: u.position || '',
      department: u.department || '',
    }))
  }

  return { getDeptExportColumns, getDeptExportRows, getHierarchyExportColumns, getHierarchyExportRows }
}
