<template>
  <div class="wish-kanban">
    <div class="wish-kanban-header mb-3">
      <div class="text-caption text-medium-emphasis">
        Распределите позиции по будущим закупкам (колонки = категории товаров). Перетащите карточку между колонками.
      </div>
      <div class="text-caption mt-1">
        Всего: <strong>{{ totalItems }}</strong> позиций · <strong>{{ formatMoney(totalAmount) }}</strong>
      </div>
    </div>

    <div class="wish-kanban-columns">
      <div
        v-for="col in columns"
        :key="col.key"
        class="wish-kanban-col"
      >
        <div class="wish-kanban-col-head">
          <div class="wish-kanban-col-title">
            <v-icon v-if="col.key === UNCAT_KEY" size="16" class="mr-1" color="grey">mdi-help-circle-outline</v-icon>
            <v-icon v-else size="16" class="mr-1" color="primary">mdi-tag-outline</v-icon>
            {{ col.label }}
          </div>
          <div class="wish-kanban-col-meta">
            {{ col.items.length }} шт · {{ formatMoney(col.sum) }}
          </div>
        </div>
        <draggable
          :list="col.items"
          :group="{ name: groupName, pull: !readonly, put: !readonly }"
          item-key="id"
          :disabled="readonly"
          :animation="150"
          ghost-class="wish-kanban-ghost"
          class="wish-kanban-drop"
          @end="onDragEnd($event, col.key)"
        >
          <template #item="{ element }">
            <WishDistributionCard :item="element" :readonly="readonly" />
          </template>
        </draggable>
      </div>
    </div>

    <div v-if="!readonly" class="wish-kanban-actions mt-4 d-flex ga-2 justify-end">
      <v-btn
        variant="tonal"
        color="default"
        :disabled="approving"
        @click="$emit('cancel')"
      >
        Закрыть
      </v-btn>
      <v-btn
        variant="flat"
        color="success"
        prepend-icon="mdi-check-all"
        :loading="approving"
        :disabled="totalItems === 0"
        @click="onApprove"
      >
        Одобрить и создать {{ nonEmptyColumnCount }} {{ pluralPurchases(nonEmptyColumnCount) }}
      </v-btn>
    </div>

    <v-alert
      v-if="readonly"
      type="success"
      variant="tonal"
      density="compact"
      class="mt-3"
      icon="mdi-check-decagram"
    >
      Заявка одобрена — распределение зафиксировано.
    </v-alert>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
// @ts-ignore - vuedraggable types are loose
import draggable from 'vuedraggable'
import { apiFetch } from '@/api'
import WishDistributionCard from '@/components/WishDistributionCard.vue'

interface WishItem {
  id: number
  item_name: string
  quantity: number
  unit: string
  total_price: number
  target_column_key: string | null
  _photo_url?: string | null
  _product_category?: string
  product_id?: number | null
}

const props = defineProps<{
  wishId: number
  items: WishItem[]
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'approved', result: { purchase_ids: number[]; count: number }): void
  (e: 'cancel'): void
  (e: 'error', message: string): void
}>()

const UNCAT_KEY = '__uncategorized__'
const groupName = computed(() => `wish-${props.wishId}`)

function resolveKey(it: WishItem): string {
  if (it.target_column_key && it.target_column_key.trim()) return it.target_column_key
  if (it._product_category && it._product_category.trim()) return it._product_category
  return UNCAT_KEY
}

function labelOf(key: string): string {
  return key === UNCAT_KEY ? 'Не определено' : key
}

const columns = computed(() => {
  const groups = new Map<string, WishItem[]>()
  groups.set(UNCAT_KEY, [])
  for (const it of props.items) {
    const k = resolveKey(it)
    if (!groups.has(k)) groups.set(k, [])
    groups.get(k)!.push(it)
  }
  const entries: { key: string; label: string; items: WishItem[]; sum: number }[] = []
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

function sumOf(items: WishItem[]): number {
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

async function onDragEnd(ev: any, colKey: string) {
  if (props.readonly) return
  const item = ev?.item?.__draggable_context?.element as WishItem | undefined
  if (!item) return
  if (item.target_column_key === colKey) return
  const prev = item.target_column_key
  item.target_column_key = colKey
  try {
    await apiFetch(`/wishes/${props.wishId}/items/${item.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ target_column_key: colKey === UNCAT_KEY ? null : colKey }),
    })
  } catch (e: any) {
    item.target_column_key = prev ?? null
    emit('error', e?.message || 'Не удалось сохранить позицию')
  }
}

const approving = ref(false)
async function onApprove() {
  if (approving.value) return
  approving.value = true
  try {
    const res = await apiFetch<{ purchase_ids: number[]; count: number }>(
      `/wishes/${props.wishId}/approve-distribution`,
      { method: 'POST' }
    )
    emit('approved', res)
  } catch (e: any) {
    emit('error', e?.message || 'Ошибка одобрения распределения')
  } finally {
    approving.value = false
  }
}
</script>

<style scoped>
.wish-kanban {
  width: 100%;
}
.wish-kanban-columns {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 8px;
}
.wish-kanban-col {
  flex: 0 0 280px;
  display: flex;
  flex-direction: column;
  background: rgba(var(--v-theme-surface-variant), 0.35);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: 10px;
}
.wish-kanban-col-head {
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.wish-kanban-col-title {
  font-weight: 600;
  font-size: 0.9rem;
  display: flex;
  align-items: center;
}
.wish-kanban-col-meta {
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), 0.65);
  margin-top: 2px;
}
.wish-kanban-drop {
  min-height: 80px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.wish-kanban-ghost {
  opacity: 0.4;
}
</style>
