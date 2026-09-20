<template>
  <div class="wish-purchases-kanban">
    <div class="wpk-header mb-3">
      <div class="text-caption text-medium-emphasis">
        Перетащите позицию в другую закупку заявки — перенос действует, пока закупка не ушла в
        договор. Замороженные закупки (серый замок в шапке) недоступны для переноса ни в них, ни
        из них.
      </div>
    </div>

    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-2" />

    <v-alert v-if="loadError" type="error" variant="tonal" density="compact" class="mb-2">
      {{ loadError }}
      <template #append>
        <v-btn size="small" variant="text" @click="loadBoard">Повторить</v-btn>
      </template>
    </v-alert>

    <CategoryKanbanBoard
      v-if="!loading && !loadError"
      ref="boardRef"
      v-model:columns="columns"
      :allow-add-column="false"
      :group-name="groupName"
      uncat-key="__wish_purchases_none__"
      column-width="240px"
      @change="onColumnChange"
    />
  </div>
</template>

<script setup lang="ts">
// WishPurchasesKanban.vue — канбан ПОСЛЕ согласования заявки (владелец, лист 2
// №2): заявка уже 'converted', закупки СОЗДАНЫ — этот борд не распределяет
// позиции по будущим закупкам (это делает WishDistributionKanban.vue до
// approve-distribution), а переносит позиции между уже существующими закупками
// заявки, пока их можно тронуть (до договора). Тот же общий столбчатый борд
// (ПРАВИЛО №6) — components/kanban/CategoryKanbanBoard.vue, третий потребитель
// после WishDistributionKanban/PurchaseSplitKanban; колонки = закупки, не
// категории, поэтому «+ Столбец» здесь нет (allow-add-column=false) и колонки
// не редактируются/не удаляются.
import { computed, onMounted, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'
import CategoryKanbanBoard from '@/components/kanban/CategoryKanbanBoard.vue'
import type { KanbanColumnState } from '@/components/kanban/kanbanTypes'

interface PurchaseBoardItem {
  id: number
  item_name: string
  quantity: number
  unit: string
  unit_price?: number | null
  total_price: number
  product_id?: number | null
  _product_category?: string | null
  feo_planned_item_id?: number | null
}
interface PurchaseBoardPurchase {
  id: number
  purchase_number?: string | number | null
  registry_number?: string | null
  subject?: string | null
  status: string
  status_label?: string | null
  frozen: boolean
  items: PurchaseBoardItem[]
}

const props = defineProps<{ wishId: number }>()
const emit = defineEmits<{ (e: 'error', message: string): void }>()

const groupName = computed(() => `wish-purchases-${props.wishId}`)
const columns = ref<KanbanColumnState[]>([])
const loading = ref(false)
const loadError = ref('')

// item.id -> закупка, которая ИМ ВЛАДЕЕТ на клиенте прямо сейчас. Эндпоинт
// переноса (POST /purchases/{purchase_id}/items/{item_id}/move) принимает id
// закупки-ИСТОЧНИКА в пути, а не в теле — сервер её не подсказывает отдельно
// от структуры доски, поэтому единственный источник этого знания на клиенте —
// собственное состояние борда, обновляемое после каждого успешного переноса.
const itemPurchaseMap = new Map<number, number>()

function statusColor(p: PurchaseBoardPurchase): string {
  if (p.frozen) return 'grey'
  if (p.status === 'contracted' || p.status === 'ordered' || p.status === 'delivered' || p.status === 'paid') return 'success'
  if (p.status === 'work_in_progress') return 'orange'
  return 'primary'
}
function labelOf(p: PurchaseBoardPurchase): string {
  const num = p.purchase_number != null ? `№${p.purchase_number}` : (p.registry_number || `№${p.id}`)
  return p.subject ? `${num} · ${p.subject}` : num
}

function buildColumns(purchases: PurchaseBoardPurchase[]) {
  itemPurchaseMap.clear()
  const out: KanbanColumnState[] = []
  for (const p of purchases) {
    for (const it of p.items || []) itemPurchaseMap.set(it.id, p.id)
    out.push({
      key: String(p.id),
      label: labelOf(p),
      items: p.items || [],
      frozen: !!p.frozen,
      statusLabel: p.status_label || undefined,
      statusColor: statusColor(p),
    })
  }
  columns.value = out
}

async function loadBoard() {
  loading.value = true
  loadError.value = ''
  try {
    const board = await apiFetch<{ wish_id: number; title?: string; purchases: PurchaseBoardPurchase[] }>(
      `/wishes/${props.wishId}/purchases-board`,
    )
    buildColumns(board.purchases || [])
  } catch (e: any) {
    loadError.value = describeApiError(e, { fallback: 'Не удалось загрузить доску закупок' })
  } finally {
    loading.value = false
  }
}
onMounted(loadBoard)
watch(() => props.wishId, loadBoard)

async function onColumnChange(colKey: string, evt: any) {
  const added = evt?.added
  if (!added) return // reorder внутри той же колонки — сохранять нечего
  const item = added.element as PurchaseBoardItem | undefined
  if (!item) return
  const targetPurchaseId = Number(colKey)
  const sourcePurchaseId = itemPurchaseMap.get(item.id)
  if (!sourcePurchaseId || sourcePurchaseId === targetPurchaseId || Number.isNaN(targetPurchaseId)) return
  try {
    await apiFetch(`/purchases/${sourcePurchaseId}/items/${item.id}/move`, {
      method: 'POST',
      body: JSON.stringify({ target_purchase_id: targetPurchaseId }),
    })
    itemPurchaseMap.set(item.id, targetPurchaseId)
  } catch (e: any) {
    // Владелец: при ошибке карточка возвращается назад — вместо точечного отката
    // элемента в массиве (как у WishDistributionKanban/PurchaseSplitKanban)
    // здесь перезагружаем всю доску с сервера. Перенос между закупками (в
    // отличие от простого target_column_key/split_column_key) может задеть
    // status/frozen/суммы ОБЕИХ закупок сразу — точечный клиентский откат рискует
    // разойтись с реальным состоянием сервера.
    emit('error', describeApiError(e, { fallback: 'Не удалось перенести позицию' }))
    await loadBoard()
  }
}

// Проброс наверх (WishKanbanDialog.vue), тот же интерфейс, что у остальных двух
// канбанов — allowAddColumn=false здесь, поэтому список всегда пуст, но метод
// нужен, чтобы WishKanbanDialog.vue мог звать её единообразно через один ref.
const boardRef = ref<InstanceType<typeof CategoryKanbanBoard> | null>(null)
function vanishingManualColumns(): string[] {
  return boardRef.value?.vanishingManualColumns() ?? []
}
defineExpose({ vanishingManualColumns })
</script>

<style scoped>
.wish-purchases-kanban {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.wpk-header {
  flex: 0 0 auto;
}
</style>
