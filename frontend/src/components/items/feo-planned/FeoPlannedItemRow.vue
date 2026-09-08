<template>
  <!-- Строка списка плановых позиций — используется И в компактном (dense-меню), И в
       развёрнутом режиме FeoPlannedItemsSelect.vue (вынесена в общий компонент, чтобы
       разметка/поведение не расходились, ПРАВИЛО №6). role="switch" — клик обрабатывается
       на самом div (не на вложенном <v-switch>, иначе браузер удваивает клик синтетическим
       событием — см. комментарий у onItemRadioClick в useFeoPlannedRows.ts). -->
  <div
    class="feo-tree-row"
    :class="{ 'feo-tree-row--selected': selected, 'feo-tree-row--clickable': !readonly }"
    :title="selected ? 'Нажмите ещё раз, чтобы снять выбор' : undefined"
    role="switch"
    :aria-checked="selected"
    :tabindex="readonly ? -1 : 0"
    @click="emit('toggle', $event)"
    @keydown.enter.prevent="emit('toggle', $event)"
    @keydown.space.prevent="emit('toggle', $event)"
  >
    <span class="feo-tree-rail" />
    <span class="feo-tree-elbow feo-tree-elbow--open" />
    <v-switch
      :model-value="selected"
      :disabled="readonly"
      density="compact"
      hide-details
      color="primary"
      class="feo-planned-switch"
    />
    <span class="feo-tree-name">
      {{ row.name }}
      <span class="feo-planned-qty text-caption text-medium-emphasis">{{ qtyLabel }}</span>
      <v-chip size="x-small" :color="kindColor" variant="tonal" class="ml-1">{{ kindLabel }}</v-chip>
      <v-chip
        v-if="suggestKey === row.key"
        size="x-small"
        color="teal"
        variant="tonal"
        prepend-icon="mdi-auto-fix"
        class="ml-1"
        @click.stop="emit('select')"
      >{{ suggestReason || 'Похоже совпадает' }}</v-chip>
    </span>
    <span class="feo-tree-residual">
      план {{ plannedLabel }} ·
      <span
        v-if="row.kind === 'planned_item'"
        class="feo-planned-consumed-link"
        role="button"
        tabindex="0"
        title="Кто расходует план — показать построчно"
        @click.stop="emit('open-consumers')"
        @keydown.enter.stop.prevent="emit('open-consumers')"
      >выбрано {{ consumedLabel }}<v-icon size="12" icon="mdi-magnify" class="ml-1" /></span>
      <span v-else>выбрано {{ consumedLabel }}</span> ·
      <span :class="residualDisplay.cssClass">{{ residualDisplay.text }}</span>
      <span v-if="shortfallLabel" class="feo-planned-shortfall-note"> — не хватает {{ shortfallLabel }}</span>
    </span>
    <!-- Владелец (сессия 2026-08-19): «где эта корзиночка?» — удаление плановой
         позиции прямо из строки списка, только у kind='planned_item'. @click.stop —
         клик по кнопке НЕ должен сработать как выбор строки. -->
    <v-btn
      v-if="row.kind === 'planned_item' && !readonly"
      icon="mdi-delete-outline"
      variant="text"
      size="x-small"
      color="error"
      class="feo-planned-delete-btn"
      title="Удалить плановую позицию"
      @click.stop="emit('delete')"
    />
  </div>
</template>

<script setup lang="ts">
import type { FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'
import type { PlanResidualDisplay } from '@/utils/numberFormat'

defineProps<{
  row: FeoPlanPosition
  selected: boolean
  readonly?: boolean
  suggestKey?: string | null
  suggestReason?: string | null
  qtyLabel: string
  plannedLabel: string
  consumedLabel: string
  residualDisplay: PlanResidualDisplay
  kindColor: string
  kindLabel: string
  /** Текст «не хватает N ₽» (без тире/приставки) — null, когда позиция не короче
   *  редактируемой суммы (см. isShort в useFeoPlannedRows.ts). */
  shortfallLabel?: string | null
}>()

const emit = defineEmits<{
  /** Клик по всей строке — переключение выбора (см. onItemRadioClick). */
  toggle: [event: Event]
  /** Клик по чипу авто-подсказки — безусловный выбор строки (см. selectItem). */
  select: []
  'open-consumers': []
  delete: []
}>()
</script>

<style scoped src="../feoTreeRails.css"></style>
