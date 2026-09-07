<template>
  <!-- 4а. Параметры для генерации договора (admin+) -->
  <v-card variant="outlined" class="mb-4">
    <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Параметры {{ contractWordGen }} (для документа)</v-card-title>
    <v-card-text>
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
      <v-row>
        <v-col cols="12" md="3">
          <v-checkbox
            v-model="form.vat_applicable"
            label="НДС применяется"
            density="compact" hide-details
          />
        </v-col>
        <v-col v-if="form.vat_applicable" cols="12" md="2">
          <v-text-field
            v-model.number="form.vat_rate"
            label="Ставка НДС (%)" variant="outlined" density="compact" type="number"
            suffix="%" placeholder="20"
          />
        </v-col>
        <v-col v-if="!form.vat_applicable" cols="12" md="6">
          <v-text-field
            v-model="form.vat_exemption_article"
            :label="vatExemptionAutoBasis ? 'Статья НК РФ (основание определено автоматически)' : 'Статья НК РФ *'"
            variant="outlined" density="compact"
            :placeholder="vatExemptionAutoBasis ? '' : 'напр. п.2 ст.346.11 НК РФ (УСН)'"
            :rules="vatExemptionAutoBasis ? [] : [(v: string) => !!(v && v.trim()) || 'Без основания документы с НДС не сформируются']"
            :hint="vatExemptionAutoBasis
              ? `Основание найдено автоматически: ${vatExemptionAutoBasis}. Можно ввести своё — оно заменит автоматическое.`
              : 'Обязательно для печати документов: без статьи НК РФ система откажет в формировании договора/приказа/листа согласования. Не требуется для самозанятых исполнителей и договоров ГПХ с физлицом — там основание определяется само.'"
            persistent-hint
          />
        </v-col>
        <!-- U-3: НДС режим toggle -->
        <v-col cols="12" md="4" class="d-flex align-center">
          <v-btn-toggle
            v-model="form.vat_mode"
            density="compact"
            rounded="lg"
            color="primary"
            border
            mandatory
            @update:model-value="onVatModeChange"
          >
            <v-btn value="uniform" size="small">НДС одинаковый</v-btn>
            <v-btn value="per_item" size="small">НДС для каждого товара</v-btn>
          </v-btn-toggle>
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
          <div id="pub-target-address" style="position:relative">
            <div v-if="pointerTarget === 'address'" class="pub-pointer"><span class="mdi mdi-arrow-down-bold" /></div>
            <div :class="pointerTarget === 'address' ? 'pub-glow' : ''">
              <div class="mb-1">
                <v-btn-toggle
                  v-model="form.delivery_location_kind"
                  density="compact" mandatory color="primary" variant="outlined"
                >
                  <v-btn value="delivery" size="small">Адрес доставки</v-btn>
                  <v-btn value="service" size="small">Место оказания услуг</v-btn>
                </v-btn-toggle>
              </div>
              <AddressAutocomplete
                v-model="form.delivery_location"
                :label="deliveryLabel"
                :customer-address="customerPreview?.address"
                hint="Подставится в шаблон документа"
                persistent-hint
              />
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
      <!-- Новые поля: скорее всего понадобится, предоплата перенесена в «Сроки и даты», подпись этапа -->
      <v-row class="mt-2">
        <v-col cols="12" md="4">
          <v-checkbox
            v-model="form.is_likely_needed"
            label="Скорее всего понадобится"
            density="compact" hide-details
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-checkbox
            v-model="form.is_prepayment"
            label="Предоплата"
            density="compact" hide-details
          />
        </v-col>
        <v-col v-if="form.is_prepayment" cols="12" md="4">
          <!-- дата предоплаты перенесена в блок «Сроки и даты» -->
        </v-col>
      </v-row>
      <v-row>
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
import AddressAutocomplete from '@/components/AddressAutocomplete.vue'
import { RUSSIAN_REGIONS, DELIVERY_REGIONS } from '@/constants/russian_regions'

defineProps<{
  form: any
  contractWordGen: string
  formMode: string
  vatExemptionAutoBasis: string | null
  onVatModeChange: (mode: string) => void
  customerPreview: any
  contractFormOptions: Array<{ title: string; value: string }>
  methodologyOptions: Array<{ title: string; value: string }>
  clearGuideArrow: () => void
  deliveryLabel: string
  scrollToDatesSection: () => void
}>()

const showPlaceholdersDialog = defineModel<boolean>('showPlaceholdersDialog', { required: true })
const pointerTarget = defineModel<string | null>('pointerTarget', { required: true })
</script>
