<template>
  <div class="mb-3">
    <div class="text-caption text-medium-emphasis mb-1">Руководитель организации (по ЕГРЮЛ)</div>
    <v-alert type="info" variant="tonal" density="compact" class="mb-2 text-caption">
      Подписант ниже может отличаться (например, действует по доверенности) —
      руководитель определяется из ЕГРЮЛ по ИНН и не редактируется вручную.
    </v-alert>

    <div v-if="loading" class="d-flex align-center ga-2 mb-2">
      <v-progress-circular indeterminate size="18" width="2" />
      <span class="text-caption">Загрузка…</span>
    </div>

    <template v-else>
      <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mb-2 text-caption">
        {{ error }}
      </v-alert>

      <template v-else>
        <div class="mb-1">
          <span v-if="fioShort" class="text-body-2">{{ fioShort }}</span>
          <span v-else class="text-body-2 text-medium-emphasis">не определён</span>
          <span v-if="position" class="text-caption text-medium-emphasis"> — {{ position }}</span>
        </div>

        <v-alert
          v-if="fioShort && employee"
          type="success" variant="tonal" density="compact" class="mb-2 text-caption"
        >
          Сотрудник в системе: {{ employee.full_name }}
        </v-alert>
        <v-alert
          v-else-if="fioShort && !employee"
          type="warning" variant="tonal" density="compact" class="mb-2 text-caption"
        >
          Такого сотрудника нет в организации — добавьте его, иначе согласование по руководителю не построится.
        </v-alert>
      </template>
    </template>

    <v-btn
      variant="tonal" color="primary" size="small"
      prepend-icon="mdi-refresh"
      :loading="refreshing"
      :disabled="loading"
      @click="refresh"
    >
      Обновить по ИНН
    </v-btn>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { apiFetch } from '@/api'

const props = defineProps<{ orgId: number | null }>()

interface DirectorInfo {
  last_name: string | null
  first_name: string | null
  middle_name: string | null
  position: string | null
  fio_short: string | null
  employee: { id: number; full_name: string } | null
  source: string
  inn: string | null
}

const loading = ref(false)
const refreshing = ref(false)
const error = ref('')
const fioShort = ref<string | null>(null)
const position = ref<string | null>(null)
const employee = ref<{ id: number; full_name: string } | null>(null)

function apply(data: DirectorInfo) {
  fioShort.value = data.fio_short
  position.value = data.position
  employee.value = data.employee
}

async function load() {
  if (!props.orgId) return
  loading.value = true
  error.value = ''
  try {
    const data = await apiFetch<DirectorInfo>(`/organizations/${props.orgId}/director`)
    apply(data)
  } catch (e: any) {
    error.value = e?.payload?.message || e?.message || 'Не удалось загрузить руководителя'
  } finally {
    loading.value = false
  }
}

async function refresh() {
  if (!props.orgId) return
  refreshing.value = true
  error.value = ''
  try {
    const data = await apiFetch<DirectorInfo>(`/organizations/${props.orgId}/director/refresh`, { method: 'POST' })
    apply(data)
  } catch (e: any) {
    error.value = e?.payload?.message || e?.message || 'Не удалось обновить руководителя по ИНН'
  } finally {
    refreshing.value = false
  }
}

watch(() => props.orgId, () => { load() }, { immediate: true })
</script>
