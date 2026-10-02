<template>
  <div class="rrp">
    <div class="rrp-filter-bar">
      <v-switch
        v-model="onlyPending" density="compact" hide-details color="deep-purple"
        :label="onlyPending ? 'Только ожидающие решения' : 'Все строки (включая решённые)'"
      />
      <template v-if="rows.length">
        <span class="text-caption text-medium-emphasis">строк: {{ rows.length }}</span>
        <v-btn icon="mdi-chevron-up" size="x-small" variant="text" title="Предыдущая" @click="goTo(cursor - 1)" />
        <v-btn icon="mdi-chevron-down" size="x-small" variant="text" title="Следующая" @click="goTo(cursor + 1)" />
      </template>
      <v-progress-circular v-if="review.overlay.loading.value" indeterminate size="14" width="2" color="#7c3aed" />
    </div>

    <div v-if="!rows.length" class="rrp-empty text-medium-emphasis">Нет строк для отображения</div>

    <div v-for="group in groupedRows" :key="group.bundleNo ?? '__none'" class="rrp-group">
      <div v-if="group.bundleNo" class="rrp-bundle-strip" :class="{ 'rrp-bundle-strip--bad': (bundleInfo(group.bundleNo)?.shortfall || 0) > 0.5 }">
        <v-icon icon="mdi-link-variant" size="14" class="mr-1" />
        Связка {{ group.bundleNo }}: {{ bundleMoneyLine(group.bundleNo) }}
        <template v-if="(bundleInfo(group.bundleNo)?.shortfall || 0) > 0.5">
          <v-btn size="x-small" variant="tonal" color="error" class="ml-1" @click="openExtraDialog(group.bundleNo)">Снять с другой позиции</v-btn>
        </template>
      </div>

      <div v-for="op in group.ops" :key="op.id" class="rrp-row" :data-rev-op-id="op.id" :class="{ 'rrp-row--blocked': review.isBlocked(op) }" @click="scrollToTreeNode(op)">
        <div class="rrp-row-main">
          <v-checkbox-btn
            v-if="op.status === 'pending' && !review.isBlocked(op)"
            :model-value="review.isAccepted(op)"
            density="compact" color="success"
            @update:model-value="(v: boolean | null) => review.toggleAccept(op.id, !!v)"
          />
          <v-icon v-else-if="review.isBlocked(op)" icon="mdi-link-off" size="16" color="grey" class="mr-1" />
          <v-chip v-else size="x-small" :color="op.status === 'applied' ? 'success' : 'error'" variant="flat" class="mr-1">
            {{ op.status === 'applied' ? 'применена' : op.status === 'rejected' ? 'отклонена' : 'отклонена (завис.)' }}
          </v-chip>

          <div class="rrp-row-body">
            <div class="rrp-row-path">
              {{ op.path || opFallbackPath(op) }}
              <v-chip v-if="op.op_type === 'create'" size="x-small" color="success" variant="tonal" class="ml-1">новая</v-chip>
              <v-chip v-if="op.op_type === 'delete'" size="x-small" color="error" variant="tonal" class="ml-1">удалить</v-chip>
              <v-chip v-if="op.added_by_reviewer" size="x-small" color="orange" variant="tonal" class="ml-1">от проверяющего</v-chip>
            </div>
            <div v-if="review.isBlocked(op)" class="rrp-row-hint" style="color:#dc2626">
              зависит от строки №{{ review.blockingParentId(op) }} (отклонена)
            </div>

            <div v-if="changeSummary(op)" class="rrp-row-summary text-caption text-medium-emphasis">{{ changeSummary(op) }}</div>

            <div v-if="primaryField(op)" class="rrp-row-amount">
              <RevisionCellBadge :before="Number(op.before?.[primaryField(op)!] ?? 0)" :after="editableAfter(op)" />
              <v-text-field
                v-if="op.status === 'pending' && review.isAccepted(op)"
                :model-value="formatInt(overrideValue(op))"
                type="text" inputmode="decimal" density="compact" variant="outlined" hide-details
                style="width:180px; min-width:180px" class="ml-2"
                label="исправить «станет»"
                @update:model-value="(v: string) => onOverrideInput(op, v)"
              />
              <v-btn
                v-if="op.status === 'pending' && review.isAccepted(op) && isIncreaseOp(op)"
                size="x-small" variant="tonal" color="error" class="ml-2"
                @click="openExtraDialog(op.bundle_no)"
              >Снять с другой позиции</v-btn>
            </div>

            <v-text-field
              v-if="op.status === 'pending'"
              :model-value="review.comments[op.id] || ''"
              density="compact" variant="outlined" hide-details placeholder="Комментарий к решению (необязательно)"
              class="rrp-row-comment" style="width:100%"
              @update:model-value="(v: string) => review.setComment(op.id, v)"
            />
            <div v-else-if="op.review_comment" class="rrp-row-hint">«{{ op.review_comment }}»</div>
          </div>
        </div>
      </div>
    </div>

    <v-dialog v-model="extraDialog.open" max-width="520">
      <v-card>
        <v-card-title class="text-subtitle-1">Снять с другой позиции субсидии</v-card-title>
        <v-card-text>
          <div class="text-caption text-medium-emphasis mb-2">
            Выберите плановую позицию субсидии и сумму, которую снять с нее в пользу связки
            {{ extraDialog.bundleNo }}. Строка подписывается «добавлено проверяющим» и учитывается в предпросмотре.
          </div>
          <v-select
            v-model="extraDialog.targetId"
            :items="itemPickerOptions"
            label="Плановая позиция" density="compact" hide-details class="mb-3"
          />
          <v-text-field
            v-model.number="extraDialog.removeAmount"
            type="number" label="Сумма снятия" density="compact" hide-details
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="extraDialog.open = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :disabled="!extraDialog.targetId || !extraDialog.removeAmount" @click="confirmExtra">Добавить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
// Основная панель экрана проверяющего — волна 3C. НЕ переиспользует
// FeoTreeTable.vue/FeoTreeRow.vue напрямую: та пара жёстко завязана на
// useSubsidyDetailCtx() (D&D, инлайн-редактирование полей субсидии, KPI) —
// открыть её для проверяющего означало бы дать ему те же клики, что и
// автору, то есть случайную ПРЯМУЮ правку живых данных мимо корректировки
// (opасно для режима 'direct' у проверяющего с правом «Утверждать субсидию»).
// Вместо этого — список строк корректировки (ops), сгруппированный по
// связкам, с теми же примитивами показа «было/станет», что и у дерева
// автора (RevisionCellBadge.vue/RevisionTotalsHeader.vue, тот же инжект
// useRevisionOverlay() — провайднут useRevisionReview.ts через
// provideRevisionReviewOverlay, Правило №6: расчёт один).
import { computed, reactive, ref } from 'vue'
import { formatCurrency } from '@/composables/subsidies/format'
import { formatOpSummary, formatBundleMoneyLine } from '@/composables/subsidies/revisionFormat'
import RevisionCellBadge from './RevisionCellBadge.vue'
import type { RevisionReviewApi, ReviewOp } from '@/composables/subsidies/useRevisionReview'

const props = defineProps<{ review: RevisionReviewApi }>()
const review = props.review

const onlyPending = ref(true)
const cursor = ref(0)

const rows = computed<ReviewOp[]>(() => onlyPending.value ? review.pendingOps.value : review.ops.value)

interface Group { bundleNo: number | null; ops: ReviewOp[] }
const groupedRows = computed<Group[]>(() => {
  const map = new Map<number | null, ReviewOp[]>()
  for (const op of rows.value) {
    const key = op.bundle_no ?? null
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(op)
  }
  // Связки — впереди (у них есть что показать в шапке), затем строки без связки.
  return [...map.entries()]
    .sort((a, b) => (a[0] ? 0 : 1) - (b[0] ? 0 : 1))
    .map(([bundleNo, ops]) => ({ bundleNo, ops }))
})

function bundleInfo(bundleNo: number) {
  return review.overlay.preview.value?.bundles?.find((b) => b.bundle_no === bundleNo) || null
}

// Строка шапки связки — тот же язык, что и у общего баннера нехватки
// (SubsidyRevisionReviewView.vue), одна функция на оба места (Правило №6).
function bundleMoneyLine(bundleNo: number): string {
  const b = bundleInfo(bundleNo)
  return formatBundleMoneyLine(b?.added || 0, b?.removed || 0, b?.shortfall || 0)
}

// Сводка изменённых полей строки (приёмка 02.10, п.8) — та же функция, что и
// у RevisionDraftBar.vue/RevisionDiffTable.vue (Правило №6). reviewer_after
// подмешиваем, если проверяющий уже исправил сумму и строка принята — иначе
// подпись показывала бы предложение автора, а не то, что реально применится.
function changeSummary(op: ReviewOp): string {
  const after = (op.reviewer_after && review.isAccepted(op)) ? { ...op.after, ...op.reviewer_after } : op.after
  return formatOpSummary({ op_type: op.op_type, before: op.before, after })
}

function goTo(i: number) {
  if (!rows.value.length) return
  const idx = ((i % rows.value.length) + rows.value.length) % rows.value.length
  cursor.value = idx
  const id = rows.value[idx]?.id
  if (id != null) {
    document.querySelector<HTMLElement>(`[data-rev-op-id="${id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

function opFallbackPath(op: ReviewOp): string {
  return `${op.entity_type === 'feo_category' ? 'Статья' : op.entity_type === 'feo_item' ? 'Позиция' : 'Субсидия'} #${op.target_id ?? op.target_ref}`
}
// Клик по строке связок → прокрутка к соответствующей строке дерева
// (RevisionTreeView.vue/RevisionTreeRow.vue, требование владельца «клик по
// строке в панели связок прокручивает к ней дерево, и наоборот») —
// review.nodeIdForOp резолвит id узла (в т.ч. через ref_map для ещё не
// сохранённых create-строк), второй резолвер не пишем (Правило №6).
function scrollToTreeNode(op: ReviewOp) {
  const nodeId = review.nodeIdForOp(op)
  if (nodeId == null) return
  document.querySelector<HTMLElement>(`[data-feo-node-id="${nodeId}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

// Поле, которое реально правит эта строка — первое числовое поле `after`
// (для create/update/move обычно ровно одно значимое поле на строку, см.
// FIELD_GROUPS в subsidy_revision_ops.py — группы разделены по смыслу).
function primaryField(op: ReviewOp): string | null {
  const src = op.after || op.before
  if (!src) return null
  const key = Object.keys(src).find((k) => typeof src[k] === 'number' && !k.startsWith('_'))
  return key || null
}
function editableAfter(op: ReviewOp): number {
  const field = primaryField(op)
  if (!field) return 0
  const ov = review.overrides[op.id]
  if (ov && ov[field] != null) return Number(ov[field])
  return Number(op.after?.[field] ?? 0)
}
function overrideValue(op: ReviewOp): number | null {
  const field = primaryField(op)
  if (!field) return null
  const ov = review.overrides[op.id]
  return ov && ov[field] != null ? Number(ov[field]) : Number(op.after?.[field] ?? 0)
}
// Поле «исправить «станет»» — приёмка 02.10, п.10: было узким (140px, голые
// цифры без пробелов) и обрезало "1 189 896" до "11898". formatInt — показ с
// пробелами (ru-RU), onOverrideInput сам чистит пробелы/NBSP перед парсингом.
function formatInt(n: number | null): string {
  if (n == null) return ''
  return new Intl.NumberFormat('ru-RU').format(n)
}
function onOverrideInput(op: ReviewOp, raw: string) {
  const field = primaryField(op)
  if (!field) return
  const cleaned = raw.replace(/[\s ]/g, '').replace(',', '.')
  const num = cleaned === '' ? null : Number(cleaned)
  if (num == null || Number.isNaN(num)) { review.setOverride(op.id, null); return }
  review.setOverride(op.id, { [field]: num })
}

// Строка-увеличение («станет» больше «было» по денежному полю) — и у связки
// (шапка группы, если не хватает), и у строки БЕЗ связки (приёмка 02.10,
// п.4: «Снять с другой позиции» раньше была только внутри rrp-bundle-strip —
// строка без связки вообще не могла её получить).
function isIncreaseOp(op: ReviewOp): boolean {
  const field = primaryField(op)
  if (!field) return false
  const before = Number(op.before?.[field] ?? 0)
  const after = editableAfter(op)
  return after > before + 0.005
}

// «Снять с другой позиции» — строка проверяющего (add_op того же формата,
// что и у автора), см. useRevisionReview.ts::addExtraOp.
const extraDialog = reactive<{ open: boolean; bundleNo: number | null; targetId: number | null; removeAmount: number | null }>({
  open: false, bundleNo: null, targetId: null, removeAmount: null,
})
const itemPickerOptions = computed(() => {
  const items = review.overlay.preview.value?.after?.items || {}
  return Object.values(items).map((it: any) => ({
    title: `${it.name} (${formatCurrency(Number(it.amount || 0))})`,
    value: it.id,
  }))
})
function openExtraDialog(bundleNo: number | null) {
  extraDialog.open = true
  extraDialog.bundleNo = bundleNo
  extraDialog.targetId = null
  extraDialog.removeAmount = null
}
function confirmExtra() {
  if (!extraDialog.targetId || !extraDialog.removeAmount) return
  const items = review.overlay.preview.value?.after?.items || {}
  const item = items[String(extraDialog.targetId)]
  review.addExtraOp({
    kind: 'item',
    targetId: extraDialog.targetId,
    label: item?.name || `Позиция #${extraDialog.targetId}`,
    currentAmount: Number(item?.amount || 0),
    removeAmount: extraDialog.removeAmount,
    bundleNo: extraDialog.bundleNo,
  })
  extraDialog.open = false
}
</script>

<style scoped>
.rrp-filter-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.rrp-empty { padding: 24px 0; text-align: center; }
.rrp-group { margin-bottom: 14px; }
.rrp-bundle-strip {
  font-size: 12px; background: rgba(99,102,241,0.08); border: 1px solid rgba(99,102,241,0.3);
  border-radius: 6px; padding: 4px 10px; margin-bottom: 6px;
}
.rrp-bundle-strip--bad { background: rgba(220,38,38,0.08); border-color: rgba(220,38,38,0.4); color: #991b1b; font-weight: 600; }
.rrp-row {
  border: 1px solid var(--crm-border); border-radius: 8px; padding: 8px 10px; margin-bottom: 6px;
}
.rrp-row--blocked { opacity: 0.55; }
.rrp-row-main { display: flex; align-items: flex-start; gap: 4px; }
.rrp-row-body { flex: 1; min-width: 0; }
.rrp-row-path { font-weight: 600; font-size: 13px; }
.rrp-row-summary { margin-top: 2px; }
.rrp-row-hint { font-size: 11px; color: var(--crm-text-muted); }
.rrp-row-amount { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.rrp-row-comment { margin-top: 6px; width: 100%; }
</style>
