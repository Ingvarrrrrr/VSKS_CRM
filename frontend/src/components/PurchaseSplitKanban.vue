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
        v-for="(col, idx) in columns"
        :key="col.key"
        class="split-kanban-col"
      >
        <div class="split-kanban-col-head">
          <div class="split-kanban-col-title">
            <v-icon v-if="col.key === UNCAT_KEY" size="16" class="mr-1" color="grey">mdi-help-circle-outline</v-icon>
            <v-icon v-else size="16" class="mr-1" color="primary">mdi-tag-outline</v-icon>
            <template v-if="!col.editing">
              <span class="flex-grow-1">{{ col.label }}</span>
              <v-btn
                v-if="!readonly && col.key !== UNCAT_KEY"
                icon="mdi-pencil-outline"
                size="x-small"
                variant="text"
                @click="col.editing = true"
              />
              <v-btn
                v-if="!readonly && !col.items.length && col.key !== UNCAT_KEY"
                icon="mdi-close"
                size="x-small"
                variant="text"
                color="error"
                @click="removeColumn(idx)"
              />
            </template>
            <template v-else>
              <input
                v-model="col.label"
                class="split-kanban-col-input"
                @keyup.enter="finishEditColumn(col)"
                @blur="finishEditColumn(col)"
              />
            </template>
          </div>
          <div class="split-kanban-col-meta">
            {{ col.items.length }} шт · {{ formatMoney(sumOf(col.items)) }}
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
        >
          <template #item="{ element }">
            <WishDistributionCard :item="element" :readonly="readonly" />
          </template>
        </draggable>
      </div>

      <div v-if="!readonly" class="split-kanban-col split-kanban-col-add" @click="addColumn">
        <v-icon size="28" color="primary">mdi-plus</v-icon>
        <div class="text-caption text-primary mt-1">Новая колонка</div>
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

interface ColumnState {
  key: string
  label: string
  items: PurchaseItemLike[]
  editing: boolean
}

// Real ref state — не computed — чтобы vuedraggable мог мутировать массив
// при drop между колонками и mutation persist'ился.
const columns = ref<ColumnState[]>([])

function rebuildFromProps() {
  const groups = new Map<string, PurchaseItemLike[]>()
  for (const it of props.items) {
    const cat = (it._product_category || '').trim()
    const k = cat || UNCAT_KEY
    if (!groups.has(k)) groups.set(k, [])
    groups.get(k)!.push(it)
  }
  const out: ColumnState[] = []
  const uncat = groups.get(UNCAT_KEY) || []
  if (uncat.length) out.push({ key: UNCAT_KEY, label: 'Не определено', items: uncat, editing: false })
  for (const [k, arr] of groups.entries()) {
    if (k === UNCAT_KEY) continue
    out.push({ key: k, label: k, items: arr, editing: false })
  }
  columns.value = out
}

rebuildFromProps()
watch(() => props.items, rebuildFromProps, { deep: false })

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

function addColumn() {
  if (props.readonly) return
  let n = columns.value.filter(c => c.key !== UNCAT_KEY).length + 1
  let key = `Новая колонка ${n}`
  while (columns.value.some(c => c.key === key)) {
    n += 1
    key = `Новая колонка ${n}`
  }
  columns.value.push({ key, label: key, items: [], editing: true })
}

function removeColumn(idx: number) {
  if (props.readonly) return
  const col = columns.value[idx]
  if (!col || col.key === UNCAT_KEY) return
  if (col.items.length) return
  columns.value.splice(idx, 1)
}

function finishEditColumn(col: ColumnState) {
  const newLabel = (col.label || '').trim()
  if (!newLabel) {
    col.label = col.key
  } else {
    col.key = newLabel
    col.label = newLabel
  }
  col.editing = false
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
.split-kanban-col-add {
  flex: 0 0 160px;
  min-width: 160px;
  max-width: 160px;
  resize: none;
  border-style: dashed;
  cursor: pointer;
  align-items: center;
  justify-content: center;
  opacity: 0.65;
  transition: opacity 0.15s;
}
.split-kanban-col-add:hover {
  opacity: 1;
}
.split-kanban-col-input {
  flex: 1;
  background: transparent;
  border: 1px solid rgba(var(--v-border-color), 0.6);
  border-radius: 4px;
  padding: 2px 6px;
  color: inherit;
  font-size: inherit;
  font-family: inherit;
  outline: none;
}
.split-kanban-col-input:focus {
  border-color: rgb(var(--v-theme-primary));
}
</style>
