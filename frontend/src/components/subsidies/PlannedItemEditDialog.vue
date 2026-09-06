<template>
  <!-- ── Диалог редактирования плановой позиции ── -->
  <v-dialog v-model="p.editPlannedDialog.value.show" max-width="480" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
        <v-icon icon="mdi-pencil" color="blue" class="mr-2" />Редактировать плановую позицию
      </v-card-title>
      <v-card-text class="px-4 pb-2">
        <v-text-field v-model="p.editPlannedDialog.value.name" label="Наименование" variant="outlined" density="compact" class="mb-2" autofocus />
        <v-row dense>
          <v-col cols="5">
            <v-text-field v-model="p.editPlannedDialog.value.quantity" label="Кол-во" type="number" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="7">
            <v-text-field v-model="p.editPlannedDialog.value.unit" label="Ед. изм." variant="outlined" density="compact" />
          </v-col>
        </v-row>
        <!-- Цена за единицу (владелец, 2026-09-02) — необязательное поле, то же
             поведение, что в диалоге создания (FeoPlannedItemsSelect.vue): задана —
             «Сумма (план)» ниже считается сама (кол-во × цена) и недоступна для
             ручного ввода; не задана — обычное поле, сумма вводится руками. -->
        <v-text-field
          v-if="p.editPlannedDialog.value.payment_mode !== 'monthly'"
          v-model.number="p.editPlannedDialog.value.unitPrice"
          type="number"
          label="Цена за единицу, ₽ (необязательно)"
          variant="outlined"
          density="compact"
          class="mb-1"
          :hint="p.editPlannedDialog.value.unitPrice === '' || p.editPlannedDialog.value.unitPrice == null ? UNIT_PRICE_NOT_FIXED_HINT : ''"
          :persistent-hint="p.editPlannedDialog.value.unitPrice === '' || p.editPlannedDialog.value.unitPrice == null"
        />
        <v-text-field
          v-model="p.editPlannedDialog.value.amount"
          label="Сумма (план), ₽" type="number"
          variant="outlined" density="compact"
          :readonly="p.editAmountIsComputed.value"
          :bg-color="p.editAmountIsComputed.value ? 'grey-lighten-4' : undefined"
          :class="p.editPlannedDialog.value.payment_mode === 'monthly' ? 'd-none' : 'mb-1'"
        />
        <div
          v-if="p.editPlannedDialog.value.payment_mode !== 'monthly'"
          class="text-caption text-medium-emphasis mb-2"
          style="line-height:1.35"
        >
          <v-icon icon="mdi-information-outline" size="13" style="margin-top:-2px" class="mr-1" />{{ p.editPriceCaption.value }}
        </div>
        <!-- Происхождение (владелец, 2026-09-01) — ДВЕ НЕЗАВИСИМЫЕ галочки, тот же
             смысл, что и в диалоге создания. Правка доступна только тому, кто может
             редактировать ФЭО — этот диалог уже за той же вкладкой (feo_categories). -->
        <div class="text-caption text-medium-emphasis mb-1">Происхождение позиции</div>
        <v-checkbox v-model="p.editPlannedDialog.value.is_feo_breakdown" density="compact" hide-details class="mb-1">
          <template #label>
            <div>
              <div style="line-height:1.2">По ФЭО</div>
              <div class="text-caption text-medium-emphasis" style="line-height:1.2">жёсткая разбивка ФЭО — покупать будут именно это, отчётность строгая</div>
            </div>
          </template>
        </v-checkbox>
        <v-checkbox v-model="p.editPlannedDialog.value.is_internal_plan" density="compact" hide-details class="mb-3">
          <template #label>
            <div>
              <div style="line-height:1.2">Внутренний план</div>
              <div class="text-caption text-medium-emphasis" style="line-height:1.2">в ФЭО была более широкая категория (или позиции не было) — разбивку придумали сами</div>
            </div>
          </template>
        </v-checkbox>
        <!-- Тип платежа -->
        <div class="text-caption text-medium-emphasis mb-1">Тип платежа</div>
        <v-btn-toggle
          v-model="p.editPlannedDialog.value.payment_mode"
          mandatory density="compact" variant="outlined" divided
          class="mb-3"
        >
          <v-btn value="one_time" size="small">Разовый</v-btn>
          <v-btn value="monthly" size="small">Ежемесячный</v-btn>
        </v-btn-toggle>
        <!-- Разовый: дата потребности -->
        <v-text-field
          v-if="p.editPlannedDialog.value.payment_mode === 'one_time'"
          v-model="p.editPlannedDialog.value.planned_date"
          label="Дата потребности"
          type="date"
          variant="outlined" density="compact"
          class="mb-2"
        />
        <!-- Ежемесячный: поля -->
        <template v-if="p.editPlannedDialog.value.payment_mode === 'monthly'">
          <v-text-field
            v-model="p.editPlannedDialog.value.monthly_start_date"
            label="Первый платёж"
            type="date"
            variant="outlined" density="compact"
            class="mb-2"
          />
          <v-row dense>
            <v-col cols="6">
              <v-text-field
                v-model.number="p.editPlannedDialog.value.months_count"
                label="Кол-во месяцев"
                type="number"
                variant="outlined" density="compact"
              />
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model.number="p.editPlannedDialog.value.monthly_amount"
                label="Платёж за месяц, ₽"
                type="number"
                variant="outlined" density="compact"
              />
            </v-col>
          </v-row>
          <div
            v-if="p.editPlannedDialog.value.monthly_amount && p.editPlannedDialog.value.months_count"
            class="text-caption text-medium-emphasis mb-2"
          >
            Итого по позиции: {{ ((p.editPlannedDialog.value.monthly_amount ?? 0) * (p.editPlannedDialog.value.months_count ?? 0)).toLocaleString('ru-RU') }} ₽
          </div>
        </template>
      </v-card-text>
      <v-card-actions class="px-4 pb-3">
        <v-spacer />
        <v-btn variant="text" @click="p.editPlannedDialog.value.show = false">Отмена</v-btn>
        <v-btn color="primary" variant="tonal" :loading="p.editPlannedDialog.value.saving" @click="p.saveEditPlannedItem">Сохранить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Диалог «Редактировать плановую позицию» — вынесен из SubsidiesView.vue.
// Состояние/логика (openEditPlannedItem, вызывается деревом ФЭО через ctx-
// подобный проброс из SubsidiesView.vue) — в usePlannedItems.ts (singleton,
// общий с остальными тремя диалогами панели «план vs факт»).
import { useDisplay } from 'vuetify'
import { UNIT_PRICE_NOT_FIXED_HINT } from '@/constants/planPriceLabels'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePlannedItems } from '@/composables/subsidies/usePlannedItems'

const { mobile } = useDisplay()
const p = usePlannedItems(useSubsidyDetailCtx())
</script>
