<template>
  <!-- Диалог создания плановой позиции (Ур.5 FeoPlannedItem) прямо в текущей категории —
       POST /feo-planned-items/, без перехода на другую страницу и потери введённых данных
       формы (см. баг «кнопка ничего не делает», сессия 2026-08-05). -->
  <v-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" max-width="420" persistent>
    <v-card>
      <v-card-title class="text-subtitle-1">Новая плановая позиция</v-card-title>
      <v-card-text>
        <div class="text-caption text-medium-emphasis mb-2">Категория: {{ categoryName }}</div>
        <v-text-field
          v-model="form.name"
          label="Наименование *"
          variant="outlined"
          density="compact"
          hide-details="auto"
          class="mb-2"
          autofocus
        />
        <v-text-field
          v-model.number="form.quantity"
          type="number"
          label="Количество"
          variant="outlined"
          density="compact"
          hide-details="auto"
          class="mb-2"
        />
        <v-text-field
          v-model="form.unit"
          label="Ед. изм."
          variant="outlined"
          density="compact"
          hide-details="auto"
          class="mb-2"
        />
        <!-- Цена за единицу (владелец, 2026-09-02) — необязательное поле, см. коммент
             у createForm.unitPrice в useFeoPlannedCreate.ts. Задана — «Сумма плана» ниже
             считается сама (кол-во × цена) и недоступна для ручного ввода; не задана —
             обычное поле. -->
        <v-text-field
          v-model.number="form.unitPrice"
          type="number"
          label="Цена за единицу, ₽ (необязательно)"
          variant="outlined"
          density="compact"
          hide-details="auto"
          class="mb-1"
          :hint="form.unitPrice == null ? UNIT_PRICE_NOT_FIXED_HINT : ''"
          :persistent-hint="form.unitPrice == null"
        />
        <v-text-field
          v-model.number="form.amount"
          type="number"
          label="Сумма плана, ₽"
          variant="outlined"
          density="compact"
          hide-details="auto"
          :readonly="amountIsComputed"
          :bg-color="amountIsComputed ? 'grey-lighten-4' : undefined"
          class="mb-1"
        />
        <div class="text-caption text-medium-emphasis mb-2" style="line-height:1.35">
          <v-icon icon="mdi-information-outline" size="13" style="margin-top:-2px" class="mr-1" />{{ priceCaption }}
        </div>
        <!-- Блок 1 (план zany-fluttering-mountain.md, 2026-08-14): товар/услуга/работа —
             необязательно, как и у остальных полей этого диалога. -->
        <v-select
          v-model="form.item_type"
          :items="ITEM_TYPE_OPTIONS"
          label="Тип"
          variant="outlined"
          density="compact"
          hide-details="auto"
          clearable
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="saving" @click="$emit('update:modelValue', false)">Отмена</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" @click="$emit('save')">Создать</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { UNIT_PRICE_NOT_FIXED_HINT } from '@/constants/planPriceLabels'
import { ITEM_TYPE_OPTIONS } from '@/composables/items/feoPlanned/useFeoPlannedCreate'

defineProps<{
  modelValue: boolean
  categoryName: string
  form: { name: string; quantity: number | null; unit: string; unitPrice: number | null; amount: number | null; item_type: string | null }
  amountIsComputed: boolean
  priceCaption: string
  saving: boolean
}>()

defineEmits<{
  'update:modelValue': [value: boolean]
  save: []
}>()
</script>
