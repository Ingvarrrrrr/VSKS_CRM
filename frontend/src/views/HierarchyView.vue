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
      <v-btn size="small" variant="tonal" color="teal" prepend-icon="mdi-plus" @click="newDeptDialog.show = true" class="ml-2">
        Добавить отдел
      </v-btn>
      <v-btn size="small" variant="tonal" color="indigo" prepend-icon="mdi-account-plus" @click="emit('create-user')" class="ml-2">
        Добавить сотрудника
      </v-btn>
      <v-btn v-if="isSuperadmin || isAccountOwner" size="small" variant="tonal" color="deep-purple" prepend-icon="mdi-domain" @click="newOrgDialog.show = true" class="ml-2">
        Организация
      </v-btn>
      <v-spacer />
      <div class="d-flex align-center ga-3 mr-3">
        <div class="d-flex align-center ga-1">
          <div class="legend-line legend-green" />
          <span class="text-caption">Подчинённость</span>
        </div>
        <div class="d-flex align-center ga-1">
          <div class="legend-line legend-orange" />
          <span class="text-caption">Начальник отдела</span>
        </div>
        <div class="d-flex align-center ga-1">
          <div class="legend-line legend-purple" />
          <span class="text-caption">Управляет организацией</span>
        </div>
        <div class="d-flex align-center ga-1">
          <div class="legend-rect legend-dept" />
          <span class="text-caption">Отдел</span>
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
            <v-list-item prepend-icon="mdi-plus-circle-outline">
              <v-list-item-title class="text-body-2">Нажми <strong>+</strong> в заголовке отдела — добавить сотрудника в отдел</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-drag">
              <v-list-item-title class="text-body-2">Перетащи сотрудника <strong>внутри</strong> отдела — изменить порядок</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-drag">
              <v-list-item-title class="text-body-2">Перетащи сотрудника <strong>за пределы</strong> отдела — он выйдет из отдела</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-drag">
              <v-list-item-title class="text-body-2">Перетащи свободного сотрудника <strong>на отдел</strong> — он вступит в отдел</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-arrow-right-circle">
              <v-list-item-title class="text-body-2">Тяни от <strong>→</strong> (зелёная точка) сотрудника к другому — создаётся связь подчинённости</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-domain">
              <v-list-item-title class="text-body-2">Тяни от сотрудника к <strong>организации</strong> — он станет руководителем всей организации (фиолетовая стрелка)</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-crown">
              <v-list-item-title class="text-body-2">Корона — начальник отдела. При добавлении в отдел с начальником связь создаётся автоматически</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-close-circle-outline">
              <v-list-item-title class="text-body-2">Нажми <strong>×</strong> на стрелке — удалить связь</v-list-item-title>
            </v-list-item>
            <v-list-item prepend-icon="mdi-auto-fix">
              <v-list-item-title class="text-body-2">"Авторасстановка" — автоматически расставить по рангу (начальник → зам → специалист)</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn color="primary" variant="flat" @click="helpDialog = false">Понятно</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <Teleport to="body">
      <v-dialog v-model="colorPickerVisible" max-width="360" :z-index="9999">
        <v-card>
          <v-card-title class="pa-4 text-body-1">
            <v-icon icon="mdi-palette" class="mr-2" />Цвет организации
          </v-card-title>
          <v-card-text class="pa-4 pt-0 d-flex flex-wrap gap-2 justify-center">
            <div
              v-for="c in ORG_COLORS_HV"
              :key="c"
              :style="{ background: c, width: '32px', height: '32px', borderRadius: '50%', cursor: 'pointer', border: '2px solid #fff', boxShadow: '0 1px 3px rgba(0,0,0,0.3)' }"
              @click="applyOrgColor(c)"
            />
          </v-card-text>
          <v-card-actions class="pa-4 pt-0">
            <v-spacer />
            <v-btn variant="text" @click="colorPickerVisible = false">Отмена</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </Teleport>

    <!-- Copy user to dept dialog -->
    <Teleport to="body">
      <v-dialog v-model="copyUserDialog.show" max-width="420" :z-index="9999">
        <v-card>
          <v-card-title class="pa-4 text-body-1">
            <v-icon icon="mdi-content-copy" class="mr-2" />Копировать «{{ copyUserDialog.userName }}» в отдел
          </v-card-title>
          <v-card-text class="pa-4 pt-0">
            <v-select
              v-model="copyTargetDeptId"
              :items="(_lastGraphData?.departments || []).map(d => ({ title: d.name + ' (' + ((_lastGraphData?.orgs || []).find(o => o.id === d.org_id)?.name || '') + ')', value: d.id }))"
              item-title="title"
              item-value="value"
              label="Целевой отдел"
              variant="outlined"
              density="compact"
            />
          </v-card-text>
          <v-card-actions class="pa-4 pt-0">
            <v-spacer />
            <v-btn variant="text" @click="copyUserDialog.show = false">Отмена</v-btn>
            <v-btn color="teal" variant="flat" :disabled="!copyTargetDeptId" @click="confirmCopyUser">Добавить</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </Teleport>

    <!-- User info dialog -->
    <Teleport to="body">
      <v-dialog v-model="userInfoDialog.show" max-width="520" :z-index="9999">
        <v-card>
          <v-card-title class="pa-4 text-body-1">
            <v-icon icon="mdi-account-details" class="mr-2" />{{ userInfoDialog.userName }}
          </v-card-title>
          <v-card-text class="pa-4 pt-0">
            <div v-if="!userInfoDialog.orgs.length" class="text-medium-emphasis">Нет данных об организациях</div>
            <div v-for="o in userInfoDialog.orgs" :key="o.org_id" class="mb-3 pa-3 rounded" style="background:rgba(0,0,0,0.03)">
              <div class="d-flex align-center gap-2 mb-2">
                <v-chip size="small" :color="o.is_primary ? 'primary' : 'grey'" variant="tonal">{{ o.org_name || `Орг #${o.org_id}` }}</v-chip>
                <v-chip v-if="o.is_primary" size="x-small" color="blue" variant="flat">основная</v-chip>
              </div>
              <v-row dense>
                <v-col cols="12" md="4">
                  <v-text-field v-model="o.position" label="Должность" variant="outlined" density="compact" hide-details @blur="saveUserOrgSalary(o.org_id)" />
                </v-col>
                <v-col cols="6" md="4">
                  <v-text-field v-model.number="o.salary_amount" label="Оклад, ₽" variant="outlined" density="compact" type="number" hide-details @blur="saveUserOrgSalary(o.org_id)" />
                </v-col>
                <v-col cols="6" md="4">
                  <v-text-field v-model.number="o.employment_percent" label="% ставки" variant="outlined" density="compact" type="number" hide-details @blur="saveUserOrgSalary(o.org_id)" />
                </v-col>
              </v-row>
            </div>
          </v-card-text>
          <v-card-actions class="pa-4 pt-0">
            <v-btn variant="text" color="primary" prepend-icon="mdi-pencil" @click="userInfoDialog.show = false; emit('edit-user', userInfoDialog.userId)">Редактировать</v-btn>
            <v-spacer />
            <v-btn variant="text" @click="userInfoDialog.show = false">Закрыть</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </Teleport>

    <!-- Edit org dialog -->
    <Teleport to="body">
      <v-dialog v-model="editOrgDialog.show" max-width="420" :z-index="9999">
        <v-card>
          <v-card-title class="pa-4 text-body-1">
            <v-icon icon="mdi-domain" class="mr-2" />Редактировать организацию
          </v-card-title>
          <v-card-text class="pa-4 pt-0">
            <v-text-field v-model="editOrgDialog.name" label="Название" variant="outlined" density="compact" class="mb-3" />
            <v-text-field v-model="editOrgDialog.inn" label="ИНН" variant="outlined" density="compact" />
          </v-card-text>
          <v-card-actions class="pa-4 pt-0">
            <v-spacer />
            <v-btn variant="text" @click="editOrgDialog.show = false">Отмена</v-btn>
            <v-btn color="primary" variant="flat" @click="saveOrg">Сохранить</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </Teleport>

    <!-- New dept dialog -->
    <v-dialog v-model="newDeptDialog.show" max-width="420">
      <v-card>
        <v-card-title class="pa-4">
          <v-icon icon="mdi-account-group" color="teal" class="mr-2" />
          Новый отдел
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-text-field
            v-model="newDeptDialog.name"
            label="Название отдела"
            prepend-inner-icon="mdi-account-group-outline"
            autofocus
            class="mb-3"
            @keydown.enter="createNewDept"
          />
          <v-select
            v-if="graphOrgs.length > 1"
            v-model="newDeptDialog.orgId"
            :items="graphOrgs"
            item-title="name"
            item-value="id"
            label="Организация"
            variant="outlined"
            density="compact"
            prepend-inner-icon="mdi-domain"
            hint="К какой организации относится отдел"
            persistent-hint
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="newDeptDialog.show = false">Отмена</v-btn>
          <v-btn color="teal" variant="flat" :disabled="!newDeptDialog.name.trim()" @click="createNewDept">Создать</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Add member to dept dialog -->
    <v-dialog v-model="addMemberDialog.show" max-width="420">
      <v-card>
        <v-card-title class="pa-4">
          <v-icon icon="mdi-account-plus" color="teal" class="mr-2" />
          Добавить сотрудника в отдел
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-autocomplete
            v-model="addMemberSelectedId"
            :items="addMemberDialog.available"
            item-title="label"
            item-value="id"
            label="Выберите сотрудника"
            no-data-text="Нет доступных сотрудников"
            prepend-inner-icon="mdi-account-search"
            clearable
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-btn variant="text" color="primary" prepend-icon="mdi-account-plus" @click="addMemberDialog.show = false; emit('create-user')">
            Создать нового
          </v-btn>
          <v-spacer />
          <v-btn variant="text" @click="addMemberDialog.show = false">Отмена</v-btn>
          <v-btn color="teal" variant="flat" :disabled="!addMemberSelectedId" :loading="addMemberLoading" @click="confirmAddMember">Добавить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete dept confirm dialog -->
    <v-dialog v-model="deleteDeptConfirm.show" max-width="380">
      <v-card>
        <v-card-title class="pa-4">
          <v-icon icon="mdi-delete-alert" color="error" class="mr-2" />
          Удалить отдел
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          Удалить отдел <strong>«{{ deleteDeptConfirm.name }}»</strong>?
          Все сотрудники станут «Вне отдела».
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="deleteDeptConfirm.show = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" @click="confirmDeleteDept">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- New org dialog (superadmin only) -->
    <v-dialog v-model="newOrgDialog.show" max-width="420">
      <v-card>
        <v-card-title class="pa-4">
          <v-icon icon="mdi-domain" color="deep-purple" class="mr-2" />
          Новая организация
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-text-field
            v-model="newOrgDialog.name"
            label="Название организации"
            prepend-inner-icon="mdi-domain"
            autofocus
            class="mb-3"
            @keydown.enter="createNewOrg"
          />
          <v-text-field
            v-model="newOrgDialog.inn"
            label="ИНН (необязательно)"
            prepend-inner-icon="mdi-identifier"
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="newOrgDialog.show = false">Отмена</v-btn>
          <v-btn color="deep-purple" variant="flat" :disabled="!newOrgDialog.name.trim()" :loading="newOrgDialog.loading" @click="createNewOrg">Создать</v-btn>
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
const emit = defineEmits<{ 'edit-user': [id: number]; 'edit-dept': [id: number]; 'create-user': []; 'data-changed': [] }>()

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
const DEPT_W = 268     // dept container width in px
const USER_W = 240     // user node width in px
const USER_H = 88      // user node height in px (name + position + role + counts)
const DEPT_HEADER_H = 60
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

// ── Rank sorting ───────────────────────────────────────────────────────────────

function getPositionRank(position: string | null): number {
  if (!position) return 10
  const p = position.toLowerCase()
  if (p.includes('начальник') || p.includes('директор') || p.includes('руководитель')) return 1
  if (p.includes('зам')) return 2
  if (p.includes('главный') || p.includes('ведущий')) return 3
  if (p.includes('старший')) return 4
  if (p.includes('специалист') || p.includes('инженер')) return 5
  return 8
}

function sortDeptMembers(
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

// ── State ──────────────────────────────────────────────────────────────────────
const nodes = ref<Node[]>([])
const edges = ref<Edge[]>([])
const loading = ref(false)
const helpDialog = ref(false)
const snack = ref({ show: false, text: '', color: 'success' })
const showSnack = (text: string, color = 'success') => { snack.value = { show: true, text, color } }

const isSuperadmin = localStorage.getItem('user_role') === 'superadmin'
const isAccountOwner = localStorage.getItem('user_role') === 'account_owner'

const newDeptDialog = ref({ show: false, name: '', orgId: null as number | null })
const newOrgDialog = ref({ show: false, name: '', inn: '', loading: false })
const graphOrgs = ref<{ id: number; name: string }[]>([])
const addMemberDialog = ref<{ show: boolean; deptId: number | null; available: { id: number; label: string }[] }>({
  show: false, deptId: null, available: [],
})
const addMemberSelectedId = ref<number | null>(null)
const addMemberLoading = ref(false)

// ── Custom node components ─────────────────────────────────────────────────────

const OrgNode = markRaw({
  name: 'OrgNode',
  props: ['data'],
  setup(p: any) {
    return () => h('div', { class: 'hnode hnode-org' }, [
      // Purple target handle for user→org "manager of org" edges
      h(Handle, {
        type: 'target', position: Position.Left, id: 'tgt',
        style: 'background:#9c27b0;width:14px;height:14px;border:2px solid white;left:-7px',
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
      ]),
    ])
  },
})

const ORG_COLORS_HV = [
  '#1976d2','#9c27b0','#ff9800','#009688','#3f51b5','#e91e63','#795548',
  '#d32f2f','#388e3c','#1565c0','#6a1b9a','#ef6c00','#00838f','#c62828',
  '#2e7d32','#283593','#ad1457','#4e342e','#00695c','#bf360c','#0277bd',
  '#7b1fa2','#f9a825','#00897b','#5c6bc0','#d81b60','#6d4c41','#00acc1',
  '#e65100','#1b5e20','#4a148c','#ff6f00','#004d40','#b71c1c','#0d47a1',
  '#880e4f','#33691e','#311b92','#e64a19','#006064','#827717','#4527a0',
  '#ff8f00','#1a237e','#c51162','#558b2f','#512da8','#ff6d00','#0097a7',
  '#9e9d24','#7c4dff',
]
const DeptNode = markRaw({
  name: 'DeptNode',
  props: ['data'],
  setup(p: any) {
    return () => h('div', { class: 'hnode-dept-header-bar', style: p.data.orgColor ? `background:linear-gradient(135deg, ${p.data.orgColor}, ${p.data.orgColor}aa)` : '' }, [
      h('span', { class: 'mdi mdi-account-group', style: 'font-size:16px;margin-right:6px;flex-shrink:0' }),
      h('span', { class: 'hnode-title', style: 'flex:1;min-width:0' }, p.data.label),
      p.data.orgName
        ? h('span', {
            style: `font-size:10px;padding:1px 6px;border-radius:8px;margin-right:4px;flex-shrink:0;background:${p.data.orgColor || '#1976d2'};color:#fff;opacity:0.9`,
          }, p.data.orgName)
        : null,
      h('span', { class: 'hnode-dept-badge' }, `${p.data.memberCount}`),
      // "+" button to add member to dept
      h('span', {
        class: 'mdi mdi-plus hnode-dept-add-btn',
        title: 'Добавить сотрудника в отдел',
        onClick: (e: Event) => { e.stopPropagation(); p.data.onAddMember?.(p.data.deptId) },
      }),
      // delete dept button
      h('span', {
        class: 'mdi mdi-delete-outline hnode-dept-del-btn',
        title: 'Удалить отдел',
        onClick: (e: Event) => { e.stopPropagation(); p.data.onDelete?.(p.data.deptId) },
      }),
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
        h('div', { class: 'hnode-avatar', style: p.data.orgColor ? `background:linear-gradient(135deg,${p.data.orgColor},${p.data.orgColor}cc)` : '' },
          p.data.initials || '?',
        ),
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
    ])
  },
})

const nodeTypes = { org: OrgNode, dept: DeptNode, user: UserNode }
const defaultEdgeOptions = { type: 'smoothstep' }

// ── VueFlow composable ─────────────────────────────────────────────────────────
const { addEdges, removeEdges, fitView, onEdgeClick, onNodeDragStop, onNodeDoubleClick } = useVueFlow()

const editOrgDialog = ref({ show: false, id: 0, name: '', inn: '' })

const userInfoDialog = ref({ show: false, userId: 0, userName: '', orgs: [] as any[], saving: false })
async function openUserInfo(userId: number) {
  try {
    const [orgsResp, salaryData] = await Promise.all([
      apiFetch<any>(`/users/${userId}/organizations`),
      apiFetch<any[]>(`/users/${userId}/salary`).catch(() => []),
    ])
    // Merge primary + extra into flat list
    const allOrgs: any[] = []
    if (orgsResp.primary) {
      allOrgs.push({ org_id: orgsResp.primary.id, org_name: orgsResp.primary.name, position: orgsResp.primary.position || '', is_primary: true })
    }
    for (const e of (orgsResp.extra || [])) {
      allOrgs.push({ org_id: e.org_id || e.id, org_name: e.org_name || e.name || '', position: e.position || '', is_primary: false })
    }
    // Merge salary data
    const salaryMap = new Map((salaryData || []).map((s: any) => [s.org_id, s]))
    for (const o of allOrgs) {
      const s: any = salaryMap.get(o.org_id) || {}
      o.salary_amount = s.salary_amount ?? null
      o.employment_percent = s.employment_percent ?? null
    }
    const user = _lastGraphData.value?.users.find(u => u.id === userId)
    userInfoDialog.value = { show: true, userId, userName: user?.full_name || user?.username || '', orgs: allOrgs, saving: false }
  } catch { emit('edit-user', userId) }
}

async function saveUserOrgSalary(orgId: number) {
  const o = userInfoDialog.value.orgs.find((x: any) => x.org_id === orgId)
  if (!o) return
  userInfoDialog.value.saving = true
  try {
    await apiFetch(`/users/${userInfoDialog.value.userId}/organizations/${orgId}`, {
      method: 'PATCH',
      body: { position: o.position, salary_amount: o.salary_amount, employment_percent: o.employment_percent },
    })
  } catch {}
  userInfoDialog.value.saving = false
}

onNodeDoubleClick(({ node }) => {
  if (node.type === 'user') {
    const userId = parseInt(node.id.replace(/user-(\d+).*/, '$1'))
    emit('edit-user', userId)
  }
  else if (node.type === 'dept') emit('edit-dept', parseInt(node.id.replace('dept-', '')))
  else if (node.type === 'org') {
    const orgId = parseInt(node.id.replace('org-', ''))
    const org = _lastGraphData.value?.orgs.find(o => o.id === orgId)
    if (org) {
      editOrgDialog.value = { show: true, id: orgId, name: (org as any).name || '', inn: (org as any).inn || '' }
    }
  }
})

async function saveOrg() {
  try {
    await apiFetch(`/organizations/${editOrgDialog.value.id}`, {
      method: 'PUT',
      body: { name: editOrgDialog.value.name, inn: editOrgDialog.value.inn },
    })
    editOrgDialog.value.show = false
    showSnack('Организация обновлена')
    await loadGraph()
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка сохранения', 'error')
  }
}

// ── Graph data ─────────────────────────────────────────────────────────────────

interface GraphData {
  orgs: { id: number; name: string }[]
  departments: { id: number; name: string; org_id: number; head_user_id: number | null; member_ids: number[] }[]
  users: { id: number; full_name: string | null; username: string; role: string; org_id: number; extra_org_ids: number[]; avatar: string | null; position: string | null }[]
  user_user_edges: { id: number; manager_id: number; subordinate_id: number }[]
  user_dept_edges: { id: number; manager_user_id: number; dept_id: number }[]
  user_org_edges: { id: number; manager_user_id: number; org_id: number }[]
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
const ORDER_KEY = 'hierarchy_dept_order'
const ORG_COLOR_KEY = 'hierarchy_org_colors'

function loadOrgColors(): Record<number, string> {
  try { return JSON.parse(localStorage.getItem(ORG_COLOR_KEY) || '{}') } catch { return {} }
}
function saveOrgColor(orgId: number, color: string) {
  const colors = loadOrgColors()
  colors[orgId] = color
  localStorage.setItem(ORG_COLOR_KEY, JSON.stringify(colors))
}
function getOrgColor(orgId: number, fallbackIdx: number): string {
  const saved = loadOrgColors()[orgId]
  return saved || ORG_COLORS_HV[fallbackIdx % ORG_COLORS_HV.length]
}

// Color picker state
const colorPickerOrgId = ref<number | null>(null)
const colorPickerVisible = ref(false)
function pickOrgColor(orgId: number) {
  colorPickerOrgId.value = orgId
  colorPickerVisible.value = true
}
// Copy user — shows dialog to pick target dept
const copyUserDialog = ref({ show: false, userId: 0, userName: '' })
const copyTargetDeptId = ref<number | null>(null)

function startCopyUser(userId: number) {
  const user = _lastGraphData.value?.users.find(u => u.id === userId)
  if (!user) return
  copyUserDialog.value = { show: true, userId, userName: user.full_name || user.username }
  copyTargetDeptId.value = null
}

async function confirmCopyUser() {
  if (!copyTargetDeptId.value) return
  try {
    await apiFetch(`/departments/${copyTargetDeptId.value}/members`, { method: 'POST', body: { user_id: copyUserDialog.value.userId } })
    copyUserDialog.value.show = false
    showSnack('Сотрудник добавлен в отдел')
    await loadGraph()
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка', 'error')
  }
}

// Listen for custom events from render functions
onMounted(() => {
  document.addEventListener('hv-pick-color', ((e: CustomEvent) => {
    pickOrgColor(e.detail)
  }) as EventListener)
  document.addEventListener('hv-copy-user', ((e: CustomEvent) => {
    startCopyUser(e.detail)
  }) as EventListener)
})
function applyOrgColor(color: string) {
  if (colorPickerOrgId.value != null) {
    saveOrgColor(colorPickerOrgId.value, color)
    colorPickerVisible.value = false
    colorPickerOrgId.value = null
    rebuildGraph() // instant rebuild with new color, no API call
  }
}

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

const _orgNameMap = new Map<number, string>()

// ── Build graph ────────────────────────────────────────────────────────────────

function buildGraph(data: GraphData) {
  const savedPos = loadPositions()
  const deptOrders = loadDeptOrders()
  const newNodes: Node[] = []
  const newEdges: Edge[] = []

  // Store orgs list for dialogs
  graphOrgs.value = data.orgs
  if (newDeptDialog.value.orgId === null && data.orgs.length === 1) {
    newDeptDialog.value.orgId = data.orgs[0].id
  }

  // Build org name map for extra org badges (module-level for drag handlers)
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
  data.orgs.forEach((org, oi) => {
    const id = `org-${org.id}`
    const oColor = getOrgColor(org.id, oi)
    newNodes.push({
      id, type: 'org',
      position: savedPos[id] || { x: 80 + oi * 320, y: 60 },
      data: { label: org.name, orgColor: oColor, orgId: org.id, onColorPick: pickOrgColor },
      draggable: true,
    })
  })

  // Dept nodes
  const orgList = data.orgs || []
  data.departments.forEach((dept, di) => {
    const id = `dept-${dept.id}`
    const mc = dept.member_ids.length
    const orgIdx = orgList.findIndex((o: any) => o.id === dept.org_id)
    const orgName = orgList.length > 1 ? orgList[orgIdx]?.name : null
    const orgColor = getOrgColor(dept.org_id, orgIdx >= 0 ? orgIdx : 0)
    newNodes.push({
      id, type: 'dept',
      position: savedPos[id] || { x: 80 + di * (DEPT_W + 40), y: 200 },
      style: { ...mkDeptStyle(mc), background: `${orgColor}0D`, border: `2px dashed ${orgColor}` },
      data: {
        label: dept.name,
        memberCount: mc,
        headUserId: dept.head_user_id,
        deptId: dept.id,
        orgName,
        orgColor,
        onAddMember: (deptId: number) => openAddMemberDialog(deptId),
        onDelete: (deptId: number) => deleteDeptNode(deptId),
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
        const uOrgColor = getOrgColor(uOrgId, uOrgIdx >= 0 ? uOrgIdx : 0)
        // Unique id per dept placement (first keeps original id for edge compatibility)
        const nodeId = ci === 0 ? `user-${user.id}` : `user-${user.id}-d${di.deptId}`
        const defaultRelPos = { x: 10, y: DEPT_HEADER_H + 4 + di.idx * (USER_H + USER_GAP) }
        newNodes.push({
          id: nodeId, type: 'user',
          parentNode: `dept-${di.deptId}`,
          position: savedPos[nodeId] || defaultRelPos,
          data: { label: user.full_name || user.username, role: user.role, initials: getInitials(user.full_name, user.username), isHead, position: user.position, extraOrgNames, orgColor: uOrgColor, orgCount, userId: user.id, deptOrgName: dept ? (orgNameMap.get(dept.org_id) || '') : '', userOrgs: (user as any).user_orgs || [] },
          draggable: true,
          zIndex: 1000,
        })
      }
    } else {
      const col = freeIdx % 4
      const row = Math.floor(freeIdx / 4)
      const freeOrgIdx = orgList.findIndex((o: any) => o.id === user.org_id)
      const freeOrgColor = getOrgColor(user.org_id, freeOrgIdx >= 0 ? freeOrgIdx : 0)
      const freeId = `user-${user.id}`
      newNodes.push({
        id: freeId, type: 'user',
        position: savedPos[freeId] || { x: 80 + col * 240, y: 600 + row * 80 },
        data: { label: user.full_name || user.username, role: user.role, initials: getInitials(user.full_name, user.username), isHead: false, position: user.position, extraOrgNames, orgColor: freeOrgColor, orgCount, userId: user.id, deptOrgName: orgNameMap.get(user.org_id) || '', userOrgs: (user as any).user_orgs || [] },
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

  // user-org edges (manager of entire org — purple)
  for (const e of (data.user_org_edges || [])) {
    newEdges.push({
      id: `uo-${e.id}`,
      source: `user-${e.manager_user_id}`,
      target: `org-${e.org_id}`,
      type: 'smoothstep',
      animated: true,
      style: { stroke: '#9c27b0', strokeWidth: 2.5 },
      markerEnd: { type: 'arrowclosed', color: '#9c27b0' },
      label: '×',
      labelStyle: { cursor: 'pointer', fill: '#f44336', fontWeight: 'bold', fontSize: '14px' },
      data: { relation_id: e.id, relation_type: 'user_org' },
    })
  }

  nodes.value = newNodes
  edges.value = newEdges
}

const _lastGraphData = ref<GraphData | null>(null)

async function loadGraph() {
  loading.value = true
  try {
    const data = await apiFetch<GraphData>('/hierarchy/graph')
    _lastGraphData.value = data
    buildGraph(data)
    emit('data-changed')
  } catch {
    showSnack('Ошибка загрузки графа', 'error')
  } finally {
    loading.value = false
  }
}

function rebuildGraph() {
  if (_lastGraphData.value) buildGraph(_lastGraphData.value)
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

  // Users inside depts: sort by rank, then arrange in column
  for (const dept of deptNodes) {
    const children = nodes.value.filter(n => n.type === 'user' && n.parentNode === dept.id)
    const headUserId = (dept.data as any).headUserId as number | null
    // Sort by rank
    const sorted = [...children].sort((a, b) => {
      const aid = parseInt(a.id.replace('user-', ''))
      const bid = parseInt(b.id.replace('user-', ''))
      if (aid === headUserId) return -1
      if (bid === headUserId) return 1
      const ra = getPositionRank((a.data as any).position || null)
      const rb = getPositionRank((b.data as any).position || null)
      return ra - rb
    })
    sorted.forEach((u, i) => {
      u.position = { x: 10, y: DEPT_HEADER_H + 4 + i * (USER_H + USER_GAP) }
    })
    // Save sorted order
    const deptId = parseInt(dept.id.replace('dept-', ''))
    saveDeptOrder(deptId, sorted.map(u => parseInt(u.id.replace('user-', ''))))
    // Resize dept
    const newH = Math.max(calcDeptHeight(sorted.length), 80)
    dept.style = { ...dept.style as object, height: `${newH}px` }
    ;(dept.data as any).memberCount = sorted.length
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

// ── Snap to slot (reorder within dept) ────────────────────────────────────────

function snapToSlot(draggedNode: Node) {
  if (!draggedNode.parentNode) return
  const deptId = parseInt(draggedNode.parentNode.replace('dept-', ''))
  const siblings = nodes.value.filter(n => n.type === 'user' && n.parentNode === draggedNode.parentNode)

  // Sort all users in dept by current y position to determine new order
  const sorted = [...siblings].sort((a, b) => a.position.y - b.position.y)
  const newOrderIds = sorted.map(n => parseInt(n.id.replace('user-', '')))

  // Snap each to their slot position
  nodes.value = nodes.value.map(n => {
    const idx = sorted.findIndex(u => u.id === n.id)
    if (idx >= 0 && n.parentNode === draggedNode.parentNode) {
      return { ...n, position: { x: 10, y: DEPT_HEADER_H + 4 + idx * (USER_H + USER_GAP) } }
    }
    return n
  })

  saveDeptOrder(deptId, newOrderIds)
  savePositions(nodes.value)
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
          emit('data-changed')
        } catch (e: any) {
          showSnack(e?.message || 'Ошибка: нельзя вывести из отдела', 'error')
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
        const tDept = _lastGraphData.value?.departments.find(d => d.id === deptId)
        if (tDept) {
          const user = _lastGraphData.value?.users.find(u => u.id === userId)
          const userOrgIds = new Set([user?.org_id, ...(user?.extra_org_ids || [])])
          if (!userOrgIds.has(tDept.org_id)) {
            try { await apiFetch(`/users/${userId}/organizations/${tDept.org_id}`, { method: 'POST', body: {} }) } catch {}
          }
        }
        showSnack('Сотрудник добавлен в отдел')

        // Update nodes locally — no full reload to avoid flicker
        // Backend may have removed user from another dept (exclusive membership)
        // Find if user was visually inside another dept and remove them
        const oldParentId = node.parentNode
        if (oldParentId && oldParentId !== targetDept.id) {
          const oldRemaining = nodes.value.filter(n => n.parentNode === oldParentId && n.id !== node.id).length
          nodes.value = nodes.value.map(n => {
            if (n.id === oldParentId) {
              const newH = Math.max(calcDeptHeight(oldRemaining), 80)
              return { ...n, style: { ...n.style as object, height: `${newH}px` }, data: { ...(n.data as object), memberCount: oldRemaining } }
            }
            return n
          })
        }

        // Count existing children in target dept (excluding this user)
        const existingCount = nodes.value.filter(n => n.parentNode === targetDept.id && n.id !== node.id).length
        const relPos = { x: 10, y: DEPT_HEADER_H + 4 + existingCount * (USER_H + USER_GAP) }
        const newCount = existingCount + 1

        // Determine new org color for the target dept
        const tDeptData = _lastGraphData.value?.departments.find(d => d.id === parseInt(targetDept.id.replace('dept-', '')))
        const tOrgId = tDeptData?.org_id
        const tOrgIdx = tOrgId ? (_lastGraphData.value?.orgs || []).findIndex(o => o.id === tOrgId) : -1
        const newOrgColor = tOrgId ? getOrgColor(tOrgId, tOrgIdx >= 0 ? tOrgIdx : 0) : undefined

        nodes.value = nodes.value.map(n => {
          if (n.id === node.id) {
            const tOrgName = tOrgId ? (_orgNameMap.get(tOrgId) || '') : (n.data as any).deptOrgName
            const updatedData = { ...(n.data as object), orgColor: newOrgColor || (n.data as any).orgColor, deptOrgName: tOrgName }
            return { ...n, parentNode: targetDept.id, position: relPos, zIndex: 1000, data: updatedData }
          }
          if (n.id === targetDept.id) {
            const newH = Math.max(calcDeptHeight(newCount), 80)
            return { ...n, style: { ...n.style as object, height: `${newH}px` }, data: { ...(n.data as object), memberCount: newCount } }
          }
          return n
        })

        emit('data-changed')
        savePositions(nodes.value)
      } catch (e: any) {
        showSnack(e?.message || 'Ошибка добавления в отдел', 'error')
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
  if (!source || !target || !source.startsWith('user-')) {
    showSnack('Связь тянуть только от сотрудника', 'warning')
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
      markerEnd: { type: 'arrowclosed', color: edgeColor },
      label: '×',
      labelStyle: { cursor: 'pointer', fill: '#f44336', fontWeight: 'bold', fontSize: '14px' },
      data: { relation_id: result.id, relation_type: type },
    }])
    const msg = type === 'user_user' ? 'Связь подчинённости создана'
      : type === 'user_dept' ? 'Назначен начальник отдела'
      : 'Назначен руководитель организации'
    showSnack(msg)
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

// ── Add member to dept ─────────────────────────────────────────────────────────

function openAddMemberDialog(deptId: number) {
  // Find users not already in this dept
  const deptMemberIds = new Set(
    nodes.value
      .filter(n => n.type === 'user' && n.parentNode === `dept-${deptId}`)
      .map(n => parseInt(n.id.replace('user-', '')))
  )
  const available = nodes.value
    .filter(n => n.type === 'user' && !deptMemberIds.has(parseInt(n.id.replace('user-', ''))))
    .map(n => ({ id: parseInt(n.id.replace('user-', '')), label: (n.data as any).label || n.id }))
    .sort((a, b) => a.label.localeCompare(b.label))

  addMemberDialog.value = { show: true, deptId, available }
  addMemberSelectedId.value = null
}

async function confirmAddMember() {
  const { deptId } = addMemberDialog.value
  const userId = addMemberSelectedId.value
  if (!deptId || !userId) return
  addMemberLoading.value = true
  try {
    await apiFetch(`/departments/${deptId}/members`, { method: 'POST', body: { user_id: userId } })
    showSnack('Сотрудник добавлен в отдел')
    addMemberDialog.value.show = false
    await loadGraph()
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка добавления', 'error')
  } finally {
    addMemberLoading.value = false
  }
}

// ── Create new org ─────────────────────────────────────────────────────────────

async function createNewOrg() {
  const name = newOrgDialog.value.name.trim()
  if (!name) return
  newOrgDialog.value.loading = true
  try {
    const body: any = { name }
    if (newOrgDialog.value.inn.trim()) body.inn = newOrgDialog.value.inn.trim()
    await apiFetch('/organizations/', { method: 'POST', body })
    showSnack(`Организация "${name}" создана`)
    newOrgDialog.value = { show: false, name: '', inn: '', loading: false }
    await loadGraph()
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка создания организации', 'error')
  } finally {
    newOrgDialog.value.loading = false
  }
}

// ── Delete dept ────────────────────────────────────────────────────────────────

const deleteDeptConfirm = ref<{ show: boolean; deptId: number | null; name: string }>({ show: false, deptId: null, name: '' })

function deleteDeptNode(deptId: number) {
  const n = nodes.value.find(n => n.id === `dept-${deptId}`)
  deleteDeptConfirm.value = { show: true, deptId, name: (n?.data as any)?.label || '' }
}

async function confirmDeleteDept() {
  const { deptId } = deleteDeptConfirm.value
  if (!deptId) return
  try {
    await apiFetch(`/departments/${deptId}`, { method: 'DELETE' })
    showSnack('Отдел удалён')
    deleteDeptConfirm.value.show = false
    await loadGraph()
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка удаления отдела', 'error')
  }
}

// ── Create new dept ────────────────────────────────────────────────────────────

async function createNewDept() {
  const name = newDeptDialog.value.name.trim()
  if (!name) return
  try {
    const body: any = { name }
    if (newDeptDialog.value.orgId) body.org_id = newDeptDialog.value.orgId
    await apiFetch('/departments/', { method: 'POST', body })
    showSnack(`Отдел "${name}" создан`)
    newDeptDialog.value = { show: false, name: '', orgId: newDeptDialog.value.orgId }
    await loadGraph()
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка создания отдела', 'error')
  }
}

onMounted(loadGraph)
defineExpose({ refresh: loadGraph })
</script>

<style>
.vue-flow__edge-text { cursor: pointer; }
/* Dept node container — style applied to wrapper by VueFlow via node.style */
.vue-flow__node-dept { padding: 0 !important; overflow: visible !important; }
.vue-flow__node-user { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; }
.vue-flow__node-org  { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; }

/* ── Dark mode overrides ── */
.v-theme--dark .hierarchy-toolbar { background: var(--crm-surface) !important; border-bottom-color: var(--crm-border) !important; }
.v-theme--dark .hierarchy-page.embedded { border-color: var(--crm-border-strong) !important; }

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
  border: 1px solid var(--crm-border-strong);
}
.hierarchy-toolbar {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  background: var(--crm-surface);
  border-bottom: 1px solid var(--crm-border);
  flex-shrink: 0;
  z-index: 10;
  gap: 4px;
  flex-wrap: wrap;
}
.hierarchy-canvas { flex: 1; min-height: 0; }
.hierarchy-loading { flex: 1; display: flex; align-items: center; justify-content: center; }

.legend-line { width: 24px; height: 3px; border-radius: 2px; }
.legend-green { background: #4caf50; }
.legend-orange { background: #ff9800; }
.legend-purple { background: #9c27b0; }
.legend-rect { width: 20px; height: 14px; border: 2px dashed #00897b; border-radius: 3px; background: rgba(0,105,92,0.07); }
.legend-dept {}

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
:deep(.hnode-org) { min-width: 200px; border-color: #1565c0; }
:deep(.hnode-header) { display: flex; align-items: center; gap: 8px; padding: 10px 14px; font-weight: 600; font-size: 13px; }
:deep(.hnode-header-org) { background: linear-gradient(135deg, #1565c0, #1e88e5); color: white; }
:deep(.hnode-icon) { font-size: 16px; }
:deep(.hnode-title) { flex: 1; white-space: normal; word-break: break-word; line-height: 1.3; overflow: visible; }

/* Dept header bar (inside the dashed container) */
:deep(.hnode-dept-header-bar) {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  padding: 8px 12px;
  background: linear-gradient(135deg, #00695c, #26a69a);
  color: white;
  font-weight: 600;
  font-size: 13px;
  border-radius: 8px 8px 0 0;
  min-height: 60px;
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
  margin-left: 4px;
  flex-shrink: 0;
  padding: 2px 4px;
  border-radius: 4px;
  opacity: 0.6;
  transition: background 0.15s, opacity 0.15s;
}
:deep(.hnode-dept-del-btn:hover) {
  background: rgba(244,67,54,0.25);
  opacity: 1;
}

/* User node */
:deep(.hnode-user) { min-width: 180px; width: 240px; border-color: #e0e0e0; }
:deep(.hnode-user-row) { display: flex; align-items: flex-start; gap: 10px; padding: 10px 14px; }
:deep(.hnode-avatar) {
  width: 34px; height: 34px; border-radius: 50%;
  background: linear-gradient(135deg, rgb(var(--v-theme-primary)), #1e88e5);
  color: white; display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: bold; flex-shrink: 0; margin-top: 2px;
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
