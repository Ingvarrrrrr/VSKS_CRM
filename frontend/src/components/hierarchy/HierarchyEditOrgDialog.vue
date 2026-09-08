<template>
  <Teleport to="body">
    <v-dialog v-model="show" max-width="640" :z-index="9999" scrollable :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4 text-body-1">
          <v-icon icon="mdi-domain" class="mr-2" />Редактировать организацию
        </v-card-title>
        <v-card-text class="pa-4 pt-3" style="max-height:75vh">
          <v-alert
            v-if="form.contractor_id"
            type="info" density="compact" variant="tonal" class="mb-3"
            icon="mdi-link-variant"
          >
            <span class="text-caption">
              Данные берутся из карточки контрагента. Редактируйте реквизиты в разделе «Контрагенты».
            </span>
          </v-alert>

          <v-autocomplete
            v-if="!form.contractor_id"
            v-model="editOrgContractorId"
            :items="contractors"
            item-title="name" item-value="id"
            label="Найти контрагента (привязать по ИНН)"
            prepend-inner-icon="mdi-account-search"
            variant="outlined" density="compact" clearable
            :custom-filter="contractorFilter"
            :loading="searching"
            :menu-props="{ maxWidth: 560 }"
            hint="Поиск по всей базе контрагентов (название или ИНН). Выбор привяжет организацию и заполнит реквизиты." persistent-hint
            class="mb-4"
            @update:search="emit('contractor-search', $event)"
            @update:model-value="emit('contractor-select', $event)"
          >
            <template #item="{ item, props: itemProps }">
              <v-list-item v-bind="itemProps" :title="undefined">
                <template #title>
                  <span style="white-space:normal;word-break:break-word;line-height:1.4">{{ item.raw.name }}</span>
                </template>
                <template #subtitle>
                  <span v-if="item.raw.inn" class="text-caption">ИНН: {{ item.raw.inn }}</span>
                </template>
              </v-list-item>
            </template>
          </v-autocomplete>

          <v-text-field
            v-model="form.name" label="Краткое название *"
            variant="outlined" density="compact" class="mb-2"
          />
          <v-text-field
            v-model="form.full_name" label="Полное наименование"
            variant="outlined" density="compact" class="mb-2"
            :readonly="!!form.contractor_id"
            :hint="form.contractor_id ? 'Поле берётся из контрагента' : ''"
            :persistent-hint="!!form.contractor_id"
          />

          <div class="d-flex gap-2 align-start mb-1">
            <v-text-field
              v-model="form.inn" label="ИНН"
              variant="outlined" density="compact" style="flex:1"
              hint="10 (юр.лицо) или 12 (ИП) цифр" persistent-hint
              :readonly="!!form.contractor_id"
            />
            <v-text-field
              v-model="form.kpp" label="КПП"
              variant="outlined" density="compact" style="max-width:130px" hide-details
              :readonly="!!form.contractor_id"
            />
            <v-text-field
              v-model="form.ogrn" label="ОГРН"
              variant="outlined" density="compact" style="max-width:150px" hide-details
              :readonly="!!form.contractor_id"
            />
          </div>

          <v-btn
            v-if="!form.contractor_id"
            variant="tonal" color="primary" size="small" class="mt-3 mb-2"
            prepend-icon="mdi-database-search-outline"
            :loading="egrulLoading"
            :disabled="!form.inn || form.inn.length < 10"
            @click="emit('enrich-egrul')"
          >
            Заполнить на основании ИНН из ЕГРЮЛ
          </v-btn>

          <v-alert
            v-if="egrulMessage"
            :type="egrulMessageType" density="compact" variant="tonal"
            class="mb-2 text-caption" closable
            @click:close="emit('clear-egrul-message')"
          >
            {{ egrulMessage }}
          </v-alert>

          <v-text-field
            v-model="form.address" label="Адрес"
            variant="outlined" density="compact" class="mb-2"
            :readonly="!!form.contractor_id"
          />
          <v-text-field
            v-model="form.signatory_position" label="Должность подписанта"
            variant="outlined" density="compact" class="mb-2"
            :readonly="!!form.contractor_id"
          />
          <v-row dense class="mb-2">
            <v-col cols="4">
              <v-text-field v-model="form.signatory_last_name" label="Фамилия" variant="outlined" density="compact" hide-details :readonly="!!form.contractor_id" />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="form.signatory_first_name" label="Имя" variant="outlined" density="compact" hide-details :readonly="!!form.contractor_id" />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="form.signatory_middle_name" label="Отчество" variant="outlined" density="compact" hide-details :readonly="!!form.contractor_id" />
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="show = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" @click="emit('save')">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </Teleport>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

defineProps<{
  form: {
    contractor_id: number | null
    name: string; full_name: string; inn: string; kpp: string; ogrn: string; address: string
    signatory_last_name: string; signatory_first_name: string; signatory_middle_name: string; signatory_position: string
  }
  contractors: any[]
  searching: boolean
  contractorFilter: (value: string, query: string, item?: any) => boolean
  egrulLoading: boolean
  egrulMessage: string
  egrulMessageType: 'success' | 'info' | 'error' | 'warning'
}>()
const emit = defineEmits<{
  save: []
  'enrich-egrul': []
  'clear-egrul-message': []
  'contractor-search': [query: string]
  'contractor-select': [id: number | null]
}>()
const { mobile } = useDisplay()
const show = defineModel<boolean>({ default: false })
const editOrgContractorId = defineModel<number | null>('contractorPickId', { default: null })
</script>
