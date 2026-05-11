<template>
  <div class="widget-renderer" style="height: 100%; display: flex; flex-direction: column">
    <div class="widget-header d-flex align-center pa-2" style="border-bottom: 1px solid #eee">
      <strong>{{ widget.title || 'Виджет' }}</strong>
      <v-spacer />
      <v-btn v-if="editMode" size="x-small" variant="text" icon="mdi-cog" @click="$emit('edit')" />
      <v-btn v-if="editMode" size="x-small" variant="text" icon="mdi-delete" color="error" @click="$emit('remove')" />
    </div>
    <div class="widget-body flex-grow-1" style="overflow: auto; padding: 8px">
      <v-progress-circular v-if="loading" indeterminate />
      <div v-else-if="error" class="text-error text-caption">{{ error }}</div>

      <!-- KPI -->
      <div v-else-if="widget.viz_type === 'kpi'" class="text-center pa-2">
        <div class="text-h4 font-weight-bold">{{ kpiValue }}</div>
        <div class="text-caption text-grey">{{ widget.kpi_label || widget.title }}</div>
      </div>

      <!-- Table -->
      <v-table v-else-if="widget.viz_type === 'table'" density="compact">
        <thead>
          <tr>
            <th v-for="col in tableColumns" :key="col">{{ col }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in tableRows" :key="idx" style="cursor: pointer" @click="onRowClick(row)">
            <td v-for="col in tableColumns" :key="col">{{ formatCell(row[col]) }}</td>
          </tr>
        </tbody>
      </v-table>

      <!-- Charts -->
      <apexchart
        v-else-if="chartOptions && chartSeries"
        :type="widget.viz_type"
        :options="chartOptions"
        :series="chartSeries"
        height="100%"
        @click="onChartClick"
      />

      <div v-else class="text-grey text-caption text-center">Нет данных</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'

const props = defineProps<{
  widget: any
  editMode: boolean
  parameters?: Record<string, any>
}>()
defineEmits<{ (e: 'edit'): void; (e: 'remove'): void }>()

const router = useRouter()
const loading = ref(false)
const error = ref('')
const result = ref<any>({ rows: [], totals: {} })

async function reload() {
  if (!props.widget?.source_config_id) return
  loading.value = true
  error.value = ''
  try {
    result.value = await apiFetch<any>(
      `/api/report-configs/${props.widget.source_config_id}/run`,
      {
        method: 'POST',
        body: JSON.stringify(props.parameters || {}),
      }
    )
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

watch(() => [props.widget?.source_config_id, props.parameters], reload, { deep: true })
onMounted(reload)

const kpiValue = computed(() => {
  const f = props.widget?.kpi_field
  if (!f) return '—'
  if (result.value?.totals?.[f] !== undefined) return formatNumber(result.value.totals[f])
  if (result.value?.rows?.[0]?.[f] !== undefined) return formatNumber(result.value.rows[0][f])
  return formatNumber(result.value?.rows_count || 0)
})

const tableColumns = computed(() => {
  if (!result.value?.rows?.length) return []
  return Object.keys(result.value.rows[0]).filter((k) => !k.startsWith('_'))
})
const tableRows = computed(() => result.value?.rows?.slice(0, 50) || [])

const chartOptions = computed(() => {
  if (!['bar', 'line', 'pie', 'donut', 'area'].includes(props.widget?.viz_type)) return null
  const rows = result.value?.rows || []
  if (!rows.length) return null

  const allKeys = Object.keys(rows[0]).filter((k) => !k.startsWith('_'))
  const dimKey = props.widget?.dimension_key || allKeys.find((k) => typeof rows[0][k] === 'string') || allKeys[0]
  const categories = rows.map((r: any) => String(r[dimKey] ?? ''))

  if (['pie', 'donut'].includes(props.widget.viz_type)) {
    return {
      chart: { toolbar: { show: false } },
      labels: categories,
      legend: { position: 'bottom' },
      dataLabels: { enabled: true },
    }
  }
  return {
    chart: { toolbar: { show: false }, zoom: { enabled: false } },
    xaxis: { categories },
    dataLabels: { enabled: false },
    plotOptions: props.widget.viz_type === 'bar' ? { bar: { horizontal: false, columnWidth: '60%' } } : undefined,
  }
})

const chartSeries = computed(() => {
  const opts = chartOptions.value
  if (!opts) return null
  const rows = result.value?.rows || []
  if (!rows.length) return null
  const allKeys = Object.keys(rows[0]).filter((k) => !k.startsWith('_'))
  const dimKey = props.widget?.dimension_key || allKeys.find((k) => typeof rows[0][k] === 'string') || allKeys[0]
  const measureKey = props.widget?.measure_key || allKeys.find((k) => k !== dimKey && typeof rows[0][k] === 'number') || allKeys[1]

  if (['pie', 'donut'].includes(props.widget.viz_type)) {
    return rows.map((r: any) => Number(r[measureKey]) || 0)
  }
  return [{ name: measureKey, data: rows.map((r: any) => Number(r[measureKey]) || 0) }]
})

function formatNumber(v: any) {
  if (v === null || v === undefined || v === '') return ''
  const n = Number(v)
  if (isNaN(n)) return String(v)
  return n.toLocaleString('ru-RU', { maximumFractionDigits: 0 })
}
function formatCell(v: any) {
  if (typeof v === 'number') return formatNumber(v)
  if (v === null || v === undefined) return ''
  return String(v)
}
function onRowClick(row: any) {
  if (row?._id) router.push(`/orders/${row._id}/edit`)
}
function onChartClick(_event: any, _ctx: any, config: any) {
  const idx = config?.dataPointIndex
  if (idx !== undefined && result.value?.rows?.[idx]?._id) {
    router.push(`/orders/${result.value.rows[idx]._id}/edit`)
  }
}
</script>

<style scoped>
.widget-renderer { width: 100%; height: 100%; }
</style>
