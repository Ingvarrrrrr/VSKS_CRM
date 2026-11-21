<template>
  <v-dialog :model-value="modelValue" max-width="950px" persistent @update:model-value="$emit('update:modelValue', $event)">
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between pb-1">
        <span class="text-h6 font-weight-bold">
          <v-icon icon="mdi-file-document-check-outline" class="mr-2" color="primary" />
          Сопоставление строк накладной с договором
        </span>
        <v-btn icon="mdi-close" variant="text" size="small" @click="close" />
      </v-card-title>

      <v-card-text class="pt-2">
        <v-alert v-if="parsedData?.warnings?.length" type="warning" variant="tonal" density="compact" class="mb-3">
          <div v-for="(warn, wIdx) in parsedData.warnings" :key="wIdx">{{ warn }}</div>
        </v-alert>

        <div class="d-flex ga-3 mb-3 flex-wrap">
          <v-text-field
            v-model="docNumber"
            label="№ документа (УПД/ТТН)"
            density="compact"
            variant="outlined"
            hide-details
            style="max-width: 220px;"
          />
          <v-text-field
            v-model="docDate"
            label="Дата поставки (ГГГГ-ММ-ДД)"
            type="date"
            density="compact"
            variant="outlined"
            hide-details
            style="max-width: 200px;"
          />
        </div>

        <v-table density="compact" class="border rounded">
          <thead>
            <tr>
              <th style="width: 28%;">Строка из накладной</th>
              <th style="width: 34%;">Позиция договора</th>
              <th style="width: 12%;">Кол-во</th>
              <th style="width: 13%;">Цена (₽)</th>
              <th style="width: 13%;">Сумма (₽)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, idx) in rows" :key="idx">
              <td>
                <div class="text-body-2 font-weight-medium">{{ item.name }}</div>
                <div v-if="item.confidence" class="text-caption text-medium-emphasis">
                  Сходство: {{ Math.round(item.confidence * 100) }}%
                </div>
              </td>
              <td>
                <v-select
                  v-model="item.contract_item_id"
                  :items="contractOptions"
                  item-title="title"
                  item-value="id"
                  density="compact"
                  variant="outlined"
                  hide-details
                  clearable
                  placeholder="Выберите позицию..."
                  @update:model-value="onSelectContractItem(item)"
                />
              </td>
              <td>
                <v-text-field
                  v-model.number="item.qty"
                  type="number"
                  step="any"
                  density="compact"
                  variant="outlined"
                  hide-details
                />
              </td>
              <td>
                <v-text-field
                  v-model.number="item.unit_price"
                  type="number"
                  step="0.01"
                  density="compact"
                  variant="outlined"
                  hide-details
                />
              </td>
              <td class="font-weight-medium text-right">
                {{ formatMoney((item.qty || 0) * (item.unit_price || 0)) }}
              </td>
            </tr>
            <tr v-if="!rows.length">
              <td colspan="5" class="text-center text-medium-emphasis py-4">
                Строки не распознаны
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>

      <v-card-actions class="px-4 pb-3 justify-end ga-2">
        <v-btn variant="plain" @click="close">Отмена</v-btn>
        <v-btn
          color="primary"
          variant="elevated"
          :loading="saving"
          :disabled="!rows.length"
          @click="apply"
        >
          Подтвердить и внести в поставку ({{ rows.length }})
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { applyWaybill, type WaybillParseResponse, type WaybillApplyItem } from '@/api/deliveryItems'

interface ContractItemOption {
  id: number
  name: string
  quantity?: number | null
  unit_price?: number | null
}

const props = defineProps<{
  modelValue: boolean
  purchaseId: number
  parsedData: WaybillParseResponse | null
  contractItems: ContractItemOption[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'applied'): void
}>()

interface MatchRow {
  name: string
  qty: number
  unit_price: number
  unit?: string | null
  contract_item_id?: number | null
  purchase_item_id?: number | null
  confidence?: number
}

const rows = ref<MatchRow[]>([])
const docNumber = ref('')
const docDate = ref('')
const saving = ref(false)

const contractOptions = computed(() => {
  return (props.contractItems || []).map((ci) => ({
    id: ci.id,
    title: `${ci.name} (${ci.quantity || 0} шт.)`,
    ci,
  }))
})

watch(
  () => props.parsedData,
  (data) => {
    if (!data) {
      rows.value = []
      docNumber.value = ''
      docDate.value = ''
      return
    }
    docNumber.value = data.doc_number || ''
    docDate.value = data.delivery_date || ''
    rows.value = (data.items || []).map((item) => ({
      name: item.raw_name,
      qty: Number(item.qty) || 0,
      unit_price: Number(item.unit_price) || 0,
      unit: item.unit,
      contract_item_id: item.suggested_contract_item_id,
      purchase_item_id: item.suggested_purchase_item_id,
      confidence: item.confidence,
    }))
  },
  { immediate: true },
)

function onSelectContractItem(row: MatchRow) {
  if (!row.contract_item_id) return
  const match = props.contractItems.find((c) => c.id === row.contract_item_id)
  if (match) {
    if (!row.unit_price && match.unit_price) {
      row.unit_price = Number(match.unit_price)
    }
    if (!row.qty && match.quantity) {
      row.qty = Number(match.quantity)
    }
  }
}

function formatMoney(val: number): string {
  return (val || 0).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽'
}

function close() {
  emit('update:modelValue', false)
}

async function apply() {
  if (!props.purchaseId) return
  saving.value = true
  try {
    const payload: WaybillApplyItem[] = rows.value.map((r) => ({
      name: r.name,
      qty: r.qty,
      unit_price: r.unit_price,
      unit: r.unit,
      contract_item_id: r.contract_item_id,
      purchase_item_id: r.purchase_item_id,
      delivery_date: docDate.value || undefined,
      doc_number: docNumber.value || undefined,
      status: 'delivered',
    }))
    await applyWaybill(props.purchaseId, {
      items: payload,
      doc_number: docNumber.value || undefined,
      delivery_date: docDate.value || undefined,
    })
    emit('applied')
    close()
  } catch (e: any) {
    console.error('Failed to apply waybill:', e)
    alert(e.message || 'Ошибка применения накладной')
  } finally {
    saving.value = false
  }
}
</script>
