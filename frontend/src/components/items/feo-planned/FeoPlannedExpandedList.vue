<template>
  <!-- Обычный (развёрнутый) режим — визуальное продолжение дерева ФЭО (feoTreeRails.css). -->
  <div>
    <!-- «Призрак»: modelValue указывает на позицию, которой нет в items -->
    <div v-if="ghostRow" class="feo-tree-row feo-planned-ghost">
      <span class="feo-tree-rail" />
      <span class="feo-tree-elbow feo-tree-elbow--open" />
      <span class="feo-tree-name">#{{ modelValueId }} (позиция удалена из плана)</span>
      <v-btn size="x-small" variant="text" color="error" @click="$emit('detach-ghost')">Отвязать</v-btn>
    </div>

    <div v-if="filteredItems.length === 0" class="feo-tree-row feo-tree-row--pseudo">
      <span class="feo-tree-rail" /><span class="feo-tree-elbow feo-tree-elbow--open" />
      <span class="feo-tree-name">В этой категории нет плановых позиций</span>
      <v-btn size="x-small" variant="text" color="primary" :disabled="readonly" @click="$emit('create-entry')">Создать в плане закупок</v-btn>
    </div>

    <FeoPlannedItemRow
      v-for="row in filteredItems"
      :key="row.key"
      :row="row"
      :selected="selectedKey === row.key"
      :readonly="readonly"
      :suggest-key="suggestKey"
      :suggest-reason="suggestReason"
      :kind-color="kindChipColor(row.kind)"
      :kind-label="kindChipLabel(row.kind)"
      v-bind="rowDisplayProps(row)"
      @toggle="$emit('toggle', row, $event)"
      @select="$emit('select', row)"
      @open-consumers="$emit('open-consumers', row)"
      @delete="$emit('delete', row)"
    />

    <div class="mt-1">
      <v-btn size="x-small" variant="text" color="primary" prepend-icon="mdi-plus" :disabled="readonly" @click="$emit('create-entry')">
        Создать в плане закупок
      </v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { FeoPlanPosition, FeoPlanKind } from '@/composables/useFeoPlannedResiduals'
import type { FeoPlannedRowDisplay } from '@/composables/items/feoPlanned/useFeoPlannedRows'
import FeoPlannedItemRow from './FeoPlannedItemRow.vue'

defineProps<{
  ghostRow: boolean
  modelValueId?: number | null
  filteredItems: FeoPlanPosition[]
  readonly?: boolean
  selectedKey: string | null
  suggestKey?: string | null
  suggestReason?: string | null
  rowDisplayProps: (row: FeoPlanPosition) => FeoPlannedRowDisplay
  kindChipColor: (kind: FeoPlanKind) => string
  kindChipLabel: (kind: FeoPlanKind) => string
}>()

defineEmits<{
  toggle: [row: FeoPlanPosition, event: Event]
  select: [row: FeoPlanPosition]
  'open-consumers': [row: FeoPlanPosition]
  delete: [row: FeoPlanPosition]
  'detach-ghost': []
  'create-entry': []
}>()
</script>

<style scoped src="../feoTreeRails.css"></style>
