<template>
  <span v-if="summary && summary.count > 0 && !productId" class="planned-store-badge-wrapper inline-flex items-center">
    <v-chip
      size="x-small"
      color="indigo"
      variant="tonal"
      class="ml-1 cursor-pointer font-weight-medium"
      prepend-icon="mdi-store-search"
      title="Нажмите, чтобы посмотреть предложения в магазинах"
      @click.stop="dialogOpen = true"
    >
      🔎 Найдено в магазинах: {{ summary.count }}, от {{ formatMoney(summary.minPrice) }}
    </v-chip>

    <v-dialog v-model="dialogOpen" max-width="800">
      <v-card class="pa-4">
        <v-card-title class="d-flex align-center justify-space-between text-subtitle-1 font-weight-bold px-0 pt-0">
          <span>Предложения в магазинах для «{{ name }}»</span>
          <v-btn icon="mdi-close" variant="text" size="small" @click="dialogOpen = false" />
        </v-card-title>
        <v-card-text class="px-0 py-2">
          <StoreOffersPanel
            :offers="summary.offers"
            :stores="summary.stores"
            :loading="false"
            :error="null"
            :has-searched="true"
            :taking-url="takingUrl"
            :take-error="takeError"
            @take="onTake"
            @dismiss-take-error="takeError = null"
          />
        </v-card-text>
      </v-card>
    </v-dialog>
  </span>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { formatMoney } from '@/utils/formatMoney'
import type { StoreOfferDTO } from '@/api'
import StoreOffersPanel from '@/components/products/StoreOffersPanel.vue'
import { usePlannedStoreOffers, type PlannedStoreSummary } from '@/composables/products/usePlannedStoreOffers'

const props = defineProps<{
  name: string
  productId?: number | null
}>()

const emit = defineEmits<{
  (e: 'taken', product: any): void
}>()

const dialogOpen = ref(false)
const summary = ref<PlannedStoreSummary | null>(null)
const { requestOffers, take, takingUrl, takeError } = usePlannedStoreOffers()

function load() {
  if (!props.productId && props.name) {
    const resRef = requestOffers(props.name)
    watch(resRef, val => {
      summary.value = val
    }, { immediate: true })
  }
}

onMounted(() => {
  load()
})

watch(() => props.name, () => {
  load()
})

async function onTake(offer: StoreOfferDTO) {
  try {
    const res = await take(offer, props.name)
    emit('taken', res?.product || res)
    dialogOpen.value = false
  } catch {
    // takeError is shown in StoreOffersPanel
  }
}
</script>
