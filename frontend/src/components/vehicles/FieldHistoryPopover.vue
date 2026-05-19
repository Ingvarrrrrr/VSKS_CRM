<template>
  <v-menu :close-on-content-click="false" location="bottom" :offset="[4, 0]">
    <template #activator="{ props: menuProps }">
      <v-icon
        v-bind="menuProps"
        size="16"
        color="grey"
        class="ml-1 cursor-pointer field-history-icon"
        title="История изменений"
        @click="loadHistory"
      >mdi-information-outline</v-icon>
    </template>
    <v-card min-width="400" max-width="600">
      <v-card-title class="text-subtitle-2 pa-3 pb-1">
        История — {{ fieldLabel }}
      </v-card-title>
      <v-divider />
      <v-card-text v-if="loading" class="text-center pa-4">
        <v-progress-circular indeterminate size="24" />
      </v-card-text>
      <v-card-text v-else-if="!history.length" class="text-medium-emphasis text-body-2 pa-3">
        История изменений пуста
      </v-card-text>
      <v-timeline v-else density="compact" side="end" class="pa-3">
        <v-timeline-item
          v-for="h in history"
          :key="h.id"
          dot-color="primary"
          size="small"
        >
          <div class="text-caption text-medium-emphasis">
            {{ formatDate(h.changed_at) }}
            <template v-if="h.changed_by_user_id"> · пользователь #{{ h.changed_by_user_id }}</template>
          </div>
          <div class="text-body-2">
            <span class="text-decoration-line-through text-medium-emphasis">{{ h.old_value ?? '—' }}</span>
            <v-icon size="14" class="mx-1">mdi-arrow-right</v-icon>
            <strong>{{ h.new_value ?? '—' }}</strong>
          </div>
          <div v-if="h.comment" class="text-caption text-medium-emphasis mt-1">
            «{{ h.comment }}»
          </div>
        </v-timeline-item>
      </v-timeline>
    </v-card>
  </v-menu>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { apiFetch } from '@/api'

interface FieldHistoryItem {
  id: number
  vehicle_id: number
  field_key: string
  old_value: string | null
  new_value: string | null
  changed_at: string
  changed_by_user_id: number | null
  comment: string | null
}

const props = defineProps<{
  vehicleId: number
  fieldKey: string
  fieldLabel: string
}>()

const history = ref<FieldHistoryItem[]>([])
const loading = ref(false)

async function loadHistory() {
  if (loading.value) return
  loading.value = true
  history.value = []
  try {
    const r = await apiFetch<FieldHistoryItem[]>(
      `/vehicles/${props.vehicleId}/field-history?field_key=${encodeURIComponent(props.fieldKey)}&limit=50`
    )
    history.value = Array.isArray(r) ? r : []
  } catch (e) {
    console.error('FieldHistoryPopover fetch error', e)
  } finally {
    loading.value = false
  }
}

function formatDate(s: string): string {
  try {
    return new Date(s).toLocaleString('ru-RU', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return s
  }
}
</script>

<style scoped>
.field-history-icon {
  opacity: 0.55;
  transition: opacity 0.15s;
  vertical-align: middle;
}
.field-history-icon:hover {
  opacity: 1;
}
</style>
