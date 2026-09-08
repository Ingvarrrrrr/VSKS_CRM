<template>
  <div>
    <v-row dense>
      <v-col v-for="c in items" :key="c.id" cols="12" sm="6" lg="4">
        <v-card variant="outlined" class="h-100 d-flex flex-column" hover @click="$emit('open-edit', c)">
          <v-card-item class="pb-1">
            <template #prepend>
              <v-checkbox-btn
                :model-value="selectedIds.has(c.id)"
                density="compact"
                @click.stop
                @update:model-value="$emit('toggle-one', c.id)"
              />
            </template>
            <v-card-title class="text-body-2 font-weight-bold" style="overflow-wrap:anywhere">
              {{ c.name }}
            </v-card-title>
          </v-card-item>
          <v-card-text class="py-1 flex-grow-1">
            <div class="d-flex gap-2 mb-2 flex-wrap">
              <span v-if="c.inn" class="text-caption text-medium-emphasis">ИНН: <span class="text-mono font-weight-medium text-body-2">{{ c.inn }}</span></span>
              <span v-if="c.kpp" class="text-caption text-medium-emphasis">КПП: <span class="text-mono font-weight-medium text-body-2">{{ c.kpp }}</span></span>
            </div>
            <div v-if="c.address" class="text-caption text-medium-emphasis mb-1">{{ c.address }}</div>
            <div v-if="c.contact_person" class="text-caption mb-1">{{ c.contact_person }}</div>
            <div v-if="c.phone || c.email" class="text-caption text-medium-emphasis">
              <span v-if="c.phone">{{ formatPhoneRu(c.phone) }}</span>
              <span v-if="c.phone && c.email"> · </span>
              <span v-if="c.email">{{ c.email }}</span>
            </div>
            <div v-if="c.product_categories.length > 0" class="d-flex flex-wrap gap-1 mt-2">
              <v-chip v-if="c.product_categories.includes('Все')" size="x-small" color="blue" variant="tonal">Все категории</v-chip>
              <template v-else>
                <v-chip v-for="cat in c.product_categories.slice(0, 2)" :key="cat" size="x-small" color="teal" variant="tonal">{{ cat }}</v-chip>
                <v-chip
                  v-if="c.product_categories.length > 2"
                  size="x-small" color="grey" variant="tonal"
                  class="cursor-pointer"
                  @click.stop="$emit('open-categories', c)"
                >+{{ c.product_categories.length - 2 }}</v-chip>
              </template>
            </div>
          </v-card-text>
          <v-divider />
          <v-card-actions class="py-1" @click.stop>
            <v-spacer />
            <v-btn icon="mdi-delete" variant="text" size="small" color="error" @click.stop="$emit('delete', c)" />
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
    <div v-if="!items.length" class="text-center py-10 text-medium-emphasis">
      <v-icon icon="mdi-account-off-outline" size="48" color="grey-lighten-1" class="d-block mx-auto mb-3" />
      Контрагенты не найдены
    </div>
    <v-pagination
      v-if="totalPages > 1"
      :model-value="page"
      :length="totalPages"
      density="compact"
      total-visible="7"
      class="d-flex justify-center mt-4"
      @update:model-value="$emit('update:page', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import { formatPhoneRu } from '@/utils/phoneFormat'
import type { ContractorWithStats } from '@/composables/contractors/contractorsTypes'

defineProps<{
  items: ContractorWithStats[]
  selectedIds: Set<number>
  page: number
  totalPages: number
}>()
defineEmits<{
  (e: 'toggle-one', id: number): void
  (e: 'open-edit', c: ContractorWithStats): void
  (e: 'open-categories', c: ContractorWithStats): void
  (e: 'delete', c: ContractorWithStats): void
  (e: 'update:page', page: number): void
}>()
</script>
