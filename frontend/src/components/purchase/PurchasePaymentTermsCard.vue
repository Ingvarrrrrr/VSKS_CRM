<template>
  <v-card id="section-payment-terms" variant="outlined" class="mb-4">
    <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 d-flex align-center">
      <v-icon start color="teal">mdi-cash-clock</v-icon>
      Условия оплаты
    </v-card-title>
    <v-card-text>
      <div id="pub-target-payment-terms" style="position:relative">
        <div v-if="pointerTarget === 'payment-terms'" class="pub-pointer">
          <span class="mdi mdi-arrow-down-bold" />
        </div>
        <div :class="pointerTarget === 'payment-terms' ? 'pub-glow' : ''">
          <v-row dense class="align-center mb-2">
            <v-col cols="12">
              <v-btn-toggle
                v-model="selectedMode"
                mandatory
                density="compact"
                color="primary"
                variant="outlined"
                class="flex-wrap"
                @update:model-value="onModeChange"
              >
                <v-btn value="postpayment" size="small">По факту поставки</v-btn>
                <v-btn value="postponement" size="small">Отсрочка платежа</v-btn>
                <v-btn value="prepayment" size="small">Предоплата</v-btn>
                <v-btn value="other" size="small">Иное</v-btn>
              </v-btn-toggle>
            </v-col>
          </v-row>

          <!-- 1. Постоплата -->
          <v-row v-if="selectedMode === 'postpayment'" dense class="mt-2">
            <v-col cols="12">
              <div class="text-caption text-medium-emphasis">
                Оплата производится в полном объёме после поставки товара / оказания услуг и подписания закрывающих документов.
              </div>
            </v-col>
          </v-row>

          <!-- 2. Отсрочка платежа -->
          <v-row v-else-if="selectedMode === 'postponement'" dense class="mt-2 align-center">
            <v-col cols="12" sm="4">
              <v-text-field
                v-model.number="form.payment_postpone_days"
                label="Срок оплаты (дней)"
                type="number"
                min="1"
                density="compact"
                variant="outlined"
                hint="В течение N дней после поставки"
                persistent-hint
                @update:model-value="onPostponeDaysChange"
              />
            </v-col>
            <v-col cols="12" sm="4">
              <v-select
                v-model="form.payment_postpone_day_type"
                :items="[
                  { title: 'Календарных дней', value: 'calendar' },
                  { title: 'Рабочих дней', value: 'work' },
                ]"
                item-title="title"
                item-value="value"
                label="Тип дней"
                density="compact"
                variant="outlined"
                @update:model-value="flushAutosaveOnBlur"
              />
            </v-col>
            <v-col cols="12" sm="4">
              <div class="text-caption text-medium-emphasis">
                Срок транслируется в шаблоны договора (&#123;&#123;payment_term_days&#125;&#125;) и площадки (Фабрикант / Росэлторг).
              </div>
            </v-col>
          </v-row>

          <!-- 3. Предоплата -->
          <v-row v-else-if="selectedMode === 'prepayment'" dense class="mt-2 align-center">
            <v-col cols="12" sm="3">
              <v-text-field
                v-model.number="form.prepayment_percent"
                label="Размер аванса, %"
                type="number"
                min="1"
                max="100"
                density="compact"
                variant="outlined"
                suffix="%"
                hint="Процент предоплаты"
                persistent-hint
                @update:model-value="flushAutosaveOnBlur"
              />
            </v-col>
            <v-col cols="12" sm="3">
              <v-text-field
                v-model.number="form.advance_amount"
                label="Сумма аванса, ₽"
                type="number"
                density="compact"
                variant="outlined"
                suffix="₽"
                hint="Используется в отчётности и договоре"
                persistent-hint
                @update:model-value="flushAutosaveOnBlur"
              />
            </v-col>
            <v-col cols="12" sm="3">
              <v-text-field
                v-model="form.prepayment_date"
                label="Дата предоплаты"
                type="date"
                density="compact"
                variant="outlined"
                hint="Дата обязательства по авансу"
                persistent-hint
                @update:model-value="flushAutosaveOnBlur"
              />
            </v-col>
            <v-col cols="12" sm="3">
              <div class="text-caption text-medium-emphasis">
                Будет сформировано условие авансирования для договора и площадок.
              </div>
            </v-col>
          </v-row>

          <!-- 4. Иное -->
          <v-row v-else-if="selectedMode === 'other'" dense class="mt-2">
            <v-col cols="12">
              <v-textarea
                v-model="form.payment_other_terms"
                label="Условия оплаты (индивидуальный текст)"
                rows="2"
                auto-grow
                density="compact"
                variant="outlined"
                hint="Текст условий оплаты для площадок и договора"
                persistent-hint
                @blur="flushAutosaveOnBlur"
              />
            </v-col>
          </v-row>
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'

const props = defineProps<{
  form: Record<string, any>
  flushAutosaveOnBlur?: () => void
  clearGuideArrow?: () => void
}>()

const pointerTarget = defineModel<string | null>('pointerTarget', { default: null })

const selectedMode = computed({
  get(): string {
    const t = props.form.payment_terms_type
    if (t === 'postponement') return 'postponement'
    if (t === 'prepayment' || props.form.is_prepayment) return 'prepayment'
    if (t === 'other') return 'other'
    return 'postpayment'
  },
  set(val: string) {
    props.form.payment_terms_type = val
    if (val === 'postpayment') {
      props.form.is_prepayment = false
      props.form.prepayment_percent = null
      props.form.prepayment_date = null
      props.form.payment_postpone_days = null
      props.form.payment_term_days = null
    } else if (val === 'postponement') {
      props.form.is_prepayment = false
      props.form.prepayment_percent = null
      props.form.prepayment_date = null
      if (!props.form.payment_postpone_days && props.form.payment_term_days) {
        props.form.payment_postpone_days = props.form.payment_term_days
      }
      if (!props.form.payment_postpone_day_type) {
        props.form.payment_postpone_day_type = 'calendar'
      }
      props.form.payment_term_days = props.form.payment_postpone_days
    } else if (val === 'prepayment') {
      props.form.is_prepayment = true
      props.form.payment_postpone_days = null
      props.form.payment_term_days = null
    } else if (val === 'other') {
      props.form.is_prepayment = false
      props.form.payment_postpone_days = null
      props.form.payment_term_days = null
    }
  },
})

function onModeChange() {
  if (pointerTarget.value === 'payment-terms') {
    pointerTarget.value = null
  }
  props.clearGuideArrow?.()
  props.flushAutosaveOnBlur?.()
}

function onPostponeDaysChange(days: number | null) {
  props.form.payment_term_days = days
  props.flushAutosaveOnBlur?.()
}

// Двусторонняя синхронизация payment_postpone_days и payment_term_days
watch(
  () => props.form.payment_postpone_days,
  (val) => {
    if (selectedMode.value === 'postponement') {
      props.form.payment_term_days = val
    }
  },
)

watch(
  () => props.form.payment_term_days,
  (val) => {
    if (selectedMode.value === 'postponement' && props.form.payment_postpone_days !== val) {
      props.form.payment_postpone_days = val
    }
  },
)
</script>

<style scoped>
.pub-pointer {
  position: absolute;
  top: -24px;
  left: 20px;
  color: #ff5722;
  font-size: 24px;
  animation: bounce 1s infinite alternate;
  z-index: 5;
}
@keyframes bounce {
  from { transform: translateY(0); }
  to { transform: translateY(-8px); }
}
.pub-glow {
  box-shadow: 0 0 12px rgba(255, 87, 34, 0.4);
  border-radius: 8px;
  transition: box-shadow 0.3s ease;
}
</style>
