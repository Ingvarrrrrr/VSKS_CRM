<template>
  <v-container fluid class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">Запросы КП</h1>
        <span class="text-body-2 text-medium-emphasis">{{ requests.length }} записей</span>
      </div>
      <div class="d-flex gap-2 align-center">
        <v-btn-toggle
          v-if="!mobile"
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
        <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" @click="showColumnPicker = true">Колонки</v-btn>
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreateDialog">
          Создать запрос КП
        </v-btn>
      </div>
    </div>

    <!-- Filters -->
    <v-card class="mb-4" variant="outlined">
      <v-card-text class="py-3">
        <div class="d-flex align-center gap-4 flex-wrap">
          <v-select
            v-model="filterStatus"
            :items="statusItems"
            item-title="label"
            item-value="value"
            label="Статус"
            variant="outlined" density="compact" clearable hide-details
            style="min-width:160px"
          />
          <v-text-field
            v-model="search"
            prepend-inner-icon="mdi-magnify"
            label="Поиск по теме"
            variant="outlined" density="compact" clearable hide-details
            style="min-width:200px"
          />
        </div>
      </v-card-text>
    </v-card>

    <!-- Table / Cards -->
    <v-data-table
      v-if="effectiveView === 'table'"
      v-resizable-columns="'commercial-requests'"
      :headers="visibleHeaders"
      :items="filteredRequests"
      :loading="loading"
      item-value="id"
      :items-per-page="20"
      density="comfortable"
      class="cr-clickable"
      @click:row="(_, { item }) => openDetailDialog(item)"
    >
      <template v-slot:item.status="{ item }">
        <v-chip :color="statusColor(item.status)" size="small" variant="tonal">
          {{ statusLabel(item.status) }}
        </v-chip>
      </template>
      <template v-slot:item.recipients="{ item }">
        <div class="d-flex gap-1 flex-wrap">
          <v-chip
            v-for="r in item.recipients" :key="r.id"
            :color="recipientStatusColor(r.status)"
            size="x-small" variant="tonal"
            :title="r.email || ''"
          >
            {{ r.contractor_name || r.email || '—' }}
          </v-chip>
        </div>
      </template>
      <template v-slot:item.delivery_date="{ item }">
        {{ item.delivery_date ? formatDate(item.delivery_date) : '—' }}
      </template>
      <template v-slot:item.created_at="{ item }">
        {{ item.created_at ? item.created_at.slice(0, 10) : '—' }}
      </template>
      <template v-slot:item.actions="{ item }">
        <div class="d-flex gap-1" @click.stop>
          <v-btn
            v-if="item.status === 'prepared'"
            icon="mdi-send" size="x-small" variant="text" color="primary"
            @click.stop="updateStatus(item.id, 'sent')" title="Отметить отправленным"
          />
          <v-btn
            v-if="item.status === 'sent'"
            icon="mdi-check-all" size="x-small" variant="text" color="success"
            @click.stop="updateStatus(item.id, 'received')" title="Получены ответы"
          />
          <v-btn
            v-if="['prepared','sent','received'].includes(item.status)"
            icon="mdi-archive" size="x-small" variant="text" color="grey"
            @click.stop="updateStatus(item.id, 'closed')" title="Закрыть"
          />
        </div>
      </template>
    </v-data-table>

    <!-- Cards view -->
    <div v-else>
      <v-row v-if="pagedCards.length" dense>
        <v-col
          v-for="item in pagedCards"
          :key="item.id"
          cols="12" sm="6" lg="4"
        >
          <v-card
            hover
            class="h-100"
            @click="openDetailDialog(item)"
          >
            <v-card-title class="pb-1 d-flex align-center gap-2">
              <span class="text-body-1 font-weight-bold">#{{ item.id }}</span>
              <v-chip :color="statusColor(item.status)" size="small" variant="tonal" class="ml-auto">
                {{ statusLabel(item.status) }}
              </v-chip>
            </v-card-title>
            <v-card-text class="pt-1 pb-2">
              <div v-if="item.subject" class="text-body-2 mb-2">{{ item.subject }}</div>
              <div class="text-caption text-medium-emphasis mb-1">
                <v-icon size="x-small" class="mr-1">mdi-calendar-clock</v-icon>
                Срок КП: {{ item.delivery_date ? formatDate(item.delivery_date) : '—' }}
              </div>
              <div class="text-caption text-medium-emphasis mb-2">
                <v-icon size="x-small" class="mr-1">mdi-calendar-plus</v-icon>
                Создан: {{ item.created_at ? item.created_at.slice(0, 10) : '—' }}
              </div>
              <div v-if="item.recipients.length" class="d-flex gap-1 flex-wrap">
                <v-chip
                  v-for="r in item.recipients" :key="r.id"
                  :color="recipientStatusColor(r.status)"
                  size="x-small" variant="tonal"
                  :title="r.email || ''"
                >
                  {{ r.contractor_name || r.email || '—' }}
                </v-chip>
              </div>
            </v-card-text>
            <v-card-actions @click.stop class="pt-0">
              <v-btn
                v-if="item.status === 'prepared'"
                icon="mdi-send" size="x-small" variant="text" color="primary"
                @click.stop="updateStatus(item.id, 'sent')" title="Отметить отправленным"
              />
              <v-btn
                v-if="item.status === 'sent'"
                icon="mdi-check-all" size="x-small" variant="text" color="success"
                @click.stop="updateStatus(item.id, 'received')" title="Получены ответы"
              />
              <v-btn
                v-if="['prepared','sent','received'].includes(item.status)"
                icon="mdi-archive" size="x-small" variant="text" color="grey"
                @click.stop="updateStatus(item.id, 'closed')" title="Закрыть"
              />
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>
      <v-empty-state
        v-else
        icon="mdi-email-search-outline"
        title="Нет запросов КП"
        text="Попробуйте изменить фильтры или создайте новый запрос"
      />
      <v-pagination
        v-if="cardsTotalPages > 1"
        v-model="cardsPage"
        :length="cardsTotalPages"
        density="compact"
        :total-visible="7"
        class="d-flex justify-center mt-4"
      />
    </div>

    <!-- Create Dialog -->
    <v-dialog v-model="createDialog.show" max-width="680" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4 d-flex align-center">
          <v-icon icon="mdi-email-plus-outline" color="primary" class="mr-2" />
          Создать запрос КП
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="createDialog.show = false" />
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-autocomplete
            v-model="createDialog.purchase_id"
            :items="purchases"
            item-title="display_name"
            item-value="id"
            label="Закупка *"
            variant="outlined" density="compact" class="mb-3"
            :loading="createDialog.loadingPurchases"
          />
          <v-text-field
            v-model="createDialog.subject"
            label="Тема письма"
            variant="outlined" density="compact" class="mb-3"
            placeholder="Запрос коммерческого предложения на ..."
          />
          <v-textarea
            v-model="createDialog.intro_text"
            label="Текст письма"
            variant="outlined" density="compact" rows="4" class="mb-3"
            placeholder="Уважаемые партнёры, просим направить коммерческое предложение..."
          />
          <v-text-field
            v-model="createDialog.delivery_date"
            label="Срок предоставления КП"
            type="date"
            variant="outlined" density="compact" class="mb-3"
          />
          <!-- Recipients section -->
          <div class="mb-2 text-body-2 font-weight-medium">Получатели</div>

          <!-- Contractor search -->
          <div class="d-flex align-center gap-2 mb-2">
            <v-autocomplete
              v-model="createDialog.recipient_ids"
              :items="contractorOptions"
              item-title="name"
              item-value="id"
              label="Найти контрагента"
              variant="outlined" density="compact"
              multiple hide-selected hide-details
              :loading="contractorsStore.searching || createDialog.loadingContractors"
              class="flex-grow-1"
              no-data-text="Введите название для поиска"
              no-filter
              @update:search="onContractorSearch"
            />
            <v-btn
              icon="mdi-account-plus-outline"
              size="small" variant="tonal" color="primary"
              title="Создать нового контрагента"
              @click="openQuickContractor"
            />
          </div>

          <!-- Selected contractors list -->
          <div v-if="createDialog.recipient_ids.length" class="mb-3">
            <div
              v-for="cid in createDialog.recipient_ids" :key="cid"
              class="d-flex align-center gap-2 pa-2 rounded mb-1"
              style="border: 1px solid rgba(0,0,0,0.12);"
            >
              <v-icon icon="mdi-domain" size="small" color="primary" />
              <span class="text-body-2 font-weight-medium" style="min-width:140px">{{ getContractor(cid)?.name }}</span>

              <!-- Email display/edit -->
              <template v-if="editEmailId !== cid">
                <span v-if="getContractor(cid)?.email" class="text-body-2 text-medium-emphasis flex-grow-1">
                  {{ getContractor(cid)?.email }}
                </span>
                <v-chip v-else color="warning" size="x-small" variant="tonal" class="flex-grow-1">
                  <v-icon start icon="mdi-alert-circle-outline" />
                  нет email
                </v-chip>
                <v-btn
                  :icon="getContractor(cid)?.email ? 'mdi-pencil-outline' : 'mdi-email-plus-outline'"
                  size="x-small" variant="text"
                  :color="getContractor(cid)?.email ? 'grey' : 'warning'"
                  title="Добавить/изменить email контрагента"
                  @click="startEditEmail(cid)"
                />
              </template>
              <template v-else>
                <v-text-field
                  v-model="editEmailValue"
                  label="Email"
                  type="email"
                  variant="outlined" density="compact" hide-details
                  class="flex-grow-1"
                  autofocus
                  @keyup.enter="saveContractorEmail(cid)"
                  @keyup.esc="editEmailId = null"
                />
                <v-btn icon="mdi-check" size="x-small" variant="tonal" color="success"
                  :loading="savingEmail" title="Сохранить"
                  @click="saveContractorEmail(cid)" />
                <v-btn icon="mdi-close" size="x-small" variant="text"
                  title="Отмена" @click="editEmailId = null" />
              </template>

              <v-btn
                icon="mdi-close" size="x-small" variant="text" color="error"
                title="Убрать из списка"
                @click="createDialog.recipient_ids = createDialog.recipient_ids.filter(id => id !== cid)"
              />
            </div>
          </div>

          <!-- Free emails -->
          <div v-if="createDialog.free_recipients.length" class="mb-2">
            <div v-for="(fr, i) in createDialog.free_recipients" :key="i" class="d-flex align-center gap-2 mb-2">
              <v-text-field
                v-model="fr.name"
                label="Название / имя"
                variant="outlined" density="compact" hide-details
                style="max-width:180px"
              />
              <v-text-field
                v-model="fr.email"
                label="Email *"
                type="email"
                variant="outlined" density="compact" hide-details
                class="flex-grow-1"
              />
              <v-btn icon="mdi-close" size="x-small" variant="text" color="error" @click="createDialog.free_recipients.splice(i, 1)" />
            </div>
          </div>
          <v-btn
            prepend-icon="mdi-email-plus-outline" size="small" variant="text" color="primary"
            @click="createDialog.free_recipients.push({ name: '', email: '' })"
          >
            Добавить email вручную
          </v-btn>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="createDialog.show = false">Отмена</v-btn>
          <v-btn
            color="primary" variant="flat"
            :loading="createDialog.saving"
            :disabled="!createDialog.purchase_id"
            @click="saveRequest">
            Создать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Quick add contractor dialog -->
    <v-dialog v-model="quickContractor.show" max-width="420" :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4 d-flex align-center">
          <v-icon icon="mdi-account-plus-outline" color="primary" class="mr-2" />
          Новый контрагент
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="quickContractor.show = false" />
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-text-field v-model="quickContractor.name" label="Название *" variant="outlined" density="compact" class="mb-3" />
          <v-text-field v-model="quickContractor.email" label="Email" type="email" variant="outlined" density="compact" class="mb-3" />
          <v-text-field v-model="quickContractor.inn" label="ИНН" variant="outlined" density="compact" class="mb-3" />
          <v-text-field v-model="quickContractor.phone" label="Телефон" variant="outlined" density="compact" />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="quickContractor.show = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="quickContractor.saving" :disabled="!quickContractor.name" @click="saveQuickContractor">
            Создать и добавить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Detail / Edit Dialog -->
    <v-dialog v-model="detailDialog.show" max-width="720" scrollable :fullscreen="mobile">
      <v-card v-if="detailDialog.item">
        <v-card-title class="pa-4 d-flex align-center">
          <v-icon icon="mdi-email-outline" color="primary" class="mr-2" />
          Запрос КП #{{ detailDialog.item.id }}
          <v-chip :color="statusColor(detailDialog.item.status)" size="small" variant="tonal" class="ml-3">
            {{ statusLabel(detailDialog.item.status) }}
          </v-chip>
          <v-spacer />
          <v-btn v-if="!detailDialog.editing" icon="mdi-pencil" variant="text" size="small" title="Редактировать" @click="startEdit" />
          <v-btn icon="mdi-close" variant="text" size="small" @click="detailDialog.show = false" />
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <!-- View mode -->
          <template v-if="!detailDialog.editing">
            <div class="mb-2"><span class="text-caption text-medium-emphasis">Тема:</span> {{ detailDialog.item.subject || '—' }}</div>
            <div class="mb-2"><span class="text-caption text-medium-emphasis">Срок КП:</span> {{ detailDialog.item.delivery_date ? formatDate(detailDialog.item.delivery_date) : '—' }}</div>
            <div v-if="detailDialog.item.intro_text" class="mb-3 text-body-2 bg-grey-lighten-4 pa-3 rounded" style="white-space:pre-wrap">{{ detailDialog.item.intro_text }}</div>
          </template>
          <!-- Edit mode -->
          <template v-else>
            <v-text-field v-model="detailDialog.editSubject" label="Тема письма" variant="outlined" density="compact" class="mb-3" />
            <v-text-field v-model="detailDialog.editDeliveryDate" label="Срок предоставления КП" type="date" variant="outlined" density="compact" class="mb-3" />
            <v-textarea v-model="detailDialog.editIntroText" label="Текст письма" variant="outlined" density="compact" rows="5" class="mb-3" />
          </template>

          <div class="text-body-2 font-weight-medium mb-2 mt-1">Получатели:</div>
          <v-table density="compact">
            <thead>
              <tr><th>Контрагент</th><th>Email</th><th>Статус</th><th style="width:140px">Изменить статус</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in detailDialog.item.recipients" :key="r.id">
                <td>{{ r.contractor_name || '—' }}</td>
                <td>{{ r.email || '—' }}</td>
                <td>
                  <v-chip :color="recipientStatusColor(r.status)" size="x-small" variant="tonal">
                    {{ recipientStatusLabel(r.status) }}
                  </v-chip>
                </td>
                <td>
                  <v-select
                    :model-value="r.status"
                    :items="recipientStatusItems"
                    item-title="label"
                    item-value="value"
                    variant="plain"
                    density="compact"
                    hide-details
                    style="min-width:120px"
                    @update:model-value="updateRecipientStatus(r.id, $event)"
                  />
                </td>
              </tr>
            </tbody>
          </v-table>

          <!-- Полученные предложения (владелец, сессия 2026-08-29: «цену из КП можно
               завести через таблицу полученных предложений в карточке запроса КП») —
               позиции закупки × получатели, ввод цены, принятие лучшей → цена уходит
               в каталог товара. -->
          <template v-if="detailDialog.item.recipients.length">
            <v-divider class="my-3" />
            <div class="d-flex align-center justify-space-between mb-2">
              <span class="text-body-2 font-weight-medium">Полученные предложения</span>
              <v-btn size="small" variant="text" density="compact"
                :icon="offersExpanded ? 'mdi-chevron-up' : 'mdi-chevron-down'"
                @click="offersExpanded = !offersExpanded" />
            </div>
            <v-expand-transition>
              <div v-show="offersExpanded">
                <v-progress-linear v-if="offersState.loading" indeterminate class="mb-2" />
                <div v-else-if="!offersGrid.length" class="text-caption text-medium-emphasis mb-2">
                  Нет позиций закупки для сравнения цен.
                </div>
                <div v-else class="overflow-x-auto">
                  <v-table density="compact">
                    <thead>
                      <tr>
                        <th style="min-width:200px">Позиция</th>
                        <th v-for="r in detailDialog.item.recipients" :key="r.id" style="min-width:170px">
                          {{ r.contractor_name || r.email || '—' }}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="row in offersGrid" :key="row.product_id ?? row.item_name">
                        <td>
                          {{ row.item_name }}
                          <span v-if="row.unit" class="text-caption text-medium-emphasis"> · {{ row.unit }}</span>
                        </td>
                        <td v-for="r in detailDialog.item.recipients" :key="r.id">
                          <div class="d-flex align-center ga-1">
                            <v-text-field
                              v-model.number="row.cells[r.id].unit_price"
                              type="number" density="compact" variant="outlined" hide-details
                              placeholder="Цена, ₽"
                              style="max-width:120px"
                              :class="{ 'font-weight-bold text-success': bestRecipientId(row) === r.id && row.cells[r.id].unit_price != null }"
                            />
                            <v-tooltip v-if="row.cells[r.id].is_accepted" text="Принято — цена ушла в каталог" location="top">
                              <template #activator="{ props: tip }">
                                <v-icon v-bind="tip" icon="mdi-check-decagram" color="success" size="18" />
                              </template>
                            </v-tooltip>
                            <v-tooltip v-else :text="row.cells[r.id].offer_id ? 'Принять эту цену' : 'Сначала сохраните предложения'" location="top">
                              <template #activator="{ props: tip }">
                                <v-btn v-bind="tip" icon="mdi-check-bold" size="x-small" variant="tonal" color="primary"
                                  :disabled="!row.cells[r.id].offer_id || row.cells[r.id].unit_price == null"
                                  :loading="acceptingOfferId === row.cells[r.id].offer_id"
                                  @click="acceptOffer(row, r.id)" />
                              </template>
                            </v-tooltip>
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </v-table>
                  <div class="d-flex justify-end mt-2">
                    <v-btn size="small" color="primary" variant="flat" prepend-icon="mdi-content-save"
                      :loading="offersState.saving" @click="saveOffers">
                      Сохранить предложения
                    </v-btn>
                  </div>
                </div>
              </div>
            </v-expand-transition>
          </template>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <template v-if="detailDialog.editing">
            <v-btn variant="text" @click="detailDialog.editing = false">Отмена</v-btn>
            <v-spacer />
            <v-btn color="primary" variant="flat" :loading="detailDialog.saving" @click="saveEdit">Сохранить</v-btn>
          </template>
          <template v-else>
            <v-spacer />
            <v-btn variant="text" @click="detailDialog.show = false">Закрыть</v-btn>
          </template>
        </v-card-actions>
      </v-card>
    </v-dialog>

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
import { ref, computed, reactive, onMounted } from 'vue'
import { apiFetch } from '@/api'
import { useContractorsStore } from '@/stores/contractors'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import { useCardView } from '@/composables/useCardView'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'
import { useToast, type ToastType } from '@/composables/useToast'
import { numOrNullZeroEmpty } from '@/utils/numberFormat'

interface Recipient { id: number; contractor_id?: number; contractor_name?: string; email?: string; status: string }
interface CommercialRequest {
  id: number; purchase_id: number; subject?: string; intro_text?: string
  delivery_date?: string; status: string; created_at?: string; recipients: Recipient[]
}
interface Purchase { id: number; item_name?: string; purchase_number?: number; display_name?: string }
interface Contractor { id: number; name: string; email?: string }

// Полученные предложения — таблица позиция × получатель (владелец, сессия 2026-08-29).
interface Offer {
  id: number; recipient_id: number; product_id: number | null; item_name: string
  unit: string; unit_price: number | null; is_accepted?: boolean; note?: string | null
}
interface OfferCell { offer_id: number | null; unit_price: number | null; note: string; is_accepted: boolean }
interface OfferRow { product_id: number | null; item_name: string; unit: string; cells: Record<number, OfferCell> }

const REQUEST_STATUSES: Record<string, { label: string; color: string }> = {
  prepared: { label: 'Подготовлен',  color: 'blue-grey' },
  sent:     { label: 'Отправлен',   color: 'blue' },
  received: { label: 'Ответы получены', color: 'teal' },
  closed:   { label: 'Закрыт',      color: 'grey' },
}
const RECIPIENT_STATUSES: Record<string, { label: string; color: string }> = {
  prepared: { label: 'Ожидает',     color: 'orange' },
  sent:     { label: 'Отправлено',  color: 'blue' },
  delivered:{ label: 'Доставлено',  color: 'teal' },
  read:     { label: 'Прочитано',   color: 'purple' },
  replied:  { label: 'Ответил',     color: 'green' },
  declined: { label: 'Отказал',     color: 'red' },
}

const statusLabel  = (s: string) => REQUEST_STATUSES[s]?.label || s
const statusColor  = (s: string) => REQUEST_STATUSES[s]?.color || 'grey'
const recipientStatusLabel = (s: string) => RECIPIENT_STATUSES[s]?.label || s
const recipientStatusColor = (s: string) => RECIPIENT_STATUSES[s]?.color || 'grey'

const statusItems = Object.entries(REQUEST_STATUSES).map(([v, d]) => ({ value: v, label: d.label }))
const recipientStatusItems = Object.entries(RECIPIENT_STATUSES).map(([v, d]) => ({ value: v, label: d.label }))

const allColumns: ColumnDef[] = [
  { title: '№', key: 'id', width: 60 },
  { title: 'Тема', key: 'subject' },
  { title: 'Получатели', key: 'recipients', sortable: false },
  { title: 'Срок КП', key: 'delivery_date', width: 110 },
  { title: 'Создан', key: 'created_at', width: 110 },
  { title: 'Статус', key: 'status', width: 140 },
  { title: 'Действия', key: 'actions', width: 130, sortable: false },
]

const { state: colState, visibleHeaders, toggleVisible, setPosition, setWidth, reset: resetColumns } = useColumnConfig('commercial_requests', allColumns)
const showColumnPicker = ref(false)

const requests = ref<CommercialRequest[]>([])
const purchases = ref<Purchase[]>([])
const contractors = ref<Contractor[]>([])
const contractorsStore = useContractorsStore()
const loading = ref(false)
const filterStatus = ref('')
const search = ref('')

const toast = useToast()
const showSnack = (text: string, color: ToastType = 'success') => { toast.addToast(text, color) }

const createDialog = reactive({
  show: false,
  purchase_id: null as number | null,
  subject: '',
  intro_text: '',
  delivery_date: '',
  recipient_ids: [] as number[],
  free_recipients: [] as { name: string; email: string }[],
  saving: false,
  loadingPurchases: false,
  loadingContractors: false,
})

const quickContractor = reactive({
  show: false,
  name: '',
  email: '',
  inn: '',
  phone: '',
  saving: false,
})

const detailDialog = reactive({
  show: false,
  item: null as CommercialRequest | null,
  editing: false,
  saving: false,
  editSubject: '',
  editIntroText: '',
  editDeliveryDate: '',
})

// ── Полученные предложения (владелец, сессия 2026-08-29) ────────────────────
const offersState = reactive({ loading: false, saving: false })
const offersGrid = ref<OfferRow[]>([])
const offersExpanded = ref(false)
const acceptingOfferId = ref<number | null>(null)

/** Строка с наилучшей (минимальной) ценой среди введённых предложений — подсвечивается в таблице. */
function bestRecipientId(row: OfferRow): number | null {
  let best: number | null = null
  let bestPrice = Infinity
  for (const [rid, cell] of Object.entries(row.cells)) {
    if (cell.unit_price != null && cell.unit_price < bestPrice) {
      bestPrice = cell.unit_price
      best = Number(rid)
    }
  }
  return best
}

async function loadOffersGrid(item: CommercialRequest) {
  if (!item.recipients?.length) { offersGrid.value = []; return }
  offersState.loading = true
  try {
    const [purchase, offers] = await Promise.all([
      apiFetch<any>(`/purchases/${item.purchase_id}`),
      apiFetch<Offer[]>(`/commercial-requests/${item.id}/offers`),
    ])
    const purchaseItems: any[] = purchase?.items || []
    offersGrid.value = purchaseItems.map((pi: any) => {
      const cells: Record<number, OfferCell> = {}
      for (const r of item.recipients) {
        const match = offers.find(o => o.recipient_id === r.id && (
          (pi.product_id != null && o.product_id === pi.product_id) ||
          (pi.product_id == null && o.item_name === pi.item_name)
        ))
        cells[r.id] = match
          ? { offer_id: match.id, unit_price: match.unit_price ?? null, note: match.note || '', is_accepted: !!match.is_accepted }
          : { offer_id: null, unit_price: null, note: '', is_accepted: false }
      }
      return { product_id: pi.product_id ?? null, item_name: pi.item_name || '', unit: pi.unit || '', cells }
    })
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || e?.message || `Ошибка загрузки предложений (HTTP ${e?.status ?? '?'})`, 'error')
  } finally {
    offersState.loading = false
  }
}

async function saveOffers() {
  if (!detailDialog.item) return
  offersState.saving = true
  try {
    const body: any[] = []
    for (const row of offersGrid.value) {
      for (const r of detailDialog.item.recipients) {
        const cell = row.cells[r.id]
        // cell.unit_price приходит из v-model.number — при очистке поля Vue кладёт
        // '' (не null), а `== null` её не ловит ('' == null → false в JS). Пустая
        // строка уходила бы на сервер и валила 422 (unit_price: Optional[Decimal]).
        // numOrNullZeroEmpty (2026-09-04, владелец: «0 тоже значит, что ничего нет» —
        // цена за единицу входит в группу «ноль бессмыслен»): '' и 0 обе → null.
        const cellPrice = numOrNullZeroEmpty(cell.unit_price)
        if (cellPrice == null) continue
        body.push({
          recipient_id: r.id,
          product_id: row.product_id,
          item_name: row.item_name,
          unit: row.unit,
          unit_price: cellPrice,
          note: cell.note || null,
        })
      }
    }
    await apiFetch(`/commercial-requests/${detailDialog.item.id}/offers`, { method: 'PUT', body })
    showSnack('Предложения сохранены')
    await loadOffersGrid(detailDialog.item)
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || e?.message || `Ошибка сохранения предложений (HTTP ${e?.status ?? '?'})`, 'error')
  } finally {
    offersState.saving = false
  }
}

async function acceptOffer(row: OfferRow, recipientId: number) {
  const cell = row.cells[recipientId]
  if (!detailDialog.item || !cell.offer_id) return
  acceptingOfferId.value = cell.offer_id
  try {
    await apiFetch(`/commercial-requests/${detailDialog.item.id}/offers/${cell.offer_id}/accept`, { method: 'POST' })
    showSnack(`Цена товара «${row.item_name}» актуализирована`)
    await loadOffersGrid(detailDialog.item)
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || e?.message || `Ошибка принятия предложения (HTTP ${e?.status ?? '?'})`, 'error')
  } finally {
    acceptingOfferId.value = null
  }
}

const editEmailId = ref<number | null>(null)
const editEmailValue = ref('')
const savingEmail = ref(false)

function getContractor(id: number) {
  // Phase 26-ZZ: ищем сперва в локальном массиве (был при создании quick),
  // затем в Pinia cache (наполняется server-search'ем).
  return contractors.value.find(c => c.id === id) || contractorsStore.getById(id) || undefined
}

// Phase 26-ZZ: опции дропдауна = последний search-результат + уже выбранные
const contractorOptions = computed(() => {
  const seen = new Set<number>()
  const out: Contractor[] = []
  for (const c of contractorsStore.searchResults) {
    if (!seen.has(c.id)) { seen.add(c.id); out.push(c) }
  }
  // Добавим selected (важно для multi-select: chip нужен в items, иначе пропадает)
  for (const id of createDialog.recipient_ids) {
    if (seen.has(id)) continue
    const c = getContractor(id)
    if (c) { seen.add(id); out.push(c) }
  }
  // Локально созданные quick-контрагенты (могут быть вне последнего search)
  for (const c of contractors.value) {
    if (!seen.has(c.id)) { seen.add(c.id); out.push(c) }
  }
  return out
})

let _contractorSearchTimer: any = null
function onContractorSearch(q: string) {
  if (_contractorSearchTimer) clearTimeout(_contractorSearchTimer)
  _contractorSearchTimer = setTimeout(() => contractorsStore.search(q, 50), 300)
}

function startEditEmail(id: number) {
  editEmailId.value = id
  editEmailValue.value = getContractor(id)?.email || ''
}

async function saveContractorEmail(id: number) {
  if (!editEmailValue.value.trim()) return
  savingEmail.value = true
  try {
    await apiFetch(`/contractors/${id}/email`, {
      method: 'PATCH',
      body: { email: editEmailValue.value.trim() },
    })
    const c = contractors.value.find(c => c.id === id)
    if (c) c.email = editEmailValue.value.trim()
    editEmailId.value = null
    showSnack('Email контрагента сохранён')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка сохранения email', 'error')
  } finally {
    savingEmail.value = false
  }
}

const formatDate = (d: string) => {
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}

const filteredRequests = computed(() => {
  let r = requests.value
  if (filterStatus.value) r = r.filter(x => x.status === filterStatus.value)
  if (search.value) {
    const q = search.value.toLowerCase()
    r = r.filter(x => (x.subject || '').toLowerCase().includes(q))
  }
  return r
})

const {
  mobile,
  viewMode,
  effectiveView,
  page: cardsPage,
  totalPages: cardsTotalPages,
  paged: pagedCards,
} = useCardView({
  storageKey: 'commercial_requests_view_mode',
  source: () => filteredRequests.value,
  pageSize: 24,
})

async function loadRequests() {
  loading.value = true
  try {
    requests.value = await apiFetch<CommercialRequest[]>('/commercial-requests/')
  } finally {
    loading.value = false
  }
}

async function openCreateDialog() {
  createDialog.purchase_id = null
  createDialog.subject = ''
  createDialog.intro_text = ''
  createDialog.delivery_date = ''
  createDialog.recipient_ids = []
  createDialog.free_recipients = []
  createDialog.show = true

  if (purchases.value.length === 0) {
    createDialog.loadingPurchases = true
    try {
      const data = await apiFetch<any[]>('/purchases/?limit=500')
      purchases.value = data.map(p => ({
        ...p,
        display_name: `#${p.purchase_number || p.id} ${p.item_name || p.subject || ''}`.trim(),
      }))
    } finally {
      createDialog.loadingPurchases = false
    }
  }
  // 27.4-24: пре-bulk загружаем топ-50 контрагентов (Phase 26-ZZ убрал bulk-load,
  // но в диалоге КП пользователь хочет видеть список сразу, а не угадывать буквы).
  // server-side search с пустым q возвращает первые 50 по дефолтной сортировке.
  createDialog.loadingContractors = true
  contractorsStore.lastError = null
  try {
    const arr = await contractorsStore.search('', 50)
    if (contractorsStore.lastError) {
      showSnack('Ошибка загрузки контрагентов: ' + contractorsStore.lastError, 'error')
    } else if (!arr || arr.length === 0) {
      showSnack('Контрагенты не найдены. Создайте нового или введите свободный email.', 'warning')
    }
  } finally {
    createDialog.loadingContractors = false
  }
}

function openQuickContractor() {
  quickContractor.name = ''
  quickContractor.email = ''
  quickContractor.inn = ''
  quickContractor.phone = ''
  quickContractor.show = true
}

async function saveQuickContractor() {
  if (!quickContractor.name) return
  quickContractor.saving = true
  try {
    const created = await apiFetch<Contractor>('/contractors/', {
      method: 'POST',
      body: {
        name: quickContractor.name,
        email: quickContractor.email || null,
        inn: quickContractor.inn || null,
        phone: quickContractor.phone || null,
      },
    })
    contractors.value.push(created)
    contractorsStore.putToCache(created)  // Phase 26-ZZ: и в Pinia cache для глобального resolve
    createDialog.recipient_ids = [...createDialog.recipient_ids, created.id]
    quickContractor.show = false
    showSnack(`Контрагент «${created.name}» добавлен`)
  } catch (e: any) {
    showSnack(e.message || 'Ошибка создания контрагента', 'error')
  } finally {
    quickContractor.saving = false
  }
}

async function saveRequest() {
  createDialog.saving = true
  try {
    const validFree = createDialog.free_recipients.filter(r => r.email.trim())
    const body: any = {
      purchase_id: createDialog.purchase_id,
      subject: createDialog.subject || null,
      intro_text: createDialog.intro_text || null,
      delivery_date: createDialog.delivery_date || null,
      recipient_ids: createDialog.recipient_ids,
      free_recipients: validFree.length ? validFree.map(r => ({ name: r.name || null, email: r.email })) : null,
    }
    const created = await apiFetch<CommercialRequest>('/commercial-requests/', { method: 'POST', body })
    requests.value = [created, ...requests.value]
    createDialog.show = false
    showSnack('Запрос КП создан')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка создания', 'error')
  } finally {
    createDialog.saving = false
  }
}

function openDetailDialog(item: CommercialRequest) {
  detailDialog.item = item
  detailDialog.editing = false
  detailDialog.show = true
  // Владелец, сессия 2026-08-29: «при статусе "Получены ответы" — раскрытым».
  offersExpanded.value = item.status === 'received'
  offersGrid.value = []
  if (item.recipients?.length) loadOffersGrid(item)
}

function startEdit() {
  if (!detailDialog.item) return
  detailDialog.editSubject = detailDialog.item.subject || ''
  detailDialog.editIntroText = detailDialog.item.intro_text || ''
  detailDialog.editDeliveryDate = detailDialog.item.delivery_date || ''
  detailDialog.editing = true
}

async function saveEdit() {
  if (!detailDialog.item) return
  detailDialog.saving = true
  try {
    const updated = await apiFetch<CommercialRequest>(`/commercial-requests/${detailDialog.item.id}`, {
      method: 'PUT',
      body: {
        subject: detailDialog.editSubject || null,
        intro_text: detailDialog.editIntroText || null,
        delivery_date: detailDialog.editDeliveryDate || null,
      },
    })
    const idx = requests.value.findIndex(r => r.id === updated.id)
    if (idx >= 0) requests.value[idx] = updated
    detailDialog.item = updated
    detailDialog.editing = false
    showSnack('Запрос КП обновлён')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка сохранения', 'error')
  } finally {
    detailDialog.saving = false
  }
}

async function updateStatus(id: number, status: string) {
  try {
    const updated = await apiFetch<CommercialRequest>(`/commercial-requests/${id}/status`, {
      method: 'PATCH',
      body: { status },
    })
    const idx = requests.value.findIndex(r => r.id === id)
    if (idx >= 0) requests.value[idx] = updated
    if (detailDialog.item?.id === id) detailDialog.item = updated
    showSnack('Статус обновлён')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка обновления', 'error')
  }
}

async function updateRecipientStatus(recipientId: number, status: string) {
  try {
    const updated = await apiFetch<CommercialRequest>(`/commercial-requests/recipients/${recipientId}/status`, {
      method: 'PATCH',
      body: { status },
    })
    const idx = requests.value.findIndex(r => r.id === updated.id)
    if (idx >= 0) requests.value[idx] = updated
    if (detailDialog.item?.id === updated.id) detailDialog.item = updated
  } catch (e: any) {
    showSnack(e.message || 'Ошибка', 'error')
  }
}

onMounted(loadRequests)
</script>

<style scoped>
.cr-clickable :deep(tbody tr) { cursor: pointer; }
</style>
