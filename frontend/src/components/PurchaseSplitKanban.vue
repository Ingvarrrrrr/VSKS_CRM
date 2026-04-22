<template>
  <div class="split-kanban">
    <div class="split-kanban-header mb-3">
      <div class="text-caption text-medium-emphasis">
        Перетащите позиции по колонкам — каждая непустая колонка станет отдельной закупкой.
      </div>
      <div class="text-caption mt-1">
        Всего: <strong>{{ totalItems }}</strong> позиций · <strong>{{ formatMoney(totalAmount) }}</strong>
      </div>
    </div>

    <div class="split-kanban-columns">
      <div
        v-for="col in columns"
        :key="col.key"
        class="split-kanban-col"
      >
        <div class="split-kanban-col-head">
          <div class="split-kanban-col-title">
            <v-icon v-if="col.key === UNCAT_KEY" size="16" class="mr-1" color="grey">mdi-help-circle-outline</v-icon>
            <v-icon v-else size="16" class="mr-1" color="primary">mdi-tag-outline</v-icon>
            {{ col.label }}
          </div>
          <div class="split-kanban-col-meta">
            {{ col.items.length }} шт · {{ formatMoney(col.sum) }}
          </div>
        </div>
        <draggable
          :list="col.items"
          :group="{ name: groupName, pull: !readonly, put: !readonly }"
          item-key="id"
          :disabled="readonly"
          :animation="150"
          ghost-class="split-kanban-ghost"
          class="split-kanban-drop"
          @end="onDragEnd($event, col.key)"
        >
          <template #item="{ element }">
            <WishDistributionCard :item="element" :readonly="readonly" />
          </template>
        </draggable>
      </div>
    </div>

    <div v-if="!readonly" class="split-kanban-actions mt-4 d-flex ga-2 justify-end">
      <v-btn
        variant="tonal"
        color="default"
        :disabled="splitting"
        @click="$emit('cancel')"
      >
        Закрыть
      </v-btn>
      <v-btn
        variant="flat"
        color="primary"
        prepend-icon="mdi-call-split"
        :loading="splitting"
        :disabled="nonEmptyColumnCount < 2"
        @click="onSplit"
      >
        Разбить на {{ nonEmptyColumnCount }} {{ pluralPurchases(nonEmptyColumnCount) }}
      </v-btn>
    </div>

    <v-alert
      v-if="readonly"
      type="info"
      variant="tonal"
      density="compact"
      class="mt-3"
      icon="mdi-call-split"
    >
      Закупка разбита на дочерние.
    </v-alert>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
// @ts-ignore - vuedraggable types are loose
import draggable from 'vuedraggable'
import { apiFetch } from '@/api'
import WishDistributionCard from '@/components/WishDistributionCard.vue'

interface PurchaseItemLike {
  id: number
  item_name: string
  quantity: number
  unit: string
  total_price: number
  product_id?: number | null
  _photo_url?: string | null
  _product_category?: string
  _column?: string
}

const props = defineProps<{
  purchaseId: number
  items: PurchaseItemLike[]
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'split', result: { source_purchase_id: number; purchase_ids: number[]; count: number }): void
  (e: 'cancel'): void
  (e: 'error', message: string): void
}>()

const UNCAT_KEY = '__uncategorized__'
const groupName = computed(() => `purchase-split-${props.purchaseId}`)

// Ensure every item has _column seeded (idempotent)
function seedColumns() {
  for (const it of props.items) {
    if (!it._column) {
      const cat = (it._product_category || '').trim()
      it._column = cat || UNCAT_KEY
    }
  }
}
seedColumns()
watch(() => props.items, seedColumns, { deep: false })

function labelOf(key: string): string {
  return key === UNCAT_KEY ? 'Не определено' : key
}

const columns = computed(() => {
  const groups = new Map<string, PurchaseItemLike[]>()
  groups.set(UNCAT_KEY, [])
  for (const it of props.items) {
    const k = it._column || UNCAT_KEY
    if (!groups.has(k)) groups.set(k, [])
    groups.get(k)!.push(it)
  }
  const entries: { key: string; label: string; items: PurchaseItemLike[]; sum: number }[] = []
  const uncat = groups.get(UNCAT_KEY) || []
  if (uncat.length > 0) {
    entries.push({ key: UNCAT_KEY, label: 'Не определено', items: uncat, sum: sumOf(uncat) })
  }
  for (const [k, arr] of groups.entries()) {
    if (k === UNCAT_KEY) continue
    entries.push({ key: k, label: labelOf(k), items: arr, sum: sumOf(arr) })
  }
  return entries
})

function sumOf(items: PurchaseItemLike[]): number {
  return items.reduce((s, it) => s + (Number(it.total_price) || 0), 0)
}

const totalItems = computed(() => props.items.length)
const totalAmount = computed(() => sumOf(props.items))
const nonEmptyColumnCount = computed(() => columns.value.filter(c => c.items.length > 0).length)

function formatMoney(v: number | null | undefined): string {
  if (v == null) return '0 ₽'
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(v)
}

function pluralPurchases(n: number): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return 'закупку'
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return 'закупки'
  return 'закупок'
}

function onDragEnd(ev: any, colKey: string) {
  if (props.readonly) return
  const item = ev?.item?.__draggable_context?.element as PurchaseItemLike | undefined
  if (!item) return
  item._column = colKey
}

const splitting = ref(false)
async function onSplit() {
  if (splitting.value) return
  if (nonEmptyColumnCount.value < 2) {
    emit('error', 'Нужно минимум 2 непустые колонки для разбиения')
    return
  }
  splitting.value = true
  try {
    const payload = {
      groups: columns.value
        .filter(c => c.items.length > 0)
        .map(c => ({
          column_key: c.key === UNCAT_KEY ? '' : c.key,
          item_ids: c.items.map(it => it.id),
        })),
    }
    const res = await apiFetch<{ source_purchase_id: number; purchase_ids: number[]; count: number }>(
      `/purchases/${props.purchaseId}/split`,
      { method: 'POST', body: JSON.stringify(payload) }
    )
    emit('split', res)
  } catch (e: any) {
    emit('error', e?.message || 'Ошибка разбиения закупки')
  } finally {
    splitting.value = false
  }
}
</script>

<style scoped>
.split-kanban {
  width: 100%;
}
.split-kanban-columns {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 8px;
}
.split-kanban-col {
  flex: 0 0 220px;
  min-width: 180px;
  max-width: 520px;
  resize: horizontal;
  overflow: hidden auto;
  display: flex;
  flex-direction: column;
  background: rgba(var(--v-theme-surface-variant), 0.35);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: 10px;
}
.split-kanban :deep(.wish-card-name) {
  white-space: normal;
  word-break: break-word;
  line-height: 1.25;
}
.split-kanban-col-head {
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.split-kanban-col-title {
  font-weight: 600;
  font-size: 0.9rem;
  display: flex;
  align-items: center;
}
.split-kanban-col-meta {
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), 0.65);
  margin-top: 2px;
}
.split-kanban-drop {
  min-height: 80px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.split-kanban-ghost {
  opacity: 0.4;
}
</style>
