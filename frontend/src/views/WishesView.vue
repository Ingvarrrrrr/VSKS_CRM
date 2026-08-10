<template>
  <v-container fluid class="pa-4">
    <!-- Consent banner: pending wish participations -->
    <v-expand-transition>
      <div v-if="pendingWishConsents.length" class="mb-4">
        <div class="d-flex align-center mb-2" style="gap:8px">
          <v-icon color="orange" size="20">mdi-bell-ring</v-icon>
          <span class="font-weight-bold">Требуется ваше согласие на заявки</span>
          <v-chip color="orange" size="x-small" variant="tonal">{{ pendingWishConsents.length }}</v-chip>
        </div>
        <v-row dense>
          <v-col
            v-for="pc in pendingWishConsents"
            :key="pc.wish_id"
            cols="12"
            sm="6"
            md="4"
          >
            <v-card variant="outlined" style="border-color: rgb(251,146,60)" class="pa-3">
              <div class="font-weight-medium mb-1">{{ pc.title }}</div>
              <div class="text-caption text-medium-emphasis mb-2">
                Добавил: <b>{{ pc.added_by_name || '—' }}</b>
                <span v-if="pc.created_at"> · {{ pc.created_at.split('T')[0] }}</span>
              </div>
              <div class="d-flex" style="gap:8px">
                <v-btn
                  color="success"
                  size="small"
                  variant="tonal"
                  :loading="consentLoading === pc.wish_id + '_a'"
                  @click="respondWishConsent(pc.wish_id, true)"
                >Принять</v-btn>
                <v-btn
                  color="error"
                  size="small"
                  variant="tonal"
                  :loading="consentLoading === pc.wish_id + '_d'"
                  @click="respondWishConsent(pc.wish_id, false)"
                >Отклонить</v-btn>
              </div>
            </v-card>
          </v-col>
        </v-row>
      </div>
    </v-expand-transition>

    <!-- Header -->
    <div class="d-flex align-center mb-4 flex-wrap" style="gap:12px">
      <div>
        <h1 class="text-h5 font-weight-bold">Заявки на закупку</h1>
        <span class="text-body-2 text-medium-emphasis">
          {{ activeTab === 'my' ? 'Мои заявки' : activeTab === 'incoming' ? 'На согласование мне' : 'Заявки сотрудников' }}
        </span>
      </div>
      <v-spacer />
      <v-btn-toggle
        v-if="!mobile && activeTab === 'my'"
        v-model="viewMode"
        mandatory
        density="compact"
        variant="outlined"
        divided
        class="ml-1"
      >
        <v-btn value="table" size="small" icon="mdi-table" />
        <v-btn value="cards" size="small" icon="mdi-view-grid" />
      </v-btn-toggle>
      <RegistryExportButton
        title="Заявки на закупку"
        :get-columns="getWishExportColumns"
        :get-rows="getWishExportRows"
        :get-capture-el="() => registryArea"
        @error="(m) => showSnack(m, 'error')"
      />
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
            v-if="isSaas"
            v-model="filterAccountId"
            :items="accountOptions"
            item-title="name"
            item-value="id"
            label="Аккаунт"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:200px;max-width:260px"
          />
          <v-autocomplete
            v-if="isSaas"
            v-model="filterOrgId"
            :items="orgOptionsFiltered"
            item-title="name"
            item-value="id"
            label="Организация"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:200px;max-width:260px"
          />
          <v-autocomplete
            v-model="filterSubsidyId"
            :items="subsidies"
            item-title="name"
            item-value="id"
            label="Субсидия"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:220px;max-width:280px"
          />
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
      <div ref="registryArea">
      <v-data-table
        v-if="effectiveView === 'table'"
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
        <template #header.approver_names="{ column }">
          <ColumnHeaderMenu col-key="approver_names" :title="column.title" col-type="text"
            :model-value="colFilters.approver_names"
            :sort-by="colSort.approver_names"
            @update:model-value="v => colFilters.approver_names = v"
            @sort="dir => colSort.approver_names = dir" />
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
          <div class="d-flex align-center flex-wrap" style="gap:6px">
            <span class="font-weight-medium">{{ item.title }}</span>
            <!-- Phase 31-06: badge for unseen changes -->
            <v-chip
              v-if="item.unseen_changes_count > 0"
              size="x-small"
              variant="tonal"
              :color="GALA_ORANGE"
              :title="`${item.unseen_changes_count} чужих правок с последнего просмотра`"
            >+{{ item.unseen_changes_count }}</v-chip>
          </div>
          <div class="text-caption text-medium-emphasis">
            <span v-if="item.items_count">Позиций: <b>{{ item.items_count }}</b></span>
            <span v-if="item.items_count && item.total_amount"> · </span>
            <span v-if="item.total_amount">НМЦК: <b>{{ formatPrice(item.total_amount) }}</b></span>
          </div>
        </template>
        <template #item.creator_name="{ item }">
          <span class="font-weight-medium">{{ shortName(item.creator_name) || '—' }}</span><span
            v-if="wishCoAuthors(item).length" class="text-medium-emphasis">, {{ wishCoAuthors(item).join(', ') }}</span>
        </template>
        <template #item.approver_names="{ item }">
          <span v-if="wishRecipients(item)">{{ wishRecipients(item) }}</span>
          <span v-else class="text-medium-emphasis">—</span>
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
            <v-menu>
              <template #activator="{ props: menuProps }">
                <v-btn v-bind="menuProps" icon="mdi-microsoft-excel" size="x-small" variant="text" color="green-darken-1" :loading="downloadingExcelId === item.id" title="Скачать в Excel" @click.stop />
              </template>
              <v-list density="compact">
                <v-list-item prepend-icon="mdi-image" title="С фото" @click="downloadWishExcel(item, true)" />
                <v-list-item prepend-icon="mdi-image-off" title="Без фото" @click="downloadWishExcel(item, false)" />
              </v-list>
            </v-menu>
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
            <template v-else-if="item.status === 'approved'">
              <v-btn
                v-if="isManagerOrAdmin"
                size="x-small"
                variant="tonal"
                color="primary"
                prepend-icon="mdi-cart-arrow-right"
                @click="openConvertDialog(item)"
              >
                Передать в план закупок
              </v-btn>
              <v-chip v-else size="x-small" color="success" variant="tonal">
                Согласована — ждёт передачи в план закупок
              </v-chip>
            </template>
            <v-btn
              v-else-if="item.status === 'converted' && item.purchase_id"
              size="x-small"
              variant="tonal"
              color="purple"
              prepend-icon="mdi-cart-arrow-right"
              @click="goToWishPurchases(item)"
            >
              {{ wishPurchasesLabel(item) }}
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

      <!-- Cards view (my wishes) -->
      <div v-else>
        <v-row dense>
          <v-col v-for="w in pagedWishes" :key="w.id" cols="12" sm="6" lg="4">
            <v-card variant="outlined" class="h-100 d-flex flex-column" hover @click="openEditDialog(w)">
              <v-card-item class="pb-1">
                <template #prepend>
                  <v-icon icon="mdi-hand-heart-outline" color="primary" size="20" />
                </template>
                <v-card-title class="text-body-2 font-weight-bold" style="overflow-wrap:anywhere">
                  {{ w.title || '—' }}
                </v-card-title>
              </v-card-item>
              <v-card-text class="py-1 flex-grow-1">
                <div class="d-flex flex-wrap align-center ga-1 mb-2">
                  <v-chip :color="statusColor[w.status]" size="x-small" variant="tonal">
                    {{ statusLabel[w.status] }}
                  </v-chip>
                  <span v-if="w.registry_number" class="text-caption text-medium-emphasis">{{ w.registry_number }}</span>
                </div>
                <div v-if="w.creator_name" class="text-caption text-medium-emphasis mb-1">
                  От: <span class="font-weight-medium text-high-emphasis">{{ shortName(w.creator_name) }}</span><span
                    v-if="wishCoAuthors(w).length">, {{ wishCoAuthors(w).join(', ') }}</span>
                </div>
                <div v-if="wishRecipients(w)" class="text-caption text-medium-emphasis mb-1">
                  Кому: <span class="font-weight-medium text-high-emphasis">{{ wishRecipients(w) }}</span>
                </div>
                <div v-if="w.executor_name" class="text-caption text-medium-emphasis mb-1">
                  Исполнитель: <span class="font-weight-medium text-high-emphasis">{{ w.executor_name }}</span>
                </div>
                <div v-if="w.execution_deadline" class="text-caption text-medium-emphasis mb-1">
                  Срок: <span class="font-weight-medium">{{ formatDate(w.execution_deadline) }}</span>
                </div>
                <div v-if="w.total_amount" class="text-caption text-medium-emphasis mb-1">
                  НМЦК: <span class="font-weight-medium">{{ formatPrice(w.total_amount) }}</span>
                </div>
              </v-card-text>
              <v-divider />
              <v-card-actions class="py-1" @click.stop>
                <v-menu>
                  <template #activator="{ props: menuProps }">
                    <v-btn v-bind="menuProps" icon="mdi-microsoft-excel" size="x-small" variant="text" color="green-darken-1" :loading="downloadingExcelId === w.id" title="Скачать в Excel" @click.stop />
                  </template>
                  <v-list density="compact">
                    <v-list-item prepend-icon="mdi-image" title="С фото" @click="downloadWishExcel(w, true)" />
                    <v-list-item prepend-icon="mdi-image-off" title="Без фото" @click="downloadWishExcel(w, false)" />
                  </v-list>
                </v-menu>
                <template v-if="w.status === 'draft'">
                  <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" @click.stop="openEditDialog(w)" />
                  <v-btn
                    icon="mdi-send"
                    size="x-small"
                    variant="text"
                    color="success"
                    :loading="submittingId === w.id"
                    @click.stop="submitWish(w)"
                  />
                  <v-btn
                    icon="mdi-delete-outline"
                    size="x-small"
                    variant="text"
                    color="error"
                    :loading="deletingId === w.id"
                    @click.stop="deleteWish(w)"
                  />
                </template>
                <template v-else-if="w.status === 'approved'">
                  <v-btn
                    v-if="isManagerOrAdmin"
                    size="x-small"
                    variant="tonal"
                    color="primary"
                    prepend-icon="mdi-cart-arrow-right"
                    @click.stop="openConvertDialog(w)"
                  >
                    В план закупок
                  </v-btn>
                  <v-chip v-else size="x-small" color="success" variant="tonal">
                    Согласована
                  </v-chip>
                </template>
                <v-btn
                  v-else-if="w.status === 'converted' && w.purchase_id"
                  size="x-small"
                  variant="tonal"
                  color="purple"
                  prepend-icon="mdi-cart-arrow-right"
                  @click.stop="goToWishPurchases(w)"
                >
                  {{ wishPurchasesLabel(w) }}
                </v-btn>
              </v-card-actions>
            </v-card>
          </v-col>
        </v-row>
        <div v-if="!pagedWishes.length" class="text-center py-10">
          <v-icon icon="mdi-hand-heart-outline" size="48" color="grey-lighten-1" class="mb-3" />
          <div class="text-medium-emphasis">Нет заявок</div>
        </div>
        <v-pagination
          v-if="cardsTotalPages > 1"
          v-model="cardsPage"
          :length="cardsTotalPages"
          density="compact"
          total-visible="7"
          class="d-flex justify-center mt-4"
        />
      </div>

      </div>

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
        <template #header.approver_names="{ column }">
          <ColumnHeaderMenu col-key="approver_names" :title="column.title" col-type="text"
            :model-value="colFilters.approver_names"
            :sort-by="colSort.approver_names"
            @update:model-value="v => colFilters.approver_names = v"
            @sort="dir => colSort.approver_names = dir" />
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
          <div class="d-flex align-center flex-wrap" style="gap:6px">
            <span class="font-weight-medium">{{ item.title }}</span>
            <!-- Phase 31-06: badge for unseen changes -->
            <v-chip
              v-if="item.unseen_changes_count > 0"
              size="x-small"
              variant="tonal"
              :color="GALA_ORANGE"
              :title="`${item.unseen_changes_count} чужих правок с последнего просмотра`"
            >+{{ item.unseen_changes_count }}</v-chip>
          </div>
          <div class="text-caption text-medium-emphasis">
            <span v-if="item.items_count">Позиций: <b>{{ item.items_count }}</b></span>
            <span v-if="item.items_count && item.total_amount"> · </span>
            <span v-if="item.total_amount">НМЦК: <b>{{ formatPrice(item.total_amount) }}</b></span>
          </div>
        </template>
        <template #item.creator_name="{ item }">
          <span class="font-weight-medium">{{ shortName(item.creator_name) || '—' }}</span><span
            v-if="wishCoAuthors(item).length" class="text-medium-emphasis">, {{ wishCoAuthors(item).join(', ') }}</span>
        </template>
        <template #item.approver_names="{ item }">
          <span v-if="wishRecipients(item)">{{ wishRecipients(item) }}</span>
          <span v-else class="text-medium-emphasis">—</span>
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
            <v-menu>
              <template #activator="{ props: menuProps }">
                <v-btn v-bind="menuProps" icon="mdi-microsoft-excel" size="x-small" variant="text" color="green-darken-1" :loading="downloadingExcelId === item.id" title="Скачать в Excel" @click.stop />
              </template>
              <v-list density="compact">
                <v-list-item prepend-icon="mdi-image" title="С фото" @click="downloadWishExcel(item, true)" />
                <v-list-item prepend-icon="mdi-image-off" title="Без фото" @click="downloadWishExcel(item, false)" />
              </v-list>
            </v-menu>
            <template v-if="item.status === 'submitted'">
              <!-- Распределить/Одобрить/Отклонить — только менеджер+ или назначенный согласующий.
                   Участник цепочки (chain approver, employee) одобряет через диалог — кнопка «Согласовать» там. -->
              <template v-if="isManagerOrAdmin || item.assigned_to === currentUserId">
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
              <template v-else>
                <!-- Участник цепочки — кликнуть строку, чтобы открыть заявку и согласовать в разделе «Согласующие» -->
                <v-btn size="x-small" variant="tonal" color="primary" @click.stop="openEditDialog(item)">
                  Согласовать
                </v-btn>
              </template>
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
        <template #header.approver_names="{ column }">
          <ColumnHeaderMenu col-key="approver_names" :title="column.title" col-type="text"
            :model-value="colFilters.approver_names"
            :sort-by="colSort.approver_names"
            @update:model-value="v => colFilters.approver_names = v"
            @sort="dir => colSort.approver_names = dir" />
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
          <div class="d-flex align-center flex-wrap" style="gap:6px">
            <span class="font-weight-medium">{{ item.title }}</span>
            <!-- Phase 31-06: badge for unseen changes -->
            <v-chip
              v-if="item.unseen_changes_count > 0"
              size="x-small"
              variant="tonal"
              :color="GALA_ORANGE"
              :title="`${item.unseen_changes_count} чужих правок с последнего просмотра`"
            >+{{ item.unseen_changes_count }}</v-chip>
          </div>
          <div class="text-caption text-medium-emphasis">
            <span v-if="item.items_count">Позиций: <b>{{ item.items_count }}</b></span>
            <span v-if="item.items_count && item.total_amount"> · </span>
            <span v-if="item.total_amount">НМЦК: <b>{{ formatPrice(item.total_amount) }}</b></span>
          </div>
        </template>
        <template #item.creator_name="{ item }">
          <span class="font-weight-medium">{{ shortName(item.creator_name) || '—' }}</span><span
            v-if="wishCoAuthors(item).length" class="text-medium-emphasis">, {{ wishCoAuthors(item).join(', ') }}</span>
        </template>
        <template #item.approver_names="{ item }">
          <span v-if="wishRecipients(item)">{{ wishRecipients(item) }}</span>
          <span v-else class="text-medium-emphasis">—</span>
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
            <v-menu>
              <template #activator="{ props: menuProps }">
                <v-btn v-bind="menuProps" icon="mdi-microsoft-excel" size="x-small" variant="text" color="green-darken-1" :loading="downloadingExcelId === item.id" title="Скачать в Excel" @click.stop />
              </template>
              <v-list density="compact">
                <v-list-item prepend-icon="mdi-image" title="С фото" @click="downloadWishExcel(item, true)" />
                <v-list-item prepend-icon="mdi-image-off" title="Без фото" @click="downloadWishExcel(item, false)" />
              </v-list>
            </v-menu>
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
              v-if="item.status === 'approved' && isManagerOrAdmin"
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
              @click="goToWishPurchases(item)"
            >
              {{ wishPurchasesLabel(item) }}
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
    <v-dialog v-model="wishDialog" max-width="1600" width="95vw" scrollable persistent :fullscreen="mobile">
      <v-card class="wish-dialog">
        <v-overlay v-model="wishDialogLoading" contained class="align-center justify-center" persistent>
          <div class="d-flex flex-column align-center ga-3">
            <v-progress-circular indeterminate size="56" width="5" color="primary" />
            <div class="text-body-2 text-medium-emphasis">Загрузка позиций…</div>
          </div>
        </v-overlay>
        <v-card-title class="pa-4 pb-2 d-flex align-center justify-space-between">
          <span>{{ editingWishId ? 'Редактировать заявку' : 'Новая заявка' }}</span>
          <!-- Phase 31-07: Undo/Redo кнопки -->
          <div class="d-flex ga-1 align-center">
            <v-btn
              :disabled="!undoRedoWish.canUndo.value"
              icon="mdi-undo"
              size="x-small"
              variant="text"
              :color="undoRedoWish.canUndo.value ? '#fb923c' : undefined"
              title="Отменить (Ctrl+Z)"
              @click="undoRedoWish.undo()"
            />
            <v-btn
              :disabled="!undoRedoWish.canRedo.value"
              icon="mdi-redo"
              size="x-small"
              variant="text"
              :color="undoRedoWish.canRedo.value ? '#fb923c' : undefined"
              title="Повторить (Ctrl+Y)"
              @click="undoRedoWish.redo()"
            />
          </div>
        </v-card-title>
        <!-- B6 — от кого/кому/дата/статус -->
        <v-card-subtitle v-if="editingWish" class="pa-4 pt-0 d-flex flex-wrap" style="gap:16px">
          <div><b>От кого:</b> <span class="font-weight-medium">{{ shortName(editingWish.creator_name) || '—' }}</span><span
            v-if="wishCoAuthors(editingWish).length" class="text-medium-emphasis">, {{ wishCoAuthors(editingWish).join(', ') }}</span></div>
          <div><b>Кому:</b> {{ wishRecipients(editingWish) || '—' }}</div>
          <div><b>Создано:</b> {{ formatDate(editingWish.created_at) }}</div>
          <div v-if="editingWish.status"><b>Статус:</b> {{ statusLabel[editingWish.status] || editingWish.status }}</div>
          <div v-if="editingWish.executor_name"><b>Исполнитель:</b> {{ editingWish.executor_name }}</div>
          <div v-if="editingWish.execution_deadline"><b>Срок исполнения:</b> {{ formatDate(editingWish.execution_deadline) }}</div>
        </v-card-subtitle>
        <v-card-text class="pa-4">
          <!-- T3: v-alert для ошибки «нет даты потребности» — остаётся пока пользователь не заполнит даты -->
          <v-alert
            v-if="wishConvertError"
            type="error"
            variant="tonal"
            class="mb-3"
            closable
            @click:close="wishConvertError = null"
          >
            <div class="font-weight-medium mb-1">Не удалось передать в план закупок</div>
            <div style="white-space:pre-wrap">{{ wishConvertError.message }}</div>
            <div v-if="wishConvertError.missingItemNames.length" class="mt-2">
              <span class="font-weight-medium">Позиции без даты:</span>
              <ul class="ml-4 mt-1">
                <li v-for="name in wishConvertError.missingItemNames" :key="name">{{ name }}</li>
              </ul>
            </div>
          </v-alert>
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

            <!-- Баннер: редактирование одобренной/конвертированной заявки -->
            <v-alert
              v-if="editingWish && ['approved', 'converted'].includes(editingWish.status) && !editingWish.contracted_locked"
              type="warning"
              variant="tonal"
              density="compact"
              class="mb-4"
              icon="mdi-alert-outline"
            >
              После изменения заявка уйдёт на повторное согласование
            </v-alert>

            <!-- Баннер: заявка заблокирована договором -->
            <v-alert
              v-if="editingWish && editingWish.contracted_locked"
              type="error"
              variant="tonal"
              density="compact"
              class="mb-4"
              icon="mdi-lock-outline"
            >
              Заявка привязана к закупке на этапе «Договор» — редактирование запрещено
            </v-alert>

            <!-- Section 1: Основная информация -->
            <v-card variant="outlined" class="mb-4">
              <v-card-title class="text-subtitle-1 pa-4 pb-2">
                <v-icon class="mr-2">mdi-information-outline</v-icon>Основная информация
              </v-card-title>
              <v-card-text class="pa-4 pt-2">
                <v-row dense>
                  <v-col cols="12">
                    <v-text-field
                      v-model="wishForm.title"
                      label="Предмет заявки"
                      variant="outlined"
                      density="compact"
                      clearable
                      :readonly="!isWishEditable"
                      hint="Краткое название заявки. Если оставить пустым — сформируется из позиций"
                      persistent-hint
                      data-field="title"
                    />
                  </v-col>
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
                      data-field="subsidy_id"
                      @update:model-value="onSubsidyChange"
                    />
                  </v-col>
                  <v-col cols="12" md="6">
                    <v-text-field
                      v-model="wishForm.desired_date"
                      :label="wishDateMode === 'per_item' ? 'Общая дата поставки (по умолчанию)' : 'Желаемая дата поставки/исполнения'"
                      type="date"
                      variant="outlined"
                      density="compact"
                      prepend-inner-icon="mdi-truck-delivery-outline"
                      :readonly="!isWishEditable"
                      persistent-hint
                      :hint="wishForm.execution_deadline ? 'Задан «Срок исполнения» — он перебивает эту дату при переносе в план закупок' : 'К этой дате нужна поставка/исполнение. Нужна для переноса в план закупок'"
                      :error-messages="serverFieldErrors.desired_date"
                      @update:model-value="serverFieldErrors.desired_date = ''"
                    />
                  </v-col>
                  <v-col cols="12" md="6">
                    <div class="text-caption font-weight-medium mb-1">Дата поставки</div>
                    <v-btn-toggle
                      v-model="wishDateMode"
                      color="primary"
                      density="compact"
                      variant="outlined"
                      divided
                      mandatory
                      :disabled="!isWishEditable"
                    >
                      <v-btn value="common" size="small" prepend-icon="mdi-calendar">Одна на заявку</v-btn>
                      <v-btn value="per_item" size="small" prepend-icon="mdi-calendar-multiple">На каждую позицию</v-btn>
                    </v-btn-toggle>
                  </v-col>
                </v-row>
              </v-card-text>
            </v-card>

            <!-- Section 2: Позиции (перенесено выше «Категории ФЭО» по просьбе владельца: при заполнении заявки
                 разумнее сначала завести позиции закупки, а уже потом — предмет ФЭО, мероприятие и получателя) -->
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
                  :feo-per-item="wishFeoPerItem"
                  :subsidy-id="wishForm.subsidy_id"
                  :subsidy-name="selectedSubsidyName"
                  :default-feo-category-id="wishFeoSelected"
                  :default-feo-planned-item-id="!wishFeoPerItem ? wishFeoPlannedItemId : null"
                  :feo-planned-per-item="wishFeoPerItem"
                  :planned-items="wishPlannedResiduals"
                  :show-needed-date="wishDateMode === 'per_item'"
                  :vat-mode="wishForm.vat_mode"
                  @update:vat-mode="(v: string) => { wishForm.vat_mode = v }"
                  @planned-item-created="onWishPlannedItemCreated"
                />
                <div class="d-flex justify-end mt-3">
                  <div class="text-subtitle-1 font-weight-bold">Сумма заявки: {{ formatMoney(totalNmck) }}</div>
                </div>
              </v-card-text>
            </v-card>

            <!-- Section: Категория ФЭО (сознательно ниже «Позиций»: субсидия выбрана в «Основной информации» выше,
                 а дерево ФЭО, плановые позиции и переключатели тут завязаны уже на введённые позиции закупки) -->
            <v-card variant="outlined" class="mb-4">
              <v-card-title class="text-subtitle-1 pa-4 pb-2">
                <v-icon class="mr-2">mdi-sitemap</v-icon>Категория ФЭО
              </v-card-title>
              <v-card-text class="pa-4 pt-2">
                <v-row dense>
                  <v-col v-if="wishForm.subsidy_id" cols="12" data-field="feo_category">
                    <v-alert v-if="wishFeoStale" type="warning" density="compact" variant="tonal" class="mb-2">
                      Категория ФЭО, выбранная в заявке, была удалена из справочника (структуру ФЭО субсидии
                      пересоздавали). Выберите актуальную категорию и сохраните. Если согласовать как есть —
                      закупка будет создана без категории ФЭО, её можно задать в «Плане закупок».
                    </v-alert>
                    <!-- Жёсткий гейт (владелец, 2026-08-11): без категории ФЭО заявку нельзя
                         согласовать/отправить в План закупок — иначе закупка остаётся сиротой
                         вне всех планов ФЭО (реальный случай с прода — заявка №32). Блокирует
                         кнопку «Отправить на согласование», см. wishFeoCategoryMissing. -->
                    <v-alert
                      v-if="wishFeoCategoryMissing"
                      type="error"
                      density="compact"
                      variant="tonal"
                      class="mb-2"
                      icon="mdi-alert-octagon-outline"
                    >
                      <div class="font-weight-medium">Категория ФЭО не выбрана — отправить заявку на согласование нельзя</div>
                      <div class="mt-1">
                        Без категории закупка не попадёт ни в один план ФЭО и её сумма потеряется.
                        Выберите категорию {{ wishFeoPerItem ? 'для каждой позиции в таблице выше' : 'в дереве ниже' }},
                        а если категория неизвестна — нажмите «Не определена».
                      </div>
                      <div v-if="wishFeoPerItem && wishItemsMissingFeoCategory.length" class="mt-2">
                        <span class="font-weight-medium">Позиции без категории:</span>
                        <ul class="ml-4 mt-1">
                          <li v-for="(it, idx) in wishItemsMissingFeoCategory" :key="idx">{{ it.item_name || 'без названия' }}</li>
                        </ul>
                      </div>
                    </v-alert>
                    <FeoTreeSelect
                      v-model="wishFeoSelected"
                      :nodes="wishFeoNodes"
                      :leaves="wishFeoLeaves"
                      :plan-positions="wishPlannedResiduals"
                      :node-amounts="wishNodeAmounts"
                      horizontal
                      :readonly="!isWishEditable && !canEditWishFeo"
                      :allow-unallocated="!!(wishForm.subsidy_id && (isWishEditable || canEditWishFeo))"
                      :root-label="selectedSubsidyName"
                      @pick-unallocated="(parentId: number | null) => pickWishUnallocated(parentId)"
                    />
                    <FeoPlannedItemsSelect
                      v-if="wishFeoSelected && !wishFeoPerItem"
                      v-model="wishFeoPlanSelection"
                      :category-id="wishFeoSelected"
                      :nodes="wishFeoNodes"
                      :items="wishPlannedResiduals"
                      :amount="totalNmck"
                      :suggest-key="wishFeoPlanSuggestKey"
                      :suggest-reason="wishFeoPlanSuggestReason"
                      :candidates="wishFeoPlanCandidatesForUi"
                      :loading="wishPlannedLoading"
                      :readonly="!isWishEditable && !canEditWishFeo"
                      :skip-last="wishFeoSkipLast"
                      :prefill="wishFeoPlannedPrefill"
                      @planned-item-created="onWishPlannedItemCreated"
                      @candidate-confirmed="onWishFeoCandidateConfirmed"
                    />
                    <div v-if="!isWishEditable && canEditWishFeo && !canAssigneeAct" class="mt-2">
                      <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-content-save"
                             :loading="savingExecution" @click="saveExecution">
                        Сохранить ФЭО
                      </v-btn>
                      <span class="text-caption text-medium-emphasis ml-2">
                        Вы согласующий — можете изменить категорию ФЭО, если не согласны с выбором автора.
                      </span>
                    </div>
                  </v-col>
                  <!-- Переключатель «не указывать последний уровень ФЭО» -->
                  <v-col v-if="wishFeoSelected" cols="12" class="py-0">
                    <v-switch
                      v-model="wishFeoSkipLast"
                      label="Не указывать последний уровень ФЭО"
                      density="compact"
                      color="primary"
                      hide-details
                      :disabled="!isWishEditable && !canEditWishFeo"
                    />
                    <div v-if="wishFeoSkipLast" class="text-caption text-medium-emphasis mt-n2 mb-2">
                      Заявка будет привязана к выбранному уровню без детализации до конечной категории.
                    </div>
                    <div v-else-if="wishFeoSelectedNotLeaf" class="text-caption text-medium-emphasis mt-n2 mb-2">
                      Выбранная категория ФЭО не конечная — углубитесь до конечной категории в дереве выше
                      либо включите этот переключатель, если сознательно хотите остановиться на этом уровне.
                    </div>
                  </v-col>
                  <!-- Тогл «Разные ФЭО позиции для каждого товара» (как в закупке) -->
                  <v-col v-if="wishForm.subsidy_id" cols="12" class="py-0">
                    <v-switch
                      v-model="wishFeoPerItem"
                      label="Разные ФЭО позиции для каждого товара"
                      density="compact"
                      color="primary"
                      hide-details
                      :disabled="!isWishEditable && !canAssigneeAct"
                      @update:model-value="onWishFeoPerItemChange"
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
                      label="На чьё имя будет заявка"
                      variant="outlined"
                      density="compact"
                      clearable
                      :disabled="!wishForm.subsidy_id"
                      :readonly="!isWishEditable && !canEditAssignee"
                      hint="Сотрудник, на имя которого составляется заявка"
                      persistent-hint
                      @update:model-value="(val) => { if (!isWishEditable && canEditAssignee) saveAssignedTo(val) }"
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

            <!-- Section: Участники заявки -->
            <v-card v-if="isWishEditable || editingWishId" variant="outlined" class="mb-4">
              <v-card-title class="text-subtitle-1 pa-4 pb-2">
                <v-icon class="mr-2" color="primary">mdi-account-multiple-plus</v-icon>
                Участники заявки
                <v-chip class="ml-2" size="x-small" variant="tonal">{{ wishMembers.length }}</v-chip>
              </v-card-title>
              <v-card-text class="pa-4 pt-2">
                <v-autocomplete
                  v-model="participantToAdd"
                  :items="orgUsers"
                  item-title="full_name"
                  item-value="id"
                  label="Добавить участника"
                  variant="outlined"
                  density="compact"
                  clearable
                  :disabled="!isWishEditable"
                  hide-details
                  @update:model-value="(val) => { if (val) { addWishMember(val); } }"
                >
                  <template #item="{ item, props: itemProps }">
                    <v-list-item v-bind="itemProps">
                      <template #title>
                        {{ item.raw.full_name }}
                        <v-chip
                          size="x-small"
                          :color="requiresConsent(item.raw.id) ? 'orange' : 'green'"
                          variant="tonal"
                          class="ml-2"
                        >{{ requiresConsent(item.raw.id) ? 'нужно согласование' : 'без согласования' }}</v-chip>
                      </template>
                      <template #subtitle>{{ resolveUserPosition(item.raw) || '—' }}</template>
                    </v-list-item>
                  </template>
                </v-autocomplete>
                <div class="text-caption text-medium-emphasis mt-1 mb-3">
                  Если у вас нет права ставить задачи участнику — потребуется его согласие.
                </div>
                <div class="d-flex flex-wrap" style="gap:8px">
                  <v-chip
                    v-for="m in wishMembers"
                    :key="m.user_id"
                    :closable="isWishEditable"
                    @click:close="removeWishMember(m.user_id)"
                  >
                    {{ m.full_name || m.username || '—' }}
                    <v-chip
                      v-if="m.consent_pending"
                      size="x-small"
                      color="orange"
                      variant="tonal"
                      class="ml-1"
                    >ждёт согласия</v-chip>
                    <v-chip
                      v-else-if="!editingWishId && requiresConsent(m.user_id)"
                      size="x-small"
                      color="orange"
                      variant="tonal"
                      class="ml-1"
                    >потребует согласования</v-chip>
                  </v-chip>
                </div>
              </v-card-text>
            </v-card>

            <!-- Section: Согласующие (мультисогласование с авто-каскадом) -->
            <v-card v-if="isWishEditable || editingWishId" variant="outlined" class="mb-4">
              <v-card-title class="text-subtitle-1 pa-4 pb-2">
                <v-icon class="mr-2" color="primary">mdi-account-check</v-icon>
                Согласующие
                <v-chip class="ml-2" size="x-small" variant="tonal">{{ wishApprovers.length }}</v-chip>
                <v-spacer />
                <v-chip size="x-small" :color="approvalMode === 'sequential' ? 'blue' : 'teal'" variant="tonal">
                  {{ approvalMode === 'sequential' ? 'Последовательно' : 'Параллельно' }}
                </v-chip>
              </v-card-title>
              <v-card-text class="pa-4 pt-2">
                <v-alert
                  v-if="!editingWishId"
                  type="info"
                  variant="tonal"
                  density="compact"
                  class="mb-0"
                >
                  Сначала сохраните черновик заявки — после этого можно назначить согласующих и построить цепочку согласования.
                  <div class="mt-2">
                    <v-btn
                      size="small"
                      color="primary"
                      variant="flat"
                      :loading="saving"
                      prepend-icon="mdi-content-save"
                      @click="saveWish(false)"
                    >Сохранить черновик</v-btn>
                  </div>
                </v-alert>
                <!-- Построение цепочки (только для черновика/отклонённой) -->
                <template v-if="isWishEditable && editingWishId">
                  <div class="text-caption text-medium-emphasis mb-2">
                    Выберите верхнего согласующего — система автоматически подтянет всю восходящую цепочку начальников снизу вверх.
                    Построение цепочки НЕ отправляет заявку: цепочку можно менять и дополнять людьми вручную,
                    а на согласование заявка уйдёт только по кнопке «Отправить на согласование».
                  </div>
                  <v-row dense align="center">
                    <v-col cols="12" md="6">
                      <v-autocomplete
                        v-model="approverTopUser"
                        :items="orgUsers"
                        item-title="full_name"
                        item-value="id"
                        label="Верхний согласующий"
                        variant="outlined"
                        density="compact"
                        clearable
                        hide-details
                      >
                        <template #item="{ item, props: itemProps }">
                          <v-list-item v-bind="itemProps">
                            <template #title>{{ item.raw.full_name }}</template>
                            <template #subtitle>{{ resolveUserPosition(item.raw) || '—' }}</template>
                          </v-list-item>
                        </template>
                      </v-autocomplete>
                    </v-col>
                    <v-col cols="12" md="3">
                      <v-select
                        v-model="approvalMode"
                        :items="[
                          { value: 'sequential', title: 'Последовательно' },
                          { value: 'parallel', title: 'Параллельно' },
                        ]"
                        label="Режим"
                        variant="outlined"
                        density="compact"
                        hide-details
                      />
                    </v-col>
                    <v-col cols="12" md="3">
                      <v-btn
                        color="primary"
                        variant="flat"
                        block
                        :loading="cascadeLoading"
                        :disabled="!approverTopUser"
                        prepend-icon="mdi-sitemap"
                        @click="runCascade"
                      >Построить цепочку</v-btn>
                    </v-col>
                  </v-row>
                  <v-divider class="my-3" />
                </template>

                <!-- Список согласующих -->
                <div v-if="wishApprovers.length === 0" class="text-caption text-medium-emphasis">
                  Согласующие ещё не назначены.
                  <div v-if="approverTopUser">Нажмите «Построить цепочку» — или просто отправьте заявку, цепочка построится автоматически.</div>
                </div>
                <div v-else class="d-flex flex-column" style="gap:10px">
                  <v-sheet
                    v-for="(a, ai) in wishApprovers"
                    :key="a.id"
                    rounded="lg"
                    border
                    class="pa-3"
                  >
                    <div class="d-flex align-center flex-wrap" style="gap:8px">
                      <v-chip size="x-small" variant="tonal" color="grey">#{{ a.order_num + 1 }}</v-chip>
                      <span class="font-weight-medium">{{ a.full_name || '—' }}</span>
                      <span v-if="a.role_name" class="text-caption text-medium-emphasis">{{ a.role_name }}</span>
                      <v-chip
                        v-if="!a.is_auto"
                        size="x-small"
                        variant="tonal"
                        color="purple"
                      >вручную</v-chip>
                      <v-spacer />
                      <v-chip size="small" :color="approvalStatusColor[a.status]" variant="tonal">
                        {{ approvalStatusLabel[a.status] || a.status }}
                      </v-chip>
                      <template v-if="isWishEditable && wishApprovers.length > 1">
                        <v-btn
                          icon="mdi-arrow-up"
                          size="x-small"
                          variant="text"
                          :disabled="ai === 0 || reorderLoading"
                          title="Поднять в очереди согласования"
                          @click="moveApprover(ai, -1)"
                        />
                        <v-btn
                          icon="mdi-arrow-down"
                          size="x-small"
                          variant="text"
                          :disabled="ai === wishApprovers.length - 1 || reorderLoading"
                          title="Опустить в очереди согласования"
                          @click="moveApprover(ai, 1)"
                        />
                      </template>
                      <v-btn
                        v-if="a.status === 'pending' && isWishEditable"
                        icon="mdi-close"
                        size="x-small"
                        variant="text"
                        @click="removeApprover(a.id)"
                      />
                    </div>
                    <div v-if="a.comment" class="text-caption text-medium-emphasis mt-1">
                      Комментарий: {{ a.comment }}
                    </div>
                    <!-- Действия текущего пользователя-согласующего -->
                    <div v-if="canDecideApprover(a)" class="mt-2">
                      <v-textarea
                        v-model="decideComment[a.id]"
                        label="Комментарий (необязательно при согласовании, обязателен при отказе)"
                        variant="outlined"
                        density="compact"
                        rows="2"
                        auto-grow
                        hide-details
                        class="mb-2"
                      />
                      <div class="d-flex" style="gap:8px">
                        <v-btn
                          color="green"
                          variant="flat"
                          size="small"
                          :loading="decideLoading === a.id"
                          prepend-icon="mdi-check"
                          @click="decideApprover(a.id, 'approved')"
                        >Согласовать</v-btn>
                        <v-btn
                          color="red"
                          variant="tonal"
                          size="small"
                          :loading="decideLoading === a.id"
                          :disabled="!decideComment[a.id]"
                          prepend-icon="mdi-close"
                          @click="decideApprover(a.id, 'rejected')"
                        >Отклонить</v-btn>
                      </div>
                    </div>
                  </v-sheet>
                </div>

                <!-- Ручное добавление -->
                <template v-if="editingWishId && (isWishEditable || (editingWish && editingWish.status === 'submitted' && (isChainApprover || isManagerOrAdmin)))">
                  <v-divider class="my-3" />
                  <v-autocomplete
                    v-model="approverToAdd"
                    :items="orgUsers"
                    item-title="full_name"
                    item-value="id"
                    label="Добавить согласующего"
                    variant="outlined"
                    density="compact"
                    clearable
                    hide-details
                    @update:model-value="(val) => { if (val) addApprover(val) }"
                  >
                    <template #item="{ item, props: itemProps }">
                      <v-list-item v-bind="itemProps">
                        <template #title>{{ item.raw.full_name }}</template>
                        <template #subtitle>{{ resolveUserPosition(item.raw) || '—' }}</template>
                      </v-list-item>
                    </template>
                  </v-autocomplete>
                </template>
              </v-card-text>
            </v-card>

            <!-- Section: Принудительная смена статуса (только superadmin/account_owner) -->
            <v-card v-if="isSaas && editingWishId" variant="outlined" class="mb-4 bg-red-lighten-5">
              <v-card-title class="text-subtitle-1 font-weight-bold pa-4 pb-2">
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
                <div class="text-body-2 text-medium-emphasis mt-2">
                  Минуя все workflow-проверки. Доступно только SaaS-роли.
                </div>
              </v-card-text>
            </v-card>

            <!-- Section: На исполнение (видна согласующему) -->
            <v-card v-if="canAssigneeAct || (editingWish && editingWish.status === 'approved' && (isDialogAssignee || isAdmin))" variant="outlined" class="mb-4 bg-amber-lighten-5">
              <v-card-title class="text-subtitle-1 font-weight-bold pa-4 pb-2">
                <v-icon class="mr-2" color="orange-darken-4">mdi-account-clock</v-icon>На исполнение
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
                    <v-autocomplete
                      v-model="wishForm.assigned_to"
                      :items="orgUsers"
                      item-title="full_name"
                      item-value="id"
                      label="На чьё имя заявка"
                      variant="outlined"
                      density="compact"
                      clearable
                      hint="Сотрудник, на имя которого составляется заявка (без сброса цепочки согласования)"
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
                  <v-col cols="12">
                    <v-btn color="orange-darken-4" variant="flat" prepend-icon="mdi-content-save" :loading="savingExecution" @click="saveExecution">
                      Сохранить исполнителя / срок / мероприятие / получателя
                    </v-btn>
                  </v-col>
                </v-row>
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
                      data-field="justification"
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
                      data-field="priority"
                    />
                  </v-col>
                </v-row>
              </v-card-text>
            </v-card>

          </v-form>
        </v-card-text>

        <v-card-actions class="px-4 pb-4 flex-wrap">
          <v-btn variant="text" @click="wishDialog = false">Закрыть</v-btn>
          <v-menu v-if="editingWishId && editingWish">
            <template #activator="{ props: menuProps }">
              <v-btn v-bind="menuProps" variant="tonal" color="green-darken-1" prepend-icon="mdi-microsoft-excel" :loading="downloadingExcelId === editingWishId">Скачать Excel</v-btn>
            </template>
            <v-list density="compact">
              <v-list-item prepend-icon="mdi-image" title="С фото" @click="downloadWishExcel(editingWish as any, true)" />
              <v-list-item prepend-icon="mdi-image-off" title="Без фото" @click="downloadWishExcel(editingWish as any, false)" />
            </v-list>
          </v-menu>
          <v-spacer />
          <!-- draft/rejected или новая заявка: черновик + отправить -->
          <template v-if="isWishEditable && (!editingWishId || ['draft', 'rejected'].includes((wishForm as any).status))">
            <v-btn color="grey" variant="tonal" :loading="saving" @click="saveWish(false)">
              Сохранить черновик
            </v-btn>
            <v-tooltip :disabled="!wishFeoCategoryMissing" location="top">
              <template #activator="{ props: tipProps }">
                <span v-bind="tipProps">
                  <v-btn ref="wishSubmitBtnRef" color="primary" variant="flat" :loading="saving"
                         :class="{ 'wish-btn-blocked': wishFeoCategoryMissing }"
                         @click="wishFeoCategoryMissing ? highlightMissingFeoCategory() : saveWish(true)">
                    Отправить на согласование
                  </v-btn>
                </span>
              </template>
              Не выбрана категория ФЭО — заполните её ниже, иначе заявку нельзя будет согласовать
            </v-tooltip>
          </template>
          <!-- approved/converted и editable (не contracted_locked): сохранить изменения -->
          <template v-else-if="isWishEditable && editingWish && ['approved', 'converted'].includes(editingWish.status)">
            <v-btn color="primary" variant="tonal" :loading="saving" @click="saveWish(false)">
              Сохранить изменения
            </v-btn>
            <v-btn v-if="isManagerOrAdmin" color="primary" variant="flat" prepend-icon="mdi-cart-arrow-right"
                   @click="openConvertDialog(editingWish); wishDialog = false">
              Передать в План закупок
            </v-btn>
          </template>
          <template v-else-if="canAssigneeAct && editingWish">
            <v-btn color="error" variant="tonal" prepend-icon="mdi-close" @click="openRejectDialog(editingWish); wishDialog = false">
              Отклонить
            </v-btn>
            <v-tooltip :disabled="!wishFeoCategoryMissing" location="top">
              <template #activator="{ props: tipProps }">
                <span v-bind="tipProps">
                  <v-btn color="success" variant="tonal" prepend-icon="mdi-check" :loading="approvingId === editingWish.id"
                         :class="{ 'wish-btn-blocked': wishFeoCategoryMissing }"
                         @click="wishFeoCategoryMissing ? highlightMissingFeoCategory() : approveWish(editingWish).then(() => wishDialog = false)">
                    Одобрить без согласования остальных
                  </v-btn>
                </span>
              </template>
              Не выбрана категория ФЭО — заполните её ниже, иначе заявку нельзя будет согласовать
            </v-tooltip>
            <v-btn color="primary" variant="flat" prepend-icon="mdi-view-column-outline"
                   @click="openKanbanDialog(editingWish); wishDialog = false">
              Распределить и одобрить
            </v-btn>
          </template>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Стрелочки от кнопки отправки к незаполненным полям (как в Закупке) -->
    <ValidationArrows
      :active="validationArrowsActive"
      :from-el="validationArrowFrom"
      :to-els="validationArrowTargets"
      @dismiss="dismissValidationArrows"
    />

    <!-- ── KANBAN DISTRIBUTION DIALOG (Phase 13) ── -->
    <v-dialog v-model="kanbanDialog" max-width="1200" scrollable :fullscreen="mobile">
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
    <v-dialog v-model="rejectDialog" max-width="480" :fullscreen="mobile">
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

    <v-dialog v-model="wishFeoPerItemDisableDialog" max-width="480" :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4 pb-2">Отключить разные ФЭО по позициям?</v-card-title>
        <v-card-text class="pa-4">
          У {{ wishFeoPerItemDisableCount }} {{ wishFeoPerItemDisableCount === 1 ? 'позиции' : 'позиций' }} указана своя категория ФЭО — при отключении режима она будет очищена.
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="cancelWishFeoPerItemDisable">Отмена</v-btn>
          <v-btn variant="flat" color="warning" @click="confirmWishFeoPerItemDisable">Отключить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── CONVERT DIALOG ── -->
    <v-dialog v-model="convertDialog" max-width="540" :fullscreen="mobile">
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

  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick, onBeforeUnmount } from 'vue'
import { useUndoRedo } from '@/composables/useUndoRedo'
import { useToast, type ToastType } from '@/composables/useToast'
import { refreshMyPendingApprovals } from '@/composables/useApprovalsBadge'
import { useRouter, useRoute } from 'vue-router'
import { apiFetch } from '@/api'
import { formatMoney } from '@/utils/formatMoney'
import PurchaseItemsEditor from '@/components/PurchaseItemsEditor.vue'
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'
import FeoPlannedItemsSelect from '@/components/items/FeoPlannedItemsSelect.vue'
import { useFeoLeaves } from '@/composables/useFeoLeaves'
import { useFeoNodeAmounts } from '@/composables/useFeoNodeAmounts'
import { useFeoPlannedResiduals } from '@/composables/useFeoPlannedResiduals'
import type { FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'
import { useFeoPlanMatching } from '@/composables/useFeoPlanMatching'
import type { FeoMatchCandidate } from '@/composables/useFeoPlanMatching'
import WishDistributionKanban from '@/components/WishDistributionKanban.vue'
import ColumnHeaderMenu from '@/components/ColumnHeaderMenu.vue'
import ValidationArrows from '@/components/ValidationArrows.vue'
import { useCardView } from '@/composables/useCardView'
import RegistryExportButton from '@/components/RegistryExportButton.vue'

// Phase 31-06: GALA-orange for unseen-changes badges
const GALA_ORANGE = '#fb923c'

const router = useRouter()
const route = useRoute()
const registryArea = ref<HTMLElement | null>(null)

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
  member_names?: string[]
  approver_names?: string[]
  purchase_ids?: number[]
  contracted_locked?: boolean
}

// «От кого»: Фамилия И.О. вместо полного ФИО
function shortName(full?: string | null): string {
  if (!full) return ''
  const parts = full.trim().split(/\s+/)
  if (parts.length < 2) return parts[0]
  return parts[0] + ' ' + parts.slice(1, 3).map(p => p[0].toUpperCase() + '.').join('')
}
// Участники заявки (WishMember) без дублирования автора — автор выделен отдельно
function wishCoAuthors(w: { creator_name?: string | null; member_names?: string[] }): string[] {
  const author = shortName(w.creator_name)
  const seen = new Set<string>([author])
  const out: string[] = []
  for (const n of w.member_names || []) {
    const s = shortName(n)
    if (s && !seen.has(s)) { seen.add(s); out.push(s) }
  }
  return out
}

// «Кому»: назначенный или цепочка согласующих (Фамилия И.О.)
function wishRecipients(w: { assigned_to_name?: string | null; approver_names?: string[] }): string {
  if (w.assigned_to_name) return shortName(w.assigned_to_name)
  return (w.approver_names || []).map(shortName).join(' → ')
}
// Конвертация разбивает заявку на несколько закупок: одна → сразу в карточку,
// несколько → список закупок с фильтром по заявке
function goToWishPurchases(w: Wish) {
  const ids = w.purchase_ids || []
  if (ids.length > 1) router.push({ path: '/orders', query: { wish_id: String(w.id) } })
  else router.push(`/orders/${w.purchase_id}/edit`)
}
function wishPurchasesLabel(w: Wish): string {
  const n = (w.purchase_ids || []).length
  return n > 1 ? `Закупки (${n})` : 'Закупка'
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
  submitted: 'На согласовании',
  approved: 'Согласовано',
  rejected: 'Не согласовано',
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
  // «Кому» = назначенный (assigned_to) или цепочка согласующих — одно понятие
  { title: 'Кому', key: 'approver_names', width: 180, sortable: false },
  { title: 'Мероприятие', key: 'event_name', width: 180, sortable: true },
  { title: 'Создано', key: 'created_at', width: 110, sortable: true },
  { title: 'Срок', key: 'desired_date', width: 110, sortable: true },
  { title: 'Исполнитель', key: 'executor_name', width: 160, sortable: true },
  { title: 'Срок исп.', key: 'execution_deadline', width: 110, sortable: true },
  { title: 'Действия', key: 'actions', width: 160, sortable: false },
]

const wishHeadersAll = wishHeaders

const EXCLUDED_WISH_KEYS = new Set(['actions', 'data-table-expand'])
function getWishExportColumns() {
  return wishHeaders
    .filter(h => !EXCLUDED_WISH_KEYS.has(h.key) && h.title)
    .map(h => ({ key: h.key, title: h.title, align: (h as any).align }))
}
function getWishExportRows() {
  if (activeTab.value === 'my') return myWishesFiltered.value
  if (activeTab.value === 'incoming') return incomingWishesFiltered.value
  return allWishesFiltered.value
}

// Filter state
const filterSubsidyId = ref<number | null>(null)
const filterCreatorId = ref<number | null>(null)
const filterAssignedToId = ref<number | null>(null)
const filterCreatedFrom = ref('')
const filterCreatedTo = ref('')
const filterDeadlineFrom = ref('')
const filterDeadlineTo = ref('')
// SaaS-фильтры: аккаунт (корневая орг + дочерние) и конкретная организация
const filterAccountId = ref<number | null>(null)
const filterOrgId = ref<number | null>(null)
const allOrgs = ref<{ id: number; name: string; root_org_id?: number | null; parent_org_id?: number | null }[]>([])
const accountOptions = computed(() => allOrgs.value.filter(o => !o.root_org_id && !o.parent_org_id))
const orgOptionsFiltered = computed(() => {
  const acc = filterAccountId.value
  if (!acc) return allOrgs.value
  return allOrgs.value.filter(o => o.id === acc || o.root_org_id === acc || o.parent_org_id === acc)
})
watch(filterAccountId, () => {
  if (filterOrgId.value && !orgOptionsFiltered.value.some(o => o.id === filterOrgId.value)) {
    filterOrgId.value = null
  }
})

function buildFilterParams(extra: Record<string, any> = {}) {
  const params = new URLSearchParams()
  if (filterAccountId.value) params.set('account_org_id', String(filterAccountId.value))
  if (filterOrgId.value) params.set('org_id', String(filterOrgId.value))
  if (filterSubsidyId.value) params.set('subsidy_id', String(filterSubsidyId.value))
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
  filterAccountId.value = null
  filterOrgId.value = null
  filterSubsidyId.value = null
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
  [filterAccountId, filterOrgId, filterSubsidyId, filterCreatorId, filterAssignedToId, filterCreatedFrom, filterCreatedTo, filterDeadlineFrom, filterDeadlineTo],
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
// Название субсидии для «ствола» дерева ФЭО (FeoTreeSelect rootLabel).
const selectedSubsidyName = computed((): string | null =>
  subsidies.value.find(s => s.id === wishForm.value.subsidy_id)?.name ?? null
)
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

// FEO: динамический каскад (глубина = реальная глубина дерева, не 3 захардкоженных уровня).
// wishFeoSelected — самый глубокий выбранный узел (лист или промежуточный при skipLast).
const wishFeoSelected = ref<number | null>(null)
const wishFeoSkipLast = ref(false)
const wishFeoPerItem = ref(false)
const wishFeoPerItemDisableDialog = ref(false)
const wishFeoPerItemDisableCount = ref(0)
const onWishFeoPerItemChange = (val: boolean | null) => {
  if (val) return
  // Ручное выключение — предупреждаем, если есть позиции с уже выбранной категорией
  const count = wishForm.value.items.filter((i: any) => i.feo_category_id != null).length
  if (count > 0) {
    wishFeoPerItemDisableCount.value = count
    wishFeoPerItemDisableDialog.value = true
  }
}
const cancelWishFeoPerItemDisable = () => {
  wishFeoPerItem.value = true
  wishFeoPerItemDisableDialog.value = false
}
// Подтверждение «Отключить» — очищаем per-item ФЭО СРАЗУ (не только при сохранении),
// иначе до следующего save() позиции продолжают нести свои feo_category_id/
// feo_planned_item_id, и любая эвристика по ним (см. loadWish) рискует снова
// включить режим сама собой.
const confirmWishFeoPerItemDisable = () => {
  for (const it of wishForm.value.items as any[]) {
    it.feo_category_id = null
    it.feo_planned_item_id = null
    it.over_plan = false
  }
  wishFeoPerItemDisableDialog.value = false
}

// F-PLAN: привязка к конкретной ПЛАНОВОЙ ПОЗИЦИИ плана закупок (FeoPlannedItem) —
// заявка расходует уже заложенный план, а не задваивает его. Блок FeoPlannedItemsSelect
// показывается всегда, когда выбрана категория ФЭО (см. шаблон).
// БАГ 3 (сессия 2026-08-05): псевдо-вариант «Вне плана (новая позиция)» убран целиком —
// владелец: «"Создать в плане закупок" замечательно отображает добавление новой позиции...
// "Вне плана" не нужна». Позицию без плановой привязки заводят кнопкой «Создать
// в плане закупок» (FeoPlannedItemsSelect) — она физически создаёт FeoPlannedItem и сразу
// выбирает его, так что «непривязанного» состояния для НОВЫХ заявок больше не возникает.
const wishFeoPlannedItemId = ref<number | null>(null)

const orgMembers = ref<User[]>([])

async function loadOrgMembers(sid: number | null) {
  orgMembers.value = []
  if (!sid) return
  try {
    orgMembers.value = await apiFetch<User[]>(`/users/?subsidy_id=${sid}`)
  } catch { orgMembers.value = [] }
}

const orgUsers = computed(() => {
  if (!wishForm.value.subsidy_id) return users.value
  if (orgMembers.value.length) return orgMembers.value
  return users.value
})

// Кому текущий может ставить задачи без согласия (для пометки в пикере участников).
// assignableAll=true → SaaS-роль, согласование не нужно ни для кого.
const assignableAll = ref(false)
const assignableIds = ref<Set<number>>(new Set())
function requiresConsent(userId: number | null | undefined): boolean {
  if (!userId || assignableAll.value) return false
  if (userId === currentUserId) return false
  return !assignableIds.value.has(userId)
}

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
const wishDialogLoading = ref(false)
watch(wishDialog, (v) => { if (!v) { dismissValidationArrows(); wishConvertError.value = null } })
const editingWishId = ref<number | null>(null)
const wishDateMode = ref<'common' | 'per_item'>('common')

// T3: error state for «missing needed dates» when converting/approving
const wishConvertError = ref<{ message: string; missingItemIds: number[]; missingItemNames: string[] } | null>(null)

watch(wishDateMode, (mode, prev) => {
  if (mode === 'per_item' && prev === 'common') {
    const d = wishForm.value.desired_date
    if (!d) return
    for (const it of wishForm.value.items as any[]) {
      if (!it.needed_date) it.needed_date = d
    }
  }
})
const editingWish = ref<Wish | null>(null)
const wishFormRef = ref<any>(null)
const wishSubmitBtnRef = ref<any>(null)

// Стрелочки к незаполненным полям (паттерн из CreateOrderView)
const validationArrowsActive = ref(false)
const validationArrowFrom = ref<HTMLElement | null>(null)
const validationArrowTargets = ref<HTMLElement[]>([])
let validationArrowsTimer: number | null = null
function dismissValidationArrows() {
  validationArrowsActive.value = false
  validationArrowFrom.value = null
  validationArrowTargets.value = []
  if (validationArrowsTimer) { window.clearTimeout(validationArrowsTimer); validationArrowsTimer = null }
}
function showValidationArrows() {
  const formEl = wishFormRef.value?.$el as HTMLElement | undefined
  if (!formEl) return
  const allErrors = Array.from(formEl.querySelectorAll('.v-input.v-input--error')) as HTMLElement[]
  if (!allErrors.length) return
  // После перестановки блоков «Позиции» теперь выше по DOM, чем часть полей шапки
  // (например «Обоснование»). Поля с [data-field] — это осознанно провалидированные
  // поля шапки/футера формы (субсидия, обоснование и т.п.); ошибка внутри таблицы
  // позиций (PurchaseItemsEditor) не помечена [data-field] и не должна перехватывать
  // стрелку у более важного поля шапки. Сначала ищем среди [data-field], и только
  // если там чисто — берём первую ошибку по обычному DOM-порядку.
  const headerErrors = allErrors.filter(el => el.closest('[data-field]'))
  const errors = headerErrors.length ? headerErrors : allErrors
  const btn = (wishSubmitBtnRef.value?.$el ?? wishSubmitBtnRef.value) as HTMLElement | null
  if (!btn) return
  errors[0].scrollIntoView({ behavior: 'smooth', block: 'center' })
  validationArrowFrom.value = btn
  validationArrowTargets.value = errors.slice(0, 8)
  validationArrowsActive.value = true
  if (validationArrowsTimer) window.clearTimeout(validationArrowsTimer)
  validationArrowsTimer = window.setTimeout(dismissValidationArrows, 8000)
}
const saving = ref(false)
// Серверные ошибки валидации по полям: {desired_date: 'неверный формат даты'}.
// Биндим в :error-messages → Vuetify сам рисует красную подпись (стрелочка к полю).
const serverFieldErrors = ref<Record<string, string>>({})

// Wish members
interface WishMember {
  id: number
  wish_id: number
  user_id: number
  role: string
  added_by_id: number | null
  consent_pending: boolean
  username: string | null
  full_name: string | null
  added_by_name: string | null
}
interface PendingWishConsent {
  wish_id: number
  wish_member_id: number
  title: string
  org_id: number | null
  status: string | null
  added_by_name: string | null
  created_at: string | null
}
const wishMembers = ref<WishMember[]>([])
const participantToAdd = ref<number | null>(null)
const pendingWishConsents = ref<PendingWishConsent[]>([])
const consentLoading = ref<string | null>(null)

// Wish approvers (multi-approver cascade)
interface WishApprover {
  id: number
  wish_id: number
  user_id: number | null
  order_num: number
  role_name: string | null
  full_name: string | null
  is_auto: boolean
  status: string  // pending / approved / rejected / skipped
  comment: string | null
  decided_at: string | null
  decided_by_user_id: number | null
}
const wishApprovers = ref<WishApprover[]>([])
const approverTopUser = ref<number | null>(null)
const approverToAdd = ref<number | null>(null)
const approvalMode = ref<'sequential' | 'parallel'>('sequential')
const cascadeLoading = ref(false)
const decideComment = ref<Record<number, string>>({})
const decideLoading = ref<number | null>(null)

const approvalStatusColor: Record<string, string> = {
  pending: 'orange',
  approved: 'green',
  rejected: 'red',
  skipped: 'grey',
}
const approvalStatusLabel: Record<string, string> = {
  pending: 'На согласовании',
  approved: 'Согласовано',
  rejected: 'Не согласовано',
  skipped: 'Пропущено',
}

const isWishEditable = computed(() => {
  if (!editingWishId.value) return true
  const status = (wishForm.value as any).status || 'draft'
  if (['draft', 'rejected'].includes(status)) return true
  if (['approved', 'converted'].includes(status)) return !editingWish.value?.contracted_locked
  return false
})

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
// Согласующий из цепочки может менять ФЭО у отправленной заявки,
// если не согласен с выбором автора (backend PATCH /execution это разрешает)
const isChainApprover = computed(() =>
  wishApprovers.value.some(a => a.user_id === currentUserId)
)
const canEditWishFeo = computed(() =>
  canAssigneeAct.value
  || (!!editingWish.value && editingWish.value.status === 'submitted' && isChainApprover.value)
)
// Зеркало backend-гейта PATCH /wishes/{id}/execution: assigned_to может менять
// менеджер/админ, согласующий цепочки или сам назначенный (при статусах submitted/approved)
const canEditAssignee = computed(() =>
  !!editingWish.value
  && ['submitted', 'approved'].includes(editingWish.value.status)
  && (isManagerOrAdmin.value || isChainApprover.value || editingWish.value.assigned_to === currentUserId)
)

const wishForm = ref({
  title: '' as string,
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
  vat_mode: 'uniform' as string,
})

// ФЭО-дерево субсидии (узлы + листья с бюджетами) — объявлено ПОСЛЕ wishForm (TDZ)
const { feoLeaves: wishFeoLeaves, feoNodes: wishFeoNodes } = useFeoLeaves({
  subsidyId: computed(() => wishForm.value.subsidy_id),
})

// Задача владельца 2026-08-06: остаток по КАЖДОМУ узлу дерева ФЭО в шапке заявки
// (per-item таблица позиций считает свою карту сама внутри PurchaseItemsEditor).
const { nodeAmounts: wishNodeAmounts } = useFeoNodeAmounts({
  subsidyId: computed(() => wishForm.value.subsidy_id),
})

// Подсказка у переключателя «Не указывать последний уровень ФЭО»: выбранная
// категория ФЭО не конечная (есть дочерние узлы) — нужно либо углубиться до
// конечной категории, либо осознанно включить переключатель. Тот же критерий
// (node.is_leaf), что и в валидации отправки (см. saveWish).
const wishFeoSelectedNotLeaf = computed((): boolean => {
  if (wishFeoSelected.value == null) return false
  const node = wishFeoNodes.value.find(n => n.id === wishFeoSelected.value)
  return !!node && !node.is_leaf
})

// F-PLAN: собрать id всех потомков узла дерева ФЭО (по parent_id) — повторяет
// collectDescendantIds из FeoPlannedItemsSelect.vue (тот компонент не трогаем,
// у него своя копия для рендера строк; здесь нужна отдельная для валидации
// отправки — «есть ли в ветке выбранной категории плановые позиции вообще»).
function collectFeoDescendantIds(rootId: number): Set<number> {
  const childrenByParent = new Map<number, number[]>()
  for (const n of wishFeoNodes.value) {
    if (n.parent_id != null) {
      const arr = childrenByParent.get(n.parent_id) || []
      arr.push(n.id)
      childrenByParent.set(n.parent_id, arr)
    }
  }
  const result = new Set<number>()
  const stack = [rootId]
  while (stack.length) {
    const id = stack.pop() as number
    for (const childId of childrenByParent.get(id) || []) {
      if (!result.has(childId)) {
        result.add(childId)
        stack.push(childId)
      }
    }
  }
  return result
}
// Есть ли у выбранной категории ФЭО (или её потомков) хоть одна плановая позиция
// плана закупок — если нет, блок «выберите плановую позицию» не имеет смысла
// требовать при отправке (см. saveWish).
const wishFeoBranchHasPlannedItems = computed((): boolean => {
  if (wishFeoSelected.value == null) return false
  const ids = collectFeoDescendantIds(wishFeoSelected.value)
  ids.add(wishFeoSelected.value)
  return wishPlannedResiduals.value.some(r => ids.has(r.category_id))
})

// F-PLAN: остатки плановых позиций плана закупок (Ур.5 ФЭО) для текущей субсидии,
// с исключением брони самой редактируемой заявки (иначе её же позиции «съедали» бы остаток).
const {
  plannedResiduals: wishPlannedResiduals,
  plannedByCategory: wishPlannedByCategory,
  plannedLoading: wishPlannedLoading,
  reloadPlanned: reloadWishPlanned,
} = useFeoPlannedResiduals({
  subsidyId: computed(() => wishForm.value.subsidy_id),
  excludeWishId: computed(() => editingWishId.value),
})

// БАГ 3 (сессия 2026-08-05): FeoPlannedItemsSelect создаёт плановую позицию прямо в
// форме (POST /feo-planned-items/) и эмитит 'planned-item-created' — перезагружаем
// список, чтобы «призрак»-строка (выбор указывает на id, которого ещё нет в items)
// исчез и подтянулись реальные план/остаток созданной позиции. wishPlannedResiduals
// передаётся ОДНИМ и тем же массивом во вложенные FeoPlannedItemsSelect внутри
// PurchaseItemsEditor (per-item режим) — перезагрузка тут актуализирует все разом.
async function onWishPlannedItemCreated() {
  await reloadWishPlanned()
}

// Плановые позиции выбранной категории ФЭО заявки.
const wishPlannedItemsForCategory = computed(() =>
  wishFeoSelected.value != null ? (wishPlannedByCategory.value.get(wishFeoSelected.value) ?? []) : []
)

// F-PLAN2: composite-выбор { kind, id } | null для FeoPlannedItemsSelect (шапка,
// единая привязка на всю заявку). get() восстанавливает выбор из фактического
// состояния (wishFeoPlannedItemId для kind='planned_item'; либо wishFeoSelected,
// если он сам является плановой позицией/статьёй ФЭО с планом — kind='plan_position'
// | 'feo_article'); set() пишет обратно в те же поля — см. FeoPlannedItemsSelect.vue
// (task 2) для семантики kind → куда что пишется.
const wishFeoPlanSelection = computed<FeoPlanSelection | null>({
  get() {
    if (wishFeoPlannedItemId.value != null) return { kind: 'planned_item', id: wishFeoPlannedItemId.value }
    if (wishFeoSelected.value != null) {
      const row = wishPlannedResiduals.value.find(
        r => r.category_id === wishFeoSelected.value && (r.kind === 'plan_position' || r.kind === 'feo_article')
      )
      if (row) return { kind: row.kind, id: wishFeoSelected.value }
    }
    return null
  },
  set(val) {
    if (!val) {
      wishFeoPlannedItemId.value = null
      return
    }
    if (val.kind === 'planned_item') {
      wishFeoPlannedItemId.value = val.id
    } else {
      // Плановая позиция/статья ФЭО с планом может оказаться ДОЧЕРНИМ листом
      // относительно того, что выбрано в дереве выше (см. FeoPlannedItemsSelect) —
      // уточняем категорию заявки до конкретного листа.
      wishFeoPlannedItemId.value = null
      wishFeoSelected.value = val.id
    }
  },
})

// Шаг 4 плана zany-fluttering-mountain.md: «когда заявки заведены, и если в субсидии
// уже есть плановая позиция, предлагать плановые позиции, похожие по имени... человек
// может подтвердить, что позиция выбрана правильно, а может отвергнуть и выбрать свою».
// Раньше (naive) сравнение шло через .includes() без score, брало первое попавшееся —
// заменено на POST /feo-planned-items/match (тот же token+stem движок, что и
// сопоставление товара с каталогом, см. app/services/text_match.py).
const { matchQueries: feoMatchQueries } = useFeoPlanMatching()
const wishFeoPlanCandidates = ref<FeoMatchCandidate[]>([])
// Кандидат, для которого пользователь нажал «Привязать» (FeoPlannedItemsSelect
// candidate-confirmed) — после успешного сохранения заявки шлём флаг подтверждения
// (POST /feo-planned-items/confirm-wish-plan-match), см. confirmWishPlanMatchIfNeeded.
const wishFeoPlanConfirmedCandidate = ref<FeoMatchCandidate | null>(null)

async function _runFeoPlanMatch() {
  const subsidyId = wishForm.value.subsidy_id
  if (!subsidyId || wishFeoPerItem.value) { wishFeoPlanCandidates.value = []; return }
  const names = Array.from(new Set(
    wishForm.value.items.map((i: any) => (i.item_name || '').trim()).filter(Boolean)
  ))
  if (!names.length) { wishFeoPlanCandidates.value = []; return }
  try {
    const results = await feoMatchQueries(names, subsidyId, wishFeoSelected.value)
    const byKey = new Map<string, FeoMatchCandidate>()
    for (const r of results) {
      for (const c of r.candidates) {
        const prev = byKey.get(c.key)
        if (!prev || c.score > prev.score) byKey.set(c.key, c)
      }
    }
    wishFeoPlanCandidates.value = Array.from(byKey.values()).sort((a, b) => b.score - a.score).slice(0, 5)
  } catch {
    wishFeoPlanCandidates.value = []
  }
}

let _feoMatchTimer: ReturnType<typeof setTimeout> | null = null
watch(
  () => [
    wishForm.value.subsidy_id,
    wishFeoSelected.value,
    wishFeoPerItem.value,
    wishForm.value.items.map((i: any) => i.item_name).join('|'),
  ] as const,
  () => {
    if (_feoMatchTimer) clearTimeout(_feoMatchTimer)
    _feoMatchTimer = setTimeout(_runFeoPlanMatch, 400)
  },
  { immediate: true },
)

// Кандидаты для UI FeoPlannedItemsSelect: не показываем, если привязка уже выбрана
// (нечего предлагать взамен уже выбранного) — компонент сам делит на «своя категория» /
// «другая категория» (same_category), см. FeoPlannedItemsSelect.vue.
const wishFeoPlanCandidatesForUi = computed((): FeoMatchCandidate[] =>
  wishFeoPlanSelection.value ? [] : wishFeoPlanCandidates.value
)

// Старый чип «Похоже совпадает» (suggestKey/suggestReason) — сохранён для обратной
// совместимости отображения, теперь питается лучшим score-кандидатом своей категории
// вместо наивного includes().
const wishFeoPlanSuggestKey = computed(() => {
  const best = wishFeoPlanCandidatesForUi.value.find(c => c.same_category)
  return best ? best.key : null
})
const wishFeoPlanSuggestReason = computed(() => {
  const best = wishFeoPlanCandidatesForUi.value.find(c => c.same_category)
  return best ? `Похоже на «${best.name}» (${Math.round(best.score * 100)}%)` : null
})

function onWishFeoCandidateConfirmed(c: FeoMatchCandidate) {
  wishFeoPlanConfirmedCandidate.value = c
}

// Ручной выбор (клик по строке полного списка) отличается от подтверждения кандидата —
// если выбор разошёлся с подтверждённым кандидатом, флаг подтверждения больше не про
// текущую привязку, сбрасываем.
watch(wishFeoPlanSelection, (val) => {
  const confirmed = wishFeoPlanConfirmedCandidate.value
  if (!confirmed) return
  if (!val || `${val.kind}:${val.id}` !== confirmed.key) {
    wishFeoPlanConfirmedCandidate.value = null
  }
})

/** После успешного сохранения заявки — фиксирует флаг «подтвердил человек» на бэкенде
 *  (прямой UPDATE в обход create_wish/update_wish, см. backend docstring). Сама привязка
 *  (feo_planned_item_id) уже сохранена обычным путём — это только про флаг. */
async function confirmWishPlanMatchIfNeeded(wishId: number | null | undefined) {
  const c = wishFeoPlanConfirmedCandidate.value
  if (!c || !wishId) return
  try {
    await apiFetch('/feo-planned-items/confirm-wish-plan-match', {
      method: 'POST',
      body: { wish_id: wishId, kind: c.kind, target_id: c.id },
    })
  } catch {
    // Не критично — сама привязка уже сохранена; флаг подтверждения — вспомогательный
    // UI-признак, не гейт бизнес-логики (см. backend docstring confirm_wish_plan_match).
  }
  wishFeoPlanConfirmedCandidate.value = null
}

// ФЭО заявки не найдена в текущем дереве субсидии → категорию удалили/пересоздали.
// Владелец, 2026-08-11: раньше согласование не блокировалось (backend молча обнулял
// и создавал закупку без ФЭО) — именно так реальная заявка №32 лишилась категории.
// Теперь backend отвечает 409 (missing_feo_category) — подсказываем выбрать
// актуальную категорию ДО попытки согласовать.
const wishFeoStale = computed(() => {
  const id = wishFeoSelected.value
  return !!id && wishFeoNodes.value.length > 0 && !wishFeoNodes.value.some(n => n.id === id)
})

// Жёсткий гейт «без категории ФЭО заявку нельзя согласовать» (владелец, 2026-08-11):
// зеркалит backend _ensure_feo_categories_assigned на фронте, чтобы блокировать
// отправку ДО запроса, а не только показывать ошибку после отказа 409. Эффективная
// категория позиции — её собственная (в режиме «разные ФЭО для каждого товара»),
// иначе — категория заявки целиком (wishFeoSelected), см. payload в saveWish.
const wishItemsMissingFeoCategory = computed(() => {
  const items = (wishForm.value.items as any[]).filter(
    (it) => (it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity)
  )
  if (!items.length) return [] as any[]
  return items.filter((it) => {
    const eff = wishFeoPerItem.value ? (it.feo_category_id ?? wishFeoSelected.value) : wishFeoSelected.value
    return eff == null
  })
})
const wishFeoCategoryMissing = computed(() => wishItemsMissingFeoCategory.value.length > 0)

function highlightMissingFeoCategory() {
  const formEl = wishFormRef.value?.$el as HTMLElement | undefined
  const btn = (wishSubmitBtnRef.value?.$el ?? wishSubmitBtnRef.value) as HTMLElement | null
  const target = formEl?.querySelector('[data-field="feo_category"]') as HTMLElement | null
  if (!target) return
  target.scrollIntoView({ behavior: 'smooth', block: 'center' })
  target.classList.add('wish-date-missing-pulse')
  setTimeout(() => target.classList.remove('wish-date-missing-pulse'), 3000)
  if (btn) {
    validationArrowFrom.value = btn
    validationArrowTargets.value = [target]
    validationArrowsActive.value = true
    if (validationArrowsTimer) window.clearTimeout(validationArrowsTimer)
    validationArrowsTimer = window.setTimeout(dismissValidationArrows, 8000)
  }
}

// Phase 31-07: Undo/Redo for wish edit form (WishDistributionCard is display-only;
// actual wish editing happens here in WishesView via wishForm ref)
const undoRedoWish = useUndoRedo(wishForm as any)
let _wishPendingBlur: { field: string; before: unknown } | null = null
const _wishFocusinHandler = (e: FocusEvent) => {
  const t = e.target as HTMLElement | null
  if (!t) return
  const field = t.dataset?.field || (t.closest('[data-field]') as HTMLElement | null)?.dataset?.field
  if (!field) return
  _wishPendingBlur = { field, before: (wishForm.value as any)[field] }
}
const _wishFocusoutHandler = (e: FocusEvent) => {
  if (!_wishPendingBlur) return
  const t = e.target as HTMLElement | null
  if (!t) return
  const field = t.dataset?.field || (t.closest('[data-field]') as HTMLElement | null)?.dataset?.field
  if (field && field === _wishPendingBlur.field) {
    undoRedoWish.push(field, _wishPendingBlur.before, (wishForm.value as any)[field])
  }
  _wishPendingBlur = null
}
onMounted(() => {
  document.addEventListener('focusin', _wishFocusinHandler, true)
  document.addEventListener('focusout', _wishFocusoutHandler, true)
})
onBeforeUnmount(() => {
  document.removeEventListener('focusin', _wishFocusinHandler, true)
  document.removeEventListener('focusout', _wishFocusoutHandler, true)
})

// Watchers зависят от wishForm — объявлены ПОСЛЕ его ref, иначе immediate:true
// дёргает getter в TDZ (ReferenceError: Cannot access 'wishForm' before initialization)
watch(() => wishForm.value.subsidy_id, (sid) => { loadOrgMembers(sid) }, { immediate: true })

// F-PLAN: при включении «Не указывать последний уровень ФЭО» плановые позиции
// недоступны (см. skipLast в FeoPlannedItemsSelect) — сбрасываем выбор.
watch(wishFeoSkipLast, (v) => {
  if (v) wishFeoPlannedItemId.value = null
})

// Items computed total
const totalNmck = computed(() =>
  wishForm.value.items.reduce((sum, i) => sum + (i.total_price || 0), 0)
)

// Предзаполнение диалога «Создать в плане закупок» шапки заявки (FeoPlannedItemsSelect
// без per-item ФЭО) — берём первую позицию с непустым наименованием (имя/количество/
// единица), сумму — totalNmck (весь план заявки), а не total_price одной позиции.
const wishFeoPlannedPrefill = computed(() => {
  const first = wishForm.value.items.find(i => (i.item_name || '').trim())
  return {
    name: first?.item_name ?? null,
    quantity: first?.quantity ?? null,
    unit: first?.unit ?? null,
    amount: totalNmck.value,
  }
})

function onSubsidyChange() {
  wishFeoSelected.value = null
  wishForm.value.assigned_to = null
  wishForm.value.event_id = null
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
const downloadingExcelId = ref<number | null>(null)

// Snackbar — единый механизм (useToast + ToastContainer, смонтирован в App.vue).
// По умолчанию уведомление НЕ исчезает само (duration=0): результат действия
// пользователя (согласование, сохранение, ошибка) должен быть прочитан, а не
// пропасть за 3-4 секунды. Стек не затирает предыдущие — новые тосты копятся.
const toast = useToast()

function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

// «Не определена» — парковка категории заявки (вызывается из @pick-unallocated каскада)
async function pickWishUnallocated(parentId: number | null) {
  const sid = wishForm.value.subsidy_id
  if (!sid) return
  try {
    const body: Record<string, unknown> = { subsidy_id: sid }
    if (parentId != null) body.parent_id = parentId
    const cat = await apiFetch<{ id: number; name: string; parent_id?: number | null }>('/feo-categories/unallocated', {
      method: 'POST',
      body: JSON.stringify(body),
    })
    // Добавить в wishFeoNodes если отсутствует, пометив родителя not-leaf
    if (!wishFeoNodes.value.find(n => n.id === cat.id)) {
      const parentNode = cat.parent_id != null ? wishFeoNodes.value.find(n => n.id === cat.parent_id) : null
      const newNode = { id: cat.id, name: cat.name, parent_id: cat.parent_id ?? null, level: parentNode ? parentNode.level + 1 : 1, is_leaf: true } as any
      const updated = [...wishFeoNodes.value, newNode]
      if (cat.parent_id != null) {
        const pi = updated.findIndex(n => n.id === cat.parent_id)
        if (pi !== -1) updated[pi] = { ...updated[pi], is_leaf: false }
      }
      wishFeoNodes.value = updated
    }
    wishFeoSelected.value = cat.id
    wishFeoSkipLast.value = false
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Ошибка получения категории «Не определена»', 'error')
  }
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
    title: '',
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
    vat_mode: 'uniform',
  }
  wishFeoSelected.value = null
  wishFeoSkipLast.value = false
  wishFeoPerItem.value = false
  wishFeoPlannedItemId.value = null
  wishDateMode.value = 'common'
  // Шаг 4 плана zany-fluttering-mountain.md — не тащить кандидатов/подтверждение
  // от предыдущего открытого диалога в новый.
  wishFeoPlanCandidates.value = []
  wishFeoPlanConfirmedCandidate.value = null
}

function openCreateDialog() {
  editingWishId.value = null
  editingWish.value = null
  wishMembers.value = []
  wishApprovers.value = []
  approverTopUser.value = null
  approverToAdd.value = null
  approvalMode.value = 'sequential'
  resetForm()
  undoRedoWish.clear() // Phase 31-07: fresh stack per dialog open
  wishDialog.value = true
}

async function openEditDialog(wish: Wish) {
  undoRedoWish.clear() // Phase 31-07: fresh stack per dialog open
  editingWishId.value = wish.id
  editingWish.value = wish
  resetForm()
  wishForm.value.title = wish.title || ''
  wishForm.value.subsidy_id = wish.subsidy_id ?? null
  loadOrgMembers(wishForm.value.subsidy_id)
  wishForm.value.feo_category_id = wish.feo_category_id ?? null
  wishForm.value.assigned_to = wish.assigned_to ?? null
  wishForm.value.event_id = (wish as any).event_id ?? null
  wishForm.value.executor_id = (wish as any).executor_id ?? null
  wishForm.value.execution_deadline = (wish as any).execution_deadline ? String((wish as any).execution_deadline).slice(0, 10) : ''
  wishForm.value.justification = wish.justification || ''
  wishForm.value.priority = wish.priority || 'medium'
  wishForm.value.desired_date = wish.desired_date || ''
  wishForm.value.status = wish.status || 'draft'
  wishForm.value.vat_mode = (wish as any).vat_mode || 'uniform'
  forceStatusValue.value = wish.status || 'draft'

  // B5 — Seed cascade from wish.feo_category_id (цепочку строит сам FeoCascadeSelect).
  // Владелец: переключатель «Не указывать последний уровень ФЭО» не должен включаться
  // сам при открытии заявки — только пользователь решает. Раньше здесь стоял
  // автоподъём wishFeoSkipLast при наличии дочерних узлов у сохранённой категории —
  // убран. Если категория не конечная, это отражается подсказкой у переключателя
  // (см. wishFeoSelectedNotLeaf) и валидацией при отправке.
  wishFeoSelected.value = wish.feo_category_id ?? null

  // Открываем диалог СРАЗУ после синхронного заполнения формы — пользователь
  // видит окно мгновенно, а тяжёлая загрузка позиций идёт под спиннером.
  wishDialog.value = true
  wishDialogLoading.value = true

  try {
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
    // Also build a by-id map to hydrate _photo_url on positions that already have
    // a product_id (most catalog products have photos, but the editor never set
    // _photo_url for existing items → only a placeholder icon was shown).
    const needsBackfill = rawItems.some((i: any) => !i.product_id && i.item_name)
    const hasProductIds = rawItems.some((i: any) => i.product_id != null)
    let byId = new Map<number, any>()
    if (needsBackfill || hasProductIds) {
      try {
        const products = await apiFetch<any[]>('/products/?limit=10000')
        const byName = new Map<string, any>(
          (products || []).map((p: any) => [(p.name || '').trim().toLowerCase(), p])
        )
        byId = new Map<number, any>((products || []).map((p: any) => [p.id, p]))
        for (const it of rawItems) {
          if (!it.product_id && it.item_name) {
            const hit = byName.get(it.item_name.trim().toLowerCase())
            if (hit) it.product_id = hit.id
          }
        }
      } catch {}
    }

    // Mirror of the editor's productPhotoSrc logic.
    const photoOf = (p: any): string | undefined => {
      if (!p) return undefined
      if (p.has_photo) return `/api/products/${p.id}/photo`
      return p.photo_url || p.photo_link || undefined
    }

    wishForm.value.items = rawItems.map((i: any) => {
      const prod = i.product_id != null ? byId.get(i.product_id) : null
      return {
        // ⚠️ БЕЗ id ветка PUT (non-draft) матчит позиции по id и молча игнорирует
        // ВСЕ правки позиций уже согласованной заявки — самостоятельный баг, не связанный с ФЭО.
        id: i.id ?? null,
        product_id: i.product_id ?? null,
        item_name: i.item_name || '',
        item_type: i.item_type || 'товар',
        quantity: i.quantity != null ? Number(i.quantity) : null,
        unit: i.unit || 'шт.',
        unit_price: i.unit_price != null ? Number(i.unit_price) : null,
        total_price: i.total_price != null ? Number(i.total_price) : null,
        country_origin: i.country_origin || 'РФ',
        feo_category_id: i.feo_category_id ?? null,
        feo_planned_item_id: i.feo_planned_item_id ?? null,
        over_plan: i.over_plan ?? false,
        vat_rate: i.vat_rate ?? null,
        needed_date: i.needed_date ?? null,
        _photo_url: prod ? photoOf(prod) : undefined,
        _description: prod?.description || undefined,
      }
    }) as any
    // Режим читаем из БД; фолбэк-эвристика — ТОЛЬКО для записей, созданных до появления
    // колонки (feo_per_item === undefined/null). Если в БД явно сохранено false — это
    // осознанный выбор владельца (выключил тумблер и сохранил), эвристика по позициям
    // НЕ должна его перебивать (правило проекта: выбранное на предыдущем этапе не смеет
    // меняться само). Запоминаем explicit-флаг отдельно для проверки ниже.
    const wishFeoPerItemFromDb = (wish as any).feo_per_item
    wishFeoPerItem.value = wishFeoPerItemFromDb ?? rawItems.some((i: any) => i.feo_category_id != null)

    // F-PLAN: восстановить привязку к плановым позициям плана закупок из фактических
    // значений позиций (отдельной колонки wishes.feo_planned_item_id нет и не будет).
    // БАГ 3 (сессия 2026-08-05): «вне плана» (over_plan) больше не отражается в шапке —
    // псевдо-вариант убран из UI; поле в БД у старых позиций может остаться true, но
    // header-состояние теперь целиком определяется feo_planned_item_id.
    {
      const items = wishForm.value.items as any[]
      const plannedIds = items.map(it => it.feo_planned_item_id)
      const nonNullPlannedIds = plannedIds.filter(id => id != null)
      if (nonNullPlannedIds.length === 0) {
        wishFeoPlannedItemId.value = null
      } else if (nonNullPlannedIds.length === plannedIds.length && new Set(nonNullPlannedIds).size === 1) {
        // Все позиции привязаны к ОДНОЙ и той же плановой позиции — единое значение в шапке
        wishFeoPlannedItemId.value = nonNullPlannedIds[0]
      } else {
        // Привязки разные у разных позиций ИЛИ часть пустая — единый выбор в шапке не
        // отразит это корректно, переключаем в режим «по позициям» (как per-item ФЭО).
        // НО: если владелец явно сохранил feo_per_item=false, эта эвристика его не трогает —
        // иначе выключенный вручную режим включался бы обратно сам собой при переоткрытии.
        if (wishFeoPerItemFromDb !== false) {
          wishFeoPerItem.value = true
        }
        wishFeoPlannedItemId.value = null
      }
    }
    wishDateMode.value = (wishForm.value.items as any[]).some(it => it.needed_date) ? 'per_item' : 'common'
    await loadWishMembers()
    await loadWishApprovers()
    approvalMode.value = ((wish as any).approval_mode === 'parallel') ? 'parallel' : 'sequential'
  } finally {
    wishDialogLoading.value = false
  }
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
      feo_category_id: wishFeoSelected.value || wishForm.value.feo_category_id,
      assigned_to: wishForm.value.assigned_to,
    }
    await apiFetch(`/wishes/${editingWishId.value}/execution`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    })
    showSnack('Сохранено: исполнитель / срок / мероприятие / ФЭО / получатель')
    await reloadActiveTab()
  } catch (e: any) {
    showSnack(`Ошибка: ${e?.message || e?.payload?.message || 'не удалось сохранить'}`, 'error')
  } finally {
    savingExecution.value = false
  }
}

// Быстрое сохранение поля «На чьё имя будет заявка» без полного saveExecution
async function saveAssignedTo(val: number | null) {
  if (!editingWishId.value) return
  try {
    await apiFetch(`/wishes/${editingWishId.value}/execution`, {
      method: 'PATCH',
      body: JSON.stringify({ assigned_to: val }),
    })
    if (editingWish.value) editingWish.value.assigned_to = val as number
    showSnack('Исполнитель обновлён')
    await reloadActiveTab()
  } catch (e: any) {
    showSnack(`Ошибка: ${e?.payload?.message || e?.message || 'не удалось сохранить'}`, 'error')
  }
}

// Wish members functions
async function loadWishMembers() {
  if (!editingWishId.value) { wishMembers.value = []; return }
  try {
    wishMembers.value = await apiFetch<WishMember[]>(`/wishes/${editingWishId.value}/members`)
  } catch { wishMembers.value = [] }
}
async function addWishMember(userId: number | null) {
  participantToAdd.value = null
  if (!userId) return
  if (wishMembers.value.some(m => m.user_id === userId)) return
  // Новая (ещё не сохранённая) заявка: у участников нет wish_id, поэтому копим их
  // локально и прикрепляем сразу после создания черновика в saveWish. Это и есть
  // «совместное создание» — люди выбираются до первого сохранения.
  if (!editingWishId.value) {
    const u = orgUsers.value.find((x: any) => x.id === userId)
    wishMembers.value.push({
      id: -userId, wish_id: 0, user_id: userId, role: 'participant',
      added_by_id: null, consent_pending: false,
      username: u?.username ?? null, full_name: u?.full_name ?? null,
    } as WishMember)
    return
  }
  try {
    await apiFetch(`/wishes/${editingWishId.value}/members`, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, role: 'participant' }),
    })
    await loadWishMembers()
    showSnack('Участник добавлен')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось добавить участника', 'error')
  }
}
async function removeWishMember(userId: number) {
  if (!editingWishId.value) {
    wishMembers.value = wishMembers.value.filter(m => m.user_id !== userId)
    return
  }
  try {
    await apiFetch(`/wishes/${editingWishId.value}/members/${userId}`, { method: 'DELETE' })
    await loadWishMembers()
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось удалить участника', 'error')
  }
}
// Wish approvers functions
async function loadWishApprovers() {
  if (!editingWishId.value) { wishApprovers.value = []; return }
  try {
    wishApprovers.value = await apiFetch<WishApprover[]>(`/wishes/${editingWishId.value}/approvers`)
  } catch { wishApprovers.value = [] }
}
// Общий вызов API построения цепочки — переиспользуется кнопкой «Построить
// цепочку» и молчаливым автопостроением при отправке на согласование.
async function callCascadeApi(wishId: number, topUserId: number) {
  return apiFetch<{ approval_mode: string; approvers: WishApprover[]; warning?: string | null }>(
    `/wishes/${wishId}/approvers/cascade`,
    { method: 'POST', body: JSON.stringify({ top_user_id: topUserId, mode: approvalMode.value }) },
  )
}
async function runCascade() {
  if (!editingWishId.value) { showSnack('Сначала сохраните заявку', 'warning'); return }
  if (!approverTopUser.value) { showSnack('Выберите верхнего согласующего', 'warning'); return }
  cascadeLoading.value = true
  try {
    const res = await callCascadeApi(editingWishId.value, approverTopUser.value)
    wishApprovers.value = res.approvers
    approverTopUser.value = null
    if (res.warning) {
      showSnack(`Цепочка построена. Внимание: ${res.warning}`, 'warning')
    } else {
      showSnack('Цепочка построена. Заявка уйдёт на согласование после кнопки «Отправить на согласование»')
    }
    await loadWishOnce()
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось построить цепочку', 'error')
  } finally {
    cascadeLoading.value = false
  }
}
// Молчаливый фолбэк для отправки на согласование: пользователь выбрал
// «Верхнего согласующего», но не нажал «Построить цепочку» — строим её сами,
// чтобы не ругать снэкбаром на пустой список согласующих.
async function ensureApprovers(wishId: number): Promise<boolean> {
  if (wishApprovers.value.length > 0) return true
  if (!approverTopUser.value) return false
  try {
    const res = await callCascadeApi(wishId, approverTopUser.value)
    if (res.approvers.length > 0) {
      wishApprovers.value = res.approvers
    } else {
      // Цепочка не построилась (например, у выбранного нет руководителей) —
      // добавляем хотя бы его самого вручную и перечитываем список.
      await apiFetch(`/wishes/${wishId}/approvers`, {
        method: 'POST', body: JSON.stringify({ user_id: approverTopUser.value }),
      })
      await loadWishApprovers()
    }
    approverTopUser.value = null
    if (res.warning) {
      showSnack(`Цепочка построена автоматически. Внимание: ${res.warning}`, 'warning')
    } else {
      showSnack('Цепочка согласования построена автоматически')
    }
    return wishApprovers.value.length > 0
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось построить цепочку согласования', 'error')
    return false
  }
}
async function addApprover(userId: number | null) {
  approverToAdd.value = null
  if (!userId || !editingWishId.value) return
  if (wishApprovers.value.some(a => a.user_id === userId)) return
  try {
    await apiFetch(`/wishes/${editingWishId.value}/approvers`, {
      method: 'POST', body: JSON.stringify({ user_id: userId }),
    })
    await loadWishApprovers()
    showSnack('Согласующий добавлен')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось добавить согласующего', 'error')
  }
}
const reorderLoading = ref(false)
async function moveApprover(idx: number, dir: number) {
  if (!editingWishId.value) return
  const j = idx + dir
  if (j < 0 || j >= wishApprovers.value.length) return
  const arr = [...wishApprovers.value]
  ;[arr[idx], arr[j]] = [arr[j], arr[idx]]
  reorderLoading.value = true
  try {
    wishApprovers.value = await apiFetch<WishApprover[]>(
      `/wishes/${editingWishId.value}/approvers/reorder`,
      { method: 'POST', body: JSON.stringify({ ids: arr.map(a => a.id) }) },
    )
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось изменить порядок согласующих', 'error')
  } finally {
    reorderLoading.value = false
  }
}
async function removeApprover(approvalId: number) {
  if (!editingWishId.value) return
  try {
    await apiFetch(`/wishes/${editingWishId.value}/approvers/${approvalId}`, { method: 'DELETE' })
    await loadWishApprovers()
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось удалить согласующего', 'error')
  }
}
async function decideApprover(approvalId: number, decision: 'approved' | 'rejected') {
  if (!editingWishId.value) return
  decideLoading.value = approvalId
  try {
    const res = await apiFetch<{ status: string; convert_error?: string | null; approvers: WishApprover[] }>(
      `/wishes/${editingWishId.value}/approvers/${approvalId}/decide`,
      { method: 'POST', body: JSON.stringify({ decision, comment: decideComment.value[approvalId] || null }) },
    )
    wishApprovers.value = res.approvers
    decideComment.value[approvalId] = ''
    if (wishForm.value) (wishForm.value as any).status = res.status
    if (res.convert_error) showSnack(res.convert_error, 'warning')
    else showSnack(decision === 'approved' ? 'Согласовано' : 'Отклонено')
    await loadWishOnce()
    await loadWishes()
    refreshMyPendingApprovals()  // бейдж «мои согласования» в сайдбаре
  } catch (e: any) {
    // Гейт ФЭО (владелец, 2026-08-11): последний согласующий цепочки может упереться
    // в 409 missing_feo_category (backend откатывает decision, заявка НЕ зависает —
    // остаётся 'submitted', попробовать decide можно снова после выбора категории).
    const handled = editingWish.value ? await handleMissingFeoCategoryError(e, editingWish.value) : false
    if (!handled) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось сохранить решение', 'error')
    }
  } finally {
    decideLoading.value = null
  }
}
// Обновить editingWish (статус) после действий с согласующими
async function loadWishOnce() {
  if (!editingWishId.value) return
  try {
    const fresh = await apiFetch<Wish>(`/wishes/${editingWishId.value}`)
    editingWish.value = fresh
    ;(wishForm.value as any).status = fresh.status
    if ((fresh as any).approval_mode) approvalMode.value = (fresh as any).approval_mode
  } catch { /* ignore */ }
}
const canDecideApprover = (a: WishApprover): boolean => {
  if (a.status !== 'pending') return false
  if ((wishForm.value as any).status !== 'submitted') return false
  const mine = a.user_id === currentUserId || isAdmin.value
  if (!mine) return false
  if (approvalMode.value === 'sequential') {
    const lowerPending = wishApprovers.value.some(x => x.order_num < a.order_num && x.status === 'pending')
    if (lowerPending) return false
  }
  return true
}

async function loadPendingWishConsents() {
  try {
    pendingWishConsents.value = await apiFetch<PendingWishConsent[]>('/wishes/members/pending-consent')
  } catch { pendingWishConsents.value = [] }
}
async function respondWishConsent(wishId: number, accept: boolean) {
  consentLoading.value = wishId + (accept ? '_a' : '_d')
  try {
    await apiFetch(`/wishes/${wishId}/members/consent?accept=${accept}`, { method: 'POST' })
    showSnack(accept ? 'Вы приняли участие в заявке' : 'Вы отклонили участие')
    await loadPendingWishConsents()
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось обработать согласие', 'error')
  } finally {
    consentLoading.value = null
  }
}

// TODO: B8 — нужен отдельный endpoint PATCH /wishes/{id}/feo для approver на submitted-заявке
async function saveWish(andSubmit = false) {
  // Черновик можно сохранить всегда — прерваться на любом этапе (даже 200 позиций,
  // часть не в каталоге). Валидацию формы требуем только при отправке на согласование.
  if (andSubmit) {
    const { valid } = await wishFormRef.value?.validate() ?? { valid: true }
    if (!valid) { await nextTick(); showValidationArrows(); return }
    // Жёсткий гейт (владелец, 2026-08-11): без категории ФЭО заявку нельзя отправить
    // на согласование — иначе одобряющий упрётся в 409 от backend, а созданная из неё
    // закупка рискует остаться сиротой вне всех планов ФЭО (см. wishFeoCategoryMissing).
    if (wishFeoCategoryMissing.value) {
      showSnack('Нельзя отправить на согласование: не выбрана категория ФЭО. Выберите категорию в дереве ниже (или для каждой позиции), либо «Не определена», если категория неизвестна.', 'error')
      await nextTick()
      highlightMissingFeoCategory()
      return
    }
    // ФЭО выбрано не до конечной категории — требуем либо лист, либо явный skipLast
    if (wishFeoSelected.value && !wishFeoSkipLast.value && !wishFeoPerItem.value) {
      const node = wishFeoNodes.value.find(n => n.id === wishFeoSelected.value)
      if (node && !node.is_leaf) {
        showSnack('Выберите конечную категорию ФЭО или включите «Не указывать последний уровень ФЭО»', 'warning')
        return
      }
    }
    // F-PLAN: в ветке выбранной категории ФЭО есть плановые позиции плана закупок, но не
    // выбрана ни одна. БАГ 3 (сессия 2026-08-05): псевдо-вариант «Вне плана» убран —
    // непривязанная позиция просто увеличит плановую сумму категории, как раньше делало
    // «вне плана», поэтому это больше НЕ блокирует отправку — только мягкое предупреждение.
    if (wishFeoBranchHasPlannedItems.value && !wishFeoPerItem.value && !wishFeoPlannedItemId.value) {
      showSnack('В этой категории ФЭО есть плановые позиции плана закупок. Выберите одну из них или создайте новую кнопкой «Создать в плане закупок» — без выбора позиция увеличит плановую сумму категории.', 'warning')
    }
    // F-PLAN: режим «разные ФЭО для каждого товара» — плановая позиция выбирается
    // в каждой строке отдельно. Аналогично выше — мягкое предупреждение, не блокирует.
    if (wishFeoBranchHasPlannedItems.value && wishFeoPerItem.value) {
      const unfilledCount = wishForm.value.items.filter((it: any) => it.feo_planned_item_id == null).length
      if (unfilledCount > 0) {
        showSnack(`У ${unfilledCount} ${unfilledCount === 1 ? 'позиции' : 'позиций'} не выбрана плановая позиция плана закупок. Выберите её или создайте новую кнопкой «Создать в плане закупок» — без выбора позиция увеличит плановую сумму категории.`, 'warning')
      }
    }
  }

  saving.value = true
  try {
    const feo = wishFeoSelected.value
    // Заголовок: приоритет — ручной «Предмет заявки»; иначе автосклейка из позиций
    // (при множестве позиций — первая + счётчик, чтобы не переполнить VARCHAR 500).
    let title = (wishForm.value.title || '').trim().slice(0, 255)
    if (!title) {
      const names = wishForm.value.items.map(i => i.item_name).filter(Boolean)
      title = names.join(', ') || 'Новая заявка'
      if (title.length > 255) {
        title = names.length > 1
          ? `${names[0].slice(0, 120)} + ещё ${names.length - 1} поз.`
          : names[0].slice(0, 252) + '…'
      }
    }
    const payload = {
      ...wishForm.value,
      feo_category_id: feo,
      feo_per_item: wishFeoPerItem.value,
      title,
      items: wishForm.value.items
        // Пустые строки-заготовки (фронт создаёт их заранее для будущего ввода) не отправляем —
        // иначе они оседают в БД как «1 шт · 0 ₽» и «удаление» позиции визуально не работает
        // (см. баг: владелец удаляет вторую пустую позицию, обновляет страницу — она снова там).
        // Строку оставляем, если заполнено хоть наименование, хоть сумма (частичный ввод).
        .filter((it: any) => (it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity))
        .map(({ _selectedProduct, _photo_url, _description, _description_44fz, ...rest }) => ({
          ...rest,
          // B9: per-item ФЭО сохраняем только в режиме «Разные ФЭО позиции»
          feo_category_id: wishFeoPerItem.value ? ((rest as any).feo_category_id ?? null) : null,
          // F-PLAN: колонки wishes.feo_planned_item_id нет — выбор из шапки проставляется
          // каждой позиции; в per-item режиме каждая строка несёт свой выбор.
          feo_planned_item_id: wishFeoPerItem.value
            ? ((rest as any).feo_planned_item_id ?? null)
            : (wishFeoPlannedItemId.value ?? null),
          // БАГ 3 (сессия 2026-08-05): UI больше не выставляет over_plan (псевдо-вариант
          // «Вне плана» убран) — колонка в БД и расчёты на бэкенде не тронуты, просто
          // отправляем то, что уже было на позиции (false для новых/непривязанных).
          over_plan: !!((rest as any).over_plan),
        })),
    }

    if (editingWishId.value) {
      const currentStatus = (wishForm.value as any).status || 'draft'
      await apiFetch(`/wishes/${editingWishId.value}`, { method: 'PUT', body: JSON.stringify(payload) })
      // Шаг 4 плана zany-fluttering-mountain.md: если пользователь подтвердил похожую
      // плановую позицию (кнопка «Привязать») — сама привязка уже ушла в payload.items
      // выше, здесь только флаг подтверждения (см. confirmWishPlanMatchIfNeeded).
      await confirmWishPlanMatchIfNeeded(editingWishId.value)
      if (andSubmit && ['draft', 'rejected'].includes(currentStatus)) {
        const hasApprovers = await ensureApprovers(editingWishId.value)
        if (!hasApprovers) {
          showSnack('Не выбраны согласующие. Выберите «Верхнего согласующего» в разделе «Согласующие» — цепочка построится автоматически.', 'error')
          return
        }
        await apiFetch(`/wishes/${editingWishId.value}/submit`, { method: 'POST' })
        showSnack('Заявка отправлена на согласование')
      } else if (['approved', 'converted'].includes(currentStatus)) {
        // Бэкенд автоматически переводит обратно в submitted при PUT — /submit не нужен
        showSnack('Заявка отправлена на повторное согласование')
        await loadWishApprovers()
      } else {
        showSnack('Заявка обновлена')
      }
    } else {
      const created = await apiFetch<any>('/wishes/', { method: 'POST', body: JSON.stringify(payload) })
      // Шаг 4 плана zany-fluttering-mountain.md — см. комментарий у PUT-ветки выше.
      await confirmWishPlanMatchIfNeeded(created?.id)
      if (andSubmit && created?.id) {
        // Переходим в режим редактирования ДО построения цепочки — ensureApprovers
        // и loadWishApprovers читают editingWishId.
        editingWishId.value = created.id
        const hasApprovers = await ensureApprovers(created.id)
        if (!hasApprovers) {
          // Черновик создан, но согласующих нет — переходим в режим редактирования
          // и объясняем, что нужно добавить согласующих перед отправкой
          showSnack('Черновик сохранён. Не выбраны согласующие. Выберите «Верхнего согласующего» в разделе «Согласующие» — цепочка построится автоматически.', 'error')
          await loadWishMembers()
          await loadWishApprovers()
          await reloadActiveTab()
          return
        }
        await apiFetch(`/wishes/${created.id}/submit`, { method: 'POST' })
        showSnack('Заявка отправлена на согласование')
      } else if (created?.id) {
        // Прикрепляем участников, выбранных до сохранения (совместное создание).
        const staged = wishMembers.value.map(m => m.user_id)
        for (const uid of staged) {
          try {
            await apiFetch(`/wishes/${created.id}/members`, {
              method: 'POST', body: JSON.stringify({ user_id: uid, role: 'participant' }),
            })
          } catch { /* дубликат/нет прав — пропускаем, не роняем сохранение */ }
        }
        // Черновик создан → переходим в режим редактирования, НЕ закрывая диалог,
        // чтобы блок «Участники заявки» остался виден и заявку можно было
        // дорасшарить нескольким людям.
        editingWishId.value = created.id
        showSnack(staged.length
          ? 'Черновик сохранён, участники добавлены'
          : 'Черновик сохранён — добавьте участников для совместной работы')
        await loadWishMembers()
        await reloadActiveTab()
        return
      }
    }

    wishDialog.value = false
    await reloadActiveTab()
  } catch (e: any) {
    // T3: 409 missing_needed_dates — не закрывать диалог, включить per-item режим
    if (editingWish.value && await handleMissingDatesError(e, editingWish.value)) {
      return
    }
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
      showValidationArrows()
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
    const handled = await handleMissingDatesError(e, wish)
    if (!handled) {
      showSnack(`Ошибка при отправке: ${e?.payload?.message || e?.message || 'неизвестная ошибка'}`, 'error')
    }
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

// T3: общий обработчик 409 missing_needed_dates — используется в approveWish/saveWish/submitWish
async function handleMissingDatesError(e: any, wish: Wish) {
  const det = e?.payload?.details
  if (e?.status !== 409 || det?.error_code !== 'missing_needed_dates') return false
  const missingIds: number[] = det.missing_item_ids || []
  const missingNames: string[] = det.missing_item_names || []
  wishConvertError.value = {
    message: det.message || e.message,
    missingItemIds: missingIds,
    missingItemNames: missingNames,
  }
  // Убедиться, что диалог открыт
  if (!wishDialog.value) {
    await openEditDialog(wish)
  }
  // Переключить в per-item режим дат и подсветить проблемные позиции
  if (missingIds.length > 0) {
    if (wishDateMode.value !== 'per_item') wishDateMode.value = 'per_item'
    await nextTick()
    highlightMissingDateItems(missingIds)
  } else {
    await nextTick()
    highlightCommonDateField()
  }
  return true
}

// Гейт ФЭО (владелец, 2026-08-11): общий обработчик 409 missing_feo_category — открывает
// диалог (если закрыт) и подсвечивает дерево категории стрелкой. Используется в
// approveWish/decideApprover — submit endpoint этот гейт не проверяет (категорию можно
// донести согласующим уже после отправки), поэтому там его вызывать не нужно.
async function handleMissingFeoCategoryError(e: any, wish: Wish): Promise<boolean> {
  const det = e?.payload?.details
  if (e?.status !== 409 || det?.error_code !== 'missing_feo_category') return false
  showSnack(det.message || e.message || 'Не выбрана категория ФЭО', 'error')
  if (!wishDialog.value) {
    await openEditDialog(wish)
  }
  await nextTick()
  highlightMissingFeoCategory()
  return true
}

async function approveWish(wish: Wish) {
  approvingId.value = wish.id
  try {
    const res = await apiFetch<{ convert_warning?: string | null }>(`/wishes/${wish.id}/approve`, { method: 'POST' })
    if (res?.convert_warning) showSnack(res.convert_warning, 'warning')
    else showSnack('Заявка одобрена')
    wishConvertError.value = null
    await reloadActiveTab()
  } catch (e: any) {
    const handled = (await handleMissingDatesError(e, wish)) || (await handleMissingFeoCategoryError(e, wish))
    if (!handled) {
      showSnack(`Ошибка при одобрении: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
    }
  } finally {
    approvingId.value = null
  }
}

// ── T3: highlight items without needed_date ──────────────────────────────
function highlightMissingDateItems(missingItemIds: number[]) {
  if (!missingItemIds.length) return
  // Find all item rows in the dialog (PurchaseItemsEditor renders them).
  // Items table rows are <tr> elements; date input is <input type="date"> inside a td.
  // We look for <input type="date"> inputs inside the dialog card.
  const dialogEl = document.querySelector('.v-dialog--active .v-card, .v-overlay--active .v-card') as HTMLElement | null
  if (!dialogEl) return

  // Find date inputs in the items section (only those in the "Дата поставки" column).
  // Each item row has an index matching wishForm.value.items order.
  // missingItemIds are WishItem.id values; we cross-reference by index.
  const items = (wishForm.value as any).items as any[]
  const missingIndexes = new Set(
    items.map((it: any, idx: number) => missingItemIds.includes(it.id) ? idx : -1).filter(i => i !== -1)
  )
  if (!missingIndexes.size) {
    // Fallback: highlight common date field
    highlightCommonDateField()
    return
  }

  // All <td v-if="showNeededDate"> cells in the items table contain a date input.
  // We count them in DOM order matching item index.
  const dateInputs = Array.from(dialogEl.querySelectorAll('td input[type="date"]')) as HTMLInputElement[]
  const highlighted: HTMLElement[] = []
  missingIndexes.forEach(idx => {
    const inp = dateInputs[idx]
    if (inp) highlighted.push(inp.closest('td') as HTMLElement || inp)
  })

  if (!highlighted.length) {
    highlightCommonDateField()
    return
  }

  // Scroll to first highlighted element
  highlighted[0].scrollIntoView({ behavior: 'smooth', block: 'center' })

  // Apply pulse highlight animation
  highlighted.forEach(el => {
    el.classList.add('wish-date-missing-pulse')
    setTimeout(() => el.classList.remove('wish-date-missing-pulse'), 3000)
  })
}

function highlightCommonDateField() {
  // Highlight the "Желаемая дата поставки" field in the dialog
  const dialogEl = document.querySelector('.v-dialog--active .v-card, .v-overlay--active .v-card') as HTMLElement | null
  if (!dialogEl) return
  // The common date field has data-field-type or we find the desired_date input
  const allDateInputs = Array.from(dialogEl.querySelectorAll('input[type="date"]')) as HTMLInputElement[]
  // The common field is near the bottom of the form, skip per-item ones (in table td)
  const commonInput = allDateInputs.find(inp => !inp.closest('td'))
  if (commonInput) {
    commonInput.scrollIntoView({ behavior: 'smooth', block: 'center' })
    const wrap = commonInput.closest('.v-field') as HTMLElement | null
    if (wrap) {
      wrap.classList.add('wish-date-missing-pulse')
      setTimeout(() => wrap.classList.remove('wish-date-missing-pulse'), 3000)
    }
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
    const _sanitized = (wish.title || '').replace(/[\\/:*?"<>|\r\n]+/g, '').replace(/\s+/g, '_').slice(0, 50)
    a.download = _sanitized ? `Служебная_записка_${_sanitized}.docx` : `Служебная_записка_заявка_${wish.id}.docx`
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

async function downloadWishExcel(wish: Wish, withPhotos: boolean = true) {
  downloadingExcelId.value = wish.id
  try {
    const token = localStorage.getItem('auth_token') || ''
    const resp = await fetch(`/api/wishes/${wish.id}/export.xlsx?with_photos=${withPhotos}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const _wishTitle = (wish.title || '').replace(/[\\/:*?"<>|\r\n]+/g, '').replace(/\s+/g, '_').slice(0, 50)
    const _suffix = withPhotos ? '' : '_без_фото'
    a.download = _wishTitle ? `Заявка_${_wishTitle}_${wish.id}${_suffix}.xlsx` : `Заявка_${wish.id}${_suffix}.xlsx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    showSnack(e?.message || 'Ошибка скачивания Excel', 'error')
  } finally {
    downloadingExcelId.value = null
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
    // Гейт ФЭО (владелец, 2026-08-11): 409 missing_feo_category — этот диалог не
    // умеет выбирать категорию, закрываем его и открываем форму заявки со стрелкой
    // к полю категории.
    const handled = convertingWish.value
      ? await handleMissingFeoCategoryError(e, convertingWish.value)
      : false
    if (handled) {
      convertDialog.value = false
    } else {
      showSnack(`Ошибка при создании закупки: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
    }
  } finally {
    convertingWishLoading.value = false
  }
}

// ── B7: ColumnHeaderMenu — per-column filter + sort ────────────────────
const colFilters = ref<Record<string, any>>({
  status: null,
  title_col: null,
  creator_name: null,
  approver_names: null,
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
  approver_names: null,
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
    result = result.filter(r => [r.creator_name || '', ...(r.member_names || [])]
      .join(' ').toLowerCase().includes(colFilters.value.creator_name.q.toLowerCase()))
  if (colFilters.value.approver_names?.type === 'text' && colFilters.value.approver_names.q)
    result = result.filter(r => wishRecipients(r).toLowerCase().includes(colFilters.value.approver_names.q.toLowerCase()))
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
      const pick = (r: any) => k === 'approver_names' ? wishRecipients(r) : r[k === 'title_col' ? 'title' : k]
      const va = pick(a) ?? ''
      const vb = pick(b) ?? ''
      const cmp = String(va).localeCompare(String(vb), 'ru', { numeric: true })
      return dir === 'asc' ? cmp : -cmp
    })
  }
  return result
}

const myWishesFiltered = computed(() => applyColFilters(myWishes.value))
const incomingWishesFiltered = computed(() => applyColFilters(incomingWishes.value))
const allWishesFiltered = computed(() => applyColFilters(allWishes.value))

// ── Card/table view toggle (primary "my" tab only) ──
const {
  mobile,
  viewMode,
  effectiveView,
  page: cardsPage,
  totalPages: cardsTotalPages,
  paged: pagedWishes,
} = useCardView({
  storageKey: 'wishes_view_mode',
  source: () => myWishesFiltered.value,
  pageSize: 24,
})

watch(activeTab, (v) => {
  if (v === 'my') loadWishes()
  else if (v === 'incoming') loadIncoming()
  else if (v === 'all') loadAllWishes()
})

onMounted(async () => {
  await Promise.all([
    apiFetch<Subsidy[]>('/subsidies/?scope=wishes').then(r => { subsidies.value = r }).catch(() => {}),
    apiFetch<FeoCategory[]>('/feo-categories/').then(r => { allFeoCategories.value = r }).catch(() => {}),
    apiFetch<User[]>('/users/').then(r => { users.value = r }).catch(() => {}),
    apiFetch<EventItem[]>('/events/').then(r => { events.value = r || [] }).catch(() => {}),
    apiFetch<{ all: boolean; ids: number[] }>('/users/assignable-ids')
      .then(r => { assignableAll.value = !!r.all; assignableIds.value = new Set(r.ids || []) })
      .catch(() => {}),
    isSaas.value
      ? apiFetch<typeof allOrgs.value>('/organizations/').then(r => { allOrgs.value = r || [] }).catch(() => {})
      : Promise.resolve(),
  ])
  await loadWishes()
  await loadIncoming()
  if (isManagerOrAdmin.value) {
    await loadAllWishes()
  }
  loadPendingWishConsents()
  // Открыть диалог создания если ?create=1 (редирект из /create-order или кнопки «Добавить»)
  if (route.query.create === '1') {
    openCreateDialog()
  }
  // Deep-link: ?open={wish_id} — открыть заявку напрямую (например, переход из субсидии)
  const openId = route.query.open ? Number(route.query.open) : null
  if (openId && !isNaN(openId)) {
    try {
      const wish = await apiFetch<Wish>(`/wishes/${openId}`)
      if (wish?.id) await openEditDialog(wish)
    } catch { /* невалидный id — игнорируем */ }
  }
})
</script>

<style scoped>
.wish-dialog.v-theme--light :deep(.text-medium-emphasis) {
  color: rgba(0, 0, 0, 0.72) !important;
}
</style>

<style>
/* T3: pulse highlight for items/fields missing needed_date */
@keyframes wish-date-pulse {
  0%   { box-shadow: 0 0 0 0 rgba(211, 47, 47, 0.6); outline: 2px solid rgba(211, 47, 47, 0.8); }
  40%  { box-shadow: 0 0 0 8px rgba(211, 47, 47, 0); outline: 2px solid rgba(211, 47, 47, 0.4); }
  60%  { box-shadow: 0 0 0 0 rgba(211, 47, 47, 0); outline: 2px solid rgba(211, 47, 47, 0.8); }
  100% { box-shadow: 0 0 0 0 rgba(211, 47, 47, 0); outline: 2px solid transparent; }
}
.wish-date-missing-pulse {
  animation: wish-date-pulse 1s ease-out 3;
  border-radius: 4px;
}
/* Кнопка «заблокирована» гейтом категории ФЭО (владелец, 2026-08-11) — визуально
   приглушена, но не :disabled: клик всё равно должен сработать и показать стрелку
   к полю категории, а не молча ничего не делать. */
.wish-btn-blocked {
  opacity: 0.55;
  filter: grayscale(0.35);
}
</style>
