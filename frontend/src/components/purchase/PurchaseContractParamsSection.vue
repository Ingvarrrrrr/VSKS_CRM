<template>
  <!-- 4а. Параметры для генерации договора (admin+) -->
  <v-card variant="outlined" class="mb-4">
    <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Параметры {{ contractWordGen }} (для документа)</v-card-title>
    <v-card-text>
      <!-- Владелец (2026-09-15): «Срок приёмки/Неустойка/Срок гарантии/Договор задним
           числом/Доставка силами поставщика» — перенесено сюда из «Основной информации»
           (CreateOrderView.vue), т.к. это всё нужно только для формирования договора.
           Владелец (жалоба п.10, 2026-09-17): «Поле "Параметры для договора"
           должно быть выделено отдельно, а то сливается с остальными
           параметрами. Я сам путаюсь.» — «Условия договора» теперь отдельная
           рамка с фоном внутри общей карточки (не просто подзаголовок), плюс
           сюда же сведены предоплата/постоплата (раньше «Предоплата» стояла
           отдельным чекбоксом в самом низу секции, срок оплаты по факту не
           был виден нигде на форме — см. form.payment_term_days). -->
      <v-card
        v-if="form.contract_form"
        variant="outlined"
        class="mb-3 contract-terms-box"
      >
        <v-card-title class="text-subtitle-1 font-weight-bold d-flex align-center">
          <v-icon start size="20" color="indigo">mdi-file-document-edit-outline</v-icon>
          Условия договора
        </v-card-title>
        <v-card-text>
          <v-row v-if="['goods_single', 'services', 'services_food'].includes(form.contract_form)">
            <v-col cols="6" md="3">
              <v-text-field v-model.number="form.acceptance_term_days" type="number" label="Срок приёмки (раб. дней)" density="compact" variant="outlined" @blur="flushAutosaveOnBlur" />
            </v-col>
            <v-col cols="6" md="3">
              <v-text-field v-model.number="form.penalty_rate" type="number" step="0.01" label="Неустойка, %/день" density="compact" variant="outlined" @blur="flushAutosaveOnBlur" />
            </v-col>
            <v-col cols="12" md="6">
              <div class="d-flex ga-2">
                <v-text-field
                  v-model.number="form.warranty_period_days"
                  type="number"
                  label="Срок гарантии"
                  density="compact"
                  variant="outlined"
                  hide-details
                  style="max-width:120px"
                  @blur="flushAutosaveOnBlur"
                />
                <v-select
                  v-model="form.warranty_period_unit"
                  :items="WARRANTY_UNIT_OPTIONS"
                  item-title="title"
                  item-value="value"
                  label="Единица"
                  density="compact"
                  variant="outlined"
                  hide-details
                  style="max-width:150px"
                  @update:model-value="flushAutosaveOnBlur"
                />
              </div>
              <div class="text-caption text-medium-emphasis mt-1">{{ warrantyHintText }}</div>
            </v-col>
          </v-row>
          <v-row class="mt-1">
            <v-col cols="12" md="6">
              <v-checkbox
                v-model="form.is_retroactive"
                label="Договор задним числом (ст. 425 ГК РФ)"
                hint="Если включено, в шаблон добавляется пункт о применении условий с даты начала услуг до подписания договора. {{is_retroactive}}"
                persistent-hint
                density="compact"
              />
            </v-col>
            <v-col v-if="form.contract_form === 'goods_single'" cols="12" md="6">
              <v-checkbox
                v-model="form.delivery_by_supplier"
                label="Доставка силами поставщика"
                hint="В договоре поставки: включено — поставщик доставляет сам; выключено — самовывоз со склада поставщика."
                persistent-hint
                density="compact"
              />
            </v-col>
          </v-row>
          <v-divider class="my-3" />
          <div class="text-caption text-medium-emphasis font-weight-medium text-uppercase mb-2">Оплата</div>
          <v-row>
            <v-col cols="12" md="4">
              <v-btn-toggle
                :model-value="form.is_prepayment ? 'prepayment' : 'postpayment'"
                mandatory density="compact" color="primary" variant="outlined"
                @update:model-value="(v: string) => { form.is_prepayment = (v === 'prepayment'); flushAutosaveOnBlur() }"
              >
                <v-btn value="prepayment" size="small">Предоплата</v-btn>
                <v-btn value="postpayment" size="small">Оплата по факту</v-btn>
              </v-btn-toggle>
            </v-col>
            <v-col v-if="form.is_prepayment || form.methodology === 'large'" cols="12" md="3">
              <v-text-field
                v-model.number="form.advance_amount"
                type="number"
                label="Сумма аванса, ₽"
                :hint="form.methodology === 'large' ? 'Также используется в актах «большой отчётности»' : undefined"
                :persistent-hint="form.methodology === 'large'"
                density="compact" variant="outlined" @blur="flushAutosaveOnBlur"
              />
            </v-col>
            <v-col v-if="form.is_prepayment" cols="12" md="5">
              <div class="d-flex align-center gap-2 mt-1">
                <v-icon size="16" color="blue-grey-lighten-2">mdi-calendar-clock</v-icon>
                <span class="text-body-2 text-medium-emphasis">
                  Дата предоплаты: <strong>{{ form.prepayment_date || '—' }}</strong>
                </span>
                <v-btn size="x-small" variant="text" color="primary" class="ml-1" @click="scrollToDatesSection">Изменить ↓</v-btn>
              </div>
              <div class="text-caption text-medium-emphasis">Дата редактируется в блоке «Сроки и даты»</div>
            </v-col>
            <v-col v-if="!form.is_prepayment" cols="12" md="4">
              <v-text-field
                v-model.number="form.payment_term_days"
                type="number"
                label="Срок оплаты после поставки, дней"
                hint="{{payment_term_days}} в шаблонах. По умолчанию 10."
                persistent-hint
                density="compact"
                variant="outlined"
                @blur="flushAutosaveOnBlur"
              />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
      <v-row>
        <v-col cols="12" md="3">
          <v-select
            v-model="form.service_period_type"
            :items="[{title: 'Период (с... по...)', value: 'period'}, {title: 'Разовая дата', value: 'date'}]"
            item-title="title" item-value="value"
            label="Тип срока оказания услуг" variant="outlined" density="compact" clearable
          />
        </v-col>
        <!-- Даты редактируются только в блоке «Сроки и даты» ниже -->
        <v-col cols="12" md="5">
          <div class="d-flex align-center gap-2 mt-1">
            <v-icon size="16" color="blue-grey-lighten-2">mdi-calendar-range</v-icon>
            <span class="text-body-2 text-medium-emphasis">
              <template v-if="form.service_period_type === 'period'">
                Период:
                <strong>{{ form.service_start_date || '—' }}</strong>
                &nbsp;—&nbsp;
                <strong>{{ form.service_end_date || '—' }}</strong>
              </template>
              <template v-else-if="form.service_period_type === 'date'">
                Дата оказания услуг:
                <strong>{{ form.service_start_date || '—' }}</strong>
              </template>
              <template v-else>Тип срока не выбран</template>
            </span>
            <v-btn
              size="x-small" variant="text" color="primary" class="ml-1"
              @click="scrollToDatesSection"
            >Изменить ↓</v-btn>
          </div>
          <div class="text-caption text-medium-emphasis">Изменить даты — в блоке «Сроки и даты»</div>
        </v-col>
        <v-col cols="12" md="3">
          <v-checkbox
            v-model="form.third_party_involved"
            label="Привлечение третьих лиц"
            density="compact" hide-details class="mt-2"
          />
        </v-col>
      </v-row>
      <!-- Владелец (закупка РЕЕ-2026-00918, 2026-09-16): «НДС должно быть в ОДНОМ
           месте, в панели "Позиции закупки"» — раньше режим/ставка/статья НК РФ
           вводились здесь, отдельно от переключателя режима над таблицей позиций,
           и терялись. Поля НДС отсюда убраны — единственное место теперь
           components/purchase/PurchaseVatBlock.vue, смонтированный в
           PurchaseItemsEditor.vue над таблицей позиций (id="pub-target-vat"). -->
      <v-row>
        <v-col cols="12">
          <div class="text-caption text-medium-emphasis d-flex align-center ga-1">
            <v-icon size="16">mdi-information-outline</v-icon>
            НДС задаётся в панели «Позиции закупки» (режим, ставка, статья НК РФ)
          </div>
        </v-col>
      </v-row>

      <!-- Phase 23: customer requisites preview -->
      <v-card variant="outlined" class="mb-3" style="border-color:#9c6ade; background:transparent">
        <v-card-text class="pa-3">
          <div class="d-flex align-center mb-2">
            <v-icon icon="mdi-domain" size="18" color="purple-darken-2" class="mr-2" />
            <span class="text-body-1 font-weight-bold">Реквизиты Заказчика (подставятся в шаблон)</span>
            <v-spacer />
            <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-information-outline" @click="showPlaceholdersDialog = true">
              Доступные переменные
            </v-btn>
          </div>
          <div v-if="customerPreview" class="text-body-2 text-high-emphasis" style="line-height:1.7">
            <div><strong>{{ customerPreview.full_name || customerPreview.name }}</strong></div>
            <div>ИНН/КПП: {{ customerPreview.inn || '—' }} / {{ customerPreview.kpp || '—' }}</div>
            <div v-if="customerPreview.address">Адрес: {{ customerPreview.address }}</div>
            <div v-if="customerPreview.signatory">Подписант: {{ customerPreview.signatory }}</div>
          </div>
          <div v-else class="text-body-2 text-medium-emphasis">
            Сначала выберите субсидию — реквизиты возьмутся из её организации.
          </div>
          <div class="text-caption text-high-emphasis mt-2">
            Изменить реквизиты можно в карточке организации (Иерархия → клик на организацию).
          </div>
        </v-card-text>
      </v-card>

      <!-- Phase 19: template-specific fields (submission deadline, delivery location, service term) -->
      <v-divider class="my-3" />
      <div class="text-subtitle-2 font-weight-bold mb-1">Для формирования договора</div>
      <div class="text-caption text-high-emphasis mb-2">
        Переменные, которые не были определены ранее (форма договора, приём заявок, место и срок оказания услуг)
      </div>
      <!-- Форма договора (текст договора) + методичка (приложение к договору, выбирается отдельно) -->
      <v-row v-if="formMode !== 'service_note_delivery' && formMode !== 'advance_report' && form.purchase_method !== 'advance'">
        <v-col cols="12" md="6">
          <v-select
            v-model="form.contract_form"
            :items="contractFormOptions"
            item-title="title"
            item-value="value"
            label="Форма договора (текст договора)"
            variant="outlined"
            density="compact"
            clearable
            hint="Определяет какой шаблон используется при скачивании «Договор» и «Договор+ТЗ»"
            persistent-hint
          />
        </v-col>
        <v-col cols="12" md="6">
          <v-select
            v-model="form.methodology"
            :items="methodologyOptions"
            item-title="title"
            item-value="value"
            label="Методические рекомендации"
            variant="outlined"
            density="compact"
            clearable
            hint="Приложение к договору — приклеивается к готовому документу отдельно от формы договора. Не выбирается автоматически."
            persistent-hint
          />
        </v-col>
      </v-row>
      <v-row>
        <v-col cols="12">
          <!-- Phase 32 (владелец, 2026-09-13): раньше здесь было ВТОРОЕ свободное
               поле ввода того же адреса поверх покомпонентных полей ниже
               (индекс/город/улица/дом/корпус) — «странно дублировать». ПРАВИЛО
               №6: один источник — form.delivery_location теперь либо особая
               формулировка (см. toggleSpecialDeliveryLocation), либо ВСЕГДА
               пересобирается из покомпонентных полей (watch на assembledDeliveryAddress
               ниже в скрипте). Ручного ввода строки адреса тут больше нет. -->
          <div id="pub-target-address" style="position:relative">
            <div v-if="pointerTarget === 'address'" class="pub-pointer"><span class="mdi mdi-arrow-down-bold" /></div>
            <div :class="pointerTarget === 'address' ? 'pub-glow' : ''">
              <div class="mb-2 d-flex align-center flex-wrap ga-2">
                <v-btn-toggle
                  v-model="form.delivery_location_kind"
                  density="compact" mandatory color="primary" variant="outlined"
                >
                  <v-btn value="delivery" size="small">Адрес доставки</v-btn>
                  <v-btn value="service" size="small">Место оказания услуг</v-btn>
                </v-btn-toggle>
                <v-btn
                  size="small" density="compact"
                  :variant="isSpecialDeliveryLocation ? 'flat' : 'tonal'"
                  :color="isSpecialDeliveryLocation ? 'primary' : undefined"
                  :prepend-icon="isSpecialDeliveryLocation ? 'mdi-check' : undefined"
                  @click="toggleSpecialDeliveryLocation"
                >
                  По месту нахождения подрядчика
                </v-btn>
              </div>
              <div class="text-body-2" style="line-height:1.5">
                <span class="text-medium-emphasis">{{ deliveryLabel }} (подставится в документ):</span>
                <strong class="ml-1">{{ form.delivery_location || '—' }}</strong>
              </div>
              <div v-if="!isSpecialDeliveryLocation" class="text-caption text-medium-emphasis">
                Собирается автоматически из полей адреса ниже (индекс / город / улица / дом / корпус) — вводить его отдельно не нужно.
              </div>
            </div>
          </div>
        </v-col>
      </v-row>
      <!-- Регион поставки и Регион проведения мероприятия — рядом в одной строке -->
      <v-row>
        <v-col cols="12" md="6">
          <div id="pub-target-region" style="position:relative">
            <div v-if="pointerTarget === 'region'" class="pub-pointer"><span class="mdi mdi-arrow-down-bold" /></div>
            <div :class="pointerTarget === 'region' ? 'pub-glow' : ''">
              <v-autocomplete
                v-model="form.delivery_region"
                :items="DELIVERY_REGIONS"
                label="Регион поставки (субъект РФ)"
                density="compact"
                variant="outlined"
                clearable
                hide-details
                hint="Используется для ОКАТО/федерального округа места поставки Фабриканта"
                persistent-hint
                @update:model-value="pointerTarget = null; clearGuideArrow()"
              />
            </div>
          </div>
        </v-col>
        <v-col cols="12" md="6">
          <v-autocomplete
            v-model="form.region"
            :items="RUSSIAN_REGIONS"
            label="Регион проведения мероприятия"
            density="compact"
            variant="outlined"
            clearable
            hide-details
            hint='Включая вариант "Федеральное мероприятие"'
            persistent-hint
          />
        </v-col>
      </v-row>
      <v-row>
        <v-col cols="12" md="3">
          <v-text-field
            v-model="form.delivery_postcode"
            label="Индекс"
            variant="outlined"
            density="compact"
            hide-details
          />
        </v-col>
        <v-col cols="12" md="3">
          <v-text-field
            v-model="form.delivery_city"
            label="Город / населённый пункт"
            variant="outlined"
            density="compact"
            hide-details
          />
        </v-col>
        <v-col cols="12" md="3">
          <v-text-field
            v-model="form.delivery_street"
            label="Улица"
            variant="outlined"
            density="compact"
            hide-details
          />
        </v-col>
        <v-col cols="12" md="2">
          <v-text-field
            v-model="form.delivery_house"
            label="Дом"
            variant="outlined"
            density="compact"
            hide-details
          />
        </v-col>
        <v-col cols="12" md="1">
          <v-text-field
            v-model="form.delivery_building"
            label="Корпус"
            variant="outlined"
            density="compact"
            hide-details
          />
        </v-col>
      </v-row>
      <!-- Владелец (жалоба п.10, 2026-09-17): «Предоплата» и срок оплаты (постоплата)
           перенесены в блок «Условия договора» выше (см. переключатель «Предоплата /
           Оплата по факту») — раньше чекбокс стоял здесь отдельно, оторванный от
           остальных условий договора, а срок оплаты по факту не был виден нигде
           на форме (form.payment_term_days). Дата предоплаты по-прежнему
           редактируется в блоке «Сроки и даты» (form.prepayment_date). -->
      <v-row class="mt-2">
        <v-col cols="12" md="4">
          <v-checkbox
            v-model="form.is_likely_needed"
            label="Скорее всего понадобится"
            density="compact" hide-details
          />
        </v-col>
      </v-row>
      <!-- «Подпись этапа» относится только к рамочным договорам (этапы/накопительные
           заказы) — владелец (2026-09-13): у разового договора этапов нет, поле
           не должно быть видно. -->
      <v-row v-if="form.purchase_contract_type !== 'single'">
        <v-col cols="12" md="6">
          <v-text-field
            v-model="form.stage_label"
            label="Подпись этапа"
            variant="outlined" density="compact"
            hint="Например: Февраль 2026"
            persistent-hint
          />
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
// Блок «4а. Параметры для генерации договора». Вынесено из CreateOrderView.vue
// (рефакторинг без изменения поведения, часть 3). form — reactive-объект
// родителя (мутируется напрямую v-model). showPlaceholdersDialog — общий
// ref с диалогом PlaceholdersDialog, который остаётся во view (используется
// вне этой секции) — приходит через v-model/defineModel, чтобы запись из
// кнопки «Доступные переменные» отражалась в том же состоянии родителя.
// pointerTarget — ref из composables/purchase/useGuideArrow.ts (композабл
// вызывается один раз в родителе, ПРАВИЛО №6); эта секция читает его для
// подсветки поля и обнуляет при выборе региона — приходит через v-model,
// как и showPlaceholdersDialog, чтобы запись отражалась в общем состоянии
// гида по всей форме (используется и другими секциями).
// DELIVERY_REGIONS/RUSSIAN_REGIONS — статические константы, импортируются
// напрямую (не пропы, т.к. не меняются и не относятся к состоянию формы).
import { computed, watch } from 'vue'
import { RUSSIAN_REGIONS, DELIVERY_REGIONS } from '@/constants/russian_regions'
import { WARRANTY_UNIT_OPTIONS, warrantyPeriodText } from '@/utils/warrantyPeriod'

const props = defineProps<{
  form: any
  contractWordGen: string
  formMode: string
  customerPreview: any
  contractFormOptions: Array<{ title: string; value: string }>
  methodologyOptions: Array<{ title: string; value: string }>
  clearGuideArrow: () => void
  deliveryLabel: string
  scrollToDatesSection: () => void
  flushAutosaveOnBlur: () => void
}>()

const showPlaceholdersDialog = defineModel<boolean>('showPlaceholdersDialog', { required: true })
const pointerTarget = defineModel<string | null>('pointerTarget', { required: true })

// ПРАВИЛО №6: адрес доставки — один источник. По умолчанию form.delivery_location
// пересобирается из покомпонентных полей ниже (индекс/регион/город/улица/дом/корпус —
// тот же порядок и формат, что использует backend/app/services/publications_payload.py
// _build_delivery_address для публикации на Фабрикант, чтобы документ и публикация не
// расходились). Если пользователь явно выбрал особую формулировку («по месту нахождения
// подрядчика» — реально встречается в боевых данных, это НЕ адрес, а юридическая фраза),
// она замораживается и watch её не перезаписывает.
const DELIVERY_LOCATION_SPECIAL = 'По месту нахождения подрядчика'

// Превью «В договор уйдёт "1 год"» — то же склонение, что использует backend
// при генерации документа (app/services/documents/contract_terms.py), см.
// комментарий в utils/warrantyPeriod.ts.
const warrantyPreview = computed(() => {
  const text = warrantyPeriodText(props.form.warranty_period_days, props.form.warranty_period_unit)
  return text || '—'
})
// Собрано в JS (не в template), чтобы литеральные "{{ }}" из имён переменных
// шаблона не путались с mustache-интерполяцией Vue-компилятора.
const warrantyHintText = computed(() =>
  `В договор уйдёт «${warrantyPreview.value}» ({{warranty_period_text}} в новых шаблонах; ` +
  `старое {{warranty_period_days}} остаётся числом — не ломает существующие договоры).`
)

const assembledDeliveryAddress = computed(() => {
  const f = props.form
  const parts: string[] = []
  if ((f.delivery_postcode || '').trim()) parts.push(f.delivery_postcode.trim())
  if ((f.delivery_region || '').trim()) parts.push(f.delivery_region.trim())
  if ((f.delivery_city || '').trim()) parts.push(f.delivery_city.trim())
  if ((f.delivery_street || '').trim()) parts.push(f.delivery_street.trim())
  if ((f.delivery_house || '').trim()) parts.push('д. ' + f.delivery_house.trim())
  if ((f.delivery_building || '').trim()) parts.push('к. ' + f.delivery_building.trim())
  return parts.join(', ')
})

const isSpecialDeliveryLocation = computed(() => props.form.delivery_location === DELIVERY_LOCATION_SPECIAL)

function toggleSpecialDeliveryLocation() {
  props.form.delivery_location = isSpecialDeliveryLocation.value
    ? assembledDeliveryAddress.value
    : DELIVERY_LOCATION_SPECIAL
}

watch(assembledDeliveryAddress, (val) => {
  if (!isSpecialDeliveryLocation.value) props.form.delivery_location = val
}, { immediate: true })
</script>

<style scoped>
/* Владелец (жалоба п.10, 2026-09-17): «Условия договора» должны читаться как
   отдельный блок, а то сливаются с остальными параметрами. Рамка + лёгкий фон,
   с адаптацией под тёмную тему (тот же приём, что BudgetBar.vue). */
.contract-terms-box {
  border-color: #6366f1 !important;
}
:deep(.v-theme--light) .contract-terms-box,
.v-theme--light .contract-terms-box {
  background: rgba(99, 102, 241, 0.05);
}
:deep(.v-theme--dark) .contract-terms-box,
.v-theme--dark .contract-terms-box {
  background: rgba(99, 102, 241, 0.1);
}
</style>
