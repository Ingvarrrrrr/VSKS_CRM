<template>
  <div class="rtv">
    <RevisionTotalsHeader />

    <div class="rtv-filter-bar">
      <v-switch
        v-model="changedFilter.onlyChanged.value"
        density="compact" hide-details color="deep-purple"
        :label="changedFilter.onlyChanged.value ? 'Только изменённые' : 'Всё дерево'"
      />
      <template v-if="changedFilter.onlyChanged.value && changedFilter.changedCount.value">
        <span class="text-caption text-medium-emphasis">изменено {{ changedFilter.changedCount.value }} из {{ changedFilter.totalCount.value }}</span>
        <v-btn icon="mdi-chevron-up" size="x-small" variant="text" title="Предыдущее изменение" @click="changedFilter.prev()" />
        <v-btn icon="mdi-chevron-down" size="x-small" variant="text" title="Следующее изменение" @click="changedFilter.next()" />
      </template>
      <v-progress-circular v-if="review.overlay.loading.value" indeterminate size="14" width="2" color="#7c3aed" />
    </div>

    <div v-if="!visibleRows.length" class="rtv-empty text-medium-emphasis">
      {{ review.loadingCategories.value ? 'Загрузка…' : 'Нет строк для отображения' }}
    </div>
    <div v-else class="rtv-rows">
      <RevisionTreeRow
        v-for="row in visibleRows" :key="`${row.kind}-${row.id}`"
        :review="review" :kind="row.kind" :id="row.id" :name="row.name"
        :depth="row.depth" :level="row.level" :has-children="row.hasChildren"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
// Дерево ФЭО проверяющего — волна 3C-доп. (02.10.2026). Владелец: «то же
// дерево Было|Станет, где по умолчанию видны только изменённые строки и
// цепочка статей над ними» — НЕ плоский список (RevisionDiffTable.vue/
// RevisionReviewPanel.vue остаются рядом вкладкой/панелью связок, см.
// SubsidyRevisionReviewView.vue). ТОЛЬКО ЧТЕНИЕ: не переиспользует
// FeoTreeTable.vue/FeoTreeRow.vue (те завязаны на useSubsidyDetailCtx с живым
// D&D и инлайн-правкой полей субсидии — опасно давать проверяющему, см.
// докстринг useRevisionReview.ts/отчёт волны 3C). Иерархия строится из уже
// загруженных review.categories (GET /feo-categories) + create-строк
// корректировки; числа — через review.overlay (useRevisionOverlay.ts,
// Правило №6, второй разбор preview не пишем). Фильтр «только изменённые» —
// useRevisionChangedFilter.ts (тот же composable, что у FeoTreeTable.vue;
// адаптирован, не продублирован — параметр parentOf, см. его докстринг).
import { computed } from 'vue'
import RevisionTotalsHeader from './RevisionTotalsHeader.vue'
import RevisionTreeRow from './RevisionTreeRow.vue'
import { useRevisionChangedFilter } from '@/composables/subsidies/useRevisionChangedFilter'
import type { RevisionReviewApi } from '@/composables/subsidies/useRevisionReview'

const props = defineProps<{ review: RevisionReviewApi }>()
const review = props.review

interface CatNode { id: number; name: string; parent_id: number | null; level: number }

// Категории: живые (GET /feo-categories, review.categories) + ещё не
// сохранённые create-категории этой корректировки — id берём из
// preview.after.ref_map (apply_ops создаёт их по-настоящему внутри
// SAVEPOINT, см. subsidy_revision_preview.py), пока preview не пришёл —
// временно используем сам target_ref строкой (дерево просто не найдёт для
// неё числовых метрик, бейдж покажет 0|0, это нормально до первого refresh).
const categoryNodes = computed<Map<number, CatNode>>(() => {
  const map = new Map<number, CatNode>()
  for (const c of review.categories.value) map.set(c.id, { id: c.id, name: c.name, parent_id: c.parent_id, level: c.level })
  const refMap = review.overlay.preview.value?.after?.ref_map || {}
  for (const op of review.ops.value) {
    if (op.op_type !== 'create' || op.entity_type !== 'feo_category') continue
    const realId = op.target_ref ? refMap[op.target_ref] : undefined
    const id = Number(realId ?? op.target_ref ?? op.id)
    if (map.has(id)) continue
    const parentId = op.parent_ref ? (refMap[op.parent_ref] ?? null) : (op.after?.parent_id ?? null)
    const parentLevel = parentId != null ? (map.get(Number(parentId))?.level ?? 0) : 0
    map.set(id, { id, name: op.after?.name || 'Новая статья', parent_id: parentId != null ? Number(parentId) : null, level: parentLevel + 1 })
  }
  return map
})

function parentOf(categoryId: number): number | null {
  return categoryNodes.value.get(categoryId)?.parent_id ?? null
}

// Позиции: объединение before.items/after.items (удалённая позиция исчезает
// из after, но остаётся в before — см. subsidy_revision_preview.py::_items_view)
// + create-строки позиций ещё без реального id.
interface ItemNode { id: number; name: string; feo_category_id: number | null }
const itemNodes = computed<ItemNode[]>(() => {
  const after = review.overlay.preview.value?.after?.items || {}
  const before = review.overlay.preview.value?.before?.items || {}
  const refMap = review.overlay.preview.value?.after?.ref_map || {}
  const map = new Map<number, ItemNode>()
  for (const [key, it] of Object.entries({ ...before, ...after })) {
    const id = Number(key)
    map.set(id, { id, name: (it as any).name, feo_category_id: (it as any).feo_category_id ?? null })
  }
  for (const op of review.ops.value) {
    if (op.op_type !== 'create' || op.entity_type !== 'feo_item') continue
    const realId = op.target_ref ? refMap[op.target_ref] : undefined
    const id = Number(realId ?? op.target_ref ?? op.id)
    if (map.has(id)) continue
    const catId = op.parent_ref ? (refMap[op.parent_ref] ?? null) : (op.after?.feo_category_id ?? null)
    map.set(id, { id, name: op.after?.name || 'Новая позиция', feo_category_id: catId != null ? Number(catId) : null })
  }
  return [...map.values()]
})

const allCategoryIds = computed(() => [...categoryNodes.value.keys()])
const changedFilter = useRevisionChangedFilter(true, () => review.overlay, () => allCategoryIds.value, parentOf)

interface Row { kind: 'category' | 'item'; id: number; name: string; depth: number; level: number; hasChildren: boolean }

// Плоский обход дерева (корни → дети по sort_order, который уже пришёл
// отсортированным с бэкенда) — позиции категории идут сразу после её строки.
const allRows = computed<Row[]>(() => {
  const nodes = categoryNodes.value
  const childrenOf = new Map<number | null, CatNode[]>()
  for (const n of nodes.values()) {
    const key = n.parent_id
    if (!childrenOf.has(key)) childrenOf.set(key, [])
    childrenOf.get(key)!.push(n)
  }
  const itemsOf = new Map<number, ItemNode[]>()
  for (const it of itemNodes.value) {
    if (it.feo_category_id == null) continue
    if (!itemsOf.has(it.feo_category_id)) itemsOf.set(it.feo_category_id, [])
    itemsOf.get(it.feo_category_id)!.push(it)
  }

  const out: Row[] = []
  function visit(catId: number | null, depth: number) {
    for (const n of childrenOf.get(catId) || []) {
      out.push({ kind: 'category', id: n.id, name: n.name, depth, level: n.level, hasChildren: (childrenOf.get(n.id)?.length || 0) > 0 })
      for (const it of itemsOf.get(n.id) || []) {
        out.push({ kind: 'item', id: it.id, name: it.name, depth: depth + 1, level: n.level + 1, hasChildren: false })
      }
      visit(n.id, depth + 1)
    }
  }
  visit(null, 0)
  return out
})

const visibleRows = computed<Row[]>(() => {
  const visibleCats = changedFilter.visibleCategoryIds.value
  if (!visibleCats) return allRows.value
  return allRows.value.filter((r) => {
    if (r.kind === 'category') return visibleCats.has(r.id)
    // Позиция видна, если её категория видна И сама позиция изменена/новая/
    // удалена (иначе "только изменённые" показал бы ВСЕ позиции видимой
    // категории, а не только реально изменённые — требование владельца).
    const catId = itemNodes.value.find((it) => it.id === r.id)?.feo_category_id
    if (catId == null || !visibleCats.has(catId)) return false
    return review.overlay.isChangedRow('item', r.id) || review.overlay.isNewRow('item', r.id) || review.overlay.isDeletedRow('item', r.id)
  })
})
</script>

<style scoped>
.rtv-filter-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.rtv-empty { padding: 24px 0; text-align: center; }
.rtv-rows { border: 1px solid var(--crm-border-strong); border-radius: 8px; overflow: hidden; max-height: calc(100vh - 320px); overflow-y: auto; }
</style>
