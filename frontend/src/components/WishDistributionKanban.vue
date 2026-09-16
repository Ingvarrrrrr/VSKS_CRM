<template>
  <div class="wish-kanban">
    <div class="wish-kanban-header mb-3">
      <div class="text-caption text-medium-emphasis">
        Распределите позиции по будущим закупкам (колонки = категории товаров). Перетащите карточку
        между колонками, «+ Столбец» — своя колонка под то, чего нет в категориях каталога.
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
      add-column-prefix="Новая категория"
      @change="onColumnChange"
    />

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
// Владелец (2026-09-16, прод): «перетаскивание карточек по категориям было
// решено, при рефакторинге WishesView (commit 8091b92d) угробилось» — на самом
// деле DnD пережил перенос в WishDistributionKanban.vue целиком (см. историю
// файла), просто не показывал ни «+ Столбец», ни полноэкранное окно. Обе вещи
// добавлены здесь на ОБЩЕМ борде — см. components/kanban/CategoryKanbanBoard.vue
// (используется и разбиением закупки, PurchaseSplitKanban.vue — ПРАВИЛО №6, один
// канбан-компонент на оба места). columns — ref (не computed, как было раньше):
// computed не мог держать пустую колонку, добавленную вручную и ещё без позиций.
import { computed, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import CategoryKanbanBoard from '@/components/kanban/CategoryKanbanBoard.vue'
import type { KanbanColumnState } from '@/components/kanban/kanbanTypes'

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

// Real ref state — не computed — чтобы можно было добавить пустую колонку
// («+ Столбец», владелец 2026-09-16) до того, как в неё перетащили хоть одну
// позицию: производный computed от props.items такую колонку не удержал бы.
const columns = ref<KanbanColumnState[]>([])

function rebuildFromProps() {
  const groups = new Map<string, WishItem[]>()
  groups.set(UNCAT_KEY, [])
  for (const it of props.items) {
    const k = resolveKey(it)
    if (!groups.has(k)) groups.set(k, [])
    groups.get(k)!.push(it)
  }
  const out: KanbanColumnState[] = []
  const uncat = groups.get(UNCAT_KEY) || []
  if (uncat.length > 0) out.push({ key: UNCAT_KEY, label: 'Не определено', items: uncat })
  for (const [k, arr] of groups.entries()) {
    if (k === UNCAT_KEY) continue
    out.push({ key: k, label: labelOf(k), items: arr })
  }
  columns.value = out
}
rebuildFromProps()
// deep:false — намеренно: onColumnChange мутирует поля СУЩЕСТВУЮЩИХ элементов
// props.items (тот же массив, что держит родитель), пересборка на это не должна
// реагировать (иначе ручные «+ Столбец» колонки исчезали бы при каждом drag).
watch(() => props.items, rebuildFromProps, { deep: false })

function sumOf(items: WishItem[]): number {
  return items.reduce((s, it) => s + (Number(it.total_price) || 0), 0)
}

const totalItems = computed(() => props.items.length)
const totalAmount = computed(() => sumOf(props.items))
const nonEmptyColumnCount = computed(() => columns.value.filter(c => c.items.length > 0).length)

// Естественная колонка позиции БЕЗ учёта ручного/объединённого target_column_key —
// см. подробное обоснование кнопки «разложить обратно» ниже у onSplitAll.
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

// Перенос элемента между массивами колонок (для отката неудавшегося PATCH —
// см. onColumnChange). vuedraggable уже переместил элемент оптимистично в
// массив колонки-получателя ДО ответа сервера; при ошибке возвращаем его в
// колонку, соответствующую восстановленному target_column_key.
function moveItemToColumnArrays(item: WishItem, targetKey: string) {
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
  if (!added) return // reorder внутри той же колонки или удаление — сохранять нечего
  const item = added.element as WishItem | undefined
  if (!item) return
  const newKey = colKey === UNCAT_KEY ? null : colKey
  if (item.target_column_key === newKey) return
  const prev = item.target_column_key ?? null
  item.target_column_key = newKey
  try {
    await apiFetch(`/wishes/${props.wishId}/items/${item.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ target_column_key: newKey }),
    })
  } catch (e: any) {
    item.target_column_key = prev
    moveItemToColumnArrays(item, resolveKey(item))
    emit('error', e?.payload?.message || e?.message || 'Не удалось сохранить позицию')
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
  // nonEmpty.length>0 гарантирован ранним return выше — non-null assertion
  // безопасен (nonEmpty[0] existence, не noUncheckedIndexedAccess artefact).
  return (realCategory || nonEmpty[0])!.key
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
      moveItemToColumnArrays(item, targetKey)
      try {
        await apiFetch(`/wishes/${props.wishId}/items/${item.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ target_column_key: targetKey }),
        })
      } catch (e: any) {
        item.target_column_key = prev ?? null
        moveItemToColumnArrays(item, resolveKey(item))
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
      moveItemToColumnArrays(item, resolveKey(item))
      try {
        await apiFetch(`/wishes/${props.wishId}/items/${item.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ target_column_key: null }),
        })
      } catch (e: any) {
        item.target_column_key = prev ?? null
        moveItemToColumnArrays(item, resolveKey(item))
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
    emit('error', e?.payload?.message || e?.message || 'Ошибка одобрения распределения')
  } finally {
    approving.value = false
  }
}

// Проброс наверх (WishKanbanDialog.vue) для предупреждения при закрытии окна —
// пустые «+ Столбец»-колонки нигде не хранятся и исчезнут при переоткрытии.
const boardRef = ref<InstanceType<typeof CategoryKanbanBoard> | null>(null)
function vanishingManualColumns(): string[] {
  return boardRef.value?.vanishingManualColumns() ?? []
}
defineExpose({ vanishingManualColumns })
</script>

<style scoped>
/* Владелец (2026-09-04): окно распределения должно быть шире, карточки —
   компактнее, а колонки — со СВОЕЙ вертикальной прокруткой (не всего окна),
   чтобы при resize диалога (см. WishKanbanDialog.vue) доска вела себя предсказуемо.
   Цепочка высот: .wish-kanban (100% высоты диалога) → CategoryKanbanBoard's
   .kb-columns (flex:1, тянется на всё оставшееся место, своя горизонтальная
   прокрутка) → .kb-col (flex-колонка) → .kb-drop (flex:1 + overflow-y:auto —
   здесь и скроллится список карточек колонки, независимо от соседних колонок). */
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
.wish-kanban-actions {
  flex: 0 0 auto;
}
</style>
