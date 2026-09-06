<template>
  <!-- Phase 21: Manual receipt dialog -->
  <v-dialog v-model="dialog.show" max-width="700" :fullscreen="mobile">
    <v-card>
      <v-card-title>Чек — ручной ввод</v-card-title>
      <v-card-text>
        <v-row dense>
          <v-col cols="12" md="6">
            <v-text-field v-model="dialog.form.fiscal_drive_number"
              label="ФН (fiscal_drive_number)" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12" md="3">
            <v-text-field v-model.number="dialog.form.fiscal_document_number"
              label="ФД" type="number" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12" md="3">
            <v-text-field v-model="dialog.form.fiscal_sign"
              label="ФП" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field v-model="dialog.form.receipt_datetime"
              label="Дата/время" type="datetime-local" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field v-model.number="dialog.form.total_sum"
              label="Сумма, ₽" type="number" variant="outlined" density="compact" suffix="₽" />
          </v-col>
          <v-col cols="12" md="8">
            <v-text-field v-model="dialog.form.seller_name"
              label="Продавец" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field v-model="dialog.form.seller_inn"
              label="ИНН продавца" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="12">
            <v-text-field v-model="dialog.form.retail_place"
              label="Место расчётов" variant="outlined" density="compact" />
          </v-col>
        </v-row>
        <div v-if="dialog.error" class="text-error text-caption mt-2">
          {{ dialog.error }}
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="dialog.show = false">Отмена</v-btn>
        <v-btn color="primary" variant="tonal" :loading="dialog.saving"
          @click="$emit('save')">Сохранить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

defineProps<{
  dialog: {
    show: boolean
    saving: boolean
    error: string
    form: {
      fiscal_drive_number: string
      fiscal_document_number: number | null
      fiscal_sign: string
      receipt_datetime: string
      total_sum: number | null
      seller_name: string
      seller_inn: string
      retail_place: string
    }
  }
}>()

defineEmits<{ (e: 'save'): void }>()

const { mobile } = useDisplay()
</script>
