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
             набранное имя сохраняется как есть в самой плановой позиции (у
             FeoPlannedItem нет product_id, см. usePlannedItems.ts).
             Владелец (волна 3, п.19, 2026-09-13): «утверждение "в каталоге нет,
             можно создать новый" не соответствует действительности... новый
             должен создаваться просто путём написания в поле» — раньше здесь
             стоял hideCreateNew, прятавший пункт «Создать новый товар…» из
             списка, при этом статус-подсказка компонента всё равно обещала
             «можно создать новый». Теперь hideCreateNew снят, пункт меню
             виден, а @create-new заводит товар в общем каталоге products
             (см. onPlannedCreateNewProduct ниже) — тем же способом, что и
             остальной каталог (POST /products/, дедуп по похожему имени на
             бэкенде), без второго диалога создания товара. -->
        <!-- Ctrl+V в это поле (жалоба владельца, там же) — почин на уровне
             самого InlineProductMatch.vue (readonly-поле до активации теперь
             перехватывает paste вручную), здесь ничего дополнительно
             включать не нужно. -->
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
          @update:search-text="p.plannedItemForm.value.name = $event"
          @pick="p.onPlannedItemProductPick"
          @create-new="onPlannedCreateNewProduct"
          @clear="p.onPlannedItemProductClear"
        />
        <!-- Владелец (Волна 3, п.2, «двоится Количество»): «Тут я выбрал ежемесячный
             платёж, соответственно должно перемножаться количество месяцев на
             ежемесячный платёж. Поле "Кол-во" в данном случае сбивает с толку»
             — количество ЕДИНИЦ товара/услуги не участвует в сумме ежемесячного
             платежа (сумма = срок × платёж за месяц, см. ниже) и не имеет
             отношения к сроку, поэтому для monthly-режима это поле скрыто, а не
             показано рядом со сроком под тем же общим смыслом «количество».
             Именно сюда раньше просачивалось дробное число месяцев (боевой
             случай владельца — «Кол-во» 6.66 в данных по субсидии). -->
        <v-row v-if="p.plannedItemForm.value.payment_mode !== 'monthly'">
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
        <!-- Тип позиции — товар/услуга/работа (владелец, 21.09, раздел W2):
             автоподставляется из каталога при выборе товара (см.
             applyPlannedProductHint в useFeoPlannedItemAddDialog.ts), пока
             пользователь не тронул поле сам. ITEM_TYPE_OPTIONS — единственный
             источник списка (Правило №6). -->
        <v-select
          v-model="p.plannedItemForm.value.item_type"
          :items="ITEM_TYPE_OPTIONS"
          label="Тип" clearable
          variant="outlined" density="compact"
          class="mb-2"
          @update:model-value="p.onPlannedItemTypeInput"
        />
        <!-- Чекбокс синхронизации типа с каталогом — виден только когда выбран
             товар каталога И тип позиции расходится с типом товара в каталоге
             (или у товара тип не задан), см. addShowSyncProductKindCheckbox. -->
        <v-checkbox
          v-if="p.addShowSyncProductKindCheckbox.value"
          v-model="p.addSyncProductKind.value"
          density="compact" hide-details
          label="Обновить тип товара в каталоге"
          class="mb-2"
        />
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
        <!-- Раздельные числа по ФЭО (владелец, 2026-09-14): «надо отдельно если я
             включил по ФЭО, и отдельно для Внутреннего плана, это нужно если ФЭО
             и внутренний план разнятся». Поля выше (Количество/Плановая стоимость
             за единицу/Плановая сумма) остаются «внутренним планом» — единственным
             источником для дерева плана и контроля превышения (см. докстринг
             FeoPlannedItem.feo_quantity в backend/app/models/feo_planned_item.py).
             Второй набор — только когда ОБЕ галочки выше стоят разом; при одной
             галочке единственный набор выше и есть план — «как сейчас» (задача,
             п.3), второй набор не показываем и не заставляем заполнять. -->
        <template v-if="p.addShowBothOriginFields.value && p.plannedItemForm.value.payment_mode !== 'monthly'">
          <div class="text-caption text-medium-emphasis mb-1">Числа по ФЭО (для сверки с внутренним планом выше)</div>
          <v-row>
            <v-col cols="5">
              <v-text-field
                v-model.number="p.plannedItemForm.value.feoQuantity"
                label="Кол-во по ФЭО" type="number"
                variant="outlined" density="compact"
              />
            </v-col>
            <v-col cols="7">
              <v-text-field
                v-model.number="p.plannedItemForm.value.feoUnitPrice"
                label="Цена за единицу по ФЭО, ₽" type="number"
                variant="outlined" density="compact" suffix="₽"
              />
            </v-col>
          </v-row>
          <v-text-field
            v-model.number="p.plannedItemForm.value.feoAmount"
            label="Сумма по ФЭО (₽)" type="number"
            variant="outlined" density="compact" suffix="₽"
            :readonly="p.plannedItemFeoAmountIsComputed.value"
            :bg-color="p.plannedItemFeoAmountIsComputed.value ? 'grey-lighten-4' : undefined"
            :hint="p.plannedItemFeoAmountIsComputed.value ? 'Считается автоматически: кол-во × цена за единицу по ФЭО' : 'Необязательно — не заполняйте, если числа по ФЭО и по внутреннему плану совпадают'"
            persistent-hint
            class="mb-3"
          />
        </template>
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
        <!-- Ежемесячный: период "с даты по дату" (владелец, Волна 3, п.3) — заменяет
             целое «Количество месяцев», которое отказывалось принимать «6,66» и не
             умело учесть разную длину месяцев. Расшифровка «6 мес. 20 дн.» и
             итоговая сумма считаются сервером (см. addPlannedMonthlySchedule в
             useFeoPlannedItemAddDialog.ts) — той же формулой, что и при
             сохранении, второй расчёт на фронте не заводим (Правило №6). -->
        <template v-if="p.plannedItemForm.value.payment_mode === 'monthly'">
          <v-row dense>
            <v-col cols="6">
              <v-text-field
                v-model="p.plannedItemForm.value.monthly_start_date"
                label="Начало периода"
                type="date"
                variant="outlined" density="compact"
              />
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model="p.plannedItemForm.value.monthly_end_date"
                label="Конец периода"
                type="date"
                variant="outlined" density="compact"
              />
            </v-col>
          </v-row>
          <v-text-field
            v-model.number="p.plannedItemForm.value.monthly_amount"
            label="Платёж за месяц, ₽"
            type="number"
            variant="outlined" density="compact"
            class="mt-2 mb-1"
          />
          <div
            v-if="p.addPlannedMonthlySchedule.value"
            class="text-caption text-medium-emphasis mb-2"
            style="line-height:1.35"
          >
            <v-icon icon="mdi-information-outline" size="13" style="margin-top:-2px" class="mr-1" />
            {{ p.addPlannedMonthlySchedule.value.label }}<template v-if="p.addPlannedMonthlySchedule.value.total != null">
              &nbsp;· итого {{ p.addPlannedMonthlySchedule.value.total.toLocaleString('ru-RU') }} ₽</template>
          </div>
          <div
            v-else-if="p.plannedItemForm.value.monthly_start_date && p.plannedItemForm.value.monthly_end_date"
            class="text-caption text-medium-emphasis mb-2"
          >
            Проверьте даты — конец периода должен быть позже начала.
          </div>
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="p.showAddPlannedDialog.value = false">Отмена</v-btn>
        <v-btn color="teal" variant="flat" :loading="p.savingPlannedItem.value"
          :disabled="p.addPlannedItemDisabled.value"
          @click="p.savePlannedItem">
          Добавить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Диалог «Такая позиция уже есть в плане» (Волна 2, п.2 владельца: кнопки
       «Привязать»/«Создать отдельную» открывались тостом БЕЗ кнопок) —
       переиспользует тот же компонент, что и FeoPlannedItemsSelect.vue, второй
       не заводим (Правило №6). attach-blocked-reason/attach-disabled здесь
       всегда «не заблокировано» — в этом пути (добавление из дерева ФЭО, не из
       подбора закупки к остатку плановой позиции) нет остатка, с которым
       сравнивать. -->
  <FeoPlannedDuplicateDialog
    v-model="p.duplicateDialog.value"
    :duplicate-info="p.duplicateInfo.value"
    :attach-blocked-reason="null"
    :attach-disabled="false"
    :saving="p.savingPlannedItem.value"
    :fmt="fmtMoney"
    @attach="p.confirmAttachDuplicate"
    @create-duplicate="p.confirmCreateDuplicate"
  />
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
import { ITEM_TYPE_OPTIONS } from '@/utils/itemTypeKind'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePlannedItems } from '@/composables/subsidies/usePlannedItems'
import { formatCurrency } from '@/composables/subsidies/format'
import FeoPlannedDuplicateDialog from '@/components/items/feo-planned/FeoPlannedDuplicateDialog.vue'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import type { MatchCandidate } from '@/composables/useItemMatching'

const { mobile } = useDisplay()
const p = usePlannedItems(useSubsidyDetailCtx())
// FeoPlannedDuplicateDialog.fmt ожидает number|null|undefined (см. её props) —
// formatCurrency сам по себе принимает только number|string, оборачиваем.
function fmtMoney(v: number | null | undefined): string {
  return v == null ? '—' : formatCurrency(v)
}

// Владелец (волна 3, п.19, 2026-09-13): «Создать новый товар…» из
// InlineProductMatch теперь виден в этом диалоге (см. шаблон выше) — по клику
// заводим товар в общем каталоге products (POST /products/, тот же эндпоинт,
// что и остальной каталог — второй способ создания товара не пишем, Правило
// №6) и сразу применяем его тем же путём, что и обычный выбор из подсказок
// (p.onPlannedItemProductPick из useFeoPlannedItemAddDialog.ts) — подставит
// имя/цену/фото и подтянет unit/price через product-hint, как при обычном
// pick. category='Прочее' — тот же дефолт, что и у Product.category в БД
// (backend/app/models/product.py) и у остальных мест автосоздания товара без
// явной категории (items_import_catalog.py, products_import_apply.py) — не
// придумываем новый дефолт. Бэкенд сам находит похожий товар (POST /products/
// уже проверяет дубликаты threshold=0.7) и возвращает 409 — в этом случае
// используем найденный существующий товар вместо создания почти-дубля.
const toast = useToast()
async function onPlannedCreateNewProduct() {
  const name = (p.plannedItemForm.value.name || '').trim()
  if (!name) return
  try {
    let created: any
    try {
      created = await apiFetch<any>('/products/', {
        method: 'POST',
        body: {
          name,
          category: 'Прочее',
          unit: p.plannedItemForm.value.unit || null,
          price: p.plannedItemForm.value.unitPrice ?? null,
        },
      })
    } catch (err: any) {
      const details = err?.payload?.details
      const existing = (err?.status === 409 && details && typeof details === 'object' && details.code === 'duplicate_product')
        ? details.existing : null
      if (!existing) throw err
      created = existing
      toast.info(`Похожий товар уже есть в каталоге — использован «${existing.name}»`)
    }
    p.onPlannedItemProductPick({
      product_id: created.id,
      name: created.name || name,
      price: created.price != null ? Number(created.price) : null,
      score: 1,
      photo_url: created.photo_url ?? null,
    } as MatchCandidate)
  } catch (e: any) {
    toast.error(e?.payload?.message || e?.detail || e?.message || 'Не удалось создать товар')
  }
}
</script>
