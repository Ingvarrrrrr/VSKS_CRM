<template>
  <ExportColumnsDialog
    ref="dialog"
    title="Экспорт в Excel"
    columns-url="/purchases/export/columns"
    :default-keys="DEFAULT_EXPORT_KEYS"
    preset-storage-key="export_columns_preset"
    :show-snack="showSnack"
    :download="doExport"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ExportColumnsDialog from '@/components/common/ExportColumnsDialog.vue'
import type { ToastType } from '@/composables/useToast'
import type { OrdersFiltersState } from '@/composables/orders/useOrdersFilters'

const props = defineProps<{
  filters: OrdersFiltersState
  showSnack: (text: string, color?: ToastType) => void
}>()

const DEFAULT_EXPORT_KEYS = [
  'purchase_number', 'registry_number', 'item_name', 'item_type', 'unit', 'quantity',
  'nmck', 'contract_price', 'economy', 'purchase_method',
  'contract_number', 'contract_date', 'contractor',
  'execution_term', 'country_origin',
  'acceptance_doc_name', 'acceptance_doc_number', 'acceptance_doc_date', 'acceptance_doc_amount',
  'payment_doc_number', 'payment_doc_date', 'payment_amount', 'payment_federal',
  'status',
]

const dialog = ref<InstanceType<typeof ExportColumnsDialog> | null>(null)

async function doExport(selectedKeys: string[]) {
  const token = localStorage.getItem('auth_token')
  const params = new URLSearchParams()
  if (props.filters.subsidyId) params.set('subsidy_id', String(props.filters.subsidyId))
  if (props.filters.status) params.set('status', props.filters.status)
  params.set('columns', selectedKeys.join(','))
  const response = await fetch(`/api/purchases/export/excel?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    let msg = `Ошибка экспорта (HTTP ${response.status})`
    try { const j = await response.json(); if (j?.message) msg = j.message } catch { /* not json */ }
    throw new Error(msg)
  }
  const missingRaw = response.headers.get('X-Missing-Columns')
  const missing = missingRaw ? decodeURIComponent(missingRaw) : null
  const blob = await response.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `Закупки_${new Date().toISOString().slice(0, 10)}.xlsx`
  document.body.appendChild(a)
  a.click()
  window.URL.revokeObjectURL(url)
  document.body.removeChild(a)
  if (missing) {
    props.showSnack(`Предупреждение: мало данных в колонках: ${missing}`, 'warning')
  }
}

function open() {
  dialog.value?.open()
}

defineExpose({ open })
</script>
