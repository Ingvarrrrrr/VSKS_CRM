<template>
  <!-- ── Contractor Override Dialog ── -->
  <v-dialog v-model="visible" max-width="640" scrollable :fullscreen="mobile">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-account-edit-outline" color="teal" class="mr-2" />
        Реквизиты контрагента для субсидии
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="visible = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4" style="max-height:75vh">
        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          Эти реквизиты будут использоваться при генерации документов для данной субсидии.
          Если не заполнены — берутся из основной карточки контрагента.
        </v-alert>

        <div class="section-label">Основные данные</div>
        <v-select v-model="overrideForm.org_type" :items="['Юр.лицо','ИП','Самозанятый','Физ.лицо']"
          label="Форма организации" variant="outlined" density="compact" clearable hide-details class="mb-3" />
        <v-row dense>
          <v-col cols="4">
            <v-text-field v-model="overrideForm.inn" label="ИНН" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="4">
            <v-text-field v-model="overrideForm.kpp" label="КПП" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="4">
            <v-text-field v-model="overrideForm.ogrn" label="ОГРН" variant="outlined" density="compact" hide-details />
          </v-col>
        </v-row>
        <v-textarea v-model="overrideForm.address" label="Адрес местонахождения" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
        <v-textarea v-model="overrideForm.postal_address" label="Почтовый адрес" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />

        <div class="section-label mt-4">Подписант</div>
        <v-text-field v-model="overrideForm.signatory_position" label="Должность подписанта" variant="outlined" density="compact" class="mb-2" hide-details />
        <v-row dense class="mb-3">
          <v-col cols="4">
            <v-text-field v-model="overrideForm.signatory_last_name" label="Фамилия" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="4">
            <v-text-field v-model="overrideForm.signatory_first_name" label="Имя" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="4">
            <v-text-field v-model="overrideForm.signatory_middle_name" label="Отчество" variant="outlined" density="compact" hide-details />
          </v-col>
        </v-row>
        <v-text-field v-model="overrideForm.signatory_basis" label="На основании чего действует" variant="outlined" density="compact" hide-details
          placeholder="Устава, доверенности №..." />

        <div class="section-label mt-4">Контакты</div>
        <v-row dense class="mb-3">
          <v-col cols="6">
            <v-text-field v-model="overrideForm.org_phone" label="Телефон организации" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="6">
            <v-text-field v-model="overrideForm.org_email" label="Email организации" variant="outlined" density="compact" hide-details />
          </v-col>
        </v-row>
        <v-text-field v-model="overrideForm.contact_person" label="Контактное лицо" variant="outlined" density="compact" class="mb-3" hide-details />
        <v-row dense>
          <v-col cols="6">
            <v-text-field v-model="overrideForm.phone" label="Телефон контактного лица" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="6">
            <v-text-field v-model="overrideForm.email" label="Email контактного лица" variant="outlined" density="compact" hide-details />
          </v-col>
        </v-row>

        <div class="section-label mt-4">Банковские реквизиты</div>
        <v-text-field v-model="overrideForm.settlement_account" label="Расчётный счёт (р/с)" variant="outlined" density="compact" class="mb-3" hide-details maxlength="20" />
        <v-text-field v-model="overrideForm.bank_name" label="Банк (наименование)" variant="outlined" density="compact" class="mb-3" hide-details
          placeholder="в ПАО «Сбербанк»..." />
        <v-row dense>
          <v-col cols="6">
            <v-text-field v-model="overrideForm.bik" label="БИК" variant="outlined" density="compact" hide-details maxlength="9" />
          </v-col>
          <v-col cols="6">
            <v-text-field v-model="overrideForm.correspondent_account" label="Корр. счёт (к/с)" variant="outlined" density="compact" hide-details maxlength="20" />
          </v-col>
        </v-row>
        <v-textarea v-model="overrideForm.bank_details" label="Банковские реквизиты (свободное поле)" variant="outlined" density="compact" rows="2" class="mt-3" hide-details />
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="visible = false">Отмена</v-btn>
        <v-btn color="teal" :loading="savingOverride" @click="saveContractorOverride">Сохранить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import type { SubsidyRow } from '@/composables/subsidies/types'

const visible = defineModel<boolean>({ default: false })

const { mobile } = useDisplay()
const toast = useToast()
function showSnack(text: string, color: ToastType = 'success', opts?: { actionText?: string; onAction?: () => void; duration?: number }) {
  toast.addToast(text, color, opts)
}

const savingOverride = ref(false)
const overrideSubsidyId = ref<number | null>(null)
const overrideForm = ref({
  org_type: '', inn: '', kpp: '', ogrn: '',
  signatory_last_name: '', signatory_first_name: '', signatory_middle_name: '', signatory_position: '',
  signatory_basis: '', address: '', postal_address: '',
  contact_person: '', phone: '', email: '', org_phone: '', org_email: '',
  bank_details: '', settlement_account: '', bank_name: '', bik: '', correspondent_account: '',
})

async function open(s: SubsidyRow) {
  if (!s.contractor_id) return
  overrideSubsidyId.value = s.id
  try {
    const data = await apiFetch<any>(`/subsidies/${s.id}/contractor-override`)
    overrideForm.value = {
      org_type: data.org_type || '',
      inn: data.inn || '',
      kpp: data.kpp || '',
      ogrn: data.ogrn || '',
      signatory_last_name: data.signatory_last_name || '',
      signatory_first_name: data.signatory_first_name || '',
      signatory_middle_name: data.signatory_middle_name || '',
      signatory_position: data.signatory_position || '',
      signatory_basis: data.signatory_basis || '',
      address: data.address || '',
      postal_address: data.postal_address || '',
      contact_person: data.contact_person || '',
      phone: data.phone || '',
      email: data.email || '',
      org_phone: data.org_phone || '',
      org_email: data.org_email || '',
      bank_details: data.bank_details || '',
      settlement_account: data.settlement_account || '',
      bank_name: data.bank_name || '',
      bik: data.bik || '',
      correspondent_account: data.correspondent_account || '',
    }
    visible.value = true
  } catch {
    showSnack('Ошибка загрузки реквизитов', 'error')
  }
}

async function saveContractorOverride() {
  if (!overrideSubsidyId.value) return
  savingOverride.value = true
  try {
    await apiFetch(`/subsidies/${overrideSubsidyId.value}/contractor-override`, {
      method: 'PUT',
      body: JSON.stringify(overrideForm.value),
    })
    visible.value = false
    showSnack('Реквизиты сохранены')
  } catch (e: any) {
    console.error('upsertContractorOverride failed:', e)
    showSnack('Ошибка сохранения', 'error')
  } finally {
    savingOverride.value = false
  }
}

defineExpose({ open })
</script>
