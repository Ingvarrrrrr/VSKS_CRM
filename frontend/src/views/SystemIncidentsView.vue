<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">Системные инциденты</h1>
        <span class="text-body-2 text-medium-emphasis">Лог ошибок бэкенда</span>
      </div>
      <v-spacer />
      <div class="d-flex gap-2">
        <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" @click="showColumnPicker = true">Колонки</v-btn>
        <v-btn color="error" variant="outlined" prepend-icon="mdi-delete-sweep" :loading="clearing" @click="confirmClear">
          Очистить всё
        </v-btn>
      </div>
    </div>

    <!-- Search -->
    <v-text-field
      v-model="search" prepend-inner-icon="mdi-magnify" label="Поиск по сообщению, пути, correlation ID"
      variant="outlined" density="compact" clearable hide-details class="mb-4" style="max-width:500px"
      @update:model-value="debouncedLoad"
    />

    <!-- Table -->
    <v-data-table
        v-resizable-columns="'system-incidents'"
        :headers="visibleHeaders"
        :items="incidents"
        :loading="loading"
        density="comfortable"
        item-value="id"
        :items-per-page="50"
      >
        <template v-slot:item.created_at="{ item }">
          <span class="text-caption">{{ formatDate(item.created_at) }}</span>
        </template>
        <template v-slot:item.method="{ item }">
          <v-chip
            size="x-small"
            :color="item.method === 'GET' ? 'info' : item.method === 'POST' ? 'success' : item.method === 'DELETE' ? 'error' : 'warning'"
            variant="tonal"
          >
            {{ item.method || '—' }}
          </v-chip>
        </template>
        <template v-slot:item.message="{ item }">
          <div class="py-1">
            <div class="text-body-2">{{ item.message }}</div>
            <div v-if="item.path" class="text-caption text-medium-emphasis">{{ item.path }}</div>
          </div>
        </template>
        <template v-slot:item.code="{ item }">
          <v-chip v-if="item.code" size="x-small" color="error" variant="tonal">{{ item.code }}</v-chip>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        <template v-slot:item.actions="{ item }">
          <div class="d-flex gap-1">
            <v-btn icon="mdi-information-outline" size="x-small" variant="text" @click="viewDetail(item)" />
            <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error" @click="deleteIncident(item)" />
          </div>
        </template>
      </v-data-table>

    <!-- Detail dialog -->
    <v-dialog v-model="detailDialog.show" max-width="700" scrollable>
      <v-card v-if="detailDialog.item">
        <v-card-title class="pa-4 d-flex align-center">
          Детали инцидента #{{ detailDialog.item.id }}
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="detailDialog.show = false" />
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-list density="compact">
            <v-list-item title="Время" :subtitle="formatDate(detailDialog.item.created_at)" />
            <v-list-item title="Метод + путь" :subtitle="`${detailDialog.item.method || ''} ${detailDialog.item.path || ''}`" />
            <v-list-item title="Код ошибки" :subtitle="detailDialog.item.code || '—'" />
            <v-list-item title="Correlation ID" :subtitle="detailDialog.item.correlation_id" />
            <v-list-item title="Сообщение" :subtitle="detailDialog.item.message" />
          </v-list>
          <div v-if="detailDialog.item.details" class="mt-2">
            <div class="text-caption text-medium-emphasis mb-1">Детали / Stack trace:</div>
            <pre class="details-pre">{{ detailDialog.item.details }}</pre>
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- Clear confirm -->
    <v-dialog v-model="clearDialog" max-width="340">
      <v-card>
        <v-card-title class="pa-4">Очистить все инциденты?</v-card-title>
        <v-card-text>Это действие нельзя отменить.</v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="clearDialog = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="clearing" @click="doClear">Очистить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack.show" :color="snack.color" timeout="3000">{{ snack.text }}</v-snackbar>

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
import { ref, reactive, onMounted } from 'vue'
import { apiFetch } from '@/api'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'

interface Incident {
  id: number
  message: string
  details?: string
  code?: string
  correlation_id: string
  path?: string
  method?: string
  user_id?: number
  created_at: string
}

const incidents = ref<Incident[]>([])
const loading = ref(false)
const clearing = ref(false)
const search = ref('')
const clearDialog = ref(false)

const detailDialog = reactive({ show: false, item: null as Incident | null })
const snack = reactive({ show: false, text: '', color: 'success' })
const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }

const allColumns: ColumnDef[] = [
  { title: 'Время', key: 'created_at', width: 160 },
  { title: 'Метод', key: 'method', width: 80 },
  { title: 'Сообщение / Путь', key: 'message' },
  { title: 'Код', key: 'code', width: 120 },
  { title: 'Correlation ID', key: 'correlation_id' },
  { title: '', key: 'actions', width: 80, sortable: false },
]

const { state: colState, visibleHeaders, toggleVisible, setPosition, setWidth, reset: resetColumns } = useColumnConfig('system_incidents', allColumns)
const showColumnPicker = ref(false)

function formatDate(iso: string) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
function debouncedLoad() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(loadIncidents, 400)
}

async function loadIncidents() {
  loading.value = true
  try {
    const params = new URLSearchParams({ limit: '200' })
    if (search.value) params.set('search', search.value)
    incidents.value = await apiFetch<Incident[]>(`/system-incidents/?${params}`)
  } catch (e: any) {
    showSnack(e.message || 'Ошибка загрузки', 'error')
  } finally {
    loading.value = false
  }
}

function viewDetail(item: Incident) {
  detailDialog.item = item
  detailDialog.show = true
}

async function deleteIncident(item: Incident) {
  try {
    await apiFetch(`/system-incidents/${item.id}`, { method: 'DELETE' })
    incidents.value = incidents.value.filter(i => i.id !== item.id)
    showSnack('Инцидент удалён')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка', 'error')
  }
}

function confirmClear() { clearDialog.value = true }

async function doClear() {
  clearing.value = true
  try {
    await apiFetch('/system-incidents/', { method: 'DELETE' })
    incidents.value = []
    clearDialog.value = false
    showSnack('Все инциденты удалены')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка', 'error')
  } finally {
    clearing.value = false
  }
}

onMounted(loadIncidents)
</script>

<style scoped>
.details-pre {
  background: var(--crm-surface-alt);
  border-radius: 4px;
  padding: 12px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
}
</style>
