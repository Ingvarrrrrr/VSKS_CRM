<template>
  <!-- Split purchase kanban dialog — владелец (2026-09-16, скриншот прода,
       закупка 919): «26 столбцов, а видно 5» — окно на весь экран вместо
       max-width 1200, закрытие крестиком в шапке (см. close() — предупреждает
       про несохранённые пустые «+ Столбец» колонки, но не блокирует закрытие;
       раскладка по реальным позициям уже персистентна — split_column_key). -->
  <v-dialog
    :model-value="open"
    fullscreen
    scrollable
    transition="dialog-bottom-transition"
    @update:model-value="onDialogUpdate"
  >
    <v-card class="split-kanban-dialog-card">
      <v-toolbar density="comfortable" color="surface" class="split-kanban-dialog-toolbar">
        <v-icon class="ml-4 mr-2" color="primary">mdi-call-split</v-icon>
        <v-toolbar-title>
          Разбить закупку на несколько
          <span class="text-caption text-medium-emphasis ml-2">
            · перетащите позиции по колонкам, затем «Разбить»
          </span>
        </v-toolbar-title>
        <v-spacer />
        <v-btn icon="mdi-close" title="Закрыть" @click="close" />
      </v-toolbar>
      <v-card-text class="pa-3 split-kanban-dialog-cardtext">
        <PurchaseSplitKanban
          v-if="open && items.length && purchaseId"
          ref="boardRef"
          :purchase-id="purchaseId"
          :items="items"
          @split="$emit('split', $event)"
          @cancel="close"
          @error="(m: string) => $emit('error', m)"
        />
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import PurchaseSplitKanban from '@/components/PurchaseSplitKanban.vue'
import { useToast } from '@/composables/useToast'

const open = defineModel<boolean>({ default: false })

defineProps<{
  purchaseId: number | null
  items: any[]
}>()

defineEmits<{
  (e: 'split', result: { purchase_ids: number[]; count: number; source_purchase_id: number }): void
  (e: 'error', message: string): void
}>()

const toast = useToast()
const boardRef = ref<InstanceType<typeof PurchaseSplitKanban> | null>(null)

// Владелец (2026-09-16): «случайно вышел из окна, всё слетает» — реальные
// позиции уже сохранены сразу (PATCH split-column), теряются только пустые
// «+ Столбец» колонки без единой позиции. Предупреждаем, не блокируем.
function warnIfEmptyColumns() {
  const names = boardRef.value?.vanishingManualColumns() ?? []
  if (names.length) {
    const list = names.map(n => `«${n}»`).join(', ')
    toast.addToast(`Пустой столбец ${list} не сохранится — в нём нет позиций`, 'warning')
  }
}
function onDialogUpdate(val: boolean) {
  if (!val) warnIfEmptyColumns()
  open.value = val
}
function close() {
  warnIfEmptyColumns()
  open.value = false
}
</script>

<style>
/* Не scoped — Vuetify телепортирует контент диалога в <body> (тот же приём,
   что WishKanbanDialog.vue). */
.split-kanban-dialog-card {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.split-kanban-dialog-toolbar {
  flex: 0 0 auto;
}
.split-kanban-dialog-cardtext {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
}
</style>
