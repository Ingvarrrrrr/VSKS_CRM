<template>
  <div class="tz-rows-section">
    <!-- Баннер нерешённых дублей (закупка) / информационный баннер (заявка) —
         21.09, corrections-21-09.md W3. Текст групп строится из tz.rowsForGroup,
         а не пересчётом дублей на фронте (Правило №6). -->
    <v-alert
      v-if="!readonly && tz.hasUnresolved.value"
      type="warning"
      variant="tonal"
      density="comfortable"
      class="mb-3"
    >
      <div class="d-flex align-center flex-wrap ga-2">
        <span>Повторяющиеся позиции: {{ unresolvedSummaryText }}</span>
        <v-btn size="small" color="warning" variant="elevated" class="ml-auto" @click="openDialog">
          Решить
        </v-btn>
      </div>
    </v-alert>
    <v-alert
      v-else-if="readonly && tz.duplicateGroups.value.length"
      type="warning"
      variant="tonal"
      density="comfortable"
      class="mb-3"
    >
      Повторяющиеся позиции: {{ allGroupsSummaryText }}. Что с ними делать — решается на закупке.
    </v-alert>

    <div
      v-if="!readonly && !tz.hasUnresolved.value && tz.resolvedGroups.value.length"
      class="d-flex align-center ga-2 mb-3 pa-2 rounded"
      style="background: rgba(0,0,0,0.03)"
    >
      <v-icon icon="mdi-check-circle-outline" size="18" color="grey-darken-1" />
      <span class="text-caption text-medium-emphasis">
        Дубли: объединено {{ tz.mergedCount.value }}, оставлено {{ tz.keptCount.value }}
      </span>
      <v-btn size="small" variant="text" color="primary" class="ml-auto" @click="openDialog">
        Изменить
      </v-btn>
    </div>

    <v-table density="comfortable" class="tz-table">
      <thead>
        <tr class="tz-table-header">
          <th style="width:36px;text-align:center">№</th>
          <th v-if="showPhoto" style="width:72px;text-align:center">Фото</th>
          <th>Наименование{{ showPhoto ? ' и описание' : '' }}</th>
          <th style="width:70px;text-align:center">Кол-во</th>
          <th style="width:56px;text-align:center">Ед.</th>
          <th v-if="showPrices" style="width:120px;text-align:right">Цена ед., ₽</th>
          <th v-if="showPrices" style="width:130px;text-align:right">Сумма, ₽</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="tz.loading.value">
          <td :colspan="colCount" class="text-center py-4 text-medium-emphasis">Загрузка…</td>
        </tr>
        <tr v-else-if="!tz.rows.value.length">
          <td :colspan="colCount" class="text-center py-4 text-medium-emphasis">Нет позиций</td>
        </tr>
        <tr v-for="(row, i) in tz.rows.value" :key="row.item_id ?? i" style="vertical-align:middle">
          <td class="text-center text-medium-emphasis">{{ i + 1 }}</td>
          <td v-if="showPhoto" class="text-center py-2">
            <v-avatar v-if="photoFor(row)" size="56" rounded="sm" style="overflow:hidden">
              <img :src="photoFor(row)" style="width:56px;height:56px;object-fit:cover;display:block" />
            </v-avatar>
            <v-icon v-else size="40" color="grey-lighten-2">mdi-image-off-outline</v-icon>
          </td>
          <td class="py-2">
            <div class="d-flex align-center flex-wrap ga-1">
              <span class="font-weight-medium" style="font-size:13px">{{ row.item_name }}</span>
              <v-chip v-if="row.source_item_ids.length > 1" size="x-small" color="primary" variant="tonal">
                объединено {{ row.source_item_ids.length }} строк
              </v-chip>
              <v-tooltip v-if="row.price_averaged" text="Цена усреднена: сумма / количество" location="top">
                <template #activator="{ props: tip }">
                  <v-icon v-bind="tip" icon="mdi-information-outline" size="14" color="grey" />
                </template>
              </v-tooltip>
            </div>
            <div
              v-if="descriptionFor(row)"
              class="text-caption text-medium-emphasis mt-1"
              style="white-space:pre-line;max-width:420px"
            >
              {{ descriptionFor(row) }}
            </div>
            <slot name="row-extra" :row="row" />
          </td>
          <td class="text-center">{{ row.quantity ?? '—' }}</td>
          <td class="text-center">{{ row.unit || '—' }}</td>
          <td v-if="showPrices" class="text-right">{{ priceDash ? '—' : formatMoney(row.unit_price) }}</td>
          <td v-if="showPrices" class="text-right font-weight-medium">{{ priceDash ? '—' : formatMoney(row.total_price) }}</td>
        </tr>
      </tbody>
      <tfoot v-if="showPrices && tz.rows.value.length">
        <tr class="tz-table-footer">
          <td :colspan="colCount - 1" class="text-right font-weight-bold pa-3" style="font-size:13px">Итого НМЦД:</td>
          <td class="text-right font-weight-bold pa-3 text-primary" style="font-size:13px">
            {{ priceDash ? '—' : formatMoney(footerTotalValue) }}
          </td>
        </tr>
      </tfoot>
    </v-table>

    <DuplicateMergeDialog
      v-if="dialogShow"
      v-model="dialogShow"
      mode="tz"
      :tz-groups="tzGroupsForDialog"
      @confirm-tz="onConfirmTz"
    />

    <ReturnToWishDialog
      v-if="returnDialogShow && purchaseId"
      v-model="returnDialogShow"
      :purchase-id="purchaseId"
      :reason-hint="pendingReturnReason"
      :show-snack="showSnack"
      @success="onReturned"
    />

    <v-snackbar v-model="localErrorShow" color="error" :timeout="-1">
      {{ tz.error.value }}
      <template #actions>
        <v-btn variant="text" @click="localErrorShow = false">Закрыть</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
// Секция «Техническое задание» — общий компонент для закупки (CreateOrderView.vue,
// секция 2.5) и заявки (WishTzSection.vue). Данные — ИСКЛЮЧИТЕЛЬНО с сервера
// (GET /api/purchases/{id}/tz-rows | GET /api/wishes/{id}/tz-rows через
// composables/purchase/useTzRows.ts) — никакого локального пересчёта дублей
// здесь нет (Правило №6, план corrections-21-09.md W3).
//
// Фото/описание позиции сервер не отдаёт (их источник — локально редактируемые
// items формы, ещё не факт что сохранённые) — за это отвечают опциональные
// props resolveLocalItem/activeDescription, которые вызывающая сторона уже
// использовала до этой правки (CreateOrderView::activeDescription,
// WishTzSection::activeDescription) — переиспользуются как есть, не дублируются.
import { computed, ref, toRef, watch } from 'vue'
import { formatMoney } from '@/utils/formatMoney'
import { describeApiError } from '@/utils/apiErrorMessage'
import { useTzRows, type TzRow, type TzDuplicateGroup } from '@/composables/purchase/useTzRows'
import DuplicateMergeDialog from '@/components/DuplicateMergeDialog.vue'
import ReturnToWishDialog from '@/components/purchase/ReturnToWishDialog.vue'

const props = withDefaults(defineProps<{
  purchaseId?: number | null
  wishId?: number | null
  /** Заявка: только информационный баннер, без решений по дублям (у заявки
   * нет своего хранилища decisions — см. wish_tz.py). */
  readonly?: boolean
  showPhoto?: boolean
  showPrices?: boolean
  /** Показывать цены прочерком (nmckMode==='manual' в CreateOrderView) —
   * решение остаётся у вызывающей стороны, здесь просто флаг отображения. */
  priceDash?: boolean
  /** Итог «Итого НМЦД» — если не передан, считается суммой total_price строк.
   * CreateOrderView передаёт displayNmck (единственный источник НМЦД, Правило №6). */
  footerTotal?: number | null
  resolveLocalItem?: (row: TzRow) => any
  activeDescription?: (item: any) => string | undefined
  // Совпадает с composables/useToast.ts::ToastType — CreateOrderView передаёт
  // сюда свой showSnack(text, color?: ToastType, opts?), a `color?: string`
  // здесь был бы шире цели (TS2322: contravariance), не принимается.
  showSnack?: (msg: string, color?: 'success' | 'error' | 'info' | 'warning') => void
}>(), {
  purchaseId: null,
  wishId: null,
  readonly: false,
  showPhoto: true,
  showPrices: true,
  priceDash: false,
  footerTotal: undefined,
})

const emit = defineEmits<{
  (e: 'unresolved-changed', v: boolean): void
}>()

const tz = useTzRows(toRef(props, 'purchaseId'), toRef(props, 'wishId'))

watch([() => props.purchaseId, () => props.wishId], () => { tz.refresh() }, { immediate: true })
watch(tz.hasUnresolved, (v) => emit('unresolved-changed', v), { immediate: true })

const localErrorShow = computed({
  get: () => !!tz.error.value,
  set: (v: boolean) => { if (!v) tz.error.value = null },
})

const colCount = computed(() => 4 + (props.showPhoto ? 1 : 0) + (props.showPrices ? 2 : 0))
const footerTotalValue = computed(() => {
  if (props.footerTotal !== undefined && props.footerTotal !== null) return props.footerTotal
  return tz.rows.value.reduce((s, r) => s + (r.total_price || 0), 0)
})

function photoFor(row: TzRow): string | undefined {
  return props.resolveLocalItem?.(row)?._photo_url
}
function descriptionFor(row: TzRow): string | undefined {
  const item = props.resolveLocalItem?.(row)
  return item ? props.activeDescription?.(item) : undefined
}

function trimNum(n: number): string {
  return Number(n).toString()
}
function groupSummaryText(g: TzDuplicateGroup): string {
  const groupRows = tz.rowsForGroup(g)
  const qtyParts = groupRows
    .map((r) => (r.quantity != null ? `${trimNum(r.quantity)} ${g.unit || ''}`.trim() : null))
    .filter(Boolean) as string[]
  const qtyText = qtyParts.length
    ? qtyParts.join(' и ')
    : g.qty_sum != null
      ? `${trimNum(g.qty_sum)} ${g.unit || ''}`.trim()
      : `${g.item_ids.length} стр.`
  return `${g.name} — ${qtyText}`
}
const unresolvedSummaryText = computed(() =>
  tz.duplicateGroups.value
    .filter((g) => tz.unresolvedKeys.value.includes(g.key))
    .map(groupSummaryText)
    .join('; '),
)
const allGroupsSummaryText = computed(() => tz.duplicateGroups.value.map(groupSummaryText).join('; '))

const dialogShow = ref(false)
function openDialog() {
  if (props.readonly) return
  dialogShow.value = true
}

const tzGroupsForDialog = computed(() =>
  tz.duplicateGroups.value.map((g) => ({
    key: g.key,
    name: g.name,
    unit: g.unit,
    prices_differ: g.prices_differ,
    qty_sum: g.qty_sum,
    total_sum: g.total_sum,
    decision: g.decision,
    rows: tz.rowsForGroup(g),
  })),
)

const returnDialogShow = ref(false)
const pendingReturnReason = ref('')

async function onConfirmTz(payload: { decisions: Record<string, 'merge' | 'keep'>; errorKeys: string[]; errorNames: string[] }) {
  if (payload.errorKeys.length) {
    pendingReturnReason.value = `Повторяющиеся позиции в ТЗ: ${payload.errorNames.join(', ')}`
    returnDialogShow.value = true
    return
  }
  if (!Object.keys(payload.decisions).length) return
  try {
    await tz.applyDecisions(payload.decisions)
    props.showSnack?.('Решения по дублям сохранены')
  } catch (e: any) {
    props.showSnack?.(describeApiError(e, { fallback: 'Не удалось сохранить решения' }), 'error')
  }
}

function onReturned() {
  returnDialogShow.value = false
}

defineExpose({ refresh: tz.refresh, hasUnresolved: tz.hasUnresolved })
</script>

<style scoped>
/* --crm-table-header/--crm-table-stripe — общие theme-aware переменные,
   заданы в App.vue (единственный источник цветов таблиц, Правило №6). */
.tz-table :deep(th) {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.6);
}
.tz-table-header {
  background: var(--crm-table-header);
}
.tz-table-footer {
  background: var(--crm-table-stripe);
}
.tz-table-footer td {
  border-top: 2px solid rgba(59, 130, 246, 0.2);
}
</style>
