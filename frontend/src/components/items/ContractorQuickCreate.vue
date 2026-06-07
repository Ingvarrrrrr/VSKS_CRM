<template>
  <!-- Presentational quick contractor-create dialog. Parent owns the reactive
       `form` object, the saving flag and the actual POST handler; this child
       renders the fields (mutating the passed-in reactive form in place) and
       emits save/cancel. Extracted from PurchaseItemsEditor.vue (Layer 2). -->
  <v-dialog :model-value="modelValue" max-width="480" persistent
    @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-4 d-flex align-center justify-space-between">
        <span><v-icon icon="mdi-store-plus" class="mr-2" />Новый контрагент</span>
        <v-btn icon="mdi-close" variant="text" size="small" @click="emit('update:modelValue', false)" />
      </v-card-title>
      <v-card-text class="px-4 pb-2">
        <v-alert type="info" density="compact" variant="tonal" class="mb-3 text-caption">
          Контрагент не найден в БД. Заполните минимальные данные для создания.
        </v-alert>
        <v-text-field
          v-model="form.name"
          label="Наименование *"
          variant="outlined" density="compact"
          :rules="[(v: string) => !!v || 'Обязательное поле']"
          class="mb-2"
        />
        <v-text-field
          v-model="form.inn"
          label="ИНН"
          variant="outlined" density="compact" class="mb-2"
        />
        <v-text-field
          v-model="form.kpp"
          label="КПП"
          variant="outlined" density="compact" class="mb-2"
        />
        <v-text-field
          v-model="form.address"
          label="Адрес"
          variant="outlined" density="compact"
        />
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="emit('update:modelValue', false)">Отмена</v-btn>
        <v-btn color="primary" :loading="saving"
          :disabled="!form.name.trim()"
          @click="emit('save')">
          Создать
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
interface ContractorForm {
  name: string
  inn: string
  kpp: string
  address: string
}

defineProps<{
  modelValue: boolean
  /** Reactive form owned by the parent; mutated in place via v-model. */
  form: ContractorForm
  saving?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  save: []
}>()
</script>
