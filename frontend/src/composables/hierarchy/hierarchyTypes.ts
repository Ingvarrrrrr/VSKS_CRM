// Общие типы для HierarchyView и его композаблов/компонентов.
// Один источник структуры графа — все композаблы читают отсюда (ПРАВИЛО №6).

export interface GraphData {
  orgs: { id: number; name: string; inn?: string | null; color?: string | null; contractor_id?: number | null }[]
  departments: { id: number; name: string; org_id: number; head_user_id: number | null; member_ids: number[] }[]
  users: { id: number; full_name: string | null; username: string; role: string; org_id: number; extra_org_ids: number[]; avatar: string | null; position: string | null }[]
  user_user_edges: { id: number; manager_id: number; subordinate_id: number }[]
  user_dept_edges: { id: number; manager_user_id: number; dept_id: number }[]
  user_org_edges: { id: number; manager_user_id: number; org_id: number }[]
  dept_dept_edges?: { parent_id: number; dept_id: number }[]
  org_org_edges?: { parent_org_id: number; org_id: number }[]
}

export interface OrgLite {
  id: number
  name: string
  inn?: string | null
  color?: string | null
  contractor_id?: number | null
}

export interface OrgFormState {
  show: boolean
  name: string
  full_name: string
  inn: string
  kpp: string
  ogrn: string
  address: string
  signatory_last_name: string
  signatory_first_name: string
  signatory_middle_name: string
  signatory_position: string
}
