<template>
  <div class="wish-card" :class="{ 'readonly': readonly, 'wish-card-unseen': hasUnseenChanges }">
    <div class="wish-card-photo">
      <img v-if="item._photo_url" :src="item._photo_url" alt="" />
      <v-icon v-else color="grey-lighten-1" size="32">mdi-package-variant</v-icon>
    </div>
    <div class="wish-card-body">
      <div class="wish-card-name" :title="item.item_name">{{ item.item_name }}</div>
      <div class="wish-card-meta">
        <span class="wish-card-qty">{{ item.quantity }} {{ item.unit || 'шт' }}</span>
        <span class="wish-card-price">{{ formatMoney(item.total_price) }}</span>
      </div>
      <v-chip v-if="item._product_category" size="x-small" color="info" variant="tonal" class="mt-1">
        {{ item._product_category }}
      </v-chip>
    </div>
    <!-- Phase 31-06: unseen changes badge -->
    <div v-if="hasUnseenChanges" class="wish-card-unseen-badge" title="Чужие правки с последнего просмотра">
      <v-icon size="14" color="#fb923c">mdi-pencil-circle</v-icon>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface WishItem {
  id: number
  item_name: string
  quantity: number
  unit: string
  total_price: number
  target_column_key: string | null
  _photo_url?: string | null
  _product_category?: string
  unseen_changes_count?: number
}

const props = defineProps<{
  item: WishItem
  readonly?: boolean
  /** Phase 31-06: passed from parent when wish entity has unseen changes */
  unseenChangesCount?: number
}>()

/** Has unseen changes — either from wish-item prop or from item itself */
const hasUnseenChanges = computed(() =>
  (props.unseenChangesCount ?? props.item.unseen_changes_count ?? 0) > 0,
)

function formatMoney(v: number | null | undefined): string {
  if (v == null) return '0 ₽'
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(v)
}
</script>

<style scoped>
.wish-card {
  display: flex;
  gap: 8px;
  padding: 8px 10px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 6px;
  cursor: grab;
  transition: box-shadow 0.15s, transform 0.15s;
  position: relative;
}
.wish-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
  transform: translateY(-1px);
}
.wish-card.readonly {
  cursor: default;
  opacity: 0.85;
}
.wish-card.readonly:hover {
  box-shadow: none;
  transform: none;
}
/* Phase 31-06: GALA-orange border for unseen-changes card */
.wish-card.wish-card-unseen {
  border-color: #fb923c;
  border-width: 2px;
}
.wish-card-unseen-badge {
  position: absolute;
  top: 4px;
  right: 4px;
}
.wish-card-photo {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: rgba(var(--v-theme-surface-variant), 0.3);
  border-radius: 4px;
}
.wish-card-photo img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}
.wish-card-body {
  flex: 1;
  min-width: 0;
}
.wish-card-name {
  font-weight: 500;
  font-size: 0.875rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wish-card-meta {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), 0.7);
  margin-top: 2px;
}
.wish-card-price {
  font-weight: 600;
}
</style>
