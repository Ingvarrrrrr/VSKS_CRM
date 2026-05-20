<template>
  <v-container fluid class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">Автотранспорт</h1>
        <span class="text-body-2 text-medium-emphasis">{{ total }} записей</span>
      </div>
      <div class="d-flex gap-2">
        <v-btn variant="outlined" size="small" prepend-icon="mdi-view-dashboard"
          @click="router.push('/property/vehicles/dashboard')">Дашборд</v-btn>
        <v-btn
          v-if="authStore.hasAction('vehicle.import')"
          variant="outlined" prepend-icon="mdi-file-excel" color="green"
          @click="importDialogShow = true">
          Импорт Excel
        </v-btn>
        <v-btn color="primary" prepend-icon="mdi-plus" @click="createDialog.show = true">Добавить ТС</v-btn>
      </div>
    </div>

    <!-- Filters -->
    <v-card class="mb-4" variant="outlined">
      <v-card-text class="py-3">
        <div class="d-flex align-center gap-4 flex-wrap">
          <v-select
            v-model="filterStates"
            :items="stateOptions"
            item-title="label"
            item-value="value"
            label="Состояние"
            variant="outlined"
            density="compact"
            multiple
            chips
            closable-chips
            clearable
            hide-details
            style="min-width:200px"
          />
          <v-select
            v-model="filterTypes"
            :items="typeOptions"
            item-title="label"
            item-value="value"
            label="Тип ТС"
            variant="outlined"
            density="compact"
            multiple
            chips
            closable-chips
            clearable
            hide-details
            style="min-width:200px"
          />
          <v-select
            v-model="filterFuelTypes"
            :items="fuelTypeOptions"
            item-title="label"
            item-value="value"
            label="Топливо"
            variant="outlined"
            density="compact"
            multiple
            chips
            closable-chips
            clearable
            hide-details
            style="min-width:180px"
          />
          <v-autocomplete
            v-model="filterOwnerOrgIds"
            :items="orgsList"
            item-title="name"
            item-value="id"
            label="Владелец"
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
            v-model="filterAssignedOrgIds"
            :items="orgsList"
            item-title="name"
            item-value="id"
            label="Эксплуатант"
            variant="outlined"
            density="compact"
            multiple
            chips
            closable-chips
            clearable
            hide-details
            style="min-width:220px"
          />
          <v-text-field
            v-model="filterSearch"
            prepend-inner-icon="mdi-magnify"
            label="Поиск (гос.№, марка, VIN)"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:220px"
          />
          <v-btn
            size="small" variant="tonal" color="primary"
            prepend-icon="mdi-bookmark-plus-outline"
            @click="saveFilterPreset">
            Сохранить фильтр
          </v-btn>
          <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" @click="showColumnPicker = true">Колонки</v-btn>
          <v-chip
            v-if="activeFiltersCount > 0"
            color="deep-orange" variant="tonal" size="small"
            prepend-icon="mdi-filter-multiple"
            class="ml-1"
            closable
            @click:close="clearAllFilters">
            Фильтры {{ activeFiltersCount }}
          </v-chip>
        </div>

        <!-- Saved presets -->
        <div v-if="savedFilterPresets.length" class="d-flex align-center gap-2 flex-wrap mt-2">
          <span class="text-caption text-medium-emphasis">Пресеты:</span>
          <v-chip
            v-for="preset in savedFilterPresets" :key="preset.name"
            size="small" variant="tonal" color="primary"
            class="cursor-pointer"
            @click="applyFilterPreset(preset)">
            {{ preset.name }}
            <v-icon icon="mdi-close" size="12" class="ml-1" @click.stop="removeFilterPreset(preset.name)" />
          </v-chip>
        </div>
      </v-card-text>
    </v-card>

    <!-- Bulk actions bar -->
    <div v-if="selectedVehicles.length > 0" class="d-flex align-center gap-3 mb-3 pa-3 bg-blue-lighten-5 rounded-lg">
      <v-icon icon="mdi-checkbox-marked-outline" color="primary" />
      <span class="text-body-2 font-weight-medium">Выбрано: {{ selectedVehicles.length }}</span>
      <v-spacer />
      <v-btn variant="text" size="small" @click="selectedVehicles = []">Снять выделение</v-btn>
    </div>

    <!-- Table -->
    <v-data-table-server
      :headers="cfg.visibleHeaders"
      :items="vehicles"
      :loading="loading"
      :items-length="total"
      item-value="id"
      density="compact"
      hover
      show-expand
      show-select
      v-model="selectedVehicles"
      v-model:expanded="expandedRows"
      v-model:page="page"
      v-model:items-per-page="itemsPerPage"
      :items-per-page-options="[25, 50, 100]"
      return-object
      class="vehicles-clickable"
      @click:row="onRowClick"
      @update:options="onTableOptions"
    >
      <!-- ColumnHeaderMenu slots -->
      <template #header.plate="{ column }">
        <ColumnHeaderMenu col-key="plate" :title="column.title" col-type="text"
          :model-value="cfg.state.value.filters['plate'] ?? null"
          :sort-by="getSortBy('plate')"
          @update:model-value="v => cfg.setFilter('plate', v)"
          @sort="dir => applySort('plate', dir)"
          @hide="cfg.toggleVisible('plate', false)" />
      </template>
      <template #header.brand_model="{ column }">
        <ColumnHeaderMenu col-key="brand_model" :title="column.title" col-type="text"
          :model-value="cfg.state.value.filters['brand_model'] ?? null"
          :sort-by="getSortBy('brand_model')"
          @update:model-value="v => cfg.setFilter('brand_model', v)"
          @sort="dir => applySort('brand_model', dir)"
          @hide="cfg.toggleVisible('brand_model', false)" />
      </template>
      <template #header.type_label="{ column }">
        <ColumnHeaderMenu col-key="type_label" :title="column.title" col-type="enum"
          :items="typeOptions.map(o => o.value)"
          :item-labels="Object.fromEntries(typeOptions.map(o => [o.value, o.label]))"
          :model-value="cfg.state.value.filters['type_label'] ?? null"
          :sort-by="getSortBy('type_label')"
          @update:model-value="v => cfg.setFilter('type_label', v)"
          @sort="dir => applySort('type_label', dir)"
          @hide="cfg.toggleVisible('type_label', false)" />
      </template>
      <template #header.state_label="{ column }">
        <ColumnHeaderMenu col-key="state_label" :title="column.title" col-type="enum"
          :items="stateOptions.map(o => o.value)"
          :item-labels="Object.fromEntries(stateOptions.map(o => [o.value, o.label]))"
          :model-value="cfg.state.value.filters['state_label'] ?? null"
          :sort-by="getSortBy('state_label')"
          @update:model-value="v => cfg.setFilter('state_label', v)"
          @sort="dir => applySort('state_label', dir)"
          @hide="cfg.toggleVisible('state_label', false)" />
      </template>
      <template #header.owner_org_name="{ column }">
        <ColumnHeaderMenu col-key="owner_org_name" :title="column.title" col-type="text"
          :model-value="cfg.state.value.filters['owner_org_name'] ?? null"
          :sort-by="getSortBy('owner_org_name')"
          @update:model-value="v => cfg.setFilter('owner_org_name', v)"
          @sort="dir => applySort('owner_org_name', dir)"
          @hide="cfg.toggleVisible('owner_org_name', false)" />
      </template>
      <template #header.assigned_label="{ column }">
        <ColumnHeaderMenu col-key="assigned_label" :title="column.title" col-type="text"
          :model-value="cfg.state.value.filters['assigned_label'] ?? null"
          :sort-by="getSortBy('assigned_label')"
          @update:model-value="v => cfg.setFilter('assigned_label', v)"
          @sort="dir => applySort('assigned_label', dir)"
          @hide="cfg.toggleVisible('assigned_label', false)" />
      </template>
      <template #header.insurance_until="{ column }">
        <ColumnHeaderMenu col-key="insurance_until" :title="column.title" col-type="date"
          :model-value="cfg.state.value.filters['insurance_until'] ?? null"
          :sort-by="getSortBy('insurance_until')"
          @update:model-value="v => cfg.setFilter('insurance_until', v)"
          @sort="dir => applySort('insurance_until', dir)"
          @hide="cfg.toggleVisible('insurance_until', false)" />
      </template>

      <!-- item.data-table-expand: показываем expand для всех строк -->
      <template #item.data-table-expand="{ internalItem, isExpanded, toggleExpand }">
        <v-btn
          :icon="isExpanded(internalItem) ? 'mdi-chevron-up' : 'mdi-chevron-down'"
          variant="text"
          size="small"
          @click.stop="toggleExpand(internalItem)"
        />
      </template>

      <!-- plate column: визуальный номерной знак + подсветка истекающей страховки -->
      <template #item.plate="{ item }">
        <div class="d-flex align-center gap-1">
          <LicensePlate :model-value="item.plate" :readonly="true" />
          <v-icon v-if="isInsuranceExpiring(item)" icon="mdi-alert-circle" size="x-small"
            color="warning" title="ОСАГО истекает менее чем через 30 дней" />
        </div>
      </template>

      <!-- brand_model computed cell -->
      <template #item.brand_model="{ item }">
        <span>{{ [item.brand, item.model].filter(Boolean).join(' ') || '—' }}</span>
        <div v-if="item.color" class="text-caption text-medium-emphasis">{{ item.color }}</div>
      </template>

      <!-- type_label -->
      <template #item.type_label="{ item }">
        <v-chip size="x-small" variant="tonal" :color="typeColor(item.type)">
          {{ typeLabel(item.type) }}
        </v-chip>
      </template>

      <!-- state_label -->
      <template #item.state_label="{ item }">
        <v-chip size="x-small" variant="tonal" :color="stateColor(item.state)">
          {{ stateLabel(item.state) }}
        </v-chip>
      </template>

      <!-- owner_org_name -->
      <template #item.owner_org_name="{ item }">
        <span class="text-body-2">{{ item.owner_org_name || '—' }}</span>
      </template>

      <!-- assigned_label: org name OR text -->
      <template #item.assigned_label="{ item }">
        <span class="text-body-2">{{ item.assigned_org_name || item.assigned_text || '—' }}</span>
      </template>

      <!-- insurance_until with color warning -->
      <template #item.insurance_until="{ item }">
        <span :class="insuranceClass(item)">{{ formatDate(item.insurance_until) }}</span>
      </template>

      <!-- odometer -->
      <template #item.current_odometer_km="{ item }">
        <span>{{ item.current_odometer_km != null ? item.current_odometer_km.toLocaleString('ru-RU') : '—' }}</span>
      </template>

      <!-- fuel_type -->
      <template #item.fuel_type="{ item }">
        <span class="text-caption">{{ fuelTypeLabel(item.fuel_type) }}</span>
      </template>

      <!-- next_to_km with warning -->
      <template #item.next_to_km="{ item }">
        <span :class="nextToClass(item)">
          {{ item.next_to_km != null ? item.next_to_km.toLocaleString('ru-RU') : '—' }}
        </span>
      </template>

      <!-- Expanded row: краткие детали из props JSONB -->
      <template #expanded-row="{ columns, item }">
        <tr>
          <td :colspan="columns.length" class="pa-0 bg-grey-lighten-5">
            <div class="pa-4 d-flex flex-wrap gap-6">
              <div>
                <div class="text-caption text-medium-emphasis mb-1">VIN</div>
                <div class="text-body-2 font-weight-medium">{{ item.vin || '—' }}</div>
              </div>
              <div v-if="item.props?.branding">
                <div class="text-caption text-medium-emphasis mb-1">Брендирование</div>
                <div class="text-body-2">{{ item.props.branding }}</div>
              </div>
              <div v-if="item.props?.paint_condition">
                <div class="text-caption text-medium-emphasis mb-1">Лакокрасочное покрытие</div>
                <div class="text-body-2">{{ item.props.paint_condition }}</div>
              </div>
              <div v-if="item.props?.tires_type">
                <div class="text-caption text-medium-emphasis mb-1">Авторезина</div>
                <div class="text-body-2">{{ item.props.tires_type }}</div>
              </div>
              <div v-if="item.props?.defect_description">
                <div class="text-caption text-medium-emphasis mb-1">Неисправность</div>
                <div class="text-body-2 text-error">{{ item.props.defect_description }}</div>
              </div>
              <div v-if="item.props?.note">
                <div class="text-caption text-medium-emphasis mb-1">Примечание</div>
                <div class="text-body-2">{{ item.props.note }}</div>
              </div>
              <div class="d-flex align-end ml-auto">
                <v-btn size="small" variant="tonal" color="primary"
                  :to="`/property/vehicles/${item.id}`"
                  prepend-icon="mdi-open-in-new"
                  @click.stop>
                  Открыть карточку
                </v-btn>
              </div>
            </div>
          </td>
        </tr>
      </template>

      <template #no-data>
        <div class="text-center py-10">
          <v-icon icon="mdi-car-off" size="48" color="grey-lighten-1" class="mb-3" />
          <div class="text-medium-emphasis">ТС не найдены</div>
        </div>
      </template>
    </v-data-table-server>

    <!-- ── Create dialog ── -->
    <v-dialog v-model="createDialog.show" max-width="560" persistent>
      <v-card>
        <v-card-title class="pa-5 pb-2 d-flex align-center">
          <v-icon icon="mdi-car-plus" color="primary" class="mr-2" />
          Добавить ТС
          <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto"
            @click="resetCreateDialog" />
        </v-card-title>
        <v-card-text class="pa-5 pt-2">
          <v-text-field v-model="createDialog.plate" label="Гос. номер *" variant="outlined"
            density="compact" class="mb-3" :rules="[v => !!v || 'Обязательное поле']" />
          <div class="d-flex gap-3 mb-3">
            <v-text-field v-model="createDialog.brand" label="Марка" variant="outlined" density="compact" />
            <v-text-field v-model="createDialog.model" label="Модель" variant="outlined" density="compact" />
          </div>
          <v-autocomplete
            v-model="createDialog.owner_org_id"
            :items="orgsList"
            item-title="name"
            item-value="id"
            label="Владелец *"
            variant="outlined"
            density="compact"
            class="mb-3"
          />
          <v-select
            v-model="createDialog.type"
            :items="typeOptions"
            item-title="label"
            item-value="value"
            label="Тип ТС"
            variant="outlined"
            density="compact"
            class="mb-3"
            clearable
          />
          <v-select
            v-model="createDialog.state"
            :items="stateOptions"
            item-title="label"
            item-value="value"
            label="Состояние"
            variant="outlined"
            density="compact"
          />
        </v-card-text>
        <v-card-actions class="pa-5 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="resetCreateDialog">Отмена</v-btn>
          <v-btn color="primary" variant="flat"
            :loading="createDialog.loading"
            :disabled="!createDialog.plate || !createDialog.owner_org_id"
            @click="doCreate">
            Создать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Import Dialog ── -->
    <VehicleImportDialog
      v-model="importDialogShow"
      :orgs="orgsList"
      @imported="onImported"
    />

    <!-- ── Column Config Dialog ── -->
    <ColumnConfigDialog
      v-model="showColumnPicker"
      :all-columns="allColumns"
      :state="cfg.state.value"
      :show-width="true"
      :toggle-visible="cfg.toggleVisible"
      :set-position="cfg.setPosition"
      :set-width="cfg.setWidth"
      :reset="cfg.reset"
    />

    <!-- ── Save Filter Preset Dialog ── -->
    <v-dialog v-model="filterPresetDialog.show" max-width="380">
      <v-card>
        <v-card-title class="pa-4">Сохранить фильтр</v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-text-field
            v-model="filterPresetDialog.name"
            label="Название пресета"
            variant="outlined" density="compact" autofocus
            @keyup.enter="confirmSaveFilterPreset"
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="filterPresetDialog.show = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat"
            :disabled="!filterPresetDialog.name.trim()"
            @click="confirmSaveFilterPreset">
            Сохранить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Error Dialog -->
    <v-dialog v-model="errorDialog.show" max-width="480">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6 d-flex align-center gap-2">
          <v-icon icon="mdi-alert-circle-outline" color="error" />
          Ошибка
        </v-card-title>
        <v-card-text class="px-6">
          <p class="mb-2">{{ errorDialog.message }}</p>
          <div v-if="errorDialog.code" class="text-caption text-medium-emphasis">Код: {{ errorDialog.code }}</div>
          <div v-if="errorDialog.correlationId" class="text-caption text-medium-emphasis">ID: {{ errorDialog.correlationId }}</div>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-btn size="small" variant="tonal" prepend-icon="mdi-content-copy"
            @click="copyError">Скопировать</v-btn>
          <v-spacer />
          <v-btn variant="text" @click="errorDialog.show = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="snack.color === 'error' ? -1 : 3000" location="bottom right">
      {{ snack.text }}
      <template #actions>
        <v-btn v-if="snack.color === 'error'" variant="text" @click="snack.show = false">Закрыть</v-btn>
      </template>
    </v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'
import ColumnHeaderMenu from '@/components/ColumnHeaderMenu.vue'
import VehicleImportDialog from '@/components/vehicles/VehicleImportDialog.vue'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'

// ─────────────── Types ───────────────

interface OrgItem {
  id: number
  name: string
}

interface VehicleListItem {
  id: number
  owner_org_id: number
  owner_org_name?: string
  assigned_org_id?: number | null
  assigned_org_name?: string | null
  assigned_text?: string | null
  brand?: string | null
  model?: string | null
  color?: string | null
  plate: string
  vin?: string | null
  type?: string | null
  state?: string | null
  fuel_type?: string | null
  current_odometer_km?: number | null
  next_to_km?: number | null
  insurance_until?: string | null
  created_at: string
  updated_at: string
  props?: Record<string, string>
}

interface VehicleListResponse {
  items: VehicleListItem[]
  total: number
}

interface FilterPreset {
  name: string
  states: string[]
  types: string[]
  fuelTypes: string[]
  ownerOrgIds: number[]
  assignedOrgIds: number[]
  search: string
}

// ─────────────── Stores / Composables ───────────────

const router = useRouter()
const authStore = useAuthStore()
const userId = localStorage.getItem('user_id') || 'anon'

// Column config
const allColumns: ColumnDef[] = [
  { key: 'plate',              title: 'Гос. №',         width: 120, group: 'core' },
  { key: 'brand_model',        title: 'Марка/Модель',    width: 200, group: 'core' },
  { key: 'vin',                title: 'VIN',             width: 160, group: 'all'  },
  { key: 'type_label',         title: 'Тип',             width: 140, group: 'core' },
  { key: 'state_label',        title: 'Состояние',       width: 130, group: 'core' },
  { key: 'owner_org_name',     title: 'Владелец',        width: 180, group: 'core' },
  { key: 'assigned_label',     title: 'Эксплуатант',     width: 180, group: 'core' },
  { key: 'insurance_until',    title: 'ОСАГО до',        width: 120, group: 'core' },
  { key: 'current_odometer_km',title: 'Пробег км',       width: 110, group: 'core' },
  { key: 'next_to_km',         title: 'След. ТО км',     width: 110, group: 'all'  },
  { key: 'fuel_type',          title: 'Топливо',         width: 100, group: 'all'  },
]

const cfg = useColumnConfig(`vehicles_list_u${userId}`, allColumns)

// ─────────────── Lookup Maps ───────────────

const TYPE_LABEL: Record<string, string> = {
  car_light:   'Легковой',
  minivan:     'Минивэн',
  truck_van:   'Фургон',
  truck_board: 'Грузовой',
  truck_tank:  'Цистерна',
  truck_metal: 'Металловоз',
  bus:         'Автобус',
  special:     'Спецтехника',
  snowmobile:  'Снегоход',
  boat:        'Лодка',
  boat_motor:  'Лодка (мотор)',
  quadbike:    'Квадроцикл',
  trailer:     'Прицеп',
  other:       'Другой',
}

const STATE_LABEL: Record<string, string> = {
  working:      'Рабочее',
  broken:       'Неисправно',
  in_repair:    'В ремонте',
  needs_repair: 'Требует ремонта',
  destroyed:    'Уничтожено',
  utilized:     'Утилизировано',
}

const FUEL_TYPE_LABEL: Record<string, string> = {
  petrol:  'Бензин',
  diesel:  'Дизель',
  gas:     'Газ',
  hybrid:  'Гибрид',
  electric:'Электро',
  other:   'Другое',
}

const TYPE_COLOR: Record<string, string> = {
  car_light: 'blue', minivan: 'cyan', truck_van: 'indigo',
  truck_board: 'brown', truck_tank: 'teal', bus: 'purple',
  special: 'orange', other: 'grey',
}

const STATE_COLOR: Record<string, string> = {
  working: 'success', broken: 'error', in_repair: 'warning',
  needs_repair: 'orange', destroyed: 'grey', utilized: 'grey',
}

const typeOptions = Object.entries(TYPE_LABEL).map(([value, label]) => ({ value, label }))
const stateOptions = Object.entries(STATE_LABEL).map(([value, label]) => ({ value, label }))
const fuelTypeOptions = Object.entries(FUEL_TYPE_LABEL).map(([value, label]) => ({ value, label }))

function typeLabel(t?: string | null) { return t ? (TYPE_LABEL[t] ?? t) : '—' }
function typeColor(t?: string | null) { return TYPE_COLOR[t ?? ''] ?? 'grey' }
function stateLabel(s?: string | null) { return s ? (STATE_LABEL[s] ?? s) : '—' }
function stateColor(s?: string | null) { return STATE_COLOR[s ?? ''] ?? 'grey' }
function fuelTypeLabel(f?: string | null) { return f ? (FUEL_TYPE_LABEL[f] ?? f) : '—' }

// ─────────────── Data ───────────────

const vehicles = ref<VehicleListItem[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const itemsPerPage = ref(25)
const sortBy = ref<string | null>(null)
const sortDesc = ref(false)
const orgsList = ref<OrgItem[]>([])
const selectedVehicles = ref<VehicleListItem[]>([])
const expandedRows = ref<VehicleListItem[]>([])

// ─────────────── Filters ───────────────

const filterStates = ref<string[]>([])
const filterTypes = ref<string[]>([])
const filterFuelTypes = ref<string[]>([])
const filterOwnerOrgIds = ref<number[]>([])
const filterAssignedOrgIds = ref<number[]>([])
const filterSearch = ref('')

const activeFiltersCount = computed(() => {
  let cnt = 0
  if (filterStates.value.length) cnt++
  if (filterTypes.value.length) cnt++
  if (filterFuelTypes.value.length) cnt++
  if (filterOwnerOrgIds.value.length) cnt++
  if (filterAssignedOrgIds.value.length) cnt++
  if (filterSearch.value.trim()) cnt++
  return cnt
})

function clearAllFilters() {
  filterStates.value = []
  filterTypes.value = []
  filterFuelTypes.value = []
  filterOwnerOrgIds.value = []
  filterAssignedOrgIds.value = []
  filterSearch.value = ''
  cfg.clearAllFilters()
}

// ─────────────── Filter presets ───────────────

const PRESETS_KEY = `vehicles_list_presets_u${userId}`

const savedFilterPresets = ref<FilterPreset[]>([])

function loadSavedPresets() {
  try {
    const raw = localStorage.getItem(PRESETS_KEY)
    if (raw) savedFilterPresets.value = JSON.parse(raw)
  } catch {}
}

const filterPresetDialog = reactive({ show: false, name: '' })

function saveFilterPreset() {
  filterPresetDialog.name = ''
  filterPresetDialog.show = true
}

function confirmSaveFilterPreset() {
  const presetName = filterPresetDialog.name.trim()
  if (!presetName) return
  const newPreset: FilterPreset = {
    name: presetName,
    states: [...filterStates.value],
    types: [...filterTypes.value],
    fuelTypes: [...filterFuelTypes.value],
    ownerOrgIds: [...filterOwnerOrgIds.value],
    assignedOrgIds: [...filterAssignedOrgIds.value],
    search: filterSearch.value,
  }
  const existing = savedFilterPresets.value.filter(p => p.name !== presetName)
  savedFilterPresets.value = [...existing, newPreset]
  try { localStorage.setItem(PRESETS_KEY, JSON.stringify(savedFilterPresets.value)) } catch {}
  filterPresetDialog.show = false
}

function applyFilterPreset(preset: FilterPreset) {
  filterStates.value = preset.states ?? []
  filterTypes.value = preset.types ?? []
  filterFuelTypes.value = preset.fuelTypes ?? []
  filterOwnerOrgIds.value = preset.ownerOrgIds ?? []
  filterAssignedOrgIds.value = preset.assignedOrgIds ?? []
  filterSearch.value = preset.search ?? ''
}

function removeFilterPreset(name: string) {
  savedFilterPresets.value = savedFilterPresets.value.filter(p => p.name !== name)
  try { localStorage.setItem(PRESETS_KEY, JSON.stringify(savedFilterPresets.value)) } catch {}
}

// ─────────────── Sort ───────────────

function getSortBy(key: string): 'asc' | 'desc' | null {
  if (sortBy.value !== key) return null
  return sortDesc.value ? 'desc' : 'asc'
}

function applySort(key: string, dir: 'asc' | 'desc' | null) {
  if (dir === null) { sortBy.value = null; sortDesc.value = false }
  else { sortBy.value = key; sortDesc.value = dir === 'desc' }
}

// ─────────────── Column picker ───────────────

const showColumnPicker = ref(false)

// ─────────────── Data loading ───────────────

async function loadVehicles() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.set('limit', String(itemsPerPage.value))
    params.set('offset', String((page.value - 1) * itemsPerPage.value))
    filterStates.value.forEach(s => params.append('state', s))
    filterTypes.value.forEach(t => params.append('type', t))
    filterFuelTypes.value.forEach(f => params.append('fuel_type', f))
    filterOwnerOrgIds.value.forEach(id => params.append('owner_org_id', String(id)))
    filterAssignedOrgIds.value.forEach(id => params.append('assigned_org_id', String(id)))
    if (filterSearch.value.trim()) params.set('q', filterSearch.value.trim())
    if (sortBy.value) { params.set('sort_by', sortBy.value); params.set('sort_desc', String(sortDesc.value)) }

    const data = await apiFetch<VehicleListResponse>(`/vehicles?${params.toString()}`)
    vehicles.value = data.items ?? []
    total.value = data.total ?? 0
  } catch (err: any) {
    showError(err)
  } finally {
    loading.value = false
  }
}

async function loadOrgs() {
  try {
    const data = await apiFetch<{ items: OrgItem[] }>('/organizations/?limit=500')
    orgsList.value = data.items ?? []
  } catch {}
}

function onTableOptions(opts: { page: number; itemsPerPage: number; sortBy: any[] }) {
  page.value = opts.page
  itemsPerPage.value = opts.itemsPerPage
  if (opts.sortBy?.length) {
    sortBy.value = opts.sortBy[0].key
    sortDesc.value = opts.sortBy[0].order === 'desc'
  } else {
    sortBy.value = null
    sortDesc.value = false
  }
}

function onRowClick(_event: Event, row: { item: VehicleListItem }) {
  router.push(`/property/vehicles/${row.item.id}`)
}

// ─────────────── Create dialog ───────────────

const createDialog = reactive({
  show: false,
  loading: false,
  plate: '',
  brand: '',
  model: '',
  owner_org_id: null as number | null,
  type: null as string | null,
  state: 'working' as string,
})

function resetCreateDialog() {
  createDialog.show = false
  createDialog.loading = false
  createDialog.plate = ''
  createDialog.brand = ''
  createDialog.model = ''
  createDialog.owner_org_id = null
  createDialog.type = null
  createDialog.state = 'working'
}

async function doCreate() {
  if (!createDialog.plate || !createDialog.owner_org_id) return
  createDialog.loading = true
  try {
    const created = await apiFetch<{ id: number }>('/vehicles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        plate: createDialog.plate,
        brand: createDialog.brand || null,
        model: createDialog.model || null,
        owner_org_id: createDialog.owner_org_id,
        type: createDialog.type || null,
        state: createDialog.state,
      }),
    })
    resetCreateDialog()
    router.push(`/property/vehicles/${created.id}`)
  } catch (err: any) {
    createDialog.loading = false
    showError(err)
  }
}

// ─────────────── Import reload ───────────────

const importDialogShow = ref(false)

function onImported() {
  loadVehicles()
}

// ─────────────── Date helpers ───────────────

function formatDate(d?: string | null): string {
  if (!d) return '—'
  try {
    return new Date(d).toLocaleDateString('ru-RU')
  } catch {
    return d
  }
}

function isInsuranceExpiring(item: VehicleListItem): boolean {
  if (!item.insurance_until) return false
  const diff = new Date(item.insurance_until).getTime() - Date.now()
  return diff < 30 * 24 * 3600 * 1000
}

function insuranceClass(item: VehicleListItem): string {
  if (!item.insurance_until) return 'text-medium-emphasis'
  const diff = new Date(item.insurance_until).getTime() - Date.now()
  if (diff < 0) return 'text-error font-weight-bold'
  if (diff < 30 * 24 * 3600 * 1000) return 'text-warning font-weight-medium'
  return ''
}

function nextToClass(item: VehicleListItem): string {
  if (item.next_to_km == null || item.current_odometer_km == null) return ''
  const remaining = item.next_to_km - item.current_odometer_km
  if (remaining < 0) return 'text-error font-weight-bold'
  if (remaining < 1000) return 'text-warning'
  return ''
}

// ─────────────── Error handling ───────────────

const errorDialog = reactive({ show: false, message: '', code: '', correlationId: '' })

function showError(err: any) {
  const payload = err?.payload ?? err?.detail ?? err
  const message = payload?.message ?? payload?.detail ?? String(err)
  const code = payload?.code ?? ''
  const correlationId = payload?.correlation_id ?? ''
  errorDialog.message = message
  errorDialog.code = code
  errorDialog.correlationId = correlationId
  errorDialog.show = true
}

function copyError() {
  const text = [
    errorDialog.message,
    errorDialog.code ? `Код: ${errorDialog.code}` : '',
    errorDialog.correlationId ? `ID: ${errorDialog.correlationId}` : '',
  ].filter(Boolean).join('\n')
  navigator.clipboard.writeText(text).catch(() => {})
}

// ─────────────── Snackbar ───────────────

const snack = reactive({ show: false, text: '', color: 'success' })

function showSnack(text: string, color = 'success') {
  snack.text = text
  snack.color = color
  snack.show = true
}

// ─────────────── Watchers ───────────────

watch(
  [filterStates, filterTypes, filterFuelTypes, filterOwnerOrgIds, filterAssignedOrgIds, filterSearch, sortBy, sortDesc],
  () => {
    page.value = 1
    loadVehicles()
  },
  { deep: true }
)

watch([page, itemsPerPage], () => { loadVehicles() })

// ─────────────── Lifecycle ───────────────

onMounted(() => {
  loadSavedPresets()
  loadOrgs()
  loadVehicles()
})

// Expose showSnack for import dialog
defineExpose({ showSnack })
</script>

<style scoped>
.vehicles-clickable :deep(tbody tr) {
  cursor: pointer;
}
</style>
