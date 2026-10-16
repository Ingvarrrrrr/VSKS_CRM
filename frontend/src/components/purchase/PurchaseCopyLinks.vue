<template>
  <div v-if="linksForPurchase && (linksForPurchase.copied_from || linksForPurchase.copies.length)" class="purchase-copy-links mb-3">
    <div v-if="linksForPurchase.copied_from" class="text-caption text-medium-emphasis d-flex align-center ga-1 flex-wrap">
      <v-icon size="14" icon="mdi-content-duplicate" />
      <span>
        Копия из {{ linksForPurchase.copied_from.registry_number }}
        (субсидия «{{ linksForPurchase.copied_from.subsidy_name }}»)
      </span>
      <v-btn size="x-small" variant="text" color="primary" @click="openOrder(linksForPurchase.copied_from.id)">Открыть</v-btn>
    </div>
    <div v-if="linksForPurchase.copies.length" class="text-caption text-medium-emphasis d-flex align-center ga-1 flex-wrap mt-1">
      <v-icon size="14" icon="mdi-content-copy" />
      <span>Скопирована в:</span>
      <template v-for="(c, i) in linksForPurchase.copies" :key="c.id">
        <span>{{ c.registry_number }} (субсидия «{{ c.subsidy_name }}»){{ i < linksForPurchase.copies.length - 1 ? ';' : '' }}</span>
        <v-btn size="x-small" variant="text" color="primary" @click="openOrder(c.id)">Открыть</v-btn>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
// «Копия из РЕЕ-… / Скопирована в: …» — блок в карточке закупки
// (views/CreateOrderView.vue), данные из GET /purchase-transfer/links/{id}
// (composables/purchaseTransfer/usePurchaseTransfer.ts::loadLinks, ПРАВИЛО №6 —
// тот же composable, что и диалоги копирования/переноса). Ничего не рендерит,
// если переносов не было.
import { computed, onMounted, watch } from 'vue'
import { usePurchaseTransfer } from '@/composables/purchaseTransfer/usePurchaseTransfer'

const props = defineProps<{ purchaseId: number | null }>()

const transfer = usePurchaseTransfer()
const linksForPurchase = computed(() => (props.purchaseId ? transfer.linksCache[props.purchaseId] ?? null : null))

async function load() {
  if (!props.purchaseId) return
  try {
    await transfer.loadLinks(props.purchaseId)
  } catch {
    // тихо — блок просто не покажется
  }
}

onMounted(load)
watch(() => props.purchaseId, load)

function openOrder(id: number) {
  window.open(`/orders/${id}/edit`, '_blank', 'noopener')
}
</script>

<style scoped>
.purchase-copy-links {
  padding: 2px 0;
}
</style>
