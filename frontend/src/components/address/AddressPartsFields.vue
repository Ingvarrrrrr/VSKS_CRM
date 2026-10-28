<template>
  <v-row dense>
    <v-col cols="4" sm="3">
      <v-text-field
        :model-value="parts.postal_code"
        label="Индекс"
        variant="outlined" density="compact" hide-details
        maxlength="6"
        @update:model-value="update('postal_code', $event)"
      />
    </v-col>
    <v-col cols="8" sm="9">
      <v-combobox
        :model-value="parts.region"
        :items="regionOptions"
        label="Субъект РФ (регион)"
        variant="outlined" density="compact" hide-details
        clearable
        @update:model-value="update('region', $event || '')"
      />
    </v-col>
  </v-row>
  <v-row dense class="mt-2">
    <v-col cols="12" sm="6">
      <v-text-field
        :model-value="parts.district"
        label="Район / городской округ"
        variant="outlined" density="compact" hide-details
        placeholder="Бердянский район / г.о. Бердянск"
        @update:model-value="update('district', $event)"
      />
    </v-col>
    <v-col cols="4" sm="2">
      <v-select
        :model-value="parts.settlement_type"
        :items="SETTLEMENT_TYPE_OPTIONS"
        label="Тип"
        variant="outlined" density="compact" hide-details
        clearable
        @update:model-value="update('settlement_type', $event || '')"
      />
    </v-col>
    <v-col cols="8" sm="4">
      <v-text-field
        :model-value="parts.settlement"
        label="Населённый пункт"
        variant="outlined" density="compact" hide-details
        placeholder="Бердянск"
        @update:model-value="update('settlement', $event)"
      />
    </v-col>
  </v-row>
  <v-row dense class="mt-2">
    <v-col cols="12">
      <v-text-field
        :model-value="parts.street"
        label="Улица"
        variant="outlined" density="compact" hide-details
        placeholder="ул. Ленина"
        @update:model-value="update('street', $event)"
      />
    </v-col>
  </v-row>
  <v-row dense class="mt-2">
    <v-col cols="4">
      <v-text-field
        :model-value="parts.house"
        label="Дом"
        variant="outlined" density="compact" hide-details
        @update:model-value="update('house', $event)"
      />
    </v-col>
    <v-col cols="4">
      <v-text-field
        :model-value="parts.building"
        label="Корпус / строение"
        variant="outlined" density="compact" hide-details
        @update:model-value="update('building', $event)"
      />
    </v-col>
    <v-col cols="4">
      <v-text-field
        :model-value="parts.office"
        label="Офис / помещение"
        variant="outlined" density="compact" hide-details
        @update:model-value="update('office', $event)"
      />
    </v-col>
  </v-row>
</template>

<script setup lang="ts">
// Переиспользуемые поля адреса "по частям" (ПРАВИЛО №5/№6) — индекс, регион,
// район/городской округ, населённый пункт (с типом), улица, дом, корпус,
// офис. Сборка итоговой строки — frontend/src/utils/addressCompose.ts
// (composeAddress), зеркало backend/app/services/address_compose.py.
//
// Используется карточкой контрагента/организации (ContractorEditDialog.vue).
// Карточку договора/закупки (CreateOrderView.vue, структурные delivery_*
// поля) этот компонент НЕ заменяет — тот экран относится к параллельно
// правящейся области "purchases"/НМЦД и не затрагивался этой задачей.
import { computed } from 'vue'
import { RUSSIAN_REGIONS } from '@/constants/russian_regions'
import { emptyAddressParts, type AddressParts } from '@/utils/addressCompose'

const SETTLEMENT_TYPE_OPTIONS = ['г.', 'г.о.', 'пгт', 'рп', 'с.', 'д.', 'х.', 'п.']

const props = defineProps<{
  modelValue: Partial<AddressParts> | null | undefined
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: AddressParts): void
}>()

const parts = computed<AddressParts>(() => ({ ...emptyAddressParts(), ...(props.modelValue || {}) }))
const regionOptions = computed(() => RUSSIAN_REGIONS)

function update<K extends keyof AddressParts>(key: K, value: AddressParts[K]) {
  emit('update:modelValue', { ...parts.value, [key]: value ?? '' })
}
</script>
