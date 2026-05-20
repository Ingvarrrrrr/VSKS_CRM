<template>
  <v-dialog v-model="dialogOpen" max-width="900" scrollable :theme="vuetifyTheme">
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-table-search" size="20" color="primary" class="mr-2" />
        Машины: {{ value }}
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="dialogOpen = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-0">
        <div v-if="loading" class="d-flex justify-center align-center py-8">
          <v-progress-circular indeterminate color="primary" />
        </div>
        <v-alert v-else-if="error" type="error" density="compact" variant="tonal" class="ma-3">
          {{ error }}
        </v-alert>
        <v-data-table
          v-else
          :items="items"
          :headers="headers"
          density="compact"
          :items-per-page="20"
          class="drill-table"
          @click:row="onRowClick"
        >
          <template #item.plate="{ item }">
            <v-chip size="x-small" variant="tonal" color="primary">{{ item.plate }}</v-chip>
          </template>
          <template #item.state="{ item }">
            <v-chip size="x-small" :color="stateColor(item.state)" variant="tonal">
              {{ stateLabel(item.state) }}
            </v-chip>
          </template>
          <template #item.fuel_cost="{ item }">
            {{ fmtCurrency(item.fuel_cost) }}
          </template>
          <template #item.repair_cost="{ item }">
            {{ fmtCurrency(item.repair_cost) }}
          </template>
          <template #item.actions="{ item }">
            <v-btn
              icon="mdi-open-in-new"
              size="x-small"
              variant="text"
              color="primary"
              @click.stop="navigate(item.vehicle_id)"
            />
          </template>
        </v-data-table>
      </v-card-text>
      <v-card-actions class="px-4 pb-3">
        <span class="text-caption text-medium-emphasis">Всего: {{ total }}</span>
        <v-spacer />
        <v-btn variant="tonal" size="small" @click="dialogOpen = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useTheme } from 'vuetify'
import { apiFetch } from '@/api'

const props = defineProps<{
  modelValue: boolean
  dimension: string
  value: string
  dateFrom?: string
  dateTo?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
}>()

const router = useRouter()
const theme = useTheme()
const vuetifyTheme = computed(() => theme.global.current.value.dark ? 'dark' : 'light')

const dialogOpen = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

interface DrillItem {
  vehicle_id: number
  plate: string
  brand: string
  model: string
  state: string
  fuel_cost: number
  repair_cost: number
  owner_org_name: string
}

const items = ref<DrillItem[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)

const headers = [
  { title: 'Гос.№', key: 'plate', width: 110 },
  { title: 'Марка/Модель', key: 'brand_model' },
  { title: 'Состояние', key: 'state', width: 140 },
  { title: 'Владелец', key: 'owner_org_name' },
  { title: 'Бензин ₽', key: 'fuel_cost', align: 'end' as const, width: 110 },
  { title: 'Ремонты ₽', key: 'repair_cost', align: 'end' as const, width: 110 },
  { title: '', key: 'actions', sortable: false, width: 48 },
]

const STATE_LABELS: Record<string, string> = {
  working: 'Работает',
  broken: 'Сломан',
  in_repair: 'В ремонте',
  needs_repair: 'Требует ремонта',
  destroyed: 'Уничтожен',
  utilized: 'Утилизирован',
}
const STATE_COLORS: Record<string, string> = {
  working: 'success',
  broken: 'error',
  in_repair: 'warning',
  needs_repair: 'orange',
  destroyed: 'grey',
  utilized: 'purple',
}

function stateLabel(s: string) {
  return STATE_LABELS[s] || s
}
function stateColor(s: string) {
  return STATE_COLORS[s] || 'default'
}

function fmtCurrency(v: number): string {
  return v.toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽'
}

async function fetchDrill() {
  if (!props.dimension || !props.value) return
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams({
      dimension: props.dimension,
      value: props.value,
    })
    if (props.dateFrom) params.set('date_from', props.dateFrom)
    if (props.dateTo) params.set('date_to', props.dateTo)
    const data = await apiFetch<{ items: DrillItem[]; total: number }>(
      '/vehicles-dashboard/drill?' + params.toString()
    )
    items.value = data.items || []
    total.value = data.total || 0
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) fetchDrill()
    else {
      items.value = []
      error.value = null
    }
  }
)

function navigate(vehicleId: number) {
  dialogOpen.value = false
  router.push(`/property/vehicles/${vehicleId}`)
}

function onRowClick(_event: unknown, { item }: { item: DrillItem }) {
  navigate(item.vehicle_id)
}
</script>

<style scoped>
.drill-table :deep(tr) {
  cursor: pointer;
}
.drill-table :deep(tr:hover td) {
  background: rgba(59, 130, 246, 0.06);
}
</style>
