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
      <v-text-field
        v-model="searchQuery"
        density="compact"
        variant="solo"
        rounded="pill"
        hide-details
        clearable
        prepend-inner-icon="mdi-magnify"
        placeholder="Найти сотрудника, отдел, организацию…"
        class="hv-search ml-3"
        style="min-width:300px;max-width:340px"
        @update:model-value="applySearch"
        @click:clear="applySearch"
      >
        <template #append-inner>
          <v-chip
            v-if="searchQuery"
            size="x-small"
            label
            :color="searchMatchCount ? 'success' : 'error'"
            variant="flat"
            class="font-weight-bold"
          >
            {{ searchMatchCount ? `${searchMatchCount} ✓` : '0' }}
          </v-chip>
        </template>
      </v-text-field>
      <v-btn size="small" variant="tonal" color="teal" prepend-icon="mdi-plus" @click="newDeptDialog.show = true" class="ml-2">
        Добавить отдел
      </v-btn>
      <v-btn size="small" variant="tonal" color="blue" prepend-icon="mdi-account-plus" @click="emit('create-user')" class="ml-2">
        Добавить сотрудника
      </v-btn>
      <v-btn v-if="isSuperadmin || isAccountOwner" size="small" variant="tonal" color="purple" prepend-icon="mdi-domain" @click="openNewOrgDialog" class="ml-2">
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
          <div class="legend-line" style="background:#1976d2" />
          <span class="text-caption">Подчинение отделов</span>
        </div>
        <div class="d-flex align-center ga-1">
          <div class="legend-line" style="background:#7b1fa2" />
          <span class="text-caption">Подчинение организаций</span>
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
    <HierarchyGraphCanvas
      v-else
      v-model:nodes="nodes"
      v-model:edges="edges"
      @connect="onConnect"
    />

    <HierarchyHelpDialog v-model="helpDialog" />

    <HierarchyOrgColorPickerDialog
      v-model="colorPickerVisible"
      :colors="ORG_COLORS_HV"
      @pick="onPickColor"
    />

    <HierarchyCopyUserDialog
      v-model="copyUserDialog.show"
      v-model:target-dept-id="copyTargetDeptId"
      :user-name="copyUserDialog.userName"
      :dept-options="copyDeptOptions"
      @confirm="confirmCopyUser"
    />

    <HierarchyUserInfoDialog
      v-model="userInfoDialog.show"
      :user-name="userInfoDialog.userName"
      :orgs="userInfoDialog.orgs"
      @edit="userInfoDialog.show = false; emit('edit-user', userInfoDialog.userId)"
      @save-org="saveUserOrgSalary"
    />

    <HierarchyEditOrgDialog
      v-model="editOrgDialog.show"
      v-model:contractor-pick-id="editOrgContractorId"
      :form="editOrgDialog"
      :contractors="editOrgContractors"
      :searching="contractorsStore.searching"
      :contractor-filter="orgContractorFilter"
      :egrul-loading="editOrgEgrulLoading"
      :egrul-message="editOrgEgrulMessage"
      :egrul-message-type="editOrgEgrulMessageType"
      @save="saveOrg"
      @enrich-egrul="enrichEditOrgFromEgrul"
      @clear-egrul-message="editOrgEgrulMessage = ''"
      @contractor-search="onEditOrgContractorSearch"
      @contractor-select="onEditOrgContractorSelect"
    />

    <!-- Edit contractor dialog (единая карточка контрагента — для организаций с contractor_id) -->
    <ContractorEditDialog
      v-model="contractorDialog.show"
      :contractor-id="contractorDialog.contractorId"
      @saved="onContractorSaved"
    />

    <HierarchyNewDeptDialog
      v-model="newDeptDialog.show"
      :form="newDeptDialog"
      :orgs="graphOrgs"
      @create="createNewDept"
    />

    <HierarchyAddMemberDialog
      v-model="addMemberDialog.show"
      v-model:selected-id="addMemberSelectedId"
      :available="addMemberDialog.available"
      :loading="addMemberLoading"
      @create-new="onCreateFromAddMember"
      @confirm="confirmAddMember"
    />

    <HierarchyDeleteDeptDialog
      v-model="deleteDeptConfirm.show"
      :name="deleteDeptConfirm.name"
      @confirm="confirmDeleteDept"
    />

    <HierarchyDeleteOrgDialog
      v-model="deleteOrgConfirm.show"
      v-model:force-ack="deleteOrgConfirm.forceAck"
      :name="deleteOrgConfirm.name"
      :loading="deleteOrgConfirm.loading"
      :loading-impact="deleteOrgConfirm.loadingImpact"
      :impact="deleteOrgConfirm.impact"
      @confirm="confirmDeleteOrg"
    />

    <HierarchyDeleteUserDialog
      v-model="deleteUserConfirm.show"
      :name="deleteUserConfirm.name"
      :loading="deleteUserConfirm.loading"
      :warning="deleteUserConfirm.warning"
      @confirm="confirmDeleteUser"
    />

    <HierarchyNewOrgDialog
      v-model="newOrgDialog.show"
      v-model:account-id="newOrgAccountId"
      v-model:contractor-id="newOrgContractorId"
      :form="newOrgDialog"
      :is-superadmin="isSuperadmin"
      :account-options="newOrgAccountOptions"
      :contractors="newOrgContractors"
      :searching="contractorsStore.searching"
      :contractor-filter="orgContractorFilter"
      :egrul-loading="newOrgEgrulLoading"
      :egrul-message="newOrgEgrulMessage"
      :egrul-message-type="newOrgEgrulMessageType"
      @create="createNewOrg"
      @enrich-egrul="enrichNewOrgFromEgrul"
      @clear-egrul-message="newOrgEgrulMessage = ''"
      @contractor-search="onNewOrgContractorSearch"
      @contractor-select="onNewOrgContractorSelect"
    />
  </div>
</template>

<script setup lang="ts">
// HierarchyView — оркестратор: собирает канвас графа (components/hierarchy/HierarchyGraphCanvas +
// composables/hierarchy/useHierarchyGraph, DnD/связи/авторасстановка) и диалоги (создание/редактирование/
// удаление организации, отдела, сотрудника) из composables/hierarchy/*. Вся бизнес-логика — в
// композаблах; здесь только их связывание и разметка.
import { onMounted, onUnmounted, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { useToast, type ToastType } from '@/composables/useToast'
import type { GraphData } from '@/composables/hierarchy/hierarchyTypes'
import { useOrgColors } from '@/composables/hierarchy/useOrgColors'
import { useHierarchySearch } from '@/composables/hierarchy/useHierarchySearch'
import { useHierarchyGraph } from '@/composables/hierarchy/useHierarchyGraph'
import { useHierarchyOrgDialogs } from '@/composables/hierarchy/useHierarchyOrgDialogs'
import { useHierarchyDeptDialogs } from '@/composables/hierarchy/useHierarchyDeptDialogs'
import { useHierarchyUserDialogs } from '@/composables/hierarchy/useHierarchyUserDialogs'
import HierarchyGraphCanvas from '@/components/hierarchy/HierarchyGraphCanvas.vue'
import HierarchyHelpDialog from '@/components/hierarchy/HierarchyHelpDialog.vue'
import HierarchyOrgColorPickerDialog from '@/components/hierarchy/HierarchyOrgColorPickerDialog.vue'
import HierarchyCopyUserDialog from '@/components/hierarchy/HierarchyCopyUserDialog.vue'
import HierarchyUserInfoDialog from '@/components/hierarchy/HierarchyUserInfoDialog.vue'
import HierarchyEditOrgDialog from '@/components/hierarchy/HierarchyEditOrgDialog.vue'
import HierarchyNewOrgDialog from '@/components/hierarchy/HierarchyNewOrgDialog.vue'
import HierarchyNewDeptDialog from '@/components/hierarchy/HierarchyNewDeptDialog.vue'
import HierarchyAddMemberDialog from '@/components/hierarchy/HierarchyAddMemberDialog.vue'
import HierarchyDeleteDeptDialog from '@/components/hierarchy/HierarchyDeleteDeptDialog.vue'
import HierarchyDeleteOrgDialog from '@/components/hierarchy/HierarchyDeleteOrgDialog.vue'
import HierarchyDeleteUserDialog from '@/components/hierarchy/HierarchyDeleteUserDialog.vue'
import ContractorEditDialog from '@/components/ContractorEditDialog.vue'

const props = withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })
const emit = defineEmits<{
  'edit-user': [id: number]
  'edit-dept': [id: number]
  // Владелец, 2026-09-01: «плюсик в отделе» обязан передать контекст (org_id +
  // название отдела), иначе форма создания сотрудника открывается пустой и
  // орг/отдел приходится проставлять руками. Опционален: кнопка в шапке (без
  // выбранного отдела) по-прежнему шлёт без контекста — там объективно нечего
  // передать (общий граф, ни одна орг/отдел не выбраны).
  'create-user': [ctx?: { orgId?: number; departmentName?: string }]
  'data-changed': []
}>()

useDisplay() // регистрирует брейкпоинты для дочерних диалогов (mobile fullscreen)
const toast = useToast()
const showSnack = (text: string, color: ToastType = 'success') => { toast.addToast(text, color) }

const isSuperadmin = localStorage.getItem('user_role') === 'superadmin'
const isAccountOwner = localStorage.getItem('user_role') === 'account_owner'

const helpDialog = ref(false)

// Общее состояние графа — источник для всех диалогов (имена отделов/орг, поиск пользователя и т.п.)
const lastGraphData = ref<GraphData | null>(null)

const { ORG_COLORS_HV, getOrgColor, pickOrgColor, colorPickerVisible, applyOrgColor } =
  useOrgColors(lastGraphData, showSnack)

const {
  contractorsStore,
  newOrgDialog, newOrgAccountId, newOrgAccountOptions, openNewOrgDialog,
  newOrgEgrulLoading, newOrgEgrulMessage, newOrgEgrulMessageType,
  newOrgContractors, newOrgContractorId, orgContractorFilter,
  onNewOrgContractorSearch, onNewOrgContractorSelect, createNewOrg, enrichNewOrgFromEgrul,
  editOrgDialog, editOrgContractors, editOrgContractorId,
  editOrgEgrulLoading, editOrgEgrulMessage, editOrgEgrulMessageType,
  onEditOrgContractorSearch, onEditOrgContractorSelect, saveOrg, enrichEditOrgFromEgrul,
  contractorDialog, onContractorSaved, openOrgDetail,
  deleteOrgConfirm, deleteOrgNode, confirmDeleteOrg,
} = useHierarchyOrgDialogs({
  lastGraphData, showSnack, isSuperadmin,
  loadGraph: () => loadGraph(),
})

const {
  newDeptDialog, setDefaultDeptOrgId, createNewDept,
  addMemberDialog, addMemberSelectedId, addMemberLoading,
  openAddMemberDialog, onCreateFromAddMember, confirmAddMember,
  deleteDeptConfirm, deleteDeptNode, confirmDeleteDept,
} = useHierarchyDeptDialogs({
  lastGraphData, showSnack,
  loadGraph: () => loadGraph(),
  onCreateUser: (ctx) => emit('create-user', ctx),
})

const {
  userInfoDialog, saveUserOrgSalary,
  copyUserDialog, copyTargetDeptId, copyDeptOptions, startCopyUser, confirmCopyUser,
  deleteUserConfirm, deleteUserNode, confirmDeleteUser,
} = useHierarchyUserDialogs({
  lastGraphData, showSnack,
  loadGraph: () => loadGraph(),
  onEditUser: (id) => emit('edit-user', id),
})

const {
  nodes, edges, loading, graphOrgs,
  loadGraph, rebuildGraph, autoLayout,
  getAvailableUsers, getDeptName, fitView, onConnect,
} = useHierarchyGraph(lastGraphData, {
  showSnack,
  getOrgColor,
  pickOrgColor,
  emitDataChanged: () => emit('data-changed'),
  onAddMember: (deptId) => openAddMemberDialog(deptId, getAvailableUsers(deptId)),
  onDeleteDept: (deptId) => deleteDeptNode(deptId, getDeptName(deptId)),
  onEditUser: (id) => emit('edit-user', id),
  onEditDept: (id) => emit('edit-dept', id),
  onOpenOrg: (org) => openOrgDetail(org),
  setDefaultDeptOrgId,
})

const { searchQuery, searchMatchCount, applySearch } = useHierarchySearch(nodes, fitView)

async function onPickColor(color: string) {
  await applyOrgColor(color, rebuildGraph)
}

// Слушатели пользовательских событий, которые рендер-функции узлов графа
// (HierarchyGraphCanvas) диспатчат через document.dispatchEvent — так узлы
// остаются decoupled от диалогов конкретной View.
const onHvPickColor = ((e: CustomEvent) => {
  pickOrgColor(e.detail)
}) as EventListener
const onHvCopyUser = ((e: CustomEvent) => {
  startCopyUser(e.detail)
}) as EventListener
// Phase 30 restore: delete org / delete user из иерархии
const onHvDeleteOrg = ((e: CustomEvent) => {
  deleteOrgNode(e.detail.id, e.detail.name)
}) as EventListener
const onHvDeleteUser = ((e: CustomEvent) => {
  deleteUserNode(e.detail.id, e.detail.name, e.detail.orgId ?? null)
}) as EventListener

onMounted(() => {
  document.addEventListener('hv-pick-color', onHvPickColor)
  document.addEventListener('hv-copy-user', onHvCopyUser)
  document.addEventListener('hv-delete-org', onHvDeleteOrg)
  document.addEventListener('hv-delete-user', onHvDeleteUser)
})

onUnmounted(() => {
  document.removeEventListener('hv-pick-color', onHvPickColor)
  document.removeEventListener('hv-copy-user', onHvCopyUser)
  document.removeEventListener('hv-delete-org', onHvDeleteOrg)
  document.removeEventListener('hv-delete-user', onHvDeleteUser)
})

onMounted(loadGraph)
defineExpose({ refresh: loadGraph })
</script>

<style>
/* ── Dark mode overrides ── */
.v-theme--dark .hierarchy-toolbar { background: var(--crm-surface) !important; border-bottom-color: var(--crm-border) !important; }
.v-theme--dark .hierarchy-page.embedded { border-color: var(--crm-border-strong) !important; }

/* ── Поиск: заметная строка ── */
.hv-search .v-field {
  background: #ffffff !important;
  border: 2px solid #fb923c !important;
  box-shadow: 0 2px 10px rgba(251,146,60,0.30) !important;
  transition: box-shadow .2s, border-color .2s;
}
.hv-search .v-field:hover { box-shadow: 0 2px 14px rgba(251,146,60,0.45) !important; }
.hv-search .v-field--focused {
  border-color: #ea7c1c !important;
  box-shadow: 0 0 0 4px rgba(251,146,60,0.25) !important;
}
.hv-search .v-field__prepend-inner .mdi { color: #ea7c1c !important; opacity: 1; }
/* Светлая тема — тёмный текст на белом */
.hv-search input { color: #1f2937 !important; }
.hv-search input::placeholder { color: #8a6d4f !important; opacity: 0.9; }

/* Тёмная тема — светлая подложка-поверхность и СВЕТЛЫЙ текст (не чёрный) */
.v-theme--dark .hv-search .v-field { background: var(--crm-surface) !important; }
.v-theme--dark .hv-search input { color: var(--crm-text, #e5e7eb) !important; }
.v-theme--dark .hv-search input::placeholder { color: #d8a87a !important; }
.v-theme--dark .hv-search .v-field__clearable .mdi { color: var(--crm-text, #e5e7eb) !important; }
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
.hierarchy-loading { flex: 1; display: flex; align-items: center; justify-content: center; }

.legend-line { width: 24px; height: 3px; border-radius: 2px; }
.legend-green { background: #4caf50; }
.legend-orange { background: #ff9800; }
.legend-purple { background: #9c27b0; }
.legend-rect { width: 20px; height: 14px; border: 2px dashed #00897b; border-radius: 3px; background: rgba(0,105,92,0.07); }
.legend-dept {}
</style>
