<!-- WishDialogMobileMenu.vue — содержимое меню «⋮» в мобильной шапке
     WishFormDialog.vue. Собирает второстепенные кнопки, которые на компьютере
     лежат в v-card-actions (Скачать Excel/Скопировать/Перейти в закупку/
     Сбросить разбивку/Авансовый отчёт/Остановить) — условия видимости и сами
     действия НЕ дублируются здесь: кнопки только эмитят, вызовы actions.*/
     purchaseNav.*/distReset.* делает родитель (Правило №6, единственный
     источник действий). -->
<template>
  <v-list density="compact">
    <v-list-item
      prepend-icon="mdi-microsoft-excel"
      title="Скачать Excel — с фото"
      :disabled="downloadingExcel"
      @click="$emit('download-excel', true)"
    />
    <v-list-item
      prepend-icon="mdi-image-off"
      title="Скачать Excel — без фото"
      :disabled="downloadingExcel"
      @click="$emit('download-excel', false)"
    />
    <v-list-item
      prepend-icon="mdi-content-copy"
      title="Скопировать заявку"
      :disabled="copying"
      @click="$emit('copy-wish')"
    />

    <template v-if="relatedPurchases.length === 1">
      <v-list-item
        prepend-icon="mdi-cart-arrow-right"
        title="Перейти в закупку"
        :disabled="purchaseNavLoading"
        @click="$emit('go-to-purchase', null)"
      />
    </template>
    <template v-else-if="relatedPurchases.length > 1">
      <v-list-subheader>Перейти в закупку</v-list-subheader>
      <v-list-item
        v-for="p in relatedPurchases"
        :key="p.id"
        :title="`${p.registry_number || p.purchase_number || ('#' + p.id)} — ${p.status_label}`"
        prepend-icon="mdi-cart-arrow-right"
        @click="$emit('go-to-purchase', p.id)"
      />
    </template>

    <v-list-item
      v-if="hiddenPurchasesCount > 0"
      prepend-icon="mdi-backspace-outline"
      :title="`Сбросить разбивку (${hiddenPurchasesCount})`"
      @click="$emit('reset-split')"
    />

    <v-list-item
      v-if="wish.source !== 'advance_report'"
      prepend-icon="mdi-cash-refund"
      title="Оформить как авансовый отчёт"
      :disabled="!!wish.contracted_locked"
      :subtitle="wish.contracted_locked ? `Нельзя: ${wish.contracted_locked_reason || 'заявка уже на этапе договора или позже'}` : undefined"
      @click="$emit('convert-to-advance')"
    />

    <v-divider class="my-1" />

    <v-list-item
      v-if="!wish.stopped_at"
      prepend-icon="mdi-stop-circle-outline"
      title="Остановить заявку"
      base-color="error"
      @click="$emit('stop-wish')"
    />
  </v-list>
</template>

<script setup lang="ts">
import type { Wish } from '@/composables/wishes/wishTypes'
import type { WishPurchaseNavItem } from '@/composables/wishes/useWishPurchaseNav'

defineProps<{
  wish: Wish
  downloadingExcel: boolean
  copying: boolean
  relatedPurchases: WishPurchaseNavItem[]
  purchaseNavLoading: boolean
  hiddenPurchasesCount: number
}>()

defineEmits<{
  (e: 'download-excel', withPhoto: boolean): void
  (e: 'copy-wish'): void
  (e: 'go-to-purchase', purchaseId: number | null): void
  (e: 'reset-split'): void
  (e: 'convert-to-advance'): void
  (e: 'stop-wish'): void
}>()
</script>
