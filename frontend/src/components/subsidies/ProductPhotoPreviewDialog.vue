<template>
  <!-- ── Превью фото товара ── -->
  <v-dialog
    :model-value="!!ctx.photoPreview.value"
    max-width="640"
    @update:model-value="v => !v && (ctx.photoPreview.value = null)"
  >
    <v-card v-if="ctx.photoPreview.value">
      <v-card-title class="d-flex align-center pa-3 text-subtitle-2">
        {{ ctx.photoPreview.value.title }}
        <v-spacer />
        <v-btn icon="mdi-close" size="small" variant="text" @click="ctx.photoPreview.value = null" />
      </v-card-title>
      <v-card-text class="pa-2">
        <v-img :src="ctx.photoPreview.value.src" contain style="max-height:70vh" />
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Превью фото товара — открывается прямо из строк дерева ФЭО (панель «план vs
// факт», несколько мест), которое остаётся в SubsidiesView.vue. photoPreview
// живёт в общем контексте (useSubsidyDetail.ts), а не локально в этом компоненте,
// т.к. пишут в него строки дерева, а не сам диалог (Правило №6 — один источник).
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'

const ctx = useSubsidyDetailCtx()
</script>
