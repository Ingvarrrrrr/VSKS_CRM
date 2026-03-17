<template>
  <div class="hierarchy-page" :class="{ embedded: props.embedded }">
    <!-- Toolbar -->
    <div class="hierarchy-toolbar elevation-1">
      <v-icon icon="mdi-sitemap" color="primary" class="mr-2" />
      <span class="text-h6 font-weight-bold mr-4">Редактор иерархии</span>
      <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-auto-fix" @click="autoLayout" class="mr-2">
        Авторасстановка
      </v-btn>
      <v-btn size="small" variant="text" prepend-icon="mdi-refresh" @click="loadGraph" :loading="loading">
        Обновить
      </v-btn>
      <v-spacer />
      <div class="d-flex align-center ga-3 mr-3">
        <div class="d-flex align-center ga-1">
          <div class="legend-line legend-green" />
          <span class="text-caption">Подчинённость</span>
        </div>
        <div class="d-flex align-center ga-1">
          <div class="legend-rect legend-dept" />
          <span class="text-caption">Отдел (содержит сотрудников)</span>
        </div>
      </div>
      <v-chip size="x-small" color="teal" variant="tonal" prepend-icon="mdi-drag" class="mr-2">
        Тяни за пределы отдела — вывести / на отдел — добавить
      </v-chip>
      <v-btn size="small" variant="text" icon="mdi-help-circle-outline" @click="helpDialog = true" />
    </div>

    <!-- Loading -->
    <div v-if="loading" class="hierarchy-loading">
      <v-progress-circular indeterminate color="primary" size="48" />
    </div>

    <!-- Canvas -->
    <VueFlow
      v-else
      v-model:nodes="nodes"
      v-model:edges="edges"
      :node-types="nodeTypes"
      :default-edge-options="defaultEdgeOptions"
      :connect-on-click="false"
      :nodes-connectable="true"
      :edges-updatable="false"
      fit-view-on-init
      class="hierarchy-canvas"
      @connect="onConnect"
    >
      <Background pattern="dots" :gap="20" :size="1" />
      <Controls />
      <MiniMap :height="120" :width="160" />
    </VueFlow>

    <!-- Help dialog -->
    <v-dialog v-model="helpDialog" max-width="460">
      <v-card>
        <v-card-title class="pa-4">
          <v-icon icon="mdi-help-circle" color="primary" class="mr-2" />
          Как пользоваться
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-list density="compact">
            <v-list-item prepend-icon="mdi-drag">
              <v-list-item-title class="text-body-2">Перетащи сотрудника <strong>за пределы</strong> отдела — он выйдет из отдела</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-drag">
              <v-list-item-title class="text-body-2">Перетащи свободного сотрудника <strong>на отдел</strong> — он вступит в отдел</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-arrow-right-circle">
              <v-list-item-title class="text-body-2">Тяни от <strong>→</strong> (зелёная точка) сотрудника к другому — создаётся связь подчинённости</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-crown">
              <v-list-item-title class="text-body-2">Корона — начальник отдела. При добавлении в отдел с начальником связь создаётся автоматически</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-close-circle-outline">
              <v-list-item-title class="text-body-2">Нажми <strong>×</strong> на стрелке — удалить связь</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-auto-fix">
              <v-list-item-title class="text-body-2">"Авторасстановка" — автоматически расставить узлы</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn color="primary" variant="flat" @click="helpDialog = false">Понятно</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snack.show" :color="snack.color" timeout="3000" location="bottom right">
      {{ snack.text }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { ref, markRaw, h, onMounted } from 'vue'
import {
  VueFlow, useVueFlow, Handle, Position,
  type Node, type Edge, type Connection,
} from '@vue-flow/core'

const props = withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })
const emit = defineEmits<{ 'edit-user': [id: number]; 'edit-dept': [id: number] }>()

import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'
// @ts-ignore
import dagre from '@dagrejs/dagre'
import { apiFetch } from '@/api'

// ── Constants ──────────────────────────────────────────────────────────────────
const DEPT_W = 230     // dept container width in px
const USER_W = 200     // user node width in px
const USER_H = 72      // user node height in px (name + position + role)
const DEPT_HEADER_H = 48
const USER_GAP = 8
const DEPT_PAD_Y = 12  // bottom padding

function calcDeptHeight(memberCount: number) {
  return DEPT_HEADER_H + Math.max(memberCount, 0) * (USER_H + USER_GAP) + DEPT_PAD_Y
}

function mkDeptStyle(memberCount: number): Record<string, string> {
  return {
    width: `${DEPT_W}px`,
    height: `${Math.max(calcDeptHeight(memberCount), 80)}px`,
    background: 'rgba(0, 105, 92, 0.05)',
    border: '2px dashed #00897b',
    borderRadius: '10px',
  }
}

// ── State ──────────────────────────────────────────────────────────────────────
const nodes = ref<Node[]>([])
const edges = ref<Edge[]>([])
const loading = ref(false)
const helpDialog = ref(false)
const snack = ref({ show: false, text: '', color: 'success' })
const showSnack = (text: string, color = 'success') => { snack.value = { show: true, text, color } }

// ── Custom node components ─────────────────────────────────────────────────────

const OrgNode = markRaw({
  name: 'OrgNode',
  props: ['data'],
  setup(p: any) {
    return () => h('div', { class: 'hnode hnode-org' }, [
      h('div', { class: 'hnode-header hnode-header-org' }, [
        h('span', { class: 'mdi mdi-domain hnode-icon' }),
        h('span', { class: 'hnode-title' }, p.data.label),
      ]),
    ])
  },
})

const DeptNode = markRaw({
  name: 'DeptNode',
  props: ['data'],
  setup(p: any) {
    return () => h('div', { class: 'hnode-dept-header-bar' }, [
      h('span', { class: 'mdi mdi-account-group', style: 'font-size:16px;margin-right:6px;flex-shrink:0' }),
      h('span', { class: 'hnode-title', style: 'flex:1;min-width:0' }, p.data.label),
      h('span', { class: 'hnode-dept-badge' }, `${p.data.memberCount}`),
      // Target handle for user→dept "manager of dept" edges
      h(Handle, {
        type: 'target', position: Position.Left, id: 'tgt',
        style: 'background:#ff9800;width:12px;height:12px;border:2px solid white;left:-6px;top:24px',
      }),
    ])
  },
})

const UserNode = markRaw({
  name: 'UserNode',
  props: ['data'],
  setup(p: any) {
    const roleColors: Record<string, string> = {
      superadmin: '#9c27b0', org_admin: '#f44336', admin: '#f44336',
      manager: '#2196f3', employee: '#009688',
    }
    const roleLabels: Record<string, string> = {
      superadmin: 'Суперадмин', org_admin: 'Администратор', admin: 'Администратор',
      manager: 'Менеджер', employee: 'Сотрудник',
    }
    return () => h('div', { class: 'hnode hnode-user' }, [
      // Green source handle (right) — drag to create hierarchy edge
      h(Handle, {
        type: 'source', position: Position.Right, id: 'src',
        style: 'background:#4caf50;width:14px;height:14px;border:2px solid white;cursor:crosshair',
        title: 'Тяните отсюда чтобы создать связь подчинённости',
      }),
      // Blue target handle (left)
      h(Handle, {
        type: 'target', position: Position.Left, id: 'tgt',
        style: 'background:#2196f3;width:14px;height:14px;border:2px solid white',
      }),
      h('div', { class: 'hnode-user-row' }, [
        h('div', { class: 'hnode-avatar' }, p.data.initials || '?'),
        h('div', { class: 'hnode-user-info' }, [
          h('div', { class: 'hnode-user-name' }, [
            p.data.isHead
              ? h('span', { class: 'mdi mdi-crown', style: 'font-size:13px;color:#f59e0b;margin-right:4px', title: 'Начальник отдела' })
              : null,
            p.data.label,
          ]),
          p.data.position
            ? h('div', { class: 'hnode-user-pos' }, p.data.position)
            : null,
          h('div', { class: 'hnode-user-role', style: { color: roleColors[p.data.role] || '#666' } },
            roleLabels[p.data.role] || p.data.role),
        ]),
      ]),
    ])
  },
})

const nodeTypes = { org: OrgNode, dept: DeptNode, user: UserNode }
const defaultEdgeOptions = { type: 'smoothstep' }

// ── VueFlow composable ─────────────────────────────────────────────────────────
const { addEdges, removeEdges, fitView, onEdgeClick, onNodeDragStop, onNodeDoubleClick } = useVueFlow()

onNodeDoubleClick(({ node }) => {
  if (node.type === 'user') emit('edit-user', parseInt(node.id.replace('user-', '')))
  else if (node.type === 'dept') emit('edit-dept', parseInt(node.id.replace('dept-', '')))
})

// ── Graph data ─────────────────────────────────────────────────────────────────

interface GraphData {
  orgs: { id: number; name: string }[]
  departments: { id: number; name: string; org_id: number; head_user_id: number | null; member_ids: number[] }[]
  users: { id: number; full_name: string | null; username: string; role: string; org_id: number; avatar: string | null; position: string | null }[]
  user_user_edges: { id: number; manager_id: number; subordinate_id: number }[]
  user_dept_edges: { id: number; manager_user_id: number; dept_id: number }[]
}

function getInitials(name: string | null, username: string): string {
  if (name) {
    const parts = name.trim().split(' ')
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
    return parts[0].slice(0, 2).toUpperCase()
  }
  return username.slice(0, 2).toUpperCase()
}

// ── Position persistence ───────────────────────────────────────────────────────
const POS_KEY = 'hierarchy_node_positions'

function loadPositions(): Record<string, { x: number; y: number }> {
  try { return JSON.parse(localStorage.getItem(POS_KEY) || '{}') } catch { return {} }
}

function savePositions(ns: Node[]) {
  const pos: Record<string, { x: number; y: number }> = {}
  for (const n of ns) pos[n.id] = { x: n.position.x, y: n.position.y }
  localStorage.setItem(POS_KEY, JSON.stringify(pos))
}

// ── Build graph ────────────────────────────────────────────────────────────────

function buildGraph(data: GraphData) {
  const savedPos = loadPositions()
  const newNodes: Node[] = []
  const newEdges: Edge[] = []

  // Map userId → { deptId, idx } — users sorted by id for stable ordering
  const userDeptMap: Record<number, { deptId: number; idx: number }> = {}
  for (const dept of data.departments) {
    const sorted = [...dept.member_ids].sort((a, b) => a - b)
    let idx = 0
    for (const uid of sorted) {
      if (!(uid in userDeptMap)) {
        userDeptMap[uid] = { deptId: dept.id, idx: idx++ }
      }
    }
  }

  // Org nodes
  data.orgs.forEach((org, oi) => {
    const id = `org-${org.id}`
    newNodes.push({
      id, type: 'org',
      position: savedPos[id] || { x: 80 + oi * 320, y: 60 },
      data: { label: org.name },
      draggable: true,
    })
  })

  // Dept nodes
  data.departments.forEach((dept, di) => {
    const id = `dept-${dept.id}`
    const mc = dept.member_ids.length
    newNodes.push({
      id, type: 'dept',
      position: savedPos[id] || { x: 80 + di * (DEPT_W + 40), y: 200 },
      style: mkDeptStyle(mc),
      data: { label: dept.name, memberCount: mc, headUserId: dept.head_user_id },
      draggable: true,
      zIndex: 0,
    })
  })

  // User nodes
  let freeIdx = 0
  for (const user of data.users) {
    const id = `user-${user.id}`
    const di = userDeptMap[user.id]
    const dept = di ? data.departments.find(d => d.id === di.deptId) : undefined
    const isHead = !!dept && dept.head_user_id === user.id

    if (di) {
      const defaultRelPos = { x: 10, y: DEPT_HEADER_H + 4 + di.idx * (USER_H + USER_GAP) }
      newNodes.push({
        id, type: 'user',
        parentNode: `dept-${di.deptId}`,
        position: savedPos[id] || defaultRelPos,
        data: { label: user.full_name || user.username, role: user.role, initials: getInitials(user.full_name, user.username), isHead, position: user.position },
        draggable: true,
        zIndex: 1000,
      })
    } else {
      const col = freeIdx % 4
      const row = Math.floor(freeIdx / 4)
      newNodes.push({
        id, type: 'user',
        position: savedPos[id] || { x: 80 + col * 240, y: 600 + row * 80 },
        data: { label: user.full_name || user.username, role: user.role, initials: getInitials(user.full_name, user.username), isHead: false, position: user.position },
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
      markerEnd: { type: 'arrowclosed', color: '#4caf50' },
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
      markerEnd: { type: 'arrowclosed', color: '#ff9800' },
      label: '×',
      labelStyle: { cursor: 'pointer', fill: '#f44336', fontWeight: 'bold', fontSize: '14px' },
      data: { relation_id: e.id, relation_type: 'user_dept' },
    })
  }

  nodes.value = newNodes
  edges.value = newEdges
}

async function loadGraph() {
  loading.value = true
  try {
    const data = await apiFetch<GraphData>('/hierarchy/graph')
    buildGraph(data)
  } catch {
    showSnack('Ошибка загрузки графа', 'error')
  } finally {
    loading.value = false
  }
}

// ── Auto-layout ────────────────────────────────────────────────────────────────

function autoLayout() {
  const orgNodes = nodes.value.filter(n => n.type === 'org')
  const deptNodes = nodes.value.filter(n => n.type === 'dept')
  const freeUsers = nodes.value.filter(n => n.type === 'user' && !n.parentNode)

  // Org row
  let x = 60
  for (const n of orgNodes) {
    n.position = { x, y: 60 }
    x += DEPT_W + 40
  }

  // Dept row
  x = 60
  for (const n of deptNodes) {
    n.position = { x, y: 200 }
    x += DEPT_W + 40
  }

  // Users inside depts: arrange in column
  for (const dept of deptNodes) {
    const children = nodes.value.filter(n => n.type === 'user' && n.parentNode === dept.id)
    children.forEach((u, i) => {
      u.position = { x: 10, y: DEPT_HEADER_H + 4 + i * (USER_H + USER_GAP) }
    })
    // Resize dept
    const newH = Math.max(calcDeptHeight(children.length), 80)
    dept.style = { ...dept.style as object, height: `${newH}px` }
    ;(dept.data as any).memberCount = children.length
  }

  // Free users row
  x = 60
  let y = 600
  for (const u of freeUsers) {
    u.position = { x, y }
    x += USER_W + 30
    if (x > 1400) { x = 60; y += USER_H + 20 }
  }

  nodes.value = [...nodes.value]
  savePositions(nodes.value)
  setTimeout(() => fitView({ padding: 0.12 }), 50)
}

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
        try {
          await apiFetch(`/departments/${deptId}/members/${userId}`, { method: 'DELETE' })
          // Update node: remove from dept
          nodes.value = nodes.value.map(n =>
            n.id === node.id ? { ...n, parentNode: undefined, position: absPos, zIndex: undefined } : n
          )
          // Shrink dept
          const remaining = nodes.value.filter(n => n.parentNode === oldParent).length
          nodes.value = nodes.value.map(n => {
            if (n.id === oldParent) {
              const newH = Math.max(calcDeptHeight(remaining), 80)
              return { ...n, style: { ...n.style as object, height: `${newH}px` }, data: { ...(n.data as object), memberCount: remaining } }
            }
            return n
          })
          showSnack('Сотрудник выведен из отдела')
        } catch (e: any) {
          showSnack(e?.message || 'Ошибка: нельзя вывести из отдела', 'error')
          loadGraph()
        }
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
        showSnack('Сотрудник добавлен в отдел')
        await loadGraph()
      } catch (e: any) {
        showSnack(e?.message || 'Ошибка добавления в отдел', 'error')
        loadGraph()
      }
      return
    }
  }

  savePositions(nodes.value)
})

// ── Connect (create hierarchy edge) ───────────────────────────────────────────

async function onConnect(conn: Connection) {
  const { source, target } = conn
  if (!source || !target || !source.startsWith('user-')) {
    showSnack('Связь тянуть только от сотрудника', 'warning')
    return
  }

  const type = target.startsWith('dept-') ? 'user_dept' : 'user_user'
  const source_id = parseInt(source.replace('user-', ''))
  const target_id = parseInt(target.replace(/^\w+-/, ''))

  try {
    const result = await apiFetch<{ id: number; type: string }>('/hierarchy/edges', {
      method: 'POST',
      body: { type, source_id, target_id },
    })

    const edgeId = type === 'user_user' ? `uu-${result.id}` : `ud-${result.id}`
    if (edges.value.some(e => e.id === edgeId)) return

    addEdges([{
      id: edgeId, source, target,
      type: 'smoothstep',
      animated: type === 'user_user',
      style: {
        stroke: type === 'user_user' ? '#4caf50' : '#ff9800',
        strokeWidth: 2,
        ...(type === 'user_dept' ? { strokeDasharray: '6 3' } : {}),
      },
      markerEnd: { type: 'arrowclosed', color: type === 'user_user' ? '#4caf50' : '#ff9800' },
      label: '×',
      labelStyle: { cursor: 'pointer', fill: '#f44336', fontWeight: 'bold', fontSize: '14px' },
      data: { relation_id: result.id, relation_type: type },
    }])
    showSnack(type === 'user_user' ? 'Связь подчинённости создана' : 'Назначен начальник отдела')
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка создания связи', 'error')
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
    showSnack('Связь удалена')
  } catch (e: any) {
    showSnack('Ошибка удаления связи', 'error')
  }
})

onMounted(loadGraph)
</script>

<style>
.vue-flow__edge-text { cursor: pointer; }
/* Dept node container — style applied to wrapper by VueFlow via node.style */
.vue-flow__node-dept { padding: 0 !important; overflow: visible !important; }
.vue-flow__node-user { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; }
.vue-flow__node-org  { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; }
</style>

<style scoped>
.hierarchy-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 48px);
  overflow: hidden;
}
.hierarchy-page.embedded {
  height: calc(100vh - 220px);
  border-radius: 8px;
  border: 1px solid rgba(0,0,0,0.12);
}
.hierarchy-toolbar {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  background: var(--v-surface-base, #fff);
  border-bottom: 1px solid rgba(0,0,0,0.08);
  flex-shrink: 0;
  z-index: 10;
  gap: 4px;
  flex-wrap: wrap;
}
.hierarchy-canvas { flex: 1; min-height: 0; }
.hierarchy-loading { flex: 1; display: flex; align-items: center; justify-content: center; }

.legend-line { width: 24px; height: 3px; border-radius: 2px; }
.legend-green { background: #4caf50; }
.legend-rect { width: 20px; height: 14px; border: 2px dashed #00897b; border-radius: 3px; background: rgba(0,105,92,0.07); }
.legend-dept {}

/* ── Node styles ── */
:deep(.hnode) {
  background: white;
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.12);
  min-width: 160px;
  overflow: hidden;
  cursor: grab;
  transition: box-shadow 0.15s;
  border: 1.5px solid #e0e0e0;
}
:deep(.hnode:hover) {
  box-shadow: 0 4px 16px rgba(0,0,0,0.18);
  border-color: rgb(var(--v-theme-primary));
}

/* Org node */
:deep(.hnode-org) { min-width: 200px; border-color: #1565c0; }
:deep(.hnode-header) { display: flex; align-items: center; gap: 8px; padding: 10px 14px; font-weight: 600; font-size: 13px; }
:deep(.hnode-header-org) { background: linear-gradient(135deg, #1565c0, #1e88e5); color: white; }
:deep(.hnode-icon) { font-size: 16px; }
:deep(.hnode-title) { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Dept header bar (inside the dashed container) */
:deep(.hnode-dept-header-bar) {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  background: linear-gradient(135deg, #00695c, #26a69a);
  color: white;
  font-weight: 600;
  font-size: 13px;
  border-radius: 8px 8px 0 0;
  min-height: 48px;
  position: relative;
}
:deep(.hnode-dept-badge) {
  background: rgba(255,255,255,0.3);
  border-radius: 12px;
  padding: 1px 8px;
  font-size: 11px;
  font-weight: 700;
  margin-left: 6px;
  flex-shrink: 0;
}

/* User node */
:deep(.hnode-user) { min-width: 160px; width: 200px; border-color: #e0e0e0; }
:deep(.hnode-user-row) { display: flex; align-items: center; gap: 10px; padding: 10px 14px; }
:deep(.hnode-avatar) {
  width: 34px; height: 34px; border-radius: 50%;
  background: linear-gradient(135deg, rgb(var(--v-theme-primary)), #1e88e5);
  color: white; display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: bold; flex-shrink: 0;
}
:deep(.hnode-user-info) { flex: 1; min-width: 0; }
:deep(.hnode-user-name) { font-weight: 600; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; }
:deep(.hnode-user-pos) { font-size: 11px; color: #555; margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
:deep(.hnode-user-role) { font-size: 10px; margin-top: 1px; opacity: 0.75; }
:deep(.hnode-crown) { color: #f59e0b; font-size: 13px; margin-right: 4px; }

/* VueFlow controls */
:deep(.vue-flow__controls) { bottom: 16px; left: 16px; }
:deep(.vue-flow__minimap) { bottom: 16px; right: 16px; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.15); }
</style>
