<template>
  <div v-if="canQuery" class="mt-1">
    <!-- Режим 1: Закупка из субсидии / плановой позиции — кнопка-плашка «Показать актуальную цену» -->
    <template v-if="isFromSubsidyPlan && !expanded">
      <v-btn
        size="x-small"
        variant="tonal"
        color="primary"
        density="compact"
        :loading="loading"
        prepend-icon="mdi-tag-search-outline"
        class="text-none"
        @click.stop="onRevealClick"
      >
        Показать актуальную цену
      </v-btn>
    </template>

    <!-- Режим 2 и раскрытая плашка: показываем розницу + за похожий объём + оценку рынка -->
    <div v-else-if="result || loading || errorText" class="text-caption market-price-box">
      <div v-if="loading && !result" class="d-inline-flex align-center ga-1 text-medium-emphasis">
        <v-progress-circular indeterminate size="12" width="2" />
        <span>Уточняем актуальную цену…</span>
      </div>

      <div v-else-if="errorText && !result" class="text-error">
        {{ errorText }}
      </div>

      <template v-else-if="result">
        <div class="d-flex align-center flex-wrap ga-1">
          <v-menu v-model="menuOpen" :close-on-content-click="false" location="bottom start" max-width="380">
            <template #activator="{ props: menuProps }">
              <v-chip
                v-bind="menuProps"
                size="x-small"
                variant="tonal"
                :color="marketStatus.color"
                class="cursor-pointer"
                @click.stop
              >
                <template v-if="isFromSubsidyPlan">
                  Розница: {{ fmtPrice(result.retail_price) }} · Объём ({{ result.volume_batch }}): {{ fmtPrice(result.volume_price) }}
                </template>
                <template v-else>
                  Актуально: {{ fmtPrice(result.retail_price) }}
                  <span v-if="showVolumeInline"> · объём ({{ result.volume_batch }}): {{ fmtPrice(result.volume_price) }}</span>
                </template>
                <v-icon end size="12">mdi-chevron-down</v-icon>
              </v-chip>
            </template>

            <v-card density="compact" class="pa-3" min-width="300">
              <div class="d-flex align-center justify-space-between mb-2">
                <span class="text-subtitle-2 font-weight-bold">Актуальность цены в рынке</span>
                <v-btn
                  size="x-small" variant="text" color="primary" :loading="loading"
                  prepend-icon="mdi-refresh"
                  @click="runLoad(true, false)"
                >
                  Обновить
                </v-btn>
              </div>

              <div class="d-flex flex-column ga-1 text-body-2">
                <div class="d-flex justify-space-between ga-3">
                  <span class="text-medium-emphasis">В розницу (медиана):</span>
                  <span class="font-weight-bold">{{ fmtPrice(result.retail_price) }}</span>
                </div>
                <div v-if="result.retail_min != null && result.retail_count > 1" class="text-caption text-medium-emphasis">
                  Диапазон по {{ result.retail_count }} маг.: {{ fmtPrice(result.retail_min) }} – {{ fmtPrice(result.retail_max) }}
                </div>

                <div class="d-flex justify-space-between ga-3 mt-1">
                  <span class="text-medium-emphasis">За объём ({{ result.volume_batch }}{{ unit ? ' ' + unit : '' }}):</span>
                  <span class="font-weight-bold text-primary">{{ fmtPrice(result.volume_price) }}</span>
                </div>
                <div v-if="result.volume_note" class="text-caption text-medium-emphasis">
                  {{ result.volume_note }}
                </div>

                <div v-if="marketStatus.status !== 'none'" class="mt-1">
                  <v-chip size="x-small" :color="marketStatus.color" variant="flat">
                    {{ marketStatus.label }}
                  </v-chip>
                </div>
              </div>

              <v-divider v-if="result.offers.length" class="my-2" />
              <div v-if="result.offers.length" class="d-flex flex-column ga-1">
                <div class="text-caption font-weight-medium text-medium-emphasis">Цены магазинов:</div>
                <div v-for="(off, i) in result.offers" :key="i" class="d-flex align-center justify-space-between text-caption ga-2">
                  <a v-if="off.url" :href="off.url" target="_blank" rel="noopener noreferrer" class="text-truncate" style="max-width:210px">
                    {{ off.store_name }}
                  </a>
                  <span v-else class="text-truncate" style="max-width:210px">{{ off.store_name }}</span>
                  <span class="font-weight-medium">{{ fmtPrice(off.price) }}</span>
                </div>
              </div>

              <div v-if="!readonly && (result.volume_price || result.retail_price)" class="d-flex ga-2 mt-3 justify-end">
                <v-btn
                  v-if="result.retail_price"
                  size="x-small" variant="tonal" color="secondary"
                  @click="applyAndClose(result.retail_price)"
                >
                  Подставить розницу
                </v-btn>
                <v-btn
                  v-if="result.volume_price && result.volume_price !== result.retail_price"
                  size="x-small" variant="flat" color="primary"
                  @click="applyAndClose(result.volume_price)"
                >
                  Подставить за объём
                </v-btn>
              </div>
            </v-card>
          </v-menu>

          <v-chip
            v-if="marketStatus.status !== 'none' && isFromSubsidyPlan"
            size="x-small"
            :color="marketStatus.color"
            variant="outlined"
          >
            {{ marketStatus.label }}
          </v-chip>

          <v-btn
            v-if="!readonly && (result.volume_price || result.retail_price) && !isFromSubsidyPlan"
            size="x-small" variant="text" color="primary" density="compact"
            class="px-1" style="min-width:0;height:18px"
            @click.stop="emit('apply-price', (result.volume_price ?? result.retail_price)!)"
          >
            подставить
          </v-btn>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { batchLabelFromQuantity } from '@/utils/avgPrice'
import {
  evaluateMarketStatus,
  useMarketPriceCheck,
  type MarketPriceCheckResult,
} from '@/composables/useMarketPriceCheck'

const props = defineProps<{
  productId?: number | null
  itemName?: string | null
  quantity?: number | null
  unit?: string | null
  unitPrice?: number | null
  isFromSubsidyPlan?: boolean
  readonly?: boolean
}>()

const emit = defineEmits<{ 'apply-price': [price: number] }>()

const { checkMarketPrice, cachedFor } = useMarketPriceCheck()
const expanded = ref(false)
const loading = ref(false)
const menuOpen = ref(false)
const errorText = ref('')
const result = ref<MarketPriceCheckResult | null>(null)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const canQuery = computed(() => props.productId != null || !!(props.itemName || '').trim())
const batchBucket = computed(() => batchLabelFromQuantity(props.quantity) || '1-9')
const marketStatus = computed(() => evaluateMarketStatus(props.unitPrice, result.value))
const showVolumeInline = computed(() => {
  const r = result.value
  if (!r || r.volume_price == null) return false
  return r.volume_price !== r.retail_price || batchBucket.value !== '1-9'
})

function fmtPrice(v: number | null | undefined): string {
  if (v == null || v <= 0) return 'нет данных'
  return Number(v).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽'
}

async function runLoad(refreshLive: boolean, background: boolean) {
  loading.value = true
  errorText.value = ''
  try {
    const res = await checkMarketPrice({
      productId: props.productId,
      itemName: props.itemName,
      quantity: props.quantity,
      unit: props.unit,
      refreshLive,
      background,
    })
    result.value = res
    if (!res) errorText.value = 'Не удалось получить рыночную цену'
  } catch {
    errorText.value = 'Ошибка запроса рыночной цены'
  } finally {
    loading.value = false
  }
}

function onRevealClick() {
  expanded.value = true
  void runLoad(true, false)
}

function applyAndClose(price: number | null | undefined) {
  if (price == null || price <= 0) return
  emit('apply-price', price)
  menuOpen.value = false
}

watch(
  [() => props.productId, () => props.itemName, batchBucket, () => props.isFromSubsidyPlan],
  ([pid, _name, _batch, fromPlan]) => {
    const cached = cachedFor({ productId: props.productId, itemName: props.itemName, quantity: props.quantity })
    if (cached) result.value = cached
    else if (!fromPlan) result.value = null

    if (fromPlan) {
      if (expanded.value) void runLoad(true, true)
      return
    }
    if (pid == null) return
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      void runLoad(false, true)
    }, 450)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (debounceTimer) clearTimeout(debounceTimer)
})
</script>

<style scoped>
.market-price-box {
  line-height: 1.25;
}
.cursor-pointer {
  cursor: pointer;
}
</style>
