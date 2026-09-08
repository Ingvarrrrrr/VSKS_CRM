<template>
  <v-container fluid class="pa-6 staff-view">
    <!-- Header -->
    <div class="d-flex align-center mb-4 flex-wrap" style="gap:12px">
      <div>
        <h1 class="text-h5 font-weight-bold">Персонал</h1>
        <span class="text-body-2 text-medium-emphasis">Отделы, сотрудники и иерархия</span>
      </div>
      <v-spacer />
      <v-btn v-if="isAdmin" color="primary" size="small" variant="outlined" prepend-icon="mdi-domain-plus" @click="router.push({ path: '/organizations', query: { create: '1' } })">
        Добавить организацию
      </v-btn>
      <v-btn v-if="isAdmin" color="primary" size="small" variant="outlined" prepend-icon="mdi-folder-plus" @click="openCreateDeptFromHeader">
        Добавить отдел
      </v-btn>
      <v-btn v-if="isAdmin" color="primary" size="small" prepend-icon="mdi-account-plus" @click="openCreateUser()">
        Добавить сотрудника
      </v-btn>
    </div>

    <!-- Tabs -->
    <v-tabs v-model="activeTab" color="primary" class="mb-4">
      <v-tab value="departments">
        <v-icon icon="mdi-sitemap" class="mr-2" size="18" />Отделы
      </v-tab>
      <v-tab value="users">
        <v-icon icon="mdi-account-group" class="mr-2" size="18" />Сотрудники
      </v-tab>
      <v-tab value="hierarchy">
        <v-icon icon="mdi-family-tree" class="mr-2" size="18" />Иерархия
      </v-tab>
    </v-tabs>

    <v-window v-model="activeTab">
      <!-- TAB 1: Departments -->
      <v-window-item value="departments">
        <StaffDeptToolbar
          v-model:filter-dept-org-id="filterDeptOrgId"
          v-model:filter-subsidy-id="filterSubsidyId"
          v-model:filter-dept-user-id="filterDeptUserId"
          :organizations="organizations"
          :subsidies="subsidies"
          :users="users"
          :get-dept-export-columns="getDeptExportColumns"
          :get-dept-export-rows="getDeptExportRows"
          :get-capture-el="() => deptArea"
          @error="(msg) => showSnack(msg, 'error')"
          @download-template="downloadDeptTemplate"
          @open-import="deptImportDialog = true"
          @create-dept="openCreateDept"
        />

        <div ref="deptArea">
          <v-row>
            <v-col cols="12" md="7">
              <StaffDeptTree
                v-model:unassigned-expanded="unassignedExpanded"
                :dept-loading="deptLoading"
                :filtered-dept-tree="filteredDeptTree"
                :dept-tree-node="StaffDeptTreeNodeComp"
                :multi-org="organizations.length > 1"
                :unassigned-users="unassignedUsers"
                :is-admin="isAdmin"
                @reload="loadDeptTree"
                @select="selectDept"
                @edit="openEditDept"
                @delete="deleteDept"
                @add-member="onAddMemberInline"
                @edit-member="onEditMemberInline"
                @remove-member="onRemoveMemberInline"
                @edit-user="openEditUser"
                @delete-user="confirmDelete"
              />
            </v-col>
            <v-col cols="12" md="5">
              <StaffDeptDetails
                :selected-dept="selectedDept"
                :dept-members="deptMembers"
                :delegates="delegates"
                :get-member-avatar="getMemberAvatar"
                :get-member-photo-url="getMemberPhotoUrl"
                @add-member="onAddMemberInline"
                @edit-user-by-id="openEditUserById"
                @remove-member="removeMember"
                @open-delegate-dialog="delegateDialog = true"
                @remove-delegate="removeDelegate"
              />
            </v-col>
          </v-row>
        </div>
      </v-window-item>

      <!-- TAB 2: Users -->
      <v-window-item value="users">
        <StaffUsersToolbar
          v-model:filter-user-org-id="filterUserOrgId"
          v-model:filter-user-role="filterUserRole"
          v-model:filter-user-search="filterUserSearch"
          v-model:staff-view-mode="staffViewMode"
          :organizations="organizations"
          :role-items="roleItems"
          :is-admin="isAdmin"
          :staff-mobile="staffMobile"
          :get-export-columns="getUsersExportColumns"
          :get-export-rows="() => filteredUsers"
          :get-capture-el="() => registryArea"
          @error="(msg) => showSnack(msg, 'error')"
          @download-template="downloadUserTemplate"
          @open-import="userImportDialog.show = true"
          @open-columns="showColumnPicker = true"
        />

        <StaffUsersAlerts
          :is-admin="isAdmin"
          :selected-users="selectedUsers"
          :duplicate-inn-groups="duplicateInnGroups"
          @bulk-delete="confirmBulkDeleteUsers"
          @clear-selection="selectedUsers = []"
          @open-inn-dup="innDupDialog = true"
        />

        <div ref="registryArea">
          <StaffUsersTable
            v-if="staffEffectiveView === 'table'"
            v-model:expanded-users="expandedUsers"
            v-model:selected-users="selectedUsers"
            :visible-headers="visibleHeaders"
            :filtered-users="filteredUsers"
            :users-loading="usersLoading"
            :is-admin="isAdmin"
            :task-authority="taskAuthority"
            :task-authority-loading="taskAuthorityLoading"
            @user-expanded="onUserExpanded"
            @edit-user="openEditUser"
            @open-hierarchy="openHierarchyDialog"
            @delete-user="confirmDelete"
            @goto-hierarchy-tab="activeTab = 'hierarchy'"
          />
          <StaffUsersCards
            v-else
            v-model:cards-page="staffCardsPage"
            :filtered-users="filteredUsers"
            :paged-cards="staffPagedCards"
            :is-admin="isAdmin"
            :selected-users="selectedUsers"
            :cards-total-pages="staffCardsTotalPages"
            @edit-user="openEditUser"
            @toggle-selection="toggleUserSelection"
            @open-hierarchy="openHierarchyDialog"
            @delete-user="confirmDelete"
          />
        </div>
      </v-window-item>

      <!-- TAB 3: Hierarchy -->
      <v-window-item value="hierarchy">
        <div class="d-flex align-center mb-3">
          <v-spacer />
          <RegistryExportButton
            title="Иерархия"
            :get-columns="getHierarchyExportColumns"
            :get-rows="getHierarchyExportRows"
            :get-capture-el="() => hierarchyArea"
            @error="(msg) => showSnack(msg, 'error')"
          />
        </div>
        <div ref="hierarchyArea">
          <HierarchyView ref="hierarchyRef" :embedded="true" @edit-user="openEditUserById" @edit-dept="openEditDeptById" @create-user="openCreateUser" @data-changed="onHierarchyDataChanged" />
        </div>
      </v-window-item>
    </v-window>

    <!-- DIALOGS -->
    <StaffCreateUserDialog
      ref="createDialogRef"
      :dialog="createDialog"
      :role-items="roleItems"
      :can-pick-org="canPickOrg"
      :assignable-organizations="assignableOrganizations"
      :current-org-name="currentOrgName"
      :get-departments-for-org="getDepartmentsForOrg"
      :get-positions-for-org="getPositionsForOrg"
      :subsidies="subsidies"
      :mobile="mobile"
      @save="saveUser"
    />

    <StaffEditUserDialog
      :dialog="editDialog"
      :mobile="mobile"
      :can-change-password="canChangePassword"
      :role-items="roleItems"
      :user-dropdown-items="userDropdownItems"
      :organizations="organizations"
      :all-org-entries="allOrgEntries"
      :grouped-org-entries="groupedOrgEntries"
      :dedup-org-access="dedupOrgAccess"
      :set-org-hired-at="setOrgHiredAt"
      :depts-for-org="deptsForOrg"
      :org-css-color="orgCssColor"
      :get-positions-for-org="getPositionsForOrg"
      :current-user-id="currentUserId"
      @save="saveEditUser"
      @delete-org-entry="confirmDeleteOrgEntry"
      @add-dept-to-org="addDeptToOrg"
      @sync-to-contractor="syncToContractor"
      @error="(msg) => showSnack(msg, 'error')"
    />

    <StaffDeleteUserDialog :dialog="deleteDialog" @confirm="doDelete" />

    <StaffBulkDeleteUsersDialog v-model:show="bulkDeleteUsersDialog" :count="selectedUsers.length" :loading="bulkDeleteUsersLoading" @confirm="doBulkDeleteUsers" />

    <StaffHierarchyDialog :dialog="hierarchyDialog" :all-subs-not-direct="allSubsNotDirect" :mobile="mobile" @add-subordinate="addSubordinate" @remove-subordinate="removeSubordinate" />

    <StaffUserImportDialog :dialog="userImportDialog" :mobile="mobile" @download-template="downloadUserTemplate" @import="doUserImport" />

    <StaffDeptDialog
      v-model:show="deptDialog"
      :editing-dept="editingDept"
      :dept-form="deptForm"
      :subsidies="subsidies"
      :dept-member-items="deptMemberItems"
      :user-dropdown-items="userDropdownItems"
      :other-dept-items="otherDeptItems"
      :mobile="mobile"
      @save="saveDept"
    />

    <StaffAddMemberDialog
      v-model:show="addMemberDialog"
      v-model:add-member-mode="addMemberMode"
      :selected-dept="selectedDept"
      :member-form="memberForm"
      :new-member-form="newMemberForm"
      :user-dropdown-items="userDropdownItems"
      :role-items="roleItems"
      :get-positions-for-org="getPositionsForOrg"
      :new-member-saving="newMemberSaving"
      :mobile="mobile"
      @add="addMember"
      @create-and-add="createAndAddMember"
    />

    <StaffEditMemberDialog v-model:show="editMemberDialog" :edit-member-target="editMemberTarget" :edit-member-form="editMemberForm" @save="saveEditMember" />

    <StaffDelegateDialog v-model:show="delegateDialog" :delegate-form="delegateForm" :user-dropdown-items="userDropdownItems" @add="addDelegate" />

    <StaffDeptImportDialog v-model:show="deptImportDialog" v-model:dept-import-file="deptImportFile" :dept-import-result="deptImportResult" :dept-importing="deptImporting" @download-template="downloadDeptTemplate" @import="doDeptImport" />

    <StaffInnDupDialog v-model:show="innDupDialog" :duplicate-inn-groups="duplicateInnGroups" :mobile="mobile" @edit-user="openEditUser" />

    <ColumnConfigDialog
      v-model="showColumnPicker"
      :all-columns="allColumns"
      :state="colState"
      :show-width="true"
      :toggle-visible="toggleVisible"
      :set-position="setPosition"
      :set-width="setWidth"
      :reset="resetColumns"
    />
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import HierarchyView from './HierarchyView.vue'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'
import RegistryExportButton from '@/components/RegistryExportButton.vue'
import { useCardView } from '@/composables/useCardView'
import { useDisplay } from 'vuetify'
import { useToast, type ToastType } from '@/composables/useToast'

import StaffDeptToolbar from '@/components/staff/StaffDeptToolbar.vue'
import StaffDeptTree from '@/components/staff/StaffDeptTree.vue'
import StaffDeptDetails from '@/components/staff/StaffDeptDetails.vue'
import StaffDeptDialog from '@/components/staff/StaffDeptDialog.vue'
import StaffAddMemberDialog from '@/components/staff/StaffAddMemberDialog.vue'
import StaffEditMemberDialog from '@/components/staff/StaffEditMemberDialog.vue'
import StaffDelegateDialog from '@/components/staff/StaffDelegateDialog.vue'
import StaffDeptImportDialog from '@/components/staff/StaffDeptImportDialog.vue'
import StaffUsersToolbar from '@/components/staff/StaffUsersToolbar.vue'
import StaffUsersAlerts from '@/components/staff/StaffUsersAlerts.vue'
import StaffUsersTable from '@/components/staff/StaffUsersTable.vue'
import StaffUsersCards from '@/components/staff/StaffUsersCards.vue'
import StaffCreateUserDialog from '@/components/staff/StaffCreateUserDialog.vue'
import StaffEditUserDialog from '@/components/staff/StaffEditUserDialog.vue'
import StaffDeleteUserDialog from '@/components/staff/StaffDeleteUserDialog.vue'
import StaffBulkDeleteUsersDialog from '@/components/staff/StaffBulkDeleteUsersDialog.vue'
import StaffUserImportDialog from '@/components/staff/StaffUserImportDialog.vue'
import StaffInnDupDialog from '@/components/staff/StaffInnDupDialog.vue'
import StaffHierarchyDialog from '@/components/staff/StaffHierarchyDialog.vue'
import { createStaffDeptTreeNode } from '@/components/staff/StaffDeptTreeNode'

import { getRoleItems } from '@/composables/staff/staffLabels'
import { useStaffDicts } from '@/composables/staff/useStaffDicts'
import { useStaffOrganizations } from '@/composables/staff/useStaffOrganizations'
import { useStaffUsersList } from '@/composables/staff/useStaffUsersList'
import { useStaffDepartments, flatDepts } from '@/composables/staff/useStaffDepartments'
import { useStaffHierarchy } from '@/composables/staff/useStaffHierarchy'
import { useStaffCreateUser } from '@/composables/staff/useStaffCreateUser'
import { useStaffEditUser } from '@/composables/staff/useStaffEditUser'
import { useStaffDeleteUser } from '@/composables/staff/useStaffDeleteUser'
import { useStaffUserImport } from '@/composables/staff/useStaffUserImport'
import { useStaffMembers } from '@/composables/staff/useStaffMembers'
import { useStaffDeptImport } from '@/composables/staff/useStaffDeptImport'
import { useStaffExport } from '@/composables/staff/useStaffExport'
import type { UserItem } from '@/composables/staff/staffTypes'

// ── Route / Tab ──
const route = useRoute()
const router = useRouter()
const activeTab = ref((route.query.tab as string) || 'departments')
watch(activeTab, (val) => {
  router.replace({ query: { ...route.query, tab: val } })
})

// ── Auth ──
const currentRole = localStorage.getItem('user_role') || ''
const currentUserId = Number(localStorage.getItem('user_id') || 0)
const isAdmin = computed(() => ['admin', 'org_admin', 'account_owner', 'superadmin'].includes(currentRole))
const roleItems = computed(() => getRoleItems(currentRole))

// ── Snackbar ── единый механизм (useToast + ToastContainer, смонтирован в App.vue).
const toast = useToast()
const showSnack = (text: string, color: ToastType = 'success') => { toast.addToast(text, color) }

const { mobile } = useDisplay()
const subsidies = ref<any[]>([])

// ── Hierarchy refs (canvas + export capture) ──
const hierarchyRef = ref<InstanceType<typeof HierarchyView> | null>(null)
const registryArea = ref<HTMLElement | null>(null)
const deptArea = ref<HTMLElement | null>(null)
const hierarchyArea = ref<HTMLElement | null>(null)
function refreshHierarchy() { hierarchyRef.value?.refresh() }

// ── Справочники / организации ──
const { knownDepartments, dictsCache, loadDicts, getDepartmentsForOrg, getPositionsForOrg } = useStaffDicts()
const { organizations, assignableOrganizations, currentOrgId, currentOrgName, canPickOrg, loadOrganizations, orgColor, orgCssColor } = useStaffOrganizations(currentRole)

// ── Сотрудники (список/фильтры) ──
const {
  users, usersLoading, loadUsers, userDropdownItems,
  filterUserRole, filterUserOrgId, filterUserSearch, filteredUsers,
  duplicateInnGroups, unassignedUsers, unassignedExpanded,
  getMemberAvatar, getMemberPhotoUrl,
  expandedUsers, taskAuthority, taskAuthorityLoading, onUserExpanded,
} = useStaffUsersList(currentRole)

const { mobile: staffMobile, viewMode: staffViewMode, effectiveView: staffEffectiveView, page: staffCardsPage, totalPages: staffCardsTotalPages, paged: staffPagedCards } = useCardView<UserItem>({
  storageKey: 'staff_view_mode',
  source: () => filteredUsers.value,
  pageSize: 24,
})

const allColumns: ColumnDef[] = [
  { title: '', key: 'avatar', width: 50, sortable: false },
  { title: 'Email', key: 'email' },
  { title: 'ФИО', key: 'full_name' },
  { title: 'Роль', key: 'role', width: 130 },
  { title: 'Отдел', key: 'department' },
  { title: 'Должность', key: 'position' },
  { title: 'Город', key: 'city' },
  { title: 'Подпись', key: 'has_signature', width: 90, sortable: false },
  { title: '', key: 'actions', width: 100, sortable: false },
]
const { state: colState, visibleHeaders, toggleVisible, setPosition, setWidth, reset: resetColumns } = useColumnConfig('staff', allColumns)
const showColumnPicker = ref(false)
function getUsersExportColumns() {
  return visibleHeaders.value.filter((h: any) => !['actions', 'avatar', 'data-table-expand', 'data-table-select'].includes(h.key) && !!h.title).map((h: any) => ({ key: h.key, title: h.title, align: h.align }))
}

// ── Отделы ──
const {
  deptLoading, deptTree, filteredDeptTree, selectedDept, deptMembers, delegates,
  filterSubsidyId, filterDeptOrgId, filterDeptUserId,
  loadDeptTree, loadDeptMembers, loadDelegates,
  deptDialog, editingDept, deptForm, otherDeptItems, deptMemberItems,
  openCreateDept, openEditDept, openEditDeptById, saveDept, deleteDept, selectDept,
} = useStaffDepartments({ showSnack, dictsCache, knownDepartments, loadDicts, refreshHierarchy })

function openCreateDeptFromHeader() {
  activeTab.value = 'departments'
  openCreateDept()
}

const StaffDeptTreeNodeComp = createStaffDeptTreeNode(orgColor, orgCssColor)

// ── Иерархия ──
// treeLoading/hierarchyTree — состояние canvas-варианта иерархии, в этой
// вкладке не используется (мёртвое поле уже в оригинале StaffView.vue),
// не деструктурируем, чтобы не плодить TS6133 "unused".
const { hierarchyDialog, allSubsNotDirect, loadHierarchyTree, openHierarchyDialog, addSubordinate, removeSubordinate } = useStaffHierarchy({ users, showSnack })

async function onHierarchyDataChanged() {
  // Reload users silently so dept/position changes from hierarchy are reflected
  try {
    users.value = await apiFetch<UserItem[]>('/users/')
    await loadDeptTree()
  } catch { /* silent */ }
}

// ── Диалоги пользователей ──
const createDialogRef = ref<InstanceType<typeof StaffCreateUserDialog> | null>(null)
const { createDialog, openCreateUser, saveUser } = useStaffCreateUser({
  users, loadDicts, assignableOrganizations, currentOrgId, showSnack, loadDeptTree, refreshHierarchy,
  validateForm: () => createDialogRef.value?.validate?.(),
})

const {
  canChangePassword, editDialog, allOrgEntries, groupedOrgEntries,
  dedupOrgAccess, setOrgHiredAt, deptsForOrg, addDeptToOrg,
  syncToContractor, openEditUser, openEditUserById, confirmDeleteOrgEntry, saveEditUser,
} = useStaffEditUser({ users, organizations, deptTree, flatDepts, showSnack, loadDeptTree, loadHierarchyTree, refreshHierarchy, loadDicts })

const { deleteDialog, selectedUsers, bulkDeleteUsersDialog, bulkDeleteUsersLoading, confirmDelete, doDelete, confirmBulkDeleteUsers, toggleUserSelection, doBulkDeleteUsers } = useStaffDeleteUser({ users, currentOrgId, showSnack })

const { userImportDialog, downloadUserTemplate, doUserImport } = useStaffUserImport({ showSnack, loadUsers })

const innDupDialog = ref(false)

// ── Участники отделов / делегирование ──
const {
  addMemberDialog, addMemberMode, memberForm, newMemberForm, newMemberSaving,
  editMemberDialog, editMemberTarget, editMemberForm,
  delegateDialog, delegateForm,
  addMember, createAndAddMember, removeMember,
  onAddMemberInline, onEditMemberInline, onRemoveMemberInline, saveEditMember,
  addDelegate, removeDelegate,
} = useStaffMembers({ showSnack, selectedDept, loadDeptMembers, loadDeptTree, loadDelegates, loadUsers, openEditUserById })

const { deptImportDialog, deptImportFile, deptImporting, deptImportResult, downloadDeptTemplate, doDeptImport } = useStaffDeptImport({ showSnack, loadDeptTree })

const { getDeptExportColumns, getDeptExportRows, getHierarchyExportColumns, getHierarchyExportRows } = useStaffExport({ deptTree, users })

// ═══════════════════════════════════════════════════════════════
// LIFECYCLE
// ═══════════════════════════════════════════════════════════════
onMounted(async () => {
  loadUsers()
  loadDeptTree()
  loadHierarchyTree()
  try { subsidies.value = await apiFetch<any[]>('/subsidies/') } catch { subsidies.value = [] }
  await loadDicts()
  await loadOrganizations()
})
</script>

<!--
  Стили дерева отделов (.dept-tree-row и т.д., глобальные) переехали в
  components/staff/staffDeptTree.css (импортируется из StaffDeptTree.vue —
  их использует и StaffDeptTreeNode.ts, рендерящийся через h(), которому
  scoped CSS недоступен). Стили «Вне отделов» (unassigned-*) — scoped-блок
  в components/staff/StaffDeptTree.vue, т.к. scoped CSS не пересекает
  границу SFC. Аватарки/фото/скан ВУ — в StaffCreateUserDialog.vue и
  StaffEditUserDialog.vue, где теперь живёт их разметка.
-->

