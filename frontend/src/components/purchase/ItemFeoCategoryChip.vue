<template>
  <!-- Владелец (26.09, закупка PEE-2026-00957): «если категория ФЭО разная для
       каждого товара, то в каждом товаре должна быть указана привязка» — раньше
       ItemsTableWish.vue (карточка заявки) вообще не показывала per-item категорию
       ФЭО, хотя WishItem.feo_category_id уже приходит с сервера (см.
       app/services/plan_to_wish.py). Только чтение — сама категория позиции
       управляется в плане закупок/шапке, а не отсюда (см. feoItemLock.ts); никакого
       второго дерева категорий не заводим (Правило №6), имя резолвится из уже
       загруженных узлов дерева ФЭО (feoNodes), второй запрос на позицию не нужен. -->
  <v-tooltip v-if="categoryId != null" :text="pathLabel" location="top" :disabled="!pathLabel">
    <template #activator="{ props: tip }">
      <!-- max-width: длинное имя категории растягивало колонку «Наименование»
           и сжимало «Кол-во»/«Цена» до нечитаемых; полный путь — в тултипе. -->
      <v-chip v-bind="tip" size="x-small" variant="tonal" color="blue-grey" class="mt-1 feo-item-chip"
        :prepend-icon="locked ? 'mdi-lock-outline' : 'mdi-shape-outline'">
        <span class="text-truncate">{{ name || `ФЭО #${categoryId}` }}</span>
      </v-chip>
    </template>
  </v-tooltip>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { FeoNode } from '@/composables/useFeoLeaves'

const props = defineProps<{
  categoryId: number | null | undefined
  nodes: FeoNode[]
  locked?: boolean
}>()

const nodeById = computed(() => new Map(props.nodes.map(n => [n.id, n])))
const node = computed(() => (props.categoryId != null ? nodeById.value.get(props.categoryId) ?? null : null))
const name = computed(() => node.value?.name ?? null)

// Путь «Родитель › Подкатегория › Конечная» для тултипа — тот же обход по
// parent_id, что и у шапочного дерева (CreateOrderView.vue::feoNodeById), но
// собран локально, чтобы не тянуть сюда весь FeoTreeSelect ради одной строки.
const pathLabel = computed(() => {
  if (props.categoryId == null) return ''
  const chain: string[] = []
  const seen = new Set<number>()
  let cur = nodeById.value.get(props.categoryId)
  while (cur && !seen.has(cur.id)) {
    seen.add(cur.id)
    chain.unshift(cur.name)
    cur = cur.parent_id != null ? nodeById.value.get(cur.parent_id) : undefined
  }
  return chain.join(' › ')
})
</script>

<style scoped>
.feo-item-chip {
  max-width: 240px;
}
</style>
