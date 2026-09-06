<template>
  <!-- ── KANBAN DISTRIBUTION DIALOG (Phase 13) ── -->
  <!-- Владелец (2026-09-04, заявка №55): readonly раньше стоял на статусе
       'approved', хотя сервер (POST /approve-distribution, PATCH /items/{id})
       на этом статусе распределение ещё разрешает — кнопка "Распределить и
       одобрить" была, а перетащить карточку нельзя. Заблокировано распределение
       по-настоящему только когда заявка УЖЕ распределена ('converted' — закупки
       созданы), гейт приведён в соответствие с бэкендом. -->
  <!-- Владелец (2026-09-04): «окно у меня большое, а окно перераспределения
       маленькое» — ширина в vw с потолком + content-class на .v-overlay__content
       для CSS resize мышью (см. WishesView.vue <style> — правила намеренно НЕ
       scoped, Vuetify телепортирует контент диалога в <body>). -->
  <v-dialog
    v-model="model"
    width="95vw"
    max-width="1800"
    scrollable
    content-class="wish-kanban-dialog-content"
    :fullscreen="mobile"
  >
    <v-card class="wish-kanban-dialog-card">
      <v-card-title class="pa-4 pb-2">
        <v-icon class="mr-2" color="primary">mdi-view-column-outline</v-icon>
        Распределение позиций по закупкам
        <span v-if="wish" class="text-subtitle-2 text-medium-emphasis ml-3">
          · {{ wish.title || `Заявка #${wish.id}` }}
        </span>
      </v-card-title>
      <v-card-text class="pa-4 wish-kanban-dialog-cardtext">
        <WishDistributionKanban
          v-if="wish"
          :wish-id="wish.id"
          :items="items"
          :readonly="wish.status === 'converted'"
          @approved="(result: any) => $emit('approved', result)"
          @cancel="model = false"
          @error="(m: string) => ctx.showSnack(m, 'error')"
        />
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// WishKanbanDialog.vue — тонкая обёртка над WishDistributionKanban. Дословный
// перенос шаблона (2213-2257) из WishesView.vue; логика (kanbanDialog/kanbanWish/
// kanbanItems/openKanbanDialog/onKanbanApproved) осталась в useWishActions.ts.
import WishDistributionKanban from '@/components/WishDistributionKanban.vue'
import { useWishesContext } from '@/composables/wishes/useWishesContext'
import type { Wish } from '@/composables/wishes/wishTypes'

defineProps<{
  wish: Wish | null
  items: any[]
  mobile: boolean
}>()
defineEmits<{ (e: 'approved', result: { purchase_ids: number[]; count: number }): void }>()
const model = defineModel<boolean>({ required: true })

const ctx = useWishesContext()
</script>
