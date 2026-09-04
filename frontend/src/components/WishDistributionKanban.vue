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

    <div v-if="!readonly" class="wish-kanban-actions mt-4 d-flex ga-2 align-center">
      <div class="d-flex ga-2 align-center">
        <v-btn
          variant="outlined"
          color="primary"
          prepend-icon="mdi-arrow-collapse-horizontal"
          :loading="merging"
          :disabled="merging || totalItems === 0 || nonEmptyColumnCount <= 1"
          @click="onMergeAll"
        >
          Объединить всё в одну закупку
        </v-btn>
        <v-btn
          v-if="naturalColumnCount > 1"
          variant="outlined"
          color="primary"
          prepend-icon="mdi-arrow-expand-horizontal"
          :loading="splitting"
          :disabled="splitting || totalItems === 0"
          @click="onSplitAll"
        >
          Разложить обратно по категориям
        </v-btn>
      </div>
      <v-spacer />
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
      Заявка уже распределена — состав закупок зафиксирован, изменить нельзя.
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

// Естественная колонка позиции БЕЗ учёта ручного/объединённого target_column_key —
// то, куда позиция попала бы после сброса. Используется, чтобы решить, показывать
// ли кнопку «разложить обратно»: если у всех позиций и так одна и та же реальная
// категория, разложить — значит вернуть их всё в ту же единственную колонку, то
// есть кнопка ничего не изменит и создаст ложное ожидание. В этом случае кнопку
// не показываем вовсе (не просто disabled — чтобы не провоцировать вопрос
// «почему не работает»).
function naturalKey(it: WishItem): string {
  if (it._product_category && it._product_category.trim()) return it._product_category
  return UNCAT_KEY
}
const naturalColumnCount = computed(() => {
  const keys = new Set<string>()
  for (const it of props.items) keys.add(naturalKey(it))
  return keys.size
})

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

// Владелец (2026-09-04, заявка №55): «покупаться-то планируется всё в одной
// фирме — нужна кнопка, которая при распределении все товары в одну закупку
// объединяет». Распределение группирует позиции ПО КОЛОНКАМ (target_column_key),
// одна закупка на непустую колонку (см. _distribute_wish_to_purchases в
// wishes.py) — значит «объединить» = «свести все позиции в одну колонку».
// Целевая колонка — первая НЕПУСТАЯ настоящая категория (не «Не определено»):
// это предсказуемо (совпадает с тем, что пользователь видит крайним слева) и не
// прячет результат в «Не определено» без надобности. Отдельного серверного
// режима нет и не нужен: каждая позиция уходит тем же PATCH /items/{id}, что и
// обычное перетаскивание, поэтому действие полностью обратимо руками (перетащить
// назад) и ничего не отправляет на сервер сверх обычных перемещений.
function pickMergeTargetKey(): string | null {
  const nonEmpty = columns.value.filter(c => c.items.length > 0)
  if (nonEmpty.length === 0) return null
  const realCategory = nonEmpty.find(c => c.key !== UNCAT_KEY)
  return (realCategory || nonEmpty[0]).key
}

const merging = ref(false)
async function onMergeAll() {
  if (props.readonly || merging.value) return
  const targetKey = pickMergeTargetKey()
  if (!targetKey) return
  merging.value = true
  try {
    const toMove = props.items.filter(it => resolveKey(it) !== targetKey)
    let failCount = 0
    for (const item of toMove) {
      const prev = item.target_column_key
      item.target_column_key = targetKey
      try {
        await apiFetch(`/wishes/${props.wishId}/items/${item.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ target_column_key: targetKey }),
        })
      } catch (e: any) {
        item.target_column_key = prev ?? null
        failCount += 1
      }
    }
    if (failCount > 0) {
      emit('error', `Не удалось объединить ${failCount} ${failCount === 1 ? 'позицию' : 'позиций'}`)
    }
  } finally {
    merging.value = false
  }
}

// Обратное действие к onMergeAll (владелец, заявка №55, 2026-09-04): «где кнопка,
// чтобы обратно по разным закупкам разобрать?». Разложить обратно = сбросить
// target_column_key в null у всех позиций — тем же PATCH /items/{id}, что и
// обычное перетаскивание и onMergeAll (второй механизм не заводим, см. ПРАВИЛО
// №5/№6). После сброса позиции сами расходятся по колонкам через resolveKey()
// (fallback на _product_category), поэтому никакой отдельной серверной логики
// не нужно. Действие полностью обратимо: после «разложить» снова доступно
// «объединить», и наоборот.
const splitting = ref(false)
async function onSplitAll() {
  if (props.readonly || splitting.value) return
  splitting.value = true
  try {
    const toReset = props.items.filter(it => it.target_column_key != null && it.target_column_key.trim() !== '')
    let failCount = 0
    for (const item of toReset) {
      const prev = item.target_column_key
      item.target_column_key = null
      try {
        await apiFetch(`/wishes/${props.wishId}/items/${item.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ target_column_key: null }),
        })
      } catch (e: any) {
        item.target_column_key = prev ?? null
        failCount += 1
      }
    }
    if (failCount > 0) {
      emit('error', `Не удалось разложить ${failCount} ${failCount === 1 ? 'позицию' : 'позиций'}`)
    }
  } finally {
    splitting.value = false
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
/* Владелец (2026-09-04): окно распределения должно быть шире, карточки —
   компактнее, а колонки — со СВОЕЙ вертикальной прокруткой (не всего окна),
   чтобы при resize диалога (см. WishesView.vue) doска вела себя предсказуемо.
   Цепочка высот: .wish-kanban (100% высоты диалога) → .wish-kanban-columns
   (flex:1, тянется на всё оставшееся место) → .wish-kanban-col (flex-колонка)
   → .wish-kanban-drop (flex:1 + overflow-y:auto — здесь и скроллится список
   карточек колонки, независимо от соседних колонок). */
.wish-kanban {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.wish-kanban-header {
  flex: 0 0 auto;
}
.wish-kanban-columns {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  overflow-y: hidden;
  flex: 1 1 auto;
  min-height: 0;
  padding-bottom: 8px;
}
.wish-kanban-col {
  flex: 0 0 220px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: rgba(var(--v-theme-surface-variant), 0.35);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: 8px;
}
.wish-kanban-col-head {
  flex: 0 0 auto;
  margin-bottom: 6px;
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.wish-kanban-col-title {
  font-weight: 600;
  font-size: 0.85rem;
  display: flex;
  align-items: center;
}
.wish-kanban-col-meta {
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), 0.65);
  margin-top: 2px;
}
.wish-kanban-drop {
  flex: 1 1 auto;
  min-height: 60px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.wish-kanban-ghost {
  opacity: 0.4;
}
.wish-kanban-actions {
  flex: 0 0 auto;
}
</style>
