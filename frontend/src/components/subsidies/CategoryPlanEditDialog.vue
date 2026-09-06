<template>
  <!-- ── Диалог редактирования ручного плана категории (синтетическая строка «ручной
       план ФЭО» в панели, planned.isManual) — правит planned_quantity/planned_amount/
       unit НА КАТЕГОРИИ, а не заводит FeoPlannedItem (для этого рядом отдельная кнопка). ── -->
  <v-dialog v-model="p.editCategoryPlanDialog.value.show" max-width="440" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
        <v-icon icon="mdi-pencil-ruler" color="blue" class="mr-2" />
        Редактировать план категории
      </v-card-title>
      <v-card-text class="px-4 pb-2">
        <div class="text-caption text-medium-emphasis mb-3">{{ p.editCategoryPlanDialog.value.categoryName }}</div>
        <v-row dense>
          <v-col cols="6">
            <v-text-field
              v-model="p.editCategoryPlanDialog.value.quantity"
              label="Плановое количество" type="number"
              variant="outlined" density="compact" autofocus
            />
          </v-col>
          <v-col cols="6">
            <v-text-field
              v-model="p.editCategoryPlanDialog.value.unitPrice"
              label="Плановая цена за единицу, ₽" type="number"
              variant="outlined" density="compact"
            />
          </v-col>
        </v-row>
        <v-combobox
          v-model="p.editCategoryPlanDialog.value.unit"
          :items="p.CATEGORY_UNIT_OPTIONS"
          label="Единица измерения"
          variant="outlined" density="compact" class="mb-1"
          :color="p.isCategoryUnitSuspicious.value ? 'warning' : undefined"
        />
        <div v-if="p.isCategoryUnitSuspicious.value" class="text-caption mb-2" style="color:#B45309;display:flex;align-items:flex-start;gap:4px">
          <v-icon icon="mdi-alert" size="14" style="margin-top:2px" />
          <span>Похоже на число, а не единицу измерения — след старого импорта со сдвигом колонок. Выберите единицу из списка или введите свою.</span>
        </div>
        <div class="text-caption text-medium-emphasis mt-2" style="border-top:1px solid #e2e8f0;padding-top:8px">
          Плановая сумма (кол-во × цена):
          <span class="font-weight-medium" :style="p.editCategoryPlanSum.value != null ? 'color:#0f766e' : ''">
            {{ p.editCategoryPlanSum.value != null ? formatCurrency(p.editCategoryPlanSum.value) : '—' }}
          </span>
        </div>
      </v-card-text>
      <v-card-actions class="px-4 pb-3">
        <v-spacer />
        <v-btn variant="text" @click="p.editCategoryPlanDialog.value.show = false">Отмена</v-btn>
        <v-btn color="primary" variant="tonal" :loading="p.editCategoryPlanDialog.value.saving" @click="p.saveEditCategoryPlan">Сохранить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Диалог «Редактировать план категории» (ручной план ФЭО на самой категории) —
// вынесен из SubsidiesView.vue. Состояние/логика (openEditCategoryPlan,
// вызывается деревом ФЭО) — в usePlannedItems.ts (singleton, общий с остальными
// тремя диалогами панели «план vs факт»).
import { useDisplay } from 'vuetify'
import { formatCurrency } from '@/composables/subsidies/format'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePlannedItems } from '@/composables/subsidies/usePlannedItems'

const { mobile } = useDisplay()
const p = usePlannedItems(useSubsidyDetailCtx())
</script>
