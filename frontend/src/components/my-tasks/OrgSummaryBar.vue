<template>
  <!-- Page header: title, tab toggles, view-mode toggles, action buttons -->
  <div class="d-flex align-center mb-4 flex-wrap" style="gap:12px">
    <div>
      <h1 class="text-h5 font-weight-bold">{{ pageTitle }}</h1>
      <span class="text-body-2 text-medium-emphasis">{{ TAB_SUBTITLES[activeTab] }}</span>
    </div>
    <v-spacer />

    <!-- Tab switcher: Purchases / Tasks / Report -->
    <v-btn-toggle
      :model-value="activeTab"
      mandatory
      density="compact"
      color="primary"
      class="mr-2"
      @update:model-value="$emit('update:activeTab', $event)"
    >
      <v-btn value="purchases" size="small">
        <v-icon icon="mdi-cart" class="mr-1" size="18"/>Закупки
      </v-btn>
      <v-btn value="general" size="small">
        <v-icon icon="mdi-clipboard-list" class="mr-1" size="18"/>Задачи
        <v-chip
          v-if="visibleActiveTasksCount"
          size="x-small"
          color="white"
          variant="flat"
          class="ml-1"
          style="color: #1565C0; font-weight: 700"
        >{{ visibleActiveTasksCount }}</v-chip>
        <v-chip v-if="pendingConsentTasks.length" size="x-small" color="orange" class="ml-1">
          +{{ pendingConsentTasks.length }}
        </v-chip>
      </v-btn>
      <v-btn value="report" size="small">
        <v-icon icon="mdi-chart-bar" class="mr-1" size="18"/>Отчёт
      </v-btn>
    </v-btn-toggle>

    <!-- View mode toggle (purchases tab) -->
    <v-btn-toggle
      v-if="activeTab === 'purchases'"
      :model-value="viewMode"
      mandatory
      density="compact"
      color="primary"
      @update:model-value="$emit('update:viewMode', $event)"
    >
      <v-btn value="kanban" size="small">
        <v-icon icon="mdi-view-column" class="mr-1" size="18"/>Канбан
      </v-btn>
      <v-btn value="list" size="small">
        <v-icon icon="mdi-format-list-bulleted" class="mr-1" size="18"/>Список
      </v-btn>
    </v-btn-toggle>

    <!-- View mode toggle (tasks tab) -->
    <v-btn-toggle
      v-if="activeTab === 'general'"
      :model-value="taskViewMode"
      mandatory
      density="compact"
      color="primary"
      class="mr-2"
      @update:model-value="$emit('update:taskViewMode', $event)"
    >
      <v-btn value="kanban" size="small">
        <v-icon icon="mdi-view-column" class="mr-1" size="18"/>Канбан
      </v-btn>
      <v-btn value="list" size="small">
        <v-icon icon="mdi-format-list-bulleted" class="mr-1" size="18"/>Список
      </v-btn>
    </v-btn-toggle>

    <!-- Action: new task (tasks tab) -->
    <v-btn
      v-if="activeTab === 'general'"
      color="primary"
      size="small"
      prepend-icon="mdi-plus"
      @click="$emit('new-task')"
    >
      Новая задача
    </v-btn>

    <!-- Action: toggle archive (purchases tab) -->
    <v-btn
      v-if="activeTab === 'purchases'"
      :variant="showArchive ? 'flat' : 'outlined'"
      color="grey"
      size="small"
      prepend-icon="mdi-archive"
      @click="$emit('update:showArchive', !showArchive)"
    >Архив</v-btn>

    <!-- Action: refresh -->
    <v-btn
      variant="tonal"
      color="primary"
      size="small"
      prepend-icon="mdi-refresh"
      :loading="loading"
      @click="$emit('refresh')"
    >
      Обновить
    </v-btn>
  </div>

  <!-- ═══ PENDING CONSENT — always visible ═══ -->
  <v-expand-transition>
    <div v-if="pendingConsentTasks.length" class="mb-4">
      <div class="d-flex align-center mb-2 ga-2">
        <v-icon icon="mdi-bell-ring" color="orange" size="20" />
        <span class="text-subtitle-2 font-weight-bold">Требуется ваше согласие на задачи</span>
        <v-chip color="orange" size="small" variant="tonal">{{ pendingConsentTasks.length }}</v-chip>
      </div>
      <v-row dense>
        <v-col v-for="pt in pendingConsentTasks" :key="pt.id" cols="12" sm="6" md="4">
          <v-card variant="outlined" class="pa-3 h-100" style="border-color:rgba(245,158,11,0.6);border-width:2px">
            <div class="d-flex align-start mb-1 ga-1">
              <v-icon icon="mdi-clipboard-arrow-right-outline" color="orange" size="18" class="mt-0.5 flex-shrink-0" />
              <span class="text-body-2 font-weight-medium">{{ pt.title }}</span>
            </div>
            <div class="text-caption text-medium-emphasis mb-3">
              <span>Поставил: <b>{{ pt.created_by_name || '—' }}</b></span>
              <span v-if="pt.due_date" class="ml-2">· 📅 {{ pt.due_date.split('T')[0] }}</span>
              <span v-if="pt.priority" class="ml-2">· {{ PRIORITY_LABELS[pt.priority] || pt.priority }}</span>
            </div>
            <div class="d-flex ga-2">
              <v-btn size="small" color="success" variant="flat" rounded
                :loading="consentLoading === String(pt.id) + '_accept'"
                prepend-icon="mdi-check-circle"
                @click="$emit('respond-consent', { taskId: pt.id, accept: true })">
                Принять
              </v-btn>
              <v-btn size="small" color="error" variant="tonal" rounded
                :loading="consentLoading === String(pt.id) + '_decline'"
                prepend-icon="mdi-close-circle"
                @click="$emit('respond-consent', { taskId: pt.id, accept: false })">
                Отклонить
              </v-btn>
            </div>
          </v-card>
        </v-col>
      </v-row>
    </div>
  </v-expand-transition>

  <!-- ═══ ACCEPTANCE NOTIFICATIONS — for task creators ═══ -->
  <v-expand-transition>
    <div v-if="acceptNotifs.length" class="mb-4">
      <div class="d-flex align-center mb-2 ga-2">
        <v-icon icon="mdi-check-circle" color="success" size="20" />
        <span class="text-subtitle-2 font-weight-bold">Задачи приняты</span>
        <v-chip color="success" size="small" variant="tonal">{{ acceptNotifs.length }}</v-chip>
      </div>
      <v-row dense>
        <v-col v-for="d in acceptNotifs" :key="d.id" cols="12" sm="6" md="4">
          <v-card variant="tonal" color="success" class="pa-3 h-100">
            <div class="d-flex align-start mb-1 ga-1">
              <v-icon icon="mdi-check-circle-outline" color="success" size="18" class="flex-shrink-0 mt-0.5" />
              <span class="text-body-2 font-weight-medium">{{ d.task_title }}</span>
            </div>
            <div class="text-caption mb-3 text-medium-emphasis">
              <b>{{ d.declined_by_name }}</b> принял задачу
              <span v-if="d.created_at" class="ml-1">· {{ d.created_at.split('T')[0] }}</span>
            </div>
            <v-btn size="small" color="success" variant="flat" rounded
              :loading="ackLoading === d.id"
              prepend-icon="mdi-check"
              @click="$emit('acknowledge-decline', d.id)">
              Понял
            </v-btn>
          </v-card>
        </v-col>
      </v-row>
    </div>
  </v-expand-transition>

  <!-- ═══ DECLINE NOTIFICATIONS — for task creators ═══ -->
  <v-expand-transition>
    <div v-if="declineNotifs.length" class="mb-4">
      <div class="d-flex align-center mb-2 ga-2">
        <v-icon icon="mdi-account-cancel" color="error" size="20" />
        <span class="text-subtitle-2 font-weight-bold">Ваши назначения отклонены</span>
        <v-chip color="error" size="small" variant="tonal">{{ declineNotifs.length }}</v-chip>
      </div>
      <v-row dense>
        <v-col v-for="d in declineNotifs" :key="d.id" cols="12" sm="6" md="4">
          <v-card variant="tonal" color="error" class="pa-3 h-100">
            <div class="d-flex align-start mb-1 ga-1">
              <v-icon icon="mdi-close-circle-outline" color="error" size="18" class="flex-shrink-0 mt-0.5" />
              <span class="text-body-2 font-weight-medium">{{ d.task_title }}</span>
            </div>
            <div class="text-caption mb-3 text-medium-emphasis">
              <b>{{ d.declined_by_name }}</b> отклонил назначение
              <span v-if="d.created_at" class="ml-1">· {{ d.created_at.split('T')[0] }}</span>
            </div>
            <v-btn size="small" color="error" variant="flat" rounded
              :loading="ackLoading === d.id"
              prepend-icon="mdi-check"
              @click="$emit('acknowledge-decline', d.id)">
              Понял
            </v-btn>
          </v-card>
        </v-col>
      </v-row>
    </div>
  </v-expand-transition>
</template>

<script setup lang="ts">
/**
 * OrgSummaryBar — page-level header bar + consent/notification banners for MyTasksView (D-18).
 * Pure presentation: renders page title, tab toggles, view-mode toggles, action buttons,
 * and consent/acceptance/decline notification blocks.
 * All state is owned by the parent (MyTasksView). Children emit events back.
 */

export interface ConsentTask {
  id: number
  title: string
  created_by_name: string | null
  due_date: string | null
  priority: string | null
}

export interface ConsentDeclineNotif {
  id: number
  task_title: string
  declined_by_name: string
  created_at: string | null
}

interface Props {
  /** Current active tab */
  activeTab: 'purchases' | 'general' | 'report'
  /** Purchase view mode (kanban / list) */
  viewMode: 'kanban' | 'list'
  /** Task view mode (kanban / list) */
  taskViewMode: 'kanban' | 'list'
  /** Whether the purchases archive is being shown */
  showArchive: boolean
  /** Global loading state (shows spinner on refresh button) */
  loading: boolean
  /** Count of visible active tasks (shown as chip inside Tasks tab button) */
  visibleActiveTasksCount: number
  /** Computed page title (e.g. "Мои задачи — Название орг") */
  pageTitle: string
  /** Tasks awaiting user consent (rendered as orange banner) */
  pendingConsentTasks: ConsentTask[]
  /** Acceptance notifications (task creators: "N принял задачу") */
  acceptNotifs: ConsentDeclineNotif[]
  /** Decline notifications (task creators: "N отклонил назначение") */
  declineNotifs: ConsentDeclineNotif[]
  /** Loading state for consent accept/decline buttons — "taskId_accept" | "taskId_decline" | null */
  consentLoading: string | null
  /** Loading state for acknowledge-decline buttons — notif id | null */
  ackLoading: number | null
}

defineProps<Props>()

defineEmits<{
  /** Tab changed by user */
  (e: 'update:activeTab', value: 'purchases' | 'general' | 'report'): void
  /** Purchase view-mode changed (kanban / list) */
  (e: 'update:viewMode', value: 'kanban' | 'list'): void
  /** Task view-mode changed (kanban / list) */
  (e: 'update:taskViewMode', value: 'kanban' | 'list'): void
  /** Archive toggle changed */
  (e: 'update:showArchive', value: boolean): void
  /** User clicked "Новая задача" */
  (e: 'new-task'): void
  /** User clicked "Обновить" */
  (e: 'refresh'): void
  /** User clicked accept/decline on a consent task */
  (e: 'respond-consent', payload: { taskId: number; accept: boolean }): void
  /** User acknowledged a consent-decline or acceptance notification */
  (e: 'acknowledge-decline', notifId: number): void
}>()

const TAB_SUBTITLES: Record<string, string> = {
  purchases: 'Канбан-доска по закупкам',
  general: 'Общие задачи',
  report: 'Отчёт по отделам',
}

const PRIORITY_LABELS: Record<string, string> = {
  low: 'Низкий',
  medium: 'Средний',
  high: 'Высокий',
  urgent: 'Срочно',
}
</script>
