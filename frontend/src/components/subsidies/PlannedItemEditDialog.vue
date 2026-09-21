<template>
  <!-- ── Диалог редактирования плановой позиции ── -->
  <v-dialog v-model="p.editPlannedDialog.value.show" max-width="480" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
        <v-icon icon="mdi-pencil" color="blue" class="mr-2" />Редактировать плановую позицию
      </v-card-title>
      <v-card-text class="px-4 pb-2">
        <v-text-field v-model="p.editPlannedDialog.value.name" label="Наименование" variant="outlined" density="compact" class="mb-2" autofocus />
        <!-- Владелец (Волна 3, п.2, «двоится Количество»): «как так получается, что
             "Кол-во" 6.66... поле "Кол-во" в данном случае сбивает с толку» — для
             monthly-режима количество единиц товара/услуги не участвует в сумме
             (сумма = срок × платёж за месяц) и скрыто, чтобы не путать со сроком
             (см. тот же приём в PlannedItemAddDialog.vue). -->
        <v-row v-if="p.editPlannedDialog.value.payment_mode !== 'monthly'" dense>
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
        <!-- Тип позиции — товар/услуга/работа (владелец, 21.09, раздел W2).
             ITEM_TYPE_OPTIONS — единственный источник списка (Правило №6).
             Без чекбокса «Обновить тип в каталоге» — плановая позиция НЕ хранит
             product_id (см. докстринг FeoPlannedItemCreate.product_id,
             backend/app/schemas/feo.py: «транзитное поле запроса»), GET сюда его
             не возвращает, так что диалог правки не знает, какой товар каталога
             привязан. sync_product_kind=true шлётся всегда (saveEditPlannedItem,
             useFeoPlannedItemEditDialog.ts) — backend (update_planned_item →
             app.services.item_types.resolve_product_for_planned_item) сам
             подбирает товар по точному совпадению имени; снэкбар после
             сохранения показывает, что реально записалось. -->
        <v-select
          v-model="p.editPlannedDialog.value.item_type"
          :items="ITEM_TYPE_OPTIONS"
          label="Тип" clearable
          variant="outlined" density="compact"
          class="mb-2"
        />
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
        <!-- Раздельные числа по ФЭО (владелец, 2026-09-14) — второй, независимый
             комплект: поля выше (Кол-во/Цена за единицу/Сумма) остаются
             «внутренним планом» (единственный источник дерева/контроля
             превышения, см. докстринг FeoPlannedItem.feo_quantity в
             backend/app/models/feo_planned_item.py). Показываем только когда ОБЕ
             галочки происхождения стоят разом; при одной галочке — набор выше и
             есть план, «как сейчас» (задача, п.3). -->
        <template v-if="p.editShowBothOriginFields.value && p.editPlannedDialog.value.payment_mode !== 'monthly'">
          <div class="text-caption text-medium-emphasis mb-1">Числа по ФЭО (для сверки с внутренним планом выше)</div>
          <v-row dense>
            <v-col cols="5">
              <v-text-field v-model="p.editPlannedDialog.value.feoQuantity" label="Кол-во по ФЭО" type="number" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="7">
              <v-text-field v-model.number="p.editPlannedDialog.value.feoUnitPrice" type="number" label="Цена за единицу по ФЭО, ₽" variant="outlined" density="compact" />
            </v-col>
          </v-row>
          <v-text-field
            v-model="p.editPlannedDialog.value.feoAmount"
            label="Сумма по ФЭО, ₽" type="number"
            variant="outlined" density="compact"
            :readonly="p.editFeoAmountIsComputed.value"
            :bg-color="p.editFeoAmountIsComputed.value ? 'grey-lighten-4' : undefined"
            :hint="p.editFeoAmountIsComputed.value ? 'Считается автоматически: кол-во × цена за единицу по ФЭО' : 'Необязательно — не заполняйте, если числа по ФЭО и по внутреннему плану совпадают'"
            persistent-hint
            class="mb-3"
          />
        </template>
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
        <!-- Ежемесячный: период "с даты по дату" (владелец, Волна 3, п.3) — вместо
             целого «Количество месяцев», отказывавшегося принимать «6,66» и не
             учитывавшего разную длину месяцев. Расшифровка и итог считаются
             сервером (editMonthlySchedule в useFeoPlannedItemEditDialog.ts) —
             та же формула, что и при сохранении (Правило №6). -->
        <template v-if="p.editPlannedDialog.value.payment_mode === 'monthly'">
          <v-row dense>
            <v-col cols="6">
              <v-text-field
                v-model="p.editPlannedDialog.value.monthly_start_date"
                label="Начало периода"
                type="date"
                variant="outlined" density="compact"
              />
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model="p.editPlannedDialog.value.monthly_end_date"
                label="Конец периода"
                type="date"
                variant="outlined" density="compact"
              />
            </v-col>
          </v-row>
          <v-text-field
            v-model.number="p.editPlannedDialog.value.monthly_amount"
            label="Платёж за месяц, ₽"
            type="number"
            variant="outlined" density="compact"
            class="mt-2 mb-1"
          />
          <div
            v-if="p.editMonthlySchedule.value"
            class="text-caption text-medium-emphasis mb-2"
            style="line-height:1.35"
          >
            <v-icon icon="mdi-information-outline" size="13" style="margin-top:-2px" class="mr-1" />
            {{ p.editMonthlySchedule.value.label }}<template v-if="p.editMonthlySchedule.value.total != null">
              &nbsp;· итого {{ p.editMonthlySchedule.value.total.toLocaleString('ru-RU') }} ₽</template>
          </div>
          <div
            v-else-if="p.editPlannedDialog.value.monthly_start_date && p.editPlannedDialog.value.monthly_end_date"
            class="text-caption text-medium-emphasis mb-2"
          >
            Проверьте даты — конец периода должен быть позже начала.
          </div>
          <div v-else-if="p.editLegacyMonthsLabel.value" class="text-caption text-medium-emphasis mb-2">
            {{ p.editLegacyMonthsLabel.value }} — укажите период выше, чтобы пересчитать точно.
          </div>
        </template>
      </v-card-text>
      <v-card-actions class="px-4 pb-3">
        <v-spacer />
        <v-btn variant="text" @click="p.editPlannedDialog.value.show = false">Отмена</v-btn>
        <v-btn color="primary" variant="tonal" :disabled="p.editPlannedItemDisabled.value" :loading="p.editPlannedDialog.value.saving" @click="p.saveEditPlannedItem">Сохранить</v-btn>
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
import { ITEM_TYPE_OPTIONS } from '@/utils/itemTypeKind'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePlannedItems } from '@/composables/subsidies/usePlannedItems'

const { mobile } = useDisplay()
const p = usePlannedItems(useSubsidyDetailCtx())
</script>
