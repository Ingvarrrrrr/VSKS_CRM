<template>
  <div
    class="rtr-row" :class="[`rtr-row--l${Math.min(depth, 3)}`, { 'rtr-row--blocked': op && review.isBlocked(op) }]"
    :data-feo-node-id="id" :style="{ paddingLeft: `${depth * 18 + 8}px` }"
    @click="onRowClick"
  >
    <v-checkbox-btn
      v-if="op && op.status === 'pending' && !review.isBlocked(op)"
      :model-value="review.isAccepted(op)"
      density="compact" color="success" class="rtr-check"
      @click.stop
      @update:model-value="(v: boolean | null) => op && review.toggleAccept(op.id, !!v)"
    />
    <span v-else class="rtr-check-spacer" />

    <v-icon v-if="kind === 'category'" :icon="hasChildren ? 'mdi-folder' : 'mdi-folder-outline'" size="16" class="mr-1" :color="level === 1 ? '#3B82F6' : level === 2 ? '#F59E0B' : '#22C55E'" />
    <v-icon v-else icon="mdi-clipboard-text-outline" size="14" class="mr-1" color="grey" />

    <span class="rtr-name" :class="{ 'rtr-name--new': isNew, 'rtr-name--deleted': isDeleted }">{{ name }}</span>

    <v-tooltip v-if="op?.review_comment || review.comments[op?.id || -1]" location="top">
      <template #activator="{ props: tProps }">
        <v-icon v-bind="tProps" icon="mdi-comment-text-outline" size="13" color="orange-darken-2" class="ml-1" />
      </template>
      <span>{{ op?.review_comment || review.comments[op?.id || -1] }}</span>
    </v-tooltip>
    <v-menu v-else-if="op && op.status === 'pending'" location="bottom" :close-on-content-click="false">
      <template #activator="{ props: mProps }">
        <v-icon v-bind="mProps" icon="mdi-comment-plus-outline" size="13" color="grey" class="ml-1" @click.stop />
      </template>
      <v-card width="260">
        <v-card-text>
          <v-textarea
            :model-value="review.comments[op.id] || ''"
            density="compact" rows="2" auto-grow hide-details placeholder="Комментарий"
            @update:model-value="(v: string) => op && review.setComment(op.id, v)"
          />
        </v-card-text>
      </v-card>
    </v-menu>

    <span v-if="isBlocked" class="rtr-hint" style="color:#dc2626">зависит от строки №{{ blockingParentId }}</span>
    <span v-if="isDeleted" class="rtr-hint" style="color:#dc2626">будет удалена</span>

    <span class="rtr-metrics">
      <span v-for="m in metrics" :key="m.label" class="rtr-metric">
        <span class="rtr-metric-label">{{ m.label }}</span>
        <RevisionCellBadge :before="m.before" :after="m.after" />
      </span>
    </span>
  </div>
</template>

<script setup lang="ts">
// Одна строка дерева проверки (категория или плановая позиция) — волна 3C,
// вынесена из RevisionTreeView.vue (Правило №5, держим файлы короткими).
// ТОЛЬКО ЧТЕНИЕ: без D&D, без инлайн-редактирования полей субсидии — любая
// правка здесь идёт ТОЛЬКО через решение проверяющего (галочка/комментарий/
// исправленная сумма), не через прямую запись в FeoCategory/FeoPlannedItem.
import { computed } from 'vue'
import RevisionCellBadge from './RevisionCellBadge.vue'
import type { RevisionReviewApi } from '@/composables/subsidies/useRevisionReview'

const props = defineProps<{
  review: RevisionReviewApi
  kind: 'category' | 'item'
  id: number | string
  name: string
  depth: number
  level?: number
  hasChildren?: boolean
}>()
const review = props.review

const op = computed(() => review.opForNode(props.kind, props.id))
const isNew = computed(() => !!review.overlay.isNewRow(props.kind, props.id))
const isDeleted = computed(() => !!review.overlay.isDeletedRow(props.kind, props.id))
const isBlocked = computed(() => !!op.value && review.isBlocked(op.value))
const blockingParentId = computed(() => (op.value ? review.blockingParentId(op.value) : null))
const level = computed(() => props.level ?? 1)
const hasChildren = computed(() => !!props.hasChildren)

// Метрики пары «Было|Станет» — категория: финансирование/плановое кол-во/
// плановая сумма/запланировано/законтрактовано/свободно (требование владельца
// волны 3C-доп., п.1); позиция: количество/сумма. Поля берутся ЧЕРЕЗ
// review.overlay.beforeFieldFor/afterFieldFor — тот же разбор preview.before/
// after.nodes|items, что и FeoTreeRow.vue (Правило №6, свой парсинг не пишем).
const CATEGORY_METRICS: Array<{ field: string; label: string }> = [
  { field: 'budget', label: 'Финанс.' },
  { field: 'display_quantity', label: 'Кол-во' },
  { field: 'plan', label: 'План. сумма' },
  { field: 'display', label: 'Запланир.' },
  { field: 'committed', label: 'Законтр.' },
  { field: 'residual', label: 'Свободно' },
]
const ITEM_METRICS: Array<{ field: string; label: string }> = [
  { field: 'quantity', label: 'Кол-во' },
  { field: 'amount', label: 'Сумма' },
]

const metrics = computed(() => {
  const defs = props.kind === 'category' ? CATEGORY_METRICS : ITEM_METRICS
  return defs.map((m) => ({
    label: m.label,
    before: review.overlay.beforeFieldFor(props.kind, props.id, m.field) ?? 0,
    after: review.overlay.afterFieldFor(props.kind, props.id, m.field) ?? 0,
  }))
})

function onRowClick() {
  if (!op.value) return
  document.querySelector<HTMLElement>(`[data-rev-op-id="${op.value.id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
</script>

<style scoped>
.rtr-row {
  display: flex; align-items: center; flex-wrap: wrap; gap: 2px;
  padding: 5px 8px; border-bottom: 1px solid var(--crm-border); cursor: default;
}
.rtr-row:hover { background: var(--crm-surface-alt); }
.rtr-row--blocked { opacity: 0.55; }
.rtr-check { flex-shrink: 0; }
.rtr-check-spacer { width: 20px; flex-shrink: 0; display: inline-block; }
.rtr-name { font-size: 13px; }
.rtr-row--l1 .rtr-name { font-weight: 700; }
.rtr-row--l2 .rtr-name { font-weight: 600; }
.rtr-name--new { color: #16a34a; font-weight: 700; }
.rtr-name--deleted { color: #dc2626; text-decoration: line-through; }
.rtr-hint { font-size: 11px; color: var(--crm-text-muted); margin-left: 4px; }
.rtr-metrics { display: flex; flex-wrap: wrap; gap: 10px; margin-left: auto; }
.rtr-metric { display: flex; align-items: center; gap: 4px; font-size: 11px; }
.rtr-metric-label { color: var(--crm-text-muted); }
</style>
