<template>
  <v-container fluid class="pa-4">
    <div class="d-flex align-center mb-4">
      <v-icon size="28" class="mr-2">mdi-view-dashboard</v-icon>
      <h2 class="text-h5">Дашборды</h2>
      <v-spacer />
      <v-btn color="primary" prepend-icon="mdi-plus" to="/dashboards/new">Новый дашборд</v-btn>
    </div>

    <v-card>
      <v-progress-linear v-if="loading" indeterminate />
      <v-table density="compact" hover v-if="configs.length">
        <thead>
          <tr>
            <th>Название</th>
            <th>Описание</th>
            <th>Дата</th>
            <th style="width: 160px">Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="cfg in configs" :key="cfg.id">
            <td class="font-weight-medium">{{ cfg.name }}</td>
            <td class="text-medium-emphasis text-caption">{{ cfg.description || '—' }}</td>
            <td class="text-caption text-medium-emphasis">{{ formatDate(cfg.created_at) }}</td>
            <td>
              <v-btn
                size="x-small"
                variant="text"
                color="primary"
                icon="mdi-open-in-new"
                :to="`/dashboards/${cfg.id}/edit`"
                title="Открыть"
              />
              <v-btn
                size="x-small"
                variant="text"
                icon="mdi-pencil"
                :to="`/dashboards/${cfg.id}/edit`"
                title="Редактировать"
              />
              <v-btn
                size="x-small"
                variant="text"
                color="error"
                icon="mdi-delete"
                title="Удалить"
                @click="confirmDelete(cfg)"
              />
            </td>
          </tr>
        </tbody>
      </v-table>
      <div v-else-if="!loading" class="text-center text-grey pa-8">
        Нет сохранённых дашбордов. Нажмите «Новый дашборд» чтобы создать.
      </div>
    </v-card>

    <!-- Delete confirm dialog -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title>Удалить дашборд?</v-card-title>
        <v-card-text>«{{ deleteTarget?.name }}» будет удалён без возможности восстановления.</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'

const toast = useToast()
const configs = ref<any[]>([])
const loading = ref(false)
const deleteDialog = ref(false)
const deleteTarget = ref<any>(null)

function formatDate(s: string) {
  if (!s) return '—'
  return new Date(s).toLocaleDateString('ru-RU')
}

function confirmDelete(cfg: any) {
  deleteTarget.value = cfg
  deleteDialog.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  try {
    await apiFetch(`/report-configs/${deleteTarget.value.id}`, { method: 'DELETE' })
    configs.value = configs.value.filter((c) => c.id !== deleteTarget.value.id)
    toast.success('Дашборд удалён')
  } catch (e: any) {
    toast.error('Ошибка удаления: ' + (e?.message || String(e)))
  } finally {
    deleteDialog.value = false
    deleteTarget.value = null
  }
}

onMounted(async () => {
  loading.value = true
  try {
    const result = await apiFetch<any>('/report-configs/?kind=dashboard')
    configs.value = Array.isArray(result) ? result : result.items || []
  } catch (e: any) {
    toast.error('Ошибка загрузки: ' + (e?.message || String(e)))
  } finally {
    loading.value = false
  }
})
</script>
