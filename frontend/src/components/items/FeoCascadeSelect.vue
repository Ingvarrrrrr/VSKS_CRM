<template>
  <!-- Cascade FEO category selector.
       Renders one v-autocomplete per depth level; each level shows only children
       of the selected parent. Selecting a node on level k resets all levels > k.
       Emits update:modelValue with the leaf id once a leaf node is chosen. -->
  <div class="feo-cascade-select" :class="{ 'is-horizontal': horizontal }">
    <template v-if="nodes.length === 0">
      <v-text-field
        model-value=""
        density="compact"
        variant="outlined"
        hide-details
        disabled
        placeholder="Нет данных ФЭО"
        class="my-1"
      />
    </template>
    <template v-else>
      <div
        v-for="(levelItems, levelIdx) in visibleLevels"
        :key="levelIdx"
      >
        <v-autocomplete
          :model-value="chain[levelIdx] ?? null"
          :items="levelItems"
          item-title="name"
          item-value="id"
          :label="`Уровень ${levelIdx + 1}`"
          density="compact"
          variant="outlined"
          clearable
          hide-details
          class="my-1"
          :disabled="readonly"
          :error="error && levelIdx === visibleLevels.length - 1 && !isLeafSelected"
          @update:model-value="(v: number | null) => onSelect(levelIdx, v)"
        />
      </div>
      <!-- Budget indicator under the last selected leaf -->
      <div v-if="selectedLeaf" class="feo-cascade-note text-caption text-medium-emphasis mt-1 px-1">
        План: {{ fmt(selectedLeaf.budget) }} • Ост.: {{ fmt(selectedLeaf.residual) }}
      </div>
      <div v-if="error && !isLeafSelected" class="feo-cascade-note text-caption text-error mt-1 px-1">
        Обязательно
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { FeoNode, FeoLeaf } from '@/composables/useFeoLeaves'

const props = defineProps<{
  modelValue: number | null
  nodes: FeoNode[]
  leaves: FeoLeaf[]
  readonly?: boolean
  error?: boolean
  horizontal?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [val: number | null]
}>()

// Internal chain of selected ids per level (including intermediate nodes).
// chain[0] = level-0 selection, chain[1] = level-1 selection, etc.
const chain = ref<number[]>([])

// Build childrenByParent map: null key = root nodes
const childrenByParent = computed((): Map<number | null, FeoNode[]> => {
  const map = new Map<number | null, FeoNode[]>()
  for (const node of props.nodes) {
    const key = node.parent_id ?? null
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(node)
  }
  return map
})

// Build id→node lookup for ancestor chain reconstruction
const nodeById = computed((): Map<number, FeoNode> => {
  const map = new Map<number, FeoNode>()
  for (const node of props.nodes) map.set(node.id, node)
  return map
})

// Helper: reconstruct full ancestor chain for a given node id.
function buildChainFor(id: number): number[] {
  const result: number[] = []
  let cur: FeoNode | undefined = nodeById.value.get(id)
  while (cur) {
    result.push(cur.id)
    cur = cur.parent_id != null ? nodeById.value.get(cur.parent_id) : undefined
  }
  return result.reverse()
}

// Watch external modelValue: when it becomes a valid non-null id, rebuild chain from it.
// When it becomes null, leave chain untouched — it is managed by onSelect.
// Also re-run when nodes arrive: modelValue may be seeded before the async
// nodes load finishes (edit-dialog case), so the chain must rebuild afterwards.
watch(
  [() => props.modelValue, nodeById],
  ([val]) => {
    if (val != null && nodeById.value.has(val)) {
      chain.value = buildChainFor(val)
    } else if (val == null) {
      // Cleared externally (e.g. propagation cleared this row) — drop the chain.
      chain.value = []
    }
  },
  { immediate: true }
)

// Build the sequence of level-item arrays to render based on chain.
// Level 0: roots (parent_id=null)
// Level k: children of chain[k-1], if chain[k-1] is defined and node is not a leaf
const visibleLevels = computed((): FeoNode[][] => {
  const levels: FeoNode[][] = []
  const roots = childrenByParent.value.get(null)
  if (!roots || roots.length === 0) return levels
  levels.push(roots)

  for (let i = 0; i < chain.value.length; i++) {
    const selId = chain.value[i]
    const node = nodeById.value.get(selId)
    if (!node) break
    // If selected node is a leaf, no further levels
    if (node.is_leaf) break
    const children = childrenByParent.value.get(selId)
    if (!children || children.length === 0) break
    levels.push(children)
  }

  return levels
})

// Is the last selected node in chain a leaf?
const isLeafSelected = computed((): boolean => {
  if (chain.value.length === 0) return false
  const lastId = chain.value[chain.value.length - 1]
  return nodeById.value.get(lastId)?.is_leaf ?? false
})

// Find the FeoLeaf entry for the current leaf selection (for budget display)
const selectedLeaf = computed((): FeoLeaf | null => {
  if (!isLeafSelected.value) return null
  const lastId = chain.value[chain.value.length - 1]
  return props.leaves.find(l => l.id === lastId) ?? null
})

function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' ₽'
}

function onSelect(levelIdx: number, val: number | null) {
  // Truncate chain to current level (drops all deeper selections)
  chain.value = chain.value.slice(0, levelIdx)

  if (val == null) {
    // Cleared this level — emit null and stop; deeper levels disappear via visibleLevels
    emit('update:modelValue', null)
    return
  }

  const node = nodeById.value.get(val)
  if (!node) return

  chain.value = [...chain.value, val]

  // Emit the selected node id on EVERY level (intermediate or leaf). modelValue
  // here is the cascade *position*, not necessarily a leaf — this lets a parent
  // mirror the same level selection onto other multi-selected rows. The parent
  // is responsible for persisting only leaf nodes as feo_category_id.
  emit('update:modelValue', val)
}
</script>

<style scoped>
.feo-cascade-select {
  /* Compact vertical stack */
  display: flex;
  flex-direction: column;
}
/* Horizontal mode: levels laid side-by-side (used in expand-row to avoid wide column) */
.feo-cascade-select.is-horizontal {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px;
}
.feo-cascade-select.is-horizontal > div {
  flex: 1 1 200px;
  min-width: 170px;
}
.feo-cascade-select.is-horizontal > .feo-cascade-note {
  flex: 1 1 100%;
}
.feo-cascade-select :deep(.v-field__input) {
  font-size: 12px !important;
}
.feo-cascade-select :deep(.v-field__field) {
  font-size: 12px;
}
</style>
