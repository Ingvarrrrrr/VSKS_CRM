<template>
  <!-- ── KANBAN DISTRIBUTION DIALOG (Phase 13) ── -->
  <!-- Владелец (2026-09-04, заявка №55): readonly раньше стоял на статусе
       'approved', хотя сервер (POST /approve-distribution, PATCH /items/{id})
       на этом статусе распределение ещё разрешает — кнопка "Распределить и
       одобрить" была, а перетащить карточку нельзя. Заблокировано распределение
       по-настоящему только когда заявка УЖЕ распределена ('converted' — закупки
       созданы), гейт приведён в соответствие с бэкендом. -->
  <!-- Владелец (2026-09-16, скриншот прода 27"): «26 столбцов, а видно 5» —
       окно на весь экран (было width 95vw/max 1800 — 5 колонок влезало),
       колонки берут всю доступную ширину, закрытие — крестиком в шапке
       (см. close() ниже: предупреждает про несохранённые пустые «+ Столбец»
       колонки, но никогда не блокирует закрытие). -->
  <v-dialog
    :model-value="model"
    fullscreen
    scrollable
    transition="dialog-bottom-transition"
    @update:model-value="onDialogUpdate"
  >
    <v-card class="wish-kanban-dialog-card">
      <v-toolbar density="comfortable" color="surface" class="wish-kanban-dialog-toolbar">
        <v-icon class="ml-4 mr-2" color="primary">mdi-view-column-outline</v-icon>
        <v-toolbar-title v-if="wish && wish.status === 'converted'">
          Закупки заявки №{{ wish.id }} — перенос позиций до договора
        </v-toolbar-title>
        <v-toolbar-title v-else>
          Распределение позиций по закупкам
          <span v-if="wish" class="text-subtitle-2 text-medium-emphasis ml-2">
            · {{ wish.title || `Заявка #${wish.id}` }}
          </span>
        </v-toolbar-title>
        <v-spacer />
        <v-btn icon="mdi-close" title="Закрыть" @click="close" />
      </v-toolbar>
      <v-card-text class="pa-3 wish-kanban-dialog-cardtext">
        <!-- Владелец (лист 2 №2, 2026-09-20): заявка УЖЕ согласована ('converted' —
             закупки созданы) — здесь больше нечего «распределять и одобрить», это
             отдельный борд переноса позиций между уже существующими закупками
             (WishPurchasesKanban.vue). Несогласованной заявке (submitted/approved) —
             старое поведение без изменений: WishDistributionKanban ниже. -->
        <WishPurchasesKanban
          v-if="wish && wish.status === 'converted'"
          ref="boardRef"
          :wish-id="wish.id"
          @error="(m: string) => ctx.showSnack(m, 'error')"
        />
        <WishDistributionKanban
          v-else-if="wish"
          ref="boardRef"
          :wish-id="wish.id"
          :items="items"
          :readonly="false"
          @approved="(result: any) => $emit('approved', result)"
          @cancel="close"
          @error="(m: string) => ctx.showSnack(m, 'error')"
        />
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// WishKanbanDialog.vue — тонкая обёртка над WishDistributionKanban/
// WishPurchasesKanban (второй — лист 2 №2, 2026-09-20, канбан по УЖЕ созданным
// закупкам согласованной заявки). Дословный перенос шаблона (2213-2257) из
// WishesView.vue; логика (kanbanDialog/kanbanWish/kanbanItems/openKanbanDialog/
// onKanbanApproved) осталась в useWishActions.ts.
import { ref } from 'vue'
import WishDistributionKanban from '@/components/WishDistributionKanban.vue'
import WishPurchasesKanban from './WishPurchasesKanban.vue'
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
const boardRef = ref<InstanceType<typeof WishDistributionKanban> | InstanceType<typeof WishPurchasesKanban> | null>(null)

// Владелец (2026-09-16): «случайно вышел из окна, всё слетает». Каждый бросок
// карточки уже сохранён PATCH-ом (см. WishDistributionKanban.vue) — единственное,
// что реально теряется при закрытии, это ПУСТЫЕ колонки, добавленные через
// «+ Столбец» (нигде не хранятся, кроме памяти открытого борда). Закрытие НЕ
// блокируется — только предупреждает, что конкретно не переживёт переоткрытие.
function warnIfEmptyColumns() {
  const names = boardRef.value?.vanishingManualColumns() ?? []
  if (names.length) {
    const list = names.map(n => `«${n}»`).join(', ')
    ctx.showSnack(`Пустой столбец ${list} не сохранится — в нём нет позиций`, 'warning')
  }
}
function onDialogUpdate(val: boolean) {
  if (!val) warnIfEmptyColumns()
  model.value = val
}
function close() {
  warnIfEmptyColumns()
  model.value = false
}
</script>

<style>
/* Не scoped — тот же приём, что и раньше (владелец, 2026-09-04): Vuetify
   телепортирует контент диалога в <body>, scoped-атрибут туда не долетает. */
.wish-kanban-dialog-card {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.wish-kanban-dialog-toolbar {
  flex: 0 0 auto;
}
.wish-kanban-dialog-cardtext {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
}
</style>
