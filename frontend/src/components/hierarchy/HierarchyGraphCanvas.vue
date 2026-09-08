<template>
  <VueFlow
    v-model:nodes="nodesModel"
    v-model:edges="edgesModel"
    :node-types="nodeTypes"
    :default-edge-options="defaultEdgeOptions"
    :connect-on-click="false"
    :nodes-connectable="true"
    :edges-updatable="false"
    fit-view-on-init
    class="hierarchy-canvas"
    @connect="emit('connect', $event)"
  >
    <Background pattern="dots" :gap="20" :size="1" />
    <Controls />
    <MiniMap :height="120" :width="160" />
  </VueFlow>
</template>

<script setup lang="ts">
// Канвас графа иерархии: рендер узлов (орг/отдел/сотрудник) через VueFlow + DnD.
// Сам приём перетаскивания/связей и построение узлов живут в composables/hierarchy/useHierarchyGraph —
// этот компонент только отображает то, что там посчитано (одна ответственность: канвас+рендер узлов).
import { markRaw, h } from 'vue'
import { VueFlow, Handle, Position, type Node, type Edge, type Connection } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

const emit = defineEmits<{ connect: [conn: Connection] }>()

const nodesModel = defineModel<Node[]>('nodes', { default: () => [] })
const edgesModel = defineModel<Edge[]>('edges', { default: () => [] })

// «Вьющаяся» стрелка-указатель: рендерится над совпавшим при поиске узлом.
function matchPointer(matched: boolean) {
  return matched
    ? h('div', { class: 'hv-pointer' }, [h('span', { class: 'mdi mdi-arrow-down-bold' })])
    : null
}

const OrgNode = markRaw({
  name: 'OrgNode',
  props: ['data'],
  setup(p: any) {
    return () => h('div', { class: 'hnode hnode-org' }, [
      // Purple target handle (вход) for user→org "manager of org" edges + орг→орг (эта орг подчинена)
      h(Handle, {
        type: 'target', position: Position.Left, id: 'tgt',
        style: 'background:#9c27b0;width:14px;height:14px;border:2px solid white;left:-7px',
      }),
      // Source handle (выход, справа) — тяни отсюда к другой орг: та станет подчинённой
      h(Handle, {
        type: 'source', position: Position.Right, id: 'src',
        style: 'background:#7b1fa2;width:14px;height:14px;border:2px solid white;right:-7px;cursor:crosshair',
        title: 'Тяни к другой организации — она станет подчинённой',
      }),
      h('div', { class: 'hnode-header hnode-header-org', style: p.data.orgColor ? `background:linear-gradient(135deg,${p.data.orgColor},${p.data.orgColor}aa)` : '' }, [
        h('span', { class: 'mdi mdi-domain hnode-icon' }),
        h('span', { class: 'hnode-title', style: 'flex:1' }, p.data.label),
        h('span', {
          class: 'mdi mdi-palette',
          style: 'font-size:14px;cursor:pointer;opacity:0.7;margin-left:6px',
          title: 'Выбрать цвет организации',
          onClick: (e: Event) => { e.stopPropagation(); e.preventDefault(); document.dispatchEvent(new CustomEvent('hv-pick-color', { detail: p.data.orgId })) },
        }),
        // Phase 30 restore: удаление организации (superadmin/admin/owner)
        p.data.canDeleteOrg ? h('span', {
          class: 'mdi mdi-close-circle-outline',
          style: 'font-size:14px;cursor:pointer;opacity:0.7;margin-left:6px;color:#ffcdd2',
          title: 'Удалить организацию',
          onClick: (e: Event) => { e.stopPropagation(); e.preventDefault(); document.dispatchEvent(new CustomEvent('hv-delete-org', { detail: { id: p.data.orgId, name: p.data.label } })) },
        }) : null,
      ]),
      p.data.inn ? h('div', { class: 'hnode-org-inn' }, `ИНН: ${p.data.inn}`) : null,
      matchPointer(p.data.matched),
    ])
  },
})

const DeptNode = markRaw({
  name: 'DeptNode',
  props: ['data'],
  setup(p: any) {
    return () => h('div', { class: 'hnode-dept-header-bar', style: p.data.orgColor ? `background:linear-gradient(135deg, ${p.data.orgColor}, ${p.data.orgColor}aa)` : '' }, [
      // Верхняя полоса: контролы + бейджи организаций (вдоль верхней границы, перенос на след. строку)
      h('div', { class: 'hnode-dept-toprow' }, [
        h('span', {
          class: 'mdi mdi-close-circle-outline hnode-dept-del-btn',
          title: 'Удалить отдел',
          onClick: (e: Event) => { e.stopPropagation(); p.data.onDelete?.(p.data.deptId) },
        }),
        h('span', { class: 'mdi mdi-account-group', style: 'font-size:15px;flex-shrink:0;opacity:0.9' }),
        p.data.orgName
          ? h('span', { class: 'hnode-dept-orgbadge', style: `background:${p.data.orgColor || '#1976d2'}` }, p.data.orgName)
          : null,
        h('span', { class: 'hnode-dept-badge' }, `${p.data.memberCount}`),
        h('span', {
          class: 'mdi mdi-plus hnode-dept-add-btn',
          title: 'Добавить сотрудника в отдел',
          onClick: (e: Event) => { e.stopPropagation(); p.data.onAddMember?.(p.data.deptId) },
        }),
      ]),
      // Название отдела — отдельной строкой на всю ширину
      h('div', { class: 'hnode-dept-name' }, p.data.label),
      // Target handle (вход) for user→dept "manager of dept" + отдел→отдел (этот подчинён)
      h(Handle, {
        type: 'target', position: Position.Left, id: 'tgt',
        style: 'background:#ff9800;width:12px;height:12px;border:2px solid white;left:-6px;top:18px',
      }),
      // Source handle (выход, справа) — тяни к другому отделу: тот станет подчинённым
      h(Handle, {
        type: 'source', position: Position.Right, id: 'src',
        style: 'background:#f57c00;width:12px;height:12px;border:2px solid white;right:-6px;top:18px;cursor:crosshair',
        title: 'Тяни к другому отделу — он станет подчинённым',
      }),
      matchPointer(p.data.matched),
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
        // Phase 30: если у пользователя загружено profile_photo — рендерим <img>, иначе инициалы
        p.data.photoUrl
          ? h('div', {
              class: 'hnode-avatar hnode-avatar--photo',
              style: p.data.orgColor ? `border:2px solid ${p.data.orgColor}` : '',
            }, [
              h('img', {
                src: p.data.photoUrl,
                alt: p.data.label,
                style: 'width:100%;height:100%;object-fit:cover;border-radius:inherit',
                onError: (e: any) => { e.target.style.display = 'none' },
              }),
            ])
          : h('div', {
              class: 'hnode-avatar',
              style: p.data.orgColor ? `background:linear-gradient(135deg,${p.data.orgColor},${p.data.orgColor}cc)` : '',
            }, p.data.initials || '?'),
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
          // Compact org/position count
          h('div', { style: 'display:flex;align-items:center;gap:6px;margin-top:2px' }, [
            h('div', { class: 'hnode-user-role', style: { color: roleColors[p.data.role] || '#666' } },
              roleLabels[p.data.role] || p.data.role),
            (() => {
              const orgs = p.data.userOrgs || []
              const orgCount = new Set(orgs.map((o: any) => o.org)).size
              const posCount = orgs.filter((o: any) => o.pos).length
              const tooltip = orgs.map((o: any) => [o.org, o.dept ? `(${o.dept})` : '', o.pos].filter(Boolean).join(' · ')).join('\n')
              return orgCount > 0 ? h('span', {
                style: 'font-size:9px;color:#666;cursor:default',
                title: tooltip,
              }, `${orgCount} орг. · ${posCount} долж.`) : null
            })(),
          ]),
        ]),
      ]),
      // Copy button (to place user in another dept/org)
      h('span', {
        class: 'mdi mdi-content-copy',
        style: 'position:absolute;top:4px;right:4px;font-size:12px;cursor:pointer;opacity:0.4;color:inherit',
        title: 'Копировать в другой отдел',
        onClick: (e: Event) => { e.stopPropagation(); document.dispatchEvent(new CustomEvent('hv-copy-user', { detail: p.data.userId })) },
      }),
      // Phase 30 restore: удаление пользователя (требует user.manage)
      p.data.canDeleteUser ? h('span', {
        class: 'mdi mdi-trash-can-outline',
        style: 'position:absolute;top:4px;right:22px;font-size:12px;cursor:pointer;opacity:0.6;color:#f44336',
        title: 'Удалить сотрудника',
        onClick: (e: Event) => { e.stopPropagation(); document.dispatchEvent(new CustomEvent('hv-delete-user', { detail: { id: p.data.userId, name: p.data.label, orgId: p.data.orgId } })) },
      }) : null,
      matchPointer(p.data.matched),
    ])
  },
})

const nodeTypes = { org: OrgNode, dept: DeptNode, user: UserNode }
const defaultEdgeOptions = { type: 'smoothstep' }
</script>

<style>
.vue-flow__edge-text { cursor: pointer; }
/* Dept node container — style applied to wrapper by VueFlow via node.style */
.vue-flow__node-dept { padding: 0 !important; overflow: visible !important; }
.vue-flow__node-user { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; }
.vue-flow__node-org  { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; }

/* Dark: dept container (VueFlow applies inline styles — override with !important) */
.v-theme--dark .vue-flow__node-dept > div[style] {
  background: rgba(0, 150, 130, 0.1) !important;
  border-color: #26a69a !important;
}

/* Dark: user/org node cards */
.v-theme--dark .hnode {
  background: var(--crm-surface) !important;
  border-color: var(--crm-border-strong) !important;
  box-shadow: 0 2px 12px rgba(0,0,0,0.5) !important;
}
.v-theme--dark .hnode:hover { border-color: #42a5f5 !important; }

/* Dark: text inside nodes */
.v-theme--dark .hnode-user-name { color: var(--crm-text) !important; }
.v-theme--dark .hnode-user-pos  { color: var(--crm-text-muted) !important; }
.v-theme--dark .hnode-user-role { color: var(--crm-text-faint) !important; }

/* Dark: VueFlow canvas & controls */
.v-theme--dark .vue-flow__background { background-color: var(--crm-bg) !important; }
.v-theme--dark .vue-flow__controls { background: var(--crm-surface) !important; border-color: var(--crm-border) !important; }
.v-theme--dark .vue-flow__controls-button { background: var(--crm-surface) !important; border-color: var(--crm-border) !important; fill: var(--crm-text) !important; }
.v-theme--dark .vue-flow__minimap { background: var(--crm-surface) !important; }

/* ── Поиск: подсветка совпавших узлов и гашение остальных ── */
.vue-flow__node.hv-node-dim { opacity: 0.18; filter: grayscale(0.6); transition: opacity .3s, filter .3s; }
.vue-flow__node.hv-node-match { z-index: 20 !important; transition: filter .3s; }
.vue-flow__node.hv-node-match .hnode,
.vue-flow__node.hv-node-match .hnode-dept-header-bar {
  outline: 3px solid #fb923c;
  outline-offset: 2px;
  border-radius: 12px;
  overflow: visible !important;
  box-shadow: 0 0 0 4px rgba(251,146,60,0.25), 0 0 22px 4px rgba(251,146,60,0.55) !important;
  animation: hv-match-glow 1.3s ease-in-out infinite;
}
@keyframes hv-match-glow {
  0%, 100% { box-shadow: 0 0 0 4px rgba(251,146,60,0.20), 0 0 16px 2px rgba(251,146,60,0.45) !important; }
  50%      { box-shadow: 0 0 0 6px rgba(251,146,60,0.35), 0 0 30px 8px rgba(251,146,60,0.75) !important; }
}

/* «Вьющаяся» стрелка-указатель над совпавшим узлом */
.hv-pointer {
  position: absolute;
  top: -42px;
  left: 50%;
  margin-left: -16px;
  width: 32px;
  height: 36px;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  pointer-events: none;
  z-index: 30;
  filter: drop-shadow(0 2px 4px rgba(0,0,0,0.35));
  animation: hv-pointer-wiggle 0.9s ease-in-out infinite;
}
.hv-pointer .mdi {
  font-size: 30px;
  color: #fb923c;
  line-height: 1;
}
@keyframes hv-pointer-wiggle {
  0%   { transform: translateY(0)    rotate(-10deg); }
  25%  { transform: translateY(-6px) rotate(10deg); }
  50%  { transform: translateY(0)    rotate(-8deg); }
  75%  { transform: translateY(-4px) rotate(8deg); }
  100% { transform: translateY(0)    rotate(-10deg); }
}
</style>

<style scoped>
.hierarchy-canvas { flex: 1; min-height: 0; width: 100%; }

/* ── Node styles ── */
:deep(.hnode) {
  background: var(--crm-surface);
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.12);
  min-width: 160px;
  overflow: hidden;
  cursor: grab;
  transition: box-shadow 0.15s;
  border: 1.5px solid var(--crm-border-strong);
}
:deep(.hnode:hover) {
  box-shadow: 0 4px 16px rgba(0,0,0,0.18);
  border-color: rgb(var(--v-theme-primary));
}

/* Org node */
:deep(.hnode-org) { min-width: 200px; max-width: 280px; border-color: #1565c0; }
:deep(.hnode-org-inn) { padding: 4px 14px 8px; font-size: 11px; color: var(--crm-text-secondary, #607d8b); }
:deep(.hnode-header) { display: flex; align-items: center; gap: 8px; padding: 10px 14px; font-weight: 600; font-size: 13px; }
:deep(.hnode-header-org) { background: linear-gradient(135deg, #1565c0, #1e88e5); color: white; }
:deep(.hnode-icon) { font-size: 16px; }
:deep(.hnode-title) { flex: 1; white-space: normal; word-break: break-word; line-height: 1.3; overflow: visible; }

/* Dept header bar (inside the dashed container) */
:deep(.hnode-dept-header-bar) {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 12px;
  background: linear-gradient(135deg, #00695c, #26a69a);
  color: white;
  font-weight: 600;
  font-size: 13px;
  border-radius: 8px 8px 0 0;
  min-height: 76px;
  position: relative;
}
:deep(.hnode-dept-toprow) {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  width: 100%;
}
:deep(.hnode-dept-name) {
  width: 100%;
  white-space: normal;
  word-break: break-word;
  line-height: 1.3;
  font-size: 13px;
  font-weight: 600;
}
:deep(.hnode-dept-orgbadge) {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  color: #fff;
  opacity: 0.95;
  font-weight: 600;
  flex-shrink: 1;
  min-width: 0;
  max-width: 100%;
  white-space: normal;
  word-break: break-word;
  line-height: 1.25;
}
:deep(.hnode-dept-badge) {
  background: rgba(255,255,255,0.3);
  border-radius: 12px;
  padding: 1px 8px;
  font-size: 11px;
  font-weight: 700;
  margin-left: auto;
  flex-shrink: 0;
}
:deep(.hnode-dept-add-btn) {
  cursor: pointer;
  font-size: 18px;
  margin-left: 6px;
  flex-shrink: 0;
  padding: 2px 4px;
  border-radius: 4px;
  opacity: 0.85;
  transition: background 0.15s, opacity 0.15s;
}
:deep(.hnode-dept-add-btn:hover) {
  background: rgba(255,255,255,0.25);
  opacity: 1;
}
:deep(.hnode-dept-del-btn) {
  cursor: pointer;
  font-size: 16px;
  flex-shrink: 0;
  padding: 2px 4px;
  border-radius: 4px;
  opacity: 0.75;
  transition: background 0.15s, opacity 0.15s;
  color: #f44336;
}
:deep(.hnode-dept-del-btn:hover) {
  background: rgba(244,67,54,0.2);
  opacity: 1;
}

/* User node */
:deep(.hnode-user) { min-width: 180px; width: 240px; border-color: #e0e0e0; }
:deep(.hnode-user-row) { display: flex; align-items: flex-start; gap: 10px; padding: 10px 14px; }
:deep(.hnode-avatar) {
  width: 32px; height: 44px; border-radius: 8px;
  background: linear-gradient(135deg, rgb(var(--v-theme-primary)), #1e88e5);
  color: white; display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: bold; flex-shrink: 0; margin-top: 2px;
  overflow: hidden;
}
/* Phase 30: фото профиля вместо инициалов */
:deep(.hnode-avatar--photo) {
  background: transparent !important;
  padding: 0;
}
:deep(.hnode-avatar--photo img) {
  width: 100%; height: 100%; object-fit: cover; border-radius: inherit;
  display: block;
}
:deep(.hnode-user-info) { flex: 1; min-width: 0; }
:deep(.hnode-user-name) { font-weight: 600; font-size: 13px; white-space: normal; word-break: break-word; overflow: visible; display: flex; align-items: flex-start; flex-wrap: wrap; line-height: 1.3; }
:deep(.hnode-user-pos) { font-size: 11px; color: var(--crm-text-muted); margin-top: 2px; white-space: normal; word-break: break-word; line-height: 1.3; }
:deep(.hnode-user-role) { font-size: 10px; margin-top: 2px; opacity: 0.75; }
:deep(.hnode-crown) { color: #f59e0b; font-size: 13px; margin-right: 4px; }

/* VueFlow controls */
:deep(.vue-flow__controls) { bottom: 16px; left: 16px; }
:deep(.vue-flow__minimap) { bottom: 16px; right: 16px; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.15); }
</style>
