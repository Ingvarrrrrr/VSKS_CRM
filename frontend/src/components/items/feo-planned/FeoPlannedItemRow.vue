<template>
  <!-- Строка списка плановых позиций — используется И в компактном (dense-меню), И в
       развёрнутом режиме FeoPlannedItemsSelect.vue (вынесена в общий компонент, чтобы
       разметка/поведение не расходились, ПРАВИЛО №6). role="switch" — клик обрабатывается
       на самом div (не на вложенном <v-switch>, иначе браузер удваивает клик синтетическим
       событием — см. комментарий у onItemRadioClick в useFeoPlannedRows.ts). -->
  <div
    class="feo-tree-row"
    :class="[
      getRowMarkClasses('feo_item', row.id),
      { 'feo-tree-row--selected': selected, 'feo-tree-row--clickable': !readonly }
    ]"
    :style="getRowMarkStyle('feo_item', row.id)"
    :data-gala-focus="`feo_item:${row.id}`"
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
    <span
      class="feo-tree-name"
      :class="getCellMarkClasses('feo_item', row.id, 'name')"
      :style="getCellMarkStyle('feo_item', row.id, 'name')"
      @click="onCellClick($event, { entityType: 'feo_item', entityId: row.id, fieldName: 'name' })"
      @contextmenu.prevent.stop="onNameContextMenu"
    >
      {{ row.name }}
      <span
        class="feo-planned-qty text-caption text-medium-emphasis"
        :class="getCellMarkClasses('feo_item', row.id, 'quantity')"
        :style="getCellMarkStyle('feo_item', row.id, 'quantity')"
        @click.stop="onCellClick($event, { entityType: 'feo_item', entityId: row.id, fieldName: 'quantity' })"
        @contextmenu.prevent.stop="onQtyContextMenu"
      >{{ qtyLabel }}</span>
      <v-chip size="x-small" :color="kindColor" variant="tonal" class="ml-1">{{ kindLabel }}</v-chip>
      <!-- Составная позиция (задача «Составная плановая позиция») — см.
           докстринг FeoPlannedItem.is_composite: несколько строк закупки на
           эту позицию не складывают количество между собой. -->
      <v-chip
        v-if="row.is_composite"
        size="x-small"
        color="indigo"
        variant="tonal"
        class="ml-1"
        title="Несколько услуг на одно количество — строки закупки не складывают количество между собой"
      >составная</v-chip>
      <v-chip
        v-if="suggestKey === row.key"
        size="x-small"
        color="teal"
        variant="tonal"
        prepend-icon="mdi-auto-fix"
        class="ml-1"
        @click.stop="emit('select')"
      >{{ suggestReason || 'Похоже совпадает' }}</v-chip>
      <PlannedStoreOffersBadge :name="row.name" />
    </span>
    <FeoPlanResidualSummary
      :row="row"
      :planned-label="plannedLabel"
      :consumed-label="consumedLabel"
      :residual-display="residualDisplay"
      :shortfall-label="shortfallLabel"
      show-consumers-link
      :class="getCellMarkClasses('feo_item', row.id, 'amount')"
      :style="getCellMarkStyle('feo_item', row.id, 'amount')"
      @click="onCellClick($event, { entityType: 'feo_item', entityId: row.id, fieldName: 'amount' })"
      @open-consumers="emit('open-consumers')"
      @contextmenu.prevent.stop="onAmountContextMenu"
    />
    <template v-if="row.linked_purchases?.length || row.linked_wishes?.length">
      · <FeoPlannedTakenBy :linked-purchases="row.linked_purchases" :linked-wishes="row.linked_wishes" short />
    </template>
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
import { onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import type { FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'
import type { PlanResidualDisplay } from '@/utils/numberFormat'
import { useGalaContextMenu } from '@/composables/useGalaContextMenu'
import { useCellMarks, type CellTarget } from '@/composables/useCellMarks'
import FeoPlannedTakenBy from './FeoPlannedTakenBy.vue'
import FeoPlanResidualSummary from './FeoPlanResidualSummary.vue'
import PlannedStoreOffersBadge from '@/components/products/PlannedStoreOffersBadge.vue'

const props = defineProps<{
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
  refresh: []
}>()

const router = useRouter()
const { openCellContextMenu } = useGalaContextMenu()
const cellMarks = useCellMarks()
const { getRowMarkClasses, getRowMarkStyle, getCellMarkClasses, getCellMarkStyle } = cellMarks

function onCellClick(event: MouseEvent, target: CellTarget) {
  if (cellMarks.handleCellSelectClick(event, target)) {
    event.stopPropagation()
    return
  }
  const el = event.currentTarget as HTMLElement | null
  if (el) {
    const rect = el.getBoundingClientRect()
    const isTopRight = event.clientX >= rect.right - 18 && event.clientY <= rect.top + 18
    const mark = cellMarks.getMark(target.entityType, Number(target.entityId), target.fieldName)
    if (isTopRight && mark?.comment) {
      event.stopPropagation()
      cellMarks.openCommentAt(event, target)
    }
  }
}

function getItemExtraItems() {
  return [
    {
      key: 'create_wish',
      label: '🛒 Создать заявку в этой категории',
      icon: 'mdi-cart-plus',
      onClick: () => {
        router.push({
          path: '/wishes',
          query: {
            feo_category_id: String((props.row as any).feo_category_id || ''),
            subsidy_id: String((props.row as any).subsidy_id || ''),
          },
        })
      },
    },
    {
      key: 'edit_item',
      label: '✏️ Редактировать позицию',
      icon: 'mdi-pencil',
      onClick: () => {
        emit('toggle', new MouseEvent('click'))
      },
    },
  ]
}

function onNameContextMenu(e: MouseEvent) {
  if (props.row.id) {
    openCellContextMenu(e, {
      entityType: 'feo_item',
      entityId: props.row.id,
      fieldName: 'name',
      fieldLabel: 'Наименование',
      cellValue: props.row.name,
      subsidyId: (props.row as any).subsidy_id ?? null,
      extraItems: getItemExtraItems(),
    } as any)
  }
}

function onQtyContextMenu(e: MouseEvent) {
  if (props.row.id) {
    openCellContextMenu(e, {
      entityType: 'feo_item',
      entityId: props.row.id,
      fieldName: 'quantity',
      fieldLabel: 'Количество',
      cellValue: props.row.quantity,
      rawNumber: props.row.quantity,
      subsidyId: (props.row as any).subsidy_id ?? null,
      extraItems: getItemExtraItems(),
    } as any)
  }
}

function onAmountContextMenu(e: MouseEvent) {
  if (props.row.id) {
    openCellContextMenu(e, {
      entityType: 'feo_item',
      entityId: props.row.id,
      fieldName: 'amount',
      fieldLabel: 'Сумма (план)',
      cellValue: props.row.amount,
      rawNumber: props.row.amount,
      subsidyId: (props.row as any).subsidy_id ?? null,
      extraItems: getItemExtraItems(),
    } as any)
  }
}

function onEntityRestored(e: Event) {
  const customEv = e as CustomEvent<{ entityType: string; entityId: number | string }>
  if (customEv.detail?.entityType === 'feo_item' && customEv.detail?.entityId === props.row.id) {
    emit('refresh')
  }
}

onMounted(() => {
  window.addEventListener('gala:entity-restored', onEntityRestored)
  if (props.row?.id) {
    void cellMarks.loadMarks('feo_item', [props.row.id], (props.row as any).subsidy_id)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('gala:entity-restored', onEntityRestored)
})
</script>

<style scoped src="../feoTreeRails.css"></style>
