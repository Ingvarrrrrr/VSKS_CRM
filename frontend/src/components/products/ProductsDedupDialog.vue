<template>
  <v-dialog v-model="dialog.show" max-width="900" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center pt-4 px-6">
        <v-icon icon="mdi-content-duplicate" color="warning" class="mr-2" />
        Найденные дубликаты
        <v-spacer />
        <v-chip color="warning" variant="tonal" size="small">
          Групп: {{ dialog.groups.length }} · Будет удалено: {{ totalToDelete }}
        </v-chip>
      </v-card-title>
      <v-card-text class="px-6">
        <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
          Из каждой группы остаётся <strong>один эталон</strong> (с фото / описанием / ссылками — приоритет автоматический). Остальные товары удаляются, но все их позиции в закупках перепривязываются к эталону. <strong>Точные совпадения (100%)</strong> отмечены галочкой по умолчанию. <strong>Неполные совпадения (80–99%)</strong> нужно подтвердить галочкой вручную.
        </v-alert>
        <v-expansion-panels variant="accordion">
          <v-expansion-panel v-for="(grp, idx) in dialog.groups" :key="idx">
            <v-expansion-panel-title>
              <div class="d-flex align-center w-100 ga-2">
                <v-icon icon="mdi-trophy" color="success" size="20" />
                <span class="text-body-2 font-weight-medium">{{ grp.winner.name }}</span>
                <v-chip v-if="grp.winner.product_type" size="x-small" color="grey" variant="tonal">{{ grp.winner.product_type }}</v-chip>
                <v-spacer />
                <v-chip size="x-small" color="warning" variant="tonal">{{ grp.duplicates.length }} дубл.</v-chip>
              </div>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <div class="text-caption text-medium-emphasis mb-2">Останется (эталон):</div>
              <v-list-item class="bg-grey-lighten-4 mb-2 rounded">
                <template #prepend><v-icon icon="mdi-check-circle" color="success" /></template>
                <v-list-item-title>{{ grp.winner.name }}</v-list-item-title>
                <v-list-item-subtitle>
                  {{ grp.winner.category || '—' }}
                  <span v-if="grp.winner.has_photo">· фото</span>
                  <span v-if="grp.winner.has_description">· описание</span>
                </v-list-item-subtitle>
              </v-list-item>
              <div class="text-caption text-medium-emphasis mb-2 mt-2">Удалится (дубликаты):</div>
              <v-list density="compact">
                <v-list-item v-for="dup in grp.duplicates" :key="dup.id">
                  <template #prepend>
                    <v-checkbox
                      :model-value="!dialog.skipIds.has(dup.id)"
                      density="compact" hide-details
                      @update:model-value="$emit('toggle-skip', dup.id)"
                    />
                  </template>
                  <v-list-item-title :class="{ 'text-decoration-line-through text-medium-emphasis': !dialog.skipIds.has(dup.id) }">
                    {{ dup.name }}
                    <v-chip v-if="dup.match === 'exact'" size="x-small" color="success" variant="tonal" class="ml-2">100%</v-chip>
                    <v-chip v-else size="x-small" color="warning" variant="tonal" class="ml-2">{{ dup.score }}% · подтвердите</v-chip>
                  </v-list-item-title>
                  <v-list-item-subtitle>
                    {{ dup.category || '—' }}
                    <span v-if="dup.has_photo">· фото</span>
                    <span v-if="dup.has_description">· описание</span>
                  </v-list-item-subtitle>
                </v-list-item>
              </v-list>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="dialog.show = false">Отмена</v-btn>
        <v-btn color="warning" variant="flat" :loading="deduplicating" :disabled="totalToDelete === 0" @click="$emit('confirm')">
          Удалить {{ totalToDelete }} дубл.
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { DupGroup } from '@/composables/products/productsTypes'

defineProps<{
  dialog: { show: boolean; groups: DupGroup[]; skipIds: Set<number> }
  totalToDelete: number
  deduplicating: boolean
  mobile: boolean
}>()
defineEmits<{
  (e: 'toggle-skip', id: number): void
  (e: 'confirm'): void
}>()
</script>
