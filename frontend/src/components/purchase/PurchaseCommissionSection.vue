<template>
  <!-- Владелец (2026-09-15): «Закупочная комиссия для протокола — это вообще
       отдельная сущность, её выделить надо отдельно». Раньше эти поля жили
       внутри «Основной информации» (CreateOrderView.vue) под подзаголовком
       «Закупочная комиссия (для протокола)» — теперь это свой блок.
       Разметка и form.* не менялись — только расположение. Рендерится, только
       если у родителя form.contract_form выбран (та же видимость, что была раньше). -->
  <v-card variant="outlined" class="mb-4">
    <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Закупочная комиссия (для протокола)</v-card-title>
    <v-card-text>
      <v-row>
        <v-col cols="12" md="4">
          <v-text-field v-model="form.commission_member_1_name" label="ФИО члена комиссии 1" density="compact" variant="outlined" @blur="flushAutosaveOnBlur" />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field v-model="form.commission_member_2_name" label="ФИО члена комиссии 2" density="compact" variant="outlined" @blur="flushAutosaveOnBlur" />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field v-model="form.commission_member_3_name" label="ФИО члена комиссии 3" density="compact" variant="outlined" @blur="flushAutosaveOnBlur" />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model="form.procurement_protocol_number"
            label="Номер протокола закупочной комиссии"
            density="compact"
            variant="outlined"
            hint="Заполняется в шаблоне протокола. {{procurement_protocol_number}}"
            persistent-hint
            @blur="flushAutosaveOnBlur"
          />
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>

  <!-- Владелец: «номер приказа о закупке необходим для формирования приказа» —
       не относится к комиссии (другой документ, другой набор подписантов),
       поэтому вынесен в отдельную карточку рядом, а не смешан со списком
       членов комиссии. -->
  <v-card variant="outlined" class="mb-4">
    <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">Приказ о закупке</v-card-title>
    <v-card-text>
      <v-row>
        <v-col cols="12" md="4">
          <v-text-field
            v-model="form.procurement_order_number"
            label="Номер приказа о закупке"
            density="compact"
            variant="outlined"
            hint="Номер внутреннего приказа, подтверждающего проведение закупки. {{procurement_order_number}}"
            persistent-hint
            @blur="flushAutosaveOnBlur"
          />
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
// Блок «Закупочная комиссия (для протокола)» + «Приказ о закупке». Вынесено
// из CreateOrderView.vue (владелец, 2026-09-15) — обе сущности раньше жили
// в общем блоке «Основная информация», хотя относятся к разным документам
// (протокол закупочной комиссии и приказ о закупке — не одно и то же).
// form — reactive-объект родителя, мутируется напрямую v-model (тот же
// паттерн, что в PurchaseContractParamsSection.vue). flushAutosaveOnBlur —
// форсирует немедленное автосохранение при потере фокуса полем (родитель
// также вешает глобальный document-level focusout listener, так что это
// не единственный путь сохранения, но сохранён 1-в-1 с прежней разметкой).
defineProps<{
  form: any
  flushAutosaveOnBlur: () => void
}>()
</script>
