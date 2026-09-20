<template>
  <!-- Подтверждение одиночного «Сделать плановой позицией» (задача 3) — v-dialog
       в стиле проекта вместо window.confirm() (координатор, приёмка в браузере
       2026-09-20), тот же паттерн, что и FeoCategoryDeleteDialog.vue. Состояние —
       useFeoCategoryCollapse.ts (module-level singleton, Правило №6 — второй
       канал подтверждения не заводим). -->
  <v-dialog v-model="feoCollapse.singleDialogOpen.value" max-width="480">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-arrow-collapse-up" color="blue-grey-darken-1" class="mr-2" />
        Сделать плановой позицией?
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="feoCollapse.closeSingleCollapseDialog()" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <div class="mb-2">Категория «{{ target?.categoryName }}»</div>
        <v-alert type="warning" density="compact" variant="tonal" class="mb-3">
          Позиция «{{ target?.plannedItemName }}» переедет в родительскую категорию, сама категория исчезнет,
          деньги ФЭО этой категории перейдут на позицию.
        </v-alert>
        <v-alert type="info" variant="tonal" density="compact" class="text-caption">
          <v-icon icon="mdi-undo-variant" size="14" class="mr-1" style="opacity:.6" />
          Действие нельзя отменить кнопкой «Отменить»/Ctrl+Z.
        </v-alert>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="feoCollapse.closeSingleCollapseDialog()">Отмена</v-btn>
        <v-btn color="blue-grey-darken-1" variant="flat" :loading="submitting" @click="onConfirm">Свернуть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useFeoCategoryCollapse } from '@/composables/subsidies/useFeoCategoryCollapse'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'

const ctx = useSubsidyDetailCtx()
const feoCollapse = useFeoCategoryCollapse()

const target = computed(() => feoCollapse.singleDialogTarget.value)
const submitting = computed(() => target.value != null && feoCollapse.singleCollapsing.value === target.value.categoryId)

async function onConfirm() {
  const t = target.value
  if (!t) return
  const ok = await feoCollapse.collapseCategoryToItem(t.categoryId, t.categoryName, t.plannedItemName)
  if (ok && ctx.selectedId.value) await ctx.loadFeo(ctx.selectedId.value)
}
</script>

<style scoped>
/* .dialog-card/.dialog-title — тот же паттерн, что и в FeoCategoryDeleteDialog.vue
   (scoped CSS не достаёт другой компонент, держать копию, см. её докстринг). */
.dialog-card {}
.dialog-title {
  display: flex; align-items: center;
  font-size: 16px !important; font-weight: 600 !important;
  padding: 16px 20px !important;
}
</style>
