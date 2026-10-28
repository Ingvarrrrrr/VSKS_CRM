<!--
  StoreOffersPanel.vue — список предложений живого поиска по магазинам
  (этап 1, владелец, 28.10.2026). ОДИН компонент (ПРАВИЛО №6) — используется
  и в ProductPickerDialog.vue, и на странице «Товары» (ProductsView.vue),
  через общий composables/products/useStoreSearch.ts.

  Кнопки «Взять в закупку/каталог» ЗДЕСЬ НЕТ (этап 2) — только просмотр и
  переход в магазин. Цена — formatMoney (ПРАВИЛО №6, тот же хелпер, что и
  везде в проекте, второй форматтер не пишем).
-->
<template>
  <div class="store-offers-panel">
    <div v-if="loading" class="store-offers-panel__loading">
      <v-progress-circular indeterminate size="20" width="2" color="primary" />
      <span>Ищем в магазинах…</span>
    </div>

    <v-alert v-else-if="error" type="warning" density="compact" variant="tonal" class="mb-2">
      {{ error }}
    </v-alert>

    <template v-else-if="hasSearched">
      <div v-if="!offers.length" class="store-offers-panel__empty text-medium-emphasis">
        Ничего не нашлось в подключённых магазинах.
      </div>

      <div v-else class="store-offers-panel__list">
        <a
          v-for="(offer, idx) in offers"
          :key="`${offer.store_key}-${offer.store_article || idx}`"
          :href="offer.url"
          target="_blank"
          rel="noopener noreferrer"
          class="store-offer-card"
        >
          <img
            v-if="offer.image_url"
            :src="offer.image_url"
            :alt="offer.name"
            class="store-offer-card__img"
            loading="lazy"
          >
          <div v-else class="store-offer-card__img store-offer-card__img--placeholder">
            <v-icon icon="mdi-image-off-outline" size="20" color="grey" />
          </div>

          <div class="store-offer-card__body">
            <div class="store-offer-card__name" :title="offer.name">{{ offer.name }}</div>
            <div class="store-offer-card__meta">
              <span class="store-offer-card__price">{{ formatMoney(offer.price) }}</span>
              <span class="store-offer-card__store">{{ offer.store_name }}</span>
            </div>
          </div>

          <v-icon icon="mdi-open-in-new" size="16" class="store-offer-card__open" />
        </a>
      </div>

      <div v-if="stores.length" class="store-offers-panel__statuses text-caption text-medium-emphasis">
        <span v-for="s in stores" :key="s.key" class="store-offers-panel__status">
          {{ s.name }} — {{ statusText(s) }}<span v-if="s !== stores[stores.length - 1]">, </span>
        </span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { StoreOfferDTO, StoreStatusDTO } from '@/api'
import { formatMoney } from '@/utils/formatMoney'

defineProps<{
  offers: StoreOfferDTO[]
  stores: StoreStatusDTO[]
  loading: boolean
  error: string | null
  hasSearched: boolean
}>()

function statusText(s: StoreStatusDTO): string {
  if (s.status === 'ok') return `${s.count}`
  if (s.status === 'timeout') return 'не ответил'
  if (s.status === 'rate_limited') return 'слишком много запросов, подождите'
  if (s.status === 'blocked') return 'недоступен'
  return 'ошибка'
}
</script>

<style scoped>
.store-offers-panel__loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 4px;
  color: rgba(0, 0, 0, 0.6);
  font-size: 0.875rem;
}

.store-offers-panel__empty {
  padding: 12px 4px;
  font-size: 0.875rem;
}

.store-offers-panel__list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 360px;
  overflow-y: auto;
}

.store-offer-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  text-decoration: none;
  color: inherit;
  transition: background-color 0.15s ease;
}
.store-offer-card:hover {
  background-color: rgba(0, 0, 0, 0.04);
}

.store-offer-card__img {
  width: 40px;
  height: 40px;
  object-fit: contain;
  border-radius: 4px;
  flex: none;
  background: #fff;
}
.store-offer-card__img--placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.04);
}

.store-offer-card__body {
  flex: 1 1 auto;
  min-width: 0;
}

.store-offer-card__name {
  font-size: 0.8125rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.store-offer-card__meta {
  display: flex;
  gap: 8px;
  font-size: 0.75rem;
  color: rgba(0, 0, 0, 0.6);
}

.store-offer-card__price {
  font-weight: 600;
  color: rgba(0, 0, 0, 0.87);
}

.store-offer-card__open {
  flex: none;
  color: rgba(0, 0, 0, 0.4);
}

.store-offers-panel__statuses {
  margin-top: 8px;
  padding: 0 4px;
}
</style>
