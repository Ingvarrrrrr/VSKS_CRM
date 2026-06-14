<template>
  <v-container fluid class="pa-4">
    <div class="text-h5 font-weight-bold mb-4">Импорт платёжных реестров</div>

    <!-- Upload card -->
    <v-card class="mb-4" variant="outlined">
      <v-card-title class="text-body-1 font-weight-medium pa-4 pb-2">
        <v-icon icon="mdi-upload" class="mr-2" />Загрузить выписку
      </v-card-title>
      <v-card-text>
        <FileDropZone
          v-model="file"
          accept=".xlsx,.xls"
          hint="Excel-файл банковской выписки (.xlsx, .xls)"
        />
        <v-progress-linear v-if="uploading" indeterminate color="primary" class="mt-3" />
        <div class="mt-3 d-flex justify-end">
          <v-btn
            color="primary"
            :disabled="!file || uploading"
            :loading="uploading"
            prepend-icon="mdi-bank-transfer"
            @click="uploadFile"
          >
            Импортировать
          </v-btn>
        </div>
      </v-card-text>
    </v-card>

    <!-- Journal table -->
    <v-card variant="outlined">
      <v-card-title class="text-body-1 font-weight-medium pa-4 pb-2 d-flex align-center">
        <v-icon icon="mdi-history" class="mr-2" />Журнал прогонов
        <v-spacer />
        <v-btn-toggle
          v-if="!mobile"
          v-model="viewMode"
          mandatory
          density="compact"
          variant="outlined"
          divided
          class="mr-2"
        >
          <v-btn value="table" size="small" icon="mdi-table" />
          <v-btn value="cards" size="small" icon="mdi-view-grid" />
        </v-btn-toggle>
        <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" @click="showColumnPicker = true">Колонки</v-btn>
      </v-card-title>

      <!-- Table view -->
      <template v-if="effectiveView === 'table'">
        <v-data-table
          v-resizable-columns="'payment-import'"
          :headers="visibleHeaders"
          :items="imports"
          :loading="loadingList"
          density="compact"
          hover
          no-data-text="Прогонов ещё нет"
        >
          <!-- Дата -->
          <template #item.uploaded_at="{ item }">
            {{ formatDateTime(item.uploaded_at) }}
          </template>

          <!-- Строк -->
          <template #item.rows_total="{ item }">
            <span class="text-mono">{{ item.rows_total ?? '—' }}</span>
          </template>

          <!-- Импортировано -->
          <template #item.rows_imported="{ item }">
            <span class="text-mono text-success">{{ item.rows_imported ?? '—' }}</span>
          </template>

          <!-- Сматчено -->
          <template #item.rows_matched="{ item }">
            <span class="text-mono text-info">{{ item.rows_matched ?? '—' }}</span>
          </template>

          <!-- Не сматчено -->
          <template #item.rows_unmatched="{ item }">
            <span class="text-mono" :class="item.rows_unmatched > 0 ? 'text-warning' : ''">
              {{ item.rows_unmatched ?? '—' }}
            </span>
          </template>

          <!-- Дубликаты -->
          <template #item.rows_dup="{ item }">
            <span class="text-mono" :class="item.rows_dup > 0 ? 'text-secondary' : ''">
              {{ item.rows_dup ?? '—' }}
            </span>
          </template>

          <!-- Статус -->
          <template #item.status="{ item }">
            <v-chip
              size="x-small"
              :color="statusColor(item.status)"
              variant="tonal"
            >
              {{ statusLabel(item.status) }}
            </v-chip>
          </template>

          <!-- Действия -->
          <template #item.actions="{ item }">
            <div class="d-flex gap-1">
              <v-btn
                size="x-small"
                variant="text"
                color="primary"
                icon="mdi-open-in-app"
                title="Открыть детали"
                @click="openDetails(item.id)"
              />
              <v-menu>
                <template #activator="{ props: menuProps }">
                  <v-btn icon size="small" variant="text" color="primary"
                         v-bind="menuProps"
                         :loading="rematchingId === item.id"
                         title="Перематчить">
                    <v-icon>mdi-refresh</v-icon>
                  </v-btn>
                </template>
                <v-list density="compact">
                  <v-list-item
                    prepend-icon="mdi-refresh"
                    title="Перематчить unmatched"
                    @click="rematchImport(item, false, true)"
                  />
                  <v-list-item
                    prepend-icon="mdi-restart"
                    title="Перепарсить и пересмотреть все"
                    @click="rematchImport(item, true, false)"
                  />
                </v-list>
              </v-menu>
              <v-btn
                size="x-small"
                variant="text"
                color="error"
                icon="mdi-delete-outline"
                title="Удалить прогон"
                @click="deleteImport(item.id)"
              />
            </div>
          </template>
        </v-data-table>
      </template>

      <!-- Cards view -->
      <template v-else>
        <v-card-text>
          <v-progress-linear v-if="loadingList" indeterminate color="primary" class="mb-3" />
          <div v-if="!loadingList && pagedImports.length === 0" class="text-center py-8 text-medium-emphasis">
            <v-icon icon="mdi-history" size="40" color="grey-lighten-2" class="d-block mx-auto mb-2" />
            Прогонов ещё нет
          </div>
          <v-row dense>
            <v-col v-for="item in pagedImports" :key="item.id" cols="12" sm="6" lg="4">
              <v-card variant="outlined" class="h-100 d-flex flex-column" hover @click="openDetails(item.id)">
                <v-card-item class="pb-1">
                  <v-card-title class="text-body-2 font-weight-bold" style="overflow-wrap:anywhere">
                    {{ item.file_name || ('Прогон #' + item.id) }}
                  </v-card-title>
                  <template #append>
                    <v-chip size="x-small" :color="statusColor(item.status)" variant="tonal">
                      {{ statusLabel(item.status) }}
                    </v-chip>
                  </template>
                </v-card-item>
                <v-card-text class="py-1 flex-grow-1">
                  <div class="text-caption text-medium-emphasis mb-1">
                    {{ formatDateTime(item.uploaded_at) }}
                  </div>
                  <div class="d-flex flex-wrap gap-x-4 gap-y-1 text-caption mt-1">
                    <span>Строк: <strong class="text-mono">{{ item.rows_total ?? '—' }}</strong></span>
                    <span>Импорт.: <strong class="text-mono text-success">{{ item.rows_imported ?? '—' }}</strong></span>
                    <span>Сматч.: <strong class="text-mono text-info">{{ item.rows_matched ?? '—' }}</strong></span>
                    <span :class="item.rows_unmatched > 0 ? 'text-warning' : ''">
                      Не сматч.: <strong class="text-mono">{{ item.rows_unmatched ?? '—' }}</strong>
                    </span>
                    <span :class="item.rows_dup > 0 ? 'text-secondary' : ''">
                      Дубл.: <strong class="text-mono">{{ item.rows_dup ?? '—' }}</strong>
                    </span>
                  </div>
                </v-card-text>
                <v-divider />
                <v-card-actions class="py-1" @click.stop>
                  <v-spacer />
                  <v-btn size="x-small" variant="text" color="primary" icon="mdi-open-in-app" title="Открыть детали" @click.stop="openDetails(item.id)" />
                  <v-menu>
                    <template #activator="{ props: menuProps }">
                      <v-btn icon size="small" variant="text" color="primary"
                             v-bind="menuProps"
                             :loading="rematchingId === item.id"
                             title="Перематчить">
                        <v-icon>mdi-refresh</v-icon>
                      </v-btn>
                    </template>
                    <v-list density="compact">
                      <v-list-item prepend-icon="mdi-refresh" title="Перематчить unmatched" @click="rematchImport(item, false, true)" />
                      <v-list-item prepend-icon="mdi-restart" title="Перепарсить и пересмотреть все" @click="rematchImport(item, true, false)" />
                    </v-list>
                  </v-menu>
                  <v-btn size="x-small" variant="text" color="error" icon="mdi-delete-outline" title="Удалить прогон" @click.stop="deleteImport(item.id)" />
                </v-card-actions>
              </v-card>
            </v-col>
          </v-row>
          <v-pagination
            v-if="importsTotalPages > 1"
            v-model="importsPage"
            :length="importsTotalPages"
            density="compact"
            total-visible="7"
            class="d-flex justify-center mt-4"
          />
        </v-card-text>
      </template>
    </v-card>

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
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import FileDropZone from '@/components/FileDropZone.vue'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'
import { useCardView } from '@/composables/useCardView'

const router = useRouter()
const { success, error } = useToast()

const file = ref<File | null>(null)
const uploading = ref(false)
const loadingList = ref(false)
const imports = ref<any[]>([])
const rematchingId = ref<number | null>(null)

const allColumns: ColumnDef[] = [
  { title: 'Дата', key: 'uploaded_at', width: 160 },
  { title: 'Файл', key: 'file_name' },
  { title: 'Строк', key: 'rows_total', width: 80, align: 'end' },
  { title: 'Импорт.', key: 'rows_imported', width: 90, align: 'end' },
  { title: 'Сматч.', key: 'rows_matched', width: 90, align: 'end' },
  { title: 'Не сматч.', key: 'rows_unmatched', width: 100, align: 'end' },
  { title: 'Дубл.', key: 'rows_dup', width: 80, align: 'end' },
  { title: 'Статус', key: 'status', width: 110 },
  { title: '', key: 'actions', width: 80, sortable: false },
]

const { state: colState, visibleHeaders, toggleVisible, setPosition, setWidth, reset: resetColumns } = useColumnConfig('payment_imports', allColumns)
const showColumnPicker = ref(false)

const {
  mobile,
  viewMode,
  effectiveView,
  page: importsPage,
  totalPages: importsTotalPages,
  paged: pagedImports,
} = useCardView({
  storageKey: 'payment_imports_view_mode',
  source: () => imports.value,
  pageSize: 24,
})

function formatDateTime(dt: string | null) {
  if (!dt) return '—'
  return new Date(dt).toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    processing: 'Обработка',
    done: 'Завершён',
    error: 'Ошибка',
  }
  return map[status] ?? status
}

function statusColor(status: string) {
  const map: Record<string, string> = {
    processing: 'info',
    done: 'success',
    error: 'error',
  }
  return map[status] ?? 'grey'
}

async function loadImports() {
  loadingList.value = true
  try {
    imports.value = await apiFetch<any[]>('/payments/imports')
  } catch {
    // errors handled globally by apiFetch
  } finally {
    loadingList.value = false
  }
}

async function uploadFile() {
  if (!file.value) return
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file.value)
    const res = await apiFetch<any>('/payments/imports', {
      method: 'POST',
      body: fd,
    })
    success(
      `Импорт завершён: ${res.rows_imported ?? 0} строк, ` +
      `сматчено ${res.rows_matched ?? 0}, ` +
      `дубликатов ${res.rows_dup ?? 0}`
    )
    await loadImports()
    file.value = null
  } catch (e: any) {
    error(`Ошибка импорта: ${e?.detail || e?.message || 'неизвестная ошибка'}`)
  } finally {
    uploading.value = false
  }
}

async function deleteImport(id: number) {
  if (!confirm('Удалить прогон импорта? Все связанные платежи будут отозваны.')) return
  try {
    await apiFetch(`/payments/imports/${id}`, { method: 'DELETE' })
    await loadImports()
  } catch (e: any) {
    error(`Ошибка удаления: ${e?.detail || e?.message || 'неизвестная ошибка'}`)
  }
}

async function rematchImport(item: any, reparse = false, onlyUnmatched = true) {
  rematchingId.value = item.id
  try {
    const params = new URLSearchParams({
      only_unmatched: String(onlyUnmatched),
      reparse: String(reparse),
    })
    const res = await apiFetch<any>(`/payments/imports/${item.id}/rematch?${params}`, { method: 'POST' })
    const label = reparse ? 'Перепарсено и перематчено' : 'Перематчено'
    success(`${label}: ${res.matched_contract ?? 0} контрактов из ${res.total ?? 0}`)
    await loadImports()
  } catch (e: any) {
    error(`Ошибка: ${e?.detail || e?.message}`)
  } finally {
    rematchingId.value = null
  }
}

function openDetails(id: number) {
  router.push({ path: '/payments/registry', query: { import_id: String(id) } })
}

onMounted(loadImports)
</script>
