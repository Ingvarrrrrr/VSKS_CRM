<template>
  <v-dialog :model-value="modelValue" max-width="560" persistent :fullscreen="mobile" @update:model-value="onDialogUpdate">
    <v-card>
      <v-card-title class="pa-5 pb-2 d-flex align-center">
        <v-icon icon="mdi-car-plus" color="primary" class="mr-2" />
        Добавить ТС
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto"
          @click="close" />
      </v-card-title>
      <v-card-text class="pa-5 pt-2">
        <v-text-field
          v-model="createDialog.vin"
          label="VIN"
          hint="17 символов. Проверим дубликат при потере фокуса"
          persistent-hint
          variant="outlined"
          density="compact"
          class="mb-3"
          maxlength="17"
          :loading="createDialog.vinChecking"
          @blur="checkVinDuplicate"
          @update:model-value="onVinChange"
        />
        <v-alert
          v-if="createDialog.vinDuplicate"
          type="warning"
          variant="tonal"
          density="compact"
          class="mb-3"
        >
          <div class="text-body-2 font-weight-medium mb-1">
            Дубликат VIN! Уже есть ТС:
            <router-link :to="`/property/vehicles/${createDialog.vinDuplicate.id}`" class="text-decoration-underline">
              {{ createDialog.vinDuplicate.plate }} ({{ createDialog.vinDuplicate.brand }} {{ createDialog.vinDuplicate.model }})
            </router-link>
          </div>
          <div class="d-flex gap-2 mt-2">
            <v-btn size="x-small" color="primary" :to="`/property/vehicles/${createDialog.vinDuplicate.id}`">
              Открыть существующее
            </v-btn>
            <v-btn size="x-small" variant="outlined" @click="createDialog.forceCreate = true; createDialog.vinDuplicate = null">
              Это другое ТС — продолжить
            </v-btn>
          </div>
        </v-alert>
        <v-text-field v-model="createDialog.plate" label="Гос. номер *" variant="outlined"
          density="compact" class="mb-3" :rules="[v => !!v || 'Обязательное поле']" />
        <div class="d-flex gap-3 mb-3">
          <v-text-field v-model="createDialog.brand" label="Марка" variant="outlined" density="compact" />
          <v-text-field v-model="createDialog.model" label="Модель" variant="outlined" density="compact" />
        </div>
        <v-autocomplete
          v-model="createDialog.owner_org_id"
          :items="orgsList"
          item-title="name"
          item-value="id"
          label="Владелец *"
          variant="outlined"
          density="compact"
          class="mb-3"
        />
        <v-select
          v-model="createDialog.type"
          :items="typeOptions"
          item-title="label"
          item-value="value"
          label="Тип ТС"
          variant="outlined"
          density="compact"
          class="mb-3"
          clearable
        />
        <v-select
          v-model="createDialog.state"
          :items="stateOptions"
          item-title="label"
          item-value="value"
          label="Состояние"
          variant="outlined"
          density="compact"
        />
      </v-card-text>
      <v-card-actions class="pa-5 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="close">Отмена</v-btn>
        <v-btn color="primary" variant="flat"
          :loading="createDialog.loading"
          :disabled="!createDialog.plate || !createDialog.owner_org_id"
          @click="submit">
          Создать
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'
import { useVehicleCreateDialog } from '@/composables/fleet/vehicle-list/useVehicleCreateDialog'
import type { OrgItem } from '@/composables/fleet/vehicle-list/vehicleListTypes'

defineProps<{
  modelValue: boolean
  orgsList: OrgItem[]
  typeOptions: { value: string; label: string }[]
  stateOptions: { value: string; label: string }[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'error', err: any): void
}>()

const { mobile } = useDisplay()

const { createDialog, resetCreateDialog, doCreate, onVinChange, checkVinDuplicate } = useVehicleCreateDialog({
  onError: err => emit('error', err),
})

function close() {
  resetCreateDialog()
  emit('update:modelValue', false)
}

function onDialogUpdate(value: boolean) {
  if (!value) close()
}

async function submit() {
  const ok = await doCreate()
  if (ok) emit('update:modelValue', false)
}
</script>

<style scoped></style>
