<template>
  <!-- 4б. Сроки и даты закупки — единый блок -->
  <v-card id="section-dates" variant="outlined" class="mb-4">
    <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 d-flex align-center">
      <v-icon start color="blue-grey">mdi-calendar-clock</v-icon>
      Сроки и даты
    </v-card-title>
    <v-card-text>

      <!-- 1. Планирование -->
      <div class="text-caption text-medium-emphasis font-weight-medium text-uppercase mb-2">Планирование</div>
      <v-row dense>
        <v-col cols="12" md="4">
          <v-text-field
            v-model="form.procurement_planned_date"
            label="Планируемая дата закупки"
            variant="outlined" density="compact" type="date"
            hint="Когда планируем провести закупку — используется в плане закупок"
            persistent-hint
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model="form.submission_deadline"
            label="Приём заявок до"
            variant="outlined" density="compact"
            type="datetime-local"
            hint="Дедлайн подачи предложений поставщиками"
            persistent-hint
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model="form.order_date"
            label="Дата заказа"
            variant="outlined" density="compact" type="date"
            hint="Когда сделан заказ поставщику" persistent-hint
          />
        </v-col>
      </v-row>

      <v-divider class="my-3" />

      <!-- 2. Срок поставки (исполнения) — единый блок -->
      <div class="text-caption text-medium-emphasis font-weight-medium text-uppercase mb-2">Срок поставки (исполнения)</div>
      <v-row dense>
        <v-col cols="12">
          <v-radio-group
            v-model="deliveryMode"
            inline density="compact" hide-details class="mt-0"
            @update:model-value="onDeliveryModeChange"
          >
            <v-radio label="Не указано" value="" />
            <v-radio label="Конкретные даты (с… по…)" value="range" />
            <v-radio label="В течение N дней" value="duration" />
            <v-radio label="До даты" value="deadline" />
          </v-radio-group>
          <div class="text-caption text-medium-emphasis mt-1">
            Единый срок поставки / оказания услуг: транслируется в шаблоны (&#123;&#123;execution_term&#125;&#125;) и на площадки
          </div>
        </v-col>
      </v-row>

      <v-row v-if="deliveryMode === 'range'" dense class="mt-1">
        <v-col cols="12" sm="4">
          <v-text-field
            v-model="form.service_start_date"
            label="Начало периода (с даты)" type="date"
            variant="outlined" density="compact"
            hint="Дата начала поставки / оказания услуг" persistent-hint
            @update:model-value="syncExecutionTermFromDates"
          />
        </v-col>
        <v-col cols="12" sm="4">
          <v-text-field
            v-model="form.service_end_date"
            label="Конец периода (по дату)" type="date"
            variant="outlined" density="compact"
            hint="Дата завершения поставки / оказания услуг" persistent-hint
            @update:model-value="syncExecutionTermFromDates"
          />
        </v-col>
      </v-row>

      <v-row v-else-if="deliveryMode === 'duration'" dense class="mt-1">
        <v-col cols="12" sm="4">
          <v-text-field
            v-model.number="form.service_term_days"
            label="Количество дней" type="number" min="1"
            variant="outlined" density="compact"
            hint="Срок исполнения в днях от даты заключения договора" persistent-hint
            @update:model-value="syncExecutionTermFromDates"
          />
        </v-col>
        <v-col cols="12" sm="4">
          <v-select
            v-model="form.service_term_type"
            :items="[{title: 'Календарных дней', value: 'calendar'}, {title: 'Рабочих дней', value: 'working'}]"
            item-title="title" item-value="value"
            label="Тип дней" variant="outlined" density="compact"
            @update:model-value="syncExecutionTermFromDates"
          />
        </v-col>
      </v-row>

      <v-row v-else-if="deliveryMode === 'deadline'" dense class="mt-1">
        <v-col cols="12" sm="5">
          <v-text-field
            v-model="form.service_deadline_date"
            label="До какой даты" type="date"
            variant="outlined" density="compact"
            hint="Товар/услуга должны быть получены не позднее этой даты" persistent-hint
            @update:model-value="syncExecutionTermFromDates"
          />
        </v-col>
        <v-col cols="12" sm="4" class="d-flex align-center gap-2">
          <!-- Конец месяца quick-fill -->
          <v-menu v-model="endOfMonthMenu" :close-on-content-click="false" location="bottom">
            <template #activator="{ props: menuProps }">
              <v-btn v-bind="menuProps" size="small" variant="tonal" color="teal" prepend-icon="mdi-calendar-end">
                Конец месяца
              </v-btn>
            </template>
            <v-card min-width="260" class="pa-3">
              <div class="text-body-2 font-weight-medium mb-2">Выберите период</div>
              <v-row dense>
                <v-col cols="6">
                  <v-text-field
                    v-model.number="endOfMonthYear"
                    label="Год" type="number" min="2020" max="2040"
                    variant="outlined" density="compact"
                  />
                </v-col>
                <v-col cols="6">
                  <v-select
                    v-model="endOfMonthMonth"
                    :items="endOfMonthMonthItems"
                    item-title="label" item-value="value"
                    label="Месяц"
                    variant="outlined" density="compact"
                  />
                </v-col>
              </v-row>
              <v-btn color="primary" size="small" block @click="onApplyEndOfMonth">Применить</v-btn>
            </v-card>
          </v-menu>
        </v-col>
      </v-row>

      <v-divider class="my-3" />

      <!-- 3. Срок действия договора и планирование оплаты -->
      <div class="text-caption text-medium-emphasis font-weight-medium text-uppercase mb-2">Срок действия договора и платежи</div>
      <v-row dense>
        <v-col cols="12" md="4">
          <div @click="(contractHeaderLocked || (isFramework && !!selectedFrameworkContract?.end_date)) ? onLockedFieldClick?.() : undefined">
            <v-text-field
              v-model="form.contract_end_date"
              label="Срок действия договора"
              variant="outlined" density="compact" type="date"
              :readonly="contractHeaderLocked || (isFramework && !!selectedFrameworkContract?.end_date)"
              :bg-color="(contractHeaderLocked || (isFramework && selectedFrameworkContract?.end_date)) ? 'grey-lighten-4' : undefined"
              :hint="(contractHeaderLocked || (isFramework && selectedFrameworkContract?.end_date)) ? 'Общий срок действия рамочного договора — при изменении применится ко всем связанным закупкам' : 'До какой даты действует договор'"
              persistent-hint
            />
            <div v-if="contractHeaderLocked || (isFramework && selectedFrameworkContract?.end_date)" class="text-caption mt-1">
              <a href="#" class="text-primary font-weight-medium" @click.prevent.stop="onGoToContract?.()">Отредактировать в договоре →</a>
            </div>
          </div>
        </v-col>
        <v-col cols="12" md="4">
          <v-select
            v-model="form.commitment_quarter"
            :items="[1,2,3,4]"
            label="Квартал принятия обязательств"
            variant="outlined" density="compact" clearable
            hint="Квартал, в котором приняты обязательства" persistent-hint
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model="form.planned_payment_month"
            label="Планируемый месяц платежа"
            variant="outlined" density="compact" type="date"
            hint="Месяц, в котором планируется платёж" persistent-hint
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model="form.agreement_date"
            label="Дата доп.соглашения"
            variant="outlined" density="compact" type="date"
            hint="Дата подписания дополнительного соглашения (при наличии)" persistent-hint
          />
        </v-col>
      </v-row>

    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useEndOfMonthFill } from '@/composables/purchase/useEndOfMonthFill'

const props = defineProps<{
  form: any
  isFramework: boolean
  selectedFrameworkContract: any
  contractHeaderLocked?: boolean
  onGoToContract?: () => void
  onLockedFieldClick?: () => void
}>()

const { endOfMonthMenu, endOfMonthYear, endOfMonthMonth, endOfMonthMonthItems, applyEndOfMonth } = useEndOfMonthFill(props.form)

const deliveryMode = computed({
  get(): string {
    if (props.form.service_term_mode) return props.form.service_term_mode
    if (props.form.execution_term || props.form.delivery_date) return 'deadline'
    return ''
  },
  set(val: string) {
    props.form.service_term_mode = val
    if (val === 'deadline') {
      if (!props.form.service_deadline_date) {
        props.form.service_deadline_date = props.form.execution_term || props.form.delivery_date || ''
      }
    }
  },
})

function onDeliveryModeChange(val: string) {
  if (val === 'deadline') {
    if (!props.form.service_deadline_date) {
      props.form.service_deadline_date = props.form.execution_term || props.form.delivery_date || ''
    }
    syncExecutionTermFromDates()
  } else if (val === 'range') {
    syncExecutionTermFromDates()
  } else if (val === 'duration') {
    syncExecutionTermFromDates()
  }
}

function syncExecutionTermFromDates() {
  const mode = props.form.service_term_mode || deliveryMode.value
  if (mode === 'deadline') {
    if (props.form.service_deadline_date) {
      props.form.execution_term = props.form.service_deadline_date
      props.form.delivery_date = props.form.service_deadline_date
    }
  } else if (mode === 'range') {
    if (props.form.service_end_date) {
      props.form.execution_term = props.form.service_end_date
      props.form.delivery_date = props.form.service_end_date
    }
  }
}

function onApplyEndOfMonth() {
  applyEndOfMonth()
  syncExecutionTermFromDates()
}
</script>
