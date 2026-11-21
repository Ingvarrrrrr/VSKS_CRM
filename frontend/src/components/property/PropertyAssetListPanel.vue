<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center justify-space-between flex-wrap mb-4 gap-2">
      <div>
        <h1 class="text-h5 font-weight-bold">{{ title }}</h1>
        <p class="text-caption text-medium-emphasis mb-0">
          Учёт, ответственные лица, состояние и привязка к организациям
        </p>
      </div>
      <div class="d-flex align-center gap-2">
        <v-btn
          color="primary"
          prepend-icon="mdi-plus"
          size="small"
          @click="openCreate"
        >
          Добавить
        </v-btn>
      </div>
    </div>

    <!-- Filters row -->
    <v-card class="mb-4 pa-4" variant="outlined">
      <v-row dense align="center">
        <v-col cols="12" sm="4" md="3">
          <v-text-field
            v-model="searchQuery"
            prepend-inner-icon="mdi-magnify"
            placeholder="Поиск по названию, номеру..."
            variant="outlined"
            density="compact"
            hide-details
            clearable
            @update:model-value="onFilterChange"
          />
        </v-col>
        <v-col cols="12" sm="4" md="3">
          <v-select
            v-model="selectedOwnerOrg"
            :items="orgsList"
            item-title="name"
            item-value="id"
            label="Организация-собственник"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            @update:model-value="onFilterChange"
          />
        </v-col>
        <v-col cols="12" sm="4" md="3">
          <v-select
            v-model="selectedState"
            :items="stateOptions"
            item-title="label"
            item-value="value"
            label="Состояние"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            @update:model-value="onFilterChange"
          />
        </v-col>
        <v-col cols="12" sm="12" md="3" class="d-flex justify-end">
          <v-btn
            variant="text"
            size="small"
            prepend-icon="mdi-filter-remove"
            @click="clearFilters"
          >
            Сбросить
          </v-btn>
        </v-col>
      </v-row>
    </v-card>

    <!-- Table -->
    <v-card variant="outlined">
      <v-data-table-server
        :headers="headers"
        :items="items"
        :items-length="total"
        :loading="loading"
        v-model:page="page"
        v-model:items-per-page="itemsPerPage"
        density="compact"
        @update:options="onOptionsChange"
        hover
      >
        <template #item.brand="{ item }">
          <div class="font-weight-medium text-body-2">
            {{ item.brand || '—' }}
          </div>
          <div v-if="item.model" class="text-caption text-medium-emphasis">
            {{ item.model }}
          </div>
        </template>

        <template #item.plate="{ item }">
          <span class="font-mono text-caption">{{ item.plate || '—' }}</span>
        </template>

        <template #item.vin="{ item }">
          <span class="font-mono text-caption">{{ item.vin || '—' }}</span>
        </template>

        <template #item.state="{ item }">
          <v-chip size="x-small" :color="stateColor(item.state)" variant="tonal">
            {{ stateLabel(item.state) }}
          </v-chip>
        </template>

        <template #item.owner_org_name="{ item }">
          <div class="text-body-2">{{ item.owner_org_name || '—' }}</div>
          <div v-if="item.assigned_org_name" class="text-caption text-medium-emphasis">
            Экспл: {{ item.assigned_org_name }}
          </div>
        </template>

        <template #item.responsible_name="{ item }">
          <div class="text-body-2">{{ item.responsible_name || '—' }}</div>
          <div v-if="item.assigned_text" class="text-caption text-medium-emphasis">
            {{ item.assigned_text }}
          </div>
        </template>

        <template #item.location_city="{ item }">
          <div class="text-body-2">{{ item.location_city || '—' }}</div>
          <div v-if="item.location_address" class="text-caption text-medium-emphasis">
            {{ item.location_address }}
          </div>
        </template>

        <template #item.note="{ item }">
          <span class="text-caption text-medium-emphasis">
            {{ item.props?.note || '—' }}
          </span>
        </template>

        <template #item.actions="{ item }">
          <div class="d-flex align-center justify-end">
            <v-tooltip text="Редактировать" location="top">
              <template #activator="{ props: tip }">
                <v-btn
                  v-bind="tip"
                  icon="mdi-pencil-outline"
                  size="x-small"
                  variant="text"
                  @click="openEdit(item)"
                />
              </template>
            </v-tooltip>
            <v-tooltip text="Удалить" location="top">
              <template #activator="{ props: tip }">
                <v-btn
                  v-bind="tip"
                  icon="mdi-delete-outline"
                  size="x-small"
                  variant="text"
                  color="error"
                  @click="confirmDelete(item)"
                />
              </template>
            </v-tooltip>
          </div>
        </template>

        <template #no-data>
          <div class="text-center py-8 text-medium-emphasis">
            <v-icon size="48" class="mb-2" :icon="category === 'equipment' ? 'mdi-toolbox-outline' : 'mdi-package-variant-closed'" />
            <div>Записи не найдены</div>
          </div>
        </template>
      </v-data-table-server>
    </v-card>

    <!-- Create/Edit Dialog -->
    <PropertyAssetDialog
      v-model="dialogShow"
      :category="category"
      :initial-data="editingItem"
      :orgs-list="orgsList"
      :state-options="stateOptions"
      @saved="onAssetSaved"
      @error="onAssetError"
    />

    <!-- Confirm delete dialog -->
    <v-dialog v-model="deleteDialogShow" max-width="400">
      <v-card>
        <v-card-title class="text-h6">Удаление</v-card-title>
        <v-card-text>
          Вы действительно хотите удалить <b>{{ deletingItem?.brand }}</b>?
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialogShow = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiFetch } from '@/api'
import { stateOptions, stateLabel, stateColor } from '@/composables/fleet/vehicle-list/vehicleListLookups'
import type { OrgItem } from '@/composables/fleet/vehicle-list/vehicleListTypes'
import PropertyAssetDialog from './PropertyAssetDialog.vue'
import { useToast } from '@/composables/useToast'

const props = defineProps<{
  category: 'equipment' | 'other'
  title: string
}>()

const toast = useToast()

const headers = [
  { title: 'Наименование / Модель', key: 'brand', sortable: false },
  { title: 'Инв. №', key: 'plate', sortable: false, width: '130px' },
  { title: 'Серийный №', key: 'vin', sortable: false, width: '130px' },
  { title: 'Состояние', key: 'state', sortable: false, width: '130px' },
  { title: 'Организация', key: 'owner_org_name', sortable: false },
  { title: 'Ответственный', key: 'responsible_name', sortable: false },
  { title: 'Местонахождение', key: 'location_city', sortable: false },
  { title: 'Примечание', key: 'note', sortable: false },
  { title: '', key: 'actions', sortable: false, width: '80px', align: 'end' as const },
]

const items = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const itemsPerPage = ref(25)

const searchQuery = ref('')
const selectedOwnerOrg = ref<number | null>(null)
const selectedState = ref<string | null>(null)
const orgsList = ref<OrgItem[]>([])

const dialogShow = ref(false)
const editingItem = ref<any | null>(null)

const deleteDialogShow = ref(false)
const deletingItem = ref<any | null>(null)
const deleting = ref(false)

async function loadOrgs() {
  try {
    const data = await apiFetch<OrgItem[] | { items: OrgItem[] }>('/auth/my-orgs')
    orgsList.value = Array.isArray(data) ? data : (data?.items ?? [])
  } catch (e) {
    orgsList.value = []
  }
}

async function loadData() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.set('type', props.category)
    params.set('limit', String(itemsPerPage.value))
    params.set('offset', String((page.value - 1) * itemsPerPage.value))
    if (searchQuery.value) params.set('q', searchQuery.value.trim())
    if (selectedOwnerOrg.value) params.set('owner_org_id', String(selectedOwnerOrg.value))
    if (selectedState.value) params.set('state', selectedState.value)

    const resp = await apiFetch<{ items: any[]; total: number }>(`/vehicles?${params.toString()}`)
    items.value = resp.items || []
    total.value = resp.total || 0
  } catch (err: any) {
    toast.addToast('Ошибка загрузки данных', 'error')
  } finally {
    loading.value = false
  }
}

function onOptionsChange(opts: { page: number; itemsPerPage: number }) {
  page.value = opts.page
  itemsPerPage.value = opts.itemsPerPage
  loadData()
}

function onFilterChange() {
  page.value = 1
  loadData()
}

function clearFilters() {
  searchQuery.value = ''
  selectedOwnerOrg.value = null
  selectedState.value = null
  page.value = 1
  loadData()
}

function openCreate() {
  editingItem.value = null
  dialogShow.value = true
}

function openEdit(item: any) {
  editingItem.value = { ...item }
  dialogShow.value = true
}

function confirmDelete(item: any) {
  deletingItem.value = item
  deleteDialogShow.value = true
}

async function doDelete() {
  if (!deletingItem.value) return
  deleting.value = true
  try {
    await apiFetch(`/vehicles/${deletingItem.value.id}`, { method: 'DELETE' })
    toast.addToast('Запись удалена', 'success')
    deleteDialogShow.value = false
    loadData()
  } catch (err: any) {
    toast.addToast(err?.message || 'Ошибка удаления', 'error')
  } finally {
    deleting.value = false
  }
}

function onAssetSaved() {
  toast.addToast('Успешно сохранено', 'success')
  loadData()
}

function onAssetError(err: any) {
  toast.addToast(err?.message || 'Ошибка сохранения', 'error')
}

onMounted(async () => {
  await loadOrgs()
  await loadData()
})
</script>
