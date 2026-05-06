<template>
  <v-dialog :model-value="visible" max-width="900" scrollable @update:model-value="v => !v && emit('close')">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-5 d-flex align-center gap-2">
        <v-icon :icon="titleIcon" :color="titleColor" />
        {{ title }}
        <v-chip size="x-small" variant="tonal" class="ml-1">{{ purchases.length }} шт.</v-chip>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="emit('close')" />
      </v-card-title>
      <v-card-text class="pa-0">
        <v-table density="compact">
          <thead>
            <tr>
              <th class="px-4">№</th>
              <th class="px-4">Предмет закупки</th>
              <th class="text-right px-4">Сумма</th>
              <th class="px-4">Контрагент</th>
              <th class="px-4">Статус</th>
              <th class="px-4">№ договора</th>
              <th class="px-4">Дата договора</th>
              <th v-if="showFrameworkSeq" class="text-right px-4">Поставка №</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="p in purchases" :key="p.id"
              style="cursor:pointer"
              @click="emit('row-click', p.id)"
            >
              <td class="px-4 text-medium-emphasis">{{ p.purchase_number || p.id }}</td>
              <td class="px-4 py-2" style="max-width:260px;white-space:normal;font-size:13px">
                {{ p.subject || p.item_name || '—' }}
              </td>
              <td class="text-right px-4 font-weight-medium text-primary">{{ fmtMoney(effectivePrice(p)) }}</td>
              <td class="px-4 text-caption text-medium-emphasis">{{ p.contractor_name || '—' }}</td>
              <td class="px-4">
                <v-chip size="x-small" :color="statusColor(p.status)" variant="flat">
                  {{ statusLabel(p.status) }}
                </v-chip>
              </td>
              <td class="px-4 text-caption">{{ p.contract_number || '—' }}</td>
              <td class="px-4 text-caption">{{ formatDate(p.contract_date) }}</td>
              <td v-if="showFrameworkSeq" class="text-right px-4 text-caption">{{ p.framework_seq ?? '—' }}</td>
            </tr>
            <tr v-if="purchases.length === 0">
              <td :colspan="showFrameworkSeq ? 8 : 7" class="text-center py-6 text-medium-emphasis">Нет закупок</td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
      <v-card-actions class="px-5 pb-4">
        <v-btn
          v-if="purchases.length > 0"
          color="success" variant="tonal" prepend-icon="mdi-microsoft-excel"
          :loading="xlsxLoading"
          @click="exportXlsx"
        >Скачать Excel</v-btn>
        <v-spacer />
        <v-btn @click="emit('close')">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  title: { type: String, default: 'Закупки' },
  titleIcon: { type: String, default: 'mdi-cart-outline' },
  titleColor: { type: String, default: 'primary' },
  purchases: { type: Array as () => any[], default: () => [] },
  filenamePrefix: { type: String, default: 'purchases' },
  showFrameworkSeq: { type: Boolean, default: false },
})

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'row-click', id: number): void
}>()

const xlsxLoading = ref(false)

const STATUS_LABELS: Record<string, string> = {
  wishes: 'Желания', plan_schedule: 'План-график',
  planned: 'Планируется', confirmed: 'Подтверждено',
  in_progress: 'В работе', work_in_progress: 'В работе',
  contracted: 'Договор', ordered: 'Заказано', delivered: 'Поставлено', paid: 'Оплачено',
}
const STATUS_VUETIFY_COLORS: Record<string, string> = {
  planned: 'grey', confirmed: 'primary', in_progress: 'teal', work_in_progress: 'teal',
  contracted: 'indigo', ordered: 'light-blue', delivered: 'deep-purple', paid: 'success',
  plan_schedule: 'warning',
}

function statusLabel(s: string): string { return STATUS_LABELS[s] || s }
function statusColor(s: string): string { return STATUS_VUETIFY_COLORS[s] || 'grey' }

function effectivePrice(p: any): number {
  const status = p.status
  if (status === 'paid')       return parseFloat(p.payment_amount || 0)
  if (status === 'delivered')  return parseFloat(p.acceptance_doc_amount || 0)
  if (status === 'ordered')    return parseFloat(p.contract_price || p.delivery_payment_amount || 0)
  if (status === 'contracted') {
    const isFramework = p.purchase_contract_type === 'framework_cumulative' ||
                        p.purchase_contract_type === 'framework_with_amount'
    if (isFramework) return parseFloat(p.acceptance_doc_amount || p.delivery_payment_amount || 0)
    return p.purchase_method === 'single'
      ? parseFloat(p.contract_price || 0)
      : parseFloat(p.delivery_payment_amount || 0)
  }
  return parseFloat(p.total_nmck || p.planned_total_price || 0)
}

function fmtMoney(v: number): string {
  return (v || 0).toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽'
}

function formatDate(iso: string): string {
  if (!iso) return '—'
  const parts = iso.split('-')
  if (parts.length !== 3) return iso
  return `${parts[2]}.${parts[1]}.${parts[0]}`
}

async function exportXlsx() {
  xlsxLoading.value = true
  try {
    const XLSX = await import('xlsx')
    const rows = props.purchases.map((p: any) => ({
      '№': p.purchase_number || p.id,
      'Предмет закупки': p.subject || p.item_name || '',
      'Сумма': effectivePrice(p),
      'Контрагент': p.contractor_name || '',
      'Статус': STATUS_LABELS[p.status] || p.status,
      '№ договора': p.contract_number || '',
      'Дата договора': formatDate(p.contract_date),
      ...(props.showFrameworkSeq ? { 'Поставка №': p.framework_seq ?? '' } : {}),
    }))
    const ws = XLSX.utils.json_to_sheet(rows)
    const wb = XLSX.utils.book_new()
    const sheetName = props.title.slice(0, 31)
    XLSX.utils.book_append_sheet(wb, ws, sheetName)
    const fname = `${props.filenamePrefix}_${new Date().toISOString().slice(0, 10)}.xlsx`
    XLSX.writeFile(wb, fname)
  } catch (e: any) {
    console.error('Excel export error', e)
  } finally {
    xlsxLoading.value = false
  }
}
</script>
