<template>
  <div class="table-card">
    <v-table class="contractors-table">
      <thead>
        <tr>
          <th style="width:48px">
            <v-checkbox
              :model-value="items.length > 0 && selectedIds.size === items.length"
              :indeterminate="selectedIds.size > 0 && selectedIds.size < items.length"
              density="compact"
              hide-details
              @update:model-value="$emit('toggle-all', $event)"
            />
          </th>
          <th>Наименование</th>
          <th>ИНН</th>
          <th>КПП</th>
          <th>Адрес</th>
          <th>Телефон / Email</th>
          <th>Контактное лицо</th>
          <th style="min-width:160px">Категории товаров</th>
          <th class="text-right">Действия</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="!loading && items.length === 0">
          <td colspan="9" class="text-center py-10 text-medium-emphasis">
            <v-icon icon="mdi-account-off-outline" size="40" color="grey-lighten-2" class="d-block mx-auto mb-2" />
            Контрагенты не найдены
          </td>
        </tr>
        <tr v-for="c in items" :key="c.id" class="contractor-row" :class="{ 'contractor-row--selected': selectedIds.has(c.id) }" style="cursor:pointer" @click="$emit('open-edit', c)">
          <td @click.stop>
            <v-checkbox
              :model-value="selectedIds.has(c.id)"
              density="compact"
              hide-details
              @update:model-value="$emit('toggle-one', c.id)"
            />
          </td>
          <td class="font-weight-medium">{{ c.name }}</td>
          <td class="text-mono">{{ c.inn || '—' }}</td>
          <td class="text-mono">{{ c.kpp || '—' }}</td>
          <td class="text-sm">{{ c.address || '—' }}</td>
          <td>
            <div class="text-sm">{{ formatPhoneRu(c.phone) || '—' }}</div>
            <div class="text-caption text-medium-emphasis">{{ c.email || '' }}</div>
          </td>
          <td class="text-sm">{{ c.contact_person || '—' }}</td>
          <td>
            <template v-if="c.product_categories.length > 0">
              <v-chip
                v-if="c.product_categories.includes('Все')"
                size="x-small"
                color="blue"
                variant="tonal"
                class="mr-1 mb-1"
              >Все категории</v-chip>
              <template v-else>
                <v-chip
                  v-for="cat in c.product_categories.slice(0, 2)"
                  :key="cat"
                  size="x-small"
                  color="teal"
                  variant="tonal"
                  class="mr-1 mb-1"
                >{{ cat }}</v-chip>
                <v-chip
                  v-if="c.product_categories.length > 2"
                  size="x-small"
                  color="grey"
                  variant="tonal"
                  class="cursor-pointer"
                  @click="$emit('open-categories', c)"
                >+{{ c.product_categories.length - 2 }}</v-chip>
              </template>
            </template>
            <span v-else class="text-medium-emphasis text-caption">—</span>
          </td>
          <td class="text-right" @click.stop>
            <v-btn icon="mdi-delete" variant="text" size="small" color="error" @click.stop="$emit('delete', c)" />
          </td>
        </tr>
      </tbody>
    </v-table>
    <!-- Pagination -->
    <div v-if="totalPages > 1" class="d-flex justify-center align-center pa-3 gap-2">
      <v-btn icon="mdi-chevron-left" variant="text" size="small" :disabled="page <= 1" @click="$emit('go-page', page - 1)" />
      <span class="text-body-2">Стр. {{ page }} из {{ totalPages }}</span>
      <v-btn icon="mdi-chevron-right" variant="text" size="small" :disabled="page >= totalPages" @click="$emit('go-page', page + 1)" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatPhoneRu } from '@/utils/phoneFormat'
import type { ContractorWithStats } from '@/composables/contractors/contractorsTypes'

defineProps<{
  items: ContractorWithStats[]
  loading: boolean
  selectedIds: Set<number>
  page: number
  totalPages: number
}>()
defineEmits<{
  (e: 'toggle-all', value: boolean | null): void
  (e: 'toggle-one', id: number): void
  (e: 'open-edit', c: ContractorWithStats): void
  (e: 'open-categories', c: ContractorWithStats): void
  (e: 'delete', c: ContractorWithStats): void
  (e: 'go-page', page: number): void
}>()
</script>
