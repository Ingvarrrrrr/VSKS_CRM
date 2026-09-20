<template>
  <!-- CategoryKanbanBoard.vue — ОБЩИЙ канбан-компонент (ПРАВИЛО №6): один
       столбчатый DnD-борд на распределение заявки (WishDistributionKanban.vue)
       и разбиение закупки (PurchaseSplitKanban.vue). Владелец жаловался на два
       расходящихся канбана (2026-09-16) — drag/drop, «+ Столбец», переименование
       и удаление пустой колонки, колёсико = горизонтальная прокрутка и
       автопрокрутка к краю во время перетаскивания теперь живут ЗДЕСЬ один раз;
       персистентность (что делать при переносе карточки) — забота потребителя
       через emit('change'), у каждого канбана свой бэкенд-эндпоинт. -->
  <div ref="columnsRef" class="kb-columns" @wheel="onWheel">
    <div
      v-for="(col, idx) in columns"
      :key="col.key"
      class="kb-col"
      :style="{ flexBasis: columnWidth, maxWidth: columnWidth }"
    >
      <div class="kb-col-head">
        <v-icon v-if="col.key === uncatKey" size="14" class="mr-1" color="grey">mdi-help-circle-outline</v-icon>
        <v-icon v-else size="14" class="mr-1" color="primary">mdi-tag-outline</v-icon>
        <template v-if="!col.editing">
          <span class="kb-col-title" :title="col.label">{{ col.label }}</span>
          <v-btn
            v-if="!readonly && allowAddColumn && col.key !== uncatKey"
            icon="mdi-pencil-outline"
            size="x-small"
            variant="text"
            density="compact"
            @click="col.editing = true"
          />
          <v-btn
            v-if="!readonly && allowAddColumn && !col.items.length && col.key !== uncatKey"
            icon="mdi-close"
            size="x-small"
            variant="text"
            density="compact"
            color="error"
            @click="removeColumn(idx)"
          />
        </template>
        <template v-else>
          <input
            v-model="col.label"
            class="kb-col-input"
            @keyup.enter="finishEditColumn(col)"
            @blur="finishEditColumn(col)"
          />
        </template>
      </div>
      <div class="kb-col-meta">{{ col.items.length }} шт · {{ formatMoney(sumOf(col.items)) }}</div>
      <!-- forceFallback (владелец, 2026-09-17: «открылся большой канбан и тут
           сразу зависает, если пытаюсь что-то перенести из раздела в раздел» —
           разбиение закупки 858, 17 столбцов): по умолчанию Sortable тащит
           нативным HTML5 drag-and-drop, а этот борд одновременно скроллится
           и по вертикали внутри колонки (.kb-drop), и по горизонтали по всей
           полосе столбцов (.kb-columns, :scroll на draggable). Нативный DnD
           программный scrollLeft/scrollTop ВО ВРЕМЯ активного перетаскивания —
           известная связка, на которой Chromium подвешивает курсор перетаскивания
           (сам drag не завершается ни отпусканием кнопки, ни Escape, вкладка
           внешне «зависает», хотя JS-поток не заблокирован). forceFallback
           переключает Sortable на собственную JS-имитацию (плавающий клон
           элемента вместо нативного drag-image) — авто-скролл двигает
           реальный DOM, а не соревнуется с браузерным перетаскиванием. -->
      <draggable
        :list="col.items"
        :group="{ name: groupName, pull: !readonly, put: !readonly }"
        item-key="id"
        :disabled="readonly"
        :animation="150"
        :scroll="true"
        :scroll-sensitivity="80"
        :scroll-speed="14"
        :force-fallback="true"
        :fallback-tolerance="3"
        fallback-class="kb-fallback-drag"
        ghost-class="kb-ghost"
        class="kb-drop"
        @change="(evt: any) => $emit('change', col.key, evt)"
      >
        <template #item="{ element }">
          <WishDistributionCard :item="element" :readonly="readonly" />
        </template>
      </draggable>
    </div>

    <div v-if="!readonly && allowAddColumn" class="kb-col kb-col-add" :style="{ flexBasis: columnWidth, maxWidth: columnWidth }" @click="addColumn">
      <v-icon size="24" color="primary">mdi-plus</v-icon>
      <div class="text-caption text-primary mt-1">Столбец</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
// @ts-ignore - vuedraggable types are loose
import draggable from 'vuedraggable'
import WishDistributionCard from '@/components/WishDistributionCard.vue'
import type { KanbanColumnState } from './kanbanTypes'

// Карточка захардкожена (не слот): vuedraggable v4 инъецирует служебный
// data-draggable/key ПРЯМО на vnode, который вернул слот "item" (см.
// node_modules/vuedraggable/src/core/renderHelper.js::computeNodes) — если
// между этим слотом и реальным элементом стоит ЕЩЁ один forwarding-<slot>
// (было так здесь до фикса 2026-09-16), инъекция достаётся вспомогательному
// slot-vnode, а не настоящей карточке, и Sortable вообще не видит перетаскиваемые
// элементы (drag молча не запускается — ни в native, ни в forceFallback режиме).
// Оба текущих потребителя доски используют одну и ту же карточку — второй
// слой косвенности не нужен и опасен; если когда-нибудь понадобится другая
// карточка, передавать её как component-проп, не как слот.

const props = withDefaults(defineProps<{
  readonly?: boolean
  groupName: string
  allowAddColumn?: boolean
  uncatKey?: string
  addColumnPrefix?: string
  columnWidth?: string
}>(), {
  readonly: false,
  allowAddColumn: true,
  uncatKey: '__uncategorized__',
  addColumnPrefix: 'Столбец',
  columnWidth: '224px',
})

defineEmits<{ (e: 'change', columnKey: string, evt: any): void }>()

const columns = defineModel<KanbanColumnState[]>('columns', { required: true })

function sumOf(items: any[]): number {
  return items.reduce((s, it) => s + (Number(it.total_price) || 0), 0)
}
function formatMoney(v: number | null | undefined): string {
  if (v == null) return '0 ₽'
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(v)
}

function addColumn() {
  if (props.readonly) return
  let n = columns.value.filter(c => c.key !== props.uncatKey).length + 1
  let key = `${props.addColumnPrefix} ${n}`
  while (columns.value.some(c => c.key === key)) {
    n += 1
    key = `${props.addColumnPrefix} ${n}`
  }
  columns.value = [...columns.value, { key, label: key, items: [], editing: true, manual: true }]
}

function removeColumn(idx: number) {
  if (props.readonly) return
  const col = columns.value[idx]
  if (!col || col.key === props.uncatKey || col.items.length) return
  columns.value = columns.value.filter((_, i) => i !== idx)
}

function finishEditColumn(col: KanbanColumnState) {
  const newLabel = (col.label || '').trim()
  if (!newLabel) {
    col.label = col.key
  } else {
    col.key = newLabel
    col.label = newLabel
  }
  col.editing = false
}

// ── Колёсико мыши над областью столбцов = горизонтальная прокрутка (владелец,
// 2026-09-16, «26 столбцов, заебался переключаться»), shift не нужен. Если
// курсор над карточками КОНКРЕТНОЙ колонки и в ней ещё есть куда скроллить
// вертикально в направлении жеста — отдаём вертикали, иначе прокручиваем всю
// полосу столбцов по горизонтали. ──
const columnsRef = ref<HTMLDivElement | null>(null)
function onWheel(e: WheelEvent) {
  if (e.deltaY === 0 && e.deltaX !== 0) return // уже горизонтальный жест (трекпад) — не мешаем
  const dropEl = (e.target as HTMLElement)?.closest?.('.kb-drop') as HTMLElement | null
  if (dropEl) {
    const canScrollDown = e.deltaY > 0 && dropEl.scrollTop + dropEl.clientHeight < dropEl.scrollHeight - 1
    const canScrollUp = e.deltaY < 0 && dropEl.scrollTop > 0
    if (canScrollDown || canScrollUp) return // естественная вертикальная прокрутка колонки
  }
  if (!columnsRef.value) return
  e.preventDefault()
  columnsRef.value.scrollLeft += e.deltaY
}

// Пустые СОЗДАННЫЕ ПОЛЬЗОВАТЕЛЕМ колонки — при следующей пересборке (переоткрытие
// диалога/перезагрузка) исчезнут без следа, т.к. держатся только в памяти этого
// компонента, не в позиции. Потребитель зовёт это перед закрытием диалога, чтобы
// предупредить (владелец, 2026-09-16), не блокируя закрытие.
function vanishingManualColumns(): string[] {
  return columns.value.filter(c => c.manual && c.items.length === 0).map(c => c.label)
}

defineExpose({ addColumn, vanishingManualColumns })
</script>

<style scoped>
.kb-columns {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  overflow-y: hidden;
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
  align-items: stretch;
  padding-bottom: 8px;
}
.kb-col {
  flex: 0 0 224px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: rgba(var(--v-theme-surface-variant), 0.35);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: 8px;
}
.kb-col-head {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  font-weight: 600;
  font-size: 0.82rem;
}
.kb-col-title {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kb-col-meta {
  flex: 0 0 auto;
  font-size: 0.7rem;
  color: rgba(var(--v-theme-on-surface), 0.65);
  margin: 2px 0 6px;
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.kb-drop {
  flex: 1 1 auto;
  min-height: 60px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.kb-ghost {
  opacity: 0.4;
}
/* Плавающий клон карточки при forceFallback — Sortable ставит его position:fixed
   на document.body, вне scroll-контейнеров борда, поэтому overflow их не режет. */
.kb-fallback-drag {
  opacity: 0.9;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.25);
  cursor: grabbing;
  pointer-events: none;
}
.kb-col-input {
  flex: 1;
  background: transparent;
  border: 1px solid rgba(var(--v-border-color), 0.6);
  border-radius: 4px;
  padding: 1px 4px;
  color: inherit;
  font-size: inherit;
  font-family: inherit;
  outline: none;
  min-width: 0;
}
.kb-col-input:focus {
  border-color: rgb(var(--v-theme-primary));
}
.kb-col-add {
  flex: 0 0 140px !important;
  max-width: 140px !important;
  border-style: dashed;
  cursor: pointer;
  align-items: center;
  justify-content: center;
  opacity: 0.65;
  transition: opacity 0.15s;
}
.kb-col-add:hover {
  opacity: 1;
}
</style>
