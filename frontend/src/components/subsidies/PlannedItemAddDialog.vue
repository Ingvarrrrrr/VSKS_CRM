<template>
  <!-- ── Диалог добавления плановой позиции ── -->
  <v-dialog v-model="p.showAddPlannedDialog.value" max-width="440" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
        <v-icon icon="mdi-plus-circle" color="teal" class="mr-2" />
        Добавить плановую позицию
      </v-card-title>
      <v-card-text>
        <!-- Владелец (2026-08-31): при добавлении плановой позиции можно написать
             что угодно, но у нас есть большая база товаров/услуг — подсказки с
             фильтром по вводу и картинкой. Переиспользует InlineProductMatch
             (тот же компонент, что и в строках позиций закупки/заявок) — второй
             такой же компонент не заводим. Свободный ввод обязателен: любое
             набранное имя сохраняется как есть, ничего не дописывается в каталог
             товаров (hideCreateNew скрывает «Создать новый товар…» — здесь это
             только подсказки/визуализация, а не привязка к каталогу). -->
        <!-- Владелец (2026-09-01): «добавляется плановая позиция по одной штуке,
             соответственно картинку сделай раза в 3 больше, чтобы было видно» —
             size 36 → 108 (ровно ×3). -->
        <!-- Владелец (2026-09-01, повторно): картинку над полем наименования (не
             сбоку) — сбоку она отжирала ширину и длинные названия вылезали за
             пределы узкого поля. Поле — на всю ширину диалога (w-100), картинку
             не уменьшаем. -->
        <div class="mb-2">
          <v-tooltip v-if="p.addPlannedProductPhoto.value" location="right">
            <template #activator="{ props: tip }">
              <v-avatar v-bind="tip" size="108" rounded="lg" style="cursor:pointer;overflow:hidden">
                <img :src="p.addPlannedProductPhoto.value" style="width:108px;height:108px;object-fit:cover;display:block" />
              </v-avatar>
            </template>
            <img :src="p.addPlannedProductPhoto.value" style="width:240px;height:240px;object-fit:cover;border-radius:8px;display:block" />
          </v-tooltip>
          <v-icon v-else size="64" class="text-medium-emphasis">mdi-package-variant</v-icon>
        </div>
        <InlineProductMatch
          class="w-100 mb-3"
          :item-name="p.plannedItemForm.value.name"
          :product-id="p.addPlannedProductId.value"
          :match-confirmed="p.addPlannedMatchConfirmed.value"
          hide-create-new
          @update:search-text="p.plannedItemForm.value.name = $event"
          @pick="p.onPlannedItemProductPick"
          @clear="p.onPlannedItemProductClear"
        />
        <v-row>
          <v-col cols="5">
            <v-text-field
              v-model.number="p.plannedItemForm.value.quantity"
              label="Количество" type="number"
              variant="outlined" density="compact"
            />
          </v-col>
          <v-col cols="7">
            <v-text-field
              v-model="p.plannedItemForm.value.unit"
              label="Единица измерения"
              variant="outlined" density="compact"
              placeholder="шт, кг, услуга..."
            />
          </v-col>
        </v-row>
        <!-- Плановая стоимость за единицу (владелец, 2026-09-01): подставляется из
             каталога при выборе товара (onPlannedItemProductPick), полностью
             редактируема; пока задана и не равна 0 — «Плановая сумма» ниже считается
             как количество × эта цена (см. watch на plannedItemForm.quantity/unitPrice
             в usePlannedItems.ts). -->
        <v-text-field
          v-model.number="p.plannedItemForm.value.unitPrice"
          label="Плановая стоимость за единицу, ₽" type="number"
          variant="outlined" density="compact" suffix="₽"
          class="mb-1"
          :hint="p.plannedItemForm.value.unitPrice == null ? UNIT_PRICE_NOT_FIXED_HINT : ''"
          :persistent-hint="p.plannedItemForm.value.unitPrice == null"
        />
        <div v-if="p.addPlannedPriceCaption.value" class="text-caption text-medium-emphasis mb-2" style="line-height:1.35">
          <v-icon icon="mdi-information-outline" size="13" style="margin-top:-2px" class="mr-1" />{{ p.addPlannedPriceCaption.value }}
        </div>
        <v-text-field
          v-model.number="p.plannedItemForm.value.amount"
          label="Плановая сумма (₽)" type="number"
          variant="outlined" density="compact" suffix="₽"
          :readonly="p.plannedItemAmountIsComputed.value"
          :bg-color="p.plannedItemAmountIsComputed.value ? 'grey-lighten-4' : undefined"
          :hint="p.plannedItemAmountIsComputed.value ? 'Считается автоматически: количество × стоимость за единицу' : ''"
          :persistent-hint="p.plannedItemAmountIsComputed.value"
          :class="p.plannedItemForm.value.payment_mode === 'monthly' ? 'd-none' : 'mb-3'"
        />
        <!-- Происхождение плановой позиции (владелец, 2026-09-01): «это плановая
             позиция в соответствии с ФЭО, или только в соответствии с нашим
             внутренним планом» — ДВЕ НЕЗАВИСИМЫЕ галочки, не переключатель, обе
             можно поставить/снять независимо. Доступны только тому, кто может
             редактировать ФЭО (вкладка feo_categories) — эта же панель уже целиком
             ограничена ею, см. проверку доступа страницы. -->
        <div class="text-caption text-medium-emphasis mb-1">Происхождение позиции</div>
        <v-checkbox
          v-model="p.plannedItemForm.value.is_feo_breakdown"
          density="compact" hide-details
          class="mb-1"
        >
          <template #label>
            <div>
              <div style="line-height:1.2">По ФЭО</div>
              <div class="text-caption text-medium-emphasis" style="line-height:1.2">жёсткая разбивка ФЭО — покупать будут именно это, отчётность строгая</div>
            </div>
          </template>
        </v-checkbox>
        <v-checkbox
          v-model="p.plannedItemForm.value.is_internal_plan"
          density="compact" hide-details
          class="mb-3"
        >
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
          v-model="p.plannedItemForm.value.payment_mode"
          mandatory density="compact" variant="outlined" divided
          class="mb-3"
        >
          <v-btn value="one_time" size="small">Разовый</v-btn>
          <v-btn value="monthly" size="small">Ежемесячный</v-btn>
        </v-btn-toggle>
        <!-- Разовый: дата потребности -->
        <v-text-field
          v-if="p.plannedItemForm.value.payment_mode === 'one_time'"
          v-model="p.plannedItemForm.value.planned_date"
          label="Дата потребности"
          type="date"
          variant="outlined" density="compact"
          class="mb-2"
        />
        <!-- Ежемесячный: поля -->
        <template v-if="p.plannedItemForm.value.payment_mode === 'monthly'">
          <v-text-field
            v-model="p.plannedItemForm.value.monthly_start_date"
            label="Первый платёж"
            type="date"
            variant="outlined" density="compact"
            class="mb-2"
          />
          <v-row dense>
            <v-col cols="6">
              <v-text-field
                v-model.number="p.plannedItemForm.value.months_count"
                label="Кол-во месяцев"
                type="number"
                variant="outlined" density="compact"
              />
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model.number="p.plannedItemForm.value.monthly_amount"
                label="Платёж за месяц, ₽"
                type="number"
                variant="outlined" density="compact"
              />
            </v-col>
          </v-row>
          <div
            v-if="p.plannedItemForm.value.monthly_amount && p.plannedItemForm.value.months_count"
            class="text-caption text-medium-emphasis mb-2"
          >
            Итого по позиции: {{ ((p.plannedItemForm.value.monthly_amount ?? 0) * (p.plannedItemForm.value.months_count ?? 0)).toLocaleString('ru-RU') }} ₽
          </div>
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="p.showAddPlannedDialog.value = false">Отмена</v-btn>
        <v-btn color="teal" variant="flat" :loading="p.savingPlannedItem.value"
          :disabled="!p.plannedItemForm.value.name.trim()"
          @click="p.savePlannedItem">
          Добавить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Диалог «Добавить плановую позицию» — вынесен из SubsidiesView.vue. Состояние/
// логика (включая openAddPlannedItem/openConvertManualPlanToItem/
// openCreatePlannedFromActual, вызываемые деревом ФЭО и FeoCategoryDialog.vue
// через ctx) — в usePlannedItems.ts (singleton, общий с остальными тремя
// диалогами панели «план vs факт»).
import { useDisplay } from 'vuetify'
import InlineProductMatch from '@/components/items/InlineProductMatch.vue'
import { UNIT_PRICE_NOT_FIXED_HINT } from '@/constants/planPriceLabels'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePlannedItems } from '@/composables/subsidies/usePlannedItems'

const { mobile } = useDisplay()
const p = usePlannedItems(useSubsidyDetailCtx())
</script>
