<template>
  <!-- ── Диалог редактирования плановой позиции ── -->
  <v-dialog v-model="p.editPlannedDialog.value.show" max-width="480" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
        <v-icon icon="mdi-pencil" color="blue" class="mr-2" />Редактировать плановую позицию
      </v-card-title>
      <v-card-text class="px-4 pb-2">
        <v-text-field v-model="p.editPlannedDialog.value.name" label="Наименование" variant="outlined" density="compact" class="mb-2" autofocus />
        <!-- Раскладка (владелец, п.15б, 13.10.2026): Наименование → галочки
             происхождения (каждая раскрывает СВОИ кол-во/ед.изм./цена/сумма) →
             общий блок «Тип платежа» → остальное (тип позиции, нужность,
             составная позиция). Общая секция-компонент с диалогом добавления
             (PlannedItemAddDialog.vue) — см. докстринг FeoPlannedOriginFields.vue,
             Правило №6, второй копии разметки не заводим. -->
        <FeoPlannedOriginFields
          :form="p.editPlannedDialog.value"
          :amount-is-computed="p.editAmountIsComputed.value"
          :price-caption="p.editPriceCaption.value"
          :feo-amount-is-computed="p.editFeoAmountIsComputed.value"
        />
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
        <!-- Остальное (владелец, п.15б: «Тип платежа — он общий для всех», всё
             прочее — после него). -->
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
        <!-- Статус «нужности» позиции (владелец, 04.10.2026) — NEED_LEVEL_OPTIONS
             единственный источник вариантов (@/utils/planNeedLevel.ts, Правило №6). -->
        <v-select
          v-model="p.editPlannedDialog.value.need_level"
          :items="NEED_LEVEL_OPTIONS"
          label="Нужность"
          variant="outlined" density="compact"
          class="mb-2"
        />
        <!-- Составная позиция (задача «Составная плановая позиция») — см.
             докстринг FeoPlannedItem.is_composite. -->
        <v-checkbox v-model="p.editPlannedDialog.value.is_composite" density="compact" hide-details class="mb-3">
          <template #label>
            <div>
              <div style="line-height:1.2">Составная позиция</div>
              <div class="text-caption text-medium-emphasis" style="line-height:1.2">
                несколько услуг на одно количество, например проживание + питание.
                Строки закупки, привязанные к этой позиции, не складывают количество:
                133 чел. проживания и 133 чел. питания = 133 чел. Цена за единицу
                проверяется по сумме цен строк.
              </div>
            </div>
          </template>
        </v-checkbox>
        <!-- История изменений (волна 3, 26.09) — «кто менял плановые позиции
             или вносил новые, независимо от способа внесения». Единственный
             компонент FeoItemHistory.vue переиспользуется и для категорий
             (FeoCategoryDialog.vue) — Правило №6, второй ленты не заводим. -->
        <v-divider class="my-3" />
        <v-expansion-panels variant="accordion">
          <v-expansion-panel>
            <v-expansion-panel-title class="text-body-2">
              <v-icon icon="mdi-history" size="16" class="mr-2" />История изменений
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <FeoItemHistory entity-type="feo_item" :entity-id="p.editPlannedDialog.value.id" />
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
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
import { ITEM_TYPE_OPTIONS } from '@/utils/itemTypeKind'
import { NEED_LEVEL_OPTIONS } from '@/utils/planNeedLevel'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePlannedItems } from '@/composables/subsidies/usePlannedItems'
import FeoItemHistory from '@/components/subsidies/FeoItemHistory.vue'
import FeoPlannedOriginFields from '@/components/items/feo-planned/FeoPlannedOriginFields.vue'

const { mobile } = useDisplay()
const p = usePlannedItems(useSubsidyDetailCtx())
</script>
