<template>
  <!-- Модульный 3-стадийный редактор для формы «Питание» (services_food):
       ТЗ («Как в ТЗ») / Договор («Как в договоре») / Поставка («Как поставили»).
       Переиспользует ItemFormFields.vue — второй копии полей формы не заводит (Правило №5/№6). -->
  <div class="food-items-panels">
    <v-sheet
      v-for="(item, fIdx) in items"
      :key="item._uid ?? fIdx"
      class="food-item-panel pa-3 mb-3"
      variant="outlined"
      rounded
    >
      <div class="d-flex align-center justify-space-between flex-wrap ga-2 mb-3">
        <div class="d-flex align-center ga-2 flex-wrap">
          <span class="text-subtitle-2 font-weight-medium">
            Позиция {{ fIdx + 1 }}<template v-if="item.item_name">: {{ item.item_name }}</template>
          </span>
          <v-chip size="x-small" color="info" variant="tonal">
            ТЗ: {{ stageTotals(fIdx).tz > 0 ? fmtRub(stageTotals(fIdx).tz) : '—' }}
          </v-chip>
          <v-chip size="x-small" color="success" variant="tonal">
            Дог: {{ stageTotals(fIdx).dog > 0 ? fmtRub(stageTotals(fIdx).dog) : '—' }}
          </v-chip>
          <v-chip size="x-small" color="purple" variant="tonal">
            Пост: {{ stageTotals(fIdx).delivery > 0 ? fmtRub(stageTotals(fIdx).delivery) : '—' }}
          </v-chip>
        </div>
        <v-btn
          v-if="!readonly && items.length > 1"
          icon="mdi-delete-outline"
          size="small"
          variant="text"
          color="error"
          title="Удалить позицию"
          @click="emit('remove-item', fIdx)"
        />
      </div>

      <!-- Стадия 1: Как в ТЗ -->
      <div class="food-stage-block food-stage-block--tz pa-3 mb-2 rounded">
        <div class="d-flex align-center ga-2 mb-2">
          <v-chip color="info" size="x-small" variant="tonal">Как в ТЗ</v-chip>
        </div>
        <ItemFormFields
          item-form="food"
          :fields="itemFormFields"
          :model-value="cleanExtra(item.extra_attrs)"
          :unit-price="item.unit_price"
          :total-price="item.total_price"
          :disabled="tzDisabled"
          @update:model-value="(v) => onUpdateTzExtra(item, fIdx, v)"
          @update:unit-price="(v) => { item.unit_price = v; emit('calc-item-total', fIdx) }"
        />
      </div>

      <!-- Стадия 2: Как в договоре -->
      <div class="food-stage-block food-stage-block--contract pa-3 mb-2 rounded">
        <div class="d-flex align-center ga-2 mb-2 flex-wrap">
          <v-chip color="success" size="x-small" variant="tonal">Как в договоре</v-chip>
          <span
            v-if="!getContractItemFor(fIdx) && !isAdvance && !readonly"
            class="text-caption text-medium-emphasis"
          >
            Заполните поля ниже или нажмите «Перенести все позиции из ТЗ в договор» сверху
          </span>
        </div>
        <ItemFormFields
          item-form="food"
          :fields="itemFormFields"
          :model-value="contractExtraFor(item, fIdx)"
          :unit-price="contractUnitPriceFor(item, fIdx)"
          :total-price="contractTotalFor(item, fIdx)"
          :disabled="readonly"
          @update:model-value="(v) => emit('update-contract-field', fIdx, 'extra_attrs', v)"
          @update:unit-price="(v) => emit('update-contract-field', fIdx, 'unit_price', v)"
        />
      </div>

      <!-- Стадия 3: Как поставили -->
      <div class="food-stage-block food-stage-block--delivery pa-3 rounded">
        <div class="d-flex align-center ga-2 mb-2">
          <v-chip color="purple" size="x-small" variant="tonal">Как поставили</v-chip>
        </div>
        <ItemFormFields
          v-if="isDelivered(fIdx)"
          item-form="food"
          :fields="itemFormFields"
          :model-value="acceptedDeliveryFor(fIdx).extra_attrs"
          :unit-price="acceptedDeliveryFor(fIdx).unit_price"
          :total-price="acceptedDeliveryFor(fIdx).total"
          :disabled="readonly"
          @update:model-value="(v) => emit('update-accepted-form', fIdx, { extra_attrs: v })"
          @update:unit-price="(v) => emit('update-accepted-form', fIdx, { unit_price: v })"
        />
        <ItemFormFields
          v-else-if="isAdvance"
          item-form="food"
          :fields="itemFormFields"
          :model-value="cleanExtra(item.extra_attrs)"
          :unit-price="item.unit_price"
          :total-price="item.total_price"
          :disabled="true"
        />
        <div v-else class="text-caption text-medium-emphasis py-1">
          Появится после перевода закупки в статус «Поставлено»
        </div>
      </div>
    </v-sheet>

    <div v-if="contractItemsTotal > 0" class="mt-2 d-flex ga-2 flex-wrap align-center">
      <v-chip color="primary" variant="tonal" size="small">
        Сумма позиций договора: {{ fmtRub(contractItemsTotal) }}
      </v-chip>
      <v-chip color="info" variant="tonal" size="small">
        НМЦД заявки: {{ fmtRub(purchasePlannedTotal) }}
      </v-chip>
      <v-chip
        v-if="contractSavings != null"
        :color="Number(contractSavings) >= 0 ? 'success' : 'error'"
        variant="tonal"
        size="small"
      >
        Экономия: {{ fmtRub(contractSavings) }} ({{ contractSavingsPercent }}%)
      </v-chip>
    </div>
  </div>
</template>

<script setup lang="ts">
import ItemFormFields from '@/components/items/ItemFormFields.vue'
import type { ContractItem } from '@/types/contractItem'
import type { ExtraAttrs, ItemFormField } from '@/utils/itemAmounts'

export interface AcceptedDeliverySnapshot {
  extra_attrs: ExtraAttrs
  unit_price: number | null
  total: number | null
  item_form: string | null
}

const props = defineProps<{
  items: any[]
  readonly: boolean
  tzDisabled: boolean
  itemFormFields: ItemFormField[]
  isAdvance: boolean
  contractItemsTotal: number
  purchasePlannedTotal: number
  contractSavings: number | null
  contractSavingsPercent: number | string | null
  getContractItemFor: (idx: number) => ContractItem | undefined
  stageTotals: (idx: number) => { tz: number; dog: number; delivery: number }
  isDelivered: (idx: number) => boolean
  acceptedDeliveryFor: (idx: number) => AcceptedDeliverySnapshot
  fmtRub: (v: number | null | undefined) => string
}>()

const emit = defineEmits<{
  'remove-item': [idx: number]
  'calc-item-total': [idx: number]
  'update-contract-field': [idx: number, field: string, val: unknown]
  'update-accepted-form': [idx: number, patch: Partial<AcceptedDeliverySnapshot>]
}>()

function cleanExtra(raw: ExtraAttrs | null | undefined): ExtraAttrs {
  if (!raw || typeof raw !== 'object') return {}
  if (!('_accepted' in raw)) return raw
  const copy: ExtraAttrs = { ...raw }
  delete copy._accepted
  return copy
}

function onUpdateTzExtra(item: any, idx: number, nextExtra: ExtraAttrs) {
  const prevAccepted = item?.extra_attrs && typeof item.extra_attrs === 'object' ? item.extra_attrs._accepted : undefined
  const merged: ExtraAttrs = { ...nextExtra }
  if (prevAccepted !== undefined) merged._accepted = prevAccepted
  item.extra_attrs = merged
  emit('calc-item-total', idx)
}

function contractExtraFor(item: any, idx: number): ExtraAttrs {
  const ci = props.getContractItemFor(idx)
  if (ci) return cleanExtra(ci.extra_attrs)
  return props.isAdvance ? cleanExtra(item?.extra_attrs) : {}
}

function contractUnitPriceFor(item: any, idx: number): number | null {
  const ci = props.getContractItemFor(idx)
  if (ci) return ci.unit_price != null ? Number(ci.unit_price) : null
  return props.isAdvance && item?.unit_price != null ? Number(item.unit_price) : null
}

function contractTotalFor(item: any, idx: number): number | null {
  const ci = props.getContractItemFor(idx)
  if (ci) return ci.total != null ? Number(ci.total) : null
  return props.isAdvance && item?.total_price != null ? Number(item.total_price) : null
}
</script>

<style scoped>
.food-stage-block {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.food-stage-block--tz {
  background: rgba(25, 118, 210, 0.04);
}
.food-stage-block--contract {
  background: rgba(46, 125, 50, 0.04);
}
.food-stage-block--delivery {
  background: rgba(156, 39, 176, 0.04);
}
</style>
