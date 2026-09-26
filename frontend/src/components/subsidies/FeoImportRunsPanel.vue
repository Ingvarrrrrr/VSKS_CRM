<template>
  <div v-if="subsidyId" class="feo-import-runs-panel mt-4">
    <div class="d-flex align-center mb-2">
      <v-icon icon="mdi-file-upload-outline" size="18" class="mr-2" />
      <span class="text-subtitle-2">Журнал загрузок ФЭО</span>
      <v-btn
        size="x-small" variant="text" icon="mdi-refresh" class="ml-auto"
        :loading="loading" @click="load"
      />
    </div>

    <div v-if="loading && !runs.length" class="d-flex align-center py-3">
      <v-progress-circular indeterminate size="20" width="2" color="primary" class="mr-2" />
      <span class="text-caption text-medium-emphasis">Загрузка журнала…</span>
    </div>

    <v-alert v-else-if="loadError" type="error" variant="tonal" density="compact" class="text-caption">
      {{ loadError }}
    </v-alert>

    <v-alert v-else-if="!runs.length" type="info" variant="tonal" density="compact" class="text-caption">
      Загрузок из Excel по этой субсидии ещё не было
    </v-alert>

    <v-table v-else density="compact" class="feo-import-runs-table">
      <thead>
        <tr>
          <th />
          <th>Файл</th>
          <th>Лист</th>
          <th>Кто</th>
          <th>Когда</th>
          <th class="text-right">Создано</th>
          <th class="text-right">Обновлено</th>
          <th class="text-right">Пропущено</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="run in runs" :key="run.id">
          <tr class="feo-import-run-row" @click="toggle(run.id)">
            <td>
              <v-icon :icon="expanded.has(run.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'" size="18" />
            </td>
            <td>{{ run.filename || '—' }}</td>
            <td>{{ run.sheet_name || '—' }}</td>
            <td>{{ run.user_name || 'неизвестно' }}</td>
            <td>{{ formatDate(run.started_at) }}</td>
            <td class="text-right">{{ run.created_count }}</td>
            <td class="text-right">{{ run.updated_count }}</td>
            <td class="text-right">{{ run.skipped_count }}</td>
          </tr>
          <tr v-if="expanded.has(run.id)">
            <td colspan="8" class="pa-0">
              <div class="pa-3" style="background:rgba(0,0,0,0.02)">
                <div v-if="changesLoading.has(run.id)" class="d-flex align-center py-2">
                  <v-progress-circular indeterminate size="18" width="2" color="primary" class="mr-2" />
                  <span class="text-caption text-medium-emphasis">Загрузка изменений…</span>
                </div>
                <v-alert
                  v-else-if="changesError.get(run.id)"
                  type="error" variant="tonal" density="compact" class="text-caption"
                >
                  {{ changesError.get(run.id) }}
                </v-alert>
                <div v-else-if="!(changesByRun.get(run.id) || []).length" class="text-caption text-medium-emphasis">
                  Этот прогон не создал и не изменил ни одной записи
                </div>
                <div v-else>
                  <div
                    v-for="ch in changesByRun.get(run.id)"
                    :key="ch.id"
                    class="text-caption mb-1"
                  >
                    <v-chip size="x-small" variant="tonal" class="mr-1">
                      {{ ch.entity_type === 'feo_category' ? 'Направление' : 'Позиция' }}
                    </v-chip>
                    <span class="font-weight-medium">{{ ch.entity_name || `#${ch.entity_id}` }}</span>
                    <template v-if="ch.is_created"> — создана</template>
                    <template v-else-if="ch.is_deleted"> — удалена</template>
                    <template v-else>
                      — {{ fieldLabel(ch.field_name) }}:
                      <span class="text-error text-decoration-line-through">{{ ch.old_value ?? '—' }}</span>
                      <v-icon icon="mdi-arrow-right" size="10" class="mx-1" />
                      <span class="text-success">{{ ch.new_value ?? '—' }}</span>
                    </template>
                  </div>
                </div>
              </div>
            </td>
          </tr>
        </template>
      </tbody>
    </v-table>

    <div v-if="total > runs.length" class="d-flex justify-center mt-2">
      <v-btn size="small" variant="text" :loading="loading" @click="loadMore">Показать ещё</v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
// Журнал прогонов импорта ФЭО в карточке субсидии (волна 3, 26.09) — владелец:
// «нужно знать, кто загрузил файл импорта и что он перезаписал». Данные —
// app/routers/feo_import_runs.py (подключён как под-роутер feo_categories.py,
// путь /api/feo-categories/import-runs — НЕ /api/feo-import-runs, см. докстринг
// роутера про запрет трогать routes.py).
import { ref, watch } from 'vue'
import { apiFetch } from '@/api'
import { feoHistoryFieldLabel } from '@/constants/feoHistoryFieldLabels'

const props = defineProps<{ subsidyId: number | null | undefined }>()

interface RunOut {
  id: number
  subsidy_id: number | null
  user_id: number | null
  user_name: string | null
  filename: string | null
  sheet_name: string | null
  started_at: string | null
  finished_at: string | null
  created_count: number
  updated_count: number
  skipped_count: number
  comments_created: number
  warnings_count: number
}

interface RunChangeOut {
  id: number
  entity_type: string
  entity_id: number
  entity_name: string | null
  field_name: string
  old_value: string | null
  new_value: string | null
  changed_at: string | null
  is_created: boolean
  is_deleted: boolean
}

const PAGE_SIZE = 10

const runs = ref<RunOut[]>([])
const total = ref(0)
const loading = ref(false)
const loadError = ref<string | null>(null)
const expanded = ref<Set<number>>(new Set())
const changesByRun = ref<Map<number, RunChangeOut[]>>(new Map())
const changesLoading = ref<Set<number>>(new Set())
const changesError = ref<Map<number, string>>(new Map())

function fieldLabel(f: string): string {
  return feoHistoryFieldLabel(f)
}

function formatDate(s: string | null): string {
  if (!s) return '—'
  try {
    return new Date(s).toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return s
  }
}

async function load() {
  if (!props.subsidyId) { runs.value = []; total.value = 0; return }
  loading.value = true
  loadError.value = null
  try {
    const res = await apiFetch<{ items: RunOut[]; total: number }>(
      `/feo-categories/import-runs?subsidy_id=${props.subsidyId}&limit=${PAGE_SIZE}&offset=0`,
    )
    runs.value = res.items
    total.value = res.total
    expanded.value = new Set()
    changesByRun.value = new Map()
  } catch (e: any) {
    loadError.value = e?.payload?.message || e?.detail || e?.message || 'Не удалось загрузить журнал загрузок'
    runs.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (!props.subsidyId) return
  loading.value = true
  try {
    const res = await apiFetch<{ items: RunOut[]; total: number }>(
      `/feo-categories/import-runs?subsidy_id=${props.subsidyId}&limit=${PAGE_SIZE}&offset=${runs.value.length}`,
    )
    runs.value = [...runs.value, ...res.items]
    total.value = res.total
  } catch (e: any) {
    loadError.value = e?.payload?.message || e?.detail || e?.message || 'Не удалось загрузить журнал загрузок'
  } finally {
    loading.value = false
  }
}

async function toggle(runId: number) {
  const next = new Set(expanded.value)
  if (next.has(runId)) {
    next.delete(runId)
    expanded.value = next
    return
  }
  next.add(runId)
  expanded.value = next
  if (changesByRun.value.has(runId)) return

  const loadingSet = new Set(changesLoading.value)
  loadingSet.add(runId)
  changesLoading.value = loadingSet
  try {
    const rows = await apiFetch<RunChangeOut[]>(`/feo-categories/import-runs/${runId}/changes`)
    const next2 = new Map(changesByRun.value)
    next2.set(runId, rows)
    changesByRun.value = next2
  } catch (e: any) {
    const errMap = new Map(changesError.value)
    errMap.set(runId, e?.payload?.message || e?.detail || e?.message || 'Не удалось загрузить изменения прогона')
    changesError.value = errMap
  } finally {
    const loadingSet2 = new Set(changesLoading.value)
    loadingSet2.delete(runId)
    changesLoading.value = loadingSet2
  }
}

watch(() => props.subsidyId, load, { immediate: true })
</script>

<style scoped>
.feo-import-run-row {
  cursor: pointer;
}
.feo-import-run-row:hover {
  background: rgba(0, 0, 0, 0.03);
}
</style>
