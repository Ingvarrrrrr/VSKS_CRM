// Чистые константы и геометрия карточек графа иерархии — без реактивного состояния.
// Вынесено из HierarchyView.vue как есть (без изменения формул).

// ── Constants ──────────────────────────────────────────────────────────────────
export const DEPT_W = 268     // dept container width in px
export const USER_W = 240     // user node width in px
export const USER_H = 88      // user node height in px (name + position + role + counts)
export const DEPT_HEADER_H = 76   // base header height (синхронизирован с min-height .hnode-dept-header-bar): padding+toprow+gap+1 строка
export const USER_GAP = 8
export const DEPT_PAD_Y = 12  // bottom padding

// Phase 30: динамическая высота шапки отдела — растёт если название многострочное.
// При DEPT_W=268 и шрифте ~14px помещается ~24 символа в строке (с учётом padding/icons).
// Каждая дополнительная строка +18px.
export const DEPT_NAME_CHARS_PER_LINE = 28
export const DEPT_HEADER_LINE_H = 18
export const DEPT_HEADER_BADGE_H = 22  // высота строки org-бейджа в шапке отдела (когда орг > 1)

export function deptHeaderHeight(name: string | undefined | null, hasOrgBadge = false): number {
  const len = (name || '').length
  const lines = Math.max(1, Math.ceil(len / DEPT_NAME_CHARS_PER_LINE))
  return DEPT_HEADER_H + (lines - 1) * DEPT_HEADER_LINE_H + (hasOrgBadge ? DEPT_HEADER_BADGE_H : 0)
}

export function calcDeptHeight(memberCount: number, name?: string, hasOrgBadge = false) {
  return deptHeaderHeight(name, hasOrgBadge) + Math.max(memberCount, 0) * (USER_H + USER_GAP) + DEPT_PAD_Y
}

export function mkDeptStyle(memberCount: number, name?: string, hasOrgBadge = false): Record<string, string> {
  return {
    width: `${DEPT_W}px`,
    height: `${Math.max(calcDeptHeight(memberCount, name, hasOrgBadge), 80)}px`,
    background: 'rgba(0, 105, 92, 0.05)',
    border: '2px dashed #00897b',
    borderRadius: '10px',
  }
}

// ── Rank sorting ───────────────────────────────────────────────────────────────

export function getPositionRank(position: string | null): number {
  if (!position) return 10
  const p = position.toLowerCase()
  if (p.includes('начальник') || p.includes('директор') || p.includes('руководитель')) return 1
  if (p.includes('зам')) return 2
  if (p.includes('главный') || p.includes('ведущий')) return 3
  if (p.includes('старший')) return 4
  if (p.includes('специалист') || p.includes('инженер')) return 5
  return 8
}

export function sortDeptMembers(
  members: number[],
  headUserId: number | null,
  userMap: Map<number, any>,
  savedOrder: number[] | null
): number[] {
  if (savedOrder?.length) {
    const saved = savedOrder.filter(id => members.includes(id))
    const missing = members.filter(id => !saved.includes(id))
    return [...saved, ...missing]
  }
  return [...members].sort((a, b) => {
    if (a === headUserId) return -1
    if (b === headUserId) return 1
    const ra = getPositionRank(userMap.get(a)?.position || null)
    const rb = getPositionRank(userMap.get(b)?.position || null)
    return ra - rb
  })
}

export function getInitials(name: string | null, username: string): string {
  if (name) {
    const parts = name.trim().split(' ')
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
    return parts[0].slice(0, 2).toUpperCase()
  }
  return username.slice(0, 2).toUpperCase()
}
