<template>
  <div>
    <div class="d-flex align-center mb-4 ga-3 flex-wrap">
      <v-select
        v-model="reportDept"
        :items="departments"
        label="Отдел"
        variant="outlined" density="compact" clearable
        style="max-width:280px"
        placeholder="Все отделы"
      />
      <v-select
        v-model="reportWeeks"
        :items="[{title:'1 неделя',value:1},{title:'2 недели',value:2},{title:'4 недели',value:4},{title:'12 недель',value:12}]"
        label="Период"
        variant="outlined" density="compact"
        style="max-width:200px"
      />
      <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-magnify" :loading="reportLoading" @click="loadReport">Сформировать</v-btn>
    </div>

    <div v-if="reportLoading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate color="primary" size="48" />
    </div>

    <template v-else-if="reportData">
      <!-- Summary KPIs -->
      <div class="d-flex ga-3 mb-4 flex-wrap">
        <v-card variant="outlined" class="pa-4 text-center" style="min-width:150px;flex:1">
          <div class="text-h4 font-weight-bold text-success">{{ reportData.summary.total_done }}</div>
          <div class="text-caption text-medium-emphasis">Выполнено</div>
        </v-card>
        <v-card variant="outlined" class="pa-4 text-center" style="min-width:150px;flex:1">
          <div class="text-h4 font-weight-bold text-primary">{{ reportData.summary.total_in_progress }}</div>
          <div class="text-caption text-medium-emphasis">В работе</div>
        </v-card>
        <v-card variant="outlined" class="pa-4 text-center" style="min-width:150px;flex:1">
          <div class="text-h4 font-weight-bold text-warning">{{ reportData.summary.total_todo }}</div>
          <div class="text-caption text-medium-emphasis">Планируется</div>
        </v-card>
        <v-card variant="outlined" class="pa-4 text-center" style="min-width:150px;flex:1">
          <div class="text-h4 font-weight-bold text-error">{{ reportData.summary.total_overdue }}</div>
          <div class="text-caption text-medium-emphasis">Просрочено</div>
        </v-card>
      </div>

      <!-- Per-department breakdown -->
      <v-card v-for="dept in reportData.departments" :key="dept.department" variant="outlined" class="mb-4">
        <v-card-title class="d-flex align-center ga-2 px-4 pt-3 pb-1">
          <v-icon icon="mdi-account-group" size="20" />
          {{ dept.department }}
          <v-spacer />
          <v-chip color="success" size="small" variant="tonal">{{ dept.done_count }} выполнено</v-chip>
          <v-chip color="primary" size="small" variant="tonal">{{ dept.in_progress_count }} в работе</v-chip>
          <v-chip color="warning" size="small" variant="tonal">{{ dept.todo_count }} план</v-chip>
          <v-chip v-if="dept.overdue_count" color="error" size="small" variant="tonal">{{ dept.overdue_count }} просрочено</v-chip>
        </v-card-title>

        <v-card-text class="pa-2">
          <div class="d-flex ga-3" style="overflow-x:auto">
            <div v-for="sec in [{key:'in_progress',label:'В работе',color:'#3B82F6'},{key:'todo',label:'Планируется',color:'#F59E0B'},{key:'done',label:'Выполнено',color:'#22C55E'}]" :key="sec.key" style="min-width:200px;flex:1">
              <div class="text-caption font-weight-medium mb-1" :style="{color:sec.color}">{{ sec.label }} ({{ dept[sec.key].length }})</div>
              <div v-for="t in dept[sec.key].slice(0,5)" :key="t.id" class="report-task-item">
                <div class="d-flex align-center ga-1">
                  <v-chip :color="PRIORITY_COLOR[t.priority]||'grey'" size="x-small" variant="flat" style="min-width:0">{{ PRIORITY_LABEL[t.priority]?.[0] || '?' }}</v-chip>
                  <span class="text-body-2 font-weight-medium text-truncate" style="max-width:160px">{{ t.title }}</span>
                </div>
                <div class="d-flex align-center ga-1 mt-1">
                  <span v-if="t.assigned_user" class="text-caption text-medium-emphasis"><v-icon icon="mdi-account" size="10"/>{{ t.assigned_user }}</span>
                  <v-chip v-if="t.due_date" :color="deadlineColor(t.due_date)" size="x-small" variant="tonal">{{ formatDate(t.due_date.split('T')[0]) }}</v-chip>
                </div>
              </div>
              <div v-if="dept[sec.key].length > 5" class="text-caption text-medium-emphasis mt-1">+ ещё {{ dept[sec.key].length - 5 }}</div>
              <div v-if="dept[sec.key].length === 0" class="text-caption text-medium-emphasis" style="opacity:.5">—</div>
            </div>
          </div>
        </v-card-text>
      </v-card>

      <div v-if="reportData.departments.length === 0" class="text-center py-8 text-medium-emphasis">
        Нет данных. Убедитесь, что сотрудники привязаны к отделам.
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { apiFetch } from '@/api'

defineProps<{
  departments: string[]
}>()

const PRIORITY_LABEL: Record<string, string> = { low: 'Низкий', medium: 'Средний', high: 'Высокий', urgent: 'Срочно' }
const PRIORITY_COLOR: Record<string, string> = { low: 'grey', medium: 'blue', high: 'orange', urgent: 'red' }

const reportDept = ref<string | null>(null)
const reportWeeks = ref(1)
const reportLoading = ref(false)
const reportData = ref<any>(null)

async function loadReport() {
  reportLoading.value = true
  try {
    const params = new URLSearchParams()
    if (reportDept.value) params.set('department', reportDept.value)
    params.set('weeks', String(reportWeeks.value))
    reportData.value = await apiFetch<any>(`/tasks/report/by-department?${params}`)
  } catch (e) { console.error(e); reportData.value = null }
  finally { reportLoading.value = false }
}

function deadlineColor(d: string): string {
  const diff = (new Date(d).getTime() - Date.now()) / 86400000
  if (diff < 0) return 'error'
  if (diff <= 7) return 'warning'
  return 'success'
}

function formatDate(d: string): string {
  if (!d) return ''
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}
</script>

<style scoped>
.report-task-item {
  padding: 6px 8px;
  border-radius: 6px;
  margin-bottom: 4px;
  background: rgba(0,0,0,0.02);
  border: 1px solid rgba(0,0,0,0.05);
}
</style>
