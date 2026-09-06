<template>
  <!-- Add contractor inline dialog -->
  <v-dialog v-model="open" max-width="700" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4">
        <v-icon icon="mdi-account-plus" class="mr-2" />Новый контрагент
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <!-- Import from file -->
        <div class="mb-4 pa-3 rounded" style="background:rgba(0,0,0,0.03)">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
            <div class="text-body-2">
              <strong>Форматы:</strong> Excel (.xlsx, .xls), Word (.docx), PDF<br>
              <strong>Данные:</strong> система автоматически извлечёт реквизиты из карточки контрагента
            </div>
          </v-alert>
          <FileDropZone v-model="importFile" accept=".xlsx,.xls,.pdf,.docx,.doc"
            hint="Excel, Word, PDF — перетащите или нажмите" class="mb-2" />
          <v-btn v-if="importFile" variant="tonal" color="primary" size="small" :loading="importing"
            @click="$emit('import-from-file')">Заполнить поля из файла</v-btn>
        </div>
        <v-select v-model="form.org_type" :items="['Юридическое лицо', 'ИП', 'Самозанятый', 'Физическое лицо']"
          label="Тип организации" variant="outlined" density="compact" class="mb-3" />
        <v-text-field v-model="form.name" label="Наименование организации *" variant="outlined" density="compact" class="mb-3"
          :rules="[v => !!v || 'Обязательное поле']" />
        <v-row dense>
          <v-col cols="4">
            <v-text-field v-model="form.inn" label="ИНН" variant="outlined" density="compact" hide-details
              @update:model-value="$emit('inn-change', $event)">
              <template #append-inner>
                <v-btn icon="mdi-database-search" size="x-small" variant="text" color="blue" :disabled="!form.inn || form.inn.length < 10" @click="$emit('lookup-inn')" title="Заполнить из ЕГРЮЛ (nalog.ru)" />
              </template>
            </v-text-field>
          </v-col>
          <v-col cols="4">
            <v-text-field v-model="form.kpp" label="КПП" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="4">
            <v-text-field v-model="form.ogrn" label="ОГРН" variant="outlined" density="compact" hide-details />
          </v-col>
        </v-row>
        <v-textarea v-model="form.address" label="Адрес местонахождения" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
        <div class="text-caption text-medium-emphasis mt-4 mb-1">Подписант</div>
        <v-text-field v-model="form.signatory_position" label="Должность подписанта" variant="outlined" density="compact" class="mb-2" hide-details />
        <v-row dense class="mb-3">
          <v-col cols="4">
            <v-text-field v-model="form.signatory_last_name" label="Фамилия" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="4">
            <v-text-field v-model="form.signatory_first_name" label="Имя" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="4">
            <v-text-field v-model="form.signatory_middle_name" label="Отчество" variant="outlined" density="compact" hide-details />
          </v-col>
        </v-row>
        <div class="text-caption text-medium-emphasis mt-3 mb-1">Контакты</div>
        <v-row dense>
          <v-col cols="6">
            <v-text-field v-model="form.phone" label="Телефон контактного лица" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="6">
            <v-text-field v-model="form.email" label="Email контактного лица" variant="outlined" density="compact" hide-details />
          </v-col>
        </v-row>
        <v-text-field v-model="form.contact_person" label="Контактное лицо" variant="outlined" density="compact" class="mt-3" hide-details />
        <div class="text-caption text-medium-emphasis mt-4 mb-1">Банковские реквизиты</div>
        <v-text-field v-model="form.settlement_account" label="Расчётный счёт (р/с)" variant="outlined" density="compact" class="mb-3" hide-details />
        <v-text-field v-model="form.bank_name" label="Банк (наименование)" variant="outlined" density="compact" class="mb-3" hide-details />
        <v-row dense>
          <v-col cols="6">
            <v-text-field v-model="form.bik" label="БИК" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="6">
            <v-text-field v-model="form.correspondent_account" label="Корр. счёт (к/с)" variant="outlined" density="compact" hide-details />
          </v-col>
        </v-row>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="open = false">Отмена</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!form.name.trim()" @click="$emit('save')">Добавить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

const open = defineModel<boolean>({ default: false })
const importFile = defineModel<File | null>('file', { default: null })

defineProps<{
  form: {
    name: string; inn: string; kpp: string; ogrn: string; address: string; phone: string; email: string
    contact_person: string; signatory_last_name: string; signatory_first_name: string; signatory_middle_name: string
    signatory_position: string; org_type: string
    bank_name: string; bik: string; settlement_account: string; correspondent_account: string
  }
  saving: boolean
  importing: boolean
}>()

defineEmits<{
  (e: 'save'): void
  (e: 'import-from-file'): void
  (e: 'lookup-inn'): void
  (e: 'inn-change', val: string): void
}>()

const { mobile } = useDisplay()
</script>
