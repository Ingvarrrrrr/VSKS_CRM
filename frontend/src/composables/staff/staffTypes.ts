// staffTypes.ts — общие типы вкладки «Персонал». Дословный перенос из StaffView.vue.
export interface UserItem {
  id: number
  username: string
  full_name?: string
  last_name?: string
  first_name?: string
  middle_name?: string
  role: string
  city?: string
  department?: string
  position?: string
  email?: string
  avatar?: string
  photo_url?: string | null
  has_signature?: boolean
  inn?: string
  org_id?: number
}

export interface SubordinateItem { id: number; username: string; full_name?: string; role: string; avatar?: string }

export interface TreeNode extends UserItem { subordinates?: SubordinateItem[] }

export type OrgEntry = {
  id: number | null
  dept_id: number | null
  org_id: number
  org_name: string
  dept_name: string
  position: string
  salary_amount: number | null
  employment_percent: number | null
  hired_at: string | null
  dept_assigned_at: string | null
  position_assigned_at: string | null
  _idx: number
}
