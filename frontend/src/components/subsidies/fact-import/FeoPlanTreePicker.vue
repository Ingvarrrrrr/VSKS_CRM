<template>
  <div class="fptp-root">
    <v-text-field
      ref="searchInputEl"
      v-model="searchQuery"
      density="compact"
      variant="outlined"
      hide-details
      clearable
      prepend-inner-icon="mdi-magnify"
      placeholder="Поиск по названию плановой позиции…"
      class="mb-2"
    />

    <div v-if="searchActive && visibleRows.length === 0" class="pa-3 text-caption text-medium-emphasis">
      По «{{ searchQuery.trim() }}» ничего не найдено.
    </div>

    <div v-else class="fptp-scroll">
      <div
        v-for="row in visibleRows"
        :key="row.key"
        class="fptp-row"
        :class="{
          'fptp-row--category': row.isCategory,
          'fptp-row--item': !row.isCategory && !row.part,
          'fptp-row--part': !!row.part,
          'fptp-row--candidate': !row.isCategory && !row.part && candidateIdSet.has(row.item!.id),
        }"
        @click="row.isCategory ? toggleExpand(row.id) : row.part ? selectPart(row.item!, row.part) : selectItem(row.item!)"
      >
        <span v-for="(hasLine, li) in row.ancestorLines" :key="'r' + li" class="fptp-rail" :class="{ 'fptp-rail--line': hasLine }" />
        <span v-if="row.depth > 0" class="fptp-elbow" :class="{ 'fptp-elbow--open': !row.isLast }" />
        <span class="fptp-chevron" @click.stop="row.isCategory ? toggleExpand(row.id) : undefined">
          <v-icon v-if="row.isCategory" size="16" :icon="expanded.has(row.id) ? 'mdi-chevron-down' : 'mdi-chevron-right'" color="grey" />
          <span v-else style="display:inline-block;width:16px" />
        </span>
        <template v-if="row.isCategory">
          <v-icon size="15" class="mr-1 flex-shrink-0" :icon="expanded.has(row.id) ? 'mdi-folder-open' : 'mdi-folder'" color="#3B82F6" />
          <span class="fptp-name">{{ row.name }}</span>
        </template>
        <template v-else-if="row.part">
          <!-- Часть объединённой позиции (план merged-item-parts.md) —
               «стр. 20 — 317 400,00 ₽ · закупка РЕЕ-… / нет закупки». -->
          <v-icon size="13" class="mr-1 flex-shrink-0" icon="mdi-call-split" color="#9333EA" />
          <span class="fptp-name">стр. {{ row.part.row ?? '—' }} — {{ fmt(row.part.amount) }}</span>
          <span class="fptp-residual">
            <template v-if="row.part.purchases?.length">
              {{ row.part.purchases.map(p => p.registry_number || ('#' + p.id)).join(', ') }}
            </template>
            <template v-else>нет закупки</template>
          </span>
        </template>
        <template v-else>
          <v-icon size="15" class="mr-1 flex-shrink-0" icon="mdi-file-document-outline" color="#22C55E" />
          <span class="fptp-name">{{ row.name }}</span>
          <v-chip v-if="candidateIdSet.has(row.item!.id)" size="x-small" color="amber" variant="tonal" class="ml-1">похоже по имени</v-chip>
          <v-chip v-if="row.item!.parts?.length" size="x-small" color="purple" variant="tonal" class="ml-1">{{ row.item!.parts.length }} части</v-chip>
          <span class="fptp-residual">{{ fmt(row.item!.planned_amount) }} · ост. {{ fmt(row.item!.residual) }}</span>
        </template>
      </div>
      <div v-if="visibleRows.length === 0" class="pa-3 text-caption text-medium-emphasis">
        В плане субсидии нет плановых позиций.
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// FeoPlanTreePicker — дерево «Направление › Тип › Подкатегория» с плановыми
// позициями (kind='planned_item') внутри листьев, для пикера строки «Импорт
// факта» (FactImportRowPlanPicker.vue). Решение владельца (прод, субсидия
// «ДНР», строка 151): плоский список /feo-planned-items/match путал («Проезд,
// проживание, питание» — показывало бинты/перчатки, фильтр на «преддрейсовых»
// без результатов подменялся ВСЕМ планом) — тут поиск детерминированный,
// клиентский, без /match (ПРАВИЛО №6 — это НЕ второй движок матчинга строк
// файла, тот остаётся как был: «похожие по имени» выше в FactImportRowPlanPicker
// по-прежнему считает бэкенд; здесь только фильтр уже загруженного дерева по
// тексту, который человек явно печатает в ЭТОМ поле).
//
// Источники данных — оба уже загружены в другом месте, второй раз не грузим:
// nodes — GET /feo-categories/flat (через useFeoLeaves, тот же источник, что
// кормит «Дерево плана закупок»/FeoTreeSelect.vue); plannedItems — переданы
// родителем (plannedResiduals, уже загружен для остатков).
import { computed, nextTick, ref, watch } from 'vue'
import { useFeoLeaves, type FeoNode } from '@/composables/useFeoLeaves'
import type { FeoPlanPosition, FeoPlanPositionPart } from '@/composables/useFeoPlannedResiduals'
import { formatMoney } from '@/utils/formatMoney'
import { normalizeSearchText, searchWords as sharedSearchWords, matchesAllWords } from '@/utils/textSearch'

const props = defineProps<{
  subsidyId: number | null
  /** Только kind='planned_item' — единственное, что можно выбрать (см.
   *  комментарий в FactImportRowPlanPicker.vue про коллизию id-пространств). */
  plannedItems: FeoPlanPosition[]
  /** row.path из FactImportRow — Ур.2/Ур.3/Ур.4 строки файла, для авто-
   *  раскрытия её ветки при открытии. */
  rowPath: string[]
  /** id кандидатов «похожие по имени» (row.match.candidates) — подсветка +
   *  авто-раскрытие их веток. */
  candidateIds: number[]
  /** Открыт ли родительский v-dialog. Компонент НЕ пересоздаётся между
   *  открытиями (row в FactImportRowPlanPicker остаётся заданным после
   *  закрытия — v-if="subsidyId && row" не размонтирует дерево), поэтому
   *  searchQuery/expanded сами по себе переживали закрытие — задание
   *  владельца: сбрасывать поиск и раскрытие заново на КАЖДОЕ открытие
   *  (той же или другой строки), не только на первый монтаж. */
  open: boolean
}>()

// Часть объединённой позиции (план merged-item-parts.md) — partKey=null,
// когда выбрана позиция целиком (как раньше, кликом по самой позиции, не по
// её части — напр. у позиций без parts).
const emit = defineEmits<{ select: [item: FeoPlanPosition, partKey: string | null] }>()

const subsidyIdRef = computed(() => props.subsidyId)
const includeUnfunded = ref(true)
const { feoNodes } = useFeoLeaves({ subsidyId: subsidyIdRef, includeUnfunded })

const searchQuery = ref('')
const searchInputEl = ref<{ focus?: () => void } | null>(null)
const expanded = ref<Set<number>>(new Set())
const candidateIdSet = computed(() => new Set(props.candidateIds))

function fmt(v: number | null | undefined) { return formatMoney(v) }

// ── нормализация для детерминированного поиска (регистр, ё/е, пробелы) —
// общий модуль frontend/src/utils/textSearch.ts (Правило №6, вынесено
// 15.10.2026 вместе с useFeoTreeSearch.ts/ordersSearch.ts), поведение не
// изменилось — та же нормализация, что была здесь раньше. normalize/
// findNodeByPath ниже используют normalizeSearchText напрямую (один сегмент
// пути = одно сравнение, не разбиение на слова).
const normalize = normalizeSearchText
const searchActive = computed(() => searchQuery.value.trim().length > 0)
const queryWords = computed(() => searchActive.value ? sharedSearchWords(searchQuery.value) : [])

function nameMatches(name: string): boolean {
  if (!queryWords.value.length) return true
  return matchesAllWords(name, queryWords.value)
}

const nodeById = computed(() => {
  const m = new Map<number, FeoNode>()
  for (const n of feoNodes.value) m.set(n.id, n)
  return m
})
const childrenByParent = computed(() => {
  const m = new Map<number | null, FeoNode[]>()
  for (const n of feoNodes.value) {
    const key = n.parent_id ?? null
    if (!m.has(key)) m.set(key, [])
    m.get(key)!.push(n)
  }
  return m
})
// Плановые позиции, сгруппированные по категории (прямо в ней — независимо
// от того, есть ли у категории подкатегории: владелец явно просил не
// прятать позиции категории-с-подкатегориями).
const itemsByCategory = computed(() => {
  const m = new Map<number, FeoPlanPosition[]>()
  for (const it of props.plannedItems) {
    const arr = m.get(it.category_id) ?? []
    arr.push(it)
    m.set(it.category_id, arr)
  }
  return m
})

function buildChain(id: number): number[] {
  const result: number[] = []
  let cur = nodeById.value.get(id)
  while (cur) {
    result.push(cur.id)
    cur = cur.parent_id != null ? nodeById.value.get(cur.parent_id) : undefined
  }
  return result.reverse()
}

interface FlatRow {
  key: string
  id: number
  depth: number
  isLast: boolean
  ancestorLines: boolean[]
  isCategory: boolean
  name: string
  item?: FeoPlanPosition
  /** Часть объединённой позиции (план merged-item-parts.md) — строка сама
   *  часть item, не сама позиция (depth = depth позиции + 1). */
  part?: FeoPlanPositionPart
}

/** Разворачивает строку позиции в [позиция, ...её части] — одна функция,
 *  используется обоими деревьями (обычным и поиском, ПРАВИЛО №6). */
function pushItemRows(result: FlatRow[], it: FeoPlanPosition, depth: number, isLast: boolean, ancestorLines: boolean[]) {
  const parts = it.parts ?? []
  result.push({ key: it.key, id: it.id, depth, isLast: isLast && parts.length === 0, ancestorLines, isCategory: false, name: it.name, item: it })
  if (parts.length) {
    const partLines = [...ancestorLines, !isLast]
    parts.forEach((part, pi) => {
      result.push({
        key: `${it.key}::${part.key}`, id: it.id, depth: depth + 1, isLast: pi === parts.length - 1,
        ancestorLines: partLines, isCategory: false, name: it.name, item: it, part,
      })
    })
  }
}

// ── режим без поиска: обычное дерево, раскрытие по expanded ──
function buildPlainTree(): FlatRow[] {
  const result: FlatRow[] = []
  function walk(nodes: FeoNode[], depth: number, ancestorLines: boolean[]) {
    nodes.forEach((node, idx) => {
      const items = itemsByCategory.value.get(node.id) ?? []
      const children = childrenByParent.value.get(node.id) ?? []
      const isLast = idx === nodes.length - 1 && items.length === 0
      result.push({ key: `c-${node.id}`, id: node.id, depth, isLast, ancestorLines, isCategory: true, name: node.name.trim() })
      if (expanded.value.has(node.id)) {
        const childLines = [...ancestorLines, !(idx === nodes.length - 1)]
        if (children.length) walk(children, depth + 1, childLines)
        items.forEach((it, ii) => {
          pushItemRows(result, it, depth + 1, ii === items.length - 1, childLines)
        })
      }
    })
  }
  walk(childrenByParent.value.get(null) ?? [], 0, [])
  return result
}

// ── режим поиска: совпавшие позиции + их предки, автораскрыто ──
function buildSearchTree(): FlatRow[] {
  const matchedItems = props.plannedItems.filter(it => nameMatches(it.name))
  if (!matchedItems.length) return []
  const matchedCategoryIds = new Set<number>()
  const ancestorIds = new Set<number>()
  for (const it of matchedItems) {
    matchedCategoryIds.add(it.category_id)
    for (const aid of buildChain(it.category_id)) ancestorIds.add(aid)
  }
  const visibleCat = (id: number) => matchedCategoryIds.has(id) || ancestorIds.has(id)
  const itemsByCat = new Map<number, FeoPlanPosition[]>()
  for (const it of matchedItems) {
    const arr = itemsByCat.get(it.category_id) ?? []
    arr.push(it)
    itemsByCat.set(it.category_id, arr)
  }

  const result: FlatRow[] = []
  function walk(nodes: FeoNode[], depth: number, ancestorLines: boolean[]) {
    const siblings = nodes.filter(n => visibleCat(n.id))
    siblings.forEach((node, idx) => {
      const items = itemsByCat.get(node.id) ?? []
      const children = (childrenByParent.value.get(node.id) ?? []).filter(n => visibleCat(n.id))
      const isLast = idx === siblings.length - 1 && items.length === 0
      result.push({ key: `c-${node.id}`, id: node.id, depth, isLast, ancestorLines, isCategory: true, name: node.name.trim() })
      const childLines = [...ancestorLines, !(idx === siblings.length - 1)]
      if (children.length) walk(children, depth + 1, childLines)
      items.forEach((it, ii) => {
        pushItemRows(result, it, depth + 1, ii === items.length - 1, childLines)
      })
    })
  }
  walk(childrenByParent.value.get(null) ?? [], 0, [])
  return result
}

const visibleRows = computed(() => searchActive.value ? buildSearchTree() : buildPlainTree())

function toggleExpand(id: number) {
  const s = new Set(expanded.value)
  s.has(id) ? s.delete(id) : s.add(id)
  expanded.value = s
}

function selectItem(item: FeoPlanPosition) {
  emit('select', item, null)
}

function selectPart(item: FeoPlanPosition, part: FeoPlanPositionPart) {
  emit('select', item, part.key)
}

// ── авто-раскрытие при монтировании: ветка строки файла (rowPath) + ветки
// кандидатов «похожие по имени» ──
function normName(s: string) { return normalize(s) }

function findNodeByPath(path: string[]): FeoNode | null {
  const wanted = path.map(normName).filter(Boolean)
  if (!wanted.length) return null
  let candidates = childrenByParent.value.get(null) ?? []
  let node: FeoNode | null = null
  for (const part of wanted) {
    const found = candidates.find(n => normName(n.name) === part)
    if (!found) break
    node = found
    candidates = childrenByParent.value.get(found.id) ?? []
  }
  return node
}

function expandInitial() {
  const s = new Set<number>()
  const rowNode = findNodeByPath(props.rowPath)
  if (rowNode) for (const id of buildChain(rowNode.id)) s.add(id)
  for (const it of props.plannedItems) {
    if (candidateIdSet.value.has(it.id)) {
      for (const id of buildChain(it.category_id)) s.add(id)
    }
  }
  expanded.value = s
}

watch(() => feoNodes.value.length, (n) => { if (n > 0) expandInitial() }, { immediate: true })
watch(() => props.rowPath, () => { if (feoNodes.value.length) expandInitial() })

// Каждое открытие диалога (эта же строка повторно или другая) — поиск с
// чистого листа, раскрытие пересчитано заново (см. комментарий у пропа open).
watch(() => props.open, (isOpen) => {
  if (!isOpen) return
  searchQuery.value = ''
  if (feoNodes.value.length) expandInitial()
  nextTick(() => searchInputEl.value?.focus?.())
})

nextTick(() => searchInputEl.value?.focus?.())
</script>

<style scoped>
.fptp-root { display: flex; flex-direction: column; }
.fptp-scroll { max-height: 360px; overflow-y: auto; border: 1px solid rgba(0,0,0,0.08); border-radius: 4px; }
.fptp-row {
  display: flex; align-items: center; min-height: 28px; padding: 0 8px; cursor: pointer; font-size: 13px; gap: 2px;
}
.fptp-row:hover { background: rgba(0,0,0,0.04); }
.fptp-row--candidate { background: rgba(251, 191, 36, 0.12); }
.fptp-row--part { background: rgba(147, 51, 234, 0.06); }
.fptp-rail, .fptp-elbow { position: relative; width: 16px; align-self: stretch; flex-shrink: 0; }
.fptp-rail--line::before { content: ''; position: absolute; left: 7px; top: 0; bottom: 0; width: 1px; background: rgba(0,0,0,0.15); }
.fptp-elbow::before { content: ''; position: absolute; left: 7px; top: 0; height: 14px; width: 1px; background: rgba(0,0,0,0.15); }
.fptp-elbow::after { content: ''; position: absolute; left: 7px; top: 14px; height: 1px; width: 9px; background: rgba(0,0,0,0.15); }
.fptp-elbow--open::before { height: 100%; }
.fptp-chevron { display: inline-flex; align-items: center; flex-shrink: 0; }
.fptp-name { flex: 1 1 auto; min-width: 0; white-space: normal; word-break: break-word; }
.fptp-residual { margin-left: auto; padding-left: 8px; flex-shrink: 0; font-size: 11px; color: rgba(0,0,0,0.6); white-space: nowrap; }
</style>
