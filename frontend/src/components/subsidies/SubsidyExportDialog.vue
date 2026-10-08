<template>
  <ExportColumnsDialog
    ref="dialog"
    title="Экспорт план-графика в Excel"
    columns-url="/subsidies/plan-graph/export/columns"
    :required-keys="['name']"
    preset-storage-key="subsidy_export_columns_preset"
    :show-snack="showSnack"
    :download="doExport"
  >
    <template #extra-options>
      <v-checkbox
        v-model="withSummary"
        label="Лист «Сводная» (Товары / Услуги)"
        density="compact"
        hide-details
      />
      <v-checkbox
        v-model="withByOrder"
        label="Лист «План закупок (по порядку)»"
        density="compact"
        hide-details
      />
      <v-checkbox
        v-model="withContracts"
        label="Лист «Реестр договоров»"
        density="compact"
        hide-details
      />
    </template>
  </ExportColumnsDialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ExportColumnsDialog from '@/components/common/ExportColumnsDialog.vue'
import { filenameFromContentDisposition } from '@/utils/contentDisposition'
import type { ToastType } from '@/composables/useToast'

const props = defineProps<{
  subsidyId: number | null
  subsidyName?: string | null
  showSnack: (text: string, color?: ToastType) => void
}>()

// ПРАВИЛО №6 (07.10.2026): defaultKeys больше не хардкодится здесь — приходит
// из GET /subsidies/plan-graph/export/columns (поле `default` у каждого
// столбца, ExportColumnsDialog сам вычисляет набор после загрузки каталога).
// Новая группа «Договор и оплата» в пресет «Стандартный» не входит.

const dialog = ref<InstanceType<typeof ExportColumnsDialog> | null>(null)
const withSummary = ref(true)
// Владелец 08.10.2026: новые листы «План закупок (по порядку)» и «Реестр
// договоров» — по умолчанию включены, своими галочками (как withSummary).
const withByOrder = ref(true)
const withContracts = ref(true)

async function doExport(selectedKeys: string[]) {
  if (!props.subsidyId) throw new Error('Субсидия не выбрана')
  const token = localStorage.getItem('auth_token')
  const params = new URLSearchParams()
  params.set('columns', selectedKeys.join(','))
  params.set('summary', withSummary.value ? '1' : '0')
  params.set('by_order', withByOrder.value ? '1' : '0')
  params.set('contracts', withContracts.value ? '1' : '0')
  const response = await fetch(`/api/subsidies/${props.subsidyId}/plan-graph/export?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    let msg = `Ошибка экспорта (HTTP ${response.status})`
    try { const j = await response.json(); if (j?.message || j?.detail) msg = j.message || j.detail } catch { /* not json */ }
    throw new Error(msg)
  }
  const cd = response.headers.get('Content-Disposition')
  const fallback = `План_график_${props.subsidyName ?? ''}.xlsx`.trim()
  const filename = filenameFromContentDisposition(cd, fallback)
  const blob = await response.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  window.URL.revokeObjectURL(url)
  document.body.removeChild(a)
}

function open() {
  dialog.value?.open()
}

defineExpose({ open })
</script>
