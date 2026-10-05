<!-- WishApproveSheet.vue — мобильный выбор способа одобрения заявки (макет
     «Вариант А», утверждён владельцем). КОНТРАКТ ФИКСИРОВАН — этот же компонент
     импортирует второй параллельный исполнитель из вкладок списка заявок,
     интерфейс (props/emits) менять нельзя без согласования.
     Сам компонент ничего не вызывает — только эмитит события, вызовы
     actions.openKanbanDialog/approveWish и т.п. делает родитель (WishFormDialog.vue
     и Wish*Tab.vue) — единственный источник этих действий (Правило №6). -->
<template>
  <v-bottom-sheet
    :model-value="modelValue"
    @update:model-value="(v: boolean) => $emit('update:modelValue', v)"
  >
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-medium pa-4 pb-2">
        Как одобрить заявку №{{ wishNumber }}
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <v-sheet
          rounded="lg"
          border
          class="pa-3 mb-3 wish-approve-sheet__option wish-approve-sheet__option--accent"
          @click="$emit('distribute')"
        >
          <div class="d-flex align-center ga-2 mb-1">
            <v-icon color="primary">mdi-view-column-outline</v-icon>
            <span class="font-weight-medium">Распределить и одобрить</span>
          </div>
          <div class="text-caption text-medium-emphasis">
            {{ itemsCount == null ? 'Разложить позиции по закупкам' : `Разложить ${itemsCount} ${pluralRu(itemsCount, 'позицию', 'позиции', 'позиций')} по закупкам` }}: что одной закупкой, что отдельно.
            Потом заявка одобряется.
          </div>
        </v-sheet>

        <v-sheet
          rounded="lg"
          border
          class="pa-3 mb-3 wish-approve-sheet__option"
          @click="$emit('quick-approve')"
        >
          <div class="d-flex align-center ga-2 mb-1">
            <v-icon color="success">mdi-check-circle-outline</v-icon>
            <span class="font-weight-medium text-success">Одобрить без согласования остальных</span>
          </div>
          <div class="text-caption text-medium-emphasis">
            Одобрить сразу, не дожидаясь остальных согласующих в цепочке.
          </div>
        </v-sheet>

        <div v-if="canWaiveTz" class="mb-2">
          <div class="text-caption text-medium-emphasis mb-1">Техническое задание</div>
          <v-btn-toggle
            :model-value="tzNotRequired"
            mandatory
            density="compact"
            color="deep-purple"
            @update:model-value="(v: boolean) => $emit('update:tzNotRequired', v)"
          >
            <v-btn :value="false" size="small">С ТЗ</v-btn>
            <v-btn :value="true" size="small">Без ТЗ</v-btn>
          </v-btn-toggle>
        </div>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" :disabled="loading" @click="$emit('update:modelValue', false)">Отмена</v-btn>
      </v-card-actions>
    </v-card>
  </v-bottom-sheet>
</template>

<script setup lang="ts">
import { pluralRu } from '@/composables/products/productsTypes'

defineProps<{
  modelValue: boolean
  wishNumber: number | string
  itemsCount: number | null
  canWaiveTz: boolean
  tzNotRequired: boolean
  loading?: boolean
}>()

defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'update:tzNotRequired', v: boolean): void
  (e: 'distribute'): void
  (e: 'quick-approve'): void
}>()
</script>

<style scoped>
.wish-approve-sheet__option {
  cursor: pointer;
}
.wish-approve-sheet__option--accent {
  border-color: #fb923c;
  background: rgba(251, 146, 60, 0.06);
}
</style>
