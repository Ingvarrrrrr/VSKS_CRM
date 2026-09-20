<template>
  <!-- Полноэкранный подбор товара для «Создать закупку на основе плана»
       (владелец, лист 2 №7) — открывается кнопкой «Подтвердить выбор» из
       FeoTreeToolbar.vue после того, как пользователь отметил плановые
       позиции галочками. Результат — ЗАЯВКА (POST plan-to-wish/create), не
       закупка. Состояние/API — usePlanToRequest.ts (Правило №6, единственный
       источник). -->
  <v-dialog :model-value="planToRequest.dialogOpen.value" fullscreen persistent
    transition="dialog-bottom-transition"
    @update:model-value="(v: boolean) => { if (!v) planToRequest.closeDialog() }">
    <v-card class="d-flex flex-column" style="height:100vh">
      <v-toolbar color="deep-purple" density="comfortable">
        <v-toolbar-title>
          Заявка из плана — {{ ctx.selectedSubsidy.value?.name || 'субсидия' }}
        </v-toolbar-title>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" @click="planToRequest.closeDialog()" />
      </v-toolbar>

      <div class="px-4 pt-3 pb-2 d-flex align-center flex-wrap" style="gap:16px">
        <v-text-field
          v-model="planToRequest.title.value"
          label="Название заявки" placeholder="По умолчанию сформирует сервер"
          density="compact" variant="outlined" hide-details style="max-width:420px"
        />
        <div class="d-flex align-center" style="gap:8px">
          <span class="text-caption text-medium-emphasis">Цена по умолчанию для всех строк:</span>
          <v-btn-toggle
            :model-value="planToRequest.globalPriceSource.value"
            density="compact" mandatory variant="outlined" color="deep-purple"
            @update:model-value="(v: 'catalog' | 'plan') => planToRequest.setGlobalPriceSource(v)"
          >
            <v-btn size="small" value="catalog">Из каталога</v-btn>
            <v-btn size="small" value="plan">Плановая</v-btn>
          </v-btn-toggle>
        </div>
        <v-spacer />
        <div class="text-body-2 text-medium-emphasis">
          Строк: <b>{{ planToRequest.totalRowsCount.value }}</b> ·
          Сумма: <b>{{ formatMoney(planToRequest.totalAmount.value) }}</b>
        </div>
      </div>

      <v-divider />

      <!-- Материализация ручных планов категорий (задача 2) — перед POST
           plan-to-wish/candidates: отрицательные id (категория без отдельных
           FeoPlannedItem) сначала становятся настоящими позициями, см.
           usePlanToRequest.ts::materializeSelectedManualPlans. -->
      <div v-if="planToRequest.materializingManualPlans.value" class="d-flex align-center justify-center" style="height:80px;gap:8px">
        <v-progress-circular indeterminate color="deep-purple" size="20" />
        <span class="text-body-2">Создаю плановые позиции…</span>
      </div>
      <!-- Пачки по 50 (владелец, задача 1) — строки появляются по мере готовности. -->
      <div v-if="planToRequest.candidatesProgress.value" class="px-4 py-2">
        <div class="text-caption text-medium-emphasis mb-1">
          Подбор товаров: {{ planToRequest.candidatesProgress.value.done }} из {{ planToRequest.candidatesProgress.value.total }}
        </div>
        <v-progress-linear
          :model-value="(planToRequest.candidatesProgress.value.done / planToRequest.candidatesProgress.value.total) * 100"
          color="deep-purple" height="6" rounded
        />
      </div>

      <div class="flex-grow-1" style="overflow-y:auto">
        <div v-if="planToRequest.loadingCandidates.value && !planToRequest.rows.value.length" class="d-flex align-center justify-center" style="height:200px;gap:8px">
          <v-progress-circular indeterminate color="deep-purple" />
          <span class="text-body-2">Подбираем кандидатов по каталогу…</span>
        </div>
        <div v-else-if="!planToRequest.rows.value.length && !planToRequest.materializingManualPlans.value" class="text-center text-medium-emphasis py-8">
          Нет плановых позиций для подбора
        </div>
        <table v-if="planToRequest.rows.value.length" class="ptr-table">
          <thead>
            <tr>
              <th style="width:26%">Плановая позиция</th>
              <th style="width:130px">Кол-во</th>
              <th style="width:26%">Товар</th>
              <th style="width:160px">Цена за ед.</th>
              <th style="width:140px">Сумма</th>
              <th style="width:36px"></th>
            </tr>
          </thead>
          <tbody>
            <PlanToRequestRow
              v-for="row in planToRequest.rows.value" :key="row.plannedItemId"
              :row="row"
              @pick="(c) => planToRequest.pickCandidateForRow(row, c)"
              @set-source-override="(s) => planToRequest.setRowPriceSourceOverride(row, s)"
              @open-catalog-search="openPickerFor(row)"
              @write-to-initiator="planToRequest.writeToInitiator(row)"
              @remove="removeRow(row)"
            />
          </tbody>
        </table>
      </div>

      <v-divider />
      <v-card-actions class="px-4 py-3">
        <span class="text-caption text-medium-emphasis">
          {{ planToRequest.totalRowsCount.value }} строк(и) станут позициями заявки
        </span>
        <v-spacer />
        <v-btn variant="text" :disabled="planToRequest.submitting.value" @click="planToRequest.closeDialog()">Отмена</v-btn>
        <v-btn color="deep-purple" variant="flat" prepend-icon="mdi-hand-heart-outline"
          :loading="planToRequest.submitting.value"
          :disabled="!planToRequest.totalRowsCount.value"
          @click="planToRequest.submitCreate()"
        >Создать заявку</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- «Найти в каталоге…» — тот же переиспользуемый ProductPickerDialog.vue
       (Правило №6), что и в PurchaseItemsEditor.vue: сервер-сайд поиск по
       всему каталогу (GET /products/), не ограничен готовыми кандидатами
       по имени/типу. -->
  <ProductPickerDialog
    v-model="pickerOpen"
    :search="pickerSearch"
    :results="pickerResults"
    :supports-full-product-dialog="false"
    :photo-src="(p) => productPhotoSrc(p as any)"
    @update:search="onPickerSearch"
    @pick="onPickerPick"
    @create-new="onPickerCreateNew"
  />
</template>

<script setup lang="ts">
// Fullscreen-диалог подбора товара для заявки, создаваемой из выбранных
// плановых позиций дерева ФЭО. Разбит на строку PlanToRequestRow.vue —
// Правило №5 (модульность), эта часть отвечает только за шапку/список/
// ручной поиск по каталогу и итоги.
import { ref } from 'vue'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePlanToRequest, type PlanToRequestRow as PlanToRequestRowState, type PlanToWishCandidate } from '@/composables/subsidies/usePlanToRequest'
import { formatMoney } from '@/utils/formatMoney'
import { productPhotoSrc } from '@/utils/productPhoto'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import ProductPickerDialog from '@/components/items/ProductPickerDialog.vue'
import PlanToRequestRow from './PlanToRequestRow.vue'
import type { ProductLike } from '@/components/items/types'

const ctx = useSubsidyDetailCtx()
const planToRequest = usePlanToRequest()
const toast = useToast()

function removeRow(row: PlanToRequestRowState) {
  planToRequest.rows.value = planToRequest.rows.value.filter(r => r.plannedItemId !== row.plannedItemId)
}

// ── «Найти в каталоге…» — ручной поиск по всему справочнику товаров ────────
const pickerOpen = ref(false)
const pickerSearch = ref('')
const pickerResults = ref<ProductLike[]>([])
const pickerTargetRow = ref<PlanToRequestRowState | null>(null)
let searchTimer: ReturnType<typeof setTimeout> | null = null

function openPickerFor(row: PlanToRequestRowState) {
  pickerTargetRow.value = row
  pickerSearch.value = row.name
  pickerOpen.value = true
  runSearch(pickerSearch.value)
}

function onPickerSearch(v: string) {
  pickerSearch.value = v
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => runSearch(v), 300)
}

async function runSearch(q: string) {
  try {
    const params = new URLSearchParams()
    if (q.trim()) params.set('search', q.trim())
    params.set('limit', '20')
    params.set('is_active', 'true')
    pickerResults.value = await apiFetch<ProductLike[]>(`/products/?${params.toString()}`)
  } catch {
    pickerResults.value = []
  }
}

function onPickerPick(p: ProductLike) {
  if (!pickerTargetRow.value) return
  const cand: PlanToWishCandidate = {
    product_id: p.id,
    name: p.name,
    price: p.price ?? null,
    score: 1,
    photo_url: productPhotoSrc(p) ?? null,
    item_type: (p as any).item_kind ?? null,
    category: p.category ?? null,
    product_type: p.product_type ?? null,
    unit: (p as any).unit ?? null,
    price_updated_at: (p as any).price_updated_at ?? null,
    price_source: (p as any).price_source ?? null,
    price_freshness: (p as any).price_freshness ?? null,
  }
  planToRequest.pickCandidateForRow(pickerTargetRow.value, cand)
  pickerOpen.value = false
}

function onPickerCreateNew() {
  // Владелец допустил (задание): если полноценный диалог создания товара
  // (FullProductDialog + useItemsCatalog.ts) нельзя подключить без копипасты
  // его логики — оставить только «Без товара». useItemsCatalog.ts завязан на
  // localItems/selectedItemIdxs формы позиций закупки, здесь их нет — второй
  // независимый экземпляр этой логики заводить не стали (Правило №6).
  toast.addToast('Создание нового товара здесь недоступно — выберите «Без товара» или заведите товар в каталоге (Товары) и повторите поиск', 'info')
}
</script>

<style scoped>
.ptr-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.ptr-table thead th {
  position: sticky;
  top: 0;
  background: #F8FAFC;
  text-align: left;
  padding: 8px 10px;
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid #E2E8F0;
  z-index: 1;
}
</style>
