<template>
  <div class="rev-diff-table">
    <table class="rdt-table">
      <thead>
        <tr>
          <th class="rdt-th">Где</th>
          <th class="rdt-th rdt-th-num">Было</th>
          <th class="rdt-th rdt-th-num">Станет</th>
          <th class="rdt-th rdt-th-num">Законтрактовано</th>
          <th class="rdt-th">Решение</th>
          <th class="rdt-th">Комментарий</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="op in rows" :key="op.id" :data-rev-op-id="op.id" class="rdt-tr" :class="{ 'rdt-tr--blocked': review.isBlocked(op) }">
          <td class="rdt-td">
            {{ op.path || opFallbackPath(op) }}
            <v-chip v-if="op.op_type === 'create'" size="x-small" color="success" variant="tonal" class="ml-1">новая</v-chip>
            <v-chip v-if="op.op_type === 'delete'" size="x-small" color="error" variant="tonal" class="ml-1">удалить</v-chip>
            <v-chip v-if="op.bundle_no" size="x-small" color="indigo" variant="tonal" class="ml-1">Связка {{ op.bundle_no }}</v-chip>
            <v-chip v-if="op.added_by_reviewer" size="x-small" color="orange" variant="tonal" class="ml-1">от проверяющего</v-chip>
            <div v-if="review.isBlocked(op)" class="text-caption" style="color:#dc2626">
              зависит от строки №{{ review.blockingParentId(op) }} (отклонена)
            </div>
          </td>
          <td class="rdt-td rdt-td-num">
            <template v-if="op.op_type === 'create'">—</template>
            <template v-else-if="op.op_type === 'delete'">{{ opSummary(op) }}</template>
            <template v-else>
              <div v-for="c in changesFor(op)" :key="c.field" class="rdt-field-line">{{ c.label }}: {{ c.before }}</div>
            </template>
          </td>
          <td class="rdt-td rdt-td-num">
            <template v-if="op.op_type === 'delete'">—</template>
            <template v-else-if="op.op_type === 'create'">{{ opSummary(op) }}</template>
            <template v-else>
              <div v-for="c in changesFor(op)" :key="c.field" class="rdt-field-line">
                {{ c.label }}: {{ c.after }}<span v-if="c.delta" class="rdt-field-delta"> ({{ c.delta }})</span>
              </div>
            </template>
          </td>
          <td class="rdt-td rdt-td-num">{{ committedFor(op) }}</td>
          <td class="rdt-td">
            <template v-if="op.status !== 'pending'">
              <v-chip size="x-small" :color="statusColor(op.status)" variant="flat">{{ statusLabel(op.status) }}</v-chip>
            </template>
            <template v-else-if="review.isBlocked(op)">
              <v-chip size="x-small" color="grey" variant="tonal">будет отклонена</v-chip>
            </template>
            <template v-else>
              <v-chip size="x-small" :color="review.isAccepted(op) ? 'success' : 'error'" variant="tonal">
                {{ review.isAccepted(op) ? 'принять' : 'отклонить' }}
              </v-chip>
            </template>
          </td>
          <td class="rdt-td">{{ op.review_comment || review.comments[op.id] || '—' }}</td>
        </tr>
        <tr v-if="!rows.length">
          <td class="rdt-td text-medium-emphasis" colspan="6">Нет строк</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
// Вкладка «Список изменений» экрана проверяющего — волна 3C. Чисто табличное
// представление ВСЕХ строк корректировки (путь/было/станет/законтрактовано/
// решение/комментарий), рядом с деревом ФЭО (RevisionReviewPanel.vue) —
// требование владельца п.10. Источник решений/состояния — useRevisionReview.ts
// (Правило №6, свой стейт здесь не заводится).
import { computed } from 'vue'
import { formatCurrency } from '@/composables/subsidies/format'
import { formatOpChanges, formatOpSummary } from '@/composables/subsidies/revisionFormat'
import type { RevisionReviewApi, ReviewOp } from '@/composables/subsidies/useRevisionReview'

const props = defineProps<{ review: RevisionReviewApi }>()
const review = props.review

const rows = computed<ReviewOp[]>(() => review.ops.value)

function opFallbackPath(op: ReviewOp): string {
  return `${op.entity_type === 'feo_category' ? 'Статья' : op.entity_type === 'feo_item' ? 'Позиция' : 'Субсидия'} #${op.target_id ?? op.target_ref}`
}
// Эффективное "станет" — с учётом reviewer_after, если строка принята (тот же
// приём, что раньше делал formatValue(op.reviewer_after && review.isAccepted(op)
// ? op.reviewer_after : op.after)) — изменённые поля и их русские подписи
// считает formatOpChanges (revisionFormat.ts, Правило №6, одна функция на
// RevisionDraftBar.vue/RevisionReviewPanel.vue/RevisionDiffTable.vue).
function effectiveAfter(op: ReviewOp): any {
  if (op.reviewer_after && review.isAccepted(op)) return { ...op.after, ...op.reviewer_after }
  return op.after
}
function changesFor(op: ReviewOp) {
  return formatOpChanges({ op_type: op.op_type, before: op.before, after: effectiveAfter(op) })
}
function opSummary(op: ReviewOp): string {
  return formatOpSummary({ op_type: op.op_type, before: op.before, after: effectiveAfter(op) })
}
// «Законтрактовано» — только для плановых позиций/категорий, где before нёс
// служебный снимок _committed* (см. subsidy_revision_ops.add_op у delete, и
// subsidy_revision_floor.check_floor у update) — другого источника здесь нет,
// второй раз committed_amounts не запрашиваем (Правило №6, это только отображение
// уже имеющегося в ops снимка, не новый расчёт).
function committedFor(op: ReviewOp): string {
  const before = op.before || {}
  const committed = before._committed_amount ?? before._committed
  return committed != null ? formatCurrency(Number(committed)) : '—'
}
function statusLabel(status: string): string {
  if (status === 'applied') return 'применена'
  if (status === 'rejected') return 'отклонена'
  if (status === 'auto_rejected') return 'отклонена (зависимая)'
  return status
}
function statusColor(status: string): string {
  if (status === 'applied') return 'success'
  if (status === 'rejected' || status === 'auto_rejected') return 'error'
  return 'grey'
}
</script>

<style scoped>
.rev-diff-table { overflow-x: auto; border: 1px solid var(--crm-border-strong); border-radius: 8px; }
.rdt-table { width: 100%; border-collapse: collapse; min-width: 760px; }
.rdt-th {
  font-size: 11px; font-weight: 600; color: var(--crm-text-muted); text-transform: uppercase;
  letter-spacing: 0.05em; background: var(--crm-table-header); padding: 8px 10px; text-align: left;
  border-bottom: 1px solid var(--crm-border-strong); position: sticky; top: 0;
}
.rdt-th-num { text-align: right; }
.rdt-td { padding: 8px 10px; border-bottom: 1px solid var(--crm-border); font-size: 13px; vertical-align: top; }
.rdt-td-num { text-align: right; white-space: nowrap; }
.rdt-tr--blocked { opacity: 0.6; }
.rdt-field-line { white-space: nowrap; }
.rdt-field-delta { color: var(--crm-text-muted); }
</style>
