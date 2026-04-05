<template>
  <v-container fluid class="pa-4">
    <!-- Header -->
    <div class="d-flex align-center mb-4 flex-wrap" style="gap:12px">
      <div>
        <h1 class="text-h5 font-weight-bold">Мои задачи и закупки</h1>
        <span class="text-body-2 text-medium-emphasis">{{ TAB_SUBTITLES[activeTab] }}</span>
      </div>
      <v-spacer />
      <v-btn-toggle v-model="activeTab" mandatory density="compact" color="primary" class="mr-2">
        <v-btn value="purchases" size="small"><v-icon icon="mdi-cart" class="mr-1" size="18"/>Закупки</v-btn>
        <v-btn value="general" size="small">
          <v-icon icon="mdi-clipboard-list" class="mr-1" size="18"/>Задачи
          <v-chip v-if="generalTasks.length" size="x-small" color="primary" class="ml-1">{{ generalTasks.length }}</v-chip>
          <v-chip v-if="pendingConsentTasks.length" size="x-small" color="orange" class="ml-1">+{{ pendingConsentTasks.length }}</v-chip>
        </v-btn>
        <v-btn value="report" size="small"><v-icon icon="mdi-chart-bar" class="mr-1" size="18"/>Отчёт</v-btn>
      </v-btn-toggle>
      <v-btn-toggle v-if="activeTab === 'purchases'" v-model="viewMode" mandatory density="compact" color="primary">
        <v-btn value="kanban" size="small"><v-icon icon="mdi-view-column" class="mr-1" size="18"/>Канбан</v-btn>
        <v-btn value="list" size="small"><v-icon icon="mdi-format-list-bulleted" class="mr-1" size="18"/>Список</v-btn>
      </v-btn-toggle>
      <v-btn-toggle v-if="activeTab === 'general'" v-model="taskViewMode" mandatory density="compact" color="primary" class="mr-2">
        <v-btn value="kanban" size="small"><v-icon icon="mdi-view-column" class="mr-1" size="18"/>Канбан</v-btn>
        <v-btn value="list" size="small"><v-icon icon="mdi-format-list-bulleted" class="mr-1" size="18"/>Список</v-btn>
      </v-btn-toggle>
      <v-btn v-if="activeTab === 'general'" color="primary" size="small" prepend-icon="mdi-plus" @click="openNewTask">
        Новая задача
      </v-btn>
      <v-btn
        v-if="activeTab === 'purchases'"
        :variant="showArchive ? 'flat' : 'outlined'" color="grey"
        size="small" prepend-icon="mdi-archive" @click="showArchive = !showArchive"
      >Архив</v-btn>
      <v-btn variant="tonal" color="primary" size="small" prepend-icon="mdi-refresh" :loading="loading" @click="load">
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
                <span v-if="pt.priority" class="ml-2">· {{ {low:'Низкий',medium:'Средний',high:'Высокий',urgent:'Срочно'}[pt.priority] || pt.priority }}</span>
              </div>
              <div class="d-flex ga-2">
                <v-btn size="small" color="success" variant="flat" rounded
                  :loading="consentLoading === String(pt.id) + '_accept'"
                  prepend-icon="mdi-check-circle"
                  @click="respondConsent(pt.id, true)">
                  Принять
                </v-btn>
                <v-btn size="small" color="error" variant="tonal" rounded
                  :loading="consentLoading === String(pt.id) + '_decline'"
                  prepend-icon="mdi-close-circle"
                  @click="respondConsent(pt.id, false)">
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
                @click="acknowledgeDecline(d.id)">
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
                @click="acknowledgeDecline(d.id)">
                Понял
              </v-btn>
            </v-card>
          </v-col>
        </v-row>
      </div>
    </v-expand-transition>

    <!-- Organization cards -->
    <div v-if="selectedOrgId === null && orgSummary.length > 1" class="mb-6">
      <div class="text-subtitle-1 font-weight-medium mb-3">Выберите организацию</div>
      <div class="org-cards-grid">
        <div
          v-for="org in orgSummary"
          :key="org.org_id ?? 'all'"
          class="org-sel-card"
          :class="{ 'org-sel-card--all': org.org_id === null }"
          @click="selectOrg(org.org_id)"
        >
          <div class="osc-icon-box">
            <v-icon :icon="org.org_id === null ? 'mdi-domain-plus' : 'mdi-domain'" size="22" />
          </div>
          <div class="osc-body">
            <div class="osc-name">{{ org.org_name }}</div>
            <div class="osc-stats">
              <span><v-icon size="12" class="mr-1">mdi-clipboard-check</v-icon>{{ org.task_count }} <span class="osc-stat-label">задач</span></span>
              <span><v-icon size="12" class="mr-1">mdi-cart</v-icon>{{ org.purchase_count }} <span class="osc-stat-label">закупок</span></span>
            </div>
          </div>
          <div v-if="org.unseen_count > 0" class="osc-badge">{{ org.unseen_count }}</div>
        </div>
      </div>
    </div>

    <!-- Back to org selection -->
    <v-btn v-if="orgSummary.length > 1 && selectedOrgId !== null" variant="text" size="small" color="primary"
      prepend-icon="mdi-arrow-left" class="mb-3" @click="selectedOrgId = null">
      К выбору организации
    </v-btn>

    <div v-show="selectedOrgId !== null || orgSummary.length <= 1">

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
    <div v-else-if="viewMode === 'kanban'" class="kanban-board">
      <div
        v-for="col in visibleColumns" :key="col.status"
        class="kanban-column"
        @dragover.prevent
        @drop="onDrop($event, col.status)"
      >
        <div class="kanban-column-header" :style="{ borderTopColor: col.color }">
          <span class="kanban-column-title">{{ col.label }}</span>
          <v-chip size="x-small" :color="col.color" variant="tonal">{{ tasksByStatus(col.status).length }}</v-chip>
        </div>
        <div class="kanban-column-body">
          <div
            v-for="task in tasksByStatus(col.status)" :key="task.id"
            class="kanban-card"
            draggable="true"
            @dragstart="onDragStart($event, task)"
            @click="openTask(task.id)"
          >
            <div class="kanban-card-header">
              <span class="kanban-card-title">{{ task.subject || `Закупка #${task.purchase_number || task.id}` }}</span>
            </div>
            <div v-if="task.contractor_name" class="kanban-card-meta">
              <v-icon icon="mdi-domain" size="12" class="mr-1" />{{ task.contractor_name }}
            </div>
            <div v-if="task.substatus" class="kanban-card-meta">
              <v-chip size="x-small" variant="outlined" color="teal">
                {{ SUBSTATUS_LABEL[task.substatus] || task.substatus }}
              </v-chip>
            </div>
            <div class="kanban-card-footer">
              <span class="kanban-card-amount">{{ formatMoney(task.contract_price || task.planned_total_price) }}</span>
              <v-chip
                v-if="task.execution_term"
                :color="deadlineColor(task.execution_term)" size="x-small" variant="tonal"
              >{{ formatDate(task.execution_term) }}</v-chip>
              <v-icon v-if="task.is_monthly_payment" size="14" color="blue" title="Ежемесячный платёж" class="ml-1">mdi-calendar-sync</v-icon>
            </div>
            <!-- Missing fields indicators -->
            <div v-if="!task.contractor_name || !task.execution_term || !(task.contract_price || task.planned_total_price)" class="d-flex flex-wrap ga-1 mt-1">
              <v-chip v-if="!task.contractor_name" size="x-small" color="error" variant="tonal" prepend-icon="mdi-domain-off" title="Не выбран контрагент">Контрагент</v-chip>
              <v-chip v-if="!task.execution_term" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-calendar-alert" title="Не указан срок исполнения">Срок</v-chip>
              <v-chip v-if="!(task.contract_price || task.planned_total_price)" size="x-small" color="warning" variant="tonal" prepend-icon="mdi-currency-rub" title="Не указана сумма">Сумма</v-chip>
            </div>
            <!-- Unseen changes -->
            <div v-if="task.unseen_changes_count" class="d-flex align-center mt-1">
              <v-chip size="x-small" variant="flat" color="warning" :title="`${task.unseen_changes_count} новых изменений`">
                <v-icon icon="mdi-bell-ring" size="10" class="mr-1" />{{ task.unseen_changes_count }}
              </v-chip>
            </div>
            <div v-if="task.delivery_date && task.status === 'contracted'" class="kanban-card-meta">
              <v-icon icon="mdi-truck-delivery" size="12" class="mr-1" />Доставка: {{ formatDate(task.delivery_date) }}
            </div>
            <div v-if="task.task_comment" class="kanban-card-comment">
              <v-icon icon="mdi-comment-text-outline" size="12" class="mr-1" />
              <span>{{ task.task_comment.length > 100 ? task.task_comment.slice(0, 100) + '…' : task.task_comment }}</span>
            </div>
          </div>
          <div v-if="tasksByStatus(col.status).length === 0" class="kanban-empty">
            Нет задач
          </div>
        </div>
      </div>
    </div>

    <!-- List View -->
    <v-card v-else variant="outlined">
      <v-table density="compact" hover>
        <thead>
          <tr>
            <th>Статус</th>
            <th>Название</th>
            <th>Контрагент</th>
            <th class="text-right">Сумма</th>
            <th>Срок</th>
            <th>Комментарий</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="task in filteredTasks" :key="task.id" style="cursor:pointer" @click="openTask(task.id)">
            <td>
              <div class="d-flex align-center ga-1 flex-wrap">
                <v-chip :color="statusColor(task.status)" size="x-small" variant="flat">
                  {{ purchaseStatusLabel(task) }}
                </v-chip>
                <v-chip v-if="task.substatus" size="x-small" variant="outlined" color="teal">
                  {{ SUBSTATUS_LABEL[task.substatus] || task.substatus }}
                </v-chip>
              </div>
            </td>
            <td class="font-weight-medium">{{ task.subject || `Закупка #${task.purchase_number || task.id}` }}</td>
            <td class="text-body-2">{{ task.contractor_name || '—' }}</td>
            <td class="text-right text-body-2">{{ formatMoney(task.contract_price || task.planned_total_price) }}</td>
            <td>
              <v-chip v-if="task.execution_term" :color="deadlineColor(task.execution_term)" size="x-small" variant="tonal">
                {{ formatDate(task.execution_term) }}
              </v-chip>
              <span v-else class="text-medium-emphasis">—</span>
            </td>
            <td class="text-body-2 text-truncate" style="max-width:200px">{{ task.task_comment || '' }}</td>
          </tr>
          <tr v-if="filteredTasks.length === 0">
            <td colspan="6" class="text-center text-medium-emphasis pa-4">Нет задач</td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

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
      <v-card v-else-if="taskViewMode === 'list'" variant="outlined">
        <v-data-table
          :headers="taskListHeaders"
          :items="generalTasks"
          density="compact"
          hover
          items-per-page="25"
          :items-per-page-options="[25,50,100]"
          @click:row="(_e: any, { item }: any) => linkPurchaseId ? doLinkPurchase(item.id) : editGeneralTask(item)"
        >
          <template #item.task_number="{ item }">
            <span class="text-caption font-weight-medium">{{ item.task_number || '—' }}</span>
          </template>
          <template #item.priority="{ item }">
            <v-chip :color="PRIORITY_COLOR[item.priority]||'grey'" size="x-small" variant="flat">{{ PRIORITY_LABEL[item.priority] }}</v-chip>
          </template>
          <template #item.status="{ item }">
            <v-chip :color="item.status==='done'?'success':item.status==='in_progress'?'primary':item.status==='review'?'purple':'warning'" size="x-small" variant="tonal">
              {{ {todo:'К выполнению',in_progress:'В работе',review:'На проверке',done:'Готово',cancelled:'Отменена'}[item.status]||item.status }}
            </v-chip>
          </template>
          <template #item.assignees="{ item }">
            <span class="text-caption">{{ item.assignees?.map((a:any) => a.user_name?.split(' ')[0]).join(', ') || '—' }}</span>
          </template>
          <template #item.due_date="{ item }">
            <v-chip v-if="item.due_date" :color="deadlineColor(item.due_date)" size="x-small" variant="tonal">{{ formatDate(item.due_date.split('T')[0]) }}</v-chip>
            <span v-else class="text-caption text-medium-emphasis">—</span>
          </template>
          <template #item.purchase_subject="{ item }">
            <v-chip v-if="item.purchase_id" size="x-small" variant="tonal" color="deep-purple"
              @click.stop="$router.push(`/orders/${item.purchase_id}/edit`)">
              {{ item.purchase_subject || `#${item.purchase_number || item.purchase_id}` }}
            </v-chip>
          </template>
          <template #item.actions="{ item }">
            <v-btn v-if="linkPurchaseId" size="x-small" variant="tonal" color="deep-purple"
              prepend-icon="mdi-link-variant" @click.stop="doLinkPurchase(item.id)">Привязать</v-btn>
            <template v-else-if="item.status === 'review' && item.created_by_id === currentUserId">
              <v-btn size="x-small" color="success" variant="tonal" prepend-icon="mdi-check" class="mr-1" @click.stop="confirmTaskDone(item.id)">Подтвердить</v-btn>
              <v-btn size="x-small" color="warning" variant="tonal" prepend-icon="mdi-undo" @click.stop="rejectTaskDone(item.id)">Вернуть</v-btn>
            </template>
            <v-btn v-else icon="mdi-pencil" variant="text" size="small" @click.stop="editGeneralTask(item)" />
          </template>
        </v-data-table>
      </v-card>

      <!-- KANBAN VIEW -->
      <div v-else class="kanban-board">
        <div v-for="col in GT_COLUMNS" :key="col.status" class="kanban-column" @dragover.prevent @drop="onDropGeneral($event, col.status)">
          <div class="kanban-column-header" :style="{ borderTopColor: col.color }">
            <span class="kanban-column-title">{{ col.label }}</span>
            <v-chip size="x-small" :color="col.color" variant="tonal">{{ generalByStatus(col.status).length }}</v-chip>
          </div>
          <div class="kanban-column-body">
            <div
              v-for="gt in generalByStatus(col.status)" :key="gt.id"
              class="kanban-card"
              :style="gtCardStyle(gt)"
              draggable="true"
              @dragstart="onDragStartGeneral($event, gt)"
              @click="linkPurchaseId ? doLinkPurchase(gt.id) : editGeneralTask(gt)"
            >
              <div class="d-flex align-center ga-1 mb-1">
                <v-chip :color="PRIORITY_COLOR[gt.priority] || 'grey'" size="x-small" variant="flat">{{ PRIORITY_LABEL[gt.priority] || gt.priority }}</v-chip>
                <v-chip v-if="gt.category" size="x-small" variant="outlined">{{ gt.category }}</v-chip>
                <v-chip v-if="gt.parent_task_id" size="x-small" variant="tonal" color="indigo" title="Подзадача">
                  <v-icon icon="mdi-subdirectory-arrow-right" size="10" class="mr-1" />Подзадача
                </v-chip>
                <v-spacer />
                <v-chip v-if="gt.unseen_changes_count" size="x-small" variant="flat" color="warning" :title="`${gt.unseen_changes_count} новых изменений`">
                  <v-icon icon="mdi-bell-ring" size="10" class="mr-1" />{{ gt.unseen_changes_count }}
                </v-chip>
                <v-chip v-if="gt.subtask_count" size="x-small" variant="tonal" color="teal" :title="`${gt.subtask_count} делегировано`">
                  <v-icon icon="mdi-sitemap-outline" size="10" class="mr-1" />{{ gt.subtask_count }}
                </v-chip>
                <v-chip v-if="gt.comment_count" size="x-small" variant="tonal" color="blue-grey">
                  <v-icon icon="mdi-comment-text-outline" size="10" class="mr-1" />{{ gt.comment_count }}
                </v-chip>
              </div>
              <!-- Linked purchase -->
              <div v-if="gt.purchase_id" class="mb-1">
                <v-chip size="x-small" variant="tonal" color="deep-purple" prepend-icon="mdi-cart-outline"
                  @click.stop="$router.push(`/orders/${gt.purchase_id}/edit`)">
                  {{ gt.purchase_subject || `Закупка #${gt.purchase_number || gt.purchase_id}` }}
                </v-chip>
              </div>
              <div class="kanban-card-title"><span v-if="gt.task_number" class="text-caption text-medium-emphasis mr-1">#{{ gt.task_number }}</span>{{ gt.title }}</div>
              <div v-if="gt.description" class="kanban-card-meta" style="font-size:11px;opacity:.7">{{ gt.description.length > 80 ? gt.description.slice(0,80)+'…' : gt.description }}</div>
              <!-- Last comment preview -->
              <div v-if="gt.last_comment" class="kanban-card-comment">
                <v-icon icon="mdi-comment-text-outline" size="12" class="mr-1" />
                <span><strong>{{ gt.last_comment_user }}:</strong> {{ gt.last_comment }}</span>
              </div>
              <div class="kanban-card-footer mt-1">
                <span v-if="gt.assignees?.length" class="kanban-card-meta">
                  <v-icon icon="mdi-account-multiple" size="12" class="mr-1"/>
                  {{ gt.assignees.map((a: any) => a.user_name?.split(' ')[0] || '?').join(', ') }}
                </span>
                <v-chip v-if="gt.due_date" :color="deadlineColor(gt.due_date)" size="x-small" variant="tonal">{{ formatDate(gt.due_date.split('T')[0]) }}</v-chip>
              </div>
              <!-- Review confirmation buttons for task creator -->
              <div v-if="gt.status === 'review' && gt.created_by_id === currentUserId" class="d-flex ga-1 mt-2" @click.stop>
                <v-btn size="x-small" color="success" variant="tonal" prepend-icon="mdi-check" @click.stop="confirmTaskDone(gt.id)">Подтвердить</v-btn>
                <v-btn size="x-small" color="warning" variant="tonal" prepend-icon="mdi-undo" @click.stop="rejectTaskDone(gt.id)">Вернуть</v-btn>
              </div>
            </div>
            <div v-if="generalByStatus(col.status).length === 0" class="kanban-empty">Нет задач</div>
          </div>
        </div>
      </div>
    </template>

    <!-- ═══ REPORT TAB ═══ -->
    <template v-if="activeTab === 'report'">
      <div class="d-flex align-center mb-4 ga-3 flex-wrap">
        <v-select
          v-model="reportDept"
          :items="departments"
          label="Отдел"
          variant="outlined" density="compact" clearable
          style="max-width:280px"
          placeholder="Все отделы"
        />
        <v-select
          v-model="reportWeeks"
          :items="[{title:'1 неделя',value:1},{title:'2 недели',value:2},{title:'4 недели',value:4},{title:'12 недель',value:12}]"
          label="Период"
          variant="outlined" density="compact"
          style="max-width:200px"
        />
        <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-magnify" :loading="reportLoading" @click="loadReport">Сформировать</v-btn>
      </div>

      <div v-if="reportLoading" class="d-flex justify-center py-12">
        <v-progress-circular indeterminate color="primary" size="48" />
      </div>

      <template v-else-if="reportData">
        <!-- Summary KPIs -->
        <div class="d-flex ga-3 mb-4 flex-wrap">
          <v-card variant="outlined" class="pa-4 text-center" style="min-width:150px;flex:1">
            <div class="text-h4 font-weight-bold text-success">{{ reportData.summary.total_done }}</div>
            <div class="text-caption text-medium-emphasis">Выполнено</div>
          </v-card>
          <v-card variant="outlined" class="pa-4 text-center" style="min-width:150px;flex:1">
            <div class="text-h4 font-weight-bold text-primary">{{ reportData.summary.total_in_progress }}</div>
            <div class="text-caption text-medium-emphasis">В работе</div>
          </v-card>
          <v-card variant="outlined" class="pa-4 text-center" style="min-width:150px;flex:1">
            <div class="text-h4 font-weight-bold text-warning">{{ reportData.summary.total_todo }}</div>
            <div class="text-caption text-medium-emphasis">Планируется</div>
          </v-card>
          <v-card variant="outlined" class="pa-4 text-center" style="min-width:150px;flex:1">
            <div class="text-h4 font-weight-bold text-error">{{ reportData.summary.total_overdue }}</div>
            <div class="text-caption text-medium-emphasis">Просрочено</div>
          </v-card>
        </div>

        <!-- Per-department breakdown -->
        <v-card v-for="dept in reportData.departments" :key="dept.department" variant="outlined" class="mb-4">
          <v-card-title class="d-flex align-center ga-2 px-4 pt-3 pb-1">
            <v-icon icon="mdi-account-group" size="20" />
            {{ dept.department }}
            <v-spacer />
            <v-chip color="success" size="small" variant="tonal">{{ dept.done_count }} выполнено</v-chip>
            <v-chip color="primary" size="small" variant="tonal">{{ dept.in_progress_count }} в работе</v-chip>
            <v-chip color="warning" size="small" variant="tonal">{{ dept.todo_count }} план</v-chip>
            <v-chip v-if="dept.overdue_count" color="error" size="small" variant="tonal">{{ dept.overdue_count }} просрочено</v-chip>
          </v-card-title>

          <v-card-text class="pa-2">
            <div class="d-flex ga-3" style="overflow-x:auto">
              <!-- Mini kanban per department -->
              <div v-for="sec in [{key:'in_progress',label:'В работе',color:'#3B82F6'},{key:'todo',label:'Планируется',color:'#F59E0B'},{key:'done',label:'Выполнено',color:'#22C55E'}]" :key="sec.key" style="min-width:200px;flex:1">
                <div class="text-caption font-weight-medium mb-1" :style="{color:sec.color}">{{ sec.label }} ({{ dept[sec.key].length }})</div>
                <div v-for="t in dept[sec.key].slice(0,5)" :key="t.id" class="report-task-item">
                  <div class="d-flex align-center ga-1">
                    <v-chip :color="PRIORITY_COLOR[t.priority]||'grey'" size="x-small" variant="flat" style="min-width:0">{{ PRIORITY_LABEL[t.priority]?.[0] || '?' }}</v-chip>
                    <span class="text-body-2 font-weight-medium text-truncate" style="max-width:160px">{{ t.title }}</span>
                  </div>
                  <div class="d-flex align-center ga-1 mt-1">
                    <span v-if="t.assigned_user" class="text-caption text-medium-emphasis"><v-icon icon="mdi-account" size="10"/>{{ t.assigned_user }}</span>
                    <v-chip v-if="t.due_date" :color="deadlineColor(t.due_date)" size="x-small" variant="tonal">{{ formatDate(t.due_date.split('T')[0]) }}</v-chip>
                  </div>
                </div>
                <div v-if="dept[sec.key].length > 5" class="text-caption text-medium-emphasis mt-1">+ ещё {{ dept[sec.key].length - 5 }}</div>
                <div v-if="dept[sec.key].length === 0" class="text-caption text-medium-emphasis" style="opacity:.5">—</div>
              </div>
            </div>
          </v-card-text>
        </v-card>

        <div v-if="reportData.departments.length === 0" class="text-center py-8 text-medium-emphasis">
          Нет данных. Убедитесь, что сотрудники привязаны к отделам.
        </div>
      </template>
    </template>

    </div><!-- end v-show org content -->

    <!-- General Task Dialog (create/edit) -->
    <v-dialog v-model="showTaskDialog" max-width="680">
      <v-card>
        <v-card-title class="d-flex align-center justify-space-between">
          <span>{{ editingTask ? 'Задача' : 'Новая задача' }}</span>
          <div class="d-flex ga-1 align-center">
            <v-chip v-if="editingTask && editingTask.created_by_name" size="small" variant="tonal" color="indigo" prepend-icon="mdi-account-arrow-right">
              Поставил: {{ editingTask.created_by_name }}
            </v-chip>
            <v-chip v-if="editingTask && isTaskReadonly" size="small" variant="tonal" color="warning" prepend-icon="mdi-lock-outline">
              Только статус
            </v-chip>
          </div>
        </v-card-title>
        <v-card-text>
          <div :class="isFieldUnseen('title') ? 'field-changed mb-2' : 'mb-2'" @click="dismissField('title')">
            <v-text-field v-model="taskForm.title" label="Название *" variant="outlined" density="compact" :readonly="isTaskReadonly" :bg-color="isTaskReadonly ? 'grey-lighten-4' : undefined" />
          </div>
          <div :class="isFieldUnseen('description') ? 'field-changed mb-2' : 'mb-2'" @click="dismissField('description')">
            <v-textarea v-model="taskForm.description" label="Описание" variant="outlined" density="compact" rows="2" :readonly="isTaskReadonly" :bg-color="isTaskReadonly ? 'grey-lighten-4' : undefined" />
          </div>
          <div class="d-flex ga-2 mb-2">
            <div :class="isFieldUnseen('priority') ? 'field-changed' : ''" style="max-width:200px;flex:0 0 auto" @click="dismissField('priority')">
              <v-select v-model="taskForm.priority" :items="priorityItems" label="Приоритет" variant="outlined" density="compact" :disabled="isTaskReadonly" />
            </div>
            <v-combobox v-model="taskForm.category" :items="taskCategories" label="Категория" variant="outlined" density="compact" clearable :disabled="isTaskReadonly" />
          </div>
          <div :class="isFieldUnseen('due_date') ? 'field-changed mb-2' : 'mb-2'" @click="dismissField('due_date')">
            <v-text-field v-model="taskForm.due_date" label="Срок исполнения" variant="outlined" density="compact" type="date" :min="todayStr" :rules="[dueDateRule]" :readonly="isTaskReadonly" :bg-color="isTaskReadonly ? 'grey-lighten-4' : undefined" />
          </div>
          <div class="mb-2">
            <v-select
              v-model="taskForm.org_id"
              :items="orgSummary.filter(o => o.org_id !== null).map(o => ({ title: o.org_name, value: o.org_id }))"
              label="Организация"
              variant="outlined"
              density="compact"
              clearable
              prepend-inner-icon="mdi-domain"
              :disabled="isTaskReadonly"
            />
          </div>
          <div :class="isFieldUnseen('assignees') ? 'field-changed mb-2' : 'mb-2'" @click="dismissField('assignees')">
          <v-autocomplete v-if="!editingTask || !isTaskReadonly" v-model="taskForm.assignee_ids" :items="userItems" label="Исполнители" variant="outlined" density="compact" multiple chips closable-chips item-title="text" item-value="value" class="mb-2">
            <template #item="{ item, props }">
              <v-list-item v-bind="props">
                <template #append>
                  <v-chip v-if="item.raw.value !== currentUserId && !subordinateIds.has(item.raw.value) && !managedOrgUserIds.has(item.raw.value)" size="x-small" color="orange" variant="tonal">нужно согласие</v-chip>
                </template>
              </v-list-item>
            </template>
          </v-autocomplete>
          </div>

          <!-- Linked purchase -->
          <div class="mb-2 d-flex align-center ga-1 flex-wrap">
            <template v-if="editingTask?.purchase_id">
              <v-chip color="deep-purple" variant="tonal" prepend-icon="mdi-cart-outline"
                @click="$router.push(`/orders/${editingTask.purchase_id}/edit`); showTaskDialog = false">
                {{ editingTask.purchase_subject || `Закупка #${editingTask.purchase_number || editingTask.purchase_id}` }}
                <v-icon end size="14">mdi-open-in-new</v-icon>
              </v-chip>
              <v-chip v-if="editingTask.purchase_status" size="x-small" variant="tonal">
                {{ editingTask.purchase_status }}
              </v-chip>
              <v-btn v-if="!isTaskReadonly" icon="mdi-link-variant-off" size="x-small" variant="text"
                color="grey" title="Отвязать закупку" @click="unlinkPurchaseFromTask" />
            </template>
            <v-btn v-else-if="editingTask && !isTaskReadonly" size="small" variant="tonal" color="deep-purple"
              prepend-icon="mdi-cart-plus" @click="showTaskDialog = false; $router.push(`/orders?link_task=${editingTask.id}`)">
              Привязать закупку
            </v-btn>
          </div>

          <!-- Диалог привязки закупки -->
          <v-dialog v-model="linkPurchaseDialog" max-width="520">
            <v-card>
              <v-card-title class="text-subtitle-1 pt-4 px-4">
                <v-icon class="mr-1" size="20">mdi-cart-plus</v-icon>
                Привязать закупку
              </v-card-title>
              <v-card-text>
                <v-text-field v-model="linkPurchaseSearch" label="Поиск по названию / номеру"
                  variant="outlined" density="compact" prepend-inner-icon="mdi-magnify" clearable autofocus
                  @update:model-value="searchPurchases" />
                <div v-if="linkPurchaseSearching" class="d-flex justify-center py-4"><v-progress-circular indeterminate size="24" /></div>
                <v-list v-else-if="linkPurchaseResults.length" density="compact" class="border rounded"
                  style="max-height:300px;overflow-y:auto">
                  <v-list-item v-for="p in linkPurchaseResults" :key="p.id" @click="linkPurchaseToTask(p.id)">
                    <v-list-item-title class="text-body-2">
                      {{ p.subject || p.item_name || `Закупка #${p.purchase_number || p.id}` }}
                    </v-list-item-title>
                    <v-list-item-subtitle class="text-caption">
                      {{ p.status }} · {{ p.contractor_name || '' }}
                    </v-list-item-subtitle>
                  </v-list-item>
                </v-list>
                <div v-else-if="linkPurchaseSearch" class="text-caption text-medium-emphasis text-center py-4">
                  Не найдено
                </div>
                <div v-else class="text-caption text-medium-emphasis text-center py-4">
                  Введите текст для поиска
                </div>
              </v-card-text>
              <v-card-actions>
                <v-spacer />
                <v-btn variant="text" @click="linkPurchaseDialog = false">Закрыть</v-btn>
              </v-card-actions>
            </v-card>
          </v-dialog>

          <!-- Subtasks (delegated) -->
          <template v-if="editingTask && taskSubtasks.length">
            <v-divider class="my-2" />
            <div class="text-subtitle-2 font-weight-medium mb-1 d-flex align-center ga-1">
              <v-icon icon="mdi-sitemap-outline" size="16" color="teal" />
              Делегировано ({{ taskSubtasks.length }})
            </div>
            <v-list density="compact" class="border rounded mb-2">
              <v-list-item v-for="st in taskSubtasks" :key="st.id"
                :prepend-icon="'mdi-circle-small'"
                :subtitle="`${st.assignees?.map((a:any)=>a.user_name?.split(' ')[0]).join(', ') || '—'} · ${st.due_date ? st.due_date.split('T')[0] : 'без срока'}`"
                @click="openSubtask(st)">
                <template #title>
                  <span class="text-body-2">{{ st.title }}</span>
                  <v-chip :color="PRIORITY_COLOR[st.priority]||'grey'" size="x-small" variant="flat" class="ml-1">{{ PRIORITY_LABEL[st.priority] }}</v-chip>
                  <v-chip :color="st.status==='done'?'success':st.status==='in_progress'?'primary':'warning'" size="x-small" variant="tonal" class="ml-1">{{ {todo:'К выполнению',in_progress:'В работе',done:'Готово'}[st.status]||st.status }}</v-chip>
                </template>
              </v-list-item>
            </v-list>
          </template>

          <!-- Chat section (only for existing tasks) -->
          <template v-if="editingTask">
            <v-divider class="my-3" />
            <div class="d-flex align-center mb-2">
              <v-icon icon="mdi-chat-outline" size="18" class="mr-1" />
              <span class="text-subtitle-2 font-weight-medium">Чат</span>
            </div>
            <ChatEmbed
              :entity-type="'task'"
              :entity-id="editingTask.id"
              :title="editingTask.title"
            />
          </template>
        </v-card-text>
        <v-card-actions>
          <v-btn v-if="editingTask && !isTaskReadonly" color="error" variant="text" @click="deleteGeneralTask">Удалить</v-btn>
          <v-btn v-if="editingTask" color="teal" variant="tonal" prepend-icon="mdi-account-arrow-right-outline" size="small" @click="openDelegateDialog">
            Делегировать
          </v-btn>
          <v-spacer />
          <v-btn variant="text" @click="closeTaskDialog">Отмена</v-btn>
          <v-btn v-if="!editingTask || !isTaskReadonly" color="primary" :disabled="!taskForm.title" @click="saveGeneralTask">{{ editingTask ? 'Сохранить' : 'Создать' }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delegation dialog -->
    <v-dialog v-model="showDelegateDialog" max-width="520">
      <v-card>
        <v-card-title>Делегировать подзадачу</v-card-title>
        <v-card-text>
          <v-alert type="info" variant="tonal" density="compact" class="mb-3">
            Создаётся подзадача на основе текущей. Вы устанавливаете исполнителя, сроки и приоритет сами.
          </v-alert>
          <v-text-field v-model="delegateForm.title" label="Название задачи *" variant="outlined" density="compact" class="mb-2" />
          <v-textarea v-model="delegateForm.description" label="Описание" variant="outlined" density="compact" rows="2" class="mb-2" />
          <div class="d-flex ga-2 mb-2">
            <v-select v-model="delegateForm.priority" :items="priorityItems" label="Приоритет" variant="outlined" density="compact" style="max-width:200px" />
            <v-text-field v-model="delegateForm.due_date" label="Срок" variant="outlined" density="compact" type="date" :min="todayStr" />
          </div>
          <v-autocomplete v-model="delegateForm.assignee_ids" :items="subordinateItems" label="Исполнители (подчинённые) *" variant="outlined" density="compact" multiple chips closable-chips item-title="text" item-value="value" class="mb-2" />
          <v-switch v-model="delegateForm.import_to_parent" label="Показывать в родительской задаче" color="teal" density="compact" hide-details />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showDelegateDialog = false">Отмена</v-btn>
          <v-btn color="teal" :disabled="!delegateForm.title || !delegateForm.assignee_ids.length" :loading="delegateSaving" @click="saveDelegate">Делегировать</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Purchase comment dialog -->
    <v-dialog v-model="commentDialog" max-width="500">
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

    <!-- Broadcast dialog -->
    <v-dialog v-model="broadcastDialog" max-width="480" persistent>
      <v-card>
        <v-card-title class="d-flex align-center gap-2 pt-4">
          <v-icon color="orange">mdi-bullhorn</v-icon>
          Рассылка из задачи
        </v-card-title>
        <v-card-text>
          <div class="text-caption text-medium-emphasis mb-3">
            Сообщение будет отправлено каждому сотруднику индивидуально в Telegram
          </div>
          <v-radio-group v-model="broadcastScope" class="mb-3">
            <v-radio value="department" label="Отдел" />
            <v-radio value="organization" label="Организация" />
            <v-radio v-if="broadcastOrgs.length > 1" value="all" label="Все организации" />
          </v-radio-group>
          <v-select v-if="broadcastScope === 'department'" v-model="broadcastScopeId"
            :items="broadcastDepts" item-title="name" item-value="id"
            label="Выберите отдел" variant="outlined" density="compact" class="mb-3" />
          <v-select v-if="broadcastScope === 'organization'" v-model="broadcastScopeId"
            :items="broadcastOrgs" item-title="name" item-value="id"
            label="Выберите организацию" variant="outlined" density="compact" class="mb-3" />
          <v-textarea v-model="broadcastText" label="Текст сообщения" variant="outlined"
            density="compact" rows="3" autofocus />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="broadcastDialog = false">Отмена</v-btn>
          <v-btn color="orange" variant="tonal" :loading="broadcastSending"
            :disabled="!broadcastText.trim() || (broadcastScope !== 'all' && !broadcastScopeId)"
            @click="sendBroadcast">
            Отправить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { apiFetch } from '@/api'
import ChatEmbed from '@/components/ChatEmbed.vue'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const selectedOrgId = ref<number | null>(null)
const orgSummary = ref<{org_id: number | null, org_name: string, task_count: number, purchase_count: number, unseen_count: number}[]>([])
const orgLoading = ref(false)
const currentUserId = parseInt(localStorage.getItem('user_id') || '0')
const currentUserRole = localStorage.getItem('user_role') || 'employee'
const isEmployee = currentUserRole === 'employee'
const isManagerOrAdmin = ['superadmin', 'org_admin', 'admin', 'manager'].includes(currentUserRole)
const chatContainer = ref<HTMLElement | null>(null)
const commentInput = ref<any>(null)
const viewMode = ref<'kanban' | 'list'>('kanban')
const taskViewMode = ref<'kanban' | 'list'>('kanban')
const showArchive = ref(false)

// Link purchase mode (from ?link_purchase=ID)
const linkPurchaseId = ref<number | null>(null)

const taskListHeaders = [
  { title: '№', key: 'task_number', width: 60 },
  { title: 'Название', key: 'title', minWidth: 200 },
  { title: 'Приоритет', key: 'priority', width: 100 },
  { title: 'Статус', key: 'status', width: 120 },
  { title: 'Исполнители', key: 'assignees', width: 160, sortable: false },
  { title: 'Срок', key: 'due_date', width: 110 },
  { title: 'Закупка', key: 'purchase_subject', width: 150, sortable: false },
  { title: '', key: 'actions', width: 80, sortable: false },
]

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
const tasks = ref<any[]>([])
const archiveTasks = ref<any[]>([])
const pendingApprovals = ref<any[]>([])

const activeTab = ref<'purchases' | 'general' | 'report'>('general')
const commentDialog = ref(false)
const commentText = ref('')
const commentTaskId = ref<number | null>(null)

const TAB_SUBTITLES: Record<string, string> = {
  purchases: 'Канбан-доска по закупкам',
  general: 'Общие задачи',
  report: 'Отчёт по отделам',
}

const todayStr = new Date().toISOString().split('T')[0]
const dueDateRule = (v: string) => {
  if (!v) return true
  return v >= todayStr || 'Срок не может быть раньше сегодня'
}

// ── General tasks ──
const generalTasks = ref<any[]>([])
const pendingConsentTasks = ref<any[]>([])
const consentLoading = ref<string | null>(null)
const consentDeclines = ref<any[]>([])
const declineNotifs = computed(() => consentDeclines.value.filter((d: any) => !d.is_accepted))
const acceptNotifs = computed(() => consentDeclines.value.filter((d: any) => d.is_accepted))
const ackLoading = ref<number | null>(null)
const showTaskDialog = ref(false)
const editingTask = ref<any>(null)
const taskCategories = ref<string[]>([])
const userItems = ref<{text:string, value:number}[]>([])
const subordinateIds = ref<Set<number>>(new Set())
const managedOrgUserIds = ref<Set<number>>(new Set())
const canAssignWithoutConsent = computed(() => {
  const role = localStorage.getItem('user_role') || ''
  return ['superadmin', 'account_owner', 'admin', 'org_admin', 'manager'].includes(role)
})
const taskForm = ref({ title: '', description: '', priority: 'medium', due_date: '', assignee_ids: [] as number[], category: '', org_id: null as number | null })

// Task comments
const taskComments = ref<any[]>([])
const commentsLoading = ref(false)
const newCommentText = ref('')
const commentSaving = ref(false)

// Subtasks and delegation
const taskSubtasks = ref<any[]>([])
const showDelegateDialog = ref(false)
const delegateSaving = ref(false)
const subordinateItems = ref<{text:string, value:number}[]>([])
const delegateForm = ref({ title: '', description: '', priority: 'medium', due_date: '', assignee_ids: [] as number[], import_to_parent: true })

const isTaskReadonly = computed(() => {
  if (!editingTask.value) return false
  const role = localStorage.getItem('user_role') || ''
  if (['superadmin', 'org_admin', 'admin'].includes(role)) return false
  const uid = currentUserId
  const t = editingTask.value
  const isAssignee = (t.assignees || []).some((a: any) => a.user_id === uid)
  return isAssignee && t.created_by_id !== uid
})

// Report
const departments = ref<string[]>([])
const reportDept = ref<string | null>(null)
const reportWeeks = ref(1)
const reportLoading = ref(false)
const reportData = ref<any>(null)

const GT_COLUMNS = [
  { status: 'todo', label: 'К выполнению', color: '#F59E0B' },
  { status: 'in_progress', label: 'В работе', color: '#3B82F6' },
  { status: 'review', label: 'На проверке', color: '#8B5CF6' },
  { status: 'done', label: 'Готово', color: '#22C55E' },
]
const PRIORITY_LABEL: Record<string,string> = { low:'Низкий', medium:'Средний', high:'Высокий', urgent:'Срочно' }
const PRIORITY_COLOR: Record<string,string> = { low:'grey', medium:'blue', high:'orange', urgent:'red' }
const priorityItems = [
  { title:'Низкий', value:'low' }, { title:'Средний', value:'medium' },
  { title:'Высокий', value:'high' }, { title:'Срочно', value:'urgent' },
]

const generalByStatus = (status: string) => generalTasks.value.filter(t => t.status === status)

// ── Deadline urgency for card background ──
function gtCardStyle(gt: any): Record<string, string> {
  if (gt.status === 'done') {
    if (!gt.due_date) return { background: 'rgba(34,197,94,0.08)', borderColor: 'rgba(34,197,94,0.3)' }
    const completedAt = gt.updated_at ? new Date(gt.updated_at) : new Date()
    const dueDate = new Date(gt.due_date)
    const diffDays = (dueDate.getTime() - completedAt.getTime()) / 86400000
    if (diffDays < 0) return { background: 'rgba(239,68,68,0.15)', borderColor: 'rgba(239,68,68,0.5)' }   // просрочена
    if (diffDays < 1) return { background: 'rgba(245,158,11,0.12)', borderColor: 'rgba(245,158,11,0.45)' } // впритык
    return { background: 'rgba(34,197,94,0.12)', borderColor: 'rgba(34,197,94,0.45)' }                    // заранее
  }
  if (!gt.due_date) return {}
  const diff = (new Date(gt.due_date).getTime() - Date.now()) / 86400000
  if (diff < 0) return { background: 'rgba(239,68,68,0.15)', borderColor: 'rgba(239,68,68,0.4)' }
  if (diff <= 1) return { background: 'rgba(239,68,68,0.10)', borderColor: 'rgba(239,68,68,0.3)' }
  if (diff <= 3) return { background: 'rgba(249,115,22,0.10)', borderColor: 'rgba(249,115,22,0.3)' }
  if (diff <= 7) return { background: 'rgba(245,158,11,0.08)', borderColor: 'rgba(245,158,11,0.25)' }
  return { background: 'rgba(34,197,94,0.06)', borderColor: 'rgba(34,197,94,0.2)' }
}

// ── General task drag & drop ──
let draggedGeneral: any = null
function onDragStartGeneral(e: DragEvent, task: any) {
  draggedGeneral = task
  if (e.dataTransfer) { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(task.id)) }
}
async function onDropGeneral(e: DragEvent, targetStatus: string) {
  e.preventDefault()
  if (!draggedGeneral || draggedGeneral.status === targetStatus) return
  const t = draggedGeneral; draggedGeneral = null
  const old = t.status; t.status = targetStatus
  try { await apiFetch(`/tasks/${t.id}`, { method: 'PATCH', body: JSON.stringify({ status: targetStatus }) }) }
  catch { t.status = old }
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

function openNewTask() {
  editingTask.value = null
  taskForm.value = { title: '', description: '', priority: 'medium', due_date: '', assignee_ids: [], category: '', org_id: selectedOrgId.value }
  taskComments.value = []
  newCommentText.value = ''
  showTaskDialog.value = true
}

function isFieldUnseen(fieldName: string): boolean {
  return (editingTask.value?.unseen_fields || []).includes(fieldName)
}

async function dismissField(fieldName: string) {
  if (!editingTask.value) return
  if (!isFieldUnseen(fieldName)) return
  try {
    await apiFetch(`/tasks/${editingTask.value.id}/dismiss-field`, {
      method: 'POST',
      body: { field_name: fieldName } as any,
    })
    editingTask.value.unseen_fields = (editingTask.value.unseen_fields || []).filter((f: string) => f !== fieldName)
    editingTask.value.unseen_changes_count = Math.max(0, (editingTask.value.unseen_changes_count || 0) - 1)
    // Sync to the task list
    const idx = generalTasks.value.findIndex((t: any) => t.id === editingTask.value.id)
    if (idx >= 0) {
      generalTasks.value[idx] = { ...generalTasks.value[idx], unseen_fields: editingTask.value.unseen_fields, unseen_changes_count: editingTask.value.unseen_changes_count }
    }
  } catch { /* best-effort */ }
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
  taskSubtasks.value = []
  newCommentText.value = ''
  showTaskDialog.value = true
  loadComments(t.id)
  if (t.subtask_count > 0 || t.import_to_parent) loadSubtasks(t.id)
}

async function loadSubtasks(taskId: number) {
  try {
    taskSubtasks.value = await apiFetch<any[]>(`/tasks/${taskId}/subtasks`)
  } catch { taskSubtasks.value = [] }
}

function openSubtask(st: any) {
  closeTaskDialog()
  setTimeout(() => editGeneralTask(st), 100)
}

async function openDelegateDialog() {
  if (!editingTask.value) return
  // Load subordinates of current user
  try {
    const subs = await apiFetch<any[]>(`/users/${currentUserId}/subordinates`)
    subordinateItems.value = subs.map((u: any) => ({ text: u.full_name || u.username, value: u.id }))
  } catch {
    subordinateItems.value = userItems.value
  }
  delegateForm.value = {
    title: editingTask.value.title,
    description: editingTask.value.description || '',
    priority: editingTask.value.priority || 'medium',
    due_date: editingTask.value.due_date ? editingTask.value.due_date.split('T')[0] : '',
    assignee_ids: [],
    import_to_parent: true,
  }
  showDelegateDialog.value = true
}

async function saveDelegate() {
  if (!editingTask.value || !delegateForm.value.assignee_ids.length) return
  delegateSaving.value = true
  try {
    const body: any = {
      ...delegateForm.value,
      parent_task_id: editingTask.value.id,
    }
    if (body.due_date) body.due_date = body.due_date + 'T23:59:59Z'
    else delete body.due_date
    const created = await apiFetch<any>('/tasks/', { method: 'POST', body: JSON.stringify(body) })
    generalTasks.value.push(created)
    // Update subtask count on parent card
    const parentCard = generalTasks.value.find(t => t.id === editingTask.value!.id)
    if (parentCard) parentCard.subtask_count = (parentCard.subtask_count || 0) + 1
    taskSubtasks.value.push(created)
    showDelegateDialog.value = false
  } catch (e: any) {
    alert(e?.detail || 'Ошибка делегирования')
  } finally {
    delegateSaving.value = false
  }
}

// Auto-refresh comments every 5s when dialog is open
let _commentsPollTimer: ReturnType<typeof setInterval> | null = null

function closeTaskDialog() {
  showTaskDialog.value = false
  editingTask.value = null
  taskComments.value = []
  taskSubtasks.value = []
  if (_commentsPollTimer) { clearInterval(_commentsPollTimer); _commentsPollTimer = null }
}

async function loadComments(taskId: number) {
  commentsLoading.value = true
  try {
    taskComments.value = await apiFetch<any[]>(`/tasks/${taskId}/comments`)
    await nextTick()
    scrollChatToBottom()
  } catch { taskComments.value = [] }
  finally { commentsLoading.value = false }

  // Start polling for new comments
  if (_commentsPollTimer) clearInterval(_commentsPollTimer)
  _commentsPollTimer = setInterval(async () => {
    if (!showTaskDialog.value || !editingTask.value) {
      if (_commentsPollTimer) { clearInterval(_commentsPollTimer); _commentsPollTimer = null }
      return
    }
    try {
      const fresh = await apiFetch<any[]>(`/tasks/${taskId}/comments`)
      if (fresh.length !== taskComments.value.length) {
        taskComments.value = fresh
        await nextTick()
        scrollChatToBottom()
      }
    } catch { /* ignore */ }
  }, 5000)
}

async function addComment() {
  if (!editingTask.value || !newCommentText.value.trim()) return
  commentSaving.value = true
  mentionOpen.value = false
  try {
    const c = await apiFetch<any>(`/tasks/${editingTask.value.id}/comments`, {
      method: 'POST', body: JSON.stringify({ text: newCommentText.value.trim() }),
    })
    taskComments.value.push(c)
    newCommentText.value = ''
    // Update preview on card
    const gt = generalTasks.value.find(t => t.id === editingTask.value.id)
    if (gt) {
      gt.last_comment = c.text.slice(0, 100)
      gt.last_comment_user = c.user_name
      gt.last_comment_at = c.created_at
      gt.comment_count = (gt.comment_count || 0) + 1
    }
    await nextTick()
    scrollChatToBottom()
  } catch(e) { console.error(e) }
  finally { commentSaving.value = false }
}

function scrollChatToBottom() {
  if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight
}

// ── @ Mentions ──
const mentionOpen = ref(false)
const mentionQuery = ref('')
const mentionFromButton = ref(false)  // true when opened via @ button
const enterToSend = ref(localStorage.getItem('chat_enter_to_send') !== 'false')  // default: true

function saveSendMode() {
  localStorage.setItem('chat_enter_to_send', String(enterToSend.value))
}

const mentionableUsers = computed(() => {
  // Users in current task (assignees + creator)
  if (!editingTask.value) return userItems.value
  const taskUsers = new Set<number>()
  if (editingTask.value.assignees) {
    for (const a of editingTask.value.assignees) taskUsers.add(a.user_id)
  }
  if (editingTask.value.created_by_id) taskUsers.add(editingTask.value.created_by_id)
  // Show task participants first, then others
  const inTask = userItems.value.filter(u => taskUsers.has(u.value))
  const others = userItems.value.filter(u => !taskUsers.has(u.value))
  return [...inTask, ...others]
})

const filteredMentionUsers = computed(() => {
  const q = mentionQuery.value.toLowerCase()
  if (mentionFromButton.value && !q) {
    // Show task participants when opened via button
    return mentionableUsers.value.slice(0, 8)
  }
  return mentionableUsers.value.filter(u => u.text.toLowerCase().includes(q)).slice(0, 6)
})

function openMentionPicker() {
  mentionFromButton.value = true
  mentionQuery.value = ''
  // Add @ to text if not already there
  const text = newCommentText.value
  if (!text.endsWith('@')) {
    newCommentText.value = text + (text && !text.endsWith(' ') ? ' @' : '@')
  }
  mentionOpen.value = true
}

function onCommentInput() {
  mentionFromButton.value = false
  const text = newCommentText.value
  // Find if cursor is after a @ trigger
  const atIdx = text.lastIndexOf('@')
  if (atIdx >= 0) {
    const afterAt = text.slice(atIdx + 1)
    // Only show if no space after the query part (still typing)
    if (!afterAt.includes('\n') && afterAt.length <= 30) {
      mentionQuery.value = afterAt
      mentionOpen.value = true
      return
    }
  }
  mentionOpen.value = false
}

function onCommentKeydown(e: KeyboardEvent) {
  if (mentionOpen.value) {
    if (e.key === 'Escape') {
      mentionOpen.value = false
      e.preventDefault()
      return
    }
    if (e.key === 'Tab' || e.key === 'Enter') {
      if (filteredMentionUsers.value.length > 0) {
        e.preventDefault()
        insertMention(filteredMentionUsers.value[0])
        return
      }
    }
  }

  if (e.key === 'Enter') {
    const ctrlOrMeta = e.ctrlKey || e.metaKey
    if (enterToSend.value) {
      // Enter = send, Ctrl+Enter = newline
      if (ctrlOrMeta) {
        // Insert newline manually
        e.preventDefault()
        const ta = (commentInput.value as any)?.$el?.querySelector('textarea')
        if (ta) {
          const start = ta.selectionStart
          newCommentText.value = newCommentText.value.slice(0, start) + '\n' + newCommentText.value.slice(ta.selectionEnd)
          nextTick(() => { ta.selectionStart = ta.selectionEnd = start + 1 })
        }
        return
      }
      if (!e.shiftKey) {
        e.preventDefault()
        addComment()
      }
    } else {
      // Ctrl+Enter = send, Enter = newline (default textarea behavior)
      if (ctrlOrMeta) {
        e.preventDefault()
        addComment()
      }
    }
  }
}

function insertMention(user: { text: string; value: number }) {
  const text = newCommentText.value
  const atIdx = text.lastIndexOf('@')
  if (atIdx >= 0) {
    newCommentText.value = text.slice(0, atIdx) + `@${user.text} `
  }
  mentionOpen.value = false
  mentionFromButton.value = false
  // Focus back on input
  nextTick(() => {
    const el = (commentInput.value as any)?.$el?.querySelector('textarea')
    if (el) el.focus()
  })
}

// ── Link purchase to task ──
const linkPurchaseDialog = ref(false)
const linkPurchaseSearch = ref('')
const linkPurchaseResults = ref<any[]>([])
const linkPurchaseSearching = ref(false)
let _purchaseSearchTimer: ReturnType<typeof setTimeout> | null = null

function openLinkPurchase() {
  linkPurchaseSearch.value = ''
  linkPurchaseResults.value = []
  linkPurchaseDialog.value = true
}

function searchPurchases(q: string | null) {
  if (_purchaseSearchTimer) clearTimeout(_purchaseSearchTimer)
  if (!q || q.length < 2) { linkPurchaseResults.value = []; return }
  _purchaseSearchTimer = setTimeout(async () => {
    linkPurchaseSearching.value = true
    try {
      linkPurchaseResults.value = await apiFetch<any[]>(`/purchases/?search=${encodeURIComponent(q)}&limit=20`)
    } catch { linkPurchaseResults.value = [] }
    finally { linkPurchaseSearching.value = false }
  }, 300)
}

async function linkPurchaseToTask(purchaseId: number) {
  if (!editingTask.value) return
  try {
    const updated = await apiFetch<any>(`/tasks/${editingTask.value.id}`, {
      method: 'PATCH', body: JSON.stringify({ purchase_id: purchaseId }),
    })
    editingTask.value = { ...editingTask.value, ...updated }
    const idx = generalTasks.value.findIndex(t => t.id === editingTask.value.id)
    if (idx >= 0) generalTasks.value[idx] = editingTask.value
    linkPurchaseDialog.value = false
  } catch (e: any) {
    alert(e?.detail || 'Ошибка привязки')
  }
}

async function unlinkPurchaseFromTask() {
  if (!editingTask.value) return
  try {
    const updated = await apiFetch<any>(`/tasks/${editingTask.value.id}`, {
      method: 'PATCH', body: JSON.stringify({ purchase_id: null }),
    })
    editingTask.value = { ...editingTask.value, ...updated, purchase_id: null, purchase_subject: null, purchase_number: null, purchase_status: null }
    const idx = generalTasks.value.findIndex(t => t.id === editingTask.value.id)
    if (idx >= 0) generalTasks.value[idx] = editingTask.value
  } catch (e: any) {
    alert(e?.detail || 'Ошибка')
  }
}

// ── Broadcast ──
const broadcastDialog = ref(false)
const broadcastScope = ref<'department' | 'organization' | 'all'>('organization')
const broadcastScopeId = ref<number | null>(null)
const broadcastText = ref('')
const broadcastSending = ref(false)
const broadcastOrgs = ref<{ id: number; name: string }[]>([])
const broadcastDepts = ref<{ id: number; name: string }[]>([])

async function openBroadcastDialog() {
  broadcastText.value = newCommentText.value || ''
  broadcastScopeId.value = null
  broadcastDialog.value = true
  // Load scopes
  try {
    const data = await apiFetch<any>('/tasks/broadcast/scopes')
    broadcastOrgs.value = data.organizations || []
    broadcastDepts.value = data.departments || []
    // Auto-select first org if only one
    if (broadcastOrgs.value.length === 1) broadcastScopeId.value = broadcastOrgs.value[0].id
  } catch {}
}

async function sendBroadcast() {
  if (!editingTask.value || !broadcastText.value.trim()) return
  broadcastSending.value = true
  try {
    const res = await apiFetch<any>(`/tasks/${editingTask.value.id}/broadcast`, {
      method: 'POST',
      body: JSON.stringify({
        text: broadcastText.value.trim(),
        scope: broadcastScope.value,
        scope_id: broadcastScope.value !== 'all' ? broadcastScopeId.value : undefined,
      }),
    })
    broadcastDialog.value = false
    newCommentText.value = ''
    alert(`Отправлено: ${res.sent} из ${res.total_users} сотрудников`)
    await loadComments(editingTask.value.id)
  } catch (e: any) {
    alert(e?.detail || 'Ошибка рассылки')
  } finally {
    broadcastSending.value = false
  }
}

function renderMentions(text: string): string {
  if (!text) return ''
  // Escape HTML first
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  // Highlight @mentions
  return escaped.replace(/@([A-Za-zА-Яа-яёЁ\s]+?)(\s|$)/g, '<span class="chat-mention">@$1</span>$2')
}

async function deleteComment(commentId: number) {
  if (!editingTask.value) return
  try {
    await apiFetch(`/tasks/${editingTask.value.id}/comments/${commentId}`, { method: 'DELETE' })
    taskComments.value = taskComments.value.filter(c => c.id !== commentId)
    const gt = generalTasks.value.find(t => t.id === editingTask.value.id)
    if (gt) {
      gt.comment_count = Math.max(0, (gt.comment_count || 1) - 1)
      if (taskComments.value.length > 0) {
        const last = taskComments.value[taskComments.value.length - 1]
        gt.last_comment = last.text.slice(0, 100)
        gt.last_comment_user = last.user_name
      } else {
        gt.last_comment = null; gt.last_comment_user = null
      }
    }
  } catch(e) { console.error(e) }
}

async function saveGeneralTask() {
  const body: any = { ...taskForm.value }
  if (body.due_date) body.due_date = body.due_date + 'T23:59:59Z'
  else delete body.due_date
  if (!body.category) delete body.category
  if (!body.assignee_ids?.length) body.assignee_ids = []
  try {
    if (editingTask.value) {
      const updated = await apiFetch<any>(`/tasks/${editingTask.value.id}`, { method: 'PATCH', body: JSON.stringify(body) })
      const idx = generalTasks.value.findIndex(t => t.id === editingTask.value.id)
      if (idx >= 0) generalTasks.value[idx] = { ...generalTasks.value[idx], ...updated }
    } else {
      const created = await apiFetch<any>('/tasks/', { method: 'POST', body: JSON.stringify(body) })
      generalTasks.value.push(created)
    }
  } catch(e: any) {
    if (e?.detail) alert(e.detail)
    else console.error(e)
    return
  }
  closeTaskDialog()
}

async function deleteGeneralTask() {
  if (!editingTask.value) return
  try { await apiFetch(`/tasks/${editingTask.value.id}`, { method: 'DELETE' }) }
  catch(e) { console.error(e); return }
  generalTasks.value = generalTasks.value.filter(t => t.id !== editingTask.value.id)
  closeTaskDialog()
}

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
    if (accept) {
      // Reload my tasks to include the accepted task
      generalTasks.value = await apiFetch<any[]>('/tasks/my')
    }
  } catch(e: any) {
    alert(e?.detail || 'Ошибка')
  } finally {
    consentLoading.value = null
  }
}

// ── Report ──
async function loadReport() {
  reportLoading.value = true
  try {
    const params = new URLSearchParams()
    if (reportDept.value) params.set('department', reportDept.value)
    params.set('weeks', String(reportWeeks.value))
    reportData.value = await apiFetch<any>(`/tasks/report/by-department?${params}`)
  } catch(e) { console.error(e); reportData.value = null }
  finally { reportLoading.value = false }
}

// ── Purchases kanban ──
interface KanbanColumn { status: string; label: string; color: string }

const COLUMNS: KanbanColumn[] = [
  { status: 'wishes', label: 'Желания сотрудников', color: '#F59E0B' },
  { status: 'plan_schedule', label: 'План-график', color: '#FB923C' },
  { status: 'confirmed', label: 'Подтверждено', color: '#3B82F6' },
  { status: 'work_in_progress', label: 'Ведётся работа', color: '#14B8A6' },
  { status: 'contracted', label: 'Договор', color: '#6366F1' },
  { status: 'delivered', label: 'Поставлено', color: '#8B5CF6' },
]
const ARCHIVE_COLUMN: KanbanColumn = { status: 'paid', label: 'Оплачено (архив)', color: '#22C55E' }

const STATUS_LABELS: Record<string, string> = {
  wishes: 'Желания', plan_schedule: 'План-график',
  confirmed: 'Подтверждено', work_in_progress: 'Ведётся работа',
  contracted: 'Договор', delivered: 'Поставлено', paid: 'Оплачено',
}
const FRAMEWORK_TYPES = new Set(['framework_cumulative', 'framework_with_amount'])
function purchaseStatusLabel(task: any): string {
  if (task.status === 'contracted' && FRAMEWORK_TYPES.has(task.purchase_contract_type || '')) return 'Заказ'
  return STATUS_LABELS[task.status] || task.status
}
const SUBSTATUS_LABEL: Record<string, string> = {
  tz_forming: 'Формируется ТЗ', kp_collecting: 'Сбор КП', on_platform: 'На площадке',
}

const visibleColumns = computed(() => showArchive.value ? [...COLUMNS, ARCHIVE_COLUMN] : COLUMNS)
const filteredTasks = computed(() => [...tasks.value, ...(showArchive.value ? archiveTasks.value : [])])
const tasksByStatus = (status: string) => {
  if (status === 'paid') return archiveTasks.value
  return tasks.value.filter(t => t.status === status)
}

let draggedTask: any = null
function onDragStart(e: DragEvent, task: any) {
  draggedTask = task
  if (e.dataTransfer) { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(task.id)) }
}
async function onDrop(e: DragEvent, targetStatus: string) {
  e.preventDefault()
  if (!draggedTask || draggedTask.status === targetStatus) return
  const task = draggedTask; draggedTask = null
  const oldStatus = task.status; task.status = targetStatus
  if (targetStatus === 'paid') { tasks.value = tasks.value.filter(t => t.id !== task.id); archiveTasks.value.unshift(task) }
  else if (oldStatus === 'paid') { archiveTasks.value = archiveTasks.value.filter(t => t.id !== task.id); tasks.value.push(task) }
  try { await apiFetch(`/purchases/${task.id}/kanban-status?status=${targetStatus}`, { method: 'PATCH' }) }
  catch {
    task.status = oldStatus
    if (targetStatus === 'paid') { archiveTasks.value = archiveTasks.value.filter(t => t.id !== task.id); tasks.value.push(task) }
    else if (oldStatus === 'paid') { tasks.value = tasks.value.filter(t => t.id !== task.id); archiveTasks.value.unshift(task) }
  }
}

function openTask(id: number) { router.push(`/orders/${id}/edit`) }

function statusColor(s: string): string {
  const map: Record<string, string> = {
    wishes: 'amber', plan_schedule: 'orange', confirmed: 'primary',
    work_in_progress: 'teal', contracted: 'indigo', delivered: 'deep-purple', paid: 'success',
  }
  return map[s] || 'grey'
}

function deadlineColor(d: string): string {
  const diff = (new Date(d).getTime() - Date.now()) / 86400000
  if (diff < 0) return 'error'
  if (diff <= 7) return 'warning'
  return 'success'
}

function formatDate(d: string): string {
  if (!d) return ''
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}

function formatDatetime(d: string): string {
  if (!d) return ''
  const dt = new Date(d)
  return dt.toLocaleDateString('ru-RU') + ' ' + dt.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

function formatMoney(v?: number): string {
  if (!v) return '0 ₽'
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + ' млн ₽'
  if (v >= 1_000) return (v / 1_000).toFixed(0) + ' тыс ₽'
  return v.toLocaleString('ru-RU') + ' ₽'
}

async function saveComment() {
  if (commentTaskId.value === null) return
  await apiFetch(`/purchases/${commentTaskId.value}/comment?comment=${encodeURIComponent(commentText.value)}`, { method: 'PATCH' })
  const task = [...tasks.value, ...archiveTasks.value].find(t => t.id === commentTaskId.value)
  if (task) task.task_comment = commentText.value
  commentDialog.value = false
}

async function loadOrgSummary() {
  orgLoading.value = true
  try {
    orgSummary.value = await apiFetch<any[]>('/tasks/org-summary')
  } catch (e) {
    console.error('Failed to load org summary:', e)
    orgSummary.value = []
  } finally {
    orgLoading.value = false
  }
}

function selectOrg(orgId: number | null) {
  selectedOrgId.value = orgId
}

async function load() {
  loading.value = true
  try {
    await Promise.all([
      // 1. All task data in ONE request (my + pending + declines + categories + departments)
      apiFetch<any>('/tasks/init').then(data => {
        generalTasks.value = data.my_tasks || []
        pendingConsentTasks.value = data.pending_consent || []
        consentDeclines.value = data.consent_declines || []
        taskCategories.value = data.categories || []
        departments.value = data.departments || []
      }).catch(() => { generalTasks.value = [] }),
      // 2. Purchases active
      apiFetch<any[]>('/purchases/my-tasks')
        .then(active => { tasks.value = active.filter(t => t.status !== 'paid') })
        .catch(e => console.error('Load purchases error:', e)),
      // 3. Purchases archive
      apiFetch<any[]>('/purchases/my-tasks?include_archive=true')
        .then(archived => { archiveTasks.value = archived.filter(t => t.status === 'paid') })
        .catch(() => {}),
      // 4. Approvals
      apiFetch<any[]>('/approvals/my-pending')
        .then(r => { pendingApprovals.value = r })
        .catch(() => { pendingApprovals.value = [] }),
    ])
  } catch (e) { console.error('Load error:', e) }
  finally { loading.value = false }
  // Load users lazily after paint (needed only for task create/edit dialog)
  apiFetch<any[]>('/users/').then(users => {
    userItems.value = users.map(u => ({ text: u.full_name || u.username, value: u.id }))
  }).catch(() => {})
  apiFetch<any[]>(`/users/${currentUserId}/subordinates`).then(subs => {
    subordinateIds.value = new Set((subs as any[]).map((u: any) => u.id))
  }).catch(() => {})
  // Load users managed via hierarchy (org edges + dept edges)
  apiFetch<any>(`/hierarchy/graph`).then((graph: any) => {
    const ids = new Set<number>()
    // Users in orgs managed by current user
    const myManagedOrgIds = new Set((graph.user_org_edges || []).filter((e: any) => e.manager_user_id === currentUserId).map((e: any) => e.org_id))
    for (const u of (graph.users || [])) {
      if (myManagedOrgIds.has(u.org_id)) ids.add(u.id)
    }
    // Users in depts managed by current user
    const myManagedDeptIds = new Set((graph.user_dept_edges || []).filter((e: any) => e.manager_user_id === currentUserId).map((e: any) => e.dept_id))
    for (const dept of (graph.departments || [])) {
      if (myManagedDeptIds.has(dept.id)) {
        for (const uid of (dept.member_ids || [])) ids.add(uid)
      }
    }
    managedOrgUserIds.value = ids
  }).catch(() => {})
}

// ── Real-time polling: refresh tasks every 30 seconds ──
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
  loadOrgSummary()
  await load()
  _pollInterval = setInterval(pollTasks, 30_000)

  // Link purchase mode: ?link_purchase=ID
  if (route.query.link_purchase) {
    linkPurchaseId.value = Number(route.query.link_purchase)
    activeTab.value = 'general'
    taskViewMode.value = 'list'
  }

  // Deep link: ?task={id} — open specific task
  const taskIdParam = route.query.task
  if (taskIdParam) {
    const taskId = Number(taskIdParam)
    if (taskId) {
      activeTab.value = 'general'
      await nextTick()
      // Try to find in loaded tasks
      let found = generalTasks.value.find((t: any) => t.id === taskId)
      if (!found) {
        // Load individually
        try {
          found = await apiFetch<any>(`/tasks/${taskId}`)
        } catch {}
      }
      if (found) {
        editGeneralTask(found)
      }
      // Clean up URL
      router.replace({ query: {} })
    }
  }
})
onUnmounted(() => {
  if (_pollInterval) clearInterval(_pollInterval)
  if (_commentsPollTimer) clearInterval(_commentsPollTimer)
})
</script>

<style scoped>
.kanban-board {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 12px;
  min-height: 400px;
}

.kanban-column {
  min-width: 240px;
  max-width: 280px;
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--crm-surface-alt);
  border-radius: 12px;
  border: 1px solid var(--crm-border);
}

.kanban-column-header {
  padding: 12px 14px;
  border-top: 3px solid;
  border-radius: 12px 12px 0 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--crm-surface);
}

.kanban-column-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--crm-text-secondary);
}

.kanban-column-body {
  flex: 1;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 100px;
}

.kanban-card {
  background: var(--crm-surface);
  border-radius: 8px;
  padding: 12px;
  border: 1px solid var(--crm-border);
  cursor: grab;
  transition: box-shadow 0.15s, transform 0.1s, background 0.3s, border-color 0.3s;
}
.kanban-card:hover {
  box-shadow: 0 2px 8px var(--crm-shadow-hover);
  transform: translateY(-1px);
}
.kanban-card:active {
  cursor: grabbing;
  opacity: 0.8;
}

.kanban-card-header { margin-bottom: 6px; }
.kanban-card-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--crm-text);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.kanban-card-meta {
  font-size: 11px;
  color: var(--crm-text-muted);
  margin-bottom: 6px;
  display: flex;
  align-items: center;
}

.kanban-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.kanban-card-amount {
  font-size: 12px;
  font-weight: 600;
  color: var(--crm-text-secondary);
}

.kanban-card-comment {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed var(--crm-border);
  font-size: 11px;
  color: var(--crm-text-muted);
  display: flex;
  align-items: flex-start;
}

.kanban-empty {
  text-align: center;
  color: var(--crm-text-faint);
  font-size: 12px;
  padding: 20px 8px;
}

.report-task-item {
  padding: 6px 8px;
  border-radius: 6px;
  margin-bottom: 4px;
  background: rgba(0,0,0,0.02);
  border: 1px solid rgba(0,0,0,0.05);
}

/* Chat styles */
.chat-container {
  max-height: 300px;
  overflow-y: auto;
  padding: 8px;
  background: rgba(0,0,0,0.02);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.chat-msg {
  max-width: 85%;
  padding: 8px 12px;
  border-radius: 12px;
  position: relative;
}
.chat-msg--mine {
  align-self: flex-end;
  background: rgb(var(--v-theme-primary));
  color: white;
  border-bottom-right-radius: 4px;
}
.chat-msg--other {
  align-self: flex-start;
  background: rgba(0,0,0,0.06);
  border-bottom-left-radius: 4px;
}

.chat-msg-header {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 2px;
}
.chat-msg-author {
  font-size: 11px;
  font-weight: 600;
  opacity: 0.85;
}
.chat-msg-time {
  font-size: 10px;
  opacity: 0.6;
  margin-left: auto;
}
.chat-msg-delete {
  opacity: 0;
  transition: opacity 0.15s;
}
.chat-msg:hover .chat-msg-delete {
  opacity: 0.7;
}
.chat-msg-text {
  font-size: 13px;
  line-height: 1.4;
  white-space: pre-line;
  word-break: break-word;
}

/* Mention dropdown */
.mention-dropdown {
  background: var(--crm-surface, #fff);
  border: 1px solid rgba(0,0,0,0.12);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  max-height: 180px;
  overflow-y: auto;
  margin-bottom: 4px;
}
.mention-item {
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  display: flex;
  align-items: center;
}
.mention-item:hover {
  background: rgba(var(--v-theme-primary), 0.08);
}

/* Mention highlight in messages */
:deep(.chat-mention) {
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
  background: rgba(var(--v-theme-primary), 0.1);
  border-radius: 3px;
  padding: 0 2px;
}
.chat-msg--mine :deep(.chat-mention) {
  color: white;
  background: rgba(255,255,255,0.25);
}
.send-mode-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #aaa;
  cursor: pointer;
  user-select: none;
  padding: 2px 0;
}
.send-mode-toggle span.active {
  color: #1976d2;
  font-weight: 500;
}
.send-mode-toggle .sep {
  color: #ddd;
}
.send-mode-toggle:hover {
  color: #666;
}
/* Field change highlight — click to dismiss */
.field-changed {
  border-radius: 6px;
  outline: 2px solid #F59E0B;
  outline-offset: 2px;
  cursor: pointer;
  transition: outline-color 0.2s;
}
.field-changed:hover {
  outline-color: #D97706;
}

.org-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}
.org-sel-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  border-radius: 12px;
  border: 1.5px solid rgba(0,0,0,0.12);
  background: #fff;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s;
  min-height: 88px;
}
.org-sel-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 14px rgba(0,0,0,0.12);
  border-color: #2563EB;
}
.org-sel-card--all {
  border-color: #2563EB;
  background: #EFF6FF;
}
.osc-icon-box {
  flex: 0 0 auto;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background: #EFF6FF;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #2563EB;
}
.org-sel-card--all .osc-icon-box {
  background: #2563EB;
  color: #fff;
}
.osc-body {
  flex: 1;
  min-width: 0;
}
.osc-name {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #1e293b;
}
.osc-stats {
  display: flex;
  gap: 12px;
  margin-top: 6px;
  font-size: 12px;
  color: #64748b;
}
.osc-stat-label {
  font-size: 10px;
  opacity: 0.75;
}
.osc-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  min-width: 20px;
  height: 20px;
  padding: 0 5px;
  border-radius: 10px;
  background: #F59E0B;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
