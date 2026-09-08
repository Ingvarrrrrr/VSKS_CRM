// Граф иерархии: загрузка/построение узлов и рёбер VueFlow, авторасстановка,
// перетаскивание сотрудников между отделами (DnD), создание/удаление связей.
// Вынесено из HierarchyView.vue одним композаблом (канвас+DnD — одна ответственность,
// см. задание на рефакторинг), без изменения логики.
import { ref, nextTick, onUnmounted, type Ref } from 'vue'
import { useVueFlow, type Node, type Edge, type Connection } from '@vue-flow/core'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { GraphData, OrgLite } from './hierarchyTypes'
import {
  DEPT_W, USER_W, USER_H, DEPT_HEADER_H, USER_GAP, DEPT_PAD_Y,
  deptHeaderHeight, calcDeptHeight, mkDeptStyle, getPositionRank, sortDeptMembers, getInitials,
} from './useHierarchyLayout'

export interface HierarchyGraphOptions {
  showSnack: (text: string, color?: ToastType) => void
  getOrgColor: (orgId: number, fallbackIdx: number) => string
  pickOrgColor: (orgId: number) => void
  emitDataChanged: () => void
  onAddMember: (deptId: number) => void
  onDeleteDept: (deptId: number) => void
  onEditUser: (id: number) => void
  onEditDept: (id: number) => void
  onOpenOrg: (org: OrgLite) => void
  setDefaultDeptOrgId: (orgId: number) => void
}

// Position persistence
const POS_KEY = 'hierarchy_node_positions'
const ORDER_KEY = 'hierarchy_dept_order'

function loadPositions(): Record<string, { x: number; y: number }> {
  try { return JSON.parse(localStorage.getItem(POS_KEY) || '{}') } catch { return {} }
}
function savePositions(ns: Node[]) {
  const pos: Record<string, { x: number; y: number }> = {}
  for (const n of ns) pos[n.id] = { x: n.position.x, y: n.position.y }
  localStorage.setItem(POS_KEY, JSON.stringify(pos))
}
function loadDeptOrders(): Record<number, number[]> {
  try { return JSON.parse(localStorage.getItem(ORDER_KEY) || '{}') } catch { return {} }
}
function saveDeptOrder(deptId: number, userIds: number[]) {
  const all = loadDeptOrders()
  all[deptId] = userIds
  localStorage.setItem(ORDER_KEY, JSON.stringify(all))
}

export function useHierarchyGraph(lastGraphData: Ref<GraphData | null>, opts: HierarchyGraphOptions) {
  const nodes = ref<Node[]>([])
  const edges = ref<Edge[]>([])
  const loading = ref(false)
  const graphOrgs = ref<{ id: number; name: string }[]>([])
  const _orgNameMap = new Map<number, string>()

  const { addEdges, removeEdges, fitView, onEdgeClick, onNodeDragStop, onNodeDoubleClick, onNodesInitialized } = useVueFlow()

  // ── Build graph ────────────────────────────────────────────────────────────────

  function buildGraph(data: GraphData) {
    const savedPos = loadPositions()
    const deptOrders = loadDeptOrders()
    const newNodes: Node[] = []
    const newEdges: Edge[] = []

    // Store orgs list for dialogs
    graphOrgs.value = data.orgs
    if (data.orgs.length === 1) opts.setDefaultDeptOrgId(data.orgs[0].id)

    // Build org name map for extra org badges
    _orgNameMap.clear()
    data.orgs.forEach(o => _orgNameMap.set(o.id, o.name))
    const orgNameMap = _orgNameMap

    // Build user lookup map for rank sorting
    const userMap = new Map(data.users.map(u => [u.id, u]))

    // Map userId → array of { deptId, idx } — user can be in multiple depts
    const userDeptMap: Record<number, { deptId: number; idx: number }[]> = {}
    for (const dept of data.departments) {
      const savedOrder = deptOrders[dept.id] || null
      const sorted = sortDeptMembers(dept.member_ids, dept.head_user_id, userMap, savedOrder)
      let idx = 0
      for (const uid of sorted) {
        if (!userDeptMap[uid]) userDeptMap[uid] = []
        userDeptMap[uid].push({ deptId: dept.id, idx: idx++ })
      }
    }

    // Org nodes
    const userRole = localStorage.getItem('user_role') || ''
    const canDeleteOrg = ['superadmin', 'admin', 'account_owner'].includes(userRole)
    const canDeleteUser = ['superadmin', 'admin', 'account_owner', 'manager'].includes(userRole)
    data.orgs.forEach((org, oi) => {
      const id = `org-${org.id}`
      const oColor = opts.getOrgColor(org.id, oi)
      newNodes.push({
        id, type: 'org',
        position: savedPos[id] || { x: 80 + oi * 320, y: 60 },
        data: { label: org.name, inn: org.inn || '', orgColor: oColor, orgId: org.id, onColorPick: opts.pickOrgColor, canDeleteOrg },
        draggable: true,
      })
    })

    // Dept nodes
    const orgList = data.orgs || []
    const hasOrgBadge = orgList.length > 1  // орг-бейдж в шапке только когда > 1 орг в контуре
    data.departments.forEach((dept, di) => {
      const id = `dept-${dept.id}`
      const mc = dept.member_ids.length
      const orgIdx = orgList.findIndex((o: any) => o.id === dept.org_id)
      const orgName = hasOrgBadge ? orgList[orgIdx]?.name : null
      const orgColor = opts.getOrgColor(dept.org_id, orgIdx >= 0 ? orgIdx : 0)
      newNodes.push({
        id, type: 'dept',
        position: savedPos[id] || { x: 80 + di * (DEPT_W + 40), y: 200 },
        style: { ...mkDeptStyle(mc, dept.name, hasOrgBadge), background: `${orgColor}0D`, border: `2px dashed ${orgColor}` },
        data: {
          label: dept.name,
          memberCount: mc,
          headUserId: dept.head_user_id,
          deptId: dept.id,
          orgId: dept.org_id,
          orgName,
          orgColor,
          onAddMember: (deptId: number) => opts.onAddMember(deptId),
          onDelete: (deptId: number) => opts.onDeleteDept(deptId),
        },
        draggable: true,
        zIndex: 0,
      })
    })

    // User nodes — create one per dept membership + one for free users
    let freeIdx = 0
    for (const user of data.users) {
      const depts = userDeptMap[user.id] || []
      const extraOrgNames = (user.extra_org_ids || [])
        .filter(oid => oid !== user.org_id)
        .map(oid => orgNameMap.get(oid) || `Орг#${oid}`)
      const orgCount = 1 + (user.extra_org_ids || []).filter((oid: number) => oid !== user.org_id).length

      if (depts.length > 0) {
        // Create a node for each dept the user belongs to
        for (let ci = 0; ci < depts.length; ci++) {
          const di = depts[ci]
          const dept = data.departments.find(d => d.id === di.deptId)
          const isHead = !!dept && dept.head_user_id === user.id
          const uOrgId = dept ? dept.org_id : user.org_id
          const uOrgIdx = orgList.findIndex((o: any) => o.id === uOrgId)
          const uOrgColor = opts.getOrgColor(uOrgId, uOrgIdx >= 0 ? uOrgIdx : 0)
          // Unique id per dept placement (first keeps original id for edge compatibility)
          const nodeId = ci === 0 ? `user-${user.id}` : `user-${user.id}-d${di.deptId}`
          const headerH = deptHeaderHeight(dept?.name, hasOrgBadge)
          const defaultRelPos = { x: 10, y: headerH + 4 + di.idx * (USER_H + USER_GAP) }
          // Страховка: если сохранённая pos наезжает на шапку — сбрасываем на корректную
          const sp = savedPos[nodeId]
          const pos = (sp && typeof sp.y === 'number' && sp.y >= headerH) ? sp : defaultRelPos
          newNodes.push({
            id: nodeId, type: 'user',
            parentNode: `dept-${di.deptId}`,
            position: pos,
            data: { label: user.full_name || user.username, role: user.role, initials: getInitials(user.full_name, user.username), isHead, position: user.position, extraOrgNames, orgColor: uOrgColor, orgCount, userId: user.id, orgId: uOrgId, deptOrgName: dept ? (orgNameMap.get(dept.org_id) || '') : '', userOrgs: (user as any).user_orgs || [], canDeleteUser, photoUrl: (user as any).photo_url || null },
            draggable: true,
            zIndex: 1000,
          })
        }
      } else {
        const col = freeIdx % 4
        const row = Math.floor(freeIdx / 4)
        const freeOrgIdx = orgList.findIndex((o: any) => o.id === user.org_id)
        const freeOrgColor = opts.getOrgColor(user.org_id, freeOrgIdx >= 0 ? freeOrgIdx : 0)
        const freeId = `user-${user.id}`
        ;(user as any)._photoUrl = (user as any).photo_url || null
        newNodes.push({
          id: freeId, type: 'user',
          position: savedPos[freeId] || { x: 80 + col * 240, y: 600 + row * 80 },
          data: { label: user.full_name || user.username, role: user.role, initials: getInitials(user.full_name, user.username), isHead: false, position: user.position, extraOrgNames, orgColor: freeOrgColor, orgCount, userId: user.id, orgId: user.org_id, deptOrgName: orgNameMap.get(user.org_id) || '', userOrgs: (user as any).user_orgs || [], canDeleteUser, photoUrl: (user as any).photo_url || null },
          draggable: true,
        })
        freeIdx++
      }
    }

    // user-user edges
    for (const e of data.user_user_edges) {
      newEdges.push({
        id: `uu-${e.id}`,
        source: `user-${e.manager_id}`,
        target: `user-${e.subordinate_id}`,
        type: 'smoothstep',
        animated: true,
        style: { stroke: '#4caf50', strokeWidth: 2 },
        markerEnd: { type: 'arrowclosed', color: '#4caf50' } as any,
        label: '×',
        labelStyle: { cursor: 'pointer', fill: '#f44336', fontWeight: 'bold', fontSize: '14px' },
        data: { relation_id: e.id, relation_type: 'user_user' },
      })
    }

    // user-dept edges (manager of dept)
    for (const e of data.user_dept_edges) {
      newEdges.push({
        id: `ud-${e.id}`,
        source: `user-${e.manager_user_id}`,
        target: `dept-${e.dept_id}`,
        type: 'smoothstep',
        style: { stroke: '#ff9800', strokeWidth: 2, strokeDasharray: '6 3' },
        markerEnd: { type: 'arrowclosed', color: '#ff9800' } as any,
        label: '×',
        labelStyle: { cursor: 'pointer', fill: '#f44336', fontWeight: 'bold', fontSize: '14px' },
        data: { relation_id: e.id, relation_type: 'user_dept' },
      })
    }

    // user-org edges (manager of entire org — purple)
    for (const e of (data.user_org_edges || [])) {
      newEdges.push({
        id: `uo-${e.id}`,
        source: `user-${e.manager_user_id}`,
        target: `org-${e.org_id}`,
        type: 'smoothstep',
        animated: true,
        style: { stroke: '#9c27b0', strokeWidth: 2.5 },
        markerEnd: { type: 'arrowclosed', color: '#9c27b0' } as any,
        label: '×',
        labelStyle: { cursor: 'pointer', fill: '#f44336', fontWeight: 'bold', fontSize: '14px' },
        data: { relation_id: e.id, relation_type: 'user_org' },
      })
    }

    // dept-dept edges (вышестоящее подразделение → дочернее) — синий
    for (const e of (data.dept_dept_edges || [])) {
      newEdges.push({
        id: `dd-${e.dept_id}`,
        source: `dept-${e.parent_id}`,
        target: `dept-${e.dept_id}`,
        type: 'smoothstep',
        style: { stroke: '#1976d2', strokeWidth: 2 },
        markerEnd: { type: 'arrowclosed', color: '#1976d2' } as any,
        label: '×',
        labelStyle: { cursor: 'pointer', fill: '#f44336', fontWeight: 'bold', fontSize: '14px' },
        data: { relation_id: e.dept_id, relation_type: 'dept_dept' },
      })
    }

    // org-org edges (вышестоящая организация → подчинённая) — тёмно-фиолетовый
    for (const e of (data.org_org_edges || [])) {
      newEdges.push({
        id: `oo-${e.org_id}`,
        source: `org-${e.parent_org_id}`,
        target: `org-${e.org_id}`,
        type: 'smoothstep',
        style: { stroke: '#7b1fa2', strokeWidth: 2.5 },
        markerEnd: { type: 'arrowclosed', color: '#7b1fa2' } as any,
        label: '×',
        labelStyle: { cursor: 'pointer', fill: '#f44336', fontWeight: 'bold', fontSize: '14px' },
        data: { relation_id: e.org_id, relation_type: 'org_org' },
      })
    }

    nodes.value = newNodes
    edges.value = newEdges
  }

  async function loadGraph() {
    loading.value = true
    try {
      const data = await apiFetch<GraphData>('/hierarchy/graph')
      lastGraphData.value = data
      buildGraph(data)
      opts.emitDataChanged()
    } catch {
      opts.showSnack('Ошибка загрузки графа', 'error')
    } finally {
      loading.value = false
    }
  }

  function rebuildGraph() {
    if (lastGraphData.value) buildGraph(lastGraphData.value)
  }

  // ── Helpers для диалогов (читают nodes.value) ───────────────────────────────────

  function getAvailableUsers(deptId: number): { id: number; label: string }[] {
    const deptMemberIds = new Set(
      nodes.value
        .filter(n => n.type === 'user' && n.parentNode === `dept-${deptId}`)
        .map(n => parseInt(n.id.replace('user-', '')))
    )
    return nodes.value
      .filter(n => n.type === 'user' && !deptMemberIds.has(parseInt(n.id.replace('user-', ''))))
      .map(n => ({ id: parseInt(n.id.replace('user-', '')), label: (n.data as any).label || n.id }))
      .sort((a, b) => a.label.localeCompare(b.label))
  }

  function getDeptName(deptId: number): string {
    const n = nodes.value.find(n => n.id === `dept-${deptId}`)
    return (n?.data as any)?.label || ''
  }

  // ── Auto-layout ────────────────────────────────────────────────────────────────

  function autoLayout() {
    const orgNodes = nodes.value.filter(n => n.type === 'org')
    const deptNodes = nodes.value.filter(n => n.type === 'dept')
    const freeUsers = nodes.value.filter(n => n.type === 'user' && !n.parentNode)

    // Arrange members inside each dept (column) + resize dept height. Independent of x/y placement.
    for (const dept of deptNodes) {
      const children = nodes.value.filter(n => n.type === 'user' && n.parentNode === dept.id)
      const headUserId = (dept.data as any).headUserId as number | null
      const sorted = [...children].sort((a, b) => {
        const aid = parseInt(a.id.replace('user-', ''))
        const bid = parseInt(b.id.replace('user-', ''))
        if (aid === headUserId) return -1
        if (bid === headUserId) return 1
        const ra = getPositionRank((a.data as any).position || null)
        const rb = getPositionRank((b.data as any).position || null)
        return ra - rb
      })
      const _autoLayoutBadge = ((lastGraphData.value?.orgs?.length || 0) > 1)
      const dHeadH = deptHeaderHeight((dept.data as any)?.label, _autoLayoutBadge)
      sorted.forEach((u, i) => {
        u.position = { x: 10, y: dHeadH + 4 + i * (USER_H + USER_GAP) }
      })
      const deptId = parseInt(dept.id.replace('dept-', ''))
      saveDeptOrder(deptId, sorted.map(u => parseInt(u.id.replace('user-', ''))))
      const newH = Math.max(calcDeptHeight(sorted.length, (dept.data as any)?.label, _autoLayoutBadge), 80)
      dept.style = { ...dept.style as object, height: `${newH}px` }
      ;(dept.data as any).memberCount = sorted.length
    }

    // Grouped block layout: each org card sits centered above its own departments.
    const GAP_X = 40
    const ORG_Y = 60
    const DEPT_Y = 230
    let cursorX = 60
    let maxBottom = DEPT_Y
    const placedDeptIds = new Set<string>()
    for (const org of orgNodes) {
      const orgId = (org.data as any).orgId
      const myDepts = deptNodes.filter(d => (d.data as any).orgId === orgId)
      myDepts.forEach(d => placedDeptIds.add(d.id))
      const count = Math.max(myDepts.length, 1)
      const blockWidth = count * DEPT_W + (count - 1) * GAP_X
      org.position = { x: cursorX + (blockWidth - DEPT_W) / 2, y: ORG_Y }
      let dx = cursorX
      for (const d of myDepts) {
        d.position = { x: dx, y: DEPT_Y }
        dx += DEPT_W + GAP_X
        const h = parseInt(String((d.style as any)?.height || '120'))
        if (DEPT_Y + h > maxBottom) maxBottom = DEPT_Y + h
      }
      cursorX += blockWidth + GAP_X * 2
    }

    // Orphan depts whose org card is not present — lay them out in a trailing row.
    let ox = cursorX
    for (const d of deptNodes) {
      if (placedDeptIds.has(d.id)) continue
      d.position = { x: ox, y: DEPT_Y }
      ox += DEPT_W + GAP_X
      const h = parseInt(String((d.style as any)?.height || '120'))
      if (DEPT_Y + h > maxBottom) maxBottom = DEPT_Y + h
    }

    // Free users (no dept) — row below the tallest dept block.
    let x = 60
    let y = maxBottom + 60
    for (const u of freeUsers) {
      u.position = { x, y }
      x += USER_W + 30
      if (x > 1400) { x = 60; y += USER_H + 20 }
    }

    nodes.value = [...nodes.value]
    savePositions(nodes.value)
    setTimeout(() => fitView({ padding: 0.12 }), 50)
  }

  // ── Snap to slot (reorder within dept) ────────────────────────────────────────

  function snapToSlot(draggedNode: Node) {
    if (!draggedNode.parentNode) return
    const deptId = parseInt(draggedNode.parentNode.replace('dept-', ''))
    const siblings = nodes.value.filter(n => n.type === 'user' && n.parentNode === draggedNode.parentNode)
    // Phase 30: учитываем динамическую высоту шапки отдела
    const dNode = nodes.value.find(n => n.id === draggedNode.parentNode)
    const _snapBadge = ((lastGraphData.value?.orgs?.length || 0) > 1)
    const dHeadH = deptHeaderHeight((dNode?.data as any)?.label, _snapBadge)

    // Sort all users in dept by current y position to determine new order
    const sorted = [...siblings].sort((a, b) => a.position.y - b.position.y)
    const newOrderIds = sorted.map(n => parseInt(n.id.replace('user-', '')))

    // Snap each to their slot position
    nodes.value = nodes.value.map(n => {
      const idx = sorted.findIndex(u => u.id === n.id)
      if (idx >= 0 && n.parentNode === draggedNode.parentNode) {
        return { ...n, position: { x: 10, y: dHeadH + 4 + idx * (USER_H + USER_GAP) } }
      }
      return n
    })

    saveDeptOrder(deptId, newOrderIds)
    savePositions(nodes.value)
  }

  // ── Phase 30: точная посадка карточек под ИЗМЕРЕННУЮ (DOM) высоту шапки отдела ──
  // JS-оценка deptHeaderHeight неточна → карточки наезжали. После маунта меряем
  // реальную высоту .hnode-dept-header-bar и пересаживаем дочерние user-узлы.
  function measuredDeptHeaderH(nodeId: string): number {
    const el = document.querySelector(
      `.vue-flow__node[data-id="${nodeId}"] .hnode-dept-header-bar`
    ) as HTMLElement | null
    return el && el.offsetHeight > 0 ? el.offsetHeight : DEPT_HEADER_H
  }

  function restackDeptUsers() {
    const deptNodes = nodes.value.filter(n => n.type === 'dept')
    let changed = false
    for (const dept of deptNodes) {
      const headerH = measuredDeptHeaderH(dept.id)
      const children = nodes.value.filter(n => n.type === 'user' && n.parentNode === dept.id)
      const sorted = [...children].sort((a, b) => a.position.y - b.position.y)
      sorted.forEach((u, i) => {
        const ny = headerH + 6 + i * (USER_H + USER_GAP)
        if (u.position.x !== 10 || Math.abs(u.position.y - ny) > 0.5) {
          u.position = { x: 10, y: ny }
          changed = true
        }
      })
      const newH = Math.max(headerH + sorted.length * (USER_H + USER_GAP) + DEPT_PAD_Y, 80)
      if ((dept.style as any)?.height !== `${newH}px`) {
        dept.style = { ...(dept.style as object), height: `${newH}px` }
        changed = true
      }
    }
    if (changed) {
      nodes.value = [...nodes.value]
      savePositions(nodes.value)
    }
  }

  // Дебаунс пересадки для ResizeObserver (шапка растёт после загрузки шрифта/переноса строк).
  let _restackDebounce: ReturnType<typeof setTimeout> | null = null
  function restackDeptUsersDebounced() {
    if (_restackDebounce) clearTimeout(_restackDebounce)
    _restackDebounce = setTimeout(() => restackDeptUsers(), 120)
  }

  const deptHeaderResizeObserver = ref<ResizeObserver | null>(null)
  function observeDeptHeaders() {
    if (deptHeaderResizeObserver.value) return // не пересоздаём
    const ro = new ResizeObserver(() => restackDeptUsersDebounced())
    document.querySelectorAll('.hnode-dept-header-bar').forEach(el => ro.observe(el))
    deptHeaderResizeObserver.value = ro
  }

  onNodesInitialized(() => {
    nextTick(() => restackDeptUsers())
    // Шапка отдела может вырасти после загрузки веб-шрифта / переноса длинного
    // названия → измеренная высота на первом nextTick слишком мала и карточки
    // налезают. Перезапускаем пересадку после fonts.ready и двойного rAF.
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(() => restackDeptUsers())
    }
    requestAnimationFrame(() => requestAnimationFrame(() => restackDeptUsers()))
    // И продолжаем реагировать на любые изменения высоты шапок.
    nextTick(() => observeDeptHeaders())
  })

  onUnmounted(() => {
    if (_restackDebounce) clearTimeout(_restackDebounce)
    deptHeaderResizeObserver.value?.disconnect()
    deptHeaderResizeObserver.value = null
  })

  // ── Открытие карточек по двойному клику ─────────────────────────────────────────

  onNodeDoubleClick(({ node }) => {
    if (node.type === 'user') {
      const userId = parseInt(node.id.replace(/user-(\d+).*/, '$1'))
      opts.onEditUser(userId)
    }
    else if (node.type === 'dept') opts.onEditDept(parseInt(node.id.replace('dept-', '')))
    else if (node.type === 'org') {
      const orgId = parseInt(node.id.replace('org-', ''))
      const org = lastGraphData.value?.orgs.find(o => o.id === orgId)
      if (org) opts.onOpenOrg(org as OrgLite)
    }
  })

  // ── Drag in/out of dept ────────────────────────────────────────────────────────

  onNodeDragStop(async ({ node }) => {
    if (node.type !== 'user') {
      savePositions(nodes.value)
      return
    }

    const userId = parseInt(node.id.replace('user-', ''))

    if (node.parentNode) {
      // Check if dragged OUTSIDE the parent dept
      const parentNode = nodes.value.find(n => n.id === node.parentNode)
      if (parentNode) {
        const pw = parseFloat((parentNode.style as any)?.width) || DEPT_W
        const ph = parseFloat((parentNode.style as any)?.height) || 200
        // User center relative to parent
        const cx = node.position.x + USER_W / 2
        const cy = node.position.y + USER_H / 2
        const outside = cx < 0 || cy < 0 || cx > pw || cy > ph

        if (outside) {
          const deptId = parseInt(node.parentNode.replace('dept-', ''))
          const absPos = {
            x: parentNode.position.x + node.position.x,
            y: parentNode.position.y + node.position.y,
          }
          const oldParent = node.parentNode

          // 7b: Check if dropped ONTO another dept (move, not just exit)
          const targetDept = nodes.value.find(dn => {
            if (dn.type !== 'dept' || dn.id === oldParent) return false
            const pw = parseFloat((dn.style as any)?.width) || DEPT_W
            const ph = parseFloat((dn.style as any)?.height) || 200
            const cx = absPos.x + USER_W / 2
            const cy = absPos.y + USER_H / 2
            return cx >= dn.position.x && cx <= dn.position.x + pw
                && cy >= dn.position.y && cy <= dn.position.y + ph
          })

          if (targetDept) {
            // Move from old dept to new dept in same org (or cross-org)
            const newDeptId = parseInt(targetDept.id.replace('dept-', ''))
            try {
              // Remove from old dept, add to new dept atomically on frontend side
              await apiFetch(`/departments/${deptId}/members/${userId}`, { method: 'DELETE' })
              await apiFetch(`/departments/${newDeptId}/members`, { method: 'POST', body: { user_id: userId } })
              // Auto-add to org if cross-org
              const tDept = lastGraphData.value?.departments.find(d => d.id === newDeptId)
              if (tDept) {
                const user = lastGraphData.value?.users.find(u => u.id === userId)
                const userOrgIds = new Set([user?.org_id, ...(user?.extra_org_ids || [])])
                if (!userOrgIds.has(tDept.org_id)) {
                  try { await apiFetch(`/users/${userId}/organizations/${tDept.org_id}`, { method: 'POST', body: {} }) } catch {}
                }
              }
              opts.showSnack('Сотрудник перемещён в другой отдел')
              // Reload to sync state cleanly
              await loadGraph()
              opts.emitDataChanged()
            } catch (e: any) {
              opts.showSnack(e?.message || 'Ошибка перемещения', 'error')
              await loadGraph()
            }
            return
          }

          try {
            await apiFetch(`/departments/${deptId}/members/${userId}`, { method: 'DELETE' })
            // Update node: remove from dept
            nodes.value = nodes.value.map(n =>
              n.id === node.id ? { ...n, parentNode: undefined, position: absPos, zIndex: undefined } : n
            )
            // Shrink dept
            const remaining = nodes.value.filter(n => n.parentNode === oldParent).length
            const _dragOutBadge = ((lastGraphData.value?.orgs?.length || 0) > 1)
            nodes.value = nodes.value.map(n => {
              if (n.id === oldParent) {
                const newH = Math.max(calcDeptHeight(remaining, (n.data as any)?.label, _dragOutBadge), 80)
                return { ...n, style: { ...n.style as object, height: `${newH}px` }, data: { ...(n.data as object), memberCount: remaining } }
              }
              return n
            })
            opts.showSnack('Сотрудник выведен из отдела')
            opts.emitDataChanged()
          } catch (e: any) {
            opts.showSnack(e?.message || 'Ошибка: нельзя вывести из отдела', 'error')
            loadGraph()
          }
          return
        } else {
          // Stayed within dept — snap to nearest slot to reorder
          snapToSlot(node)
          return
        }
      }
    } else {
      // Free user — check if dropped ONTO a dept
      const absPos = node.position
      const targetDept = nodes.value.find(dn => {
        if (dn.type !== 'dept') return false
        const pw = parseFloat((dn.style as any)?.width) || DEPT_W
        const ph = parseFloat((dn.style as any)?.height) || 200
        const cx = absPos.x + USER_W / 2
        const cy = absPos.y + USER_H / 2
        return cx >= dn.position.x && cx <= dn.position.x + pw
            && cy >= dn.position.y && cy <= dn.position.y + ph
      })

      if (targetDept) {
        const deptId = parseInt(targetDept.id.replace('dept-', ''))
        try {
          await apiFetch(`/departments/${deptId}/members`, { method: 'POST', body: { user_id: userId } })
          // Auto-add to org if dropping into different org's dept
          const tDept = lastGraphData.value?.departments.find(d => d.id === deptId)
          if (tDept) {
            const user = lastGraphData.value?.users.find(u => u.id === userId)
            const userOrgIds = new Set([user?.org_id, ...(user?.extra_org_ids || [])])
            if (!userOrgIds.has(tDept.org_id)) {
              try { await apiFetch(`/users/${userId}/organizations/${tDept.org_id}`, { method: 'POST', body: {} }) } catch {}
            }
          }
          opts.showSnack('Сотрудник добавлен в отдел')

          // Update nodes locally — no full reload to avoid flicker
          // Backend may have removed user from another dept (exclusive membership)
          // Find if user was visually inside another dept and remove them
          const _dropBadge = ((lastGraphData.value?.orgs?.length || 0) > 1)
          const oldParentId = node.parentNode
          if (oldParentId && oldParentId !== targetDept.id) {
            const oldRemaining = nodes.value.filter(n => n.parentNode === oldParentId && n.id !== node.id).length
            nodes.value = nodes.value.map(n => {
              if (n.id === oldParentId) {
                const newH = Math.max(calcDeptHeight(oldRemaining, (n.data as any)?.label, _dropBadge), 80)
                return { ...n, style: { ...n.style as object, height: `${newH}px` }, data: { ...(n.data as object), memberCount: oldRemaining } }
              }
              return n
            })
          }

          // Count existing children in target dept (excluding this user)
          const existingCount = nodes.value.filter(n => n.parentNode === targetDept.id && n.id !== node.id).length
          const tDeptHeadH = deptHeaderHeight((targetDept.data as any)?.label, _dropBadge)
          const relPos = { x: 10, y: tDeptHeadH + 4 + existingCount * (USER_H + USER_GAP) }
          const newCount = existingCount + 1

          // Determine new org color for the target dept
          const tDeptData = lastGraphData.value?.departments.find(d => d.id === parseInt(targetDept.id.replace('dept-', '')))
          const tOrgId = tDeptData?.org_id
          const tOrgIdx = tOrgId ? (lastGraphData.value?.orgs || []).findIndex(o => o.id === tOrgId) : -1
          const newOrgColor = tOrgId ? opts.getOrgColor(tOrgId, tOrgIdx >= 0 ? tOrgIdx : 0) : undefined

          nodes.value = nodes.value.map(n => {
            if (n.id === node.id) {
              const tOrgName = tOrgId ? (_orgNameMap.get(tOrgId) || '') : (n.data as any).deptOrgName
              const updatedData = { ...(n.data as object), orgColor: newOrgColor || (n.data as any).orgColor, deptOrgName: tOrgName }
              return { ...n, parentNode: targetDept.id, position: relPos, zIndex: 1000, data: updatedData }
            }
            if (n.id === targetDept.id) {
              const newH = Math.max(calcDeptHeight(newCount, (n.data as any)?.label, _dropBadge), 80)
              return { ...n, style: { ...n.style as object, height: `${newH}px` }, data: { ...(n.data as object), memberCount: newCount } }
            }
            return n
          })

          opts.emitDataChanged()
          savePositions(nodes.value)
        } catch (e: any) {
          opts.showSnack(e?.message || 'Ошибка добавления в отдел', 'error')
          await loadGraph()
        }
        return
      }
    }

    savePositions(nodes.value)
  })

  // ── Connect (create hierarchy edge) ───────────────────────────────────────────

  async function onConnect(conn: Connection) {
    const { source, target } = conn
    if (!source || !target) return

    // Стрелка отдел→отдел: источник становится вышестоящим подразделением цели.
    if (source.startsWith('dept-') && target.startsWith('dept-')) {
      const source_id = parseInt(source.replace('dept-', ''))
      const target_id = parseInt(target.replace('dept-', ''))
      try {
        const result = await apiFetch<{ id: number; type: string }>('/hierarchy/edges', {
          method: 'POST',
          body: { type: 'dept_dept', source_id, target_id },
        })
        const edgeId = `dd-${result.id}`
        // Убрать прежнюю стрелку к этому отделу (у отдела один родитель).
        edges.value = edges.value.filter(e => e.id !== edgeId)
        addEdges([{
          id: edgeId, source, target,
          type: 'smoothstep',
          style: { stroke: '#1976d2', strokeWidth: 2 },
          markerEnd: { type: 'arrowclosed', color: '#1976d2' } as any,
          label: '×',
          labelStyle: { cursor: 'pointer', fill: '#f44336', fontWeight: 'bold', fontSize: '14px' },
          data: { relation_id: result.id, relation_type: 'dept_dept' },
        }])
        opts.showSnack('Задано вышестоящее подразделение')
      } catch (e: any) {
        opts.showSnack(e?.message || 'Ошибка создания связи', 'error')
      }
      return
    }

    // Стрелка орг→орг: источник становится вышестоящей организацией цели.
    if (source.startsWith('org-') && target.startsWith('org-')) {
      const source_id = parseInt(source.replace('org-', ''))
      const target_id = parseInt(target.replace('org-', ''))
      try {
        const result = await apiFetch<{ id: number; type: string }>('/hierarchy/edges', {
          method: 'POST',
          body: { type: 'org_org', source_id, target_id },
        })
        const edgeId = `oo-${result.id}`
        // Убрать прежнюю стрелку к этой орг (у орг один родитель).
        edges.value = edges.value.filter(e => e.id !== edgeId)
        addEdges([{
          id: edgeId, source, target,
          type: 'smoothstep',
          style: { stroke: '#7b1fa2', strokeWidth: 2.5 },
          markerEnd: { type: 'arrowclosed', color: '#7b1fa2' } as any,
          label: '×',
          labelStyle: { cursor: 'pointer', fill: '#f44336', fontWeight: 'bold', fontSize: '14px' },
          data: { relation_id: result.id, relation_type: 'org_org' },
        }])
        opts.showSnack('Задана вышестоящая организация')
      } catch (e: any) {
        opts.showSnack(e?.message || 'Ошибка создания связи', 'error')
      }
      return
    }

    // Орг-источник допускает только орг→орг (обработано выше). Иначе — понятная причина.
    if (source.startsWith('org-')) {
      opts.showSnack('От организации стрелку можно вести только к другой организации', 'warning')
      return
    }

    if (!source.startsWith('user-')) {
      opts.showSnack('Связь тянуть от сотрудника, между отделами или между организациями', 'warning')
      return
    }

    const type = target.startsWith('dept-') ? 'user_dept'
      : target.startsWith('org-') ? 'user_org'
      : 'user_user'
    const source_id = parseInt(source.replace('user-', ''))
    const target_id = parseInt(target.replace(/^\w+-/, ''))

    try {
      const result = await apiFetch<{ id: number; type: string }>('/hierarchy/edges', {
        method: 'POST',
        body: { type, source_id, target_id },
      })

      const edgeId = type === 'user_user' ? `uu-${result.id}`
        : type === 'user_dept' ? `ud-${result.id}`
        : `uo-${result.id}`
      if (edges.value.some(e => e.id === edgeId)) return

      const edgeColor = type === 'user_user' ? '#4caf50' : type === 'user_dept' ? '#ff9800' : '#9c27b0'
      addEdges([{
        id: edgeId, source, target,
        type: 'smoothstep',
        animated: type !== 'user_dept',
        style: {
          stroke: edgeColor,
          strokeWidth: type === 'user_org' ? 2.5 : 2,
          ...(type === 'user_dept' ? { strokeDasharray: '6 3' } : {}),
        },
        markerEnd: { type: 'arrowclosed', color: edgeColor } as any,
        label: '×',
        labelStyle: { cursor: 'pointer', fill: '#f44336', fontWeight: 'bold', fontSize: '14px' },
        data: { relation_id: result.id, relation_type: type },
      }])

      const msg = type === 'user_user' ? 'Связь подчинённости создана'
        : type === 'user_dept' ? 'Назначен куратор отдела'
        : 'Назначен руководитель организации'
      opts.showSnack(msg)
    } catch (e: any) {
      opts.showSnack(e?.message || 'Ошибка создания связи', 'error')
    }
  }

  // ── Delete edge on × click ────────────────────────────────────────────────────

  onEdgeClick(async ({ edge, event }) => {
    const target = event.target as HTMLElement
    if (!target) return
    if (target.textContent?.trim() !== '×' && !target.closest('.vue-flow__edge-textwrapper')) return
    const { relation_id, relation_type } = edge.data || {}
    if (!relation_id || !relation_type) return
    try {
      await apiFetch(`/hierarchy/edges/${relation_id}?type=${relation_type}`, { method: 'DELETE' })
      removeEdges([edge.id])
      opts.showSnack('Связь удалена')
    } catch (e: any) {
      opts.showSnack('Ошибка удаления связи', 'error')
    }
  })

  return {
    nodes, edges, loading, graphOrgs,
    loadGraph, rebuildGraph, autoLayout,
    getAvailableUsers, getDeptName,
    fitView, onConnect,
  }
}
