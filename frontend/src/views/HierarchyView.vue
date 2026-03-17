<template>
  <div class="hierarchy-page" :class="{ embedded: props.embedded }">
    <!-- Toolbar -->
    <div class="hierarchy-toolbar elevation-1">
      <v-icon icon="mdi-sitemap" color="primary" class="mr-2" />
      <span class="text-h6 font-weight-bold mr-4">Редактор иерархии</span>
      <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-auto-fix" @click="autoLayout" class="mr-2">
        Авторасстановка
      </v-btn>
      <v-btn size="small" variant="text" prepend-icon="mdi-refresh" @click="loadGraph" :loading="loading" class="mr-2">
        Обновить
      </v-btn>
      <v-spacer />
      <!-- Legend -->
      <div class="d-flex align-center ga-3 mr-4">
        <div class="d-flex align-center ga-1">
          <div class="legend-line legend-green" />
          <span class="text-caption">Подчинённость</span>
        </div>
        <div class="d-flex align-center ga-1">
          <div class="legend-line legend-orange" />
          <span class="text-caption">Начальник отдела</span>
        </div>
      </div>
      <!-- Connection hint -->
      <div class="d-flex align-center ga-2 mr-2">
        <v-chip size="x-small" color="success" variant="tonal" prepend-icon="mdi-circle-medium">
          тянуть → подчинённость
        </v-chip>
        <v-chip size="x-small" color="warning" variant="tonal" prepend-icon="mdi-circle-medium">
          тянуть → к отделу
        </v-chip>
      </div>
      <v-btn size="small" variant="text" prepend-icon="mdi-help-circle-outline" @click="helpDialog = true" />
    </div>

    <!-- Loading overlay -->
    <div v-if="loading" class="hierarchy-loading">
      <v-progress-circular indeterminate color="primary" size="48" />
    </div>

    <!-- Vue Flow canvas -->
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
      @nodes-change="onNodesChange"
    >
      <Background pattern="dots" :gap="20" :size="1" />
      <Controls />
      <MiniMap :height="120" :width="160" />
    </VueFlow>

    <!-- Help dialog -->
    <v-dialog v-model="helpDialog" max-width="420">
      <v-card>
        <v-card-title class="pa-4 d-flex align-center">
          <v-icon icon="mdi-help-circle" color="primary" class="mr-2" />
          Как пользоваться
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-list density="compact">
            <v-list-item prepend-icon="mdi-cursor-move">
              <v-list-item-title class="text-body-2">Перемещайте узлы перетаскиванием</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-arrow-right-circle">
              <v-list-item-title class="text-body-2">Тяните от <strong>→</strong> одного сотрудника к другому — создаётся подчинённость</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-office-building-outline">
              <v-list-item-title class="text-body-2">Тяните от сотрудника к <strong>отделу</strong> — сотрудник становится начальником отдела</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-close-circle-outline">
              <v-list-item-title class="text-body-2">Нажмите <strong>×</strong> на связи для её удаления</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-auto-fix">
              <v-list-item-title class="text-body-2">"Авторасстановка" перестроит граф по иерархии</v-list-item-title>
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
import { ref, shallowRef, markRaw, h, onMounted } from 'vue'
import { VueFlow, useVueFlow, Handle, Position, type Node, type Edge, type Connection, type NodeChange } from '@vue-flow/core'

const props = withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'
import { apiFetch } from '@/api'

// ── Dagre layout ───────────────────────────────────────────────────────────────
// @ts-ignore
import dagre from '@dagrejs/dagre'

const nodes = ref<Node[]>([])
const edges = ref<Edge[]>([])
const loading = ref(false)
const helpDialog = ref(false)
const snack = ref({ show: false, text: '', color: 'success' })
const showSnack = (text: string, color = 'success') => { snack.value = { show: true, text, color } }

// ── Custom node components ────────────────────────────────────────────────────

const OrgNode = markRaw({
  name: 'OrgNode',
  props: ['data', 'id'],
  setup(props: any) {
    return () => h('div', { class: 'hnode hnode-org' }, [
      h('div', { class: 'hnode-header hnode-header-org' }, [
        h('span', { class: 'mdi mdi-domain hnode-icon' }),
        h('span', { class: 'hnode-title' }, props.data.label),
      ]),
    ])
  },
})

const DeptNode = markRaw({
  name: 'DeptNode',
  props: ['data', 'id'],
  setup(props: any) {
    return () => h('div', { class: 'hnode hnode-dept' }, [
      // Dept is TARGET only (someone becomes head of it)
      h(Handle, { type: 'target', position: Position.Left, id: 'tgt',
        style: 'background:#ff9800; width:12px; height:12px; border:2px solid white' }),
      h('div', { class: 'hnode-header hnode-header-dept' }, [
        h('span', { class: 'mdi mdi-account-group hnode-icon' }),
        h('span', { class: 'hnode-title' }, props.data.label),
      ]),
      props.data.memberCount != null
        ? h('div', { class: 'hnode-subtitle' }, `${props.data.memberCount} сотр.`)
        : null,
    ])
  },
})

const UserNode = markRaw({
  name: 'UserNode',
  props: ['data', 'id'],
  setup(props: any) {
    const roleColors: Record<string, string> = {
      superadmin: '#9c27b0', org_admin: '#f44336', admin: '#f44336',
      manager: '#2196f3', employee: '#009688',
    }
    const roleLabels: Record<string, string> = {
      superadmin: 'Суперадмин', org_admin: 'Администратор', admin: 'Администратор',
      manager: 'Менеджер', employee: 'Сотрудник',
    }
    return () => h('div', { class: 'hnode hnode-user' }, [
      // Source handle (right) — drag FROM here to create edge
      h(Handle, { type: 'source', position: Position.Right, id: 'src',
        style: 'background:#4caf50; width:14px; height:14px; border:2px solid white; cursor:crosshair',
        title: 'Тяните отсюда чтобы создать связь' }),
      // Target handle (left) — receives edge
      h(Handle, { type: 'target', position: Position.Left, id: 'tgt',
        style: 'background:#2196f3; width:14px; height:14px; border:2px solid white' }),
      h('div', { class: 'hnode-user-row' }, [
        h('div', { class: 'hnode-avatar' }, props.data.initials || '?'),
        h('div', { class: 'hnode-user-info' }, [
          h('div', { class: 'hnode-user-name' }, props.data.label),
          h('div', {
            class: 'hnode-user-role',
            style: { color: roleColors[props.data.role] || '#666' }
          }, roleLabels[props.data.role] || props.data.role),
        ]),
      ]),
    ])
  },
})

const nodeTypes = {
  org: OrgNode,
  dept: DeptNode,
  user: UserNode,
}

const defaultEdgeOptions = {
  type: 'smoothstep',
}

// ── VueFlow instance ──────────────────────────────────────────────────────────
const { addEdges, removeEdges, fitView } = useVueFlow()

// ── Graph data ────────────────────────────────────────────────────────────────

interface GraphData {
  orgs: { id: number; name: string }[]
  departments: { id: number; name: string; org_id: number; head_user_id: number | null; member_ids: number[] }[]
  users: { id: number; full_name: string | null; username: string; role: string; org_id: number; avatar: string | null }[]
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

const POSITIONS_KEY = 'hierarchy_node_positions'

function loadPositions(): Record<string, { x: number; y: number }> {
  try {
    return JSON.parse(localStorage.getItem(POSITIONS_KEY) || '{}')
  } catch { return {} }
}

function savePositions(ns: Node[]) {
  const pos: Record<string, { x: number; y: number }> = {}
  for (const n of ns) pos[n.id] = { x: n.position.x, y: n.position.y }
  localStorage.setItem(POSITIONS_KEY, JSON.stringify(pos))
}

function buildGraph(data: GraphData) {
  const savedPos = loadPositions()
  const newNodes: Node[] = []
  const newEdges: Edge[] = []

  // Org nodes
  for (const org of data.orgs) {
    const id = `org-${org.id}`
    newNodes.push({
      id, type: 'org',
      position: savedPos[id] || { x: 100, y: 50 },
      data: { label: org.name },
      draggable: true,
    })
  }

  // Dept nodes
  for (const dept of data.departments) {
    const id = `dept-${dept.id}`
    newNodes.push({
      id, type: 'dept',
      position: savedPos[id] || { x: 100, y: 200 },
      data: { label: dept.name, memberCount: dept.member_ids.length },
      draggable: true,
    })
  }

  // User nodes
  for (const user of data.users) {
    const id = `user-${user.id}`
    newNodes.push({
      id, type: 'user',
      position: savedPos[id] || { x: 100, y: 350 },
      data: {
        label: user.full_name || user.username,
        role: user.role,
        initials: getInitials(user.full_name, user.username),
      },
      draggable: true,
    })
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

  // user-dept edges
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
  } catch (e: any) {
    showSnack('Ошибка загрузки графа', 'error')
  } finally {
    loading.value = false
  }
}

// ── Dagre auto-layout ─────────────────────────────────────────────────────────

function autoLayout() {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'TB', ranksep: 80, nodesep: 50, marginx: 40, marginy: 40 })
  g.setDefaultEdgeLabel(() => ({}))

  const nodeSizes: Record<string, { width: number; height: number }> = {
    org: { width: 220, height: 50 },
    dept: { width: 180, height: 60 },
    user: { width: 180, height: 60 },
  }

  for (const node of nodes.value) {
    const sz = nodeSizes[node.type as string] || { width: 180, height: 60 }
    g.setNode(node.id, { width: sz.width, height: sz.height })
  }

  for (const edge of edges.value) {
    g.setEdge(edge.source, edge.target)
  }

  dagre.layout(g)

  nodes.value = nodes.value.map(n => {
    const pos = g.node(n.id)
    return { ...n, position: { x: pos.x - pos.width / 2, y: pos.y - pos.height / 2 } }
  })

  savePositions(nodes.value)
  setTimeout(() => fitView({ padding: 0.1 }), 50)
}

// ── Connect handler ───────────────────────────────────────────────────────────

async function onConnect(conn: Connection) {
  const { source, target } = conn
  if (!source || !target) return

  // Only allow user as source
  if (!source.startsWith('user-')) {
    showSnack('Связь можно тянуть только от сотрудника', 'warning')
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
    // Check if edge already exists (server returned existing)
    if (edges.value.some(e => e.id === edgeId)) return

    addEdges([{
      id: edgeId,
      source,
      target,
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

// ── Edge label click (delete) ─────────────────────────────────────────────────
// VueFlow fires edge-label-click; we listen via edge click pattern
// Actually in VueFlow, clicking the label fires edge click
// Use onEdgeClick from useVueFlow

const { onEdgeClick } = useVueFlow()

onEdgeClick(async ({ edge, event }) => {
  // Check if click was on label (× symbol)
  const target = event.target as HTMLElement
  if (!target) return
  // Check if user clicked on the label text (contains ×)
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

// ── Save positions on drag ────────────────────────────────────────────────────

function onNodesChange(changes: NodeChange[]) {
  const hasMoved = changes.some(c => c.type === 'position' && c.dragging === false)
  if (hasMoved) {
    savePositions(nodes.value)
  }
}

onMounted(loadGraph)
</script>

<style>
/* Import vue-flow styles globally (not scoped) */
.vue-flow__edge-text {
  cursor: pointer;
}
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
}

.hierarchy-canvas {
  flex: 1;
  min-height: 0;
}

.hierarchy-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.legend-line {
  width: 24px;
  height: 3px;
  border-radius: 2px;
}
.legend-green { background: #4caf50; }
.legend-orange { background: #ff9800; border-top: 1px dashed #ff9800; }

/* Node styles */
:deep(.hnode) {
  background: white;
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.12);
  min-width: 160px;
  overflow: hidden;
  cursor: pointer;
  transition: box-shadow 0.15s;
  border: 1.5px solid transparent;
}
:deep(.hnode:hover) {
  box-shadow: 0 4px 16px rgba(0,0,0,0.18);
  border-color: rgb(var(--v-theme-primary));
}
:deep(.hnode-org) {
  min-width: 200px;
  border-color: #1565c0;
}
:deep(.hnode-header) {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  font-weight: 600;
  font-size: 13px;
}
:deep(.hnode-header-org) {
  background: linear-gradient(135deg, #1565c0, #1e88e5);
  color: white;
}
:deep(.hnode-header-dept) {
  background: linear-gradient(135deg, #00695c, #26a69a);
  color: white;
}
:deep(.hnode-icon) {
  font-size: 16px;
}
:deep(.hnode-title) {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
:deep(.hnode-subtitle) {
  padding: 4px 14px 8px;
  font-size: 11px;
  color: #666;
}
:deep(.hnode-user) {
  min-width: 160px;
  border-color: #e0e0e0;
}
:deep(.hnode-user-row) {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
}
:deep(.hnode-avatar) {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgb(var(--v-theme-primary)), #1e88e5);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: bold;
  flex-shrink: 0;
}
:deep(.hnode-user-info) {
  flex: 1;
  min-width: 0;
}
:deep(.hnode-user-name) {
  font-weight: 600;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
:deep(.hnode-user-role) {
  font-size: 11px;
  margin-top: 1px;
}

/* VueFlow controls/minimap positioning */
:deep(.vue-flow__controls) {
  bottom: 16px;
  left: 16px;
}
:deep(.vue-flow__minimap) {
  bottom: 16px;
  right: 16px;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}
</style>
