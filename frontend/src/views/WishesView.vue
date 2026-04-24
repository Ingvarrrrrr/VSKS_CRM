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
      <v-btn variant="tonal" color="primary" size="small" prepend-icon="mdi-refresh" :loading="loading" @click="loadWishes">
        Обновить
      </v-btn>
    </div>

    <!-- Tabs (visible to all authenticated users) -->
    <v-tabs v-model="activeTab" class="mb-4">
      <v-tab value="my">Мои заявки</v-tab>
      <v-tab value="incoming">На согласование мне</v-tab>
      <v-tab v-if="isManagerOrAdmin" value="all">Заявки сотрудников</v-tab>
    </v-tabs>

    <!-- ── MY WISHES TAB ── -->
    <div v-if="activeTab === 'my'">
      <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-2" />

      <div v-if="!loading && myWishes.length === 0" class="text-center py-12">
        <v-icon icon="mdi-hand-heart-outline" size="64" color="grey-lighten-1" class="mb-3" />
        <div class="text-h6 text-medium-emphasis">Нет заявок</div>
        <div class="text-body-2 text-medium-emphasis mt-1">Создайте первую заявку с помощью кнопки +</div>
      </div>

      <v-row v-else dense>
        <v-col v-for="wish in myWishes" :key="wish.id" cols="12" md="6" lg="4">
          <v-card variant="outlined" class="pa-3 h-100 wish-card-clickable" @click="openEditDialog(wish)">
            <div class="d-flex align-start justify-space-between mb-2">
              <div class="flex-grow-1 mr-2">
                <div class="d-flex align-center ga-1 mb-1 flex-wrap">
                  <v-chip v-if="wish.priority" size="x-small" variant="tonal" :color="priorityColor[wish.priority]">
                    {{ priorityLabel[wish.priority] }}
                  </v-chip>
                  <v-chip v-if="wish.subsidy_name" size="x-small" variant="tonal" color="blue-grey">
                    {{ wish.subsidy_name }}
                  </v-chip>
                </div>
                <div class="text-subtitle-1 font-weight-medium">{{ wish.title }}</div>
                <div class="text-caption text-medium-emphasis mt-1">
                  <span v-if="wish.items_count">Позиций: <b>{{ wish.items_count }}</b></span>
                  <span v-if="wish.items_count && wish.total_amount"> · </span>
                  <span v-if="wish.total_amount">НМЦК: <b>{{ formatPrice(wish.total_amount) }}</b></span>
                </div>
                <div v-if="wish.assigned_to_name" class="text-caption text-medium-emphasis mt-0.5">
                  <v-icon icon="mdi-account-arrow-right" size="12" class="mr-1" />{{ wish.assigned_to_name }}
                </div>
              </div>
              <div class="d-flex flex-column align-end ga-1">
                <v-chip :color="statusColor[wish.status]" size="small" variant="tonal">
                  {{ statusLabel[wish.status] }}
                </v-chip>
                <v-btn
                  v-if="wish.status === 'draft'"
                  icon="mdi-delete-outline"
                  size="x-small"
                  variant="text"
                  color="error"
                  :loading="deletingId === wish.id"
                  @click.stop="deleteWish(wish)"
                />
              </div>
            </div>

            <!-- Metadata -->
            <div class="d-flex flex-wrap ga-2 text-caption text-medium-emphasis mb-2">
              <span v-if="wish.desired_date">
                <v-icon icon="mdi-calendar" size="12" class="mr-0.5" />
                <b>{{ formatDate(wish.desired_date) }}</b>
              </span>
            </div>

            <!-- Rejection reason -->
            <div v-if="wish.status === 'rejected' && wish.rejection_reason" class="text-caption text-error mt-1 mb-2">
              <v-icon icon="mdi-close-circle" size="14" class="mr-1" />
              Причина отказа: {{ wish.rejection_reason }}
            </div>

            <!-- Link to purchase for converted wishes -->
            <div v-if="wish.status === 'converted' && wish.purchase_id" class="mb-2">
              <v-btn
                size="small"
                variant="tonal"
                color="purple"
                prepend-icon="mdi-cart-arrow-right"
                :href="`/orders/${wish.purchase_id}/edit`"
                @click.stop.prevent="$router.push(`/orders/${wish.purchase_id}/edit`)"
              >
                Перейти к закупке
              </v-btn>
            </div>

            <!-- Actions for draft wishes -->
            <div v-if="wish.status === 'draft'" class="d-flex ga-2 mt-2">
              <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-pencil" @click.stop="openEditDialog(wish)">
                Изменить
              </v-btn>
              <v-btn
                size="small"
                variant="flat"
                color="success"
                prepend-icon="mdi-send"
                :loading="submittingId === wish.id"
                @click.stop="submitWish(wish)"
              >
                Отправить
              </v-btn>
            </div>
          </v-card>
        </v-col>
      </v-row>

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
      <v-progress-linear v-if="loadingIncoming" indeterminate color="primary" class="mb-2" />

      <div v-if="!loadingIncoming && incomingWishes.length === 0" class="text-center py-12">
        <v-icon icon="mdi-hand-heart-outline" size="64" color="grey-lighten-1" class="mb-3" />
        <div class="text-h6 text-medium-emphasis">Нет заявок на согласование</div>
        <div class="text-body-2 text-medium-emphasis mt-1">Здесь появятся заявки, где вы указаны как согласующий</div>
      </div>

      <v-row v-else dense>
        <v-col v-for="wish in incomingWishes" :key="wish.id" cols="12" md="6" lg="4">
          <v-card variant="outlined" class="pa-3 h-100 wish-card-clickable" @click="openEditDialog(wish)">
            <div class="d-flex align-start justify-space-between mb-2">
              <div class="flex-grow-1 mr-2">
                <div class="d-flex align-center ga-1 mb-1 flex-wrap">
                  <v-chip v-if="wish.priority" size="x-small" variant="tonal" :color="priorityColor[wish.priority]">
                    {{ priorityLabel[wish.priority] }}
                  </v-chip>
                  <v-chip v-if="wish.subsidy_name" size="x-small" variant="tonal" color="blue-grey">
                    {{ wish.subsidy_name }}
                  </v-chip>
                </div>
                <div class="text-subtitle-1 font-weight-medium">{{ wish.title }}</div>
                <div class="text-caption text-medium-emphasis mt-0.5">
                  <v-icon icon="mdi-account" size="12" class="mr-1" />{{ wish.creator_name || 'Неизвестно' }}
                </div>
                <div class="text-caption text-medium-emphasis mt-1">
                  <span v-if="wish.items_count">Позиций: <b>{{ wish.items_count }}</b></span>
                  <span v-if="wish.items_count && wish.total_amount"> · </span>
                  <span v-if="wish.total_amount">НМЦК: <b>{{ formatPrice(wish.total_amount) }}</b></span>
                </div>
              </div>
              <v-chip :color="statusColor[wish.status]" size="small" variant="tonal">
                {{ statusLabel[wish.status] }}
              </v-chip>
            </div>

            <div v-if="wish.justification" class="text-caption text-medium-emphasis mb-2">
              <b>Обоснование:</b> {{ wish.justification }}
            </div>

            <!-- Actions for submitted wishes assigned to me -->
            <div v-if="wish.status === 'submitted'" class="d-flex ga-2 mt-2 flex-wrap">
              <v-btn size="small" variant="flat" color="primary" prepend-icon="mdi-view-column-outline"
                     @click.stop="openKanbanDialog(wish)">
                Распределить и одобрить
              </v-btn>
              <v-btn size="small" variant="tonal" color="success" prepend-icon="mdi-check"
                     :loading="approvingId === wish.id" @click.stop="approveWish(wish)">
                Быстрое одобрение
              </v-btn>
              <v-btn size="small" variant="tonal" color="error" prepend-icon="mdi-close"
                     @click.stop="openRejectDialog(wish)">
                Отклонить
              </v-btn>
              <v-btn size="small" variant="text" prepend-icon="mdi-file-document-edit-outline"
                     :loading="downloadingServiceNoteId === wish.id" @click.stop="downloadServiceNote(wish)">
                Служебная записка
              </v-btn>
            </div>
          </v-card>
        </v-col>
      </v-row>
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

      <v-progress-linear v-if="loadingAll" indeterminate color="primary" class="mb-2" />

      <div v-if="!loadingAll && allWishes.length === 0" class="text-center py-12">
        <v-icon icon="mdi-hand-heart-outline" size="64" color="grey-lighten-1" class="mb-3" />
        <div class="text-h6 text-medium-emphasis">Нет заявок от подчинённых</div>
      </div>

      <v-row v-else dense>
        <v-col v-for="wish in allWishes" :key="wish.id" cols="12" md="6" lg="4">
          <v-card variant="outlined" class="pa-3 h-100 wish-card-clickable" @click="openEditDialog(wish)">
            <div class="d-flex align-start justify-space-between mb-2">
              <div class="flex-grow-1 mr-2">
                <div class="d-flex align-center ga-1 mb-1 flex-wrap">
                  <v-chip v-if="wish.priority" size="x-small" variant="tonal" :color="priorityColor[wish.priority]">
                    {{ priorityLabel[wish.priority] }}
                  </v-chip>
                  <v-chip v-if="wish.subsidy_name" size="x-small" variant="tonal" color="blue-grey">
                    {{ wish.subsidy_name }}
                  </v-chip>
                </div>
                <div class="text-subtitle-1 font-weight-medium">{{ wish.title }}</div>
                <div class="text-caption text-medium-emphasis mt-0.5">
                  <v-icon icon="mdi-account" size="12" class="mr-1" />{{ wish.creator_name || 'Неизвестно' }}
                </div>
                <div class="text-caption text-medium-emphasis mt-1">
                  <span v-if="wish.items_count">Позиций: <b>{{ wish.items_count }}</b></span>
                  <span v-if="wish.items_count && wish.total_amount"> · </span>
                  <span v-if="wish.total_amount">НМЦК: <b>{{ formatPrice(wish.total_amount) }}</b></span>
                </div>
                <div v-if="wish.assigned_to_name" class="text-caption text-medium-emphasis mt-0.5">
                  <v-icon icon="mdi-account-arrow-right" size="12" class="mr-1" />{{ wish.assigned_to_name }}
                </div>
              </div>
              <v-chip :color="statusColor[wish.status]" size="small" variant="tonal">
                {{ statusLabel[wish.status] }}
              </v-chip>
            </div>

            <!-- Justification -->
            <div v-if="wish.justification" class="text-caption text-medium-emphasis mb-2">
              <b>Обоснование:</b> {{ wish.justification }}
            </div>

            <!-- Rejection reason -->
            <div v-if="wish.status === 'rejected' && wish.rejection_reason" class="text-caption text-error mt-1 mb-2">
              <v-icon icon="mdi-close-circle" size="14" class="mr-1" />
              Причина отказа: {{ wish.rejection_reason }}
            </div>

            <!-- Actions for submitted wishes -->
            <div v-if="wish.status === 'submitted'" class="d-flex ga-2 mt-2 flex-wrap">
              <v-btn
                size="small"
                variant="flat"
                color="primary"
                prepend-icon="mdi-view-column-outline"
                @click.stop="openKanbanDialog(wish)"
              >
                Распределить и одобрить
              </v-btn>
              <v-btn
                size="small"
                variant="tonal"
                color="success"
                prepend-icon="mdi-check"
                :loading="approvingId === wish.id"
                @click.stop="approveWish(wish)"
              >
                Быстрое одобрение
              </v-btn>
              <v-btn
                size="small"
                variant="tonal"
                color="error"
                prepend-icon="mdi-close"
                @click.stop="openRejectDialog(wish)"
              >
                Отклонить
              </v-btn>
              <v-btn
                size="small"
                variant="text"
                prepend-icon="mdi-file-document-edit-outline"
                :loading="downloadingServiceNoteId === wish.id"
                @click.stop="downloadServiceNote(wish)"
              >
                Служебная записка
              </v-btn>
            </div>
            <!-- Service note available for any wish (draft/approved/etc) -->
            <div v-else-if="wish.status !== 'rejected'" class="mt-2">
              <v-btn
                size="small"
                variant="text"
                prepend-icon="mdi-file-document-edit-outline"
                :loading="downloadingServiceNoteId === wish.id"
                @click.stop="downloadServiceNote(wish)"
              >
                Скачать служебную записку
              </v-btn>
            </div>

            <!-- Convert to purchase (admin+) -->
            <div v-if="wish.status === 'approved' && isAdmin" class="mt-2">
              <v-btn
                size="small"
                variant="flat"
                color="primary"
                prepend-icon="mdi-cart-plus"
                @click.stop="openConvertDialog(wish)"
              >
                Создать закупку
              </v-btn>
            </div>
          </v-card>
        </v-col>
      </v-row>
    </div>

    <!-- ── CREATE/EDIT DIALOG ── -->
    <v-dialog v-model="wishDialog" max-width="1600" width="95vw" scrollable>
      <v-card>
        <v-card-title class="pa-4 pb-2">
          {{ editingWishId ? 'Редактировать заявку' : 'Новая заявка' }}
        </v-card-title>
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
                      :readonly="!isWishEditable"
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
                      :readonly="!isWishEditable"
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
                      :readonly="!isWishEditable"
                    />
                  </v-col>
                  <v-col cols="12">
                    <v-autocomplete
                      v-model="wishForm.assigned_to"
                      :items="orgUsers"
                      item-title="full_name"
                      item-value="id"
                      label="Кому направить"
                      variant="outlined"
                      density="compact"
                      clearable
                      :disabled="!wishForm.subsidy_id"
                      :readonly="!isWishEditable"
                      hint="Сотрудник, которому адресована заявка"
                      persistent-hint
                    />
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
                  :default-country="'Российская Федерация'"
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
    <v-snackbar v-model="snackbar" :color="snackbarColor" timeout="3000" location="bottom right">
      {{ snackbarText }}
    </v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import PurchaseItemsEditor from '@/components/PurchaseItemsEditor.vue'
import WishDistributionKanban from '@/components/WishDistributionKanban.vue'

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
  converted: 'Конвертирована',
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

// Create/edit dialog
const wishDialog = ref(false)
const editingWishId = ref<number | null>(null)
const editingWish = ref<Wish | null>(null)
const wishFormRef = ref<any>(null)
const saving = ref(false)

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
  justification: '',
  priority: 'medium' as string,
  desired_date: '',
  items: [] as any[],
  status: 'draft' as string,
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
    myWishes.value = await apiFetch<Wish[]>('/wishes?mine_only=true')
  } catch {
    showSnack('Ошибка загрузки заявок', 'error')
  } finally {
    loading.value = false
  }
}

async function loadAllWishes() {
  loadingAll.value = true
  try {
    const statusParam = allFilter.value && allFilter.value !== 'all' ? `&status=${allFilter.value}` : ''
    allWishes.value = await apiFetch<Wish[]>(`/wishes/?subordinates_only=true${statusParam}`)
  } catch {
    showSnack('Ошибка загрузки заявок', 'error')
  } finally {
    loadingAll.value = false
  }
}

async function loadIncoming() {
  loadingIncoming.value = true
  try {
    const data = await apiFetch<Wish[]>('/wishes/?assigned_to_me=true')
    incomingWishes.value = data || []
  } catch {
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
  wishForm.value = {
    subsidy_id: null,
    feo_category_id: null,
    assigned_to: null,
    justification: '',
    priority: 'medium',
    desired_date: '',
    items: [],
    status: 'draft',
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
  wishForm.value.justification = wish.justification || ''
  wishForm.value.priority = wish.priority || 'medium'
  wishForm.value.desired_date = wish.desired_date || ''
  wishForm.value.status = wish.status || 'draft'

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
    country_origin: i.country_origin || 'Российская Федерация',
  })) as any
  wishDialog.value = true
}

async function saveWish(andSubmit = false) {
  const { valid } = await wishFormRef.value?.validate() ?? { valid: true }
  if (!valid) return

  saving.value = true
  try {
    const feo = selectedFeo3.value || selectedFeo2.value || selectedFeo1.value
    const title = wishForm.value.items.map(i => i.item_name).filter(Boolean).join(', ') || 'Новая заявка'
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
    await loadWishes()
  } catch {
    showSnack('Ошибка при сохранении', 'error')
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
  } catch {
    showSnack('Ошибка при отправке', 'error')
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
  } catch {
    showSnack('Ошибка при удалении', 'error')
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
  } catch {
    showSnack('Ошибка при одобрении', 'error')
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
        _photo_url: prod?.photo_url ?? it._photo_url ?? null,
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
  } catch {
    showSnack('Ошибка при отклонении', 'error')
  } finally {
    rejectingWish.value = false
  }
}

function openConvertDialog(wish: Wish) {
  convertingWish.value = wish
  convertForm.value = {
    approved_quantity: null,
    approved_price: wish.total_amount ?? null,
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
  } catch {
    showSnack('Ошибка при создании закупки', 'error')
  } finally {
    convertingWishLoading.value = false
  }
}

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
  ])
  await loadWishes()
  await loadIncoming()
  if (isManagerOrAdmin.value) {
    await loadAllWishes()
  }
})
</script>

<style scoped>
.wish-card-clickable {
  cursor: pointer;
  transition: box-shadow 0.15s ease, transform 0.15s ease;
}
.wish-card-clickable:hover {
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  transform: translateY(-1px);
}
</style>
