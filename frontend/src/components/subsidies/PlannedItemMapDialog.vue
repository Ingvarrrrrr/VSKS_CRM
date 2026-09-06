<template>
  <!-- ── Диалог сопоставления позиций ── -->
  <v-dialog v-model="p.showMapDialog.value" max-width="520" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
        <v-icon icon="mdi-link-variant" color="teal" class="mr-2" />
        Сопоставить с плановой позицией
      </v-card-title>
      <v-card-text>
        <div v-if="p.mapTarget.value" class="mb-3">
          <div class="text-caption text-medium-emphasis mb-1">Фактическая позиция:</div>
          <div class="font-weight-medium">{{ p.mapTarget.value.item_name }}</div>
          <div class="text-caption text-medium-emphasis">Контрагент: {{ p.mapTarget.value.contractor_name || '—' }}</div>
        </div>
        <div class="text-caption text-medium-emphasis mb-2">Выберите плановую позицию:</div>
        <v-list density="compact" v-if="p.mapCategoryId.value && ctx.comparisonData.value[p.mapCategoryId.value]">
          <v-list-item
            v-for="planned in ctx.comparisonData.value[p.mapCategoryId.value!]!.planned"
            :key="planned.id"
            :title="planned.name"
            :subtitle="planned.quantity ? `${planned.quantity} ${planned.unit || ''}` : undefined"
            rounded="lg"
            class="mb-1"
            style="border:1px solid #e2e8f0"
            @click="() => { p.mapTarget.value && (p.mapTarget.value.feo_planned_item_id = planned.id); p.applyMapping(planned.id) }"
          >
            <template #append>
              <v-icon icon="mdi-check" color="teal" v-if="p.mapTarget.value && p.mapTarget.value.feo_planned_item_id === planned.id" />
            </template>
          </v-list-item>
          <div v-if="!ctx.comparisonData.value[p.mapCategoryId.value]!.planned.length" class="text-caption text-medium-emphasis pa-2">
            Нет плановых позиций. Сначала добавьте их.
          </div>
        </v-list>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="p.showMapDialog.value = false">Отмена</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Диалог «Сопоставить с плановой позицией» — вынесен из SubsidiesView.vue.
// Состояние/логика (openMapDialog, вызывается деревом ФЭО) — в
// usePlannedItems.ts (singleton, общий с остальными тремя диалогами панели
// «план vs факт»); comparisonData читается напрямую из общего контекста
// (ctx) — тот же список, что и у дерева ФЭО, второй копии не заводим.
import { useDisplay } from 'vuetify'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePlannedItems } from '@/composables/subsidies/usePlannedItems'

const { mobile } = useDisplay()
const ctx = useSubsidyDetailCtx()
const p = usePlannedItems(ctx)
</script>
