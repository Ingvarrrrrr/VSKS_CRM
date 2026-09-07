<template>
  <!-- ── Редактирование позиции закупки (из дерева ФЭО) ── -->
  <v-dialog v-model="state.show" :max-width="dialogWidth" :fullscreen="ctx.mobile.value">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-pencil-outline" color="primary" class="mr-2" />
        Редактировать позицию
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="state.show = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <v-text-field v-model="state.form.item_name" label="Название позиции" density="comfortable"
          variant="outlined" class="mb-2" hide-details="auto" />
        <div class="d-flex ga-2 mb-2">
          <v-text-field v-model.number="state.form.quantity" label="Кол-во" type="number" min="0"
            density="comfortable" variant="outlined" hide-details="auto" style="max-width: 130px" />
          <v-text-field v-model="state.form.unit" label="Ед." density="comfortable" variant="outlined"
            hide-details="auto" style="max-width: 100px" />
          <v-text-field v-model.number="state.form.unit_price" label="Цена за ед., ₽" type="number" min="0"
            density="comfortable" variant="outlined" hide-details="auto" />
        </div>
        <div class="text-body-2 text-medium-emphasis mb-3">
          Сумма: <b>{{ formatCurrency((Number(state.form.quantity) || 0) * (Number(state.form.unit_price) || 0)) }}</b>
        </div>
        <FeoTreeSelect
          v-model="state.form.feo_category_id"
          :nodes="feoNodes"
          :leaves="feoLeaves"
          label="Категория ФЭО"
        />
        <div class="text-caption text-medium-emphasis mt-1 mb-2">
          Перенос в другую категорию не тратит новых денег — так перерасход и разбирается
        </div>
        <!-- Владелец (2026-08-18): выбор ПЛАНОВОЙ ПОЗИЦИИ внутри выбранной категории —
             без него позиция при переносе в новую категорию находит план только точным
             совпадением имени, иначе молча заводит новую плановую позицию рядом с уже
             подходящей (прод-инцидент «Огнетушитель ОУ-2»). -->
        <FeoPlannedItemsSelect
          v-if="state.form.feo_category_id"
          :model-value="planSelection"
          :category-id="state.form.feo_category_id"
          :nodes="feoNodes"
          :items="plannedResiduals"
          :amount="planAmount"
          :loading="plannedLoading"
          :prefill="planPrefill"
          :purchase-id="state.purchaseId"
          @update:model-value="onPlanSelect"
          @planned-item-created="reloadPlanned"
          @planned-item-deleted="reloadPlanned"
        />
        <div class="text-caption text-medium-emphasis mt-1">
          Можно привязать к существующей плановой позиции или создать новую — если не
          выбирать, система подберёт сама по точному совпадению названия.
        </div>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="state.show = false">Отмена</v-btn>
        <v-btn color="primary" :loading="state.saving" @click="save">Сохранить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Редактирование позиции закупки прямо из дерева ФЭО (карандаш в строках факта
// панели «план vs факт», строках «из заявок», реестре непривязанных) — вынесен
// из SubsidiesView.vue (волна 5c). Открывается через ctx.openReqItemEdit(node,
// item)/ctx.openReqItemEditFromActual(node, actual) — трамполины вызывают
// open()/openFromActual() этого компонента через ref, см. её докстринг.
import { computed, reactive, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { useFeoLeaves } from '@/composables/useFeoLeaves'
import { useFeoPlannedResiduals } from '@/composables/useFeoPlannedResiduals'
import type { FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'
import { numOrNull } from '@/utils/numberFormat'
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'
import FeoPlannedItemsSelect from '@/components/items/FeoPlannedItemsSelect.vue'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { formatCurrency } from '@/composables/subsidies/format'
import type { FeoActualItem, FeoNode, FeoReqItem } from '@/composables/subsidies/types'

const ctx = useSubsidyDetailCtx()

const toast = useToast()
function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

const state = reactive({
  show: false, saving: false,
  catId: null as number | null, purchaseId: null as number | null, itemId: null as number | null,
  form: { item_name: '', quantity: null as number | null, unit: '', unit_price: null as number | null, feo_category_id: null as number | null },
  // Снимок значений на момент открытия диалога (правка 2026-08-18): save() шлёт в PATCH
  // только реально изменённые поля — иначе при заморозке ТЗ (TZ_FROZEN_STATUSES) правка
  // ОДНОЙ ТОЛЬКО категории отбивается 409 из-за молча переотправленных qty/price.
  original: { item_name: '', quantity: null as number | null, unit: '', unit_price: null as number | null },
})

// Жалоба владельца (2026-08-18): диалог правки позиции всегда был зашит в max-width 520 —
// на мониторе 27" название категории/позиции не влезает. Свой computed по брейкпоинтам Vuetify.
const { smAndDown, mdAndDown } = useDisplay()
const dialogWidth = computed(() => {
  if (smAndDown.value) return 720   // планшет/маленький ноутбук
  if (mdAndDown.value) return 900   // обычный десктоп
  return 1100                        // крупный монитор (lg/xl и выше)
})

// Дерево категорий ФЭО для пикера (Правка владельца 2026-08-12: «перенести позицию в
// другую категорию — так превышение и разбирается»).
const subsidyId = computed(() => ctx.selectedSubsidy.value?.id ?? null)
const { feoLeaves, feoNodes } = useFeoLeaves({ subsidyId })

// Плановые позиции категории для диалога правки (владелец, 2026-08-18).
const {
  plannedResiduals, plannedLoading, reloadPlanned,
} = useFeoPlannedResiduals({
  subsidyId,
  excludePurchaseId: computed(() => state.purchaseId),
})
const planSelection = ref<FeoPlanSelection | null>(null)
const planTouched = ref(false)
function onPlanSelect(val: FeoPlanSelection | null) {
  planTouched.value = true
  planSelection.value = val && val.kind === 'planned_item' ? val : null
}
const planAmount = computed(() =>
  (Number(state.form.quantity) || 0) * (Number(state.form.unit_price) || 0)
)
const planPrefill = computed(() => ({
  name: state.form.item_name,
  quantity: state.form.quantity,
  unit: state.form.unit,
  amount: planAmount.value,
}))

// Принцип владельца (2026-08-18): «после того как заявка попала в План закупок, дальше
// редактирование — только в Закупках». Диалог открывается всегда; блокировки (заморозка
// ТЗ, превышение плана) отрабатывает сам PATCH своим 409, распаковывается в save().
function open(node: FeoNode, item: FeoReqItem) {
  state.catId = node.id
  state.purchaseId = item.purchase_id
  state.itemId = item.id
  state.form = { item_name: item.item_name, quantity: item.quantity, unit: item.unit || '', unit_price: item.unit_price, feo_category_id: node.id }
  state.original = {
    item_name: state.form.item_name, quantity: state.form.quantity,
    unit: state.form.unit, unit_price: state.form.unit_price,
  }
  planSelection.value = item.feo_planned_item_id != null
    ? { kind: 'planned_item', id: item.feo_planned_item_id }
    : null
  planTouched.value = false
  state.show = true
}

// Карандаш в строках факта панели «план vs факт» (все три блока) правит ПОЗИЦИЮ ЗАКУПКИ,
// а не план — адаптер собирает совместимый FeoReqItem из FeoActualItem.
function openFromActual(node: FeoNode, actual: FeoActualItem) {
  open(node, {
    id: actual.purchase_item_id,
    item_name: actual.item_name,
    quantity: actual.quantity ?? 0,
    unit: actual.unit,
    unit_price: actual.unit_price ?? 0,
    total_price: actual.total_price ?? 0,
    purchase_id: actual.purchase_id,
    purchase_number: actual.purchase_number,
    registry_number: actual.registry_number,
    purchase_status: actual.purchase_status || '',
    wish_id: actual.wish_id ?? null,
    category: '', product_type: '',
    feo_planned_item_id: actual.feo_planned_item_id ?? null,
  })
}

async function save() {
  if (!state.itemId || !state.purchaseId) return
  state.saving = true
  try {
    // Шлём ТОЛЬКО реально изменённые поля (правка 2026-08-18).
    const body: Record<string, any> = {}
    if (state.form.item_name !== state.original.item_name) {
      body.item_name = state.form.item_name
    }
    const normQuantity = numOrNull(state.form.quantity)
    if (normQuantity !== numOrNull(state.original.quantity)) {
      body.quantity = normQuantity
    }
    if ((state.form.unit || '') !== (state.original.unit || '')) {
      body.unit = state.form.unit || null
    }
    const normUnitPrice = numOrNull(state.form.unit_price)
    if (normUnitPrice !== numOrNull(state.original.unit_price)) {
      body.unit_price = normUnitPrice
    }
    const categoryChanged = state.form.feo_category_id != null && state.form.feo_category_id !== state.catId
    if (categoryChanged) body.feo_category_id = state.form.feo_category_id
    if (planTouched.value) {
      body.feo_planned_item_id = planSelection.value?.id ?? null
    }
    if (Object.keys(body).length === 0) {
      state.show = false
      showSnack('Изменений нет')
      return
    }
    const _patchRes = await apiFetch<any>(`/purchases/${state.purchaseId}/items/${state.itemId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    })
    state.show = false
    await ctx.refreshReqData(state.catId ?? undefined)
    if (categoryChanged && state.form.feo_category_id != null) {
      delete ctx.comparisonData.value[state.form.feo_category_id]
      await ctx.ensureComparison(state.form.feo_category_id)
    }
    // Владелец (2026-09-03): «перекос ветки — предупреждение, не блокировка».
    if (_patchRes?.excess_warnings?.length) {
      showSnack(_patchRes.excess_warnings.map((w: any) => w.message).join(' '), 'warning')
    } else {
      showSnack('Позиция обновлена')
    }
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || 'Не удалось сохранить позицию', 'error')
  } finally {
    state.saving = false
  }
}

defineExpose({ open, openFromActual })
</script>

<style scoped>
.dialog-card {}
.dialog-title {
  display: flex; align-items: center;
  font-size: 16px !important; font-weight: 600 !important;
  padding: 16px 20px !important;
}
</style>

