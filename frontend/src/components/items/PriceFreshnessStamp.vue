<template>
  <div v-if="show" class="text-caption mt-1" :class="isStale ? PRICE_STALE_CLASS : 'text-medium-emphasis'">
    <v-tooltip :disabled="!tooltipText" :text="tooltipText" location="top" max-width="320">
      <template #activator="{ props: tip }">
        <span v-bind="tip" class="d-inline-flex align-center ga-1" style="white-space:normal">
          <v-icon v-if="isStale" size="12">mdi-alert-outline</v-icon>
          <span>{{ stampText }}</span>
        </span>
      </template>
    </v-tooltip>
  </div>
</template>

<script setup lang="ts">
// Владелец, сессия 2026-08-29: «показывать дату последней актуализации цены под
// строкой, устаревшее — подсвечивать оранжевым с тултипом-причиной». Общий кусок
// разметки для ItemsTableFlat/ItemsCardsView/ItemsTableStages/ItemsTableWish (и
// ProductsView), чтобы не плодить 4 копии одной и той же логики.
import { computed } from 'vue'
import { formatPriceStamp, freshnessTooltip, PRICE_STALE_CLASS, type PriceFreshness } from '@/composables/usePriceFreshness'

interface PriceMetaLike {
  price_updated_at?: string | null
  price_source?: string | null
  price_source_ref?: string | null
  price_freshness?: PriceFreshness | null
}

const props = defineProps<{
  priceMeta?: PriceMetaLike | null
}>()

const show = computed(() => {
  const m = props.priceMeta
  if (!m) return false
  return !!(m.price_updated_at || m.price_source || m.price_freshness)
})
const isStale = computed(() => !!props.priceMeta?.price_freshness?.is_stale)
const stampText = computed(() => formatPriceStamp(
  props.priceMeta?.price_updated_at,
  props.priceMeta?.price_source,
  props.priceMeta?.price_source_ref,
))
const tooltipText = computed(() => props.priceMeta?.price_freshness ? freshnessTooltip(props.priceMeta.price_freshness) : '')
</script>
