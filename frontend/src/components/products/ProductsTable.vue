<template>
  <div>
    <!-- Horizontal scrollbar — always visible above the table -->
    <div ref="mirrorScrollRef" class="mirror-hscroll">
      <div :style="{ width: tableScrollWidth + 'px', height: '1px' }" />
    </div>

    <v-card variant="outlined">
      <!-- Bulk action bar -->
      <ProductsBulkActionBar
        v-if="selectedIds.length"
        :selected-count="selectedIds.length"
        :total-count="items.length"
        :is-superadmin="isSuperadmin"
        @clear="$emit('update:selectedIds', [])"
        @select-all="$emit('update:selectedIds', items.map(p => p.id))"
        @bulk-edit="$emit('bulk-edit')"
        @toggle-active="active => $emit('toggle-active', active)"
        @bulk-delete="$emit('bulk-delete')"
        @delete-all="$emit('delete-all')"
      />

      <v-data-table
        v-resizable-columns="'products'"
        :model-value="selectedIds"
        show-select
        item-value="id"
        :headers="headers"
        :items="items"
        :loading="loading"
        :search="search"
        density="compact"
        fixed-header
        hover
        items-per-page="25"
        class="products-clickable products-table"
        @update:model-value="$emit('update:selectedIds', $event)"
        @click:row="(_: any, row: { item: Product }) => $emit('row-click', row.item)"
        :items-per-page-options="[25, 50, 100, -1]"
      >
        <!-- Photo -->
        <template #item.photo="{ item }">
          <v-avatar size="40" rounded="sm" class="my-1" style="overflow:hidden">
            <img
              v-if="item.has_photo"
              :src="`/api/products/${item.id}/photo`"
              style="width:40px;height:40px;object-fit:cover;display:block"
              @error="($event.target as HTMLImageElement).style.display='none'"
            />
            <img
              v-else-if="item.photo_url || item.photo_link"
              :src="(item.photo_url || item.photo_link) as string"
              style="width:40px;height:40px;object-fit:cover;display:block"
              @error="($event.target as HTMLImageElement).style.display='none'"
            />
            <v-icon v-else icon="mdi-package-variant" color="grey" />
          </v-avatar>
        </template>

        <!-- Name + description -->
        <template #item.name="{ item }">
          <div class="font-weight-medium">{{ item.name }}</div>
          <div v-if="item.description" class="text-caption text-medium-emphasis" style="max-width:280px;white-space:normal;line-height:1.3">
            {{ item.description.slice(0, 100) }}{{ item.description.length > 100 ? '…' : '' }}
          </div>
          <v-chip v-if="item.description_44fz" size="x-small" variant="tonal" color="blue" class="mt-1">44-ФЗ</v-chip>
        </template>

        <!-- Type chip -->
        <template #item.product_type="{ item }">
          <v-chip v-if="item.product_type" size="x-small" variant="tonal" :color="typeColor(item.product_type)">
            {{ item.product_type }}
          </v-chip>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <!-- Price -->
        <template #item.price="{ item }">
          <div v-if="item.price" class="font-weight-medium text-blue-darken-2">
            {{ Number(item.price).toLocaleString('ru-RU') }} ₽
          </div>
          <div v-if="item.price_links?.length" class="text-caption text-medium-emphasis">
            {{ item.price_links.length }} ист.
          </div>
          <span v-if="!item.price" class="text-medium-emphasis">—</span>
          <!-- Владелец, сессия 2026-08-29: штамп даты/источника актуализации мелким
               шрифтом под ценой; устаревшее — оранжевым с иконкой предупреждения. -->
          <v-tooltip v-if="item.price" :disabled="!item.price_freshness?.is_stale" :text="freshnessTooltip(item.price_freshness)" location="top" max-width="320">
            <template #activator="{ props: tip }">
              <div v-bind="tip" class="text-caption" :class="freshnessColor(item.price_freshness) === 'warning' ? PRICE_STALE_CLASS : 'text-medium-emphasis'">
                <v-icon v-if="item.price_freshness?.is_stale" :icon="freshnessIcon(item.price_freshness)" size="12" class="mr-1" />{{ formatPriceStamp(item.price_updated_at, item.price_source, item.price_source_ref) }}
              </div>
            </template>
          </v-tooltip>
        </template>

        <!-- Contract Price -->
        <template #item.contract_price="{ item }">
          <template v-if="item.contract_price">
            <div class="font-weight-medium text-green-darken-2">
              {{ Number(item.contract_price).toLocaleString('ru-RU') }} ₽
            </div>
            <div v-if="item.contract_number" class="text-caption text-medium-emphasis">
              № {{ item.contract_number }}
              <span v-if="item.contract_date"> от {{ item.contract_date }}</span>
            </div>
            <v-tooltip :text="item.price_shared ? 'Цена видна другим организациям' : 'Цена скрыта от других организаций'" location="top">
              <template #activator="{ props: tip }">
                <v-btn v-bind="tip" :icon="item.price_shared ? 'mdi-eye' : 'mdi-eye-off'" variant="text"
                  size="x-small" :color="item.price_shared ? 'success' : 'grey'"
                  @click="$emit('toggle-sharing', item)" />
              </template>
            </v-tooltip>
          </template>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <!-- Price freshness -->
        <template #item.price_freshness="{ item }">
          <v-tooltip v-if="item.price" :disabled="!item.price_freshness" :text="freshnessTooltip(item.price_freshness)" location="top" max-width="320">
            <template #activator="{ props: tip }">
              <div v-bind="tip">
                <v-chip v-if="item.price_freshness?.is_stale" size="x-small" color="warning" variant="tonal" class="mb-1">
                  <v-icon start icon="mdi-alert-outline" size="14" />{{ item.price_freshness?.reason === 'fx' ? 'Курс — проверить цену' : 'Требует актуализации' }}
                </v-chip>
                <div class="text-caption" :class="item.price_freshness?.is_stale ? PRICE_STALE_CLASS : 'text-medium-emphasis'">
                  {{ formatPriceStamp(item.price_updated_at, item.price_source, item.price_source_ref) }}
                </div>
              </div>
            </template>
          </v-tooltip>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <!-- Country origin -->
        <template #item.country_origin="{ item }">
          <v-chip v-if="item.country_origin" size="x-small" variant="tonal"
            :color="isDomesticCountry(item.country_origin) ? 'primary' : 'orange'">
            {{ item.country_origin }}
          </v-chip>
          <v-chip v-else size="x-small" variant="tonal" color="error">не указана</v-chip>
        </template>

        <!-- Active -->
        <template #item.is_active="{ item }">
          <v-chip size="x-small" :color="item.is_active ? 'success' : 'grey'" variant="tonal">
            {{ item.is_active ? 'Активен' : 'Неактивен' }}
          </v-chip>
        </template>

        <!-- TZ verified -->
        <template #item.tz_verified_at="{ item }">
          <v-progress-circular v-if="tzVerifying === item.id + '_standard'" indeterminate size="18" width="2" color="primary" />
          <div v-else class="d-flex align-center gap-1">
            <v-tooltip
              :text="item.tz_verified_at
                ? `${new Date(item.tz_verified_at).toLocaleDateString('ru-RU')} · ${item.tz_verified_by}`
                : 'Нажмите чтобы подтвердить'"
              location="top"
            >
              <template #activator="{ props }">
                <v-icon
                  v-bind="props"
                  :icon="item.tz_verified_at ? 'mdi-checkbox-marked-circle' : 'mdi-checkbox-blank-circle-outline'"
                  :color="item.tz_verified_at ? 'success' : 'grey-lighten-1'"
                  style="cursor: pointer"
                  @click.stop="!item.tz_verified_at ? $emit('verify-tz', item, 'standard') : null"
                />
              </template>
            </v-tooltip>
            <v-tooltip v-if="item.tz_verified_at && isAdmin" text="Снять отметку (Администратор)" location="top">
              <template #activator="{ props }">
                <v-icon v-bind="props" icon="mdi-close-circle-outline" color="error" size="14"
                  style="cursor:pointer; opacity:0.7" @click.stop="$emit('unverify-tz', item, 'standard')" />
              </template>
            </v-tooltip>
          </div>
        </template>

        <!-- TZ 44fz verified -->
        <template #item.tz_44fz_verified_at="{ item }">
          <v-progress-circular v-if="tzVerifying === item.id + '_44fz'" indeterminate size="18" width="2" color="blue" />
          <div v-else class="d-flex align-center gap-1">
            <v-tooltip
              :text="item.tz_44fz_verified_at
                ? `${new Date(item.tz_44fz_verified_at).toLocaleDateString('ru-RU')} · ${item.tz_44fz_verified_by}`
                : 'Нажмите чтобы подтвердить (44-ФЗ)'"
              location="top"
            >
              <template #activator="{ props }">
                <v-icon
                  v-bind="props"
                  :icon="item.tz_44fz_verified_at ? 'mdi-checkbox-marked-circle' : 'mdi-checkbox-blank-circle-outline'"
                  :color="item.tz_44fz_verified_at ? 'blue-darken-2' : 'grey-lighten-1'"
                  style="cursor: pointer"
                  @click.stop="!item.tz_44fz_verified_at ? $emit('verify-tz', item, '44fz') : null"
                />
              </template>
            </v-tooltip>
            <v-tooltip v-if="item.tz_44fz_verified_at && isAdmin" text="Снять отметку (Администратор)" location="top">
              <template #activator="{ props }">
                <v-icon v-bind="props" icon="mdi-close-circle-outline" color="error" size="14"
                  style="cursor:pointer; opacity:0.7" @click.stop="$emit('unverify-tz', item, '44fz')" />
              </template>
            </v-tooltip>
          </div>
        </template>

        <!-- Actions -->
        <template #item.actions="{ item }">
          <div class="d-flex gap-1" @click.stop>
            <v-tooltip text="Актуализировать цену" location="top">
              <template #activator="{ props: tip }">
                <v-btn v-bind="tip" icon="mdi-cash-refresh" variant="text" size="small"
                  :color="item.price_freshness?.is_stale ? 'warning' : 'teal'"
                  @click.stop="$emit('actualize', item)" />
              </template>
            </v-tooltip>
            <v-btn icon="mdi-delete-outline" variant="text" size="small" color="error"
              @click.stop="$emit('delete', item)" />
          </div>
        </template>

        <template #no-data>
          <div class="text-center py-10">
            <v-icon icon="mdi-package-variant-closed" size="48" color="grey-lighten-1" class="mb-3" />
            <div class="text-medium-emphasis">Товары не найдены</div>
          </div>
        </template>
      </v-data-table>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import {
  PRICE_STALE_CLASS,
  formatPriceStamp,
  freshnessColor,
  freshnessIcon,
  freshnessTooltip,
} from '@/composables/usePriceFreshness'
import { onMounted, nextTick } from 'vue'
import { typeColor, isDomesticCountry } from '@/composables/products/productsTypes'
import type { Product } from '@/composables/products/productsTypes'
import { useProductsScroll } from '@/composables/products/useProductsScroll'
import ProductsBulkActionBar from './ProductsBulkActionBar.vue'

defineProps<{
  headers: any[]
  items: Product[]
  loading: boolean
  search: string
  selectedIds: number[]
  isSuperadmin: boolean
  isAdmin: boolean
  tzVerifying: string | null
}>()

// Зеркальная горизонтальная полоса прокрутки — живёт вместе с таблицей.
const { mirrorScrollRef, tableScrollWidth, initMirrorScroll } = useProductsScroll()
onMounted(async () => {
  await nextTick()
  setTimeout(initMirrorScroll, 400)
})

defineEmits<{
  (e: 'update:selectedIds', ids: number[]): void
  (e: 'row-click', item: Product): void
  (e: 'toggle-sharing', item: Product): void
  (e: 'verify-tz', item: Product, tzType: 'standard' | '44fz'): void
  (e: 'unverify-tz', item: Product, tzType: 'standard' | '44fz'): void
  (e: 'actualize', item: Product): void
  (e: 'delete', item: Product): void
  (e: 'bulk-edit'): void
  (e: 'toggle-active', active: boolean): void
  (e: 'bulk-delete'): void
  (e: 'delete-all'): void
}>()
</script>

<style scoped>
.products-clickable :deep(tbody tr) { cursor: pointer; }
/* Mirror scrollbar — between filter card and table card */
.mirror-hscroll {
  overflow-x: auto;
  overflow-y: hidden;
  height: 16px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 4px;
  margin-bottom: 4px;
  background: rgba(var(--v-theme-on-surface), 0.03);
}
/* Hide native scrollbar inside the table (mirror takes over) */
.products-table :deep(.v-table__wrapper) {
  scrollbar-width: none;
}
.products-table :deep(.v-table__wrapper::-webkit-scrollbar) {
  display: none;
}
</style>
