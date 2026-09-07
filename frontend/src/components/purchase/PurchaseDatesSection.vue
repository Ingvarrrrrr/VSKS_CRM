<template>
  <!-- 4б. Сроки и даты закупки — единый блок -->
  <v-card id="section-dates" variant="outlined" class="mb-4">
    <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 d-flex align-center">
      <v-icon start color="blue-grey">mdi-calendar-clock</v-icon>
      Сроки и даты
    </v-card-title>
    <v-card-text>

      <!-- Планирование -->
      <div class="text-caption text-medium-emphasis font-weight-medium text-uppercase mb-2">Планирование</div>
      <v-row>
        <v-col cols="12" md="3">
          <v-text-field
            v-model="form.procurement_planned_date"
            label="Планируемая дата закупки"
            variant="outlined" density="compact" type="date"
            hint="Когда планируем провести закупку — используется в плане закупок"
            persistent-hint
          />
        </v-col>
        <v-col cols="12" md="3">
          <v-text-field
            v-model="form.delivery_date"
            label="Нужна к дате"
            variant="outlined" density="compact" type="date"
            hint="Срок, к которому товар/услуга должны быть получены"
            persistent-hint
          />
        </v-col>
        <v-col cols="12" md="6">
          <v-text-field
            v-model="form.submission_deadline"
            label="Приём заявок до"
            variant="outlined" density="compact"
            type="datetime-local"
            hint="Дедлайн подачи предложений поставщиками (уходит на Фабрикант как {{submission_deadline_datetime}})"
            persistent-hint
          />
        </v-col>
      </v-row>

      <v-divider class="my-3" />

      <!-- Исполнение -->
      <div class="text-caption text-medium-emphasis font-weight-medium text-uppercase mb-2">Исполнение</div>
      <v-row>
        <v-col cols="12">
          <div class="text-body-2 mb-1">Срок оказания услуг</div>
          <v-radio-group
            v-model="form.service_term_mode"
            inline density="compact" hide-details class="mt-0"
          >
            <v-radio label="Не указано" value="" />
            <v-radio label="Конкретные даты (с… по…)" value="range" />
            <v-radio label="В течение N дней" value="duration" />
            <v-radio label="До даты" value="deadline" />
          </v-radio-group>
          <div class="text-caption text-medium-emphasis mt-1">Как считается срок исполнения: период, длительность или конкретная дата</div>
        </v-col>
      </v-row>
      <v-row v-if="form.service_term_mode === 'range'">
        <v-col cols="12" md="3">
          <v-text-field
            v-model="form.service_start_date"
            label="Начало периода" type="date"
            variant="outlined" density="compact"
            hint="Дата начала оказания услуг/поставки" persistent-hint
          />
        </v-col>
        <v-col cols="12" md="3">
          <v-text-field
            v-model="form.service_end_date"
            label="Конец периода" type="date"
            variant="outlined" density="compact"
            hint="Дата завершения оказания услуг/поставки" persistent-hint
          />
        </v-col>
      </v-row>
      <v-row v-if="form.service_term_mode === 'duration'">
        <v-col cols="12" md="3">
          <v-text-field
            v-model.number="form.service_term_days"
            label="Количество дней" type="number" min="1"
            variant="outlined" density="compact"
            hint="Срок исполнения в днях от даты подписания" persistent-hint
          />
        </v-col>
        <v-col cols="12" md="3">
          <v-select
            v-model="form.service_term_type"
            :items="[{title: 'Календарных', value: 'calendar'}, {title: 'Рабочих', value: 'working'}]"
            item-title="title" item-value="value"
            label="Тип дней" variant="outlined" density="compact"
          />
        </v-col>
      </v-row>
      <v-row v-if="form.service_term_mode === 'deadline'">
        <v-col cols="12" md="3">
          <v-text-field
            v-model="form.service_deadline_date"
            label="До какой даты" type="date"
            variant="outlined" density="compact"
            hint="Услуга/поставка должна быть исполнена не позднее этой даты" persistent-hint
          />
        </v-col>
        <v-col cols="12" md="4" class="d-flex align-center gap-2">
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
              <v-btn color="primary" size="small" block @click="applyEndOfMonth">Применить</v-btn>
            </v-card>
          </v-menu>
        </v-col>
      </v-row>

      <v-divider class="my-3" />

      <!-- Договор и оплата -->
      <div class="text-caption text-medium-emphasis font-weight-medium text-uppercase mb-2">Договор и оплата</div>
      <v-row>
        <v-col cols="12" md="3">
          <v-text-field
            v-model="form.contract_end_date"
            label="Срок действия договора"
            variant="outlined" density="compact" type="date"
            :readonly="isFramework && !!selectedFrameworkContract?.end_date"
            :bg-color="isFramework && selectedFrameworkContract?.end_date ? 'grey-lighten-4' : undefined"
            hint="До какой даты действует договор" persistent-hint
          />
        </v-col>
        <v-col cols="12" md="3">
          <v-select
            v-model="form.commitment_quarter"
            :items="[1,2,3,4]"
            label="Квартал принятия обязательств"
            variant="outlined" density="compact" clearable
            hint="Квартал, в котором приняты обязательства" persistent-hint
          />
        </v-col>
        <v-col cols="12" md="3">
          <v-text-field
            v-model="form.planned_payment_month"
            label="Планируемый месяц платежа"
            variant="outlined" density="compact" type="date"
            hint="Месяц, в котором планируется платёж" persistent-hint
          />
        </v-col>
        <v-col cols="12" md="3">
          <v-text-field
            v-model="form.agreement_date"
            label="Дата доп.соглашения"
            variant="outlined" density="compact" type="date"
            hint="Дата подписания дополнительного соглашения (при наличии)" persistent-hint
          />
        </v-col>
        <v-col cols="12" md="3">
          <v-text-field
            v-model="form.order_date"
            label="Дата заказа"
            variant="outlined" density="compact" type="date"
            hint="Когда сделан заказ поставщику" persistent-hint
          />
        </v-col>
        <v-col v-if="form.is_prepayment" cols="12" md="3">
          <v-text-field
            v-model="form.prepayment_date"
            label="Дата предоплаты" type="date"
            variant="outlined" density="compact"
            hint="Когда возникло обязательство по предоплате" persistent-hint
          />
        </v-col>
      </v-row>

    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
// Блок «Сроки и даты» закупки. Вынесено из CreateOrderView.vue (рефакторинг
// без изменения поведения, часть 3). form — тот же reactive-объект родителя,
// мутируется напрямую через v-model (как и раньше). useEndOfMonthFill(form)
// вызывается прямо здесь: endOfMonthMenu/Year/Month/Items и applyEndOfMonth
// нигде за пределами этого блока в CreateOrderView.vue не используются —
// перенос композабла целиком безопасен (проверено grep по всему файлу).
import { useEndOfMonthFill } from '@/composables/purchase/useEndOfMonthFill'

const props = defineProps<{
  form: any
  isFramework: boolean
  selectedFrameworkContract: any
}>()

const { endOfMonthMenu, endOfMonthYear, endOfMonthMonth, endOfMonthMonthItems, applyEndOfMonth } = useEndOfMonthFill(props.form)
</script>
