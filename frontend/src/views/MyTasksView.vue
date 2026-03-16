<template>
  <v-container fluid class="pa-4">
    <!-- Header -->
    <div class="d-flex align-center mb-4 flex-wrap" style="gap:12px">
      <div>
        <h1 class="text-h5 font-weight-bold">Мои задачи</h1>
        <span class="text-body-2 text-medium-emphasis">{{ TAB_SUBTITLES[activeTab] }}</span>
      </div>
      <v-spacer />
      <v-btn-toggle v-model="activeTab" mandatory density="compact" color="primary" class="mr-2">
        <v-btn value="purchases" size="small"><v-icon icon="mdi-cart" class="mr-1" size="18"/>Закупки</v-btn>
        <v-btn value="general" size="small"><v-icon icon="mdi-clipboard-list" class="mr-1" size="18"/>Задачи <v-chip v-if="generalTasks.length" size="x-small" color="primary" class="ml-1">{{ generalTasks.length }}</v-chip></v-btn>
        <v-btn value="report" size="small"><v-icon icon="mdi-chart-bar" class="mr-1" size="18"/>Отчёт</v-btn>
      </v-btn-toggle>
      <v-btn-toggle v-if="activeTab === 'purchases'" v-model="viewMode" mandatory density="compact" color="primary">
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
                  {{ STATUS_LABELS[task.status] || task.status }}
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
      <div v-if="loading && generalTasks.length === 0" class="d-flex justify-center py-12">
        <v-progress-circular indeterminate color="primary" size="48" />
      </div>
      <div v-else-if="generalTasks.length === 0" class="text-center py-12">
        <v-icon icon="mdi-clipboard-plus-outline" size="64" color="grey-lighten-2" />
        <div class="text-h6 text-medium-emphasis mt-4">Нет задач</div>
        <div class="text-body-2 text-medium-emphasis mt-1">Создайте первую задачу</div>
        <v-btn color="primary" class="mt-4" prepend-icon="mdi-plus" @click="openNewTask">Новая задача</v-btn>
      </div>
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
              @click="editGeneralTask(gt)"
            >
              <div class="d-flex align-center ga-1 mb-1">
                <v-chip :color="PRIORITY_COLOR[gt.priority] || 'grey'" size="x-small" variant="flat">{{ PRIORITY_LABEL[gt.priority] || gt.priority }}</v-chip>
                <v-chip v-if="gt.category" size="x-small" variant="outlined">{{ gt.category }}</v-chip>
                <v-chip v-if="gt.parent_task_id" size="x-small" variant="tonal" color="indigo" title="Подзадача">
                  <v-icon icon="mdi-subdirectory-arrow-right" size="10" class="mr-1" />Подзадача
                </v-chip>
                <v-spacer />
                <v-chip v-if="gt.subtask_count" size="x-small" variant="tonal" color="teal" :title="`${gt.subtask_count} делегировано`">
                  <v-icon icon="mdi-sitemap-outline" size="10" class="mr-1" />{{ gt.subtask_count }}
                </v-chip>
                <v-chip v-if="gt.comment_count" size="x-small" variant="tonal" color="blue-grey">
                  <v-icon icon="mdi-comment-text-outline" size="10" class="mr-1" />{{ gt.comment_count }}
                </v-chip>
              </div>
              <div class="kanban-card-title">{{ gt.title }}</div>
              <div v-if="gt.description" class="kanban-card-meta" style="font-size:11px;opacity:.7">{{ gt.description.length > 80 ? gt.description.slice(0,80)+'…' : gt.description }}</div>
              <!-- Last comment preview -->
              <div v-if="gt.last_comment" class="kanban-card-comment">
                <v-icon icon="mdi-comment-text-outline" size="12" class="mr-1" />
                <span><strong>{{ gt.last_comment_user }}:</strong> {{ gt.last_comment }}</span>
              </div>
              <div class="kanban-card-footer mt-1">
                <span v-if="gt.assigned_user_name" class="kanban-card-meta"><v-icon icon="mdi-account" size="12" class="mr-1"/>{{ gt.assigned_user_name }}</span>
                <span v-if="gt.created_by_name && gt.created_by_id !== gt.assigned_user_id" class="kanban-card-meta text-medium-emphasis" style="font-size:10px"><v-icon icon="mdi-account-arrow-right" size="10" class="mr-1"/>{{ gt.created_by_name }}</span>
                <v-chip v-if="gt.due_date" :color="deadlineColor(gt.due_date)" size="x-small" variant="tonal">{{ formatDate(gt.due_date.split('T')[0]) }}</v-chip>
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
          <v-text-field v-model="taskForm.title" label="Название *" variant="outlined" density="compact" class="mb-2" :readonly="isTaskReadonly" :bg-color="isTaskReadonly ? 'grey-lighten-4' : undefined" />
          <v-textarea v-model="taskForm.description" label="Описание" variant="outlined" density="compact" rows="2" class="mb-2" :readonly="isTaskReadonly" :bg-color="isTaskReadonly ? 'grey-lighten-4' : undefined" />
          <div class="d-flex ga-2 mb-2">
            <v-select v-model="taskForm.priority" :items="priorityItems" label="Приоритет" variant="outlined" density="compact" style="max-width:200px" :disabled="isTaskReadonly" />
            <v-combobox v-model="taskForm.category" :items="taskCategories" label="Категория" variant="outlined" density="compact" clearable :disabled="isTaskReadonly" />
          </div>
          <div class="d-flex ga-2 mb-2">
            <v-text-field v-model="taskForm.due_date" label="Срок исполнения" variant="outlined" density="compact" type="date" :min="todayStr" :rules="[dueDateRule]" :readonly="isTaskReadonly" :bg-color="isTaskReadonly ? 'grey-lighten-4' : undefined" />
            <v-select v-if="!isEmployee" v-model="taskForm.assigned_user_id" :items="userItems" label="Исполнитель" variant="outlined" density="compact" clearable item-title="text" item-value="value" :disabled="isTaskReadonly" />
          </div>

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
                :subtitle="`${st.assigned_user_name || '—'} · ${st.due_date ? st.due_date.split('T')[0] : 'без срока'}`"
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
              <v-chip v-if="taskComments.length" size="x-small" color="blue-grey" class="ml-2" variant="tonal">{{ taskComments.length }}</v-chip>
            </div>
            <div v-if="commentsLoading" class="d-flex justify-center py-4"><v-progress-circular indeterminate size="24" /></div>
            <div v-else ref="chatContainer" class="chat-container mb-2">
              <div v-for="c in taskComments" :key="c.id"
                class="chat-msg" :class="c.user_id === currentUserId ? 'chat-msg--mine' : 'chat-msg--other'">
                <div class="chat-msg-header">
                  <v-icon icon="mdi-account-circle" size="14" :color="c.user_id === currentUserId ? 'white' : 'primary'" class="mr-1" />
                  <span class="chat-msg-author">{{ c.user_name }}</span>
                  <span class="chat-msg-time">{{ formatDatetime(c.created_at) }}</span>
                  <v-btn v-if="c.user_id === currentUserId" icon="mdi-delete-outline" size="x-small" variant="text" density="compact"
                    :color="c.user_id === currentUserId ? 'white' : 'grey'" class="chat-msg-delete"
                    @click.stop="deleteComment(c.id)" title="Удалить" />
                </div>
                <div class="chat-msg-text" v-html="renderMentions(c.text)"></div>
              </div>
              <div v-if="taskComments.length === 0" class="text-caption text-medium-emphasis text-center pa-4">Начните обсуждение</div>
            </div>
            <!-- Mention dropdown -->
            <div v-if="mentionOpen" class="mention-dropdown">
              <div v-for="u in filteredMentionUsers" :key="u.value"
                class="mention-item" @mousedown.prevent="insertMention(u)">
                <v-icon icon="mdi-account" size="14" class="mr-1" />{{ u.text }}
              </div>
              <div v-if="filteredMentionUsers.length === 0" class="mention-item text-medium-emphasis">Нет совпадений</div>
            </div>
            <div class="d-flex ga-2 align-end">
              <v-textarea
                ref="commentInput"
                v-model="newCommentText"
                placeholder="Напишите сообщение... (@для упоминания)"
                variant="outlined" density="compact" rows="2" hide-details auto-grow
                style="flex:1"
                @keydown="onCommentKeydown"
                @input="onCommentInput"
              />
              <v-btn color="primary" size="small" :disabled="!newCommentText.trim()" :loading="commentSaving" @click="addComment">
                <v-icon icon="mdi-send" />
              </v-btn>
            </div>
          </template>
        </v-card-text>
        <v-card-actions>
          <v-btn v-if="editingTask && !isTaskReadonly" color="error" variant="text" @click="deleteGeneralTask">Удалить</v-btn>
          <v-btn v-if="editingTask" color="teal" variant="tonal" prepend-icon="mdi-account-arrow-right-outline" size="small" @click="openDelegateDialog">
            Делегировать
          </v-btn>
          <v-spacer />
          <v-btn variant="text" @click="closeTaskDialog">Отмена</v-btn>
          <v-btn color="primary" :disabled="!taskForm.title" @click="saveGeneralTask">{{ editingTask ? 'Сохранить' : 'Создать' }}</v-btn>
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
          <v-select v-model="delegateForm.assigned_user_id" :items="subordinateItems" label="Исполнитель (подчинённый) *" variant="outlined" density="compact" item-title="text" item-value="value" class="mb-2" />
          <v-switch v-model="delegateForm.import_to_parent" label="Показывать в родительской задаче" color="teal" density="compact" hide-details />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showDelegateDialog = false">Отмена</v-btn>
          <v-btn color="teal" :disabled="!delegateForm.title || !delegateForm.assigned_user_id" :loading="delegateSaving" @click="saveDelegate">Делегировать</v-btn>
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
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'

const router = useRouter()
const loading = ref(false)
const currentUserId = parseInt(localStorage.getItem('user_id') || '0')
const isEmployee = localStorage.getItem('user_role') === 'employee'
const chatContainer = ref<HTMLElement | null>(null)
const commentInput = ref<any>(null)
const viewMode = ref<'kanban' | 'list'>('kanban')
const showArchive = ref(false)
const tasks = ref<any[]>([])
const archiveTasks = ref<any[]>([])
const pendingApprovals = ref<any[]>([])

const activeTab = ref<'purchases' | 'general' | 'report'>('purchases')
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
const showTaskDialog = ref(false)
const editingTask = ref<any>(null)
const taskCategories = ref<string[]>([])
const userItems = ref<{text:string, value:number}[]>([])
const taskForm = ref({ title: '', description: '', priority: 'medium', due_date: '', assigned_user_id: null as number|null, category: '' })

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
const delegateForm = ref({ title: '', description: '', priority: 'medium', due_date: '', assigned_user_id: null as number|null, import_to_parent: true })

const isTaskReadonly = computed(() => {
  if (!editingTask.value) return false
  const uid = currentUserId
  const t = editingTask.value
  // Readonly if: I am the assignee but NOT the creator
  return t.assigned_user_id === uid && t.created_by_id !== uid
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
  if (gt.status === 'done') return {}
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

function openNewTask() {
  editingTask.value = null
  taskForm.value = { title: '', description: '', priority: 'medium', due_date: '', assigned_user_id: null, category: '' }
  taskComments.value = []
  newCommentText.value = ''
  showTaskDialog.value = true
}

function editGeneralTask(t: any) {
  editingTask.value = t
  taskForm.value = {
    title: t.title, description: t.description || '', priority: t.priority,
    due_date: t.due_date ? t.due_date.split('T')[0] : '',
    assigned_user_id: t.assigned_user_id, category: t.category || '',
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
    assigned_user_id: null,
    import_to_parent: true,
  }
  showDelegateDialog.value = true
}

async function saveDelegate() {
  if (!editingTask.value || !delegateForm.value.assigned_user_id) return
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

function closeTaskDialog() {
  showTaskDialog.value = false
  editingTask.value = null
  taskComments.value = []
  taskSubtasks.value = []
}

async function loadComments(taskId: number) {
  commentsLoading.value = true
  try {
    taskComments.value = await apiFetch<any[]>(`/tasks/${taskId}/comments`)
    await nextTick()
    scrollChatToBottom()
  } catch { taskComments.value = [] }
  finally { commentsLoading.value = false }
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

const filteredMentionUsers = computed(() => {
  const q = mentionQuery.value.toLowerCase()
  return userItems.value.filter(u => u.text.toLowerCase().includes(q)).slice(0, 6)
})

function onCommentInput() {
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
  // Ctrl+Enter to send
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    addComment()
  }
}

function insertMention(user: { text: string; value: number }) {
  const text = newCommentText.value
  const atIdx = text.lastIndexOf('@')
  if (atIdx >= 0) {
    newCommentText.value = text.slice(0, atIdx) + `@${user.text} `
  }
  mentionOpen.value = false
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
  if (!body.assigned_user_id) delete body.assigned_user_id
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

async function load() {
  loading.value = true
  try {
    const [active, archived] = await Promise.all([
      apiFetch<any[]>('/purchases/my-tasks'),
      apiFetch<any[]>('/purchases/my-tasks?include_archive=true'),
    ])
    tasks.value = active.filter(t => t.status !== 'paid')
    archiveTasks.value = archived.filter(t => t.status === 'paid')
  } catch (e) { console.error('Load tasks error:', e) }
  finally { loading.value = false }
  // Load pending approvals
  try { pendingApprovals.value = await apiFetch<any[]>('/approvals/my-pending') }
  catch { pendingApprovals.value = [] }
  // Load general tasks
  try {
    generalTasks.value = await apiFetch<any[]>('/tasks/my')
    taskCategories.value = await apiFetch<string[]>('/tasks/categories')
  } catch { generalTasks.value = [] }
  // Load users for assignment
  try {
    const users = await apiFetch<any[]>('/users/')
    userItems.value = users.map(u => ({ text: u.full_name || u.username, value: u.id }))
  } catch { userItems.value = [] }
  // Load departments
  try { departments.value = await apiFetch<string[]>('/tasks/departments') }
  catch { departments.value = [] }
}

onMounted(load)
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
</style>
