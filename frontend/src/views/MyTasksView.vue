<template>
  <v-container fluid class="pa-4">
    <!-- Header + consent/notification banners -->
    <OrgSummaryBar
      v-model:active-tab="activeTab"
      v-model:view-mode="viewMode"
      v-model:task-view-mode="taskViewMode"
      v-model:show-archive="showArchive"
      :loading="loading"
      :visible-active-tasks-count="visibleActiveTasksCount"
      :page-title="pageTitle"
      :pending-consent-tasks="pendingConsentTasks"
      :accept-notifs="acceptNotifs"
      :decline-notifs="declineNotifs"
      :consent-loading="consentLoading"
      :ack-loading="ackLoading"
      @new-task="openNewTask"
      @refresh="load"
      @respond-consent="({ taskId, accept }) => respondConsent(taskId, accept)"
      @acknowledge-decline="acknowledgeDecline"
    />

    <!-- Organization cards -->
    <OrgSelector
      :org-summary="orgSummary"
      :selected-org-id="selectedOrgId"
      :org-cards-open="orgCardsOpen"
      @select-org="selectOrg"
      @update:org-cards-open="orgCardsOpen = $event"
      @click-stat="handleOrgStatClick"
    />

    <div v-show="!orgCardsOpen || orgSummary.length <= 1">

      <!-- ═══ PURCHASES TAB ═══ -->
      <template v-if="activeTab === 'purchases'">
        <!-- Pending approvals -->
        <v-card v-if="pendingApprovals.length" variant="outlined" class="mb-4" style="border-color:#059669">
          <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-3 d-flex align-center ga-2">
            <v-icon icon="mdi-check-decagram" color="green-darken-2" size="20" />
            Ожидают моего согласования
            <v-chip color="orange" size="small" variant="tonal">{{ pendingApprovals.length }}</v-chip>
          </v-card-title>
          <v-list density="compact">
            <v-list-item v-for="pa in pendingApprovals" :key="pa.approval.id"
              :to="`/orders/${pa.approval.purchase_id}/edit`"
              prepend-icon="mdi-file-sign">
              <v-list-item-title>
                Закупка #{{ pa.purchase.purchase_number }} — {{ pa.purchase.subject || pa.purchase.item_name || 'Без названия' }}
              </v-list-item-title>
              <v-list-item-subtitle>
                {{ pa.approval.role_name }}: {{ pa.approval.approver_full_name }}
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </v-card>

        <!-- Loading -->
        <div v-if="loading && tasks.length === 0" class="d-flex justify-center py-12">
          <v-progress-circular indeterminate color="primary" size="48" />
        </div>

        <!-- Empty state -->
        <div v-else-if="!loading && tasks.length === 0 && !showArchive" class="text-center py-12">
          <v-icon icon="mdi-clipboard-check-outline" size="64" color="grey-lighten-2" />
          <div class="text-h6 text-medium-emphasis mt-4">Нет назначенных задач</div>
          <div class="text-body-2 text-medium-emphasis mt-1">Попросите администратора назначить вам закупки</div>
        </div>

        <!-- Kanban View -->
        <PurchasesKanban
          v-if="!loading && (tasks.length > 0 || showArchive) && viewMode === 'kanban'"
          :purchases="tasks"
          :archive-purchases="archiveTasks"
          :selected-org-id="selectedOrgId"
          :show-archive="showArchive"
          @open-purchase="openTask"
          @update-kanban-status="handleUpdateKanbanStatus"
        />

        <!-- List View -->
        <PurchasesTable
          v-if="!loading && (tasks.length > 0 || showArchive) && viewMode === 'list'"
          :purchases="filteredTasks"
          :selected-org-id="selectedOrgId"
          :loading="loading"
          @open-purchase="openTask"
        />
      </template>

      <!-- ═══ GENERAL TASKS TAB ═══ -->
      <template v-if="activeTab === 'general'">
        <!-- Link purchase banner -->
        <v-alert v-if="linkPurchaseId" type="info" variant="tonal" closable class="mb-3"
          @click:close="linkPurchaseId = null; $router.replace({ query: {} })">
          <div class="d-flex align-center ga-2">
            <v-icon>mdi-link-variant</v-icon>
            <span>Выберите задачу для привязки к закупке <b>#{{ linkPurchaseId }}</b></span>
            <v-btn size="small" variant="text" @click="linkPurchaseId = null; $router.replace({ query: {} })">Отмена</v-btn>
          </div>
        </v-alert>

        <div v-if="loading && generalTasks.length === 0" class="d-flex justify-center py-12">
          <v-progress-circular indeterminate color="primary" size="48" />
        </div>
        <div v-else-if="generalTasks.length === 0" class="text-center py-12">
          <v-icon icon="mdi-clipboard-plus-outline" size="64" color="grey-lighten-2" />
          <div class="text-h6 text-medium-emphasis mt-4">Нет задач</div>
          <div class="text-body-2 text-medium-emphasis mt-1">Создайте первую задачу</div>
          <v-btn color="primary" class="mt-4" prepend-icon="mdi-plus" @click="openNewTask">Новая задача</v-btn>
        </div>

        <!-- LIST VIEW -->
        <TasksTable
          v-else-if="taskViewMode === 'list'"
          :tasks="filteredGeneralTasks"
          :current-user-id="currentUserId"
          :link-purchase-id="linkPurchaseId"
          @open-task="editGeneralTask"
          @link-purchase="doLinkPurchase"
          @navigate-purchase="(id) => router.push(`/orders/${id}/edit`)"
          @confirm-done="confirmTaskDone"
          @reject-done="rejectTaskDone"
        />

        <!-- KANBAN VIEW -->
        <TasksKanban
          v-else
          :tasks="filteredGeneralTasks"
          :current-user-id="currentUserId"
          :link-purchase-id="linkPurchaseId"
          @open-task="editGeneralTask"
          @update-status="handleUpdateTaskStatus"
          @link-purchase="doLinkPurchase"
          @navigate-purchase="(id) => router.push(`/orders/${id}/edit`)"
          @confirm-done="confirmTaskDone"
          @reject-done="rejectTaskDone"
        />
      </template>

      <!-- ═══ REPORT TAB ═══ -->
      <template v-if="activeTab === 'report'">
        <TasksReport :departments="departments" />
      </template>

    </div><!-- end v-show org content -->

    <!-- Task Edit Dialog -->
    <TaskEditDialog
      v-model:show="showTaskDialog"
      :editing-task="editingTask"
      :task-form="taskForm"
      :org-summary="orgSummary"
      :current-user-id="currentUserId"
      :user-items="userItems"
      :subordinate-ids="subordinateIds"
      :managed-org-user-ids="managedOrgUserIds"
      :task-categories="taskCategories"
      @task-saved="onTaskSaved"
      @task-deleted="onTaskDeleted"
      @subtask-added="onSubtaskAdded"
    />

    <!-- Purchase comment dialog -->
    <v-dialog v-model="commentDialog" max-width="500" :fullscreen="mobile">
      <v-card>
        <v-card-title>Комментарий к задаче</v-card-title>
        <v-card-text>
          <v-textarea v-model="commentText" label="Комментарий" rows="3" variant="outlined" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="commentDialog = false">Отмена</v-btn>
          <v-btn color="primary" @click="saveComment">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'

const { mobile } = useDisplay()
import { useAuthStore } from '@/stores/auth'
import OrgSelector from '@/components/my-tasks/OrgSelector.vue'
import OrgSummaryBar from '@/components/my-tasks/OrgSummaryBar.vue'
import TasksTable from '@/components/my-tasks/TasksTable.vue'
import TasksKanban from '@/components/my-tasks/TasksKanban.vue'
import PurchasesTable from '@/components/my-tasks/PurchasesTable.vue'
import PurchasesKanban from '@/components/my-tasks/PurchasesKanban.vue'
import TaskEditDialog from '@/components/my-tasks/TaskEditDialog.vue'
import TasksReport from '@/components/my-tasks/TasksReport.vue'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const selectedOrgId = ref<number | null>(null)
const orgCardsOpen = ref<boolean>(true)
const orgSummary = ref<{org_id: number | null, org_name: string, task_count: number, purchase_count: number, unseen_count: number}[]>([])
const currentUserId = parseInt(localStorage.getItem('user_id') || '0')
const currentUserRole = localStorage.getItem('user_role') || 'employee'
const viewMode = ref<'kanban' | 'list'>('kanban')
const taskViewMode = ref<'kanban' | 'list'>('kanban')
const showArchive = ref(false)
const linkPurchaseId = ref<number | null>(null)

// ── Purchases state ──
const tasks = ref<any[]>([])
const archiveTasks = ref<any[]>([])
const pendingApprovals = ref<any[]>([])
const filteredTasks = computed(() => [...tasks.value, ...(showArchive.value ? archiveTasks.value : [])])

const activeTab = ref<'purchases' | 'general' | 'report'>('general')
const commentDialog = ref(false)
const commentText = ref('')
const commentTaskId = ref<number | null>(null)

// ── General tasks ──
const generalTasks = ref<any[]>([])
const filteredGeneralTasks = computed(() =>
  selectedOrgId.value === null ? generalTasks.value : generalTasks.value.filter((t: any) => t.org_id === selectedOrgId.value)
)
const visibleActiveTasksCount = computed(() =>
  filteredGeneralTasks.value.filter((t: any) => !['done', 'cancelled'].includes(t.status)).length
)
const pageTitle = computed(() => {
  const BASE = { general: 'Мои задачи', purchases: 'Мои закупки', report: 'Мои задачи и закупки' }
  const base = BASE[activeTab.value] ?? 'Мои задачи'
  const org = selectedOrgId.value !== null ? orgSummary.value.find(o => o.org_id === selectedOrgId.value) : null
  return org ? `${base} — ${org.org_name}` : base
})

// ── Consent ──
const pendingConsentTasks = ref<any[]>([])
const consentLoading = ref<string | null>(null)
const consentDeclines = ref<any[]>([])
const declineNotifs = computed(() => consentDeclines.value.filter((d: any) => !d.is_accepted))
const acceptNotifs = computed(() => consentDeclines.value.filter((d: any) => d.is_accepted))
const ackLoading = ref<number | null>(null)

// ── Task dialog ──
const showTaskDialog = ref(false)
const editingTask = ref<any>(null)
const taskCategories = ref<string[]>([])
const userItems = ref<{text:string, value:number}[]>([])
const subordinateIds = ref<Set<number>>(new Set())
const managedOrgUserIds = ref<Set<number>>(new Set())
const taskForm = ref({ title: '', description: '', priority: 'medium', due_date: '', assignee_ids: [] as number[], category: '', org_id: null as number | null })
const departments = ref<string[]>([])

// ── Task dialog handlers ──
function openNewTask() {
  editingTask.value = null
  taskForm.value = { title: '', description: '', priority: 'medium', due_date: '', assignee_ids: [], category: '', org_id: selectedOrgId.value }
  showTaskDialog.value = true
}

function editGeneralTask(t: any) {
  editingTask.value = t
  taskForm.value = {
    title: t.title, description: t.description || '', priority: t.priority,
    due_date: t.due_date ? t.due_date.split('T')[0] : '',
    assignee_ids: (t.assignees || []).map((a: any) => a.user_id),
    category: t.category || '',
    org_id: t.org_id ?? null,
  }
  showTaskDialog.value = true
}

function onTaskSaved(task: any, isNew: boolean) {
  if (isNew) {
    generalTasks.value.push(task)
  } else {
    const idx = generalTasks.value.findIndex(t => t.id === task.id)
    if (idx >= 0) generalTasks.value[idx] = { ...generalTasks.value[idx], ...task }
  }
}

function onTaskDeleted(taskId: number) {
  generalTasks.value = generalTasks.value.filter(t => t.id !== taskId)
}

function onSubtaskAdded(task: any, parentId: number) {
  generalTasks.value.push(task)
  const parentCard = generalTasks.value.find(t => t.id === parentId)
  if (parentCard) parentCard.subtask_count = (parentCard.subtask_count || 0) + 1
}

async function doLinkPurchase(taskId: number) {
  if (!linkPurchaseId.value) return
  try {
    await apiFetch(`/tasks/${taskId}`, {
      method: 'PATCH', body: JSON.stringify({ purchase_id: linkPurchaseId.value }),
    })
    const pid = linkPurchaseId.value
    linkPurchaseId.value = null
    router.replace({ path: `/orders/${pid}/edit` })
  } catch (e: any) {
    alert(e?.detail || 'Ошибка привязки')
  }
}

async function handleUpdateTaskStatus(taskId: number, newStatus: string) {
  const t = generalTasks.value.find((task: any) => task.id === taskId)
  if (!t) return
  const oldStatus = t.status
  try {
    await apiFetch(`/tasks/${taskId}`, { method: 'PATCH', body: JSON.stringify({ status: newStatus }) })
  } catch {
    t.status = oldStatus
  }
}

async function confirmTaskDone(taskId: number) {
  await apiFetch(`/tasks/${taskId}/review-complete`, { method: 'POST', body: JSON.stringify({ confirm: true }) })
  const t = generalTasks.value.find(task => task.id === taskId)
  if (t) t.status = 'done'
}

async function rejectTaskDone(taskId: number) {
  await apiFetch(`/tasks/${taskId}/review-complete`, { method: 'POST', body: JSON.stringify({ confirm: false }) })
  const t = generalTasks.value.find(t => t.id === taskId)
  if (t) t.status = 'in_progress'
}

// ── Purchases handlers ──
async function handleUpdateKanbanStatus(purchaseId: number, newStatus: string) {
  const task = [...tasks.value, ...archiveTasks.value].find(t => t.id === purchaseId)
  if (!task) return
  const oldStatus = task.status
  task.status = newStatus
  if (newStatus === 'paid') {
    tasks.value = tasks.value.filter(t => t.id !== purchaseId)
    archiveTasks.value.unshift(task)
  } else if (oldStatus === 'paid') {
    archiveTasks.value = archiveTasks.value.filter(t => t.id !== purchaseId)
    tasks.value.push(task)
  }
  try {
    await apiFetch(`/purchases/${purchaseId}/kanban-status?status=${newStatus}`, { method: 'PATCH' })
  } catch {
    task.status = oldStatus
    if (newStatus === 'paid') {
      archiveTasks.value = archiveTasks.value.filter(t => t.id !== purchaseId)
      tasks.value.push(task)
    } else if (oldStatus === 'paid') {
      tasks.value = tasks.value.filter(t => t.id !== purchaseId)
      archiveTasks.value.unshift(task)
    }
  }
}

function openTask(id: number) { router.push(`/orders/${id}/edit`) }

async function saveComment() {
  if (commentTaskId.value === null) return
  await apiFetch(`/purchases/${commentTaskId.value}/comment?comment=${encodeURIComponent(commentText.value)}`, { method: 'PATCH' })
  const task = [...tasks.value, ...archiveTasks.value].find(t => t.id === commentTaskId.value)
  if (task) task.task_comment = commentText.value
  commentDialog.value = false
}

// ── Consent ──
async function acknowledgeDecline(declineId: number) {
  ackLoading.value = declineId
  try {
    await apiFetch(`/tasks/consent-declines/${declineId}/acknowledge`, { method: 'POST' })
    consentDeclines.value = consentDeclines.value.filter(d => d.id !== declineId)
  } catch { /* silent */ } finally {
    ackLoading.value = null
  }
}

async function respondConsent(taskId: number, accept: boolean) {
  const key = `${taskId}_${accept ? 'accept' : 'decline'}`
  consentLoading.value = key
  try {
    await apiFetch(`/tasks/${taskId}/consent?accept=${accept}`, { method: 'POST' })
    pendingConsentTasks.value = pendingConsentTasks.value.filter(t => t.id !== taskId)
    if (accept) generalTasks.value = await apiFetch<any[]>('/tasks/my')
  } catch (e: any) {
    alert(e?.detail || 'Ошибка')
  } finally {
    consentLoading.value = null
  }
}

// ── Data loading ──
async function loadOrgSummary() {
  try {
    orgSummary.value = await apiFetch<any[]>('/tasks/org-summary')
  } catch (e) {
    console.error('Failed to load org summary:', e)
    orgSummary.value = []
  }
}

async function selectOrg(orgId: number | null) {
  selectedOrgId.value = orgId
  orgCardsOpen.value = false
  generalTasks.value = []
  tasks.value = []
  archiveTasks.value = []
  if (orgId !== null) localStorage.setItem('active_org_id', String(orgId))
  else localStorage.removeItem('active_org_id')
  // Phase 30 fix: при смене активной организации обновить permissions →
  // sidebar (AppBar) подхватит новые tabs/actions для этой org
  try {
    const authStore = useAuthStore()
    await authStore.loadPermissions(orgId)
  } catch (e) {
    console.warn('loadPermissions on org switch failed', e)
  }
  await loadOrgData()
}

async function handleOrgStatClick({ orgId, tab }: { orgId: number | null; tab: 'general' | 'purchases' }) {
  activeTab.value = tab
  await selectOrg(orgId)
}

async function loadOrgData() {
  loading.value = true
  try {
    const orgId = selectedOrgId.value
    if (currentUserRole === 'employee' && orgId === null) {
      await load()
    } else {
      const taskUrl = orgId !== null ? `/tasks/?org_id=${orgId}` : '/tasks/'
      const purchaseUrl = orgId !== null ? `/purchases/?org_id=${orgId}` : '/purchases/'
      const [allTasks, allPurchases] = await Promise.all([
        apiFetch<any[]>(taskUrl).catch(() => []),
        apiFetch<any[]>(purchaseUrl).catch(() => []),
      ])
      generalTasks.value = allTasks
      tasks.value = allPurchases.filter((t: any) => t.status !== 'paid')
      archiveTasks.value = allPurchases.filter((t: any) => t.status === 'paid')
    }
  } catch (e) { console.error('Load org data error:', e) }
  finally { loading.value = false }
}

async function load() {
  loading.value = true
  try {
    await Promise.all([
      apiFetch<any>('/tasks/init').then(data => {
        generalTasks.value = data.my_tasks || []
        pendingConsentTasks.value = data.pending_consent || []
        consentDeclines.value = data.consent_declines || []
        taskCategories.value = data.categories || []
        departments.value = data.departments || []
      }).catch(() => { generalTasks.value = [] }),
      apiFetch<any[]>('/purchases/my-tasks')
        .then(active => { tasks.value = active.filter(t => t.status !== 'paid') })
        .catch(e => console.error('Load purchases error:', e)),
      apiFetch<any[]>('/purchases/my-tasks?include_archive=true')
        .then(archived => { archiveTasks.value = archived.filter(t => t.status === 'paid') })
        .catch(() => {}),
      apiFetch<any[]>('/approvals/my-pending')
        .then(r => { pendingApprovals.value = r })
        .catch(() => { pendingApprovals.value = [] }),
    ])
  } catch (e) { console.error('Load error:', e) }
  finally { loading.value = false }
  // Load users lazily after paint
  apiFetch<any[]>('/users/in-my-orgs').then(users => {
    userItems.value = users.map(u => ({ text: u.full_name || u.username, value: u.id }))
  }).catch(() => {})
  apiFetch<any[]>(`/users/${currentUserId}/subordinates`).then(subs => {
    subordinateIds.value = new Set((subs as any[]).map((u: any) => u.id))
  }).catch(() => {})
  apiFetch<any>(`/hierarchy/graph`).then((graph: any) => {
    const ids = new Set<number>()
    const myManagedOrgIds = new Set((graph.user_org_edges || []).filter((e: any) => e.manager_user_id === currentUserId).map((e: any) => e.org_id))
    for (const u of (graph.users || [])) {
      if (myManagedOrgIds.has(u.org_id)) ids.add(u.id)
    }
    const myManagedDeptIds = new Set((graph.user_dept_edges || []).filter((e: any) => e.manager_user_id === currentUserId).map((e: any) => e.dept_id))
    for (const dept of (graph.departments || [])) {
      if (myManagedDeptIds.has(dept.id)) {
        for (const uid of (dept.member_ids || [])) ids.add(uid)
      }
    }
    managedOrgUserIds.value = ids
  }).catch(() => {})
}

// ── Real-time polling ──
async function pollTasks() {
  try {
    const [myTasks, pending, declines] = await Promise.all([
      apiFetch<any[]>('/tasks/my'),
      apiFetch<any[]>('/tasks/pending-consent').catch(() => [] as any[]),
      apiFetch<any[]>('/tasks/consent-declines').catch(() => [] as any[]),
    ])
    generalTasks.value = myTasks
    pendingConsentTasks.value = pending
    consentDeclines.value = declines
  } catch { /* silent */ }
}

let _pollInterval: ReturnType<typeof setInterval> | null = null
onMounted(async () => {
  await loadOrgSummary()
  if (currentUserRole === 'employee') {
    await load()
  } else {
    await loadOrgData()
  }
  _pollInterval = setInterval(pollTasks, 30_000)

  if (route.query.link_purchase) {
    linkPurchaseId.value = Number(route.query.link_purchase)
    activeTab.value = 'general'
    taskViewMode.value = 'list'
  }

  const taskIdParam = route.query.task
  if (taskIdParam) {
    const taskId = Number(taskIdParam)
    if (taskId) {
      activeTab.value = 'general'
      await nextTick()
      let found = generalTasks.value.find((t: any) => t.id === taskId)
      if (!found) {
        try { found = await apiFetch<any>(`/tasks/${taskId}`) } catch {}
      }
      if (found) editGeneralTask(found)
      router.replace({ query: {} })
    }
  }
})
onUnmounted(() => {
  if (_pollInterval) clearInterval(_pollInterval)
})
</script>

<style scoped>
/* All layout CSS lives in child component scoped styles */
</style>
