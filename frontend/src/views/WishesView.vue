<template>
  <v-container fluid class="pa-4">
    <!-- Header -->
    <div class="d-flex align-center mb-4 flex-wrap" style="gap:12px">
      <div>
        <h1 class="text-h5 font-weight-bold">Заявки</h1>
        <span class="text-body-2 text-medium-emphasis">
          {{ activeTab === 'my' ? 'Мои заявки' : activeTab === 'incoming' ? 'На согласование мне' : 'Заявки сотрудников' }}
        </span>
      </div>
      <v-spacer />
      <v-btn variant="tonal" color="primary" size="small" prepend-icon="mdi-refresh" :loading="loading" @click="reloadActiveTab">
        Обновить
      </v-btn>
    </div>

    <!-- Tabs (visible to all authenticated users) -->
    <v-tabs v-model="activeTab" class="mb-4">
      <v-tab value="my">Мои заявки</v-tab>
      <v-tab value="incoming">На согласование мне</v-tab>
      <v-tab v-if="isManagerOrAdmin" value="all">Заявки сотрудников</v-tab>
    </v-tabs>

    <!-- ── FILTER PANEL (общий для всех табов) ── -->
    <v-card variant="outlined" class="mb-4">
      <v-card-text class="py-3">
        <div class="d-flex flex-wrap align-center" style="gap:12px">
          <v-autocomplete
            v-model="filterCreatorId"
            :items="users"
            item-title="full_name"
            item-value="id"
            label="От кого"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:200px;max-width:240px"
          />
          <v-autocomplete
            v-model="filterAssignedToId"
            :items="users"
            item-title="full_name"
            item-value="id"
            label="Кому"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:200px;max-width:240px"
          />
          <v-text-field
            v-model="filterCreatedFrom"
            type="date"
            label="Создано с"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:150px;max-width:180px"
          />
          <v-text-field
            v-model="filterCreatedTo"
            type="date"
            label="Создано по"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:150px;max-width:180px"
          />
          <v-text-field
            v-model="filterDeadlineFrom"
            type="date"
            label="Срок с"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:150px;max-width:180px"
          />
          <v-text-field
            v-model="filterDeadlineTo"
            type="date"
            label="Срок по"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:150px;max-width:180px"
          />
          <v-btn variant="tonal" size="small" prepend-icon="mdi-filter-off" @click="resetFilters">
            Очистить фильтры
          </v-btn>
        </div>
      </v-card-text>
    </v-card>

    <!-- ── MY WISHES TAB ── -->
    <div v-if="activeTab === 'my'">
      <v-data-table
        v-resizable-columns="'wishes-my'"
        :headers="wishHeaders"
        :items="myWishesFiltered"
        :loading="loading"
        density="compact"
        hover
        items-per-page="25"
        :items-per-page-options="[25, 50, 100, -1]"
        @click:row="(_, { item }) => openEditDialog(item)"
      >
        <!-- B7: column header menus -->
        <template #header.status="{ column }">
          <ColumnHeaderMenu col-key="status" :title="column.title" col-type="enum"
            :items="Object.keys(statusLabel)"
            :item-labels="statusLabel"
            :model-value="colFilters.status"
            :sort-by="colSort.status"
            @update:model-value="v => colFilters.status = v"
            @sort="dir => colSort.status = dir" />
        </template>
        <template #header.title_col="{ column }">
          <ColumnHeaderMenu col-key="title_col" :title="column.title" col-type="text"
            :model-value="colFilters.title_col"
            :sort-by="colSort.title_col"
            @update:model-value="v => colFilters.title_col = v"
            @sort="dir => colSort.title_col = dir" />
        </template>
        <template #header.creator_name="{ column }">
          <ColumnHeaderMenu col-key="creator_name" :title="column.title" col-type="text"
            :model-value="colFilters.creator_name"
            :sort-by="colSort.creator_name"
            @update:model-value="v => colFilters.creator_name = v"
            @sort="dir => colSort.creator_name = dir" />
        </template>
        <template #header.assigned_to_name="{ column }">
          <ColumnHeaderMenu col-key="assigned_to_name" :title="column.title" col-type="text"
            :model-value="colFilters.assigned_to_name"
            :sort-by="colSort.assigned_to_name"
            @update:model-value="v => colFilters.assigned_to_name = v"
            @sort="dir => colSort.assigned_to_name = dir" />
        </template>
        <template #header.created_at="{ column }">
          <ColumnHeaderMenu col-key="created_at" :title="column.title" col-type="date"
            :model-value="colFilters.created_at"
            :sort-by="colSort.created_at"
            @update:model-value="v => colFilters.created_at = v"
            @sort="dir => colSort.created_at = dir" />
        </template>
        <template #header.desired_date="{ column }">
          <ColumnHeaderMenu col-key="desired_date" :title="column.title" col-type="date"
            :model-value="colFilters.desired_date"
            :sort-by="colSort.desired_date"
            @update:model-value="v => colFilters.desired_date = v"
            @sort="dir => colSort.desired_date = dir" />
        </template>
        <template #header.executor_name="{ column }">
          <ColumnHeaderMenu col-key="executor_name" :title="column.title" col-type="text"
            :model-value="colFilters.executor_name"
            :sort-by="colSort.executor_name"
            @update:model-value="v => colFilters.executor_name = v"
            @sort="dir => colSort.executor_name = dir" />
        </template>
        <template #header.execution_deadline="{ column }">
          <ColumnHeaderMenu col-key="execution_deadline" :title="column.title" col-type="date"
            :model-value="colFilters.execution_deadline"
            :sort-by="colSort.execution_deadline"
            @update:model-value="v => colFilters.execution_deadline = v"
            @sort="dir => colSort.execution_deadline = dir" />
        </template>
        <template #item.status="{ item }">
          <v-chip :color="statusColor[item.status]" size="small" variant="tonal">
            {{ statusLabel[item.status] }}
          </v-chip>
        </template>
        <template #item.title_col="{ item }">
          <div class="font-weight-medium">{{ item.title }}</div>
          <div class="text-caption text-medium-emphasis">
            <span v-if="item.items_count">Позиций: <b>{{ item.items_count }}</b></span>
            <span v-if="item.items_count && item.total_amount"> · </span>
            <span v-if="item.total_amount">НМЦК: <b>{{ formatPrice(item.total_amount) }}</b></span>
          </div>
        </template>
        <template #item.creator_name="{ item }">
          {{ item.creator_name || '—' }}
        </template>
        <template #item.assigned_to_name="{ item }">
          {{ item.assigned_to_name || '—' }}
        </template>
        <template #item.event_name="{ item }">
          {{ item.event_name || '—' }}
        </template>
        <template #header.event_name="{ column }">
          <ColumnHeaderMenu col-key="event_name" :title="column.title" col-type="text"
            :model-value="colFilters.event_name"
            :sort-by="colSort.event_name"
            @update:model-value="v => colFilters.event_name = v"
            @sort="dir => colSort.event_name = dir" />
        </template>
        <template #item.created_at="{ item }">
          {{ formatDate(item.created_at) }}
        </template>
        <template #item.desired_date="{ item }">
          {{ item.desired_date ? formatDate(item.desired_date) : '—' }}
        </template>
        <template #item.executor_name="{ item }">
          {{ item.executor_name || '—' }}
        </template>
        <template #item.execution_deadline="{ item }">
          {{ item.execution_deadline ? formatDate(item.execution_deadline) : '—' }}
        </template>
        <template #item.actions="{ item }">
          <div class="d-flex align-center" style="gap:4px" @click.stop>
            <template v-if="item.status === 'draft'">
              <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" @click="openEditDialog(item)" />
              <v-btn
                icon="mdi-send"
                size="x-small"
                variant="text"
                color="success"
                :loading="submittingId === item.id"
                @click="submitWish(item)"
              />
              <v-btn
                icon="mdi-delete-outline"
                size="x-small"
                variant="text"
                color="error"
                :loading="deletingId === item.id"
                @click="deleteWish(item)"
              />
            </template>
            <v-btn
              v-else-if="item.status === 'converted' && item.purchase_id"
              size="x-small"
              variant="tonal"
              color="purple"
              prepend-icon="mdi-cart-arrow-right"
              @click="$router.push(`/orders/${item.purchase_id}/edit`)"
            >
              Закупка
            </v-btn>
          </div>
        </template>
        <template #no-data>
          <div class="text-center py-10">
            <v-icon icon="mdi-hand-heart-outline" size="48" color="grey-lighten-1" class="mb-3" />
            <div class="text-medium-emphasis">Нет заявок</div>
          </div>
        </template>
      </v-data-table>

      <!-- FAB to create new wish -->
      <v-btn
        icon="mdi-plus"
        color="primary"
        size="large"
        style="position:fixed;bottom:32px;right:32px;z-index:100"
        elevation="4"
        @click="openCreateDialog"
      />
    </div>

    <!-- ── INCOMING FOR APPROVAL TAB ── -->
    <div v-if="activeTab === 'incoming'">
      <v-data-table
        v-resizable-columns="'wishes-incoming'"
        :headers="wishHeaders"
        :items="incomingWishesFiltered"
        :loading="loadingIncoming"
        density="compact"
        hover
        items-per-page="25"
        :items-per-page-options="[25, 50, 100, -1]"
        @click:row="(_, { item }) => openEditDialog(item)"
      >
        <!-- B7: column header menus -->
        <template #header.status="{ column }">
          <ColumnHeaderMenu col-key="status" :title="column.title" col-type="enum"
            :items="Object.keys(statusLabel)"
            :item-labels="statusLabel"
            :model-value="colFilters.status"
            :sort-by="colSort.status"
            @update:model-value="v => colFilters.status = v"
            @sort="dir => colSort.status = dir" />
        </template>
        <template #header.title_col="{ column }">
          <ColumnHeaderMenu col-key="title_col" :title="column.title" col-type="text"
            :model-value="colFilters.title_col"
            :sort-by="colSort.title_col"
            @update:model-value="v => colFilters.title_col = v"
            @sort="dir => colSort.title_col = dir" />
        </template>
        <template #header.creator_name="{ column }">
          <ColumnHeaderMenu col-key="creator_name" :title="column.title" col-type="text"
            :model-value="colFilters.creator_name"
            :sort-by="colSort.creator_name"
            @update:model-value="v => colFilters.creator_name = v"
            @sort="dir => colSort.creator_name = dir" />
        </template>
        <template #header.assigned_to_name="{ column }">
          <ColumnHeaderMenu col-key="assigned_to_name" :title="column.title" col-type="text"
            :model-value="colFilters.assigned_to_name"
            :sort-by="colSort.assigned_to_name"
            @update:model-value="v => colFilters.assigned_to_name = v"
            @sort="dir => colSort.assigned_to_name = dir" />
        </template>
        <template #header.created_at="{ column }">
          <ColumnHeaderMenu col-key="created_at" :title="column.title" col-type="date"
            :model-value="colFilters.created_at"
            :sort-by="colSort.created_at"
            @update:model-value="v => colFilters.created_at = v"
            @sort="dir => colSort.created_at = dir" />
        </template>
        <template #header.desired_date="{ column }">
          <ColumnHeaderMenu col-key="desired_date" :title="column.title" col-type="date"
            :model-value="colFilters.desired_date"
            :sort-by="colSort.desired_date"
            @update:model-value="v => colFilters.desired_date = v"
            @sort="dir => colSort.desired_date = dir" />
        </template>
        <template #header.executor_name="{ column }">
          <ColumnHeaderMenu col-key="executor_name" :title="column.title" col-type="text"
            :model-value="colFilters.executor_name"
            :sort-by="colSort.executor_name"
            @update:model-value="v => colFilters.executor_name = v"
            @sort="dir => colSort.executor_name = dir" />
        </template>
        <template #header.execution_deadline="{ column }">
          <ColumnHeaderMenu col-key="execution_deadline" :title="column.title" col-type="date"
            :model-value="colFilters.execution_deadline"
            :sort-by="colSort.execution_deadline"
            @update:model-value="v => colFilters.execution_deadline = v"
            @sort="dir => colSort.execution_deadline = dir" />
        </template>
        <template #item.status="{ item }">
          <v-chip :color="statusColor[item.status]" size="small" variant="tonal">
            {{ statusLabel[item.status] }}
          </v-chip>
        </template>
        <template #item.title_col="{ item }">
          <div class="font-weight-medium">{{ item.title }}</div>
          <div class="text-caption text-medium-emphasis">
            <span v-if="item.items_count">Позиций: <b>{{ item.items_count }}</b></span>
            <span v-if="item.items_count && item.total_amount"> · </span>
            <span v-if="item.total_amount">НМЦК: <b>{{ formatPrice(item.total_amount) }}</b></span>
          </div>
        </template>
        <template #item.creator_name="{ item }">
          {{ item.creator_name || '—' }}
        </template>
        <template #item.assigned_to_name="{ item }">
          {{ item.assigned_to_name || '—' }}
        </template>
        <template #item.event_name="{ item }">
          {{ item.event_name || '—' }}
        </template>
        <template #header.event_name="{ column }">
          <ColumnHeaderMenu col-key="event_name" :title="column.title" col-type="text"
            :model-value="colFilters.event_name"
            :sort-by="colSort.event_name"
            @update:model-value="v => colFilters.event_name = v"
            @sort="dir => colSort.event_name = dir" />
        </template>
        <template #item.created_at="{ item }">
          {{ formatDate(item.created_at) }}
        </template>
        <template #item.desired_date="{ item }">
          {{ item.desired_date ? formatDate(item.desired_date) : '—' }}
        </template>
        <template #item.executor_name="{ item }">
          {{ item.executor_name || '—' }}
        </template>
        <template #item.execution_deadline="{ item }">
          {{ item.execution_deadline ? formatDate(item.execution_deadline) : '—' }}
        </template>
        <template #item.actions="{ item }">
          <div class="d-flex align-center" style="gap:4px" @click.stop>
            <template v-if="item.status === 'submitted'">
              <v-btn size="x-small" variant="tonal" color="primary" @click="openKanbanDialog(item)">
                Распределить
              </v-btn>
              <v-btn size="x-small" variant="tonal" color="success" :loading="approvingId === item.id" @click="approveWish(item)">
                Одобрить
              </v-btn>
              <v-btn size="x-small" variant="tonal" color="error" @click="openRejectDialog(item)">
                Отклонить
              </v-btn>
            </template>
          </div>
        </template>
        <template #no-data>
          <div class="text-center py-10">
            <v-icon icon="mdi-hand-heart-outline" size="48" color="grey-lighten-1" class="mb-3" />
            <div class="text-medium-emphasis">Нет заявок на согласование</div>
          </div>
        </template>
      </v-data-table>
    </div>

    <!-- ── ALL WISHES TAB (manager/admin) ── -->
    <div v-if="isManagerOrAdmin && activeTab === 'all'">
      <!-- Status filter chips -->
      <div class="d-flex flex-wrap ga-2 mb-4">
        <v-chip
          v-for="f in allFilters"
          :key="f.value"
          :color="allFilter === f.value ? 'primary' : undefined"
          :variant="allFilter === f.value ? 'flat' : 'outlined'"
          size="small"
          @click="allFilter = f.value; loadAllWishes()"
        >
          {{ f.label }}
        </v-chip>
      </div>

      <v-data-table
        v-resizable-columns="'wishes-all'"
        :headers="wishHeadersAll"
        :items="allWishesFiltered"
        :loading="loadingAll"
        density="compact"
        hover
        items-per-page="25"
        :items-per-page-options="[25, 50, 100, -1]"
        @click:row="(_, { item }) => openEditDialog(item)"
      >
        <!-- B7: column header menus -->
        <template #header.status="{ column }">
          <ColumnHeaderMenu col-key="status" :title="column.title" col-type="enum"
            :items="Object.keys(statusLabel)"
            :item-labels="statusLabel"
            :model-value="colFilters.status"
            :sort-by="colSort.status"
            @update:model-value="v => colFilters.status = v"
            @sort="dir => colSort.status = dir" />
        </template>
        <template #header.title_col="{ column }">
          <ColumnHeaderMenu col-key="title_col" :title="column.title" col-type="text"
            :model-value="colFilters.title_col"
            :sort-by="colSort.title_col"
            @update:model-value="v => colFilters.title_col = v"
            @sort="dir => colSort.title_col = dir" />
        </template>
        <template #header.creator_name="{ column }">
          <ColumnHeaderMenu col-key="creator_name" :title="column.title" col-type="text"
            :model-value="colFilters.creator_name"
            :sort-by="colSort.creator_name"
            @update:model-value="v => colFilters.creator_name = v"
            @sort="dir => colSort.creator_name = dir" />
        </template>
        <template #header.assigned_to_name="{ column }">
          <ColumnHeaderMenu col-key="assigned_to_name" :title="column.title" col-type="text"
            :model-value="colFilters.assigned_to_name"
            :sort-by="colSort.assigned_to_name"
            @update:model-value="v => colFilters.assigned_to_name = v"
            @sort="dir => colSort.assigned_to_name = dir" />
        </template>
        <template #header.created_at="{ column }">
          <ColumnHeaderMenu col-key="created_at" :title="column.title" col-type="date"
            :model-value="colFilters.created_at"
            :sort-by="colSort.created_at"
            @update:model-value="v => colFilters.created_at = v"
            @sort="dir => colSort.created_at = dir" />
        </template>
        <template #header.desired_date="{ column }">
          <ColumnHeaderMenu col-key="desired_date" :title="column.title" col-type="date"
            :model-value="colFilters.desired_date"
            :sort-by="colSort.desired_date"
            @update:model-value="v => colFilters.desired_date = v"
            @sort="dir => colSort.desired_date = dir" />
        </template>
        <template #header.executor_name="{ column }">
          <ColumnHeaderMenu col-key="executor_name" :title="column.title" col-type="text"
            :model-value="colFilters.executor_name"
            :sort-by="colSort.executor_name"
            @update:model-value="v => colFilters.executor_name = v"
            @sort="dir => colSort.executor_name = dir" />
        </template>
        <template #header.execution_deadline="{ column }">
          <ColumnHeaderMenu col-key="execution_deadline" :title="column.title" col-type="date"
            :model-value="colFilters.execution_deadline"
            :sort-by="colSort.execution_deadline"
            @update:model-value="v => colFilters.execution_deadline = v"
            @sort="dir => colSort.execution_deadline = dir" />
        </template>
        <template #item.status="{ item }">
          <v-chip :color="statusColor[item.status]" size="small" variant="tonal">
            {{ statusLabel[item.status] }}
          </v-chip>
        </template>
        <template #item.title_col="{ item }">
          <div class="font-weight-medium">{{ item.title }}</div>
          <div class="text-caption text-medium-emphasis">
            <span v-if="item.items_count">Позиций: <b>{{ item.items_count }}</b></span>
            <span v-if="item.items_count && item.total_amount"> · </span>
            <span v-if="item.total_amount">НМЦК: <b>{{ formatPrice(item.total_amount) }}</b></span>
          </div>
        </template>
        <template #item.creator_name="{ item }">
          {{ item.creator_name || '—' }}
        </template>
        <template #item.assigned_to_name="{ item }">
          {{ item.assigned_to_name || '—' }}
        </template>
        <template #item.event_name="{ item }">
          {{ item.event_name || '—' }}
        </template>
        <template #header.event_name="{ column }">
          <ColumnHeaderMenu col-key="event_name" :title="column.title" col-type="text"
            :model-value="colFilters.event_name"
            :sort-by="colSort.event_name"
            @update:model-value="v => colFilters.event_name = v"
            @sort="dir => colSort.event_name = dir" />
        </template>
        <template #item.created_at="{ item }">
          {{ formatDate(item.created_at) }}
        </template>
        <template #item.desired_date="{ item }">
          {{ item.desired_date ? formatDate(item.desired_date) : '—' }}
        </template>
        <template #item.executor_name="{ item }">
          {{ item.executor_name || '—' }}
        </template>
        <template #item.execution_deadline="{ item }">
          {{ item.execution_deadline ? formatDate(item.execution_deadline) : '—' }}
        </template>
        <template #item.actions="{ item }">
          <div class="d-flex align-center" style="gap:4px" @click.stop>
            <template v-if="item.status === 'submitted'">
              <v-btn size="x-small" variant="tonal" color="primary" @click="openKanbanDialog(item)">
                Распределить
              </v-btn>
              <v-btn size="x-small" variant="tonal" color="success" :loading="approvingId === item.id" @click="approveWish(item)">
                Одобрить
              </v-btn>
              <v-btn size="x-small" variant="tonal" color="error" @click="openRejectDialog(item)">
                Отклонить
              </v-btn>
            </template>
            <v-btn
              v-if="item.status === 'approved' && isAdmin"
              size="x-small"
              variant="flat"
              color="primary"
              @click="openConvertDialog(item)"
            >
              Закупку
            </v-btn>
            <v-btn
              v-if="item.status === 'converted' && item.purchase_id"
              size="x-small"
              variant="tonal"
              color="purple"
              @click="$router.push(`/orders/${item.purchase_id}/edit`)"
            >
              Перейти
            </v-btn>
          </div>
        </template>
        <template #no-data>
          <div class="text-center py-10">
            <v-icon icon="mdi-hand-heart-outline" size="48" color="grey-lighten-1" class="mb-3" />
            <div class="text-medium-emphasis">Нет заявок от подчинённых</div>
          </div>
        </template>
      </v-data-table>
    </div>

    <!-- ── CREATE/EDIT DIALOG ── -->
    <v-dialog v-model="wishDialog" max-width="1600" width="95vw" scrollable>
      <v-card>
        <v-card-title class="pa-4 pb-2">
          {{ editingWishId ? 'Редактировать заявку' : 'Новая заявка' }}
        </v-card-title>
        <!-- B6 — от кого/кому/дата/статус -->
        <v-card-subtitle v-if="editingWish" class="pa-4 pt-0 d-flex flex-wrap" style="gap:16px">
          <div><b>От кого:</b> {{ editingWish.creator_name || '—' }}</div>
          <div><b>Кому:</b> {{ editingWish.assigned_to_name || '—' }}</div>
          <div><b>Создано:</b> {{ formatDate(editingWish.created_at) }}</div>
          <div v-if="editingWish.status"><b>Статус:</b> {{ statusLabel[editingWish.status] || editingWish.status }}</div>
          <div v-if="editingWish.executor_name"><b>Исполнитель:</b> {{ editingWish.executor_name }}</div>
          <div v-if="editingWish.execution_deadline"><b>Срок исполнения:</b> {{ formatDate(editingWish.execution_deadline) }}</div>
        </v-card-subtitle>
        <v-card-text class="pa-4">
          <v-alert
            v-if="!isWishEditable && canAssigneeAct"
            type="warning"
            variant="tonal"
            density="compact"
            class="mb-3"
          >
            Вы согласующий. Проверьте позиции и используйте кнопки ниже — «Распределить и одобрить», «Быстрое одобрение» или «Отклонить».
          </v-alert>
          <v-alert
            v-else-if="!isWishEditable && isDialogCreator && wishForm.status === 'submitted'"
            type="info"
            variant="tonal"
            density="compact"
            class="mb-3"
          >
            Заявка отправлена на согласование — редактирование недоступно. Вернуть можно, только если согласующий отклонит её.
          </v-alert>
          <v-alert
            v-else-if="!isWishEditable"
            type="info"
            variant="tonal"
            density="compact"
            class="mb-3"
          >
            Заявка в статусе «{{ statusLabel[wishForm.status] || wishForm.status }}» — редактирование недоступно. Редактировать можно только черновик или отклонённую заявку.
          </v-alert>
          <v-form ref="wishFormRef" @submit.prevent>

            <!-- Section 1: Основная информация -->
            <v-card variant="outlined" class="mb-4">
              <v-card-title class="text-subtitle-1 pa-4 pb-2">
                <v-icon class="mr-2">mdi-information-outline</v-icon>Основная информация
              </v-card-title>
              <v-card-text class="pa-4 pt-2">
                <v-row dense>
                  <v-col cols="12">
                    <v-select
                      v-model="wishForm.subsidy_id"
                      :items="subsidies"
                      item-title="name"
                      item-value="id"
                      label="Субсидия *"
                      variant="outlined"
                      density="compact"
                      :rules="[v => !!v || 'Выберите субсидию']"
                      clearable
                      :readonly="!isWishEditable"
                      @update:model-value="onSubsidyChange"
                    />
                  </v-col>
                  <v-col cols="12" md="4">
                    <v-select
                      v-model="selectedFeo1"
                      :items="feoLevel1"
                      item-title="name"
                      item-value="id"
                      label="Категория ФЭО (ур.1)"
                      variant="outlined"
                      density="compact"
                      clearable
                      :disabled="!wishForm.subsidy_id"
                      :readonly="!isWishEditable && !canAssigneeAct"
                      @update:model-value="onFeo1Change"
                    />
                  </v-col>
                  <v-col cols="12" md="4">
                    <v-select
                      v-model="selectedFeo2"
                      :items="feoLevel2"
                      item-title="name"
                      item-value="id"
                      label="Категория ФЭО (ур.2)"
                      variant="outlined"
                      density="compact"
                      clearable
                      :disabled="!selectedFeo1"
                      :readonly="!isWishEditable && !canAssigneeAct"
                      @update:model-value="onFeo2Change"
                    />
                  </v-col>
                  <v-col cols="12" md="4">
                    <v-select
                      v-model="selectedFeo3"
                      :items="feoLevel3"
                      item-title="name"
                      item-value="id"
                      label="Категория ФЭО (ур.3)"
                      variant="outlined"
                      density="compact"
                      clearable
                      :disabled="!selectedFeo2"
                      :readonly="!isWishEditable && !canAssigneeAct"
                    />
                  </v-col>
                  <v-col cols="12">
                    <v-autocomplete
                      v-model="wishForm.event_id"
                      :items="eventsForSubsidy"
                      item-title="name"
                      item-value="id"
                      label="Мероприятие"
                      variant="outlined"
                      density="compact"
                      clearable
                      :disabled="!wishForm.subsidy_id"
                      :readonly="!isWishEditable && !canAssigneeAct"
                      hint="Связать заявку с конкретным мероприятием субсидии"
                      persistent-hint
                    />
                  </v-col>
                  <v-col cols="12">
                    <v-autocomplete
                      v-model="wishForm.assigned_to"
                      :items="orgUsers"
                      item-title="full_name"
                      item-value="id"
                      label="На чьё имя заявка"
                      variant="outlined"
                      density="compact"
                      clearable
                      :disabled="!wishForm.subsidy_id"
                      :readonly="!isWishEditable"
                      hint="Сотрудник, на имя которого составляется заявка"
                      persistent-hint
                    >
                      <template #item="{ item, props: itemProps }">
                        <v-list-item v-bind="itemProps">
                          <template #title>{{ item.raw.full_name }}</template>
                          <template #subtitle>{{ resolveUserPosition(item.raw) || '—' }}</template>
                        </v-list-item>
                      </template>
                      <template #selection="{ item }">
                        {{ item.raw.full_name }}<span v-if="resolveUserPosition(item.raw)" class="text-caption text-medium-emphasis ml-2">— {{ resolveUserPosition(item.raw) }}</span>
                      </template>
                    </v-autocomplete>
                  </v-col>
                </v-row>
              </v-card-text>
            </v-card>

            <!-- Section: Принудительная смена статуса (только superadmin/account_owner) -->
            <v-card v-if="isSaas && editingWishId" variant="outlined" class="mb-4" color="red-lighten-5">
              <v-card-title class="text-subtitle-1 pa-4 pb-2">
                <v-icon class="mr-2" color="red-darken-2">mdi-shield-crown</v-icon>Принудительная смена статуса (SaaS-admin)
              </v-card-title>
              <v-card-text class="pa-4 pt-2">
                <v-row dense align="center">
                  <v-col cols="12" md="8">
                    <v-select
                      v-model="forceStatusValue"
                      :items="[
                        { value: 'draft', title: 'Черновик' },
                        { value: 'submitted', title: 'Отправлена' },
                        { value: 'approved', title: 'Одобрена' },
                        { value: 'rejected', title: 'Отклонена' },
                        { value: 'converted', title: 'Конвертирована' },
                      ]"
                      label="Новый статус"
                      variant="outlined"
                      density="compact"
                      hide-details
                    />
                  </v-col>
                  <v-col cols="12" md="4">
                    <v-btn color="red-darken-2" variant="flat" block prepend-icon="mdi-flash" :loading="forcingStatus" @click="forceStatus">
                      Применить
                    </v-btn>
                  </v-col>
                </v-row>
                <div class="text-caption text-medium-emphasis mt-2">
                  Минуя все workflow-проверки. Доступно только SaaS-роли.
                </div>
              </v-card-text>
            </v-card>

            <!-- Section: На исполнение (видна согласующему) -->
            <v-card v-if="canAssigneeAct || (editingWish && editingWish.status === 'approved' && (isDialogAssignee || isAdmin))" variant="outlined" class="mb-4" color="amber-lighten-5">
              <v-card-title class="text-subtitle-1 pa-4 pb-2">
                <v-icon class="mr-2" color="amber-darken-3">mdi-account-clock</v-icon>На исполнение
              </v-card-title>
              <v-card-text class="pa-4 pt-2">
                <v-row dense>
                  <v-col cols="12" md="6">
                    <v-autocomplete
                      v-model="wishForm.executor_id"
                      :items="orgUsers"
                      item-title="full_name"
                      item-value="id"
                      label="Исполнитель"
                      variant="outlined"
                      density="compact"
                      clearable
                      hint="Кому назначено фактическое исполнение"
                      persistent-hint
                    >
                      <template #item="{ item, props: itemProps }">
                        <v-list-item v-bind="itemProps">
                          <template #title>{{ item.raw.full_name }}</template>
                          <template #subtitle>{{ resolveUserPosition(item.raw) || '—' }}</template>
                        </v-list-item>
                      </template>
                      <template #selection="{ item }">
                        {{ item.raw.full_name }}<span v-if="resolveUserPosition(item.raw)" class="text-caption text-medium-emphasis ml-2">— {{ resolveUserPosition(item.raw) }}</span>
                      </template>
                    </v-autocomplete>
                  </v-col>
                  <v-col cols="12" md="6">
                    <v-text-field
                      v-model="wishForm.execution_deadline"
                      label="Срок исполнения"
                      type="date"
                      variant="outlined"
                      density="compact"
                      clearable
                      hint="К какому числу должно быть исполнено"
                      persistent-hint
                    />
                  </v-col>
                  <v-col cols="12">
                    <v-autocomplete
                      v-model="wishForm.event_id"
                      :items="eventsForSubsidy"
                      item-title="name"
                      item-value="id"
                      label="Мероприятие"
                      variant="outlined"
                      density="compact"
                      clearable
                      hint="Связать с конкретным мероприятием (можно изменить тут даже после одобрения)"
                      persistent-hint
                    />
                  </v-col>
                  <v-col cols="12">
                    <v-btn color="amber-darken-3" variant="flat" prepend-icon="mdi-content-save" :loading="savingExecution" @click="saveExecution">
                      Сохранить исполнителя / срок / мероприятие
                    </v-btn>
                  </v-col>
                </v-row>
              </v-card-text>
            </v-card>

            <!-- Section 2: Позиции -->
            <v-card variant="outlined" class="mb-4">
              <v-card-title class="text-subtitle-1 pa-4 pb-2">
                <v-icon class="mr-2">mdi-format-list-numbered</v-icon>Позиции
              </v-card-title>
              <v-card-text class="pa-4 pt-2">
                <PurchaseItemsEditor
                  v-model="wishForm.items"
                  item-shape="purchase"
                  :purchase-id="null"
                  :default-unit="'шт.'"
                  :default-country="'РФ'"
                  :allowed-item-types="['товар','услуга','работа']"
                  :supports-excel-import="true"
                  :supports-smart-import="true"
                  :supports-full-product-dialog="true"
                  :supports-photo-upload="true"
                  :readonly="!isWishEditable"
                />
              </v-card-text>
            </v-card>

            <!-- Section 3: Обоснование и сроки -->
            <v-card variant="outlined" class="mb-4">
              <v-card-title class="text-subtitle-1 pa-4 pb-2">
                <v-icon class="mr-2">mdi-text-box-check-outline</v-icon>Обоснование и сроки
              </v-card-title>
              <v-card-text class="pa-4 pt-2">
                <v-row dense>
                  <v-col cols="12">
                    <v-textarea
                      v-model="wishForm.justification"
                      label="Обоснование *"
                      variant="outlined"
                      density="compact"
                      rows="3"
                      :rules="[v => !!v || 'Обязательное поле']"
                      hint="Почему это необходимо для работы"
                      persistent-hint
                      :readonly="!isWishEditable"
                    />
                  </v-col>
                  <v-col cols="12" md="6">
                    <v-select
                      v-model="wishForm.priority"
                      :items="priorityOptions"
                      label="Приоритет"
                      variant="outlined"
                      density="compact"
                      :readonly="!isWishEditable"
                    />
                  </v-col>
                  <v-col cols="12" md="6">
                    <v-text-field
                      v-model="wishForm.desired_date"
                      label="Желаемый срок"
                      type="date"
                      variant="outlined"
                      density="compact"
                      :readonly="!isWishEditable"
                      :error-messages="serverFieldErrors.desired_date"
                      @update:model-value="serverFieldErrors.desired_date = ''"
                    />
                  </v-col>
                </v-row>
              </v-card-text>
            </v-card>

          </v-form>
        </v-card-text>

        <v-card-actions class="px-4 pb-4 flex-wrap">
          <v-btn variant="text" @click="wishDialog = false">Закрыть</v-btn>
          <v-spacer />
          <template v-if="isWishEditable">
            <v-btn color="grey" variant="tonal" :loading="saving" @click="saveWish(false)">
              Сохранить черновик
            </v-btn>
            <v-btn color="primary" variant="flat" :loading="saving" @click="saveWish(true)">
              Отправить на согласование
            </v-btn>
          </template>
          <template v-else-if="canAssigneeAct && editingWish">
            <v-btn color="error" variant="tonal" prepend-icon="mdi-close" @click="openRejectDialog(editingWish); wishDialog = false">
              Отклонить
            </v-btn>
            <v-btn color="success" variant="tonal" prepend-icon="mdi-check" :loading="approvingId === editingWish.id"
                   @click="approveWish(editingWish).then(() => wishDialog = false)">
              Быстрое одобрение
            </v-btn>
            <v-btn color="primary" variant="flat" prepend-icon="mdi-view-column-outline"
                   @click="openKanbanDialog(editingWish); wishDialog = false">
              Распределить и одобрить
            </v-btn>
          </template>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── KANBAN DISTRIBUTION DIALOG (Phase 13) ── -->
    <v-dialog v-model="kanbanDialog" max-width="1200" scrollable>
      <v-card>
        <v-card-title class="pa-4 pb-2">
          <v-icon class="mr-2" color="primary">mdi-view-column-outline</v-icon>
          Распределение позиций по закупкам
          <span v-if="kanbanWish" class="text-subtitle-2 text-medium-emphasis ml-3">
            · {{ kanbanWish.title || `Заявка #${kanbanWish.id}` }}
          </span>
        </v-card-title>
        <v-card-text class="pa-4">
          <WishDistributionKanban
            v-if="kanbanWish"
            :wish-id="kanbanWish.id"
            :items="kanbanItems"
            :readonly="kanbanWish.status === 'approved'"
            @approved="onKanbanApproved"
            @cancel="kanbanDialog = false"
            @error="(m) => showSnack(m, 'error')"
          />
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- ── REJECT DIALOG ── -->
    <v-dialog v-model="rejectDialog" max-width="480">
      <v-card>
        <v-card-title class="pa-4 pb-2">Отклонить заявку</v-card-title>
        <v-card-text class="pa-4">
          <v-textarea
            v-model="rejectionReason"
            label="Причина отклонения *"
            variant="outlined"
            density="compact"
            rows="4"
            :rules="[v => !!v || 'Укажите причину']"
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="rejectDialog = false">Отмена</v-btn>
          <v-btn variant="flat" color="error" :loading="rejectingWish" :disabled="!rejectionReason.trim()" @click="rejectWish">
            Отклонить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── CONVERT DIALOG ── -->
    <v-dialog v-model="convertDialog" max-width="540">
      <v-card>
        <v-card-title class="pa-4 pb-2">Создать закупку из заявки</v-card-title>
        <v-card-text class="pa-4">
          <div class="mb-4 pa-3 bg-grey-lighten-4 rounded">
            <div class="text-subtitle-2 font-weight-bold mb-1">Исходная заявка</div>
            <div class="text-body-2">{{ convertingWish?.title }}</div>
            <div class="text-caption text-medium-emphasis mt-1">
              <span v-if="convertingWish?.total_amount">НМЦК: {{ formatPrice(convertingWish.total_amount) }}</span>
            </div>
          </div>
          <v-row dense class="mb-3">
            <v-col cols="6">
              <v-text-field
                v-model.number="convertForm.approved_quantity"
                label="Утверждённое количество"
                type="number"
                variant="outlined"
                density="compact"
                min="0"
              />
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model.number="convertForm.approved_price"
                label="Утверждённая цена (₽)"
                type="number"
                variant="outlined"
                density="compact"
                min="0"
              />
            </v-col>
          </v-row>
          <v-select
            v-model="convertForm.subsidy_id"
            :items="subsidies"
            item-title="name"
            item-value="id"
            label="Субсидия (опционально)"
            variant="outlined"
            density="compact"
            clearable
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="convertDialog = false">Отмена</v-btn>
          <v-btn variant="flat" color="primary" :loading="convertingWishLoading" @click="convertWish">
            Создать закупку
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snackbar" :color="snackbarColor" :timeout="snackbarColor === 'error' ? -1 : 4000" location="bottom right">
      {{ snackbarText }}
      <template #actions>
        <v-btn variant="text" @click="snackbar = false">Закрыть</v-btn>
      </template>
    </v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import PurchaseItemsEditor from '@/components/PurchaseItemsEditor.vue'
import WishDistributionKanban from '@/components/WishDistributionKanban.vue'
import ColumnHeaderMenu from '@/components/ColumnHeaderMenu.vue'

const router = useRouter()

interface WishItem {
  item_name: string
  item_type: string
  quantity: number
  unit: string
  unit_price: number
  total_price: number
  country_origin: string
}

interface Wish {
  id: number
  org_id: number
  title: string
  subsidy_id?: number
  subsidy_name?: string
  feo_category_id?: number
  assigned_to?: number
  assigned_to_name?: string
  priority?: string
  desired_date?: string
  justification?: string
  status: 'draft' | 'submitted' | 'approved' | 'rejected' | 'converted'
  rejection_reason?: string
  created_by: number
  creator_name?: string
  approved_by?: number
  approver_name?: string
  purchase_id?: number
  items_count?: number
  total_amount?: number
  created_at: string
  updated_at: string
  event_id?: number | null
  event_name?: string | null
  assignee_name?: string
  executor_id?: number | null
  executor_name?: string | null
  execution_deadline?: string | null
}

interface Subsidy {
  id: number
  name: string
  org_id?: number
}

interface FeoCategory {
  id: number
  name: string
  subsidy_id?: number
  parent_id?: number | null
}

interface EventItem { id: number; name: string; subsidy_id: number; is_active?: boolean }

interface User {
  id: number
  full_name: string
  org_id?: number
}

// Role detection
const userRole = localStorage.getItem('user_role') || ''
const currentUserId = Number(localStorage.getItem('user_id') || '0')

const ADMIN_ROLES = ['superadmin', 'account_owner', 'org_admin', 'admin']
const MANAGER_ROLES = ['superadmin', 'account_owner', 'org_admin', 'admin', 'manager']

const isAdmin = computed(() => ADMIN_ROLES.includes(userRole))
const isManagerOrAdmin = computed(() => MANAGER_ROLES.includes(userRole))
const isSaas = computed(() => ['superadmin', 'account_owner'].includes(userRole))

// Status display
const statusColor: Record<string, string> = {
  draft: 'grey',
  submitted: 'blue',
  approved: 'green',
  rejected: 'red',
  converted: 'purple',
}
const statusLabel: Record<string, string> = {
  draft: 'Черновик',
  submitted: 'Отправлена',
  approved: 'Одобрена',
  rejected: 'Отклонена',
  converted: 'Передано в исполнение',
}

// Priority
const priorityColor: Record<string, string> = {
  low: 'grey',
  medium: 'blue',
  high: 'orange',
  urgent: 'red',
}
const priorityLabel: Record<string, string> = {
  low: 'Низкий',
  medium: 'Средний',
  high: 'Высокий',
  urgent: 'Срочный',
}

const priorityOptions = [
  { title: 'Низкий', value: 'low' },
  { title: 'Средний', value: 'medium' },
  { title: 'Высокий', value: 'high' },
  { title: 'Срочный', value: 'urgent' },
]

// Table headers
const wishHeaders = [
  { title: 'Статус', key: 'status', width: 110, sortable: true },
  { title: 'Заявка', key: 'title_col', sortable: false },
  { title: 'От кого', key: 'creator_name', width: 180, sortable: true },
  { title: 'На чьё имя', key: 'assigned_to_name', width: 180, sortable: true },
  { title: 'Мероприятие', key: 'event_name', width: 180, sortable: true },
  { title: 'Создано', key: 'created_at', width: 110, sortable: true },
  { title: 'Срок', key: 'desired_date', width: 110, sortable: true },
  { title: 'Исполнитель', key: 'executor_name', width: 160, sortable: true },
  { title: 'Срок исп.', key: 'execution_deadline', width: 110, sortable: true },
  { title: 'Действия', key: 'actions', width: 160, sortable: false },
]

const wishHeadersAll = wishHeaders

// Filter state
const filterCreatorId = ref<number | null>(null)
const filterAssignedToId = ref<number | null>(null)
const filterCreatedFrom = ref('')
const filterCreatedTo = ref('')
const filterDeadlineFrom = ref('')
const filterDeadlineTo = ref('')

function buildFilterParams(extra: Record<string, any> = {}) {
  const params = new URLSearchParams()
  if (filterCreatorId.value) params.set('creator_id', String(filterCreatorId.value))
  if (filterAssignedToId.value) params.set('assigned_to_id', String(filterAssignedToId.value))
  if (filterCreatedFrom.value) params.set('created_from', filterCreatedFrom.value)
  if (filterCreatedTo.value) params.set('created_to', filterCreatedTo.value)
  if (filterDeadlineFrom.value) params.set('deadline_from', filterDeadlineFrom.value)
  if (filterDeadlineTo.value) params.set('deadline_to', filterDeadlineTo.value)
  for (const [k, v] of Object.entries(extra)) {
    if (v !== undefined && v !== null && v !== '') params.set(k, String(v))
  }
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

function resetFilters() {
  filterCreatorId.value = null
  filterAssignedToId.value = null
  filterCreatedFrom.value = ''
  filterCreatedTo.value = ''
  filterDeadlineFrom.value = ''
  filterDeadlineTo.value = ''
}

// Debounced filter watcher
let filterTimer: any = null
watch(
  [filterCreatorId, filterAssignedToId, filterCreatedFrom, filterCreatedTo, filterDeadlineFrom, filterDeadlineTo],
  () => {
    clearTimeout(filterTimer)
    filterTimer = setTimeout(() => reloadActiveTab(), 300)
  }
)

// Tabs
const activeTab = ref('my')

// My wishes
const myWishes = ref<Wish[]>([])
const loading = ref(false)

// All wishes (manager/admin — subordinates)
const allWishes = ref<Wish[]>([])
const loadingAll = ref(false)
const allFilter = ref('submitted')

// Incoming for approval (assigned_to = me)
const incomingWishes = ref<Wish[]>([])
const loadingIncoming = ref(false)
const allFilters = [
  { value: 'all', label: 'Все' },
  { value: 'submitted', label: 'Отправленные' },
  { value: 'approved', label: 'Одобренные' },
  { value: 'rejected', label: 'Отклонённые' },
  { value: 'converted', label: 'Конвертированные' },
]

// Reference data
const subsidies = ref<Subsidy[]>([])
const allFeoCategories = ref<FeoCategory[]>([])
const users = ref<User[]>([])
const events = ref<EventItem[]>([])
const eventsForSubsidy = computed(() => {
  const filtered = wishForm.value.subsidy_id
    ? events.value.filter(e => e.subsidy_id === wishForm.value.subsidy_id && (e.is_active !== false))
    : []
  // Всегда включать текущий выбранный event (даже если deactivated или events.value ещё не загружен),
  // чтобы select показывал label, а не пустое поле, и при PUT event_id не «слетал».
  const selId = wishForm.value.event_id
  if (selId && !filtered.find(e => e.id === selId)) {
    const fromAll = events.value.find(e => e.id === selId)
    if (fromAll) {
      filtered.unshift(fromAll)
    } else if ((editingWish.value as any)?.event_name) {
      filtered.unshift({
        id: selId,
        name: (editingWish.value as any).event_name,
        subsidy_id: wishForm.value.subsidy_id || 0,
        is_active: true,
      })
    }
  }
  return filtered
})

// FEO cascading selects
const selectedFeo1 = ref<number | null>(null)
const selectedFeo2 = ref<number | null>(null)
const selectedFeo3 = ref<number | null>(null)

const feoLevel1 = computed(() =>
  wishForm.value.subsidy_id
    ? allFeoCategories.value.filter(c => c.subsidy_id === wishForm.value.subsidy_id && !c.parent_id)
    : []
)
const feoLevel2 = computed(() =>
  selectedFeo1.value
    ? allFeoCategories.value.filter(c => c.parent_id === selectedFeo1.value)
    : []
)
const feoLevel3 = computed(() =>
  selectedFeo2.value
    ? allFeoCategories.value.filter(c => c.parent_id === selectedFeo2.value)
    : []
)

const orgUsers = computed(() => {
  if (!wishForm.value.subsidy_id) return users.value
  const sub = subsidies.value.find(s => s.id === wishForm.value.subsidy_id)
  if (!sub || !sub.org_id) return users.value
  return users.value.filter(u => u.org_id === sub.org_id)
})

// Должность сотрудника: per-org → fallback на legacy User.position/department
function resolveUserPosition(u: any): string {
  if (!u) return ''
  const targetOrgId = subsidies.value.find(s => s.id === wishForm.value.subsidy_id)?.org_id
  if (targetOrgId && Array.isArray(u.organizations)) {
    const match = u.organizations.find((o: any) => o.org_id === targetOrgId || o.id === targetOrgId)
    if (match?.position) return match.position
  }
  return u.position || u.department || ''
}

// Create/edit dialog
const wishDialog = ref(false)
const editingWishId = ref<number | null>(null)
const editingWish = ref<Wish | null>(null)
const wishFormRef = ref<any>(null)
const saving = ref(false)
// Серверные ошибки валидации по полям: {desired_date: 'неверный формат даты'}.
// Биндим в :error-messages → Vuetify сам рисует красную подпись (стрелочка к полю).
const serverFieldErrors = ref<Record<string, string>>({})

const isWishEditable = computed(() =>
  !editingWishId.value || ['draft', 'rejected'].includes((wishForm.value as any).status || 'draft')
)

const isDialogAssignee = computed(() =>
  !!editingWish.value && editingWish.value.assigned_to === currentUserId
)
const isDialogCreator = computed(() =>
  !!editingWish.value && editingWish.value.created_by === currentUserId
)
const canAssigneeAct = computed(() =>
  !!editingWish.value
  && editingWish.value.status === 'submitted'
  && (isDialogAssignee.value || isAdmin.value)
)

const wishForm = ref({
  subsidy_id: null as number | null,
  feo_category_id: null as number | null,
  assigned_to: null as number | null,
  event_id: null as number | null,
  justification: '',
  priority: 'medium' as string,
  desired_date: '',
  items: [] as any[],
  status: 'draft' as string,
  executor_id: null as number | null,
  execution_deadline: '' as string,
})

// Items computed total
const totalNmck = computed(() =>
  wishForm.value.items.reduce((sum, i) => sum + (i.total_price || 0), 0)
)

function onSubsidyChange() {
  selectedFeo1.value = null
  selectedFeo2.value = null
  selectedFeo3.value = null
  wishForm.value.assigned_to = null
  wishForm.value.event_id = null
}

function onFeo1Change() {
  selectedFeo2.value = null
  selectedFeo3.value = null
}

function onFeo2Change() {
  selectedFeo3.value = null
}

// Submit
const submittingId = ref<number | null>(null)

// Delete
const deletingId = ref<number | null>(null)

// Reject dialog
const rejectDialog = ref(false)
const rejectingWish = ref(false)
const rejectionReason = ref('')
const rejectingWishItem = ref<Wish | null>(null)

// Convert dialog
const convertDialog = ref(false)
const convertingWishLoading = ref(false)
const convertingWish = ref<Wish | null>(null)
const convertForm = ref({
  approved_quantity: null as number | null,
  approved_price: null as number | null,
  subsidy_id: null as number | null,
})

// Approve
const approvingId = ref<number | null>(null)

// Kanban distribution dialog (Phase 13)
const kanbanDialog = ref(false)
const kanbanWish = ref<Wish | null>(null)
const kanbanItems = ref<any[]>([])

// Service note download (Phase 13 / D-07)
const downloadingServiceNoteId = ref<number | null>(null)

// Snackbar
const snackbar = ref(false)
const snackbarText = ref('')
const snackbarColor = ref('success')

function showSnack(text: string, color = 'success') {
  snackbarText.value = text
  snackbarColor.value = color
  snackbar.value = true
}

function formatPrice(price: number) {
  return price.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 })
}

function formatDate(dateStr: string) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

async function loadWishes() {
  loading.value = true
  try {
    myWishes.value = await apiFetch<Wish[]>('/wishes/' + buildFilterParams({ mine_only: true }))
  } catch (e: any) {
    showSnack(`Ошибка загрузки заявок: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
  } finally {
    loading.value = false
  }
}

async function loadAllWishes() {
  loadingAll.value = true
  try {
    const statusParam = allFilter.value && allFilter.value !== 'all' ? { status: allFilter.value } : {}
    allWishes.value = await apiFetch<Wish[]>('/wishes/' + buildFilterParams({ subordinates_only: true, ...statusParam }))
  } catch (e: any) {
    showSnack(`Ошибка загрузки заявок: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
  } finally {
    loadingAll.value = false
  }
}

async function loadIncoming() {
  loadingIncoming.value = true
  try {
    const data = await apiFetch<Wish[]>('/wishes/' + buildFilterParams({ assigned_to_me: true }))
    incomingWishes.value = data || []
  } catch (e: any) {
    showSnack(`Ошибка загрузки входящих заявок: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
    incomingWishes.value = []
  } finally {
    loadingIncoming.value = false
  }
}

async function reloadActiveTab() {
  if (activeTab.value === 'my') await loadWishes()
  else if (activeTab.value === 'incoming') await loadIncoming()
  else if (activeTab.value === 'all') await loadAllWishes()
}

function resetForm() {
  serverFieldErrors.value = {}
  wishForm.value = {
    subsidy_id: null,
    feo_category_id: null,
    assigned_to: null,
    event_id: null,
    justification: '',
    priority: 'medium',
    desired_date: '',
    items: [],
    status: 'draft',
    executor_id: null,
    execution_deadline: '',
  }
  selectedFeo1.value = null
  selectedFeo2.value = null
  selectedFeo3.value = null
}

function openCreateDialog() {
  editingWishId.value = null
  editingWish.value = null
  resetForm()
  wishDialog.value = true
}

async function openEditDialog(wish: Wish) {
  editingWishId.value = wish.id
  editingWish.value = wish
  resetForm()
  wishForm.value.subsidy_id = wish.subsidy_id ?? null
  wishForm.value.feo_category_id = wish.feo_category_id ?? null
  wishForm.value.assigned_to = wish.assigned_to ?? null
  wishForm.value.event_id = (wish as any).event_id ?? null
  wishForm.value.executor_id = (wish as any).executor_id ?? null
  wishForm.value.execution_deadline = (wish as any).execution_deadline ? String((wish as any).execution_deadline).slice(0, 10) : ''
  wishForm.value.justification = wish.justification || ''
  wishForm.value.priority = wish.priority || 'medium'
  wishForm.value.desired_date = wish.desired_date || ''
  wishForm.value.status = wish.status || 'draft'
  forceStatusValue.value = wish.status || 'draft'

  // B5 — Seed cascade selects from wish.feo_category_id by walking up parent_id
  if (wish.feo_category_id) {
    const chain: number[] = []
    let curId: number | null = wish.feo_category_id
    while (curId) {
      const node = allFeoCategories.value.find(c => c.id === curId)
      if (!node) break
      chain.unshift(node.id)
      curId = node.parent_id || null
    }
    selectedFeo1.value = chain[0] ?? null
    selectedFeo2.value = chain[1] ?? null
    selectedFeo3.value = chain[2] ?? null
  }

  let rawItems: any[] = []
  if (Array.isArray((wish as any).items) && (wish as any).items.length > 0) {
    rawItems = (wish as any).items
  } else {
    try {
      const fresh = await apiFetch<any>(`/wishes/${wish.id}`)
      if (Array.isArray(fresh?.items)) rawItems = fresh.items
    } catch {}
  }

  // Backfill product_id by matching item_name against catalog — handles legacy
  // wish_items saved before product_id was persisted on backend.
  const needsBackfill = rawItems.some((i: any) => !i.product_id && i.item_name)
  if (needsBackfill) {
    try {
      const products = await apiFetch<any[]>('/products/?limit=10000')
      const byName = new Map<string, any>(
        (products || []).map((p: any) => [(p.name || '').trim().toLowerCase(), p])
      )
      for (const it of rawItems) {
        if (!it.product_id && it.item_name) {
          const hit = byName.get(it.item_name.trim().toLowerCase())
          if (hit) it.product_id = hit.id
        }
      }
    } catch {}
  }

  wishForm.value.items = rawItems.map((i: any) => ({
    product_id: i.product_id ?? null,
    item_name: i.item_name || '',
    item_type: i.item_type || 'товар',
    quantity: i.quantity != null ? Number(i.quantity) : null,
    unit: i.unit || 'шт.',
    unit_price: i.unit_price != null ? Number(i.unit_price) : null,
    total_price: i.total_price != null ? Number(i.total_price) : null,
    country_origin: i.country_origin || 'РФ',
  })) as any
  wishDialog.value = true
}

// Superadmin: force-смена статуса
const forceStatusValue = ref<string>('draft')
const forcingStatus = ref(false)
async function forceStatus() {
  if (!editingWishId.value) { showSnack('Сначала откройте заявку', 'warning'); return }
  if (!confirm(`Принудительно установить статус «${forceStatusValue.value}»? Workflow-проверки будут пропущены.`)) return
  forcingStatus.value = true
  try {
    await apiFetch(`/wishes/${editingWishId.value}/status`, {
      method: 'POST',
      body: JSON.stringify({ status: forceStatusValue.value }),
    })
    showSnack(`Статус принудительно изменён на «${forceStatusValue.value}»`)
    wishDialog.value = false
    await reloadActiveTab()
  } catch (e: any) {
    showSnack(`Ошибка force-status: ${e?.message || e?.payload?.message || 'не удалось'}`, 'error')
  } finally {
    forcingStatus.value = false
  }
}

const savingExecution = ref(false)
async function saveExecution() {
  if (!editingWishId.value) { showSnack('Сначала сохраните заявку', 'warning'); return }
  savingExecution.value = true
  try {
    const body: any = {
      executor_id: wishForm.value.executor_id,
      execution_deadline: wishForm.value.execution_deadline || null,
      event_id: wishForm.value.event_id,
      feo_category_id: selectedFeo3.value || selectedFeo2.value || selectedFeo1.value || wishForm.value.feo_category_id,
    }
    await apiFetch(`/wishes/${editingWishId.value}/execution`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    })
    showSnack('Сохранено: исполнитель / срок / мероприятие / ФЭО')
    await reloadActiveTab()
  } catch (e: any) {
    showSnack(`Ошибка: ${e?.message || e?.payload?.message || 'не удалось сохранить'}`, 'error')
  } finally {
    savingExecution.value = false
  }
}

// TODO: B8 — нужен отдельный endpoint PATCH /wishes/{id}/feo для approver на submitted-заявке
async function saveWish(andSubmit = false) {
  // Черновик можно сохранить всегда — прерваться на любом этапе (даже 200 позиций,
  // часть не в каталоге). Валидацию формы требуем только при отправке на согласование.
  if (andSubmit) {
    const { valid } = await wishFormRef.value?.validate() ?? { valid: true }
    if (!valid) return
  }

  saving.value = true
  try {
    const feo = selectedFeo3.value || selectedFeo2.value || selectedFeo1.value
    // Заголовок: краткий и читаемый. При множестве позиций — первая + счётчик,
    // иначе склейка переполняет title (VARCHAR 500) и роняет создание заявки.
    const names = wishForm.value.items.map(i => i.item_name).filter(Boolean)
    let title = names.join(', ') || 'Новая заявка'
    if (title.length > 255) {
      title = names.length > 1
        ? `${names[0].slice(0, 120)} + ещё ${names.length - 1} поз.`
        : names[0].slice(0, 252) + '…'
    }
    const payload = {
      ...wishForm.value,
      feo_category_id: feo,
      title,
      items: wishForm.value.items.map(({ _selectedProduct, _photo_url, _description, _description_44fz, ...rest }) => rest),
    }

    if (editingWishId.value) {
      await apiFetch(`/wishes/${editingWishId.value}`, { method: 'PUT', body: JSON.stringify(payload) })
      showSnack('Заявка обновлена')
    } else {
      const created = await apiFetch<any>('/wishes/', { method: 'POST', body: JSON.stringify(payload) })
      if (andSubmit && created?.id) {
        await apiFetch(`/wishes/${created.id}/submit`, { method: 'POST' })
        showSnack('Заявка отправлена на согласование')
      } else {
        showSnack('Черновик сохранён')
      }
    }

    wishDialog.value = false
    await reloadActiveTab()
  } catch (e: any) {
    // Серверная валидация: backend шлёт {message, fields:[{field,label}]}.
    // Подсвечиваем проблемные поля и скроллим к первому — «стрелочка» вместо
    // технического дампа с именами переменных.
    const fields = e?.payload?.fields
    if (Array.isArray(fields) && fields.length) {
      serverFieldErrors.value = {}
      for (const f of fields) {
        serverFieldErrors.value[f.field] = e?.payload?.message?.includes('обязательно')
          ? 'Заполните это поле'
          : 'Проверьте значение'
      }
      await nextTick()
      document.querySelector('.v-overlay--active .v-input--error')
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
    const msg = e?.payload?.message || e?.message || 'неизвестная ошибка'
    showSnack(`Не удалось сохранить: ${msg}`, 'error')
  } finally {
    saving.value = false
  }
}

async function submitWish(wish: Wish) {
  submittingId.value = wish.id
  try {
    await apiFetch(`/wishes/${wish.id}/submit`, { method: 'POST' })
    showSnack('Заявка отправлена')
    await loadWishes()
  } catch (e: any) {
    showSnack(`Ошибка при отправке: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
  } finally {
    submittingId.value = null
  }
}

async function deleteWish(wish: Wish) {
  deletingId.value = wish.id
  try {
    await apiFetch(`/wishes/${wish.id}`, { method: 'DELETE' })
    showSnack('Заявка удалена')
    await loadWishes()
  } catch (e: any) {
    showSnack(`Ошибка при удалении: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
  } finally {
    deletingId.value = null
  }
}

async function approveWish(wish: Wish) {
  approvingId.value = wish.id
  try {
    await apiFetch(`/wishes/${wish.id}/approve`, { method: 'POST' })
    showSnack('Заявка одобрена')
    await reloadActiveTab()
  } catch (e: any) {
    showSnack(`Ошибка при одобрении: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
  } finally {
    approvingId.value = null
  }
}

// ── Kanban distribution (Phase 13) ─────────────────────────────────────
async function openKanbanDialog(wish: Wish) {
  kanbanWish.value = wish
  kanbanItems.value = []
  kanbanDialog.value = true
  try {
    const full = await apiFetch<Wish & { items?: any[] }>(`/wishes/${wish.id}`)
    const items: any[] = Array.isArray(full.items) ? full.items : []

    // Always fetch products — we need them for both id→category enrichment
    // AND name→id backfill for legacy wish_items without product_id.
    let products: any[] = []
    try { products = await apiFetch<any[]>('/products/?limit=10000') } catch {}
    const byId = new Map<number, any>(products.map((p: any) => [p.id, p]))
    const byName = new Map<string, any>(
      products.map((p: any) => [(p.name || '').trim().toLowerCase(), p])
    )

    kanbanItems.value = items.map((it: any) => {
      let prod = it.product_id ? byId.get(it.product_id) : null
      if (!prod && it.item_name) {
        prod = byName.get(it.item_name.trim().toLowerCase()) || null
      }
      return {
        ...it,
        product_id: it.product_id ?? prod?.id ?? null,
        _photo_url: (prod?.has_photo ? `/api/products/${prod.id}/photo` : (prod?.photo_url ?? prod?.photo_link)) ?? it._photo_url ?? null,
        _product_category: prod?.category || it._product_category || '',
      }
    })
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка загрузки заявки', 'error')
  }
}

async function onKanbanApproved(result: { purchase_ids: number[]; count: number }) {
  showSnack(`Одобрено. Создано закупок: ${result.count}`)
  kanbanDialog.value = false
  await reloadActiveTab()
}

// ── Service note download (Phase 13 / D-07) ────────────────────────────
async function downloadServiceNote(wish: Wish) {
  downloadingServiceNoteId.value = wish.id
  try {
    const token = localStorage.getItem('auth_token') || ''
    const resp = await fetch(`/api/wishes/${wish.id}/documents/service_note`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `service_note_wish_${wish.id}.docx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка скачивания служебной записки', 'error')
  } finally {
    downloadingServiceNoteId.value = null
  }
}

function openRejectDialog(wish: Wish) {
  rejectingWishItem.value = wish
  rejectionReason.value = ''
  rejectDialog.value = true
}

async function rejectWish() {
  if (!rejectionReason.value.trim() || !rejectingWishItem.value) return
  rejectingWish.value = true
  try {
    await apiFetch(`/wishes/${rejectingWishItem.value.id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ rejection_reason: rejectionReason.value }),
    })
    showSnack('Заявка отклонена')
    rejectDialog.value = false
    await reloadActiveTab()
  } catch (e: any) {
    showSnack(`Ошибка при отклонении: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
  } finally {
    rejectingWish.value = false
  }
}

async function openConvertDialog(wish: Wish) {
  convertingWish.value = wish
  // Pre-fill from items: sum quantities and total_prices
  let items: any[] = Array.isArray((wish as any).items) ? (wish as any).items : []
  if (items.length === 0) {
    try {
      const fresh = await apiFetch<any>(`/wishes/${wish.id}`)
      if (Array.isArray(fresh?.items)) items = fresh.items
    } catch {}
  }
  const sumQty = items.reduce((s, i) => s + Number(i.quantity || 0), 0)
  const sumPrice = items.reduce((s, i) => s + Number(i.total_price || 0), 0)
  convertForm.value = {
    approved_quantity: sumQty > 0 ? sumQty : (wish.quantity != null ? Number(wish.quantity) : null),
    approved_price: sumPrice > 0 ? sumPrice : (wish.total_amount ?? (wish.estimated_price != null ? Number(wish.estimated_price) : null)),
    subsidy_id: wish.subsidy_id ?? null,
  }
  convertDialog.value = true
}

async function convertWish() {
  if (!convertingWish.value) return
  convertingWishLoading.value = true
  try {
    const body: any = {}
    if (convertForm.value.approved_quantity != null) body.approved_quantity = convertForm.value.approved_quantity
    if (convertForm.value.approved_price != null) body.approved_price = convertForm.value.approved_price
    if (convertForm.value.subsidy_id != null) body.subsidy_id = convertForm.value.subsidy_id
    const result = await apiFetch<{ wish_id: number; purchase_id: number; status: string }>(
      `/wishes/${convertingWish.value.id}/convert`,
      { method: 'POST', body: JSON.stringify(body) }
    )
    showSnack('Закупка создана')
    convertDialog.value = false
    await loadAllWishes()
    router.push(`/orders/${result.purchase_id}/edit`)
  } catch (e: any) {
    showSnack(`Ошибка при создании закупки: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
  } finally {
    convertingWishLoading.value = false
  }
}

// ── B7: ColumnHeaderMenu — per-column filter + sort ────────────────────
const colFilters = ref<Record<string, any>>({
  status: null,
  title_col: null,
  creator_name: null,
  assigned_to_name: null,
  event_name: null,
  created_at: null,
  desired_date: null,
  executor_name: null,
  execution_deadline: null,
})
const colSort = ref<Record<string, 'asc' | 'desc' | null>>({
  status: null,
  title_col: null,
  creator_name: null,
  assigned_to_name: null,
  event_name: null,
  created_at: null,
  desired_date: null,
  executor_name: null,
  execution_deadline: null,
})

function applyColFilters(rows: Wish[]): Wish[] {
  let result = [...rows]
  // text filters
  if (colFilters.value.title_col?.type === 'text' && colFilters.value.title_col.q)
    result = result.filter(r => (r.title || '').toLowerCase().includes(colFilters.value.title_col.q.toLowerCase()))
  if (colFilters.value.creator_name?.type === 'text' && colFilters.value.creator_name.q)
    result = result.filter(r => (r.creator_name || '').toLowerCase().includes(colFilters.value.creator_name.q.toLowerCase()))
  if (colFilters.value.assigned_to_name?.type === 'text' && colFilters.value.assigned_to_name.q)
    result = result.filter(r => (r.assigned_to_name || '').toLowerCase().includes(colFilters.value.assigned_to_name.q.toLowerCase()))
  if (colFilters.value.event_name?.type === 'text' && colFilters.value.event_name.q)
    result = result.filter(r => ((r as any).event_name || '').toLowerCase().includes(colFilters.value.event_name.q.toLowerCase()))
  if (colFilters.value.executor_name?.type === 'text' && colFilters.value.executor_name.q)
    result = result.filter(r => ((r as any).executor_name || '').toLowerCase().includes(colFilters.value.executor_name.q.toLowerCase()))
  // enum filter for status
  if (colFilters.value.status?.type === 'enum' && Array.isArray(colFilters.value.status.values) && colFilters.value.status.values.length)
    result = result.filter(r => colFilters.value.status.values.includes(r.status))
  // sort: pick first active sort
  const activeSort = Object.entries(colSort.value).find(([_, v]) => v)
  if (activeSort) {
    const [k, dir] = activeSort
    result.sort((a: any, b: any) => {
      const va = a[k === 'title_col' ? 'title' : k] ?? ''
      const vb = b[k === 'title_col' ? 'title' : k] ?? ''
      const cmp = String(va).localeCompare(String(vb), 'ru', { numeric: true })
      return dir === 'asc' ? cmp : -cmp
    })
  }
  return result
}

const myWishesFiltered = computed(() => applyColFilters(myWishes.value))
const incomingWishesFiltered = computed(() => applyColFilters(incomingWishes.value))
const allWishesFiltered = computed(() => applyColFilters(allWishes.value))

watch(activeTab, (v) => {
  if (v === 'my') loadWishes()
  else if (v === 'incoming') loadIncoming()
  else if (v === 'all') loadAllWishes()
})

onMounted(async () => {
  await Promise.all([
    apiFetch<Subsidy[]>('/subsidies/').then(r => { subsidies.value = r }).catch(() => {}),
    apiFetch<FeoCategory[]>('/feo-categories/').then(r => { allFeoCategories.value = r }).catch(() => {}),
    apiFetch<User[]>('/users/').then(r => { users.value = r }).catch(() => {}),
    apiFetch<EventItem[]>('/events/').then(r => { events.value = r || [] }).catch(() => {}),
  ])
  await loadWishes()
  await loadIncoming()
  if (isManagerOrAdmin.value) {
    await loadAllWishes()
  }
})
</script>

<style scoped>
</style>
