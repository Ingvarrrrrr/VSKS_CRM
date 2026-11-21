<template>
  <div class="delivery-items-panel mt-4">
    <v-card variant="outlined" class="pa-3">
      <!-- Header & Progress -->
      <div class="d-flex align-center justify-space-between flex-wrap ga-2 mb-3">
        <div>
          <div class="text-subtitle-1 font-weight-bold d-flex align-center ga-2">
            <v-icon icon="mdi-truck-delivery-outline" color="purple" />
            Фактические поставки по накладным (УПД / ТТН)
          </div>
          <div class="text-caption text-medium-emphasis">
            Поставлено: {{ formatMoney(summary.delivered_total) }} из {{ formatMoney(summary.contract_total) }}
            ({{ summary.delivered_amount_pct }}%)
          </div>
        </div>

        <div class="d-flex align-center ga-2" style="min-width: 200px;">
          <v-progress-linear
            :model-value="summary.delivered_amount_pct"
            height="18"
            rounded
            :color="progressColor"
          >
            <template #default="{ value }">
              <span class="text-caption font-weight-bold text-white">{{ Math.round(value) }}%</span>
            </template>
          </v-progress-linear>
        </div>
      </div>

      <!-- Action buttons -->
      <div v-if="!readonly" class="d-flex align-center ga-2 flex-wrap mb-3">
        <v-btn
          variant="tonal"
          prepend-icon="mdi-playlist-plus"
          size="small"
          color="purple"
          :loading="loadingFromContract"
          @click="onFillFromContract"
        >
          Заполнить из договора
        </v-btn>

        <v-btn
          variant="tonal"
          prepend-icon="mdi-file-upload-outline"
          size="small"
          color="primary"
          :loading="parsingWaybill"
          @click="triggerFileInput"
        >
          Загрузить накладную (ТТН/УПД)
        </v-btn>
        <input
          ref="fileInputRef"
          type="file"
          accept=".xlsx,.xls,.pdf,.docx,.doc,.jpg,.jpeg,.png"
          style="display: none;"
          @change="onFileSelected"
        >

        <v-btn
          variant="text"
          prepend-icon="mdi-plus"
          size="small"
          color="success"
          @click="addManualRow"
        >
          + Строка поставки
        </v-btn>
      </div>

      <!-- Table of items -->
      <v-table density="compact" class="border rounded">
        <thead>
          <tr>
            <th style="width: 26%;">Наименование</th>
            <th style="width: 10%;">Кол-во</th>
            <th style="width: 12%;">Цена (₽)</th>
            <th style="width: 12%;">Сумма (₽)</th>
            <th style="width: 12%;">Дата поставки</th>
            <th style="width: 12%;">№ документа</th>
            <th style="width: 12%;">Статус</th>
            <th v-if="!readonly" style="width: 4%;"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td>
              <v-text-field
                v-if="!readonly"
                v-model="item.name"
                density="compact"
                variant="plain"
                hide-details
                @change="saveItem(item)"
              />
              <span v-else>{{ item.name }}</span>
            </td>
            <td>
              <v-text-field
                v-if="!readonly"
                v-model.number="item.qty"
                type="number"
                step="any"
                density="compact"
                variant="plain"
                hide-details
                @change="saveItem(item)"
              />
              <span v-else>{{ item.qty }}</span>
            </td>
            <td>
              <v-text-field
                v-if="!readonly"
                v-model.number="item.unit_price"
                type="number"
                step="0.01"
                density="compact"
                variant="plain"
                hide-details
                @change="saveItem(item)"
              />
              <span v-else>{{ formatMoney(item.unit_price) }}</span>
            </td>
            <td class="font-weight-medium">
              {{ formatMoney(item.total) }}
            </td>
            <td>
              <v-text-field
                v-if="!readonly"
                v-model="item.delivery_date"
                type="date"
                density="compact"
                variant="plain"
                hide-details
                @change="saveItem(item)"
              />
              <span v-else>{{ item.delivery_date || '—' }}</span>
            </td>
            <td>
              <v-text-field
                v-if="!readonly"
                v-model="item.doc_number"
                density="compact"
                variant="plain"
                hide-details
                placeholder="—"
                @change="saveItem(item)"
              />
              <span v-else>{{ item.doc_number || '—' }}</span>
            </td>
            <td>
              <v-select
                v-if="!readonly"
                v-model="item.status"
                :items="statusOptions"
                density="compact"
                variant="plain"
                hide-details
                @update:model-value="saveItem(item)"
              />
              <v-chip v-else size="x-small" :color="statusColor(item.status)">
                {{ statusLabel(item.status) }}
              </v-chip>
            </td>
            <td v-if="!readonly" class="text-right">
              <v-btn
                icon="mdi-delete-outline"
                variant="text"
                size="x-small"
                color="error"
                @click="removeItem(item.id)"
              />
            </td>
          </tr>
          <tr v-if="!items.length">
            <td colspan="8" class="text-center text-medium-emphasis py-4">
              Поставок пока не зарегистрировано. Нажмите «Заполнить из договора» или загрузите накладную.
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <!-- Waybill Match Dialog -->
    <DeliveryWaybillMatchDialog
      v-model="showMatchDialog"
      :purchase-id="purchaseId"
      :parsed-data="parsedWaybillData"
      :contract-items="contractItems"
      @applied="loadData"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  listDeliveryItems,
  createDeliveryItem,
  patchDeliveryItem,
  deleteDeliveryItem,
  createDeliveryItemsFromContract,
  parseWaybill,
  type DeliveryItem,
  type DeliverySummary,
  type WaybillParseResponse,
} from '@/api/deliveryItems'
import DeliveryWaybillMatchDialog from './DeliveryWaybillMatchDialog.vue'

const props = withDefaults(
  defineProps<{
    purchaseId: number
    readonly?: boolean
    contractItems?: any[]
  }>(),
  {
    readonly: false,
    contractItems: () => [],
  },
)

const items = ref<DeliveryItem[]>([])
const summary = ref<DeliverySummary>({
  contract_total: 0,
  delivered_total: 0,
  delivered_qty_pct: 0,
  delivered_amount_pct: 0,
  status_counts: { pending: 0, partial: 0, delivered: 0 },
})

const loadingFromContract = ref(false)
const parsingWaybill = ref(false)
const showMatchDialog = ref(false)
const parsedWaybillData = ref<WaybillParseResponse | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

const statusOptions = [
  { value: 'pending', title: 'Ожидается' },
  { value: 'partial', title: 'Частично' },
  { value: 'delivered', title: 'Получено' },
]

const progressColor = computed(() => {
  const p = summary.value.delivered_amount_pct
  if (p >= 100) return 'success'
  if (p >= 50) return 'primary'
  return 'orange'
})

function statusColor(st: string) {
  if (st === 'delivered') return 'success'
  if (st === 'partial') return 'orange'
  return 'grey'
}

function statusLabel(st: string) {
  const found = statusOptions.find((o) => o.value === st)
  return found ? found.title : st
}

function formatMoney(val?: number): string {
  return (val || 0).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽'
}

async function loadData() {
  if (!props.purchaseId) return
  try {
    const res = await listDeliveryItems(props.purchaseId)
    items.value = res.items
    summary.value = res.summary
  } catch (e) {
    console.error('Failed to load delivery items:', e)
  }
}

async function saveItem(item: DeliveryItem) {
  try {
    const updated = await patchDeliveryItem(props.purchaseId, item.id, {
      name: item.name,
      qty: item.qty,
      unit_price: item.unit_price,
      delivery_date: item.delivery_date,
      doc_number: item.doc_number,
      status: item.status,
    })
    item.total = updated.total
    await loadData()
  } catch (e) {
    console.error('Failed to patch item:', e)
  }
}

async function addManualRow() {
  try {
    await createDeliveryItem(props.purchaseId, {
      name: 'Новая поставка',
      qty: 1,
      unit_price: 0,
      status: 'pending',
    })
    await loadData()
  } catch (e) {
    console.error('Failed to add delivery item:', e)
  }
}

async function removeItem(itemId: number) {
  if (!confirm('Удалить строку поставки?')) return
  try {
    await deleteDeliveryItem(props.purchaseId, itemId)
    await loadData()
  } catch (e) {
    console.error('Failed to delete delivery item:', e)
  }
}

async function onFillFromContract() {
  loadingFromContract.value = true
  try {
    await createDeliveryItemsFromContract(props.purchaseId)
    await loadData()
  } catch (e: any) {
    alert(e.message || 'Ошибка заполнения из договора')
  } finally {
    loadingFromContract.value = false
  }
}

function triggerFileInput() {
  fileInputRef.value?.click()
}

async function onFileSelected(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  parsingWaybill.value = true
  try {
    parsedWaybillData.value = await parseWaybill(props.purchaseId, file)
    showMatchDialog.value = true
  } catch (e: any) {
    alert(e.message || 'Не удалось распознать накладную')
  } finally {
    parsingWaybill.value = false
    target.value = ''
  }
}

watch(() => props.purchaseId, loadData, { immediate: true })
onMounted(loadData)
</script>
