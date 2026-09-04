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
      <v-btn variant="tonal" size="small" prepend-icon="mdi-view-column" @click="showWishColumnPicker = true">
        Колонки
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
          <v-chip
            :color="statusColor[item.status]"
            size="small"
            variant="tonal"
            :title="item.status === 'rejected' ? rejectedByLine(item) : undefined"
          >
            {{ statusLabel[item.status] }}
          </v-chip>
        </template>
        <template #item.title_col="{ item }">
          <!-- Владелец, 2026-08-13: остановка заявки — крупный алерт на всю строку -->
          <div v-if="item.stopped_at" class="wish-stopped-banner">
            <v-icon icon="mdi-alert-octagon" size="18" class="mr-1" />
            <span class="wish-stopped-banner__title">{{ item.stopped_partial ? 'ОСТАНОВЛЕНА ЧАСТИЧНО' : 'ЗАЯВКА ОСТАНОВЛЕНА' }}</span>
            <span class="wish-stopped-banner__meta">{{ stoppedByLine(item) }}</span>
          </div>
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
        <!-- Владелец, 2026-09-02: колонка «Субсидия» — subsidy_name уже приходит в WishOut -->
        <template #item.subsidy_name="{ item }">
          {{ (item as any).subsidy_name || '—' }}
        </template>
        <template #header.subsidy_name="{ column }">
          <ColumnHeaderMenu col-key="subsidy_name" :title="column.title" col-type="enum"
            :items="wishSubsidyNameOptions"
            :model-value="colFilters.subsidy_name"
            :sort-by="colSort.subsidy_name"
            @update:model-value="v => colFilters.subsidy_name = v"
            @sort="dir => colSort.subsidy_name = dir" />
        </template>
        <!-- Владелец, 2026-08-13: сумма заявки (Σ total_price позиций) -->
        <template #item.wish_total="{ item }">
          {{ wishItemsTotal(item) != null ? formatPrice(wishItemsTotal(item)!) : '—' }}
        </template>
        <template #header.wish_total="{ column }">
          <ColumnHeaderMenu col-key="wish_total" :title="column.title" col-type="number"
            align="end"
            :model-value="colFilters.wish_total"
            :sort-by="colSort.wish_total"
            @update:model-value="v => colFilters.wish_total = v"
            @sort="dir => colSort.wish_total = dir" />
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
            <!-- Владелец (2026-09-02): «раньше суперадмин мог двигать заявки по статусам
                 самостоятельно, куда делось» — принудительная смена статуса прямо из
                 списка, без диалога правки. См. openRowForceStatus/rowForceStatusWish. -->
            <v-btn v-if="isSaas" icon="mdi-shield-crown" size="x-small" variant="text" color="red-darken-2"
              title="Принудительно сменить статус (SaaS-admin)" @click="openRowForceStatus(item)" />
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
            <v-menu v-else-if="item.status === 'converted' && item.purchase_id && (item.purchases?.length || 0) > 1">
              <template #activator="{ props: menuProps }">
                <v-btn v-bind="menuProps" size="x-small" variant="tonal" color="purple" prepend-icon="mdi-cart-arrow-right">
                  {{ wishPurchasesLabel(item) }}
                </v-btn>
              </template>
              <v-list density="compact">
                <v-list-item v-for="p in item.purchases" :key="p.id" @click="goToPurchase(p.id)">
                  <v-list-item-title>
                    {{ purchaseMenuLabel(p) }}
                    <v-chip v-if="p.stopped_at" size="x-small" color="error" variant="tonal" class="ml-1">остановлена</v-chip>
                  </v-list-item-title>
                </v-list-item>
              </v-list>
            </v-menu>
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
              <!-- Владелец, 2026-08-13: остановка заявки — крупный алерт на всю ширину карточки -->
              <div v-if="w.stopped_at" class="wish-stopped-banner ma-2 mb-0">
                <v-icon icon="mdi-alert-octagon" size="18" class="mr-1" />
                <span class="wish-stopped-banner__title">{{ w.stopped_partial ? 'ОСТАНОВЛЕНА ЧАСТИЧНО' : 'ЗАЯВКА ОСТАНОВЛЕНА' }}</span>
                <span class="wish-stopped-banner__meta">{{ stoppedByLine(w) }}</span>
              </div>
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
                <div v-if="wishItemsTotal(w) != null" class="text-caption text-medium-emphasis mb-1">
                  Сумма: <span class="font-weight-medium">{{ formatPrice(wishItemsTotal(w)!) }}</span>
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
                <!-- Владелец (2026-09-02): та же принудительная смена статуса, что и в
                     табличном виде (#item.actions выше) — см. openRowForceStatus. -->
                <v-btn v-if="isSaas" icon="mdi-shield-crown" size="x-small" variant="text" color="red-darken-2"
                  title="Принудительно сменить статус (SaaS-admin)" @click.stop="openRowForceStatus(w)" />
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
                <v-menu v-else-if="w.status === 'converted' && w.purchase_id && (w.purchases?.length || 0) > 1">
                  <template #activator="{ props: menuProps }">
                    <v-btn v-bind="menuProps" size="x-small" variant="tonal" color="purple" prepend-icon="mdi-cart-arrow-right" @click.stop>
                      {{ wishPurchasesLabel(w) }}
                    </v-btn>
                  </template>
                  <v-list density="compact">
                    <v-list-item v-for="p in w.purchases" :key="p.id" @click.stop="goToPurchase(p.id)">
                      <v-list-item-title>
                        {{ purchaseMenuLabel(p) }}
                        <v-chip v-if="p.stopped_at" size="x-small" color="error" variant="tonal" class="ml-1">остановлена</v-chip>
                      </v-list-item-title>
                    </v-list-item>
                  </v-list>
                </v-menu>
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
          <v-chip
            :color="statusColor[item.status]"
            size="small"
            variant="tonal"
            :title="item.status === 'rejected' ? rejectedByLine(item) : undefined"
          >
            {{ statusLabel[item.status] }}
          </v-chip>
        </template>
        <template #item.title_col="{ item }">
          <!-- Владелец, 2026-08-13: остановка заявки — крупный алерт на всю строку -->
          <div v-if="item.stopped_at" class="wish-stopped-banner">
            <v-icon icon="mdi-alert-octagon" size="18" class="mr-1" />
            <span class="wish-stopped-banner__title">{{ item.stopped_partial ? 'ОСТАНОВЛЕНА ЧАСТИЧНО' : 'ЗАЯВКА ОСТАНОВЛЕНА' }}</span>
            <span class="wish-stopped-banner__meta">{{ stoppedByLine(item) }}</span>
          </div>
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
        <!-- Владелец, 2026-09-02: колонка «Субсидия» — subsidy_name уже приходит в WishOut -->
        <template #item.subsidy_name="{ item }">
          {{ (item as any).subsidy_name || '—' }}
        </template>
        <template #header.subsidy_name="{ column }">
          <ColumnHeaderMenu col-key="subsidy_name" :title="column.title" col-type="enum"
            :items="wishSubsidyNameOptions"
            :model-value="colFilters.subsidy_name"
            :sort-by="colSort.subsidy_name"
            @update:model-value="v => colFilters.subsidy_name = v"
            @sort="dir => colSort.subsidy_name = dir" />
        </template>
        <!-- Владелец, 2026-08-13: сумма заявки (Σ total_price позиций) -->
        <template #item.wish_total="{ item }">
          {{ wishItemsTotal(item) != null ? formatPrice(wishItemsTotal(item)!) : '—' }}
        </template>
        <template #header.wish_total="{ column }">
          <ColumnHeaderMenu col-key="wish_total" :title="column.title" col-type="number"
            align="end"
            :model-value="colFilters.wish_total"
            :sort-by="colSort.wish_total"
            @update:model-value="v => colFilters.wish_total = v"
            @sort="dir => colSort.wish_total = dir" />
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
      <!-- Status filter chips (накопительные — см. wish_tab_statuses на бэке) -->
      <div class="d-flex flex-wrap ga-2 mb-4">
        <v-chip
          v-for="f in allFilters"
          :key="f.value"
          :color="allFilter === f.value ? 'primary' : undefined"
          :variant="allFilter === f.value ? 'flat' : 'outlined'"
          size="small"
          @click="allFilter = f.value; loadAllWishes()"
        >
          {{ f.label }}<template v-if="wishCounts[f.value] !== undefined"> ({{ wishCounts[f.value] }})</template>
        </v-chip>
      </div>
      <div v-if="allWishesTruncated" class="text-caption text-medium-emphasis mb-4">
        Показаны первые {{ allWishes.length }} из {{ allWishesTruncated }} — уточните фильтры, чтобы увидеть остальные
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
          <v-chip
            :color="statusColor[item.status]"
            size="small"
            variant="tonal"
            :title="item.status === 'rejected' ? rejectedByLine(item) : undefined"
          >
            {{ statusLabel[item.status] }}
          </v-chip>
        </template>
        <template #item.title_col="{ item }">
          <!-- Владелец, 2026-08-13: остановка заявки — крупный алерт на всю строку -->
          <div v-if="item.stopped_at" class="wish-stopped-banner">
            <v-icon icon="mdi-alert-octagon" size="18" class="mr-1" />
            <span class="wish-stopped-banner__title">{{ item.stopped_partial ? 'ОСТАНОВЛЕНА ЧАСТИЧНО' : 'ЗАЯВКА ОСТАНОВЛЕНА' }}</span>
            <span class="wish-stopped-banner__meta">{{ stoppedByLine(item) }}</span>
          </div>
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
        <!-- Владелец, 2026-09-02: колонка «Субсидия» — subsidy_name уже приходит в WishOut -->
        <template #item.subsidy_name="{ item }">
          {{ (item as any).subsidy_name || '—' }}
        </template>
        <template #header.subsidy_name="{ column }">
          <ColumnHeaderMenu col-key="subsidy_name" :title="column.title" col-type="enum"
            :items="wishSubsidyNameOptions"
            :model-value="colFilters.subsidy_name"
            :sort-by="colSort.subsidy_name"
            @update:model-value="v => colFilters.subsidy_name = v"
            @sort="dir => colSort.subsidy_name = dir" />
        </template>
        <!-- Владелец, 2026-08-13: сумма заявки (Σ total_price позиций) -->
        <template #item.wish_total="{ item }">
          {{ wishItemsTotal(item) != null ? formatPrice(wishItemsTotal(item)!) : '—' }}
        </template>
        <template #header.wish_total="{ column }">
          <ColumnHeaderMenu col-key="wish_total" :title="column.title" col-type="number"
            align="end"
            :model-value="colFilters.wish_total"
            :sort-by="colSort.wish_total"
            @update:model-value="v => colFilters.wish_total = v"
            @sort="dir => colSort.wish_total = dir" />
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
            <v-menu v-if="item.status === 'converted' && item.purchase_id && (item.purchases?.length || 0) > 1">
              <template #activator="{ props: menuProps }">
                <v-btn v-bind="menuProps" size="x-small" variant="tonal" color="purple">
                  {{ wishPurchasesLabel(item) }}
                </v-btn>
              </template>
              <v-list density="compact">
                <v-list-item v-for="p in item.purchases" :key="p.id" @click="goToPurchase(p.id)">
                  <v-list-item-title>
                    {{ purchaseMenuLabel(p) }}
                    <v-chip v-if="p.stopped_at" size="x-small" color="error" variant="tonal" class="ml-1">остановлена</v-chip>
                  </v-list-item-title>
                </v-list-item>
              </v-list>
            </v-menu>
            <v-btn
              v-else-if="item.status === 'converted' && item.purchase_id"
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
          <span>{{ editingWishId ? `Заявка №${editingWishId} — редактирование` : 'Новая заявка' }}</span>
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
        <!-- Владелец, 2026-08-19: «нужно, чтобы было видно, кто отклонил. Так удобнее
             сходить внутри офиса и спросить, что не так, или просто связаться» -->
        <div v-if="editingWish && editingWish.status === 'rejected'" class="px-4 pb-3">
          <v-alert type="error" variant="tonal" density="compact" icon="mdi-close-circle-outline">
            {{ rejectedByLine(editingWish) }}
          </v-alert>
        </div>
        <v-card-text class="pa-4">
          <!-- Владелец, 2026-08-13: остановка заявки — крупный алерт в красной рамке на всю ширину -->
          <div v-if="editingWish?.stopped_at" class="wish-stopped-banner wish-stopped-banner--large mb-3">
            <v-icon icon="mdi-alert-octagon" size="26" class="mr-2" />
            <div>
              <div class="wish-stopped-banner__title">{{ editingWish.stopped_partial ? 'ЗАЯВКА ОСТАНОВЛЕНА ЧАСТИЧНО' : 'ЗАЯВКА ОСТАНОВЛЕНА' }}</div>
              <div class="wish-stopped-banner__meta">{{ stoppedByLine(editingWish) }}</div>
              <div v-if="editingWish.stopped_partial" class="wish-stopped-banner__meta mt-1">
                Часть закупок этой заявки уже прошла договор (и не останавливается) — точный список пока не отдаётся с сервера построчно. Проверьте статус позиций в разделе «Закупки».
              </div>
            </div>
          </div>
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
              Редактирование запрещено: заявка привязана к закупке — {{ editingWish.contracted_locked_reason || 'на этапе договора или позже' }}
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
                    <!-- Владелец (сессия 2026-08-19): «Должна быть возможность задать дату
                         поставки всем позициям заявки одновременно. Если позиций много,
                         заполнять каждую очень неудобно» — в режиме «на каждую позицию»
                         поле выше только дозаполняет ПУСТЫЕ позиции при переключении
                         режима (см. watch(wishDateMode)), явного массового действия не
                         было. Кнопка берёт текущее значение поля и раздаёт его всем
                         непустым позициям, ПЕРЕЗАПИСЫВАЯ уже проставленные — как и
                         единственный другой confirm() в этом файле (forceStatus), без
                         нового визуального языка. -->
                    <v-btn
                      v-if="wishDateMode === 'per_item' && isWishEditable"
                      size="small"
                      variant="text"
                      color="primary"
                      class="mt-1"
                      prepend-icon="mdi-calendar-sync-outline"
                      :disabled="!wishForm.desired_date"
                      @click="applyCommonDateToAllItems"
                    >
                      Проставить эту дату всем позициям
                    </v-btn>
                  </v-col>
                  <!-- Task 2 (сессия 2026-08-17): контрагент заявки — необязательное поле.
                       Владелец: «должна быть возможность указывать контрагента и его имя,
                       но это по желанию». Переиспользуем ContractorPicker (тот же модуль,
                       что в SubsidiesView/ContractsView), плюс ручной ввод имени, если
                       контрагента ещё нет в справочнике. -->
                  <v-col cols="12" data-field="contractor">
                    <div class="text-caption font-weight-medium mb-1">Контрагент <span class="text-medium-emphasis">(необязательно)</span></div>
                    <v-row v-if="isWishEditable || canAssigneeAct" dense>
                      <v-col cols="12" md="6">
                        <ContractorPicker
                          v-model="wishForm.contractor_id"
                          :initial-contractor="wishContractorInitial"
                          label="Из справочника"
                          hint="Необязательно. Поиск по названию или ИНН"
                          @select="onWishContractorSelect"
                        />
                      </v-col>
                      <v-col cols="12" md="6">
                        <v-text-field
                          v-model="wishForm.contractor_name"
                          label="Или впишите имя вручную"
                          variant="outlined"
                          density="compact"
                          clearable
                          hint="Если контрагента ещё нет в справочнике"
                          persistent-hint
                        />
                      </v-col>
                    </v-row>
                    <div v-else class="text-body-2">
                      {{ editingWish?.contractor_display_name || wishForm.contractor_name || '—' }}
                    </div>
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
                <!-- Владелец (сессия 2026-08-19): тумблер «Разные ФЭО позиции для каждого товара»
                     ВЕРНУЛИ — «куда ты дел переключатель между тем, что категория ФЭО для всех
                     одинаковая, плановые позиции для всех одна или не одна? Сейчас этого
                     переключателя нет, а он нужен». Был убран 2026-08-17, а следом 2026-08-19
                     убрали и дублирующую карточку «Категория ФЭО» (коммит c1225bd, «два раза
                     даёт выбирать категорию — дубляж») — без тумблера общий выбор пропал совсем.
                     Общий выбор и построчный НИКОГДА не показываются одновременно (см. v-if
                     ниже) — именно их одновременное присутствие владелец и назвал «дубляжом».
                     Тумблер переключает между режимами, по образцу закупки — CreateOrderView.vue
                     (form.feo_per_item, строки 569-577). -->
                <v-switch
                  v-if="wishForm.subsidy_id"
                  v-model="wishForm.feo_per_item"
                  label="Разные категории ФЭО для каждого товара"
                  density="compact"
                  color="primary"
                  hide-details
                  class="mb-3"
                  :disabled="!isWishEditable"
                  @update:model-value="onWishFeoPerItemChange"
                />
                <!-- data-field="feo_category" — цель для highlightMissingFeoCategory. Общая для
                     обоих режимов: внутри либо общий выбор (шапка), либо построчный — см. п.5
                     задачи 2026-08-19: без категории заявку отправить нельзя ни в одном режиме. -->
                <div data-field="feo_category">
                  <!-- Режим «одна категория и одна плановая позиция на всю заявку» (тумблер
                       выключен) — общий выбор, как раньше было в карточке «Категория ФЭО» (до
                       c1225bd) и как в шапке закупки. Скрыт, если то же самое уже показывает
                       карточка «Категория ФЭО (согласующий)» ниже (canEditWishFeo && !isWishEditable) —
                       иначе это снова тот самый дубляж, на который жаловался владелец. -->
                  <template v-if="!wishForm.feo_per_item">
                    <v-alert v-if="wishFeoStale" type="warning" density="compact" variant="tonal" class="mb-2">
                      Категория ФЭО, выбранная в заявке, была удалена из справочника (структуру ФЭО субсидии
                      пересоздавали). Выберите актуальную категорию и сохраните. Если согласовать как есть —
                      закупка будет создана без категории ФЭО, её можно задать в «Плане закупок».
                    </v-alert>
                    <v-alert
                      v-if="wishFeoCategoryMissing"
                      type="error"
                      density="compact"
                      variant="tonal"
                      class="mb-2"
                      icon="mdi-alert-octagon-outline"
                    >
                      <div class="font-weight-medium">Конечная категория ФЭО не выбрана — отправить заявку на согласование нельзя</div>
                      <div class="mt-1">
                        Без конечной категории закупка не попадёт ни в один план ФЭО и её сумма потеряется.
                        Выберите категорию ниже, углубившись до самого конечного уровня дерева, а если
                        категория неизвестна — нажмите «Не определена».
                      </div>
                    </v-alert>
                    <template v-if="wishForm.subsidy_id && !(canEditWishFeo && !isWishEditable)">
                      <FeoTreeSelect
                        v-model="wishFeoSelected"
                        :nodes="wishFeoTreeNodes"
                        :leaves="wishFeoLeaves"
                        :plan-positions="wishPlannedResiduals"
                        :node-amounts="wishNodeAmounts"
                        horizontal
                        :readonly="!isWishEditable && !canEditWishFeo"
                        :allow-unallocated="!!(wishForm.subsidy_id && (isWishEditable || canEditWishFeo))"
                        :root-label="selectedSubsidyName"
                        @pick-unallocated="(parentId: number | null) => pickWishUnallocated(parentId)"
                      />
                      <!-- Владелец (сессия 2026-08-21): «эта таблица с плановыми ничего не
                           даёт, т.к. каждому товару надо присваивать свою плановую» — шапочный
                           общий выбор плановой позиции убран целиком (в обоих режимах). Выбор
                           плановой — ТОЛЬКО построчно в таблице «Позиции» ниже
                           (:allow-per-item-plan="true" у PurchaseItemsEditor), там же остаётся
                           корзинка удаления случайно созданной плановой позиции. -->
                    </template>
                  </template>
                  <!-- Режим «каждой позиции своя категория» (тумблер включён) — построчный выбор,
                       как было единственным режимом 2026-08-17..08-19. Общий выбор выше СКРЫТ. -->
                  <template v-else>
                    <!-- Было wishFeoStale (для категории шапки) — теперь по каждой позиции: своя
                         feo_category_id ссылается на узел, которого больше нет в дереве субсидии
                         (структуру ФЭО пересоздавали). См. wishItemsWithStaleFeoCategory. -->
                    <v-alert v-if="wishItemsWithStaleFeoCategory.length" type="warning" density="compact" variant="tonal" class="mb-2">
                      У части позиций категория ФЭО была удалена из справочника (структуру ФЭО субсидии
                      пересоздавали). Выберите актуальную категорию у этих позиций и сохраните — иначе
                      закупка будет создана без категории ФЭО.
                      <ul class="ml-4 mt-1">
                        <li v-for="(it, idx) in wishItemsWithStaleFeoCategory" :key="'stale-' + idx">{{ it.item_name || 'без названия' }}</li>
                      </ul>
                    </v-alert>
                    <!-- Жёсткий гейт (владелец, 2026-08-11, переведён на позиции 2026-08-19, тумблер
                         «Не указывать последний уровень ФЭО» убран в тот же день): без КОНЕЧНОЙ
                         категории ФЭО хотя бы у одной непустой позиции заявку нельзя согласовать/
                         отправить в План закупок — иначе закупка остаётся сиротой вне всех планов
                         ФЭО (реальный случай с прода — заявка №32). Промежуточный (нелистовой) узел
                         дерева считается таким же отсутствием категории. Блокирует кнопку
                         «Отправить на согласование», см. wishFeoCategoryMissing. -->
                    <v-alert
                      v-if="wishFeoCategoryMissing"
                      type="error"
                      density="compact"
                      variant="tonal"
                      class="mb-2"
                      icon="mdi-alert-octagon-outline"
                    >
                      <div class="font-weight-medium">Конечная категория ФЭО не выбрана — отправить заявку на согласование нельзя</div>
                      <div class="mt-1">
                        Без конечной категории закупка не попадёт ни в один план ФЭО и её сумма потеряется.
                        Выберите категорию у каждой позиции в таблице ниже, углубившись до самого конечного
                        уровня дерева, а если категория неизвестна — нажмите «Не определена» у нужной строки.
                      </div>
                      <div v-if="wishItemsMissingFeoCategory.length" class="mt-2">
                        <span class="font-weight-medium">Позиции без конечной категории:</span>
                        <ul class="ml-4 mt-1">
                          <li v-for="(it, idx) in wishItemsMissingFeoCategory" :key="idx">{{ it.item_name || 'без названия' }}</li>
                        </ul>
                      </div>
                    </v-alert>
                  </template>
                  <!-- Дефект 1 (владелец, 2026-08-20): видимый индикатор автосейва построчных
                       ФЭО-правок (правило проекта — долгая операция без индикатора запрещена).
                       Показывается только согласующему, который реально может править
                       feo-attrs-editable построчно ниже. -->
                  <div
                    v-if="!isWishEditable && canEditWishFeo && (feoAutosaveSaving || feoAutosavePending)"
                    class="d-flex align-center ga-2 mb-2 text-caption text-medium-emphasis"
                  >
                    <v-progress-circular v-if="feoAutosaveSaving" size="14" width="2" indeterminate color="primary" />
                    <v-icon v-else size="14" icon="mdi-clock-outline" />
                    {{ feoAutosaveSaving ? 'Сохранение ФЭО…' : 'Есть несохранённые изменения ФЭО — сохранятся автоматически' }}
                  </div>
                  <PurchaseItemsEditor
                    v-model="wishForm.items"
                    item-shape="purchase"
                    :purchase-id="null"
                    :wish-id="editingWishId"
                    :default-unit="'шт.'"
                    :default-country="'РФ'"
                    :allowed-item-types="['товар','услуга','работа']"
                    :supports-excel-import="true"
                    :supports-smart-import="true"
                    :supports-full-product-dialog="true"
                    :supports-photo-upload="true"
                    :readonly="!isWishEditable"
                    :feo-attrs-editable="!isWishEditable && canEditWishFeo"
                    :feo-per-item="wishForm.feo_per_item"
                    :subsidy-id="wishForm.subsidy_id"
                    :subsidy-name="selectedSubsidyName"
                    :default-feo-category-id="wishFeoSelected"
                    :feo-planned-per-item="false"
                    :allow-per-item-plan="true"
                    :planned-items="wishPlannedResiduals"
                    :show-needed-date="wishDateMode === 'per_item'"
                    :vat-mode="wishForm.vat_mode"
                    @update:vat-mode="(v: string) => { wishForm.vat_mode = v }"
                    @planned-item-created="onWishPlannedItemCreated"
                    @planned-item-deleted="onWishPlannedItemCreated"
                  />
                </div>
                <!-- Владелец, 2026-08-13: построчные пометки — что остановлено, что разошлось с
                     закупкой, что не удалось сопоставить однозначно. Данные — item.purchase_match
                     с бэка (только в карточке). ⚠️ PurchaseItemsEditor.vue вне задачи — подсветить
                     саму строку таблицы позиций отсюда нельзя, поэтому статус выведен отдельным
                     списком под таблицей, по одной строке на позицию. -->
                <div v-if="wishForm.items.some(i => wishItemStatus(i))" class="mt-2 d-flex flex-column" style="gap:4px">
                  <template v-for="(it, idx) in wishForm.items" :key="'pmstatus-' + idx">
                    <div v-if="wishItemStatus(it)" class="d-flex align-center flex-wrap" style="gap:6px">
                      <span class="text-caption" :class="it.purchase_match?.purchase_stopped_at ? 'text-medium-emphasis text-decoration-line-through' : 'text-medium-emphasis'">
                        {{ it.item_name || 'без названия' }}:
                      </span>
                      <v-chip
                        v-if="it.purchase_match?.purchase_stopped_at"
                        size="x-small" color="error" variant="tonal" prepend-icon="mdi-stop-circle-outline"
                        :style="it.purchase_match?.purchase_id ? 'cursor:pointer' : ''"
                        :title="`Закупка №${it.purchase_match?.purchase_number || it.purchase_match?.purchase_id} остановлена ${formatDate(it.purchase_match!.purchase_stopped_at!)}`"
                        @click="goToMatchedPurchase(it)"
                      >остановлена</v-chip>
                      <v-tooltip v-if="itemDiscrepancy(it)" location="top">
                        <template #activator="{ props: dTip }">
                          <v-chip
                            v-bind="dTip"
                            size="x-small" color="orange" variant="tonal" prepend-icon="mdi-alert-outline"
                            :style="it.purchase_match?.purchase_id ? 'cursor:pointer' : ''"
                            @click="goToMatchedPurchase(it)"
                          >в закупке иначе</v-chip>
                        </template>
                        <div style="white-space:pre-line">{{ itemDiscrepancy(it)!.lines.join('\n') }}</div>
                      </v-tooltip>
                      <v-tooltip v-else-if="it.purchase_match?.match_method === 'item_name_ambiguous'" location="top">
                        <template #activator="{ props: aTip }">
                          <v-chip v-bind="aTip" size="x-small" color="grey" variant="tonal" prepend-icon="mdi-help-circle-outline">
                            двойник в закупке не определён
                          </v-chip>
                        </template>
                        Под этим наименованием в закупке несколько строк ({{ it.purchase_match?.ambiguous_candidates_count }}) — различить их автоматически нельзя.
                      </v-tooltip>
                    </div>
                  </template>
                </div>
                <div class="d-flex justify-end mt-3">
                  <div class="text-subtitle-1 font-weight-bold">Сумма заявки: {{ formatMoney(totalNmck) }}</div>
                </div>
              </v-card-text>
            </v-card>

            <!-- Section: Категория ФЭО — согласующий (владелец, 2026-08-19: убрана дублирующая
                 шапка-выбор для автора заявки, см. «Позиции» выше — там теперь единственное
                 место выбора категории). Эта карточка — узкий случай: согласующий отправленной
                 заявки, не согласный с выбором автора, может переопределить категорию ЦЕЛОЙ
                 заявки одним действием (PATCH /execution, минуя полное редактирование позиций),
                 см. canEditWishFeo/saveExecution. Для самого автора/редактора (isWishEditable)
                 и для простого просмотра карточка не показывается — категории видны в таблице
                 позиций (readonly построчный выбор). -->
            <v-card v-if="wishForm.subsidy_id && !isWishEditable && canEditWishFeo" variant="outlined" class="mb-4">
              <v-card-title class="text-subtitle-1 pa-4 pb-2">
                <v-icon class="mr-2">mdi-sitemap</v-icon>Категория ФЭО (согласующий)
              </v-card-title>
              <v-card-text class="pa-4 pt-2">
                <!-- QA-фикс (2026-08-19, дефект 1 «дубляж категории ФЭО в режиме согласующего»):
                     общий выбор (шапка) имеет смысл ТОЛЬКО в режиме «одна категория на всех»
                     (wishForm.feo_per_item === false) — в режиме «каждому своя» он дублирует
                     построчные контролы, доступные согласующему прямо в таблице «Позиции»
                     (:feo-attrs-editable="!isWishEditable && canEditWishFeo" у PurchaseItemsEditor,
                     см. выше). Кнопка «Сохранить ФЭО» ниже НЕ прячется — она же сохраняет
                     построчные правки (wishItemsFeoDirtyList), это единственный Save для
                     «чистого» согласующего (не canAssigneeAct, у которого есть своя кнопка в
                     карточке «На исполнение»). -->
                <template v-if="!wishForm.feo_per_item">
                  <v-alert v-if="wishFeoStale" type="warning" density="compact" variant="tonal" class="mb-2">
                    Категория ФЭО, выбранная в заявке, была удалена из справочника (структуру ФЭО субсидии
                    пересоздавали). Выберите актуальную категорию и сохраните. Если согласовать как есть —
                    закупка будет создана без категории ФЭО, её можно задать в «Плане закупок».
                  </v-alert>
                  <FeoTreeSelect
                    v-model="wishFeoSelected"
                    :nodes="wishFeoTreeNodes"
                    :leaves="wishFeoLeaves"
                    :plan-positions="wishPlannedResiduals"
                    :node-amounts="wishNodeAmounts"
                    horizontal
                    :readonly="!isWishEditable && !canEditWishFeo"
                    :allow-unallocated="!!(wishForm.subsidy_id && (isWishEditable || canEditWishFeo))"
                    :root-label="selectedSubsidyName"
                    @pick-unallocated="(parentId: number | null) => pickWishUnallocated(parentId)"
                  />
                  <!-- Владелец (сессия 2026-08-21): шапочный перечень плановых позиций убран —
                       выбор плановой позиции построчно в таблице «Позиции» выше, доступен
                       согласующему там же (feo-attrs-editable). -->
                </template>
                <div v-else class="text-caption text-medium-emphasis mb-2">
                  Включён режим «Разные категории ФЭО для каждого товара» — категория выбирается по каждой
                  позиции в таблице «Позиции» выше.
                </div>
                <!-- Владелец (2026-08-19): для «чистого» согласующего из цепочки (не assignee/admin)
                     кнопка видна всегда (!canAssigneeAct). Для assignee/admin (canAssigneeAct — у них
                     есть свои кнопки решения «Распределить и одобрить»/«Отклонить» выше) кнопка
                     появляется ДОПОЛНИТЕЛЬНО, только когда они что-то поменяли построчно в
                     категориях/плановых позициях ФЭО (wishItemsFeoDirty) — иначе не мешает их обычному
                     сценарию одобрения. -->
                <div v-if="!canAssigneeAct || wishItemsFeoDirty" class="mt-2">
                  <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-content-save"
                         :loading="savingExecution" @click="saveExecution">
                    Сохранить ФЭО
                  </v-btn>
                  <span class="text-caption text-medium-emphasis ml-2">
                    Вы согласующий — можете изменить категорию ФЭО, если не согласны с выбором автора.
                  </span>
                </div>
              </v-card-text>
            </v-card>

            <!-- Section: Дополнительно (было «Категория ФЭО» — переименовано 2026-08-19, т.к.
                 выбор категории отсюда убран; здесь остались поля, к ФЭО не относящиеся) -->
            <v-card variant="outlined" class="mb-4">
              <v-card-title class="text-subtitle-1 pa-4 pb-2">
                <v-icon class="mr-2">mdi-information-outline</v-icon>Дополнительно
              </v-card-title>
              <v-card-text class="pa-4 pt-2">
                <v-row dense>
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

            <!-- Section: Согласующие необходимости закупки (мультисогласование с авто-каскадом).
                 Владелец, 2026-08-29: развести название с согласованием ПРЕВЫШЕНИЯ плана ФЭО
                 (см. SubsidiesView.vue) — это два разных контура, пользователь их путал. -->
            <v-card v-if="isWishEditable || editingWishId" variant="outlined" class="mb-4">
              <v-card-title class="text-subtitle-1 pa-4 pb-2">
                <v-icon class="mr-2" color="primary">mdi-account-check</v-icon>
                Согласующие необходимости закупки
                <v-chip class="ml-2" size="x-small" variant="tonal">{{ wishApprovers.length }}</v-chip>
                <v-spacer />
                <v-chip size="x-small" :color="approvalMode === 'sequential' ? 'blue' : 'teal'" variant="tonal">
                  {{ approvalMode === 'sequential' ? 'Последовательно' : 'Параллельно' }}
                </v-chip>
              </v-card-title>
              <div class="text-caption text-medium-emphasis px-4 pb-2">
                Здесь подтверждают, что закупка вообще нужна. Согласование превышения плана ФЭО — отдельно, в разделе субсидии, и доступно только уполномоченным.
              </div>
              <v-card-text class="pa-4 pt-2">
                <!-- Владелец, 2026-08-19: «почему в поле „Согласующие" написано „Сохранить
                     черновик"? Там должна быть простая кнопка „Добавить согласующих"... черновик
                     должен сохраняться автоматически». Кнопка сама сохраняет черновик молча
                     (переиспользует saveWish) и сразу скроллит/фокусирует «Верхнего
                     согласующего» — отдельно сохранять вручную больше не нужно. -->
                <v-alert
                  v-if="!editingWishId"
                  type="info"
                  variant="tonal"
                  density="compact"
                  class="mb-0"
                >
                  <v-btn
                    size="small"
                    color="primary"
                    variant="flat"
                    :loading="saving"
                    prepend-icon="mdi-account-plus"
                    @click="onAddApproversClick"
                  >Добавить согласующих</v-btn>
                  <div class="mt-2 text-caption">
                    Черновик заявки сохранится автоматически, и появится возможность выбрать согласующих.
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
                    <v-col cols="12" md="6" data-field="approvers">
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
                    <div v-if="approverDecisionLine(a)" class="text-caption text-medium-emphasis mt-1">
                      {{ approverDecisionLine(a) }}
                    </div>
                    <div v-if="a.comment" class="text-caption text-medium-emphasis mt-1">
                      Комментарий: {{ a.comment }}
                    </div>
                    <!-- Действия текущего пользователя-согласующего -->
                    <div v-if="canDecideApprover(a)" class="mt-2">
                      <div v-if="isDecidingOnBehalf(a)" class="text-caption text-orange-darken-3 mb-1 d-flex align-center" style="gap:4px">
                        <v-icon size="14">mdi-account-arrow-right</v-icon>
                        Вы решаете за {{ shortName(a.full_name) || a.full_name || 'назначенного согласующего' }}
                      </div>
                      <v-textarea
                        v-model="decideComment[a.id]"
                        :label="isDecidingOnBehalf(a) ? 'Причина решения за другого (обязательно)' : 'Комментарий (необязательно при согласовании, обязателен при отказе)'"
                        variant="outlined"
                        density="compact"
                        rows="2"
                        auto-grow
                        hide-details
                        class="mb-1"
                      />
                      <div v-if="isDecidingOnBehalf(a) && !(decideComment[a.id] || '').trim()" class="text-caption text-red mb-2">
                        Укажите причину — например, что согласующий в отпуске или поручил вам решение.
                      </div>
                      <div v-else class="mb-2" />
                      <div class="d-flex" style="gap:8px">
                        <v-btn
                          color="green"
                          variant="flat"
                          size="small"
                          :loading="decideLoading === a.id"
                          :disabled="isDecidingOnBehalf(a) && !(decideComment[a.id] || '').trim()"
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
                    <!-- Задача 2: строка стала неактуальна из-за живого обновления
                    (кто-то другой согласовал/отклонил, пока диалог был открыт) —
                    вместо молчаливого исчезновения кнопок объясняем причину. -->
                    <div
                      v-else-if="a.status === 'pending' && (a.user_id === currentUserId || isAdmin) && editingWish && editingWish.status !== 'submitted'"
                      class="text-caption text-medium-emphasis mt-2"
                    >
                      Действие недоступно — статус заявки изменился на «{{ statusLabel[editingWish.status] || editingWish.status }}».
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
                      :items="WISH_FORCE_STATUS_OPTIONS"
                      label="Новый статус"
                      variant="outlined"
                      density="compact"
                      hide-details
                    />
                  </v-col>
                  <v-col cols="12" md="4">
                    <v-btn color="red-darken-2" variant="flat" block prepend-icon="mdi-flash" :loading="forcingStatus"
                      @click="async () => { if (await forceStatus()) wishDialog = false }">
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
          <!-- Владелец, 2026-08-13: копирование — доступно всегда, кто видит заявку -->
          <v-tooltip v-if="editingWishId && editingWish" location="top" text="Скопируются позиции и количества, остальное заполните заново">
            <template #activator="{ props: tipProps }">
              <v-btn v-bind="tipProps" variant="tonal" color="secondary" prepend-icon="mdi-content-copy"
                     :loading="copyingId === editingWishId" @click="copyWish(editingWish)">
                Скопировать заявку
              </v-btn>
            </template>
          </v-tooltip>
          <!-- Владелец, 2026-08-13: «останавливать могут все» — без ролевых проверок -->
          <v-btn v-if="editingWishId && editingWish && !editingWish.stopped_at" variant="tonal" color="error"
                 prepend-icon="mdi-stop-circle-outline" @click="openStopDialog(editingWish)">
            Остановить заявку
          </v-btn>
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
              {{ wishFeoCategoryMissingTooltip }}
            </v-tooltip>
          </template>
          <!-- approved/converted и editable (не contracted_locked): сохранить изменения -->
          <template v-else-if="isWishEditable && editingWish && ['approved', 'converted'].includes(editingWish.status)">
            <v-btn color="primary" variant="tonal" :loading="saving" @click="saveWish(false)">
              Сохранить изменения
            </v-btn>
            <!-- Владелец (2026-08-20): 'approved' — закупки ещё нет, кнопка её создаёт.
                 'converted' — закупка УЖЕ создана (согласование последним в цепочке или
                 «Одобрить» делает это само, см. decideApprover/approveWish) — повторный
                 POST /convert здесь раньше бился об гейт статуса, хотя всё уже готово;
                 показываем переход в готовую закупку вместо повторного создания. -->
            <v-btn v-if="isManagerOrAdmin && editingWish.status === 'approved'" color="primary" variant="flat" prepend-icon="mdi-cart-arrow-right"
                   @click="openConvertDialog(editingWish); wishDialog = false">
              Передать в План закупок
            </v-btn>
            <v-btn v-else-if="editingWish.status === 'converted' && editingWish.purchase_id" color="primary" variant="flat" prepend-icon="mdi-cart-arrow-right"
                   @click="goToWishPurchases(editingWish); wishDialog = false">
              Перейти в {{ (editingWish.purchases?.length || editingWish.purchase_ids?.length || 1) > 1 ? 'закупки' : 'закупку' }}
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
              {{ wishFeoCategoryMissingTooltip }}
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

    <!-- ── ПРИНУДИТЕЛЬНАЯ СМЕНА СТАТУСА ИЗ СПИСКА (владелец, 2026-09-02, SaaS-admin) ── -->
    <v-dialog :model-value="!!rowForceStatusWish" max-width="440" :fullscreen="mobile" @update:model-value="(v: boolean) => { if (!v) rowForceStatusWish = null }">
      <v-card v-if="rowForceStatusWish">
        <v-card-title class="pa-4 pb-2 d-flex align-center ga-2">
          <v-icon color="red-darken-2">mdi-shield-crown</v-icon>
          Сменить статус заявки №{{ rowForceStatusWish.id }}
        </v-card-title>
        <v-card-text class="pa-4 pt-2">
          <v-select
            v-model="forceStatusValue"
            :items="WISH_FORCE_STATUS_OPTIONS"
            label="Новый статус"
            variant="outlined"
            density="compact"
            hide-details
          />
          <div class="text-body-2 text-medium-emphasis mt-2">
            Минуя все workflow-проверки. Доступно только SaaS-роли.
          </div>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="rowForceStatusWish = null">Отмена</v-btn>
          <v-btn color="red-darken-2" variant="flat" prepend-icon="mdi-flash" :loading="forcingStatus" @click="applyRowForceStatus">
            Применить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── FEO PER-ITEM DISABLE CONFIRM (владелец, 2026-08-19, тумблер вернули) ── -->
    <v-dialog v-model="wishFeoPerItemDisableDialog" max-width="480" :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4 pb-2">Одна категория ФЭО на всю заявку?</v-card-title>
        <v-card-text class="pa-4">
          У позиций заявки разные категории ФЭО (разных категорий: {{ wishFeoPerItemDisableCount }}) —
          при переключении в режим «одна на всех» построчный выбор будет очищен, и всем позициям
          достанется ОДНА категория, которую нужно будет выбрать в открывшемся блоке над таблицей.
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="cancelWishFeoPerItemDisable">Отмена</v-btn>
          <v-btn variant="flat" color="warning" @click="confirmWishFeoPerItemDisable">Переключить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── STOP DIALOG (владелец, 2026-08-13) ── -->
    <v-dialog v-model="stopDialog" max-width="520" :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4 pb-2 d-flex align-center ga-2">
          <v-icon color="error">mdi-alert-octagon</v-icon>
          Остановить заявку
        </v-card-title>
        <v-card-text class="pa-4">
          <v-alert type="warning" variant="tonal" density="compact" class="mb-3">
            Заявка и её закупки, не дошедшие до договора, будут остановлены и уйдут из плана закупок.
            Данные не удаляются. Чтобы изменить количество, создайте новую заявку (можно скопировать эту).
          </v-alert>
          <v-textarea
            v-model="stopReason"
            label="Причина остановки (необязательно)"
            variant="outlined"
            density="compact"
            rows="3"
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="stopDialog = false">Отмена</v-btn>
          <v-btn variant="flat" color="error" :loading="stoppingWish" @click="confirmStopWish">
            Остановить заявку
          </v-btn>
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

    <!-- Владелец, 2026-09-02: редактор колонок ОДИН на все три вкладки заявок
         («Мои» / «На согласование мне» / «Заявки сотрудников») — набор колонок
         у них одинаковый, раздельная настройка заставила бы настраивать
         одно и то же трижды. -->
    <ColumnConfigDialog
      v-model="showWishColumnPicker"
      :all-columns="allWishColumns"
      :state="wishColState"
      :show-width="true"
      :toggle-visible="wishToggleVisible"
      :set-position="wishSetPosition"
      :set-width="wishSetWidth"
      :reset="wishResetColumns"
    />

  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick, onBeforeUnmount } from 'vue'
import { useUndoRedo } from '@/composables/useUndoRedo'
import { useToast, type ToastType } from '@/composables/useToast'
import { refreshMyPendingApprovals } from '@/composables/useApprovalsBadge'
import { useWishLive } from '@/composables/useWishLive'
import { useRouter, useRoute } from 'vue-router'
import { apiFetch } from '@/api'
import { formatMoney } from '@/utils/formatMoney'
import PurchaseItemsEditor from '@/components/PurchaseItemsEditor.vue'
// Task 2 (сессия 2026-08-17): переиспользуем существующий пикер контрагентов (уже
// применяется в SubsidiesView/ContractsView; server-search по всей базе, RU ИНН выше) —
// не плодить урезанную копию (правило проекта: один модуль везде).
import ContractorPicker from '@/components/ContractorPicker.vue'
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'
import { useFeoLeaves } from '@/composables/useFeoLeaves'
import { useFeoTreeNodes } from '@/composables/useFeoTreeNodes'
import { useFeoNodeAmounts } from '@/composables/useFeoNodeAmounts'
import { useFeoPlannedResiduals } from '@/composables/useFeoPlannedResiduals'
import WishDistributionKanban from '@/components/WishDistributionKanban.vue'
import ColumnHeaderMenu from '@/components/ColumnHeaderMenu.vue'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'
import ValidationArrows from '@/components/ValidationArrows.vue'
import { useCardView } from '@/composables/useCardView'
import RegistryExportButton from '@/components/RegistryExportButton.vue'
import { useAuthStore } from '@/stores/auth'

// Phase 31-06: GALA-orange for unseen-changes badges
const GALA_ORANGE = '#fb923c'

const router = useRouter()
const route = useRoute()
const registryArea = ref<HTMLElement | null>(null)

// Владелец (2026-08-19): «менять позиции может только тот, кто имеет право» —
// см. canEditWishFeo ниже. Тот же паттерн, что и PaymentRegistryView.vue.
const authStore = useAuthStore()
function can(action: string) {
  return authStore.hasAction?.(action) ?? true
}

// Владелец, 2026-08-13: снимок сопоставленной позиции закупки — приходит на каждой
// позиции карточки заявки (GET /wishes/{id}). В списке заявок этого поля нет.
interface PurchaseMatch {
  match_method: 'wish_item_id' | 'item_name' | 'item_name_qty' | 'item_name_ambiguous'
  ambiguous_candidates_count?: number | null
  purchase_item_id?: number | null
  purchase_id?: number | null
  purchase_number?: string | null
  purchase_status?: string | null
  purchase_stopped_at?: string | null
  feo_category_id?: number | null
  feo_category_name?: string | null
  quantity?: number | null
  unit_price?: number | null
  total_price?: number | null
}

// Пункт 4 (владелец, 2026-08-13): сводка закупки для меню «Перейти в закупку»
// (см. WishPurchaseSummary в backend/app/schemas/wishes.py).
interface WishPurchaseSummary {
  id: number
  purchase_number?: number | null
  registry_number?: string | null
  item_name?: string | null
  status?: string | null
  status_label?: string | null
  amount?: number | string | null
  stopped_at?: string | null
}

interface WishItem {
  item_name: string
  item_type: string
  quantity: number
  unit: string
  unit_price: number
  total_price: number
  country_origin: string
  feo_category_id?: number | null
  purchase_match?: PurchaseMatch | null
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
  // Владелец, 2026-08-19: «нужно, чтобы было видно, кто отклонил» — переживает
  // сброс approver_names/цепочки при отклонении (см. backend Wish.rejected_by).
  rejected_by?: number | null
  rejected_at?: string | null
  rejected_by_name?: string | null
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
  purchases?: WishPurchaseSummary[]
  contracted_locked?: boolean
  // Правка владельца (2026-08-18): человекочитаемая причина блокировки — номер
  // закупки и её реальная стадия, вместо захардкоженного «на этапе «Договор»».
  contracted_locked_reason?: string | null
  items?: WishItem[]
  // Владелец, 2026-08-13: сумма заявки (Σ total_price позиций) — приходит с бэка
  // батчем в списке; если поле ещё не подъехало (параллельная разработка), считаем
  // сами из items на фронте (см. wishItemsTotal).
  items_total?: number | string | null
  // Остановка заявки (владелец, 2026-08-13, POST /{id}/stop)
  stopped_at?: string | null
  stopped_by?: number | null
  stopped_by_name?: string | null
  stopped_reason?: string | null
  stopped_partial?: boolean
  // Task 2 (сессия 2026-08-17): контрагент заявки — необязателен. contractor_id — из
  // справочника; contractor_name — ручной ввод, если контрагента в справочнике ещё нет;
  // contractor_display_name — готовое имя для показа, считает backend (только чтение).
  contractor_id?: number | null
  contractor_name?: string | null
  contractor_display_name?: string | null
  // Владелец, 2026-08-19: тумблер вернули — режим «одна на всех» / «каждой позиции своя»,
  // NOT NULL колонка бэкенда (см. backend/app/schemas/wishes.py::WishOut.feo_per_item).
  feo_per_item?: boolean
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
// несколько → выпадающий список (см. purchaseMenuLabel/goToPurchase) в шаблоне —
// эта функция остаётся фолбэком для одной закупки / случая без w.purchases.
// Пункт 4 (владелец, 2026-08-13): «переход в закупки, исполняемые на основании
// заявки; несколько — выпадающий список». Навигация — тем же путём, что и везде
// в проекте (router.push(`/orders/{id}/edit`), см. DashboardView/PlanView и др.).
function goToWishPurchases(w: Wish) {
  const purchases = w.purchases || []
  if (purchases.length === 1) { router.push(`/orders/${purchases[0].id}/edit`); return }
  const ids = w.purchase_ids || []
  if (ids.length > 1) router.push({ path: '/orders', query: { wish_id: String(w.id) } })
  else router.push(`/orders/${w.purchase_id}/edit`)
}
function wishPurchasesLabel(w: Wish): string {
  const n = (w.purchases || w.purchase_ids || []).length
  return n > 1 ? `Закупки (${n})` : 'Закупка'
}
function goToPurchase(id: number) {
  router.push(`/orders/${id}/edit`)
}
// Подпись пункта меню: «№123 — Заключён договор — 45 000 ₽» (+ «остановлена»).
function purchaseMenuLabel(p: WishPurchaseSummary): string {
  const num = p.registry_number || (p.purchase_number != null ? `№${p.purchase_number}` : `№${p.id}`)
  const parts = [num, p.status_label || p.status].filter(Boolean)
  const amt = Number(p.amount)
  if (p.amount != null && !Number.isNaN(amt)) parts.push(formatPrice(amt))
  return parts.join(' — ')
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
const allWishColumns: ColumnDef[] = [
  { title: 'Статус', key: 'status', width: 110, sortable: true },
  // Явный width (не только «резиновая» колонка без width): «Заявка» — единственная
  // колонка без фикс. width, при добавлении «Суммы» ниже сумма фикс. width колонок
  // превысила типичную ширину экрана и она схлопывалась почти до нуля — текст рвался
  // по буквам в вертикальный столбик (Vuetify 3.11 minWidth в headers не действует
  // на раскладку th — проверено). Таблица уходит в горизонтальный скролл, как и
  // остальные широкие реестры проекта.
  { title: 'Заявка', key: 'title_col', width: 260, sortable: false },
  { title: 'От кого', key: 'creator_name', width: 180, sortable: true },
  // «Кому» = назначенный (assigned_to) или цепочка согласующих — одно понятие
  { title: 'Кому', key: 'approver_names', width: 180, sortable: false },
  { title: 'Мероприятие', key: 'event_name', width: 180, sortable: true },
  // Владелец, 2026-09-02: subsidy_name уже приходит в WishOut (backend/app/schemas/wishes.py) —
  // просто вывести колонку.
  { title: 'Субсидия', key: 'subsidy_name', width: 180, sortable: true },
  // Владелец, 2026-08-13: сумма заявки (Σ total_price позиций) — как денежные колонки
  // в закупках (formatPrice), с сортировкой (соседние колонки тоже sortable).
  { title: 'Сумма', key: 'wish_total', width: 120, align: 'end' as const, sortable: true },
  { title: 'Создано', key: 'created_at', width: 110, sortable: true },
  { title: 'Срок', key: 'desired_date', width: 110, sortable: true },
  { title: 'Исполнитель', key: 'executor_name', width: 160, sortable: true },
  { title: 'Срок исп.', key: 'execution_deadline', width: 110, sortable: true },
  { title: 'Действия', key: 'actions', width: 160, sortable: false },
]

// Владелец, 2026-09-02: редактор колонок (выбор видимых + порядок + ширина) — ОДИН
// набор настроек на все три вкладки заявок («Мои» / «На согласование мне» /
// «Заявки сотрудников»): колонки везде одни и те же, раздельная настройка заставила
// бы настраивать одно и то же трижды. Ключ localStorage 'wishes' (в паре с
// v-resizable-columns, у которого свои ключи per-таб 'wishes-my' и т.п. — это
// отдельный механизм ширины колонок при live-резайзе, не конфликтует).
const {
  state: wishColState,
  visibleHeaders: wishVisibleHeaders,
  toggleVisible: wishToggleVisible,
  setPosition: wishSetPosition,
  setWidth: wishSetWidth,
  reset: wishResetColumns,
} = useColumnConfig('wishes', allWishColumns)
const showWishColumnPicker = ref(false)

const wishHeaders = computed(() => wishVisibleHeaders.value)
const wishHeadersAll = wishHeaders

const EXCLUDED_WISH_KEYS = new Set(['actions', 'data-table-expand'])
function getWishExportColumns() {
  // Экспорт не зависит от того, что пользователь скрыл в редакторе колонок —
  // как и раньше, выгружаем полный набор.
  return allWishColumns
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
  { value: 'draft', label: 'Черновики' },
  { value: 'submitted', label: 'Отправленные' },
  { value: 'approved', label: 'Одобренные' },
  { value: 'rejected', label: 'Отклонённые' },
  { value: 'converted', label: 'Конвертированные' },
]

// Счётчики по вкладкам (GET /wishes/counts) — накопительные множества статусов,
// см. app/services/wish_tabs.py на бэке. Владелец, сессия 2026-09-01: список
// обрезан limit=50, сравнивать «сколько заявок» по длине ответа нельзя —
// нужен отдельный точный счётчик рядом с названием каждой вкладки.
const wishCounts = ref<Record<string, number>>({})

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
// wishFeoSelected — самый глубокий выбранный узел. Владелец, 2026-08-19: тумблер
// «Не указывать последний уровень ФЭО» (wishFeoSkipLast) убран — теперь узел всегда
// должен быть листом дерева, промежуточный уровень не допускается нигде.
const wishFeoSelected = ref<number | null>(null)
// Владелец, 2026-08-19: тумблер «Разные категории ФЭО для каждого товара» ВЕРНУЛИ (был убран
// 2026-08-17) — режим снова переключаемый (wishForm.value.feo_per_item), см. шаблон карточки
// «Позиции». wishFeoSelected — значение шапки: единственный источник истины КАТЕГОРИИ в режиме
// «одна на всех» (feo_per_item=false) и дефолт для позиций БЕЗ своей категории в режиме
// «каждому своя» (feo_per_item=true) — см. симметричный фолбэк в buildWishPayload. Владелец,
// 2026-08-21: «каждому товару надо присваивать свою плановую» — тумблер отвечает ТОЛЬКО за
// категорию; плановая позиция (FeoPlannedItem) выбирается ПОСТРОЧНО в ОБОИХ режимах, шапочного
// значения для неё больше нет (см. allow-per-item-plan="true" у PurchaseItemsEditor и
// feo_planned_item_id в buildWishPayload — всегда построчный).

// Владелец, 2026-08-19: тумблер вернули — «Разные категории ФЭО для каждого товара» переключает
// между «одна категория на всех» и «каждой позиции своя», по образцу CreateOrderView.vue
// (onFeoPerItemChange/feoPerItemDisableDialog). Включение (каждой своя) всегда безопасно —
// шапка просто становится дефолтом для строк без собственной категории. Выключение (одна на
// всех) рискует молча потерять информацию, если у позиций УЖЕ разные категории — buildWishPayload
// в этом режиме проставляет ОДНУ шапочную категорию КАЖДОЙ позиции безусловно (см. ниже), поэтому
// правило проекта «выбранное на предыдущем этапе не смеет меняться само» требует подтверждения.
const wishFeoPerItemDisableDialog = ref(false)
const wishFeoPerItemDisableCount = ref(0)
function onWishFeoPerItemChange(val: boolean | null) {
  if (val) return // включение — безопасно, ничего подтверждать не нужно
  const relevantItems = (wishForm.value.items as any[])
    .filter((it) => (it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity))
  const distinctCats = new Set(
    relevantItems.map((it) => it.feo_category_id).filter((id) => id != null)
  )
  if (distinctCats.size > 1) {
    wishFeoPerItemDisableCount.value = distinctCats.size
    wishFeoPerItemDisableDialog.value = true
    wishForm.value.feo_per_item = true // держим тумблер включённым, пока владелец не подтвердит
    return
  }
  // QA-фикс (2026-08-19, дефект 2 «молчаливая потеря категории при ВКЛ→ВЫКЛ»): раньше при
  // distinctCats.size === 1 функция ничего не делала — wishFeoSelected (шапка) оставался null,
  // а buildWishPayload в ветке feo_per_item=false шлёт feo_category_id: feo ?? null КАЖДОЙ
  // позиции безусловно, т.е. единственная реальная категория молча стиралась в null. Если
  // категория одна и та же у всех непустых позиций — переносим её в шапку молча (пользователю
  // нечего терять и не в чем подтверждаться). Владелец, 2026-08-21: построчную плановую
  // позицию (feo_planned_item_id) БОЛЬШЕ НЕ ТРОГАЕМ здесь — она остаётся построчной и в режиме
  // «одна на всех», очищаем только feo_category_id (категория теперь берётся из шапки).
  if (distinctCats.size === 1) {
    const onlyCatId = distinctCats.values().next().value as number
    wishFeoSelected.value = onlyCatId
    for (const it of wishForm.value.items as any[]) {
      it.feo_category_id = null
    }
  }
  // Категория нигде не выбрана (distinctCats.size === 0) — выключение ничего не теряет,
  // подтверждение не требуется.
}
function cancelWishFeoPerItemDisable() {
  wishForm.value.feo_per_item = true
  wishFeoPerItemDisableDialog.value = false
}
// Подтверждение «Переключить» — категории у позиций реально различались (distinctCats.size > 1),
// принудительное объединение в одну шапочную категорию делает старые построчные плановые
// позиции потенциально несогласованными со своей новой категорией — очищаем и категорию, и
// плановую построчно, пользователь выберет заново под уже гарантированно свою категорию
// каждой позиции (см. аналогичный фикс в CreateOrderView.vue::confirmFeoPerItemDisable).
function confirmWishFeoPerItemDisable() {
  for (const it of wishForm.value.items as any[]) {
    it.feo_category_id = null
    it.feo_planned_item_id = null
  }
  wishForm.value.feo_per_item = false
  wishFeoPerItemDisableDialog.value = false
}

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

// Владелец (сессия 2026-08-19): «Должна быть возможность задать дату поставки всем
// позициям заявки одновременно». В отличие от watch(wishDateMode) выше (дозаполняет
// только ПУСТЫЕ позиции при переключении режима один раз), это явное действие кнопки —
// перезаписывает дату даже у уже заполненных позиций. Считаем «непустой» позицию так
// же, как остальные проверки формы (wishItemsMissingFeoCategory и т.п.): есть название,
// сумма или количество — иначе это ещё не заведённая заготовка строки.
function applyCommonDateToAllItems() {
  const d = wishForm.value.desired_date
  if (!d) return
  const items = (wishForm.value.items as any[]).filter(
    (it) => (it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity)
  )
  if (!items.length) return
  const hasDifferent = items.some((it) => it.needed_date && it.needed_date !== d)
  if (hasDifferent) {
    if (!confirm('У части позиций уже указана другая дата поставки. Заменить её выбранной датой у ВСЕХ позиций?')) return
  }
  for (const it of items) it.needed_date = d
  showSnack('Дата поставки проставлена всем позициям')
}
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
// Общий хелпер: рисует стрелки от кнопки «Отправить/Сохранить» к переданным целям.
// Используется во всех местах точечной подсветки одного/нескольких полей (ФЭО-категория,
// недостающие даты позиций/общая дата), чтобы не дублировать возню с рефами и таймером.
function pointArrowsTo(targets: HTMLElement[]) {
  if (!targets.length) return
  const btn = (wishSubmitBtnRef.value?.$el ?? wishSubmitBtnRef.value) as HTMLElement | null
  if (!btn) return
  validationArrowFrom.value = btn
  validationArrowTargets.value = targets.slice(0, 8)
  validationArrowsActive.value = true
  if (validationArrowsTimer) window.clearTimeout(validationArrowsTimer)
  validationArrowsTimer = window.setTimeout(dismissValidationArrows, 8000)
}
function showValidationArrows() {
  const formEl = wishFormRef.value?.$el as HTMLElement | undefined
  if (!formEl) return
  const allErrors = Array.from(formEl.querySelectorAll('.v-input.v-input--error')) as HTMLElement[]
  if (!allErrors.length) return
  // После перестановки блоков «Позиции» теперь выше по DOM, чем часть полей шапки
  // (например «Обоснование»). Поля с [data-field] — это осознанно провалидированные
  // поля шапки/футера формы (субсидия, обоснование и т.п.) и им отдаём приоритет —
  // первой целью и первым скроллом становится ошибка шапки. Но ошибки внутри таблицы
  // позиций (PurchaseItemsEditor), не помеченные [data-field], больше НЕ теряются:
  // они дописываются следом, чтобы стрелки указывали на все незаполненные поля
  // формы, а не только на шапку.
  const headerErrors = allErrors.filter(el => el.closest('[data-field]'))
  const restErrors = allErrors.filter(el => !el.closest('[data-field]'))
  const errors = [...headerErrors, ...restErrors].slice(0, 8)
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
  // Задача 1 (сессия 2026-08-20): кто РЕАЛЬНО принял решение и решал ли не за
  // себя — бэкенд отдаёт оба поля в GET /approvers и в ответе decide.
  decided_by_name?: string | null
  is_on_behalf?: boolean
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
  // Владелец, 2026-08-19: после отклонения строка отклонившего в цепочке
  // больше не сбрасывается в pending (см. backend _reset_approvals
  // keep_user_id) — чип должен явно читаться как «отклонил», не общим
  // «не согласовано», иначе рядом с чипами «ожидает» не видно, кто виновник.
  pending: 'Ожидает',
  approved: 'Согласовано',
  rejected: 'Отклонил',
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
// Владелец (2026-08-19): «менять позиции может только тот, кто имеет право» —
// построчная правка ФЭО (см. backend PATCH /execution, гейт wish.edit_feo)
// теперь дополнительно требует явного права, иначе любой согласующий из
// цепочки (например, случайный юрист) мог сам перетыкивать позиции.
const canEditWishFeo = computed(() =>
  can('wish.edit_feo')
  && (
    canAssigneeAct.value
    || (!!editingWish.value && editingWish.value.status === 'submitted' && isChainApprover.value)
  )
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
  // Task 2 (сессия 2026-08-17): контрагент заявки — оба поля необязательны.
  // contractor_id — выбор из справочника; contractor_name — ручной ввод, если
  // контрагента в справочнике ещё нет. contractor_display_name на форме не
  // редактируется (готовое имя для показа считает backend).
  contractor_id: null as number | null,
  contractor_name: '' as string,
  // Владелец, 2026-08-19: тумблер «Разные ФЭО позиции для каждого товара» вернули — режим
  // хранится в РЕАЛЬНОЙ колонке бэкенда (Wish.feo_per_item, NOT NULL, уже была заведена и
  // использовалась 2026-08-06..08-17, см. backend/app/models/wish.py, buildWishPayload и
  // openEditDialog ниже), а не в локальном ref-е — так режим переживает перезагрузку страницы
  // и виден в GET /wishes без гадания по позициям.
  feo_per_item: false as boolean,
})

// Task 2 (сессия 2026-08-17): предзаполнение ContractorPicker при открытии карточки —
// без него автокомплит не знает имя выбранного контрагента, пока не подгрузит его
// поиском (по образцу editInitialContractor в SubsidiesView.vue).
const wishContractorInitial = computed(() => {
  const id = wishForm.value.contractor_id
  if (!id) return null
  const name = editingWish.value?.contractor_display_name || `Контрагент #${id}`
  return { id, name }
})
// Выбор контрагента из справочника — ручное имя больше не нужно (иначе два
// источника contractor_display_name на бэке разойдутся); очистка picker'а
// (id → null) ручной ввод не трогает — пользователь мог начать с него.
function onWishContractorSelect(c: { id: number; name: string } | null) {
  if (c) wishForm.value.contractor_name = ''
}

// ФЭО-дерево субсидии (узлы + листья с бюджетами) — объявлено ПОСЛЕ wishForm (TDZ)
const { feoLeaves: wishFeoLeaves, feoNodes: wishFeoNodes } = useFeoLeaves({
  subsidyId: computed(() => wishForm.value.subsidy_id),
})

// Узлы дерева ФЭО для шапочного FeoTreeSelect (строки ~1303/~1480) — тот же общий
// composable, что и в CreateOrderView (см. composables/useFeoTreeNodes.ts): помимо
// filterFundedNodes добавляет цепочку-фолбэк для уже выбранной, но не профинансированной
// категории (wishFeoSelected), иначе дерево не может отрисовать выбранный узел и поле
// окажется пустым. wishFeoNodes (выше) не трогаем — он используется в других местах
// (wishFeoStale, collectFeoDescendantIds), где нужен именно строго профинансированный набор.
const { feoTreeNodes: wishFeoTreeNodes, rawNodes: wishFeoTreeRawNodes } = useFeoTreeNodes(
  computed(() => wishForm.value.subsidy_id),
  computed(() => wishFeoSelected.value),
)

// Задача владельца 2026-08-06: остаток по КАЖДОМУ узлу дерева ФЭО в шапке заявки
// (per-item таблица позиций считает свою карту сама внутри PurchaseItemsEditor).
const { nodeAmounts: wishNodeAmounts } = useFeoNodeAmounts({
  subsidyId: computed(() => wishForm.value.subsidy_id),
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
// Есть ли у категорий ФЭО, выбранных в позициях заявки (или их потомков), хоть одна
// плановая позиция плана закупок — если нет, предупреждение «выберите плановую
// позицию» не имеет смысла показывать при отправке (см. saveWish). Владелец,
// 2026-08-19: раньше смотрел только на wishFeoSelected (шапка) — после того как
// шапочный выбор убран из формы создания/редактирования, эта проверка молча
// перестала бы срабатывать почти всегда. Теперь собирает категории со ВСЕХ
// непустых позиций (с фолбэком на wishFeoSelected для обратной совместимости
// со старыми заявками, см. wishItemsMissingFeoCategory).
const wishFeoBranchHasPlannedItems = computed((): boolean => {
  const items = (wishForm.value.items as any[]).filter(
    (it) => (it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity)
  )
  const catIds = new Set<number>()
  for (const it of items) {
    const cid = it.feo_category_id ?? wishFeoSelected.value
    if (cid != null) catIds.add(cid)
  }
  for (const cid of catIds) {
    const ids = collectFeoDescendantIds(cid)
    ids.add(cid)
    if (wishPlannedResiduals.value.some(r => ids.has(r.category_id))) return true
  }
  return false
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

// Владелец (сессия 2026-08-21): шапочный выбор ОДНОЙ плановой позиции на всю заявку
// (FeoPlannedItemsSelect в шапке, composite-выбор wishFeoPlanSelection, автоподбор
// похожих плановых позиций по имени и подтверждение совпадения) убран целиком вместе
// с шапочным перечнем плановых — «каждому товару надо присваивать свою плановую»,
// привязка теперь ТОЛЬКО построчная (FeoPlannedItemsSelect внутри PurchaseItemsEditor,
// см. allow-per-item-plan="true" в шаблоне выше). Автоподбор похожих плановых по имени
// был возможен только через убранный шапочный UI — построчный селектор его не поддерживает.

// ФЭО заявки не найдена в текущем дереве субсидии → категорию удалили/пересоздали.
// Владелец, 2026-08-11: раньше согласование не блокировалось (backend молча обнулял
// и создавал закупку без ФЭО) — именно так реальная заявка №32 лишилась категории.
// Теперь backend отвечает 409 (missing_feo_category) — подсказываем выбрать
// актуальную категорию ДО попытки согласовать.
const wishFeoStale = computed(() => {
  const id = wishFeoSelected.value
  return !!id && wishFeoNodes.value.length > 0 && !wishFeoNodes.value.some(n => n.id === id)
})

// Жёсткий гейт «без конечной категории ФЭО заявку нельзя согласовать» (владелец, 2026-08-11,
// объединено с проверкой нелистового узла 2026-08-19 — тумблер «Не указывать последний
// уровень ФЭО» убран: «для всех закупок без плановой позиции она теперь создаётся
// автоматически», поэтому промежуточный уровень больше нигде не допускается). Зеркалит
// backend _ensure_feo_categories_assigned на фронте, чтобы блокировать отправку ДО запроса,
// а не только показывать ошибку после отказа 409. Эффективная категория позиции — её
// собственная, а если её нет — категория заявки целиком (wishFeoSelected) как значение по
// умолчанию, см. симметричный payload в buildWishPayload. Позиция считается «без категории»,
// если категория не выбрана ВООБЩЕ, либо выбранный узел найден в дереве, но не является
// листом (узел, удалённый из дерева, — отдельный случай, см. wishItemsWithStaleFeoCategory).
const wishItemsMissingFeoCategory = computed(() => {
  const items = (wishForm.value.items as any[]).filter(
    (it) => (it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity)
  )
  if (!items.length) return [] as any[]
  // Владелец, 2026-08-19: тумблер вернули — гейт снова режимо-зависимый (п.4 задачи).
  // «Одна на всех» (feo_per_item=false): единственная проверяемая категория — шапочная
  // (wishFeoSelected), т.к. buildWishPayload при сохранении проставит её КАЖДОЙ позиции
  // безусловно — собственная категория позиции тут вообще не смотрится.
  if (!wishForm.value.feo_per_item) {
    const catId = wishFeoSelected.value
    if (catId == null) return items
    const node = wishFeoNodes.value.find(n => n.id === catId)
    return (node && !node.is_leaf) ? items : []
  }
  // «Каждому своя» (feo_per_item=true, как было единственным режимом 2026-08-17..08-19):
  // собственная категория позиции, а если её нет — шапка как дефолт (см. buildWishPayload).
  return items.filter((it) => {
    const catId = it.feo_category_id ?? wishFeoSelected.value
    if (catId == null) return true
    const node = wishFeoNodes.value.find(n => n.id === catId)
    return !!node && !node.is_leaf
  })
})
const wishFeoCategoryMissing = computed(() => wishItemsMissingFeoCategory.value.length > 0)
// Владелец, 2026-08-19: текст подсказки у заблокированных кнопок отправки/одобрения —
// режимо-зависимый (тот же п.4), иначе в режиме «одна на всех» текст врал бы про «таблицу
// позиций выше», в которой построчных ФЭО-контролов в этом режиме нет вовсе.
const wishFeoCategoryMissingTooltip = computed(() =>
  wishForm.value.feo_per_item
    ? 'Не у всех позиций выбрана категория ФЭО — заполните её в таблице позиций выше, иначе заявку нельзя будет согласовать'
    : 'Категория ФЭО заявки не выбрана (или не до конечного уровня) — заполните её в блоке выше, иначе заявку нельзя будет согласовать'
)

// Было wishFeoStale (для шапочного выбора) — по каждой позиции: собственная feo_category_id
// ссылается на узел, которого больше нет в дереве субсидии (структуру ФЭО пересоздавали).
// Показывается у таблицы позиций (см. шаблон «Позиции»), а не молча теряется.
const wishItemsWithStaleFeoCategory = computed(() => {
  if (!wishFeoNodes.value.length) return [] as any[]
  const items = (wishForm.value.items as any[]).filter(
    (it) => (it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity)
  )
  return items.filter((it) => it.feo_category_id != null && !wishFeoNodes.value.some(n => n.id === it.feo_category_id))
})

function highlightMissingFeoCategory() {
  const formEl = wishFormRef.value?.$el as HTMLElement | undefined
  const target = formEl?.querySelector('[data-field="feo_category"]') as HTMLElement | null
  if (!target) return
  target.scrollIntoView({ behavior: 'smooth', block: 'center' })
  target.classList.add('wish-date-missing-pulse')
  setTimeout(() => target.classList.remove('wish-date-missing-pulse'), 3000)
  pointArrowsTo([target])
}

// Гейт «нельзя отправить без согласующих» (saveWish): по образцу highlightMissingFeoCategory —
// подсвечивает поле «Верхний согласующий» в секции «Согласующие» стрелкой от кнопки отправки.
function highlightMissingApprovers() {
  const formEl = wishFormRef.value?.$el as HTMLElement | undefined
  const target = formEl?.querySelector('[data-field="approvers"]') as HTMLElement | null
  if (!target) return
  target.scrollIntoView({ behavior: 'smooth', block: 'center' })
  target.classList.add('wish-date-missing-pulse')
  setTimeout(() => target.classList.remove('wish-date-missing-pulse'), 3000)
  pointArrowsTo([target])
}

// Скроллит к «Верхнему согласующему» и ставит туда фокус — без пульсации/ошибки
// (в отличие от highlightMissingApprovers, это не отказ, а обычная навигация после
// клика «Добавить согласующих», см. onAddApproversClick).
function focusApproversField() {
  const formEl = wishFormRef.value?.$el as HTMLElement | undefined
  const target = formEl?.querySelector('[data-field="approvers"]') as HTMLElement | null
  if (!target) return
  target.scrollIntoView({ behavior: 'smooth', block: 'center' })
  const input = target.querySelector('input') as HTMLInputElement | null
  input?.focus()
}

// Владелец, 2026-08-19: кнопка «Добавить согласующих» в блоке «Согласующие» несохранённой
// заявки заменяет прежнюю неочевидную «Сохранить черновик». Черновик сохраняется молча
// (переиспользуем saveWish, как и раньше делал этот же alert), а после успешного сохранения
// пользователя сразу переносит к выбору верхнего согласующего — отдельного шага «сначала
// сохраните» больше нет. saveWish сам ловит ошибки и показывает snackbar
// (e.payload?.message ?? e.message, без таймаута — см. правило проекта), здесь их
// дублировать не нужно; :loading="saving" на кнопке уже переключается внутри saveWish.
async function onAddApproversClick() {
  if (editingWishId.value) { focusApproversField(); return }
  const ok = await saveWish(false)
  if (!ok) return
  await nextTick()
  focusApproversField()
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

// Items computed total
const totalNmck = computed(() =>
  wishForm.value.items.reduce((sum, i) => sum + (i.total_price || 0), 0)
)

// Владелец (сессия 2026-08-21): предзаполнение старого шапочного диалога создания
// плановой позиции (wishFeoPlannedPrefill) и «диалог выбора способа» для нескольких
// позиций разом (wishFeoBulkItems/onWishFeoBulkItemsCreated) — убраны вместе с шапочным
// FeoPlannedItemsSelect. Массовое «Создать в плане закупок» для ВСЕХ позиций заявки
// сразу остаётся доступным кнопкой в шапке таблицы «Позиции» (PurchaseItemsEditor.vue,
// createPlannedBulkDialog/runCreatePlannedBulk) — она создаёт СВОЮ плановую позицию
// под каждую позицию заявки в её собственной категории, что и было целью этого кода.

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

function showSnack(text: string, color: ToastType = 'success', opts?: { duration?: number }) {
  toast.addToast(text, color, opts)
}

// Владелец (2026-09-04, п.5 задачи заявки №54): «уведомления от предыдущей заявки
// остаются на экране и читаются как отчёт о текущей» — успех «Заявка согласована и
// перенесена в закупку РЕЕ-2026-00906» (заявка №51) провисел рядом с ошибкой по
// уже ОТКРЫТОЙ заявке №54 и создал впечатление, что это про неё. Тосты — общий
// модульный стек (composables/useToast.ts), рассчитанный на то, что результат
// действия читают, поэтому он НЕ исчезает сам (duration=0) — трогать сам механизм
// не будем (общий для всего приложения, риск задеть другие экраны). Вместо этого
// локально для WishesView: при открытии ЛЮБОЙ карточки заявки (в т.ч. повторном
// открытии той же) убираем уже прочитанные/непрочитанные success-тосты — они
// однозначно относятся к ДРУГОМУ, уже завершённому действию, а не к тому, что
// пользователь сейчас видит в открывшейся карточке. Ошибки/предупреждения не
// трогаем — они могли быть от действия, которое пользователь как раз хочет
// разобрать, открыв заявку.
function clearStaleSuccessToasts() {
  for (const t of [...toast.toasts.value]) {
    if (t.type === 'success') toast.removeToast(t.id)
  }
}

// Предупреждение о превышении ФЭО (задача владельца 2026-08-12: «согласовали —
// всё равно конвертировать в закупку, но заметно показать, из-за чего
// превышение»). Бэкенд отдаёт его ключом excess_warnings в ответе эндпоинтов
// согласования/конвертации заявки (decide/approve/convert) — пустой массив,
// пока превышения нет. Поле опционально: пока бэкенд не доехал, warnings
// будет undefined/[] и никакого уведомления не покажем (тихая деградация).
interface ExcessWarningItem { name: string; amount: number }
interface ExcessWarning {
  category_id: number
  category_name: string
  budget: number | null
  plan_after: number
  excess_amount: number
  items: ExcessWarningItem[]
}

function showExcessWarnings(warnings: ExcessWarning[] | null | undefined, actionPrefix: string) {
  if (!warnings || !warnings.length) return
  const parts = warnings.map(w => {
    const itemsText = (w.items || []).map(i => `${i.name} — ${formatPrice(i.amount)}`).join(', ')
    return `Категория «${w.category_name}»: план превышает ФЭО на ${formatPrice(w.excess_amount)}${itemsText ? ` (позиции: ${itemsText})` : ''}`
  })
  // Владелец (2026-09-03): «перебор в ветке не блокирует, но виден как пометка» —
  // раньше здесь текст утверждал, что закупка «не пойдёт дальше "Ведётся работа"»
  // (это было правдой ДО правки assert_no_unapproved_excess). Теперь перекос
  // ОТДЕЛЬНОЙ категории ФЭО НЕ блокирует движение закупки вообще (суммарный
  // потолок ФЭО в целом — единственный жёсткий контроль) — текст обязан
  // отражать это, иначе врёт пользователю о несуществующей блокировке.
  showSnack(
    `${actionPrefix} ${parts.join('; ')}. Это ориентир, не блокировка — закупка продолжает двигаться по стадиям. `
    + `При желании перенесите позиции в другую категорию или согласуйте превышение в панели субсидии.`,
    'warning',
  )
}

// Задача владельца (сессия 2026-08-21, план «Превышение плана видно везде; закупка
// знает свою заявку и обновляется вместе с ней»): «повторное согласование обновляет
// закупку из заявки» + «перед применением показать, что именно изменится — молча
// переписывать документ нельзя». Бэкенд-агент (параллельная сессия) добавляет поле
// purchase_sync в ответ decide/approve/convert (те же три эндпоинта, что уже отдают
// excess_warnings выше) — эта функция превращает его в понятную сводку: что
// поменялось в закупке (предмет было→стало, сколько позиций добавлено/убрано/
// изменено), либо причину, почему обновление заблокировано (закупка ушла дальше
// «Плана закупок» — blocked_reason). Поле опционально — пока бэкенд его не отдаёт,
// sync будет undefined и функция тихо ничего не показывает (без заглушек).
interface PurchaseSyncItem { name: string; quantity?: number | null; amount?: number | null }
interface PurchaseSyncItemChange { name: string; was?: string | number | null; now?: string | number | null }
// QA-правки (2026-08-21, дефекты 2-3 «потеря данных при повторном согласовании»):
// items_conflicted — поля, которые правили ПРЯМО В ЗАКУПКЕ после переноса (значение
// разошлось со снимком planned_*) — из заявки НЕ перезаписаны, показываем конфликт,
// а не молча теряем правку. items_kept_manual — строки закупки без связи с заявкой
// (заведены закупщиком в самой закупке) — при сверке не удаляются; сообщаем, что
// они остались, чтобы не выглядело, будто их «забыли».
interface PurchaseSyncItemConflict { name: string; field: string; in_purchase?: number | null; in_wish?: number | null }
interface PurchaseSync {
  purchase_id: number
  registry_number?: string | null
  subject_before?: string | null
  subject_after?: string | null
  items_added?: PurchaseSyncItem[]
  items_removed?: PurchaseSyncItem[]
  items_changed?: PurchaseSyncItemChange[]
  items_conflicted?: PurchaseSyncItemConflict[]
  items_kept_manual?: PurchaseSyncItem[]
  blocked_reason?: string | null
}

const _SYNC_FIELD_LABELS: Record<string, string> = {
  quantity: 'количество', unit_price: 'цена', total_price: 'сумма',
}

function showPurchaseSync(sync: PurchaseSync | null | undefined) {
  if (!sync) return
  const label = sync.registry_number || `№${sync.purchase_id}`
  if (sync.blocked_reason) {
    showSnack(`Закупка ${label} НЕ обновлена из заявки: ${sync.blocked_reason}`, 'warning')
    return
  }
  const parts: string[] = []
  if (sync.subject_before != null && sync.subject_after != null && sync.subject_before !== sync.subject_after) {
    parts.push(`предмет: «${sync.subject_before}» → «${sync.subject_after}»`)
  }
  const added = sync.items_added || []
  const removed = sync.items_removed || []
  const changed = sync.items_changed || []
  const keptManual = sync.items_kept_manual || []
  if (added.length) parts.push(`добавлено позиций: ${added.length} (${added.map(i => i.name).join(', ')})`)
  if (removed.length) parts.push(`убрано позиций: ${removed.length} (${removed.map(i => i.name).join(', ')})`)
  if (changed.length) parts.push(`изменено позиций: ${changed.length} (${changed.map(i => i.name).join(', ')})`)
  if (keptManual.length) parts.push(`оставлены как есть (заведены в закупке): ${keptManual.length} (${keptManual.map(i => i.name).join(', ')})`)
  if (!parts.length) {
    showSnack(`Закупка ${label} сверена с заявкой — изменений в составе нет`, 'info')
  } else {
    showSnack(`Закупка ${label} обновлена из заявки — ${parts.join('; ')}.`, 'info')
  }

  const conflicted = sync.items_conflicted || []
  if (conflicted.length) {
    const conflictText = conflicted
      .map(c => `${c.name} (${_SYNC_FIELD_LABELS[c.field] || c.field}: в закупке ${c.in_purchase ?? '—'}, в заявке ${c.in_wish ?? '—'})`)
      .join('; ')
    showSnack(
      `Закупка ${label}: значения правили прямо в закупке — из заявки НЕ перезаписаны: ${conflictText}. Сверьте вручную.`,
      'warning',
    )
  }
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
    // Тот же псевдо-узел — в rawNodes composable'а useFeoTreeNodes (источник шапочного
    // FeoTreeSelect, :nodes="wishFeoTreeNodes"): без этого дерево не знает о только что
    // созданной категории «Не определена» и не может отрисовать её как выбранную (селект
    // окажется пустым, см. useFeoTreeNodes.ts).
    if (!wishFeoTreeRawNodes.value.find(n => n.id === cat.id)) {
      const parentRawNode = cat.parent_id != null ? wishFeoTreeRawNodes.value.find(n => n.id === cat.parent_id) : null
      const newRawNode = { id: cat.id, name: cat.name, parent_id: cat.parent_id ?? null, level: parentRawNode ? parentRawNode.level + 1 : 1, is_leaf: true } as any
      const updatedRaw = [...wishFeoTreeRawNodes.value, newRawNode]
      if (cat.parent_id != null) {
        const pi = updatedRaw.findIndex(n => n.id === cat.parent_id)
        if (pi !== -1) updatedRaw[pi] = { ...updatedRaw[pi], is_leaf: false }
      }
      wishFeoTreeRawNodes.value = updatedRaw
    }
    wishFeoSelected.value = cat.id
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Ошибка получения категории «Не определена»', 'error')
  }
}

function formatPrice(price: number) {
  return price.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 })
}

// Владелец, 2026-08-13: столбец «сумма заявки» на /wishes. Бэк батчем считает
// items_total (Σ total_price позиций) и в списке, и в карточке — используем его;
// если поле почему-то не пришло (переходный момент/старый кэш), считаем сами из
// items. ⚠️ НЕ используем total_amount как фолбэк — по подтверждению бэкенда это
// мёртвое поле (никогда не заполнялось), оставлено в типе как есть, но не трогается.
function wishItemsTotal(w: Wish): number | null {
  if (w.items_total != null) {
    const n = Number(w.items_total)
    if (Number.isFinite(n)) return n
  }
  if (Array.isArray(w.items) && w.items.length) {
    const sum = w.items.reduce((s, i) => s + (Number(i.total_price) || 0), 0)
    if (sum > 0) return sum
  }
  return null
}

// Владелец, 2026-08-13: чип «в закупке иначе» — расхождение позиции заявки с
// сопоставленной позицией закупки (категория ФЭО/кол-во/цена), чтобы «при сравнении
// было видно, где накосячили». Бэкенд отдаёт снимок закупочной позиции в
// item.purchase_match (только в карточке, GET /wishes/{id} — см. openEditDialog).
// Деньги/количество сравниваем с допуском в копейку (округление до 2 знаков), чтобы
// не дёргать чип из-за 0,004 разницы округления. Категорию сравниваем по id, а
// показываем названиями: своё — по allFeoCategories (справочник грузится глобально,
// отдельного поля с именем на позиции заявки нет), закупочное — feo_category_name,
// которое уже приходит готовым с бэка.
function moneyRoundedEq(a: number | null | undefined, b: number | null | undefined): boolean {
  if (a == null || b == null) return true
  return Math.round(Number(a) * 100) === Math.round(Number(b) * 100)
}
function feoCategoryNameById(id?: number | null): string {
  if (id == null) return ''
  return allFeoCategories.value.find(c => c.id === id)?.name || `#${id}`
}
function itemDiscrepancy(item: any): { lines: string[] } | null {
  const pm = item?.purchase_match
  if (!pm || pm.match_method === 'item_name_ambiguous') return null
  const lines: string[] = []
  // Эффективная своя категория позиции: как и в остальном файле (см. wishFeoSelected
  // fallback), если у позиции нет собственной feo_category_id (режим «одна категория
  // на заявку»), берём общую категорию заявки.
  const ownCategoryId = item.feo_category_id ?? wishFeoSelected.value
  if (pm.feo_category_id != null && ownCategoryId != null && pm.feo_category_id !== ownCategoryId) {
    const ownName = feoCategoryNameById(ownCategoryId) || '—'
    const purchName = pm.feo_category_name || feoCategoryNameById(pm.feo_category_id) || '—'
    lines.push(`категория: «${ownName}» → «${purchName}»`)
  }
  if (pm.quantity != null && item.quantity != null && !moneyRoundedEq(item.quantity, pm.quantity)) {
    lines.push(`количество: ${item.quantity} → ${pm.quantity}`)
  }
  if (pm.unit_price != null && item.unit_price != null && !moneyRoundedEq(item.unit_price, pm.unit_price)) {
    lines.push(`цена: ${formatMoney(item.unit_price)} → ${formatMoney(pm.unit_price)}`)
  }
  if (!lines.length) return null
  return { lines }
}
// Есть что показать построчно: остановлена / расхождение / неоднозначный двойник
function wishItemStatus(item: any): boolean {
  const pm = item?.purchase_match
  if (!pm) return false
  if (pm.purchase_stopped_at) return true
  if (pm.match_method === 'item_name_ambiguous') return true
  return !!itemDiscrepancy(item)
}
function goToMatchedPurchase(item: any) {
  const pid = item?.purchase_match?.purchase_id
  if (!pid) return
  router.push(`/orders/${pid}/edit`)
}

// Владелец, 2026-08-13: «остановка заявки» — крупная подпись под алертом.
function stoppedByLine(w: { stopped_by_name?: string | null; stopped_at?: string | null; stopped_reason?: string | null }): string {
  const who = w.stopped_by_name || 'неизвестно кем'
  const when = w.stopped_at ? formatDate(w.stopped_at) : ''
  let line = `остановил${when ? ' ' + who + ',' : ' ' + who} ${when}`.trim()
  if (w.stopped_reason) line += ` — ${w.stopped_reason}`
  return line
}

// Владелец, 2026-08-19: «нужно, чтобы было видно, кто отклонил» — строка для
// шапки диалога и tooltip'а статуса «Не согласована» в списке.
function rejectedByLine(w: { rejected_by_name?: string | null; rejected_at?: string | null; rejection_reason?: string | null }): string {
  const who = w.rejected_by_name || 'неизвестно кем'
  const when = w.rejected_at ? formatDate(w.rejected_at) : ''
  let line = `Отклонил: ${who}${when ? ', ' + when : ''}`
  if (w.rejection_reason) line += ` — ${w.rejection_reason}`
  return line
}

function formatDate(dateStr: string) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

// Задача 1 (сессия 2026-08-20): строка решения в цепочке согласования
// («Согласовал: ... вместо ... · 20.08.2026 14:49») требует времени, а не
// только даты — своего хелпера с временем в файле не было, минимальный,
// без сторонних библиотек.
function formatDateTime(dateStr?: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const date = d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
  const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  return `${date} ${time}`
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
    // Владелец, 2026-09-01: «Все» больше не значит «без статуса» (тот путь
    // молча исключал converted на бэке для других потребителей эндпоинта) —
    // передаём status ЯВНО всегда, включая 'all', которое сервер трактует как
    // «действительно всё» (см. list_wishes / wish_tab_statuses на бэке).
    allWishes.value = await apiFetch<Wish[]>('/wishes/' + buildFilterParams({ subordinates_only: true, status: allFilter.value }))
    loadWishCounts()
  } catch (e: any) {
    showSnack(`Ошибка загрузки заявок: ${e?.message || e?.payload?.message || 'неизвестная ошибка'}`, 'error')
  } finally {
    loadingAll.value = false
  }
}

// Счётчики вкладок — тот же scope видимости (subordinates_only), что и
// список выше, но COUNT()-ом на бэке, без ограничения limit=50.
async function loadWishCounts() {
  try {
    wishCounts.value = await apiFetch<Record<string, number>>('/wishes/counts' + buildFilterParams({ subordinates_only: true }))
  } catch {
    // Счётчики — не критичны для работы списка, тихо оставляем прежние значения
  }
}

// Активная вкладка чипов показала МЕНЬШЕ записей, чем реально есть (limit=50
// на бэке) — «показаны первые N из M» вместо молчаливой обрезки (владелец,
// 2026-09-01). Такой же приём, как «Показано X из Y» в PurchaseItemsEditor/
// ContractorsView/ContractsView — переиспользуем формулировку, не плодим новую.
const allWishesTruncated = computed(() => {
  const total = wishCounts.value[allFilter.value]
  if (total === undefined) return null
  return allWishes.value.length < total ? total : null
})

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
    contractor_id: null,
    contractor_name: '',
    feo_per_item: false,
  }
  wishFeoSelected.value = null
  wishDateMode.value = 'common'
}

function openCreateDialog() {
  clearStaleSuccessToasts()
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
  clearStaleSuccessToasts()
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
  wishForm.value.contractor_id = (wish as any).contractor_id ?? null
  wishForm.value.contractor_name = (wish as any).contractor_name || ''
  // Владелец, 2026-08-19: тумблер вернули — режим читаем из БД (Wish.feo_per_item, NOT NULL
  // колонка бэка, всегда реальный boolean). Никакой эвристики по позициям не нужно — значение
  // либо явно сохранено пользователем, либо false по умолчанию для совсем старых записей.
  wishForm.value.feo_per_item = (wish as any).feo_per_item ?? false
  forceStatusValue.value = wish.status || 'draft'

  // B5 — Seed cascade from wish.feo_category_id (цепочку строит сам FeoCascadeSelect).
  // Владелец, 2026-08-19: тумблер «Не указывать последний уровень ФЭО» убран целиком —
  // легаси-заявка с промежуточной (нелистовой) категорией на сервере грузится как есть,
  // ничего не падает; позиция просто попадает в wishItemsMissingFeoCategory и требует
  // от пользователя углубиться до конечного уровня перед отправкой на согласование.
  wishFeoSelected.value = wish.feo_category_id ?? null

  // Открываем диалог СРАЗУ после синхронного заполнения формы — пользователь
  // видит окно мгновенно, а тяжёлая загрузка позиций идёт под спиннером.
  wishDialog.value = true
  wishDialogLoading.value = true

  try {
    let rawItems: any[] = []
    // Владелец, 2026-08-13: список заявок (myWishes/allWishes/incoming) уже подгружает
    // items, но БЕЗ purchase_match (бэк считает его только в карточке, GET /wishes/{id}
    // — дорогой запрос под конкретный id). Построчные пометки «остановлена»/«в закупке
    // иначе» без этого поля не построить, поэтому при открытии карточки всегда идём за
    // свежими данными; items из списка — только фолбэк, если запрос не удался.
    try {
      const fresh = await apiFetch<any>(`/wishes/${wish.id}`)
      if (Array.isArray(fresh?.items)) rawItems = fresh.items
    } catch {}
    if (!rawItems.length && Array.isArray((wish as any).items) && (wish as any).items.length > 0) {
      rawItems = (wish as any).items
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
        // Владелец, 2026-08-13: снимок сопоставленной позиции закупки — для построчных
        // пометок «остановлена»/«в закупке иначе»/«двойник не определён» (см. itemStatus).
        purchase_match: i.purchase_match ?? null,
        _photo_url: prod ? photoOf(prod) : undefined,
        _description: prod?.description || undefined,
        // Владелец, 2026-08-29: штамп даты/источника актуализации цены — из
        // привязанного товара каталога, см. usePriceFreshness.ts.
        _price_meta: prod ? {
          price_updated_at: prod.price_updated_at ?? null,
          price_source: prod.price_source ?? null,
          price_source_ref: prod.price_source_ref ?? null,
          price_freshness: prod.price_freshness ?? null,
        } : null,
      }
    }) as any
    // Владелец (сессия 2026-08-17): тумблер «Разные ФЭО позиции для каждого товара» убран,
    // построчная категория читается как есть — ничего гадать не нужно. Старые заявки,
    // сохранённые в «общем» режиме (feo_per_item=false), имели пустой feo_category_id на
    // всех позициях — заполняем его значением из шапки ЗДЕСЬ (а не полагаемся на watch в
    // PurchaseItemsEditor.vue, у него нет immediate:true — при монтировании карточки
    // defaultFeoCategoryId уже равен wishFeoSelected с самого начала, «изменения» не
    // происходит, автозаполнение там не сработает), чтобы позиция сразу показывала
    // категорию, а не пустой обязательный выбор. Правило проекта соблюдено: трогаем
    // ТОЛЬКО пустые позиции, построчный выбор никогда не перезаписывается.
    if (wishFeoSelected.value != null) {
      for (const it of wishForm.value.items as any[]) {
        if (it.feo_category_id == null) it.feo_category_id = wishFeoSelected.value
      }
    }

    // Владелец (сессия 2026-08-21): «каждому товару надо присваивать свою плановую» —
    // шапочного значения feo_planned_item_id больше нет ни в одном режиме (см. п.7 задачи),
    // построчные значения читаются как есть выше (feo_planned_item_id: i.feo_planned_item_id),
    // никакого восстановления/каскада из шапки не требуется.
    wishDateMode.value = (wishForm.value.items as any[]).some(it => it.needed_date) ? 'per_item' : 'common'
    await loadWishMembers()
    await loadWishApprovers()
    approvalMode.value = ((wish as any).approval_mode === 'parallel') ? 'parallel' : 'sequential'
    // Пункт 3 (владелец, 2026-08-13): базовый снимок формы «как загружено» — approveWish
    // сравнивает с ним, чтобы понять, есть ли несохранённые правки перед согласованием.
    wishFormSavedSnapshot.value = wishPayloadSnapshotJson()
    // Владелец (2026-08-19): снимок построчных feo_category_id/feo_planned_item_id —
    // см. wishItemsFeoSnapshot/wishItemsFeoDirty у saveExecution. Берётся ПОСЛЕ автозаполнения
    // категории из шапки выше (это не правка согласующего, а достройка данных при загрузке).
    snapshotWishItemsFeo()
  } finally {
    wishDialogLoading.value = false
  }
}

// Superadmin: force-смена статуса. Список статусов вынесен в константу — используется
// и блоком в диалоге правки, и мини-диалогом прямо из списка (rowForceStatusWish ниже).
const WISH_FORCE_STATUS_OPTIONS = [
  { value: 'draft', title: 'Черновик' },
  { value: 'submitted', title: 'Отправлена' },
  { value: 'approved', title: 'Одобрена' },
  { value: 'rejected', title: 'Отклонена' },
  { value: 'converted', title: 'Конвертирована' },
]
const forceStatusValue = ref<string>('draft')
const forcingStatus = ref(false)
// Владелец (2026-09-02): «раньше суперадмин мог двигать заявки по статусам
// самостоятельно» — теперь доступно ещё и прямо из списка, без открытия диалога
// правки (см. rowForceStatusWish/openRowForceStatus ниже). wishId параметром —
// без него берётся заявка, открытая в диалоге (прежнее поведение). Возвращает
// true при успехе, чтобы вызывающая сторона сама решила, что закрыть.
async function forceStatus(wishId?: number): Promise<boolean> {
  const targetId = wishId ?? editingWishId.value
  if (!targetId) { showSnack('Сначала откройте заявку', 'warning'); return false }
  const label = WISH_FORCE_STATUS_OPTIONS.find(o => o.value === forceStatusValue.value)?.title || forceStatusValue.value
  if (!confirm(`Принудительно установить статус «${label}»? Workflow-проверки будут пропущены.`)) return false
  forcingStatus.value = true
  try {
    await apiFetch(`/wishes/${targetId}/status`, {
      method: 'POST',
      body: JSON.stringify({ status: forceStatusValue.value }),
    })
    showSnack(`Статус принудительно изменён на «${label}»`)
    await reloadActiveTab()
    return true
  } catch (e: any) {
    showSnack(`Ошибка force-status: ${e?.detail || e?.payload?.message || e?.message || 'не удалось'}`, 'error')
    return false
  } finally {
    forcingStatus.value = false
  }
}

// Мини-диалог смены статуса прямо из списка (не открывая полный диалог правки заявки).
const rowForceStatusWish = ref<Wish | null>(null)
function openRowForceStatus(wish: Wish) {
  forceStatusValue.value = wish.status || 'draft'
  rowForceStatusWish.value = wish
}
async function applyRowForceStatus() {
  if (!rowForceStatusWish.value) return
  if (await forceStatus(rowForceStatusWish.value.id)) rowForceStatusWish.value = null
}

const savingExecution = ref(false)

// Владелец (2026-08-19): согласующий из цепочки не может редактировать состав
// заявки (PurchaseItemsEditor readonly), но должен уметь перераспределить
// позиции по категориям/плановым позициям ФЭО построчно — эти изменения
// прилетают в те же wishForm.value.items объекты (FeoTreeSelect/FeoPlannedItemsSelect
// пишут в них напрямую через emitUpdate, независимо от readonly, который блокирует
// только название/кол-во/цену). Снимок feo_category_id/feo_planned_item_id на момент
// открытия карточки — чтобы понимать, что реально поменялось, и отправлять на
// PATCH /execution только эти два поля, никогда не состав. Снимок ключуется по id —
// позиции без id (только что добавленные автором, недоступно согласующему — состав
// у него readonly) в диф не попадают.
const wishItemsFeoSnapshot = ref<Map<number, { feo_category_id: number | null; feo_planned_item_id: number | null }>>(new Map())

function snapshotWishItemsFeo() {
  const m = new Map<number, { feo_category_id: number | null; feo_planned_item_id: number | null }>()
  for (const it of wishForm.value.items as any[]) {
    if (it.id != null) {
      m.set(it.id, {
        feo_category_id: it.feo_category_id ?? null,
        feo_planned_item_id: it.feo_planned_item_id ?? null,
      })
    }
  }
  wishItemsFeoSnapshot.value = m
}

const wishItemsFeoDirtyList = computed(() => {
  const out: { id: number; feo_category_id: number | null; feo_planned_item_id: number | null }[] = []
  for (const it of wishForm.value.items as any[]) {
    if (it.id == null) continue
    const before = wishItemsFeoSnapshot.value.get(it.id)
    if (!before) continue
    const catId = it.feo_category_id ?? null
    const planId = it.feo_planned_item_id ?? null
    if (before.feo_category_id !== catId || before.feo_planned_item_id !== planId) {
      out.push({ id: it.id, feo_category_id: catId, feo_planned_item_id: planId })
    }
  }
  return out
})
const wishItemsFeoDirty = computed(() => wishItemsFeoDirtyList.value.length > 0)

// ── ДЕФЕКТ 1 (владелец, 2026-08-20): автосохранение построчных ФЭО-правок ──────
// Дословно: «Я поменял плановую позицию футболки 10 шт с 15 на 10 и дальше нажал
// "Распределить и одобрить". Но этого не происходит, потому что мои изменения не
// сохраняются, они должны сохраняться автоматически, только когда я поменяю».
// Правки жили ТОЛЬКО в wishForm.value.items (см. wishItemsFeoDirtyList выше) до
// нажатия отдельной кнопки «Сохранить ФЭО» (saveExecution ниже) — «Распределить
// и одобрить» вообще перезагружает состав заявки СВЕЖИМ с сервера
// (openKanbanDialog → GET /wishes/{id}), поэтому только что сделанная правка
// терялась молча, а действие уходило со старыми данными.
//
// Правило проекта (feedback_new_field_three_places): валидация/серверное действие
// допускаются только ПОСЛЕ автосейва. Debounce 700мс на изменение
// wishItemsFeoDirtyList → тихая отправка PATCH /execution ТОЛЬКО с items (никогда
// executor_id/execution_deadline/event_id/feo_category_id/assigned_to — те поля
// патчатся, только если явно не null, см. patch_wish_execution в
// backend/app/routers/wishes.py, так что отправка одних items их не трогает).
// flushFeoAutosave() — обязательная точка перед approveWish/rejectWish/
// openKanbanDialog (единственные серверные действия формы, достижимые в
// состоянии, когда wishItemsFeoDirtyList вообще может быть непустым — см.
// разбор feoAttrsEditable/canEditWishFeo/canAssigneeAct у соответствующих
// кнопок; «Сохранить черновик»/«Отправить»/«Сохранить изменения» показываются
// только когда isWishEditable, а тогда feoAttrsEditable всегда false).
let feoAutosaveTimer: ReturnType<typeof setTimeout> | null = null
// Индикатор для UI (правило проекта: долгая операция без индикатора запрещена) —
// pending = тикает debounce, saving = запрос реально в полёте.
const feoAutosavePending = ref(false)
const feoAutosaveSaving = ref(false)
let feoAutosaveInFlight: Promise<boolean> | null = null

// Регресс (владелец, 2026-08-20): автосейв ФЭО добавлен для сценария согласующего/
// исполнителя на ОТПРАВЛЕННОЙ заявке — сервер (PATCH /wishes/{id}/execution, см.
// backend/app/routers/wishes.py::patch_wish_execution) отвечает 400 на любом другом
// статусе («Срок и исполнителя можно задать только на статусах submitted/approved»).
// В черновике (и rejected/converted) построчная правка ФЭО всё равно попадает в
// wishItemsFeoDirtyList (диф пишется напрямую в wishForm.items дочерними компонентами
// независимо от статуса), но сохраняется она обычным «Сохранить черновик»/PUT — не
// планируем автосейв там, где backend его гарантированно отклонит, иначе пользователь
// видит лишний красный тост про несуществующую проблему со сроком/исполнителем.
const feoAutosaveApplicable = computed(() =>
  !!editingWishId.value && ['submitted', 'approved'].includes((wishForm.value as any).status)
)

// Заявка №54 (владелец, 2026-09-04, дословно): «какого хуя ... автосохранение не
// удалось, с хуяли оно не удалось, если я везде поменял категорию ФЭО» — согласующий
// поменял категорию ФЭО в панели «Категория ФЭО (согласующий)» (wishFeoSelected), но
// не нажал «Сохранить ФЭО». wishForm.value.feo_category_id — категория, реально
// подтверждённая сервером (обновляется ТОЛЬКО после успешного PATCH /execution, см.
// applyFeoExecutionSuccess ниже и openEditDialog). Пока wishFeoSelected от неё
// отличается — шапка «грязная»: сервер всё ещё думает, что категория старая, а
// построчные правки (feoExecutionItemsPayload ниже), отправленные БЕЗ неё, будут
// сверяться с категорией позиции, которую сервер тоже не обновил, и 409-ить.
// Только для режима «одна категория на всех» — в feo_per_item=true у шапки вообще
// нет роли источника категории (см. buildWishPayload).
const wishFeoHeaderDirty = computed(() =>
  !!editingWishId.value &&
  !wishForm.value.feo_per_item &&
  (wishFeoSelected.value ?? null) !== (wishForm.value.feo_category_id ?? null)
)

// Единая формула категории позиции для PATCH /execution — ТА ЖЕ, что buildWishPayload
// использует для полного PUT-сохранения (см. feo_category_id: wishForm.value.feo_per_item
// ? ... : (feo ?? null) там): в режиме «одна на всех» эффективная категория КАЖДОЙ
// позиции — категория шапки (wishFeoSelected), а не собственное (возможно устаревшее)
// поле позиции — оно в этом режиме вообще не должно быть источником истины (см.
// комментарий у _effectiveFeoCategoryId в PurchaseItemsEditor.vue). Без этой единой
// точки построчный автосейв и кнопка «Сохранить ФЭО» слали РАЗНОЕ значение категории
// позиции, хотя категория заявки к этому моменту уже могла обновиться — и итог
// расходился с тем, что видит пользователь на экране (заявка №54).
function feoExecutionItemsPayload(): { id: number; feo_category_id: number | null; feo_planned_item_id: number | null }[] {
  return wishItemsFeoDirtyList.value.map(it => ({
    id: it.id,
    feo_category_id: wishForm.value.feo_per_item ? it.feo_category_id : (wishFeoSelected.value ?? null),
    feo_planned_item_id: it.feo_planned_item_id,
  }))
}

// Общий постобработчик успешного PATCH /execution — держит wishForm.value.feo_category_id
// (снимок «что реально на сервере», см. wishFeoHeaderDirty выше) синхронным с тем, что
// реально ушло в body.feo_category_id. Без этого поле оставалось замороженным на значении
// с момента открытия карточки (openEditDialog) НАВСЕГДА — ни ручное «Сохранить ФЭО», ни
// автосейв его не обновляли, и wishFeoHeaderDirty видел бы «грязную» шапку даже сразу
// после успешного сохранения.
function applyFeoExecutionSuccess(sentFeoCategoryId: number | null | undefined) {
  if (sentFeoCategoryId != null) wishForm.value.feo_category_id = sentFeoCategoryId
  snapshotWishItemsFeo()
  wishFormSavedSnapshot.value = wishPayloadSnapshotJson()
}

// Человекочитаемое сообщение об ошибке PATCH /execution. Пункт 3 задачи 2026-09-04
// (заявка №54): само по себе «категория А, а плановая категория Б» верно описывает
// сервер, но не говорит пользователю, что делать — теперь явно называем, что смена
// категории НЕ сохранилась, и что нажать.
function describeFeoExecutionError(e: any, headerWasDirty: boolean): string {
  const msg = e?.payload?.message ?? e?.detail ?? e?.message ?? 'не удалось сохранить'
  const status = e?.status != null ? ` (HTTP ${e.status})` : ''
  const hint = headerWasDirty
    ? ' Смена категории ФЭО заявки НЕ сохранена — категория позиции и выбранная категория заявки разошлись. Проверьте категорию/плановую позицию у товара и нажмите «Сохранить ФЭО» ещё раз.'
    : ''
  return `${msg}${status}.${hint}`
}

function scheduleFeoAutosave() {
  feoAutosavePending.value = true
  if (feoAutosaveTimer) clearTimeout(feoAutosaveTimer)
  feoAutosaveTimer = setTimeout(() => {
    feoAutosaveTimer = null
    void runFeoAutosave()
  }, 700)
}

// Правки построчного ФЭО пишутся напрямую в объекты wishForm.value.items дочерними
// компонентами (FeoTreeSelect/FeoPlannedItemsSelect, см. комментарий у
// wishItemsFeoSnapshot выше) — wishItemsFeoDirtyList уже computed поверх этого,
// пересчитывается на каждое изменение. Наблюдаем за НИМ, а не за items напрямую —
// он и так меняет ссылку при каждом релевантном изменении. Не планируем автосейв
// вовсе, если статус не submitted/approved (см. feoAutosaveApplicable выше) — правка
// остаётся в форме и уйдёт обычным сохранением заявки.
watch(() => wishItemsFeoDirtyList.value, (list) => {
  if (list.length > 0 && feoAutosaveApplicable.value) scheduleFeoAutosave()
})

// Если пока тикал debounce статус заявки перестал быть submitted/approved (например,
// подгрузка живого обновления откатила её) — гасим таймер без отправки: сработавший
// PATCH всё равно был бы отклонён backend'ом 400-й.
watch(feoAutosaveApplicable, (applicable) => {
  if (!applicable && feoAutosaveTimer) {
    clearTimeout(feoAutosaveTimer)
    feoAutosaveTimer = null
    feoAutosavePending.value = false
  }
})

async function runFeoAutosave(): Promise<boolean> {
  feoAutosavePending.value = false
  if (feoAutosaveInFlight) {
    // Уже летит запрос — items для НЕГО захвачены ДО этого await и правку,
    // сделанную ПОКА он в полёте, не содержат. Ждём его, затем пересчитываем
    // дифф заново (снимок уже обновлён завершившимся запросом) — если правка,
    // сделанная во время ожидания, всё ещё не сохранена, шлём её отдельным
    // запросом. Без этого повторного шага она молча пропала бы: снимок
    // обновляется по ТЕКУЩЕМУ состоянию формы, а не по тому, что реально ушло
    // на сервер.
    const prevOk = await feoAutosaveInFlight
    if (!prevOk) return false
  }
  // Статус сменился (или заявка ещё не сохранена) между планированием и срабатыванием —
  // backend отклонит PATCH /execution 400-й вне submitted/approved. Не шлём, но и не
  // считаем это ошибкой: правка жива в форме, уйдёт обычным сохранением. true — чтобы
  // flushFeoAutosave (п. задачи) не блокировал вызывающих там, где автосейв неприменим.
  if (!feoAutosaveApplicable.value) return true
  if (!editingWishId.value || wishItemsFeoDirtyList.value.length === 0) return true
  const items = feoExecutionItemsPayload()
  // Заявка №54 (п.1 задачи 2026-09-04): автосейв построчных правок — единственный
  // МОЛЧАЛИВЫЙ путь на сервер (кнопка «Сохранить ФЭО» рядом требует ручного клика).
  // Если к моменту срабатывания шапочная категория ФЭО ещё не сохранена
  // (wishFeoHeaderDirty), включаем её в ТОТ ЖЕ PATCH — иначе позиции уедут со
  // старой категорией заявки на сервере и 409-нут против уже выбранной пользователем
  // (см. описание бага выше и describeFeoExecutionError). Ручная кнопка «Сохранить
  // ФЭО» остаётся — это не второй путь сохранения, а тот же самый apiFetch-вызов,
  // просто включённый в тело автосейва вместо отдельного клика.
  const headerDirty = wishFeoHeaderDirty.value
  const body: any = { items }
  if (headerDirty) body.feo_category_id = wishFeoSelected.value
  feoAutosaveSaving.value = true
  const p = (async (): Promise<boolean> => {
    try {
      await apiFetch(`/wishes/${editingWishId.value}/execution`, {
        method: 'PATCH',
        body: JSON.stringify(body),
        suppressErrorDialog: true,
      })
      // Дефект 1 (владелец, 2026-08-20): buildWishPayload() включает feo_category_id/
      // feo_planned_item_id позиций — без обновления снимка здесь decideApprover/
      // approveWish видели бы ВЕЧНЫЙ ложный diff со снимком, взятым при открытии
      // карточки (wishFormSavedSnapshot обновлялся раньше только после PUT), и звали
      // saveWish там, где он не нужен и не должен вызываться.
      applyFeoExecutionSuccess(headerDirty ? body.feo_category_id : undefined)
      // Тихое подтверждение — короткий самоисчезающий тост (composables/useToast.ts
      // явно разрешает duration только для фонового автосейва, не для результата
      // ручного действия пользователя).
      showSnack(headerDirty ? 'ФЭО заявки и позиций сохранено' : 'ФЭО сохранено', 'success', { duration: 2000 })
      return true
    } catch (e: any) {
      showSnack(`Автосохранение ФЭО не удалось: ${describeFeoExecutionError(e, headerDirty)}`, 'error')
      return false
    } finally {
      feoAutosaveSaving.value = false
      feoAutosaveInFlight = null
    }
  })()
  feoAutosaveInFlight = p
  return p
}

// Обязательная точка перед серверными действиями формы (п.б задачи): гасит
// висящий debounce и шлёт правки немедленно, дожидается уже летящего запроса.
// false — сохранение реально требовалось и упало; вызывающий обязан НЕ выполнять
// действие (ошибку уже показал runFeoAutosave выше — не дублируем).
async function flushFeoAutosave(): Promise<boolean> {
  if (feoAutosaveTimer) {
    clearTimeout(feoAutosaveTimer)
    feoAutosaveTimer = null
    feoAutosavePending.value = false
  }
  if (feoAutosaveInFlight) {
    // См. комментарий в runFeoAutosave — после того как летящий запрос завершится
    // и обновит снимок, перепроверяем дифф заново, а не просто возвращаем его
    // результат: правка, сделанная, пока он летел, в его тело не попала.
    const ok = await feoAutosaveInFlight
    if (!ok) return false
  }
  if (wishItemsFeoDirtyList.value.length === 0) return true
  return runFeoAutosave()
}

onBeforeUnmount(() => {
  if (feoAutosaveTimer) clearTimeout(feoAutosaveTimer)
})

// Задача 2 (сессия 2026-08-20): живое обновление открытой заявки — работает
// только пока wishDialog открыт (useWishLive сам ставит/снимает setInterval +
// visibilitychange/focus по этому флагу и снимает их на unmount компонента).
// wishForm НЕ передаём и намеренно: composable обновляет только wishApprovers
// и перечисленные шапочные поля editingWish, чтобы не затереть несохранённые
// правки ФЭО (scheduleFeoAutosave/flushFeoAutosave выше).
const wishLive = useWishLive({
  wishId: editingWishId,
  isOpen: wishDialog,
  approvers: wishApprovers,
  wish: editingWish,
  currentUserId,
  isAutosaveBusy: () => feoAutosaveSaving.value || feoAutosavePending.value,
  showSnack,
  shortName,
  onExternalChange: () => {
    loadWishes()
    loadAllWishes()
    refreshMyPendingApprovals()
  },
})

async function saveExecution() {
  if (!editingWishId.value) { showSnack('Сначала сохраните заявку', 'warning'); return }
  // «Сохранить ФЭО» больше не единственный способ сохранить (п.в задачи), но
  // остаётся ручным путём — гасим висящий автосейв-debounce и дожидаемся уже
  // летящего запроса, чтобы не отправить items дважды гонкой (единый источник
  // истины на подпись — runFeoAutosave/эта функция никогда не выполняются
  // параллельно друг с другом).
  if (feoAutosaveTimer) { clearTimeout(feoAutosaveTimer); feoAutosaveTimer = null; feoAutosavePending.value = false }
  if (feoAutosaveInFlight) await feoAutosaveInFlight
  savingExecution.value = true
  try {
    const body: any = {
      executor_id: wishForm.value.executor_id,
      execution_deadline: wishForm.value.execution_deadline || null,
      event_id: wishForm.value.event_id,
      feo_category_id: wishFeoSelected.value || wishForm.value.feo_category_id,
      assigned_to: wishForm.value.assigned_to,
    }
    if (wishItemsFeoDirtyList.value.length > 0) {
      // Заявка №54 (п.4 задачи 2026-09-04): та же формула категории позиции, что и
      // автосейв (feoExecutionItemsPayload) — раньше кнопка слала item.feo_category_id
      // «как есть» (возможно устаревшее в режиме «одна категория на всех»), и ручное
      // «Сохранить ФЭО» могло 409-ить по той же причине, что и автосейв.
      body.items = feoExecutionItemsPayload()
    }
    await apiFetch(`/wishes/${editingWishId.value}/execution`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    })
    showSnack('Сохранено: исполнитель / срок / мероприятие / ФЭО / получатель')
    // Дефект 1 (владелец, 2026-08-20): см. тот же комментарий в runFeoAutosave — без
    // этого diff со снимком «как загружено» оставался бы вечным и ложным. Плюс держит
    // wishForm.value.feo_category_id синхронным с сервером (wishFeoHeaderDirty выше).
    applyFeoExecutionSuccess(body.feo_category_id)
    await reloadActiveTab()
  } catch (e: any) {
    showSnack(`Ошибка: ${describeFeoExecutionError(e, wishFeoHeaderDirty.value)}`, 'error')
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
// Владелец (2026-09-03), дословно: «когда выбираешь согласующего, предлагает
// "Построить цепочку", даже если эту кнопку не нажимаешь, то цепочка всё
// равно строится» — раньше здесь при отправке на согласование МОЛЧА вызывался
// callCascadeApi (build_ascending_chain), который достраивал ПРОМЕЖУТОЧНЫЕ
// звенья между автором и выбранным «верхним согласующим», даже если кнопку
// «Построить цепочку» никто не нажимал. Теперь: не нажал кнопку — цепочка НЕ
// строится вообще, согласующим становится РОВНО тот человек, что выбран в
// поле «Верхний согласующий» (без каскада). Кнопка «Построить цепочку» —
// единственный способ реально построить цепочку (см. runCascade выше).
async function ensureApprovers(wishId: number): Promise<boolean> {
  if (wishApprovers.value.length > 0) return true
  if (!approverTopUser.value) return false
  try {
    await apiFetch(`/wishes/${wishId}/approvers`, {
      method: 'POST', body: JSON.stringify({ user_id: approverTopUser.value }),
    })
    await loadWishApprovers()
    approverTopUser.value = null
    showSnack('Согласующий добавлен')
    return wishApprovers.value.length > 0
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось добавить согласующего', 'error')
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
  // Дефект 1 (владелец, 2026-08-20): согласующий из цепочки правит категории ФЭО
  // построчно (canEditWishFeo) — эти правки летят автосейвом на PATCH /execution
  // (см. runFeoAutosave), НЕ через saveWish/PUT. Флаш ПЕРВЫМ — гасит висящий
  // debounce и дожидается уже летящего запроса, чтобы «Согласовать» не ушло со
  // старыми плановыми позициями. Флаш упал — решение не отправляем, причину уже
  // показал сам runFeoAutosave.
  const flushedFeo = await flushFeoAutosave()
  if (!flushedFeo) return
  // Пункт 3 (владелец, 2026-08-13): реальный сценарий жалобы — в открытой карточке
  // поменял привязку ФЭО, нажал «Согласовать» (эта кнопка), нажал «Сохранить изменения»:
  // согласование легло ДО сохранения, а сохранение потом сбрасывало его поверх свежего
  // согласования. Фикс: несохранённые правки формы сохраняем СНАЧАЛА (тем же путём,
  // что кнопка «Сохранить изменения» — saveWish, код не дублируем), и только потом
  // шлём решение по согласованию. Правок нет — лишний PUT не шлём. Сохранение упало —
  // решение не отправляем, ошибку сервера уже показал сам saveWish.
  // Дефект 1 (владелец, 2026-08-20): PUT /wishes/{id} доступен только автору/участнику
  // (backend update_wish) — согласующий из цепочки, у которого isWishEditable=false
  // (статус submitted), туда попадать не должен вовсе: его правки уже ушли автосейвом
  // выше, а wishFormSavedSnapshot он в принципе не может сравнять с текущим payload
  // (тело заявки ему readonly), diff был бы вечным и ложным.
  if (decision === 'approved' && isWishEditable.value) {
    const currentSnapshot = wishPayloadSnapshotJson()
    if (currentSnapshot && currentSnapshot !== wishFormSavedSnapshot.value) {
      const saved = await saveWish(false)
      if (!saved) return
    }
  }
  decideLoading.value = approvalId
  try {
    const res = await apiFetch<{
      status: string
      convert_error?: string | null
      approvers: WishApprover[]
      excess_warnings?: ExcessWarning[]
      purchases?: { id: number; registry_number?: string | null }[]
      purchase_sync?: PurchaseSync | null
    }>(
      `/wishes/${editingWishId.value}/approvers/${approvalId}/decide`,
      { method: 'POST', body: JSON.stringify({ decision, comment: decideComment.value[approvalId] || null }) },
    )
    wishApprovers.value = res.approvers
    decideComment.value[approvalId] = ''
    if (wishForm.value) (wishForm.value as any).status = res.status
    // QA (сессия 2026-08-20): свежий ответ decide применён выше — сообщаем
    // useWishLive, что локальное состояние продвинулось дальше, чтобы уже
    // летящий фоновый тик не перезатёр его своим устаревшим снимком (см.
    // комментарий у markLocalUpdate в composables/useWishLive.ts).
    wishLive.markLocalUpdate()
    // Владелец (2026-08-20): согласование ПОСЛЕДНИМ в цепочке само создаёт закупку
    // и переводит заявку в 'converted' на бэке (см. wish_approvals.py::decide) — не
    // просто «Согласовано», а явно сказать, что заявка уехала в закупку, иначе
    // пользователь не понимает, что делать дальше (и раньше сам нажимал «Передать
    // в План закупок» второй раз, получая красную ошибку поверх настоящего успеха).
    const _convertedPurchase = res.status === 'converted' ? (res.purchases || [])[0] : null
    if (res.convert_error) showSnack(res.convert_error, 'warning')
    else if (_convertedPurchase)
      showSnack(`Заявка согласована и перенесена в закупку ${_convertedPurchase.registry_number || `№${_convertedPurchase.id}`}`)
    else showSnack(decision === 'approved' ? 'Согласовано' : 'Отклонено')
    showExcessWarnings(res.excess_warnings, 'Заявка согласована, закупка создана.')
    showPurchaseSync(res.purchase_sync)
    await loadWishOnce()
    await loadWishes()
    refreshMyPendingApprovals()  // бейдж «мои согласования» в сайдбаре
  } catch (e: any) {
    // Гейт ФЭО (владелец, 2026-08-11): последний согласующий цепочки может упереться
    // в 409 missing_feo_category (backend откатывает decision, заявка НЕ зависает —
    // остаётся 'submitted', попробовать decide можно снова после выбора категории).
    const handled = editingWish.value ? await handleMissingFeoCategoryError(e, editingWish.value) : false
    if (!handled) {
      showSnack(e?.payload?.message ?? e?.detail ?? e?.message ?? 'Не удалось сохранить решение', 'error')
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
  // Задача 2 (сессия 2026-08-20, живое обновление): editingWish.status обновляется
  // композаблом useWishLive независимо от wishForm (который живым тиком НЕ трогаем,
  // чтобы не затирать несохранённые правки ФЭО) — если пока пользователь сидел в
  // диалоге, заявку отклонил/согласовал кто-то другой (что после отклонения сбрасывает
  // остальные строки цепочки обратно в pending, см. backend _reset_approvals), кнопки
  // решения обязаны спрятаться и без перезагрузки формы. wishForm.status при этом
  // остаётся статичным «submitted» до явного действия — сверяем со свежим editingWish.
  if (editingWish.value && editingWish.value.status !== 'submitted') return false
  const mine = a.user_id === currentUserId || isAdmin.value
  if (!mine) return false
  if (approvalMode.value === 'sequential') {
    const lowerPending = wishApprovers.value.some(x => x.order_num < a.order_num && x.status === 'pending')
    if (lowerPending) return false
  }
  return true
}
// Задача 1: решает не сам назначенный (менеджер+/SaaS решает вместо него) —
// зеркалит backend-гейт wish_approvals.py::decide_wish_approval (a.user_id != current_user.id).
function isDecidingOnBehalf(a: WishApprover): boolean {
  return a.user_id !== currentUserId
}
// Строка решения под именем в цепочке: кто и когда решил, и решал ли не за себя.
// Ничего не показываем, пока решения нет (decided_at пуст / статус ещё pending/skipped).
function approverDecisionLine(a: WishApprover): string | null {
  if (!a.decided_at || (a.status !== 'approved' && a.status !== 'rejected')) return null
  const when = formatDateTime(a.decided_at)
  if (a.is_on_behalf) {
    const verb = a.status === 'rejected' ? 'Отклонил' : 'Согласовал'
    const who = shortName(a.decided_by_name) || a.decided_by_name || '—'
    const whom = shortName(a.full_name) || a.full_name || '—'
    return `${verb}: ${who} вместо ${whom} · ${when}`
  }
  const verb = a.status === 'rejected' ? 'Отклонено' : 'Согласовано'
  return `${verb} ${when}`
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

// Снимок последнего сохранённого/загруженного состояния формы заявки — используется
// approveWish (пункт 3, владелец 2026-08-13), чтобы не слать лишний PUT, если правок
// со времени открытия карточки/последнего сохранения не было.
const wishFormSavedSnapshot = ref<string>('')

// Собирает PUT/POST-payload заявки из wishForm — вынесено из saveWish, чтобы
// approveWish мог построить ТОТ ЖЕ payload для сравнения со снимком, не дублируя
// логику сохранения (пункт 3, владелец 2026-08-13).
function buildWishPayload() {
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
  return {
    ...wishForm.value,
    feo_category_id: feo,
    // Владелец, 2026-08-19: тумблер вернули — feo_per_item снова реальный флаг формы
    // (wishForm.value.feo_per_item), а не жёстко true. Явная строка здесь чисто
    // документирующая (значение и так уже уехало через ...wishForm.value выше) — оставлена,
    // чтобы читатель не искал его глазами по всему объекту.
    feo_per_item: wishForm.value.feo_per_item,
    title,
    // Контрагент — необязательное поле, снятие должно долетать до бэкенда как явный
    // null (backend различает «null» = очистить от «ключ отсутствует» = не трогать,
    // см. update_wish в backend/app/routers/wishes.py). wishForm хранит contractor_id
    // как null уже по умолчанию, но contractor_name — как '' (пустая строка, не null:
    // так исторически инициализировано поле формы), и ContractorPicker/ручная очистка
    // текстового поля не гарантированно приходят null-ом. Нормализуем оба явным null
    // при пустом значении здесь, в одном месте построения payload — иначе «снятие»
    // контрагента через очистку текстового поля тихо сохранило бы пустую строку
    // вместо NULL в БД.
    contractor_id: wishForm.value.contractor_id || null,
    contractor_name: (wishForm.value.contractor_name || '').toString().trim() || null,
    items: wishForm.value.items
      // Пустые строки-заготовки (фронт создаёт их заранее для будущего ввода) не отправляем —
      // иначе они оседают в БД как «1 шт · 0 ₽» и «удаление» позиции визуально не работает
      // (см. баг: владелец удаляет вторую пустую позицию, обновляет страницу — она снова там).
      // Строку оставляем, если заполнено хоть наименование, хоть сумма (частичный ввод).
      .filter((it: any) => (it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity))
      .map(({ _selectedProduct, _photo_url, _description, _description_44fz, _price_meta, ...rest }) => ({
        ...rest,
        // Владелец, 2026-08-19: тумблер вернули — режим снова определяет, чья категория
        // «главная». feo_per_item=false («одна на всех», общий выбор в карточке «Позиции»):
        // ВСЯ заявка получает ОДНУ категорию — построчное значение (даже если где-то осталось
        // от предыдущего режима) игнорируется целиком, иначе «одна категория на всех» была бы
        // неправдой при сохранении (см. п.2 задачи 2026-08-19; именно поэтому
        // onWishFeoPerItemChange спрашивает подтверждение при выключении, если позиции уже
        // разошлись по разным категориям). feo_per_item=true («каждому своя», как было
        // единственным режимом 2026-08-17..08-19): построчный выбор — источник истины, шапка —
        // только дефолт для позиций БЕЗ своей категории (правило проекта: выбранное на
        // предыдущем этапе не меняется само).
        feo_category_id: wishForm.value.feo_per_item
          ? ((rest as any).feo_category_id ?? feo ?? null)
          : (feo ?? null),
        // Владелец (сессия 2026-08-21, п.7 задачи): «каждому товару надо присваивать свою
        // плановую» — feo_planned_item_id ВСЕГДА построчный, в ОБОИХ режимах. В отличие от
        // feo_category_id выше (которая в режиме «одна на всех» единая на всю заявку),
        // никакого шапочного значения для плановой позиции больше нет — построчный выбор
        // работает и когда категория общая (см. allow-per-item-plan="true" в шаблоне,
        // FeoPlannedItemsSelect берёт категорию из фолбэка defaultFeoCategoryId).
        feo_planned_item_id: (rest as any).feo_planned_item_id ?? null,
        // БАГ 3 (сессия 2026-08-05): UI больше не выставляет over_plan (псевдо-вариант
        // «Вне плана» убран) — колонка в БД и расчёты на бэкенде не тронуты, просто
        // отправляем то, что уже было на позиции (false для новых/непривязанных).
        over_plan: !!((rest as any).over_plan),
      })),
  }
}

// Возвращает JSON-снимок текущего payload формы для сравнения «есть ли несохранённые
// правки» (approveWish, пункт 3). try/catch — сериализация не должна ронять approve.
function wishPayloadSnapshotJson(): string {
  try { return JSON.stringify(buildWishPayload()) } catch { return '' }
}

// TODO: B8 — нужен отдельный endpoint PATCH /wishes/{id}/feo для approver на submitted-заявке
// Возвращает true при успешном сохранении, false при ошибке (approveWish, пункт 3,
// проверяет это перед отправкой согласования — существующие вызовы результат игнорируют).
async function saveWish(andSubmit = false): Promise<boolean> {
  // Черновик можно сохранить всегда — прерваться на любом этапе (даже 200 позиций,
  // часть не в каталоге). Валидацию формы требуем только при отправке на согласование.
  if (andSubmit) {
    const { valid } = await wishFormRef.value?.validate() ?? { valid: true }
    if (!valid) { await nextTick(); showValidationArrows(); return false }
    // Жёсткий гейт (владелец, 2026-08-11, переведён на позиции 2026-08-19, объединён с
    // проверкой нелистового узла в тот же день — тумблер «Не указывать последний уровень
    // ФЭО» убран): без КОНЕЧНОЙ категории ФЭО хотя бы у одной непустой позиции заявку
    // нельзя отправить на согласование — иначе одобряющий упрётся в 409 от backend, а
    // созданная из неё закупка рискует остаться сиротой вне всех планов ФЭО (см.
    // wishFeoCategoryMissing / wishItemsMissingFeoCategory).
    if (wishFeoCategoryMissing.value) {
      // Владелец, 2026-08-19: тумблер вернули — сообщение снова режимо-зависимое (п.4
      // задачи): «одна на всех» указывает на общий выбор, «каждому своя» — на позиции поимённо.
      const message = wishForm.value.feo_per_item
        ? `Нельзя отправить на согласование: не выбрана конечная категория ФЭО у позиций (${wishItemsMissingFeoCategory.value.map((it: any) => it.item_name || 'без названия').join(', ')}). Выберите категорию в таблице позиций, углубившись до конечного уровня, либо «Не определена», если категория неизвестна.`
        : 'Нельзя отправить на согласование: не выбрана конечная категория ФЭО заявки. Выберите категорию в блоке выше, углубившись до конечного уровня, либо «Не определена», если категория неизвестна.'
      showSnack(message, 'error')
      await nextTick()
      highlightMissingFeoCategory()
      return false
    }
    // F-PLAN: в ветке выбранной категории ФЭО есть плановые позиции плана закупок, но
    // не у всех позиций заявки выбрана своя. БАГ 3 (сессия 2026-08-05): псевдо-вариант
    // «Вне плана» убран — непривязанная позиция просто увеличит плановую сумму
    // категории, поэтому это НЕ блокирует отправку — только мягкое предупреждение.
    // Владелец, 2026-08-21: предупреждение больше НЕ режимо-зависимое — плановая позиция
    // всегда построчная (п.7 задачи), поэтому обе ветки одинаково перечисляют строки
    // по номеру и названию, как раньше делал только режим «каждому своя».
    if (wishFeoBranchHasPlannedItems.value) {
      // Жалоба владельца 2026-08-20: снекбар не называл ни заявку, ни конкретные позиции —
      // «какой заявки, к чему относится, непонятно». Теперь префикс с номером/предметом
      // заявки (тот же номер, что в шапке диалога, см. v-card-title) — как для новой заявки
      // (editingWishId ещё нет), так и для существующей.
      const wishLabel = (editingWishId.value ? `Заявка №${editingWishId.value}` : 'Новая заявка')
        + (wishForm.value.title ? ` «${wishForm.value.title}»` : '')
      // Номер позиции — как в таблице позиций (PurchaseItemsEditor нумерует №${idx+1}).
      // Пустые строки-заготовки не учитываем — тот же фильтр, что и у остальных проверок формы.
      const unfilledItems = (wishForm.value.items as any[])
        .map((it: any, idx: number) => ({ it, idx }))
        .filter(({ it }) => (
          ((it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity))
          && it.feo_planned_item_id == null
        ))
      if (unfilledItems.length > 0) {
        const names = unfilledItems.slice(0, 5)
          .map(({ it, idx }) => `№${idx + 1} «${it.item_name || 'без названия'}»`)
          .join(', ')
        const more = unfilledItems.length > 5 ? `, …и ещё ${unfilledItems.length - 5}` : ''
        showSnack(`${wishLabel}: позиции без плановой позиции плана закупок — ${names}${more}. Выберите её или создайте новую кнопкой «Создать в плане закупок» — без выбора позиция увеличит плановую сумму категории.`, 'warning')
      }
    }
  }

  saving.value = true
  try {
    const payload = buildWishPayload()

    if (editingWishId.value) {
      const currentStatus = (wishForm.value as any).status || 'draft'
      // Жалоба владельца 2026-08-13: раньше текст снекбара выбирался по статусу ДО
      // сохранения и не смотрел на ответ сервера — «отправлена на повторное согласование»
      // всплывало даже когда бэкенд ничего не сбрасывал (привязка к ФЭО — не смена
      // предмета закупки). Теперь смотрим на факт: что реально вернул PUT.
      const putResp = await apiFetch<any>(`/wishes/${editingWishId.value}`, { method: 'PUT', body: JSON.stringify(payload) })
      const newStatus = putResp?.status || currentStatus
      // Пункт 3 (владелец, 2026-08-13): снимок того, что реально уехало на сервер —
      // approveWish сравнивает с ним, чтобы не слать повторный PUT без правок.
      wishFormSavedSnapshot.value = JSON.stringify(payload)
      if (andSubmit && ['draft', 'rejected'].includes(currentStatus)) {
        const hasApprovers = await ensureApprovers(editingWishId.value)
        if (!hasApprovers) {
          showSnack('Не выбраны согласующие. Выберите «Верхнего согласующего» в разделе «Согласующие» — цепочка построится автоматически.', 'error')
          await nextTick()
          highlightMissingApprovers()
          return false
        }
        await apiFetch(`/wishes/${editingWishId.value}/submit`, { method: 'POST' })
        showSnack('Заявка отправлена на согласование')
      } else if (['approved', 'converted'].includes(currentStatus) && newStatus === 'submitted') {
        // Бэкенд реально сбросил согласование (изменился предмет закупки) — /submit не нужен.
        showSnack('Заявка изменена по существу и ушла на повторное согласование', 'error')
        await loadWishApprovers()
      } else if (['approved', 'converted'].includes(currentStatus)) {
        // Статус не изменился — сохранили несущественную правку (например, привязку к ФЭО),
        // согласование бэкенд не трогал.
        showSnack('Заявка обновлена, согласование сохранено')
      } else {
        showSnack('Заявка обновлена')
      }
    } else {
      const created = await apiFetch<any>('/wishes/', { method: 'POST', body: JSON.stringify(payload) })
      wishFormSavedSnapshot.value = JSON.stringify(payload)
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
          await nextTick()
          highlightMissingApprovers()
          return false
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
        return true
      }
    }

    wishDialog.value = false
    await reloadActiveTab()
    return true
  } catch (e: any) {
    // T3: 409 missing_needed_dates — не закрывать диалог, включить per-item режим.
    // editingWish может быть null при СОЗДАНИИ новой заявки (только что переведена в
    // per-item и отправлена без даты) — handleMissingDatesError теперь это допускает.
    if (await handleMissingDatesError(e, editingWish.value)) {
      return false
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
    return false
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

// T3: общий обработчик 409 missing_needed_dates — используется в approveWish/saveWish/submitWish.
// wish необязателен: при СОЗДАНИИ новой заявки editingWish ещё null (openEditDialog его не
// выставляла — заявки ещё не существовало), но диалог создания и так уже открыт, поэтому
// открывать нечего.
async function handleMissingDatesError(e: any, wish?: Wish | null) {
  const det = e?.payload?.details
  if (e?.status !== 409 || det?.error_code !== 'missing_needed_dates') return false
  const missingIds: number[] = det.missing_item_ids || []
  const missingNames: string[] = det.missing_item_names || []
  wishConvertError.value = {
    message: det.message || e.message,
    missingItemIds: missingIds,
    missingItemNames: missingNames,
  }
  // Убедиться, что диалог открыт (только если известна заявка и диалог реально закрыт —
  // при создании новой заявки диалог уже открыт и wish ещё не существует)
  if (!wishDialog.value && wish) {
    await openEditDialog(wish)
  }
  // Переключить в per-item режим дат и подсветить проблемные позиции
  if (missingIds.length > 0) {
    if (wishDateMode.value !== 'per_item') wishDateMode.value = 'per_item'
    await nextTick()
    highlightMissingDateItems(missingIds, missingNames)
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
  // Пункт 3 (владелец, 2026-08-13): реальный сценарий жалобы — в открытой карточке
  // поменял привязку ФЭО, нажал «Согласовал», нажал «Сохранить изменения»: согласование
  // легло ДО сохранения, а сохранение потом сбрасывало его поверх свежего согласования
  // (актуально и для других существенных полей — количество, цена — не только ФЭО).
  // Фикс: если карточка ЭТОЙ заявки открыта и есть несохранённые правки — сохраняем их
  // СНАЧАЛА тем же путём, что кнопка «Сохранить изменения» (saveWish, не дублируем код),
  // и только потом шлём согласование. Правок нет — лишний PUT не шлём.
  if (wishDialog.value && editingWishId.value === wish.id) {
    // Дефект 1 (владелец, 2026-08-20): та же логика для построчных ФЭО-правок
    // согласующего (wishItemsFeoDirtyList) — «Одобрить без согласования остальных»
    // не должно уходить старыми плановыми позициями. Флаш ПЕРВЫМ — до общего
    // saveWish, чтобы при ошибке сохранения ФЭО согласование точно не ушло.
    const flushedFeo = await flushFeoAutosave()
    if (!flushedFeo) return // flushFeoAutosave/runFeoAutosave уже показал причину — не дублируем
    // Дефект 1 (владелец, 2026-08-20): PUT /wishes/{id} доступен только автору/участнику —
    // согласующему (isWishEditable=false на статусе submitted) хватает автосейва ФЭО выше,
    // saveWish/PUT ему вызывать не за чем и он вернёт 403 (см. decideApprover, тот же гейт).
    if (isWishEditable.value) {
      const currentSnapshot = wishPayloadSnapshotJson()
      if (currentSnapshot && currentSnapshot !== wishFormSavedSnapshot.value) {
        const saved = await saveWish(false)
        if (!saved) return // saveWish уже показал ошибку сервера (правило: не глотать) — согласование не шлём
      }
    }
  }

  approvingId.value = wish.id
  try {
    const res = await apiFetch<{
      status?: string
      convert_warning?: string | null
      excess_warnings?: ExcessWarning[]
      purchases?: { id: number; registry_number?: string | null }[]
      purchase_sync?: PurchaseSync | null
    }>(`/wishes/${wish.id}/approve`, { method: 'POST' })
    // Владелец (2026-08-20): «Одобрить без согласования остальных» тоже создаёт
    // закупку сразу (wish.status становится 'converted' на бэке) — говорим об этом
    // явно, той же формулировкой, что и цепочка согласующих (decideApprover), иначе
    // пользователь не понимает, что закупка уже готова и второй раз жать не нужно.
    const _convertedPurchase = res?.status === 'converted' ? (res.purchases || [])[0] : null
    if (res?.convert_warning) showSnack(res.convert_warning, 'warning')
    else if (_convertedPurchase)
      showSnack(`Заявка одобрена и перенесена в закупку ${_convertedPurchase.registry_number || `№${_convertedPurchase.id}`}`)
    else showSnack('Заявка одобрена')
    showExcessWarnings(res?.excess_warnings, 'Заявка одобрена, закупка создана.')
    showPurchaseSync(res?.purchase_sync)
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
function highlightMissingDateItems(missingItemIds: number[], missingItemNames: string[] = []) {
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
  let missingIndexes = new Set(
    items.map((it: any, idx: number) => missingItemIds.includes(it.id) ? idx : -1).filter((i: number) => i !== -1)
  )
  // (б) У ТОЛЬКО ЧТО СОЗДАННОЙ заявки локальные строки формы ещё не имеют серверных id
  // (заявка создаётся, а следом сразу шлётся submit) — сопоставление по id даёт пусто.
  // Пробуем сопоставить по нормализованному имени позиции, которое сервер прислал вместе
  // с missing_item_ids.
  if (!missingIndexes.size && missingItemNames.length) {
    const namesNorm = new Set(missingItemNames.map(n => String(n).trim().toLowerCase()).filter(Boolean))
    missingIndexes = new Set(
      items
        .map((it: any, idx: number) => namesNorm.has(String(it.item_name || '').trim().toLowerCase()) ? idx : -1)
        .filter((i: number) => i !== -1)
    )
  }
  // (в) Если и по имени сопоставить не удалось (например сервер имена не прислал) — считаем
  // проблемными ВСЕ непустые строки без даты потребности. Условие «непустая строка» —
  // то же самое, что используется при фильтрации payload перед отправкой в saveWish.
  if (!missingIndexes.size) {
    missingIndexes = new Set(
      items
        .map((it: any, idx: number) => {
          const nonEmpty = (it.item_name || '').toString().trim() || Number(it.total_price) || Number(it.quantity)
          return (nonEmpty && !it.needed_date) ? idx : -1
        })
        .filter((i: number) => i !== -1)
    )
  }
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

  // Стрелка от кнопки отправки к подсвеченным строкам (как highlightMissingFeoCategory)
  pointArrowsTo(highlighted)
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
      pointArrowsTo([wrap])
    }
  }
}

// ── Kanban distribution (Phase 13) ─────────────────────────────────────
async function openKanbanDialog(wish: Wish) {
  // Дефект 1 (владелец, 2026-08-20): «нажал "Распределить и одобрить". Но этого
  // не происходит, потому что мои изменения не сохраняются» — этот диалог грузит
  // состав заявки СВЕЖИМ с сервера (GET /wishes/{id} ниже), поэтому несохранённая
  // построчная ФЭО-правка терялась молча ещё ДО открытия кнопки «Распределить».
  // Кнопка закрывает wishDialog синхронно (см. @click="openKanbanDialog(editingWish);
  // wishDialog = false" в шаблоне), так что здесь, как и в rejectWish, гейт — только
  // по совпадению id, не по wishDialog.value. Флаш упал — диалог распределения не
  // открываем вообще (иначе он покажет старые данные), причину уже показал
  // runFeoAutosave.
  if (editingWishId.value === wish.id) {
    const flushedFeo = await flushFeoAutosave()
    if (!flushedFeo) return
  }
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
  // Дефект 1 (владелец, 2026-08-20): кнопка «Отклонить» закрывает wishDialog
  // СИНХРОННО, до открытия диалога причины (см. @click="openRejectDialog(editingWish);
  // wishDialog = false" в шаблоне) — к моменту вызова этой функции wishDialog уже
  // false, поэтому здесь (в отличие от approveWish) флаш НЕ гейтуется на
  // wishDialog.value, только на совпадение id — та же заявка, чья форма ещё
  // держит несохранённые построчные ФЭО-правки.
  if (editingWishId.value === rejectingWishItem.value.id) {
    const flushedFeo = await flushFeoAutosave()
    if (!flushedFeo) return
  }
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

// ── Остановка заявки (владелец, 2026-08-13): «Останавливать могут все» — доступно
// любому, кто видит заявку, без ролевых проверок. Причина необязательна.
const stopDialog = ref(false)
const stoppingWish = ref(false)
const stopReason = ref('')
const stoppingWishItem = ref<Wish | null>(null)

function openStopDialog(wish: Wish) {
  stoppingWishItem.value = wish
  stopReason.value = ''
  stopDialog.value = true
}

async function confirmStopWish() {
  if (!stoppingWishItem.value) return
  stoppingWish.value = true
  try {
    const body: Record<string, string> = {}
    if (stopReason.value.trim()) body.reason = stopReason.value.trim()
    const updated = await apiFetch<Wish>(`/wishes/${stoppingWishItem.value.id}/stop`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
    showSnack(
      updated?.stopped_partial ? 'Заявка остановлена частично' : 'Заявка остановлена',
      updated?.stopped_partial ? 'warning' : 'success',
    )
    stopDialog.value = false
    // Обновить открытую карточку заявки на лету, без ожидания перезагрузки списка
    if (editingWish.value && editingWish.value.id === stoppingWishItem.value.id) {
      editingWish.value = { ...editingWish.value, ...updated }
    }
    await reloadActiveTab()
  } catch (e: any) {
    showSnack(`Не удалось остановить заявку: ${e?.payload?.message || e?.message || 'неизвестная ошибка'}`, 'error')
  } finally {
    stoppingWish.value = false
  }
}

// ── Копирование заявки (владелец, 2026-08-13): «переделывать большие заявки без
// двойной работы» — копируются только позиции (наименование/тип/кол-во/ед./
// страна), остальное дозаполняется. Открывает копию сразу на редактирование.
const copyingId = ref<number | null>(null)

async function copyWish(wish: Wish) {
  copyingId.value = wish.id
  try {
    const created = await apiFetch<Wish>(`/wishes/${wish.id}/copy`, { method: 'POST' })
    showSnack('Заявка скопирована — дозаполните недостающее')
    wishDialog.value = false
    await reloadActiveTab()
    if (created?.id) await openEditDialog(created)
  } catch (e: any) {
    showSnack(`Не удалось скопировать заявку: ${e?.payload?.message || e?.message || 'неизвестная ошибка'}`, 'error')
  } finally {
    copyingId.value = null
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
    const result = await apiFetch<{
      wish_id: number
      purchase_id: number
      status: string
      registry_number?: string | null
      already_converted?: boolean
      excess_warnings?: ExcessWarning[]
      purchase_sync?: PurchaseSync | null
    }>(
      `/wishes/${convertingWish.value.id}/convert`,
      { method: 'POST', body: JSON.stringify(body) }
    )
    // Владелец (2026-08-20): идемпотентность — заявка могла уже уехать в закупку
    // раньше (согласование последним в цепочке / «Одобрить» делают это сами), этот
    // клик просто подтверждает то же самое, а не создаёт вторую закупку. Раньше это
    // падало 400 «должна быть approved» — теперь бэк отдаёт ту же закупку 200-м с
    // already_converted:true, показываем это честно, не как «закупка создана».
    if (result.already_converted) {
      showSnack(`Закупка уже создана: ${result.registry_number || `№${result.purchase_id}`}`)
    } else {
      showSnack('Закупка создана')
      showExcessWarnings(result.excess_warnings, 'Закупка создана.')
    }
    // Задача владельца (сессия 2026-08-21): «повторное согласование обновляет
    // закупку из заявки» — показываем ОБА случая (свежесозданную и уже
    // существующую, но обновлённую/заблокированную), не только «создана».
    showPurchaseSync(result.purchase_sync)
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
  subsidy_name: null,
  wish_total: null,
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
  subsidy_name: null,
  wish_total: null,
  created_at: null,
  desired_date: null,
  executor_name: null,
  execution_deadline: null,
})

// Владелец, 2026-09-02: список значений для enum-фильтра колонки «Субсидия» — образец OrdersView.vue.
function uniqWishValues(rows: Wish[], key: string): (string | number | null)[] {
  const set = new Set<any>()
  rows.forEach(r => set.add((r as any)?.[key] ?? null))
  return [...set].sort((a, b) => String(a ?? '').localeCompare(String(b ?? '')))
}

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
  // enum filter for subsidy_name
  if (colFilters.value.subsidy_name?.type === 'enum' && Array.isArray(colFilters.value.subsidy_name.values) && colFilters.value.subsidy_name.values.length)
    result = result.filter(r => colFilters.value.subsidy_name.values.includes((r as any).subsidy_name ?? null))
  // number filter for wish_total (сумма заявки)
  if (colFilters.value.wish_total?.type === 'number') {
    const { min, max } = colFilters.value.wish_total
    result = result.filter(r => {
      const v = wishItemsTotal(r)
      if (v == null) return false
      if (min != null && v < min) return false
      if (max != null && v > max) return false
      return true
    })
  }
  // sort: pick first active sort
  const activeSort = Object.entries(colSort.value).find(([_, v]) => v)
  if (activeSort) {
    const [k, dir] = activeSort
    if (k === 'wish_total') {
      result.sort((a, b) => {
        const va = wishItemsTotal(a) ?? -Infinity
        const vb = wishItemsTotal(b) ?? -Infinity
        return dir === 'asc' ? va - vb : vb - va
      })
    } else {
      result.sort((a: any, b: any) => {
        const pick = (r: any) => k === 'approver_names' ? wishRecipients(r) : r[k === 'title_col' ? 'title' : k]
        const va = pick(a) ?? ''
        const vb = pick(b) ?? ''
        const cmp = String(va).localeCompare(String(vb), 'ru', { numeric: true })
        return dir === 'asc' ? cmp : -cmp
      })
    }
  }
  return result
}

const myWishesFiltered = computed(() => applyColFilters(myWishes.value))
const incomingWishesFiltered = computed(() => applyColFilters(incomingWishes.value))
const allWishesFiltered = computed(() => applyColFilters(allWishes.value))

// Владелец, 2026-09-02: варианты для enum-фильтра «Субсидия» — по данным активной вкладки
// (colFilters/colSort общие на все три таба, шаблон ColumnHeaderMenu тоже один и тот же).
const wishSubsidyNameOptions = computed(() => uniqWishValues(
  activeTab.value === 'my' ? myWishesFiltered.value
    : activeTab.value === 'incoming' ? incomingWishesFiltered.value
    : allWishesFiltered.value,
  'subsidy_name',
))

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

/* Владелец, 2026-08-13: «остановка заявки/закупки» — крупный алерт в красной
   рамке на всю ширину строки/карточки, а не мелкий чип. */
.wish-stopped-banner {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  column-gap: 10px;
  row-gap: 2px;
  width: 100%;
  border: 2px solid #d32f2f;
  background: #fdecea;
  color: #b71c1c;
  border-radius: 6px;
  padding: 6px 10px;
  margin-bottom: 6px;
}
.wish-stopped-banner__title {
  font-weight: 800;
  font-size: 0.92rem;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}
.wish-stopped-banner__meta {
  font-size: 0.78rem;
  font-weight: 500;
  opacity: 0.9;
}
.wish-stopped-banner--large {
  padding: 12px 16px;
}
.wish-stopped-banner--large .wish-stopped-banner__title {
  font-size: 1.15rem;
}
.wish-stopped-banner--large .wish-stopped-banner__meta {
  font-size: 0.85rem;
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
