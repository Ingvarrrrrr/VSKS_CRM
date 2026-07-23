<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">Авансовые отчёты</h1>
        <span class="text-body-2 text-medium-emphasis">{{ enrichedItems.length }} записей</span>
      </div>
      <div class="d-flex gap-2 align-center">
        <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" @click="showColumnPicker = true">Колонки</v-btn>
        <RegistryExportButton
          title="Авансовые отчёты"
          :get-columns="() => visibleHeaders.filter(h => !['actions','avatar','data-table-expand','data-table-select'].includes(h.key) && !!h.title).map(h => ({ key: h.key, title: h.title, align: h.align }))"
          :get-rows="() => filteredItems"
          :get-capture-el="() => registryArea"
          @error="(msg) => { snack.text = msg; snack.color = 'error'; snack.show = true }"
        />
        <v-btn color="primary" prepend-icon="mdi-plus" to="/advance-reports/create">Добавить</v-btn>
        <v-btn-toggle v-if="!arMobile" v-model="arViewMode" mandatory density="comfortable" variant="outlined" divided class="ml-1">
          <v-btn value="table" size="small" icon="mdi-table" />
          <v-btn value="cards" size="small" icon="mdi-view-grid" />
        </v-btn-toggle>
      </div>
    </div>

    <v-card class="mb-4" variant="outlined">
      <v-card-text class="py-3">
        <div class="d-flex align-center gap-4 flex-wrap">
          <v-select
            v-model="filterSubsidyId"
            :items="subsidies"
            item-title="name"
            item-value="id"
            label="Субсидия"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:220px"
          />
          <v-autocomplete
            v-model="filterContractorIds"
            :items="usedContractors"
            item-title="name"
            item-value="id"
            label="Контрагент"
            variant="outlined"
            density="compact"
            multiple
            chips
            closable-chips
            clearable
            hide-details
            style="min-width:220px"
          />
          <v-autocomplete
            v-model="filterReimbursementUsers"
            :items="usedReimbursementUsers"
            item-title="title"
            item-value="id"
            label="Кому возмещать"
            variant="outlined"
            density="compact"
            multiple
            chips
            closable-chips
            clearable
            hide-details
            style="min-width:220px"
            prepend-inner-icon="mdi-account-cash"
          />
          <v-text-field
            v-model="search"
            prepend-inner-icon="mdi-magnify"
            label="Поиск"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:200px"
          />
          <v-text-field
            v-model="fProduct"
            label="Поиск товара"
            prepend-inner-icon="mdi-magnify"
            variant="outlined" density="compact" hide-details clearable
            placeholder="Название товара..."
            style="min-width:200px"
          />
          <v-btn size="small" variant="tonal" @click="clearFilters">Сбросить</v-btn>
          <v-chip
            v-if="activeFilterCount > 0"
            color="primary"
            variant="tonal"
            prepend-icon="mdi-filter"
            size="small"
            closable
            @click:close="clearAllFilters"
          >
            Фильтры {{ activeFilterCount }}
          </v-chip>
          <v-chip color="primary" variant="tonal" prepend-icon="mdi-cash-multiple" size="small" class="ml-2">
            Сумма: {{ formatMoney(filteredSum) }}
          </v-chip>
        </div>
      </v-card-text>
    </v-card>

    <v-chip-group v-model="filterStatus" class="mb-4">
      <v-chip value="" variant="outlined" filter>Все</v-chip>
      <v-chip
        v-for="s in statusItems"
        :key="s.value"
        :value="s.value"
        :color="s.color"
        filter
        variant="outlined"
      >
        {{ s.label }}
      </v-chip>
    </v-chip-group>

    <div ref="registryArea">
    <v-data-table
        v-if="arEffectiveView === 'table'"
        v-resizable-columns="'advance-reports'"
        v-model="selected"
        v-model:expanded="expandedRows"
        :headers="tableHeaders"
        :items="filteredItemsWithRowNum"
        :loading="loading"
        :search="search"
        :sort-by="localSort ? [localSort] : undefined"
        show-select
        show-expand
        :single-expand="false"
        density="compact"
        hover
        items-per-page="25"
        :items-per-page-options="[25, 50, 100, -1]"
        item-value="id"
        @click:row="onRowClick"
      >
        <!-- ColumnHeaderMenu slots -->
        <template #header.displayName="{ column }">
          <ColumnHeaderMenu
            col-key="displayName"
            :title="column.title"
            col-type="text"
            :model-value="cfg.state.value.filters['displayName'] ?? null"
            :sort-by="getSortBy('displayName')"
            @update:model-value="(v: FilterValue | null) => setFilter('displayName', v)"
            @sort="(dir: 'asc' | 'desc' | null) => applySort('displayName', dir)"
            @hide="toggleVisible('displayName', false)"
          />
        </template>
        <template #header.contractor_name="{ column }">
          <ColumnHeaderMenu
            col-key="contractor_name"
            :title="column.title"
            col-type="enum"
            :items="uniqValues(enrichedItems, 'contractor_name')"
            :model-value="cfg.state.value.filters['contractor_name'] ?? null"
            :sort-by="getSortBy('contractor_name')"
            @update:model-value="(v: FilterValue | null) => setFilter('contractor_name', v)"
            @sort="(dir: 'asc' | 'desc' | null) => applySort('contractor_name', dir)"
            @hide="toggleVisible('contractor_name', false)"
          />
        </template>
        <template #header.reimbursement_user_name="{ column }">
          <ColumnHeaderMenu
            col-key="reimbursement_user_name"
            :title="column.title"
            col-type="enum"
            :items="uniqValues(enrichedItems, 'reimbursement_user_name')"
            :model-value="cfg.state.value.filters['reimbursement_user_name'] ?? null"
            :sort-by="getSortBy('reimbursement_user_name')"
            @update:model-value="(v: FilterValue | null) => setFilter('reimbursement_user_name', v)"
            @sort="(dir: 'asc' | 'desc' | null) => applySort('reimbursement_user_name', dir)"
            @hide="toggleVisible('reimbursement_user_name', false)"
          />
        </template>
        <template #header.subsidy_name="{ column }">
          <ColumnHeaderMenu
            col-key="subsidy_name"
            :title="column.title"
            col-type="enum"
            :items="uniqValues(enrichedItems, 'subsidy_name')"
            :model-value="cfg.state.value.filters['subsidy_name'] ?? null"
            :sort-by="getSortBy('subsidy_name')"
            @update:model-value="(v: FilterValue | null) => setFilter('subsidy_name', v)"
            @sort="(dir: 'asc' | 'desc' | null) => applySort('subsidy_name', dir)"
            @hide="toggleVisible('subsidy_name', false)"
          />
        </template>
        <template #header.nmck="{ column }">
          <ColumnHeaderMenu
            col-key="nmck"
            :title="column.title"
            col-type="number"
            :model-value="cfg.state.value.filters['nmck'] ?? null"
            :sort-by="getSortBy('nmck')"
            align="end"
            @update:model-value="(v: FilterValue | null) => setFilter('nmck', v)"
            @sort="(dir: 'asc' | 'desc' | null) => applySort('nmck', dir)"
            @hide="toggleVisible('nmck', false)"
          />
        </template>
        <template #header.executionDate="{ column }">
          <ColumnHeaderMenu
            col-key="executionDate"
            :title="column.title"
            col-type="date"
            :model-value="cfg.state.value.filters['executionDate'] ?? null"
            :sort-by="getSortBy('executionDate')"
            @update:model-value="(v: FilterValue | null) => setFilter('executionDate', v)"
            @sort="(dir: 'asc' | 'desc' | null) => applySort('executionDate', dir)"
            @hide="toggleVisible('executionDate', false)"
          />
        </template>
        <template #header.status="{ column }">
          <ColumnHeaderMenu
            col-key="status"
            :title="column.title"
            col-type="enum"
            :items="uniqValues(enrichedItems, 'status')"
            :item-labels="STATUS_LABEL"
            :model-value="cfg.state.value.filters['status'] ?? null"
            :sort-by="getSortBy('status')"
            @update:model-value="(v: FilterValue | null) => setFilter('status', v)"
            @sort="(dir: 'asc' | 'desc' | null) => applySort('status', dir)"
            @hide="toggleVisible('status', false)"
          />
        </template>
        <template #header.registry_number="{ column }">
          <ColumnHeaderMenu
            col-key="registry_number"
            :title="column.title"
            col-type="text"
            :model-value="cfg.state.value.filters['registry_number'] ?? null"
            :sort-by="getSortBy('registry_number')"
            @update:model-value="(v: FilterValue | null) => setFilter('registry_number', v)"
            @sort="(dir: 'asc' | 'desc' | null) => applySort('registry_number', dir)"
            @hide="toggleVisible('registry_number', false)"
          />
        </template>
        <template #header.purchase_number="{ column }">
          <ColumnHeaderMenu
            col-key="purchase_number"
            :title="column.title"
            col-type="text"
            :model-value="cfg.state.value.filters['purchase_number'] ?? null"
            :sort-by="getSortBy('purchase_number')"
            @update:model-value="(v: FilterValue | null) => setFilter('purchase_number', v)"
            @sort="(dir: 'asc' | 'desc' | null) => applySort('purchase_number', dir)"
            @hide="toggleVisible('purchase_number', false)"
          />
        </template>
        <template #header.subject="{ column }">
          <ColumnHeaderMenu
            col-key="subject"
            :title="column.title"
            col-type="text"
            :model-value="cfg.state.value.filters['subject'] ?? null"
            :sort-by="getSortBy('subject')"
            @update:model-value="(v: FilterValue | null) => setFilter('subject', v)"
            @sort="(dir: 'asc' | 'desc' | null) => applySort('subject', dir)"
            @hide="toggleVisible('subject', false)"
          />
        </template>
        <template #header.last_receipt_date="{ column }">
          <ColumnHeaderMenu
            col-key="last_receipt_date"
            :title="column.title"
            col-type="date"
            :model-value="cfg.state.value.filters['last_receipt_date'] ?? null"
            :sort-by="getSortBy('last_receipt_date')"
            @update:model-value="(v: FilterValue | null) => setFilter('last_receipt_date', v)"
            @sort="(dir: 'asc' | 'desc' | null) => applySort('last_receipt_date', dir)"
            @hide="toggleVisible('last_receipt_date', false)"
          />
        </template>
        <template #header.planned_total_price="{ column }">
          <ColumnHeaderMenu
            col-key="planned_total_price"
            :title="column.title"
            col-type="number"
            :model-value="cfg.state.value.filters['planned_total_price'] ?? null"
            :sort-by="getSortBy('planned_total_price')"
            align="end"
            @update:model-value="(v: FilterValue | null) => setFilter('planned_total_price', v)"
            @sort="(dir: 'asc' | 'desc' | null) => applySort('planned_total_price', dir)"
            @hide="toggleVisible('planned_total_price', false)"
          />
        </template>
        <template #header.total_nmck="{ column }">
          <ColumnHeaderMenu
            col-key="total_nmck"
            :title="column.title"
            col-type="number"
            :model-value="cfg.state.value.filters['total_nmck'] ?? null"
            :sort-by="getSortBy('total_nmck')"
            align="end"
            @update:model-value="(v: FilterValue | null) => setFilter('total_nmck', v)"
            @sort="(dir: 'asc' | 'desc' | null) => applySort('total_nmck', dir)"
            @hide="toggleVisible('total_nmck', false)"
          />
        </template>
        <!-- End ColumnHeaderMenu slots -->

        <template #item.index="{ item }">
          <!-- Phase 26-hhh: убран white-space:nowrap — позволить overflow-wrap:anywhere
               из useColumnConfig разорвать длинный реестровый номер по ширине
               ячейки (140px), как в OrdersView. Раньше nowrap заставлял текст
               вылезать в соседнюю колонку и сливаться с наименованием. -->
          <span class="text-caption" style="color:#7c3aed; font-family:monospace">
            {{ item.registry_number || `#${item.id}` }}
          </span>
        </template>

        <template #item.displayName="{ item }">
          <span>{{ item.displayName }}</span>
        </template>

        <template #item.contractor_name="{ item }">
          <!-- U-1: Контрагент = продавец из items чека, а не получатель возмещения -->
          <div>
            <!-- Единственный контрагент из items -->
            <v-chip
              v-if="(item as any)._unique_item_contractor_count === 1"
              size="x-small" color="indigo" variant="tonal" prepend-icon="mdi-store"
            >
              {{ (item as any)._unique_item_contractor_name }}
            </v-chip>
            <!-- Несколько контрагентов из items -->
            <v-tooltip v-else-if="(item as any)._unique_item_contractor_count > 1" location="top">
              <template #activator="{ props: tip }">
                <v-chip v-bind="tip" size="x-small" color="orange" variant="tonal" prepend-icon="mdi-domain-switch">
                  {{ (item as any)._unique_item_contractor_name }} +{{ (item as any)._unique_item_contractor_count - 1 }} ещё
                </v-chip>
              </template>
              <span>{{ (item as any)._all_item_contractor_names }}</span>
            </v-tooltip>
            <!-- Fallback: legacy contractor_name -->
            <span v-else class="text-caption">
              {{ (item as any).multi_contractor_label || item.contractor_name || '—' }}
            </span>
            <!-- Получатель возмещения — дополняет, не подменяет -->
            <div v-if="(item as any).reimbursement_user_name" class="text-caption text-medium-emphasis mt-0" style="font-size:11px">
              <v-icon size="12" color="purple">mdi-account</v-icon>
              возмещ.: {{ (item as any).reimbursement_user_name }}
            </div>
          </div>
        </template>

        <template #item.reimbursement_user_name="{ item }">
          <v-chip v-if="item.reimbursement_user_name" size="x-small" color="purple" variant="tonal" prepend-icon="mdi-account">
            {{ item.reimbursement_user_name }}
          </v-chip>
          <v-chip v-else-if="(item as any).responsible_person" size="x-small" color="purple" variant="tonal" prepend-icon="mdi-account">
            {{ (item as any).responsible_person }}
          </v-chip>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <template #item.subsidy_name="{ item }">
          <span class="text-caption">{{ item.subsidy_name || '—' }}</span>
        </template>

        <template #item.status="{ item }">
          <v-chip :color="statusColor(item.status)" size="x-small" variant="tonal">
            {{ statusLabel(item.status, item) }}
          </v-chip>
        </template>

        <template #item.nmck="{ item }">
          {{ formatMoney(item.total_nmck ?? item.planned_total_price) }}
        </template>

        <template #item.executionDate="{ item }">
          {{ item.executionDate ? new Date(item.executionDate).toLocaleDateString('ru-RU') : '—' }}
        </template>

        <!-- Expanded row: состав (items + receipts info) -->
        <template #expanded-row="{ columns, item }">
          <tr>
            <td :colspan="columns.length" class="pa-0">
              <div class="pa-3 bg-grey-lighten-5">
                <div class="text-caption font-weight-medium text-medium-emphasis mb-2">
                  Состав авансового отчёта #{{ item.purchase_number || item.id }}
                </div>
                <div v-if="!item.items || !item.items.length" class="text-caption text-medium-emphasis">
                  Нет позиций
                </div>
                <v-table v-else density="compact">
                  <thead>
                    <tr>
                      <th>Наименование</th>
                      <th class="text-right">Кол-во</th>
                      <th class="text-right">Цена ед.</th>
                      <th class="text-right">Сумма</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(pi, ii) in item.items" :key="ii">
                      <td class="text-caption">{{ pi.item_name || '—' }}</td>
                      <td class="text-right text-caption">{{ pi.quantity ?? '—' }}</td>
                      <td class="text-right text-caption">{{ pi.unit_price ? formatMoney(pi.unit_price) : '—' }}</td>
                      <td class="text-right text-caption">{{ pi.total_price ? formatMoney(pi.total_price) : '—' }}</td>
                    </tr>
                    <tr class="font-weight-bold">
                      <td colspan="3" class="text-right text-caption">Итого:</td>
                      <td class="text-right text-caption">{{ formatMoney((item.items as any[]).reduce((s: number, i: any) => s + (Number(i.total_price) || 0), 0)) }}</td>
                    </tr>
                  </tbody>
                </v-table>
                <div v-if="item.last_receipt_date" class="text-caption text-medium-emphasis mt-2">
                  Последний чек: {{ new Date(item.last_receipt_date).toLocaleDateString('ru-RU') }}
                </div>
              </div>
            </td>
          </tr>
        </template>

        <template #no-data>
          <div class="text-center py-10">
            <v-icon icon="mdi-cash-register" size="48" color="grey-lighten-1" class="mb-3" />
            <div class="text-medium-emphasis">Авансовые отчёты не найдены</div>
            <v-btn color="primary" class="mt-3" to="/advance-reports/create">Создать первый</v-btn>
          </div>
        </template>
      </v-data-table>

    <!-- Cards view -->
    <div v-else>
      <v-row dense>
        <v-col v-for="item in arPaged" :key="item.id" cols="12" sm="6" md="4" lg="3">
          <v-card variant="outlined" class="h-100 d-flex flex-column" hover @click="router.push(`/advance-reports/${item.id}/edit`)">
            <v-card-item class="pb-1">
              <v-card-title class="text-body-2 d-flex align-center ga-2 flex-wrap">
                <span class="font-weight-bold" style="color:#7c3aed; font-family:monospace">
                  {{ item.registry_number || ('#' + item.id) }}
                </span>
                <v-chip :color="statusColor(item.status)" size="x-small" variant="tonal">
                  {{ statusLabel(item.status, item) }}
                </v-chip>
              </v-card-title>
            </v-card-item>
            <v-card-text class="py-1 flex-grow-1">
              <div v-if="item.displayName && item.displayName !== '—'" class="text-caption text-medium-emphasis mb-1" style="overflow-wrap:anywhere">
                {{ item.displayName.length > 80 ? item.displayName.slice(0, 80) + '...' : item.displayName }}
              </div>
              <div class="text-caption text-medium-emphasis">Контрагент</div>
              <div class="text-body-2 mb-1" style="overflow-wrap:anywhere">
                <span v-if="(item as any)._unique_item_contractor_count >= 1">
                  {{ (item as any)._unique_item_contractor_name }}
                  <span v-if="(item as any)._unique_item_contractor_count > 1" class="text-caption text-medium-emphasis">
                    +{{ (item as any)._unique_item_contractor_count - 1 }} ещё
                  </span>
                </span>
                <span v-else>{{ item.contractor_name || '—' }}</span>
              </div>
              <div v-if="(item as any).reimbursement_user_name" class="text-caption text-medium-emphasis mb-1">
                <v-icon size="12" color="purple">mdi-account</v-icon>
                возмещ.: {{ (item as any).reimbursement_user_name }}
              </div>
              <div class="text-caption text-medium-emphasis">Субсидия</div>
              <div class="mb-1">
                <v-chip v-if="item.subsidy_name" size="x-small" color="primary" variant="tonal">{{ item.subsidy_name }}</v-chip>
                <span v-else class="text-body-2 text-medium-emphasis">—</span>
              </div>
              <div class="d-flex flex-wrap ga-3 mt-2">
                <div>
                  <div class="text-caption text-medium-emphasis">Сумма</div>
                  <div class="text-body-2 font-weight-bold">{{ formatMoney(item.total_nmck ?? item.planned_total_price) }}</div>
                </div>
                <div v-if="item.executionDate">
                  <div class="text-caption text-medium-emphasis">Дата исполнения</div>
                  <div class="text-body-2">{{ new Date(item.executionDate).toLocaleDateString('ru-RU') }}</div>
                </div>
              </div>
            </v-card-text>
            <v-divider />
            <v-card-actions class="py-1" @click.stop>
              <v-spacer />
              <v-btn icon="mdi-pencil" variant="text" size="small" color="primary" @click.stop="router.push(`/advance-reports/${item.id}/edit`)" />
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>
      <div v-if="!arPaged.length" class="text-center py-10">
        <v-icon icon="mdi-cash-register" size="48" color="grey-lighten-1" class="mb-3" />
        <div class="text-medium-emphasis">Авансовые отчёты не найдены</div>
      </div>
      <v-pagination v-if="arTotalPages > 1" v-model="arPage" :length="arTotalPages" density="compact" total-visible="7" class="d-flex justify-center mt-4" />
    </div>
    </div>

    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3000" location="bottom right">
      {{ snack.text }}
    </v-snackbar>

    <ColumnConfigDialog
      v-model="showColumnPicker"
      :all-columns="allColumns"
      :state="colState"
      :show-width="true"
      :groups="groups"
      :toggle-visible="toggleVisible"
      :set-position="setPosition"
      :set-width="setWidth"
      :reset="resetColumns"
    />
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useColumnConfig, type ColumnDef, type FilterValue } from '@/composables/useColumnConfig'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'
import RegistryExportButton from '@/components/RegistryExportButton.vue'
import ColumnHeaderMenu from '@/components/ColumnHeaderMenu.vue'
import { formatMoney } from '@/utils/formatMoney'
import { useCardView } from '@/composables/useCardView'

const router = useRouter()
const registryArea = ref<HTMLElement | null>(null)

function onRowClick(_e: MouseEvent | undefined, ctx: any) {
  // Не реагируем если клик пришёл по чекбоксу/expand-кнопке (Vuetify сам обрабатывает)
  const target = (_e?.target as HTMLElement | undefined)
  if (target?.closest('.v-data-table__td--select-row, .v-data-table__td--select-multiple, [role="checkbox"], button')) return
  const id = ctx?.item?.id
  if (id) router.push(`/advance-reports/${id}/edit`)
}

interface Purchase {
  id: number
  purchase_number?: number
  status: string
  item_name?: string
  subject?: string
  subsidy_id?: number
  subsidy_name?: string
  total_nmck?: number
  planned_total_price?: number
  delivery_date?: string
  acceptance_doc_date?: string
  last_receipt_date?: string
  purchase_method?: string
  purchase_contract_type?: string
  contractor_id?: number
  contractor_name?: string
  contractor_inn?: string
  reimbursement_user_id?: number | null
  reimbursement_user_name?: string | null
  multi_contractor_label?: string | null
  responsible_person?: string | null
  registry_number?: string | null
  items?: any[]
}

interface Subsidy { id: number; name: string }
interface Contractor { id: number; name: string; inn?: string }

const FRAMEWORK_TYPES = new Set(['framework_cumulative', 'framework_with_amount'])

const items = ref<Purchase[]>([])
const subsidies = ref<Subsidy[]>([])
const contractors = ref<Contractor[]>([])
const loading = ref(false)
const filterStatus = ref<string>('')
const filterSubsidyId = ref<number | null>(null)
const filterContractorIds = ref<number[]>([])
const filterReimbursementUsers = ref<number[]>([])
const allUsers = ref<any[]>([])
const search = ref('')
const fProduct = ref('')
const selected = ref<number[]>([])
const expandedRows = ref<number[]>([])

const snack = reactive({ show: false, text: '', color: 'success' })

const STATUS_LABEL: Record<string, string> = {
  wishes: 'Желания', plan_schedule: 'План-график',
  work_in_progress: 'Ведётся работа',
  contracted: 'Договор', ordered: 'Заказано',
  delivered: 'Поставлено', paid: 'Оплачено',
}
const STATUS_COLOR: Record<string, string> = {
  wishes: 'amber', plan_schedule: 'orange',
  work_in_progress: 'teal',
  contracted: 'indigo', ordered: 'purple',
  delivered: 'deep-purple', paid: 'green',
}
const statusItems = Object.entries(STATUS_LABEL).map(([value, label]) => ({
  value, label, color: STATUS_COLOR[value],
}))

const statusLabel = (s: string, item?: Purchase) => {
  if (s === 'contracted' && item && FRAMEWORK_TYPES.has(item.purchase_contract_type || '')) return 'Заказ'
  return STATUS_LABEL[s] || s
}
const statusColor = (s: string) => STATUS_COLOR[s] || 'grey'
const formatMoney = (v?: number | null) => v ? Number(v).toLocaleString('ru-RU') + ' ₽' : '—'

function pickDate(...dates: (string | undefined | null)[]): string | null {
  for (const d of dates) {
    if (d) return d
  }
  return null
}

const allColumns: ColumnDef[] = [
  // core — видимые по умолчанию
  // _rownum добавляется отдельно через tableHeaders computed (всегда первая колонка, не зависит от LS)
  { title: '', key: 'data-table-select', width: 40, group: 'core' },
  { title: '', key: 'data-table-expand', width: 40, group: 'core' },
  { title: '№', key: 'index', width: 140, sortable: false, group: 'core' },
  { title: 'Наименование', key: 'displayName', group: 'core' },
  { title: 'Контрагент', key: 'contractor_name', width: 220, group: 'core' },
  { title: 'Кому возмещать', key: 'reimbursement_user_name', group: 'core' },
  { title: 'Субсидия', key: 'subsidy_name', width: 160, group: 'core' },
  { title: 'Сумма', key: 'nmck', width: 130, align: 'end', group: 'core' },
  { title: 'Дата исполнения', key: 'executionDate', width: 140, group: 'core' },
  { title: 'Статус', key: 'status', width: 130, group: 'core' },
  // all — дополнительные поля из Purchase (purchase_method='advance')
  { title: '№ реестра', key: 'registry_number', width: 130, group: 'all' },
  { title: '№ закупки', key: 'purchase_number', width: 110, group: 'all' },
  { title: 'Предмет', key: 'subject', group: 'all' },
  { title: 'Тип позиции', key: 'item_type', width: 120, group: 'all' },
  { title: 'Кол-во', key: 'planned_quantity', width: 100, align: 'end', group: 'all' },
  { title: 'Ед. изм.', key: 'unit', width: 90, group: 'all' },
  { title: 'Цена ед. (план)', key: 'planned_unit_price', width: 150, align: 'end', group: 'all' },
  { title: 'Сумма (план)', key: 'planned_total_price', width: 140, align: 'end', group: 'all' },
  { title: 'Цена ед. (факт)', key: 'final_unit_price', width: 150, align: 'end', group: 'all' },
  { title: 'Сумма (факт)', key: 'final_total_amount', width: 140, align: 'end', group: 'all' },
  { title: 'Итого НМЦД', key: 'total_nmck', width: 130, align: 'end', group: 'all' },
  { title: 'Цена договора', key: 'contract_price', width: 140, align: 'end', group: 'all' },
  { title: '№ договора', key: 'contract_number', width: 140, group: 'all' },
  { title: 'Дата договора', key: 'contract_date', width: 140, group: 'all' },
  { title: 'Ответственный', key: 'responsible_person', group: 'all' },
  { title: 'Последний чек', key: 'last_receipt_date', width: 150, group: 'all' },
  { title: 'Дата поставки', key: 'delivery_date', width: 140, group: 'all' },
  { title: 'Дата закрывающего', key: 'acceptance_doc_date', width: 170, group: 'all' },
  { title: 'Закрывающий документ', key: 'acceptance_doc_name', width: 190, group: 'all' },
  { title: '№ закрывающего', key: 'acceptance_doc_number', width: 160, group: 'all' },
  { title: 'Сумма закрывающего', key: 'acceptance_doc_amount', width: 180, align: 'end', group: 'all' },
  { title: '№ ПП', key: 'payment_doc_number', width: 110, group: 'all' },
  { title: 'Дата ПП', key: 'payment_doc_date', width: 130, group: 'all' },
  { title: 'Оплачено', key: 'payment_amount', width: 130, align: 'end', group: 'all' },
  { title: 'Оплачено (федерал.)', key: 'payment_federal', width: 170, align: 'end', group: 'all' },
  { title: 'Место доставки', key: 'delivery_location', group: 'all' },
  { title: 'Тип места', key: 'delivery_location_kind', width: 130, group: 'all' },
  { title: 'Адрес доставки', key: 'delivery_address', group: 'all' },
  { title: 'Срок подачи заявок', key: 'submission_deadline', width: 170, group: 'all' },
  { title: 'Нач. период услуги', key: 'service_start_date', width: 170, group: 'all' },
  { title: 'Кон. период услуги', key: 'service_end_date', width: 170, group: 'all' },
  { title: 'Дедлайн услуги', key: 'service_deadline_date', width: 150, group: 'all' },
  { title: 'Дней услуги', key: 'service_term_days', width: 130, group: 'all' },
  { title: 'Этап', key: 'stage_label', width: 160, group: 'all' },
  { title: 'Подстатус', key: 'substatus', width: 150, group: 'all' },
  { title: 'ФЭО категория', key: 'feo_category_name', group: 'all' },
  { title: 'Мероприятие', key: 'event_name', group: 'all' },
  { title: 'Способ закупки', key: 'purchase_method', width: 150, group: 'all' },
  { title: 'Основание закупки', key: 'purchase_basis', width: 160, group: 'all' },
  { title: 'Предоплата', key: 'is_prepayment', width: 120, group: 'all' },
  { title: 'Дата предоплаты', key: 'prepayment_date', width: 150, group: 'all' },
  { title: 'Скорее всего нужно', key: 'is_likely_needed', width: 170, group: 'all' },
  { title: 'Основание оплаты', key: 'payment_basis_type', width: 170, group: 'all' },
  { title: 'Казначейский код', key: 'treasury_code', width: 160, group: 'all' },
  { title: 'Претензионная работа', key: 'has_pretension', width: 180, group: 'all' },
  { title: 'НДС применяется', key: 'vat_applicable', width: 150, group: 'all' },
  { title: 'Ставка НДС', key: 'vat_rate', width: 120, group: 'all' },
  { title: 'Служебная записка', key: 'service_note_text', group: 'all' },
  { title: 'ID субсидии', key: 'subsidy_id', width: 110, group: 'all' },
  { title: 'ID договора', key: 'contract_id', width: 110, group: 'all' },
]

const groups = [
  { key: 'core', label: 'Основные' },
  { key: 'all', label: 'Все возможные' },
]

const cfg = useColumnConfig('advance_reports', allColumns)
const { state: colState, visibleHeaders, toggleVisible, setPosition, setWidth, reset: resetColumns,
  setFilter, clearAllFilters, activeFilterCount } = cfg
// _rownum — всегда первая колонка, не зависит от useColumnConfig состояния
const tableHeaders = computed(() => [
  { title: '№ п/п', key: '_rownum', width: 60, sortable: false },
  ...visibleHeaders.value,
])
const showColumnPicker = ref(false)

// Дедуп по имени контрагента — у авансовых contractor_id часто пуст, есть только contractor_name.
const usedContractors = computed(() => {
  const byName = new Map<string, any>()
  for (const p of items.value) {
    const name = p.contractor_name
    if (!name || byName.has(name)) continue
    const real = contractors.value.find(c =>
      (p.contractor_id && c.id === p.contractor_id) ||
      (p.contractor_inn && c.inn === p.contractor_inn) ||
      c.name === name
    )
    byName.set(name, real || { id: -byName.size - 1, name, inn: p.contractor_inn || '' })
  }
  return Array.from(byName.values())
})

// Список юзеров для filter dropdown — берём всех из /users/ (с fallback на имена из items)
const usedReimbursementUsers = computed(() => {
  // Имена→id из items, на случай если в /users/ нет какого-то юзера
  const fromItems = new Map<number, string>()
  for (const p of items.value as any[]) {
    if (p.reimbursement_user_id && p.reimbursement_user_name) {
      fromItems.set(p.reimbursement_user_id, p.reimbursement_user_name)
    }
  }
  // Все юзеры из API
  const list = allUsers.value.map((u: any) => ({
    id: u.id,
    title: u.full_name || u.username || `#${u.id}`,
  }))
  // Дополнить из items если кого-то не было в /users/
  const ids = new Set(list.map(u => u.id))
  for (const [id, name] of fromItems) {
    if (!ids.has(id)) list.push({ id, title: name })
  }
  return list.sort((a, b) => a.title.localeCompare(b.title, 'ru'))
})

const enrichedItems = computed(() => items.value.map(p => {
  // U-1: вычислить уникальных контрагентов из purchase items
  const itemContractors = (p.items || [])
    .map((it: any) => it.contractor_name)
    .filter((n: any): n is string => !!n)
  const uniqueContractors = [...new Set(itemContractors)]
  const uniqueCount = uniqueContractors.length
  return {
    ...p,
    displayName: p.subject || p.item_name || '—',
    executionDate: pickDate(p.last_receipt_date, p.acceptance_doc_date, p.delivery_date),
    _unique_item_contractor_count: uniqueCount,
    _unique_item_contractor_name: uniqueCount > 0 ? uniqueContractors[0] : null,
    _all_item_contractor_names: uniqueContractors.join(', '),
  }
}))

const filteredItems = computed(() => {
  let r = enrichedItems.value
  if (filterStatus.value) r = r.filter(p => p.status === filterStatus.value)
  if (filterSubsidyId.value) r = r.filter(p => p.subsidy_id === filterSubsidyId.value)
  if (filterContractorIds.value.length) {
    const allowedNames = new Set(
      usedContractors.value
        .filter((c: any) => filterContractorIds.value.includes(c.id))
        .map((c: any) => c.name)
    )
    r = r.filter(p => !!p.contractor_name && allowedNames.has(p.contractor_name))
  }
  if (filterReimbursementUsers.value.length) {
    const allowed = new Set(filterReimbursementUsers.value)
    r = r.filter(p => (p as any).reimbursement_user_id && allowed.has((p as any).reimbursement_user_id))
  }
  if (fProduct.value && fProduct.value.trim()) {
    const q = fProduct.value.trim().toLowerCase()
    r = r.filter(p =>
      (p as any).items?.some((it: any) => it.item_name?.toLowerCase().includes(q)) ||
      p.subject?.toLowerCase().includes(q) ||
      p.item_name?.toLowerCase().includes(q)
    )
  }
  r = r.filter(matchesColumnFilters)
  return r
})

const filteredItemsWithRowNum = computed(() => {
  // Нумерация по возрастанию id: более раннее (меньший id) = меньший _rownum
  const sorted = [...filteredItems.value].sort((a, b) => (Number(a.id) || 0) - (Number(b.id) || 0))
  const map = new Map<string, number>()
  sorted.forEach((p, idx) => map.set(String(p.id), idx + 1))
  return filteredItems.value.map(p => ({ ...p, _rownum: map.get(String(p.id)) ?? '' }))
})

const filteredSum = computed(() =>
  filteredItems.value.reduce((acc, p) => {
    const v = (p as any).final_total_amount ?? (p as any).planned_total_price ?? 0
    return acc + Number(v)
  }, 0)
)

// ---- Column-header filtering & sorting ----

function uniqValues(rows: any[], key: string): (string | number | null)[] {
  const set = new Set<any>()
  rows.forEach(r => set.add(r?.[key] ?? null))
  return [...set].sort((a, b) => String(a ?? '').localeCompare(String(b ?? '')))
}

function matchesColumnFilters(row: any): boolean {
  const filters = cfg.state.value.filters
  for (const [k, f] of Object.entries(filters)) {
    const v = row?.[k] ?? null
    if (f.type === 'text') {
      if (!f.q) continue
      if (!String(v ?? '').toLowerCase().includes(f.q.toLowerCase())) return false
    } else if (f.type === 'enum') {
      if (!f.values || f.values.length === 0) continue
      if (!f.values.includes(v)) return false
    } else if (f.type === 'number') {
      const n = typeof v === 'number' ? v : parseFloat(v)
      if (f.min != null && !(n >= f.min)) return false
      if (f.max != null && !(n <= f.max)) return false
    } else if (f.type === 'date') {
      if (!v) { if (f.from || f.to) return false; continue }
      const d = String(v).slice(0, 10)
      if (f.from && d < f.from) return false
      if (f.to && d > f.to) return false
    } else if (f.type === 'boolean') {
      if (f.value == null) continue
      if (Boolean(v) !== f.value) return false
    }
  }
  return true
}

const localSort = ref<{ key: string; order: 'asc' | 'desc' } | null>(null)
function getSortBy(k: string) { return localSort.value?.key === k ? localSort.value.order : null }
function applySort(k: string, dir: 'asc' | 'desc' | null) { localSort.value = dir ? { key: k, order: dir } : null }

// ---- End column-header helpers ----

function clearFilters() {
  filterStatus.value = ''
  filterSubsidyId.value = null
  filterContractorIds.value = []
  filterReimbursementUsers.value = []
  search.value = ''
  fProduct.value = ''
  clearAllFilters()
}

// Phase 26-ZZ: bulk-load контрагентов убран. usedContractors computed
// dedupe-by-name из items, не требует справочника.
async function load() {
  loading.value = true
  try {
    // Phase 26-ZZ: bulk-load контрагентов убран — usedContractors берёт имена из items
    const [purchasesData, subsidiesData, usersData] = await Promise.all([
      apiFetch<Purchase[]>('/purchases/?purchase_method=advance&scope=advance_reports'),
      apiFetch<Subsidy[]>('/subsidies/'),
      apiFetch<any[]>('/users/').catch(() => []),
    ])
    items.value = purchasesData
    subsidies.value = subsidiesData
    allUsers.value = Array.isArray(usersData) ? usersData : []
  } catch {
    snack.text = 'Ошибка загрузки'; snack.color = 'error'; snack.show = true
  } finally {
    loading.value = false
  }
}

// ── Card view (table↔cards toggle) ────────────────────────────────────────
const {
  mobile: arMobile,
  viewMode: arViewMode,
  effectiveView: arEffectiveView,
  page: arPage,
  totalPages: arTotalPages,
  paged: arPaged,
} = useCardView({
  storageKey: 'advance_reports_view_mode',
  source: () => filteredItemsWithRowNum.value,
  search: () => search.value,
  searchFields: (item) => [
    item.registry_number,
    item.displayName,
    item.contractor_name,
    item.subsidy_name,
    item.reimbursement_user_name,
    item.subject,
    item.item_name,
    (item as any)._unique_item_contractor_name,
  ],
})

onMounted(load)
</script>
