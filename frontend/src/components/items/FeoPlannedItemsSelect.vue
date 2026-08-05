<template>
  <!-- Выбор ПЛАНОВОЙ ПОЗИЦИИ (единый источник /feo-categories/plan-positions —
       конечный элемент дерева ФЭО с планом, статья ФЭО с планом, или детализация
       Ур.5 FeoPlannedItem) — визуально продолжение дерева ФЭО (FeoTreeSelect): те же
       рельсы/локти (feoTreeRails.css), корневая строка — выбранная категория, ниже —
       её плановые позиции (сама категория + дочерние конечные элементы) + строка
       «Вне плана». Радио — нативный <input>, НЕ v-radio-group (ломает flex-строку);
       клик по всей строке = выбор. -->
  <div v-if="categoryId != null" class="feo-planned-select" :class="{ 'feo-planned-select--dense': dense }">
    <!-- skipLast: заявка привязана к промежуточному уровню — плановые позиции недоступны -->
    <template v-if="skipLast">
      <div class="feo-tree-row feo-tree-row--pseudo feo-planned-disabled">
        <v-icon size="16" icon="mdi-clipboard-list-outline" class="mr-1" />
        <span class="feo-tree-name">Заявка привязана к промежуточному уровню ФЭО — плановые позиции недоступны</span>
      </div>
    </template>

    <template v-else>
      <div class="feo-planned-title text-caption font-weight-medium d-flex align-center ga-1 mb-1">
        <v-icon size="16" icon="mdi-clipboard-list-outline" />
        <span>Плановые позиции план-графика</span>
      </div>

      <template v-if="loading">
        <v-skeleton-loader type="list-item-two-line@2" />
      </template>

      <template v-else>
        <!-- Корневая строка — выбранная категория, не кликается -->
        <div class="feo-tree-row feo-tree-row--root">
          <v-icon size="15" class="mr-1 flex-shrink-0" icon="mdi-folder" color="#3B82F6" />
          <span class="feo-tree-name feo-tree-name--root">{{ categoryName }}</span>
        </div>

        <!-- Компактный (dense) режим — свёрнутая строка с разворотом по клику -->
        <template v-if="dense">
          <v-menu v-model="denseMenuOpen" :close-on-content-click="false" location="bottom start">
            <template #activator="{ props: menuActivatorProps }">
              <div v-bind="menuActivatorProps" class="feo-tree-row feo-planned-dense-row">
                <span class="feo-tree-rail" />
                <span class="feo-tree-elbow" />
                <span class="feo-tree-name">{{ denseSummaryLabel }}</span>
                <v-icon size="16" icon="mdi-chevron-down" class="flex-shrink-0" />
              </div>
            </template>
            <v-card class="feo-planned-dense-menu pa-1">
              <div v-if="ghostRow" class="feo-tree-row feo-planned-ghost">
                <span class="feo-tree-rail" />
                <span class="feo-tree-elbow feo-tree-elbow--open" />
                <span class="feo-tree-name">#{{ modelValue?.id }} (позиция удалена из плана)</span>
                <v-btn size="x-small" variant="text" color="error" @click.stop="detachGhost">Отвязать</v-btn>
              </div>
              <div v-if="filteredItems.length === 0" class="feo-tree-row feo-tree-row--pseudo">
                <span class="feo-tree-rail" /><span class="feo-tree-elbow feo-tree-elbow--open" />
                <span class="feo-tree-name">В этой категории нет плановых позиций</span>
                <v-btn size="x-small" variant="text" color="primary" @click.stop="goCreateInPlan">Создать в план-графике</v-btn>
              </div>
              <label
                v-for="row in filteredItems"
                :key="row.key"
                class="feo-tree-row"
                :class="{ 'feo-tree-row--selected': selectedKey === row.key }"
              >
                <span class="feo-tree-rail" />
                <span class="feo-tree-elbow feo-tree-elbow--open" />
                <input
                  type="radio"
                  class="feo-planned-radio"
                  :name="radioName"
                  :checked="selectedKey === row.key"
                  :disabled="readonly"
                  @change="selectItem(row)"
                />
                <span class="feo-tree-name">
                  {{ row.name }}
                  <span class="feo-planned-qty text-caption text-medium-emphasis">{{ fmtQty(row) }}</span>
                  <v-chip size="x-small" :color="kindChipColor(row.kind)" variant="tonal" class="ml-1">{{ kindChipLabel(row.kind) }}</v-chip>
                  <v-chip
                    v-if="suggestKey === row.key"
                    size="x-small"
                    color="teal"
                    variant="tonal"
                    prepend-icon="mdi-auto-fix"
                    class="ml-1"
                    @click.stop="selectItem(row)"
                  >{{ suggestReason || 'Похоже совпадает' }}</v-chip>
                </span>
                <span class="feo-tree-residual">
                  план {{ fmt(row.planned_amount) }} · выбрано {{ fmt(row.consumed) }} ·
                  <span :class="{ 'feo-planned-shortfall': isShort(row) }">остаток {{ fmt(row.residual) }}</span>
                  <span v-if="isShort(row)" class="feo-planned-shortfall-note"> — не хватает {{ fmt(Math.abs(shortfall(row))) }}</span>
                </span>
              </label>
              <label class="feo-tree-row feo-tree-row--pseudo" :class="{ 'feo-tree-row--selected': outOfPlan }">
                <span class="feo-tree-rail" />
                <span class="feo-tree-elbow" />
                <input
                  type="radio"
                  class="feo-planned-radio"
                  :name="radioName"
                  :checked="!!outOfPlan"
                  :disabled="readonly"
                  @change="selectOutOfPlan"
                />
                <span class="feo-tree-name feo-tree-name--pseudo">Вне плана (новая позиция)</span>
              </label>
            </v-card>
          </v-menu>
        </template>

        <!-- Обычный (развёрнутый) режим -->
        <template v-else>
          <!-- «Призрак»: modelValue указывает на позицию, которой нет в items -->
          <div v-if="ghostRow" class="feo-tree-row feo-planned-ghost">
            <span class="feo-tree-rail" />
            <span class="feo-tree-elbow feo-tree-elbow--open" />
            <span class="feo-tree-name">#{{ modelValue?.id }} (позиция удалена из плана)</span>
            <v-btn size="x-small" variant="text" color="error" @click="detachGhost">Отвязать</v-btn>
          </div>

          <div v-if="filteredItems.length === 0" class="feo-tree-row feo-tree-row--pseudo">
            <span class="feo-tree-rail" /><span class="feo-tree-elbow feo-tree-elbow--open" />
            <span class="feo-tree-name">В этой категории нет плановых позиций</span>
            <v-btn size="x-small" variant="text" color="primary" @click="goCreateInPlan">Создать в план-графике</v-btn>
          </div>

          <label
            v-for="row in filteredItems"
            :key="row.key"
            class="feo-tree-row"
            :class="{ 'feo-tree-row--selected': selectedKey === row.key }"
          >
            <span class="feo-tree-rail" />
            <span class="feo-tree-elbow feo-tree-elbow--open" />
            <input
              type="radio"
              class="feo-planned-radio"
              :name="radioName"
              :checked="selectedKey === row.key"
              :disabled="readonly"
              @change="selectItem(row)"
            />
            <span class="feo-tree-name">
              {{ row.name }}
              <span class="feo-planned-qty text-caption text-medium-emphasis">{{ fmtQty(row) }}</span>
              <v-chip size="x-small" :color="kindChipColor(row.kind)" variant="tonal" class="ml-1">{{ kindChipLabel(row.kind) }}</v-chip>
              <v-chip
                v-if="suggestKey === row.key"
                size="x-small"
                color="teal"
                variant="tonal"
                prepend-icon="mdi-auto-fix"
                class="ml-1"
                @click.stop="selectItem(row)"
              >{{ suggestReason || 'Похоже совпадает' }}</v-chip>
            </span>
            <span class="feo-tree-residual">
              план {{ fmt(row.planned_amount) }} · выбрано {{ fmt(row.consumed) }} ·
              <span :class="{ 'feo-planned-shortfall': isShort(row) }">остаток {{ fmt(row.residual) }}</span>
              <span v-if="isShort(row)" class="feo-planned-shortfall-note"> — не хватает {{ fmt(Math.abs(shortfall(row))) }}</span>
            </span>
          </label>

          <!-- Псевдо-строка «Вне плана» — всегда последняя -->
          <label class="feo-tree-row feo-tree-row--pseudo" :class="{ 'feo-tree-row--selected': outOfPlan }">
            <span class="feo-tree-rail" />
            <span class="feo-tree-elbow" />
            <input
              type="radio"
              class="feo-planned-radio"
              :name="radioName"
              :checked="!!outOfPlan"
              :disabled="readonly"
              @change="selectOutOfPlan"
            />
            <span class="feo-tree-name feo-tree-name--pseudo">Вне плана (новая позиция)</span>
          </label>

          <v-alert v-if="outOfPlan" type="warning" density="compact" variant="tonal" class="mt-1">
            Позиция вне плана увеличит плановую сумму ФЭО «{{ categoryName }}» на {{ fmt(amount) }}.
          </v-alert>
        </template>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FeoNode } from '@/composables/useFeoLeaves'
import type { FeoPlanPosition, FeoPlanSelection, FeoPlanKind } from '@/composables/useFeoPlannedResiduals'

const props = defineProps<{
  modelValue: FeoPlanSelection | null
  outOfPlan?: boolean
  categoryId: number | null
  nodes: FeoNode[]
  items: FeoPlanPosition[]
  /** Сумма позиций заявки — чтобы показать нехватку остатка при выборе строки. */
  amount?: number | null
  /** Составной ключ (`${kind}:${id}`) авто-подсказанной строки — см. FeoPlanPosition.key. */
  suggestKey?: string | null
  suggestReason?: string | null
  loading?: boolean
  readonly?: boolean
  skipLast?: boolean
  dense?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [val: FeoPlanSelection | null]
  'update:outOfPlan': [val: boolean]
}>()

const router = useRouter()

// Уникальное имя radio-группы на инстанс — несколько компонентов на странице
// не должны конфликтовать нативной радио-группировкой по имени.
const radioName = `feo-planned-${Math.random().toString(36).slice(2)}`

const denseMenuOpen = ref(false)

const selectedNode = computed((): FeoNode | undefined =>
  props.categoryId != null ? props.nodes.find(n => n.id === props.categoryId) : undefined
)

const categoryName = computed((): string => selectedNode.value?.name?.trim() ?? '—')

const selectedKey = computed((): string | null =>
  props.modelValue ? `${props.modelValue.kind}:${props.modelValue.id}` : null
)

// Рекурсивно собирает id всех потомков узла (по parent_id в nodes) — глубина дерева
// ФЭО может доходить до 6-7 уровней, поэтому обход через стек, а не фиксированную
// вложенность вызовов.
function collectDescendantIds(rootId: number, nodes: FeoNode[]): Set<number> {
  const childrenByParent = new Map<number, number[]>()
  for (const n of nodes) {
    if (n.parent_id != null) {
      const arr = childrenByParent.get(n.parent_id) || []
      arr.push(n.id)
      childrenByParent.set(n.parent_id, arr)
    }
  }
  const result = new Set<number>()
  const stack = [rootId]
  while (stack.length) {
    const id = stack.pop() as number
    for (const childId of childrenByParent.get(id) || []) {
      if (!result.has(childId)) {
        result.add(childId)
        stack.push(childId)
      }
    }
  }
  return result
}

// Родитель может передавать полный список плановых позиций субсидии (все категории) —
// компонент отфильтровывает по своей categoryId + релевантности: (а) сама категория,
// если она конечная и попала в список плановых позиций, и (б) её ДОЧЕРНИЕ конечные
// элементы — пользователь мог выбрать в дереве промежуточный узел («Внедорожник
// повышенной проходимости»), а привязать позицию нужно к дочернему листу
// («Great Wall POER 2026»).
const relevantCategoryIds = computed((): Set<number> => {
  if (props.categoryId == null) return new Set()
  const ids = collectDescendantIds(props.categoryId, props.nodes)
  ids.add(props.categoryId)
  return ids
})

const filteredItems = computed((): FeoPlanPosition[] => {
  if (props.categoryId == null) return []
  const ids = relevantCategoryIds.value
  return props.items.filter(r => ids.has(r.category_id))
})

// modelValue ссылается на строку, которой больше нет среди актуальных (отфильтрованных
// по категории/потомкам) items — либо позицию удалили из план-графика, либо она
// принадлежит категории вне текущей ветки дерева.
const ghostRow = computed((): boolean => {
  if (!props.modelValue) return false
  return !filteredItems.value.some(r => r.key === selectedKey.value)
})

function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' ₽'
}

function fmtQty(row: FeoPlanPosition): string {
  const qty = row.planned_quantity != null ? row.planned_quantity.toLocaleString('ru-RU') : '—'
  return `${qty} ${row.unit || ''}`.trim()
}

function shortfall(row: FeoPlanPosition): number {
  if (props.amount == null) return 0
  return row.residual - props.amount
}

function isShort(row: FeoPlanPosition): boolean {
  return props.amount != null && shortfall(row) < 0
}

const KIND_CHIP_COLOR: Record<FeoPlanKind, string> = {
  plan_position: 'teal',
  feo_article: 'grey',
  planned_item: 'indigo',
}
const KIND_CHIP_LABEL: Record<FeoPlanKind, string> = {
  plan_position: 'плановая позиция',
  feo_article: 'статья ФЭО с планом',
  planned_item: 'детализация',
}
function kindChipColor(kind: FeoPlanKind): string { return KIND_CHIP_COLOR[kind] }
function kindChipLabel(kind: FeoPlanKind): string { return KIND_CHIP_LABEL[kind] }

const denseSummaryLabel = computed((): string => {
  if (props.outOfPlan) return 'Вне плана (новая позиция)'
  const row = selectedKey.value != null ? filteredItems.value.find(r => r.key === selectedKey.value) : undefined
  if (row) return `${row.name} — план ${fmt(row.planned_amount)} · остаток ${fmt(row.residual)}`
  return 'Выбрать плановую позицию'
})

function selectItem(row: FeoPlanPosition) {
  if (props.readonly) return
  emit('update:modelValue', { kind: row.kind, id: row.id })
  if (props.outOfPlan) emit('update:outOfPlan', false)
}

function selectOutOfPlan() {
  if (props.readonly) return
  emit('update:modelValue', null)
  emit('update:outOfPlan', true)
}

function detachGhost() {
  if (props.readonly) return
  emit('update:modelValue', null)
}

function goCreateInPlan() {
  router.push('/subsidies')
}
</script>

<style scoped src="./feoTreeRails.css"></style>
<style scoped>
.feo-planned-select {
  margin-top: 4px;
}
.feo-planned-title {
  color: var(--crm-text-secondary);
}
.feo-planned-disabled {
  cursor: default;
  opacity: 0.85;
}
.feo-planned-radio {
  flex-shrink: 0;
  margin-top: calc((var(--feo-row-line) - 14px) / 2);
  cursor: pointer;
}
.feo-planned-qty {
  margin-left: 6px;
}
.feo-planned-shortfall {
  color: #EF4444;
  font-weight: 700;
}
.feo-planned-shortfall-note {
  color: #EF4444;
  font-weight: 700;
}
.feo-planned-ghost {
  color: #EF4444;
}
.feo-planned-ghost .feo-tree-name {
  color: #EF4444;
}
.feo-planned-dense-row {
  cursor: pointer;
}
.feo-planned-dense-menu {
  max-height: 360px;
  overflow-y: auto;
  min-width: 320px;
}
</style>
