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

    <!-- Товар из каталога -->
    <td class="ptr-td">
      <v-menu location="bottom start">
        <template #activator="{ props: menuProps }">
          <div v-bind="menuProps" class="ptr-product-box" style="cursor:pointer">
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
            <template v-else-if="row.productChosen">
              <v-icon icon="mdi-close-circle-outline" size="16" class="mr-1" color="grey" />
              <span class="text-medium-emphasis">Без товара из каталога</span>
            </template>
            <template v-else>
              <span class="text-medium-emphasis">Выбрать товар…</span>
            </template>
            <v-spacer />
            <v-icon icon="mdi-chevron-down" size="16" />
          </div>
        </template>

        <v-list density="compact" style="max-height:420px;overflow-y:auto;min-width:320px">
          <template v-if="row.exact">
            <v-list-subheader>Точное совпадение</v-list-subheader>
            <v-list-item @click="$emit('pick', row.exact)">
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
          <v-list-item prepend-icon="mdi-close-circle-outline" @click="$emit('pick', null)">
            <v-list-item-title>Без товара из каталога</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
    </td>

    <!-- Цена за единицу -->
    <td class="ptr-td">
      <v-btn-toggle
        :model-value="row.priceSourceOverride ?? 'inherit'"
        density="compact" variant="outlined" color="deep-purple" mandatory
        style="height:24px" class="mb-1"
        @update:model-value="onSourceToggle"
      >
        <v-btn size="x-small" value="inherit" :disabled="!row.selectedCandidate">Общее</v-btn>
        <v-btn size="x-small" value="catalog" :disabled="!row.selectedCandidate">Каталог</v-btn>
        <v-btn size="x-small" value="plan">План</v-btn>
      </v-btn-toggle>
      <v-text-field
        v-model.number="row.unitPrice"
        type="number" density="compact" variant="outlined" hide-details
        style="max-width:130px"
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
import type { PlanToRequestRow as PlanToRequestRowState, PlanToWishCandidate, PriceSource } from '@/composables/subsidies/usePlanToRequest'

const props = defineProps<{ row: PlanToRequestRowState }>()
const emit = defineEmits<{
  pick: [c: PlanToWishCandidate | null]
  'set-source-override': [s: PriceSource | null]
  'open-catalog-search': []
  'write-to-initiator': []
  remove: []
}>()

const row = props.row

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

function onSourceToggle(v: PriceSource | 'inherit') {
  emit('set-source-override', v === 'inherit' ? null : v)
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
