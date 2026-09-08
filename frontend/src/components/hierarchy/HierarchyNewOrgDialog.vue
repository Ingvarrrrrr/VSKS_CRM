<template>
  <v-dialog v-model="show" max-width="640" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4">
        <v-icon icon="mdi-domain" color="deep-purple" class="mr-2" />
        Новая организация
      </v-card-title>
      <v-card-text class="pa-4 pt-3" style="max-height:75vh">
        <!-- 2026-09-01: суперадмин один вправе выбрать, в какой АККАУНТ уходит
             новая организация — иначе она рискует остаться «ничейной» (см. баг
             с региональными отделениями ВСКС). account_owner ничего не видит:
             аккаунт и так его собственный. -->
        <v-select
          v-if="isSuperadmin"
          v-model="accountId"
          :items="accountOptions"
          item-title="name" item-value="id"
          label="Аккаунт (головная организация)"
          hint="Куда привязать новую организацию. Не выбрано — уйдёт в ваш собственный аккаунт."
          persistent-hint
          clearable
          variant="outlined" density="compact" class="mb-4"
          prepend-inner-icon="mdi-domain"
        />
        <v-autocomplete
          v-model="contractorId"
          :items="contractors"
          item-title="name" item-value="id"
          label="Выбрать из существующих контрагентов"
          prepend-inner-icon="mdi-account-search"
          variant="outlined" density="compact" clearable
          :custom-filter="contractorFilter"
          :loading="searching"
          :menu-props="{ maxWidth: 560 }"
          hint="Поиск по всей базе контрагентов (название или ИНН). Выбор заполнит поля ниже." persistent-hint
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
          v-model="form.name"
          label="Краткое название *"
          prepend-inner-icon="mdi-domain"
          variant="outlined" density="compact" class="mb-2"
        />
        <v-text-field
          v-model="form.full_name"
          label="Полное наименование"
          variant="outlined" density="compact" class="mb-2"
        />

        <div class="d-flex gap-2 align-start mb-1">
          <v-text-field
            v-model="form.inn" label="ИНН"
            variant="outlined" density="compact" style="flex:1"
            hint="10 (юр.лицо) или 12 (ИП) цифр" persistent-hint
          />
          <v-text-field
            v-model="form.kpp" label="КПП"
            variant="outlined" density="compact" style="max-width:130px" hide-details
          />
          <v-text-field
            v-model="form.ogrn" label="ОГРН"
            variant="outlined" density="compact" style="max-width:150px" hide-details
          />
        </div>

        <v-btn
          variant="tonal" color="deep-purple" size="small" class="mt-3 mb-2"
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
        />
        <v-text-field
          v-model="form.signatory_position" label="Должность подписанта"
          variant="outlined" density="compact" class="mb-2"
        />
        <v-row dense class="mb-2">
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
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn color="deep-purple" variant="flat" :disabled="!form.name.trim()" :loading="form.loading" @click="emit('create')">Создать</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

defineProps<{
  form: {
    loading: boolean
    name: string; full_name: string; inn: string; kpp: string; ogrn: string; address: string
    signatory_last_name: string; signatory_first_name: string; signatory_middle_name: string; signatory_position: string
  }
  isSuperadmin: boolean
  accountOptions: { id: number; name: string }[]
  contractors: any[]
  searching: boolean
  contractorFilter: (value: string, query: string, item?: any) => boolean
  egrulLoading: boolean
  egrulMessage: string
  egrulMessageType: 'success' | 'info' | 'error' | 'warning'
}>()
const emit = defineEmits<{
  create: []
  'enrich-egrul': []
  'clear-egrul-message': []
  'contractor-search': [query: string]
  'contractor-select': [id: number | null]
}>()
const { mobile } = useDisplay()
const show = defineModel<boolean>({ default: false })
const accountId = defineModel<number | null>('accountId', { default: null })
const contractorId = defineModel<number | null>('contractorId', { default: null })
</script>
