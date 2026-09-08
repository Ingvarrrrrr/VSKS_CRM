<template>
  <!-- Компактный (dense) режим — свёрнутая строка с разворотом по клику. Визуально
       продолжение дерева ФЭО (feoTreeRails.css) — см. комментарий в FeoPlannedItemsSelect.vue. -->
  <v-menu :model-value="denseMenuOpen" @update:model-value="$emit('update:denseMenuOpen', $event)" :close-on-content-click="false" location="bottom start">
    <template #activator="{ props: menuActivatorProps }">
      <div v-bind="menuActivatorProps" class="feo-tree-row feo-planned-dense-row">
        <span class="feo-tree-rail" />
        <span class="feo-tree-elbow" />
        <span class="feo-tree-name">
          <template v-if="denseSummaryRow">{{ denseSummaryRow.name }} — план {{ fmt(denseSummaryRow.planned_amount) }} ·
            <span :class="denseResidualDisplay!.cssClass">{{ denseResidualDisplay!.text }}</span>
          </template>
          <template v-else>Выбрать плановую позицию</template>
        </span>
        <v-icon size="16" icon="mdi-chevron-down" class="flex-shrink-0" />
      </div>
    </template>
    <v-card class="feo-planned-dense-menu pa-1">
      <!-- «Призрак»: modelValue указывает на позицию, которой нет в items -->
      <div v-if="ghostRow" class="feo-tree-row feo-planned-ghost">
        <span class="feo-tree-rail" />
        <span class="feo-tree-elbow feo-tree-elbow--open" />
        <span class="feo-tree-name">#{{ modelValueId }} (позиция удалена из плана)</span>
        <v-btn size="x-small" variant="text" color="error" @click.stop="$emit('detach-ghost')">Отвязать</v-btn>
      </div>
      <div v-if="filteredItems.length === 0" class="feo-tree-row feo-tree-row--pseudo">
        <span class="feo-tree-rail" /><span class="feo-tree-elbow feo-tree-elbow--open" />
        <span class="feo-tree-name">В этой категории нет плановых позиций</span>
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
      <!-- Владелец 2026-08-06: кнопка «Создать в плане закупок» доступна ВСЕГДА в
           dense-режиме (не только когда список пуст) — если ни одна из существующих
           плановых позиций категории не подходит для конкретного товара, должна быть
           возможность завести новую, не переключаясь в развёрнутый режим. -->
      <div class="mt-1 px-1">
        <v-btn size="x-small" variant="text" color="primary" prepend-icon="mdi-plus" :disabled="readonly" @click.stop="$emit('create-entry')">
          Создать в плане закупок
        </v-btn>
      </div>
    </v-card>
  </v-menu>
</template>

<script setup lang="ts">
import type { FeoPlanPosition, FeoPlanKind } from '@/composables/useFeoPlannedResiduals'
import type { FeoPlannedRowDisplay } from '@/composables/items/feoPlanned/useFeoPlannedRows'
import type { PlanResidualDisplay } from '@/utils/numberFormat'
import FeoPlannedItemRow from './FeoPlannedItemRow.vue'

defineProps<{
  denseMenuOpen: boolean
  denseSummaryRow?: FeoPlanPosition
  denseResidualDisplay?: PlanResidualDisplay | null
  ghostRow: boolean
  modelValueId?: number | null
  filteredItems: FeoPlanPosition[]
  readonly?: boolean
  selectedKey: string | null
  suggestKey?: string | null
  suggestReason?: string | null
  fmt: (v: number | null | undefined) => string
  rowDisplayProps: (row: FeoPlanPosition) => FeoPlannedRowDisplay
  kindChipColor: (kind: FeoPlanKind) => string
  kindChipLabel: (kind: FeoPlanKind) => string
}>()

defineEmits<{
  'update:denseMenuOpen': [value: boolean]
  toggle: [row: FeoPlanPosition, event: Event]
  select: [row: FeoPlanPosition]
  'open-consumers': [row: FeoPlanPosition]
  delete: [row: FeoPlanPosition]
  'detach-ghost': []
  'create-entry': []
}>()
</script>

<style scoped src="../feoTreeRails.css"></style>
