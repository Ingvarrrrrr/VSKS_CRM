<template>
  <div class="split-kanban">
    <div class="split-kanban-header mb-3">
      <div class="text-caption text-medium-emphasis">
        Перетащите позиции по колонкам — каждая непустая колонка станет отдельной закупкой.
        Раскладка сохраняется на сервере сразу же (переживает закрытие окна и перезагрузку).
      </div>
      <div class="text-caption mt-1">
        Всего: <strong>{{ totalItems }}</strong> позиций · <strong>{{ formatMoney(totalAmount) }}</strong>
      </div>
    </div>

    <CategoryKanbanBoard
      ref="boardRef"
      v-model:columns="columns"
      :readonly="readonly"
      :group-name="groupName"
      :uncat-key="UNCAT_KEY"
      add-column-prefix="Новая колонка"
      @change="onColumnChange"
    />

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
// Владелец (2026-09-16): «перекидывал по категориям в канбане разбиения
// закупки, случайно вышел из окна — всё слетело». Раскладка теперь сохраняется
// на сервере per-позиция (purchase_items.split_column_key, PATCH на каждый
// бросок — см. app/routers/purchase_split_columns.py) вместо чисто клиентского
// состояния, живущего только в памяти этого компонента. Общий столбчатый борд
// (drag/drop, «+ Столбец», rename/remove пустой колонки, горизонтальная
// прокрутка колёсиком, автопрокрутка к краю при перетаскивании) — тот же
// компонент, что у распределения заявки (ПРАВИЛО №6, владелец: «один канбан на
// оба места»): components/kanban/CategoryKanbanBoard.vue.
import { computed, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import CategoryKanbanBoard from '@/components/kanban/CategoryKanbanBoard.vue'
import type { KanbanColumnState } from '@/components/kanban/kanbanTypes'

interface PurchaseItemLike {
  id: number
  item_name: string
  quantity: number
  unit: string
  total_price: number
  product_id?: number | null
  _photo_url?: string | null
  _product_category?: string
  split_column_key?: string | null
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

function resolveKey(it: PurchaseItemLike): string {
  if (it.split_column_key && it.split_column_key.trim()) return it.split_column_key
  if (it._product_category && it._product_category.trim()) return it._product_category
  return UNCAT_KEY
}
function labelOf(key: string): string {
  return key === UNCAT_KEY ? 'Не определено' : key
}

// Real ref state — не computed, чтобы держать пустые «+ Столбец» колонки и
// колонки с уже сохранённым на сервере split_column_key.
const columns = ref<KanbanColumnState[]>([])

function rebuildFromProps() {
  const groups = new Map<string, PurchaseItemLike[]>()
  for (const it of props.items) {
    const k = resolveKey(it)
    if (!groups.has(k)) groups.set(k, [])
    groups.get(k)!.push(it)
  }
  const out: KanbanColumnState[] = []
  const uncat = groups.get(UNCAT_KEY) || []
  if (uncat.length) out.push({ key: UNCAT_KEY, label: 'Не определено', items: uncat })
  for (const [k, arr] of groups.entries()) {
    if (k === UNCAT_KEY) continue
    out.push({ key: k, label: k, items: arr })
  }
  columns.value = out
}
rebuildFromProps()
// deep:false — как и у WishDistributionKanban.vue: onColumnChange мутирует
// split_column_key на существующих элементах props.items (тот же массив, не
// заменяется), пересборка на эту мутацию реагировать не должна.
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

// Откат неудавшегося PATCH — см. onColumnChange (тот же приём, что и в
// WishDistributionKanban.vue::moveItemToColumnArrays).
function moveItemToColumnArrays(item: PurchaseItemLike, targetKey: string) {
  for (const c of columns.value) {
    const i = c.items.findIndex((x: any) => x.id === item.id)
    if (i !== -1) c.items.splice(i, 1)
  }
  let target = columns.value.find(c => c.key === targetKey)
  if (!target) {
    target = { key: targetKey, label: labelOf(targetKey), items: [] }
    columns.value.push(target)
  }
  target.items.push(item)
}

async function onColumnChange(colKey: string, evt: any) {
  if (props.readonly) return
  const added = evt?.added
  if (!added) return
  const item = added.element as PurchaseItemLike | undefined
  if (!item) return
  const newKey = colKey === UNCAT_KEY ? null : colKey
  if ((item.split_column_key ?? null) === newKey) return
  const prev = item.split_column_key ?? null
  item.split_column_key = newKey
  try {
    await apiFetch(`/purchases/${props.purchaseId}/items/${item.id}/split-column`, {
      method: 'PATCH',
      body: JSON.stringify({ split_column_key: newKey }),
    })
  } catch (e: any) {
    item.split_column_key = prev
    moveItemToColumnArrays(item, resolveKey(item))
    emit('error', e?.payload?.message || e?.message || 'Не удалось сохранить раскладку позиции')
  }
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
          item_ids: c.items.map((it: any) => it.id),
        })),
    }
    const res = await apiFetch<{ source_purchase_id: number; purchase_ids: number[]; count: number }>(
      `/purchases/${props.purchaseId}/split`,
      { method: 'POST', body: JSON.stringify(payload) }
    )
    emit('split', res)
  } catch (e: any) {
    emit('error', e?.payload?.message || e?.message || 'Ошибка разбиения закупки')
  } finally {
    splitting.value = false
  }
}

// Проброс наверх (SplitKanbanDialog.vue) — предупреждение при закрытии окна о
// пустых «+ Столбец» колонках, которые нигде не хранятся (см. CategoryKanbanBoard).
const boardRef = ref<InstanceType<typeof CategoryKanbanBoard> | null>(null)
function vanishingManualColumns(): string[] {
  return boardRef.value?.vanishingManualColumns() ?? []
}
defineExpose({ vanishingManualColumns })
</script>

<style scoped>
.split-kanban {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.split-kanban-header {
  flex: 0 0 auto;
}
.split-kanban :deep(.wish-card-name) {
  white-space: normal;
  word-break: break-word;
  line-height: 1.25;
}
.split-kanban-actions {
  flex: 0 0 auto;
}
</style>
