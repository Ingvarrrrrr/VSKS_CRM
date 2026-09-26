<template>
  <v-dialog :model-value="modelValue" max-width="900" @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <v-card>
      <v-card-title class="d-flex align-center">
        Расхождения НДС в закупках
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="emit('update:modelValue', false)" />
      </v-card-title>
      <v-card-text>
        <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-3" />
        <div v-else-if="!rows.length" class="text-body-2 text-medium-emphasis pa-4 text-center">
          Расхождений не найдено.
        </div>
        <v-table v-else density="comfortable">
          <thead>
            <tr>
              <th>Закупка</th>
              <th>Субсидия</th>
              <th>НДС закупки</th>
              <th>НДС платежей</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id">
              <td>
                <router-link :to="`/orders/${row.id}`" target="_blank">
                  №{{ row.purchase_number ?? row.id }}{{ row.subject ? ` — ${row.subject}` : '' }}
                </router-link>
              </td>
              <td class="text-caption">{{ row.subsidy_name ?? '—' }}</td>
              <td>{{ row.purchase_vat_label }}</td>
              <td>
                <span v-if="row.status === 'payments_disagree'" class="text-warning">платежи расходятся между собой</span>
                <span v-else>
                  {{ row.payments?.[0]?.label ?? '—' }}
                  <v-chip v-if="row.payments?.some(p => !p.confirmed)" size="x-small" color="warning" variant="outlined" class="ml-1">
                    не подтверждён
                  </v-chip>
                </span>
              </td>
              <td>
                <v-btn
                  v-if="row.suggested"
                  size="small" color="warning" variant="tonal"
                  :loading="aligningId === row.id"
                  @click="confirmRow = row"
                >
                  Приравнять
                </v-btn>
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
    </v-card>

    <v-dialog :model-value="!!confirmRow" max-width="440" @update:model-value="(v: boolean) => { if (!v) confirmRow = null }">
      <v-card v-if="confirmRow">
        <v-card-title class="text-body-1">Приравнять НДС закупки №{{ confirmRow.purchase_number ?? confirmRow.id }}?</v-card-title>
        <v-card-text class="text-body-2">
          Ставка НДС закупки будет изменена на
          <strong>{{ confirmRow.suggested?.vat_applicable ? `${confirmRow.suggested.vat_rate}%` : 'без НДС' }}</strong>.
          <v-alert v-if="confirmRow.payments?.some(p => !p.confirmed)" type="warning" variant="tonal" density="compact" class="mt-3">
            Часть платежей, на которых основано предложение, сопоставлена с закупкой
            автоматически и ЕЩЁ НЕ подтверждена в реестре платежей.
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="confirmRow = null">Отмена</v-btn>
          <v-btn color="warning" variant="flat" :loading="aligningId === confirmRow.id" @click="align(confirmRow)">Приравнять</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-dialog>
</template>

<script setup lang="ts">
// Владелец (2026-09-26): список закупок, где НДС в закупке не совпадает с
// НДС, распознанным в подтверждённых платежах выписки — со ссылками на
// закупки и кнопкой «Приравнять» по строке. Данные и сверка — ИСКЛЮЧИТЕЛЬНО
// с бэка (app/services/purchase_vat_check.py::find_vat_mismatches), здесь
// только отображение (ПРАВИЛО №6, не считаем НДС повторно на фронте).
import { ref, watch } from 'vue'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'

interface MismatchRow {
  id: number
  purchase_number: number | null
  subject: string | null
  subsidy_id: number | null
  subsidy_name: string | null
  purchase_vat_label: string
  status: string
  payments: Array<{ id: number; label: string; number: string | null; date: string | null; confirmed: boolean }>
  suggested: { vat_applicable: boolean; vat_rate: number | null } | null
}

const props = defineProps<{
  modelValue: boolean
}>()
const emit = defineEmits<{
  'update:modelValue': [boolean]
  loaded: [count: number]
}>()

const { success, error } = useToast()

const rows = ref<MismatchRow[]>([])
const loading = ref(false)
const aligningId = ref<number | null>(null)
const confirmRow = ref<MismatchRow | null>(null)

async function load() {
  loading.value = true
  try {
    rows.value = await apiFetch<MismatchRow[]>('/purchases/vat-payment-mismatches')
    emit('loaded', rows.value.length)
  } catch (e: any) {
    error(`Не удалось загрузить расхождения НДС: ${e?.detail || e?.message || 'неизвестная ошибка'}`, { duration: 0 })
  } finally {
    loading.value = false
  }
}

async function align(row: MismatchRow) {
  if (!row.suggested) return
  aligningId.value = row.id
  try {
    await apiFetch(`/purchases/${row.id}/align-vat-to-payments`, {
      method: 'POST',
      body: row.suggested,
    })
    success(`НДС закупки №${row.purchase_number ?? row.id} приравнен к платежам`)
    confirmRow.value = null
    await load()
  } catch (e: any) {
    error(`Не удалось приравнять НДС: ${e?.detail || e?.message || 'неизвестная ошибка'}${e?.status ? ` (HTTP ${e.status})` : ''}`, { duration: 0 })
  } finally {
    aligningId.value = null
  }
}

watch(() => props.modelValue, (v) => { if (v) load() })

defineExpose({ reload: load })
</script>
