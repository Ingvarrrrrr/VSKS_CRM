<template>
  <tr class="ptr-row">
    <!-- Плановая позиция ── имя/категория/план/остаток -->
    <td class="ptr-td">
      <div class="font-weight-medium">{{ row.name }}</div>
      <div class="text-caption text-medium-emphasis">{{ row.feoCategoryName }}</div>
      <div class="text-caption text-medium-emphasis mt-1">
        план: {{ row.planQuantity ?? '—' }} {{ row.unit || '' }} × {{ formatMoney(row.planUnitPrice) }} = {{ formatMoney(row.planAmount) }}
      </div>
      <div class="text-caption mt-1" :class="isOverResidual ? 'text-error font-weight-medium' : 'text-medium-emphasis'">
        Остаток: {{ row.residualQuantity != null ? row.residualQuantity : 'не ограничено' }}<template v-if="row.planQuantity != null"> из {{ row.planQuantity }}</template> {{ row.unit || '' }}
      </div>
    </td>

    <!-- Количество для заявки -->
    <td class="ptr-td">
      <v-text-field
        v-model.number="row.quantity"
        type="number" density="compact" variant="outlined" hide-details
        style="max-width:110px"
      />
      <div v-if="isOverResidual" class="ptr-warning mt-2">
        <v-icon icon="mdi-alert-outline" size="14" class="mr-1" />
        Запланировано {{ row.planQuantity ?? '—' }} {{ row.unit || '' }}, уже в закупках {{ row.usedQuantity }} {{ row.unit || '' }}
        <template v-if="primaryPurchase">
          ({{ primaryPurchaseLabel }} — инициатор {{ primaryPurchase.initiator_name || '—' }})
        </template>
        <template v-if="row.linkedPurchases.length > 1">, и ещё {{ row.linkedPurchases.length - 1 }}</template>.
        Свяжитесь с инициатором для уточнения потребности.
        <div class="mt-1">
          <v-btn size="x-small" variant="tonal" color="warning" prepend-icon="mdi-email-fast-outline"
            :loading="row.creatingTask" :disabled="!primaryPurchase || primaryPurchase.initiator_user_id == null"
            @click="$emit('write-to-initiator')"
          >Написать инициатору</v-btn>
        </div>
      </div>
    </td>

    <!-- Товар из каталога — «Без товара» убрано (владелец, задача 2: «на
         основании чего появится ТЗ в закупке?»), каждая строка ОБЯЗАНА иметь
         товар. Пока не выбран — рамка/фон предупреждения на самом боксе
         (ptr-product-box--missing), не только текст, см. CSS ниже. -->
    <td class="ptr-td" :data-planned-item-id="row.plannedItemId">
      <v-menu location="bottom start">
        <template #activator="{ props: menuProps }">
          <div v-bind="menuProps" class="ptr-product-box" :class="{ 'ptr-product-box--missing': !row.selectedCandidate }" style="cursor:pointer">
            <template v-if="row.selectedCandidate">
              <v-avatar size="32" rounded="sm" class="mr-2">
                <img v-if="row.selectedCandidate.photo_url" :src="row.selectedCandidate.photo_url" style="width:32px;height:32px;object-fit:cover" />
                <v-icon v-else icon="mdi-package-variant" size="18" color="grey" />
              </v-avatar>
              <div class="flex-grow-1" style="min-width:0">
                <div class="d-flex align-center" style="gap:4px">
                  <span class="text-truncate" style="max-width:180px">{{ row.selectedCandidate.name }}</span>
                  <v-chip v-if="matchBadge" size="x-small" color="teal" variant="tonal">{{ matchBadge }}</v-chip>
                </div>
                <PriceFreshnessStamp :price-meta="row.selectedCandidate" />
              </div>
            </template>
            <template v-else>
              <v-icon icon="mdi-alert-outline" size="16" class="mr-1" color="warning" />
              <span class="ptr-missing-text">Выберите товар из каталога или добавьте новый</span>
            </template>
            <v-spacer />
            <v-icon icon="mdi-chevron-down" size="16" />
          </div>
        </template>

        <v-list density="compact" style="max-height:420px;overflow-y:auto;min-width:320px">
          <template v-if="row.exact">
            <v-list-subheader>Точное совпадение</v-list-subheader>
            <v-list-item @click="$emit('pick', row.exact!)">
              <template #prepend>
                <v-avatar size="28" rounded="sm">
                  <img v-if="row.exact.photo_url" :src="row.exact.photo_url" style="width:28px;height:28px;object-fit:cover" />
                  <v-icon v-else icon="mdi-package-variant" size="16" color="grey" />
                </v-avatar>
              </template>
              <v-list-item-title>{{ row.exact.name }}</v-list-item-title>
              <v-list-item-subtitle>{{ formatMoney(row.exact.price) }}</v-list-item-subtitle>
              <template #append><v-chip size="x-small" color="teal" variant="tonal">100%</v-chip></template>
            </v-list-item>
            <v-divider />
          </template>

          <template v-if="row.byName.length">
            <v-list-subheader>По названию</v-list-subheader>
            <v-list-item v-for="c in row.byName" :key="'n' + c.product_id" @click="$emit('pick', c)">
              <template #prepend>
                <v-avatar size="28" rounded="sm">
                  <img v-if="c.photo_url" :src="c.photo_url" style="width:28px;height:28px;object-fit:cover" />
                  <v-icon v-else icon="mdi-package-variant" size="16" color="grey" />
                </v-avatar>
              </template>
              <v-list-item-title>{{ c.name }}</v-list-item-title>
              <v-list-item-subtitle>{{ formatMoney(c.price) }}</v-list-item-subtitle>
              <template #append><v-chip size="x-small" variant="tonal">{{ pct(c.score) }}%</v-chip></template>
            </v-list-item>
          </template>

          <template v-if="row.byType.length">
            <v-list-subheader>По типу товара</v-list-subheader>
            <v-list-item v-for="c in row.byType" :key="'t' + c.product_id" @click="$emit('pick', c)">
              <template #prepend>
                <v-avatar size="28" rounded="sm">
                  <img v-if="c.photo_url" :src="c.photo_url" style="width:28px;height:28px;object-fit:cover" />
                  <v-icon v-else icon="mdi-package-variant" size="16" color="grey" />
                </v-avatar>
              </template>
              <v-list-item-title>{{ c.name }}</v-list-item-title>
              <v-list-item-subtitle>{{ formatMoney(c.price) }}</v-list-item-subtitle>
            </v-list-item>
          </template>

          <v-divider />
          <v-list-item prepend-icon="mdi-magnify" @click="$emit('open-catalog-search')">
            <v-list-item-title>Найти в каталоге…</v-list-item-title>
          </v-list-item>
          <v-list-item prepend-icon="mdi-plus-box" @click="openAddProduct">
            <v-list-item-title>Добавить товар</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>

      <!-- «Добавить товар» — тот же каталожный диалог/композабл, что и
           страница «Товары» (Правило №6, useProductsForm.ts::onSaved). Товар
           создаётся в общем каталоге (POST /products/) и сразу подставляется
           в строку как выбранный кандидат. -->
      <ProductFormDialog
        v-model="productCreate.dialog.value"
        v-model:name-search="productCreate.nameSearch.value"
        :mobile="productCreate.mobile.value"
        :editing-id="productCreate.editingId.value"
        :edit-meta="productCreate.editMeta"
        :form="productCreate.form"
        :name-suggestions="productCreate.nameSuggestions.value"
        :is-duplicate-name="productCreate.isDuplicateName.value"
        :type-options="productCreate.typeOptions.value"
        :category-options="productCreate.categoryOptions.value"
        :avg-price="productCreate.avgPrice.value"
        :photo-preview="productCreate.photoPreview.value"
        :photo-file="productCreate.photoFile.value"
        :photo-file-list="productCreate.photoFileList.value"
        :photo-cache-buster="productCreate.photoCacheBuster.value"
        :downloading-photo="productCreate.downloadingPhoto.value"
        :deleting-photo="productCreate.deletingPhoto.value"
        :saving="productCreate.saving.value"
        @save="productCreate.save"
        @clear-photo="productCreate.clearUploadedPhoto"
        @download-photo="productCreate.downloadSinglePhoto"
        @photo-file-change="productCreate.onPhotoFileChange"
      />
    </td>

    <!-- Цена за единицу — три именованных режима (владелец, задача 3): «Ввести
         самостоятельно» (правится вручную), «Из прошлых закупок» (цена товара
         из каталога, бывш. 'catalog'), «По плану» (плановая цена за единицу).
         Построчный переключатель меняет ТОЛЬКО эту строку — «следует общему»
         больше нет, у строки всегда явный режим (usePlanToRequest.ts::priceMode).
         Названия — PRICE_MODE_LABELS, тот же источник, что и общий переключатель
         в PlanToRequestDialog.vue (Правило №6). -->
    <td class="ptr-td">
      <div class="ptr-price-toggle">
        <v-tooltip v-for="mode in PRICE_MODE_ORDER" :key="mode" location="top" :disabled="!disabledReason(mode)">
          <template #activator="{ props: modeTooltipProps }">
            <v-btn v-bind="modeTooltipProps"
              size="x-small" variant="outlined" density="compact"
              :color="row.priceMode === mode ? 'deep-purple' : 'grey'"
              :class="{ 'ptr-price-btn--active': row.priceMode === mode }"
              :disabled="!!disabledReason(mode)"
              @click="$emit('set-price-mode', mode)"
            >{{ PRICE_MODE_LABELS[mode] }}</v-btn>
          </template>
          <span>{{ disabledReason(mode) }}</span>
        </v-tooltip>
      </div>
      <v-text-field
        v-model.number="row.unitPrice"
        type="number" density="compact" variant="outlined" hide-details
        style="max-width:150px" class="mt-1"
        :readonly="row.priceMode !== 'manual'"
        :bg-color="row.priceMode !== 'manual' ? 'grey-lighten-4' : undefined"
        :title="row.priceMode !== 'manual' ? `Цена берётся автоматически (${PRICE_MODE_LABELS[row.priceMode]}) — для правки переключите на «Ввести самостоятельно»` : ''"
      />
    </td>

    <!-- Сумма -->
    <td class="ptr-td text-right font-weight-medium">
      {{ formatMoney((Number(row.unitPrice) || 0) * (Number(row.quantity) || 0)) }}
    </td>

    <td class="ptr-td text-center">
      <v-btn icon="mdi-close" size="x-small" variant="text" color="grey" title="Убрать строку" @click="$emit('remove')" />
    </td>
  </tr>
</template>

<script setup lang="ts">
// Строка диалога подбора товара для заявки из плана (PlanToRequestDialog.vue).
// Вынесена отдельным компонентом — Правило №5 (модульность, диалог + все
// строки в одном файле разрослись бы far за 400 строк).
import { computed } from 'vue'
import { formatMoney } from '@/utils/formatMoney'
import PriceFreshnessStamp from '@/components/items/PriceFreshnessStamp.vue'
import ProductFormDialog from '@/components/products/ProductFormDialog.vue'
import { usePlanToRequestProductCreate } from '@/composables/subsidies/usePlanToRequestProductCreate'
import {
  PRICE_MODE_LABELS, PRICE_MODE_ORDER, priceModeDisabledReason,
  type PlanToRequestRow as PlanToRequestRowState, type PlanToWishCandidate, type PriceMode,
} from '@/composables/subsidies/usePlanToRequest'

const props = defineProps<{ row: PlanToRequestRowState }>()
const emit = defineEmits<{
  // «Без товара из каталога» убрано (владелец, задача 2) — pick теперь всегда
  // с реальным товаром, null-варианта больше нет.
  pick: [c: PlanToWishCandidate]
  'set-price-mode': [mode: PriceMode]
  'open-catalog-search': []
  'write-to-initiator': []
  remove: []
}>()

const row = props.row
// Причина недоступности режима цены для ЭТОЙ строки (задача 3) — единственный
// источник usePlanToRequest.ts::priceModeDisabledReason, второй if/else не
// заводим (Правило №6). Используется и для disabled кнопки, и для текста tooltip.
function disabledReason(mode: PriceMode): string | null {
  return priceModeDisabledReason(row, mode)
}

const isOverResidual = computed(() => row.residualQuantity != null && Number(row.quantity) > Number(row.residualQuantity))
const primaryPurchase = computed(() => row.linkedPurchases[0] || null)
const primaryPurchaseLabel = computed(() => {
  const p = primaryPurchase.value
  if (!p) return ''
  return p.registry_number || (p.purchase_number != null ? `№ ${p.purchase_number}` : `#${p.purchase_id}`)
})

const matchBadge = computed(() => {
  if (!row.selectedCandidate) return ''
  if (row.exact && row.selectedCandidate.product_id === row.exact.product_id) return '100%'
  const byName = row.byName.find(c => c.product_id === row.selectedCandidate!.product_id)
  if (byName) return `${pct(byName.score)}%`
  return ''
})

function pct(score: number): number {
  const v = score <= 1 ? score * 100 : score
  return Math.max(0, Math.min(100, Math.round(v)))
}

// «Добавить товар» — открывает каталожный диалог создания товара
// (ProductFormDialog.vue через useProductsForm.ts, Правило №6) прямо из
// строки, без ухода на страницу «Товары». Наименование/ед. изм. плановой
// позиции предзаполняются; после сохранения товар подставляется как
// выбранный кандидат строки (см. onCreated в usePlanToRequestProductCreate.ts).
const productCreate = usePlanToRequestProductCreate((cand: PlanToWishCandidate) => {
  emit('pick', cand)
})

function openAddProduct() {
  productCreate.openCreateFor(row.name, row.unit)
}
</script>

<style scoped>
.ptr-row {
  border-bottom: 1px solid #E2E8F0;
}
.ptr-row:hover {
  background: #FAFAFC;
}
.ptr-td {
  padding: 10px;
  vertical-align: top;
}
.ptr-product-box {
  display: flex;
  align-items: center;
  padding: 4px 8px;
  border: 1px solid #E2E8F0;
  border-radius: 6px;
  min-height: 40px;
}
.ptr-product-box:hover {
  border-color: #7c3aed;
}
/* Строка без товара — недопустимо (владелец, задача 2): рамка/фон
   предупреждения на самом боксе, не только текст-плейсхолдер. */
.ptr-product-box--missing {
  border-color: rgba(245, 158, 11, 0.5);
  background: rgba(245, 158, 11, 0.08);
}
.ptr-product-box--missing:hover {
  border-color: #F59E0B;
}
.ptr-missing-text {
  color: #b45309;
  font-size: 12px;
}
/* Три режима цены построчно (задача 3) — узкая ячейка, кнопки переносятся по
   ширине, а не сжимают текст до нечитаемого. */
.ptr-price-toggle {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.ptr-price-toggle .v-btn {
  font-size: 10px;
  line-height: 1.1;
  min-width: 0;
  padding: 0 6px;
  height: 22px;
}
.ptr-price-btn--active {
  background: rgba(124, 58, 237, 0.1);
}
.ptr-warning {
  font-size: 11px;
  line-height: 1.4;
  color: #b45309;
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: 6px;
  padding: 6px 8px;
  max-width: 260px;
}
</style>
