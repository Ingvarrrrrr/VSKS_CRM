<template>
  <!-- ── Approver Picker Dialog ── -->
  <v-dialog v-model="docPickerOpen" max-width="560" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-account-check-outline" color="teal" class="mr-2" />
        {{ docPickerType.startsWith('service_note') ? 'Служебная записка — выбор инициатора' : 'Лист согласования — выбор согласующих' }}
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="docPickerOpen = false" />
      </v-card-title>
      <v-divider />
      <v-card-text>
        <div v-if="loadingDocApprovers" class="d-flex justify-center py-4">
          <v-progress-circular indeterminate color="teal" />
        </div>
        <div v-else-if="!docApprovers.length" class="text-center text-medium-emphasis py-4">
          Для этой субсидии не настроены согласующие.<br>
          Откройте страницу Субсидии → кнопка «Согласующие».
        </div>
        <!-- service_note: autocomplete только из подчинённых + сам пользователь
             (бизнес-правило: за другого может делать только его руководитель) -->
        <div v-else-if="docPickerType.startsWith('service_note')" class="mt-1">
          <v-autocomplete
            v-model="pickerInitiatorId"
            :items="actAsList"
            item-title="full_name"
            item-value="id"
            label="Специалист (инициатор)"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            :hint="'Доступны: вы и сотрудники, кому вы можете ставить задачи'"
            persistent-hint
            :no-data-text="loadingDocApprovers ? 'Загрузка...' : 'Нет сотрудников'"
          >
            <template #item="{ item, props }">
              <v-list-item v-bind="props">
                <template #subtitle>
                  <span v-if="item.raw.position" class="text-caption text-medium-emphasis">{{ item.raw.position }}</span>
                </template>
              </v-list-item>
            </template>
          </v-autocomplete>
        </div>
        <!-- approval_sheet: responsible person + checkboxes -->
        <div v-else>
          <!-- Ответственный исполнитель -->
          <div class="d-flex align-start gap-2 mb-4">
            <v-autocomplete
              v-model="pickerResponsibleName"
              :items="responsibleOptions"
              item-title="display"
              item-value="full_name"
              label="Ответственный исполнитель"
              variant="outlined"
              density="compact"
              clearable
              class="flex-grow-1"
              :return-object="false"
              autocomplete="off"
              hint="По умолчанию — ответственный исполнитель этой закупки. Можно выбрать другого сотрудника или запись справочника."
              persistent-hint
            />
            <v-tooltip text="Добавить в справочник" location="top">
              <template #activator="{ props: tip }">
                <v-btn v-bind="tip" icon="mdi-account-plus-outline" size="small"
                  variant="tonal" color="teal" class="mt-1" @click="$emit('add-responsible')" />
              </template>
            </v-tooltip>
          </div>
          <v-divider class="mb-3" />
          <div class="text-body-2 font-weight-medium mb-2">Согласующие</div>
          <v-checkbox
            v-for="a in docApprovers"
            :key="a.id"
            v-model="pickerApproverIds"
            :value="a.id"
            :label="`${a.order_num}. ${a.role_name} — ${a.full_name}`"
            density="compact"
            hide-details
          />
        </div>
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="text" @click="docPickerOpen = false">Отмена</v-btn>
        <v-btn
          color="teal"
          variant="tonal"
          prepend-icon="mdi-download"
          :loading="docLoading === docPickerType"
          :disabled="docPickerType.startsWith('service_note') ? !pickerInitiatorId : !pickerApproverIds.length"
          @click="$emit('download')"
        >
          Скачать
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Phase 27.2-02: Диалог выбора закрывающих документов перед скачиванием СЗ -->
  <v-dialog v-model="acceptanceOpen" max-width="520" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-file-check-outline" color="teal" class="mr-2" />
        Выберите закрывающие документы
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="acceptanceOpen = false" />
      </v-card-title>
      <v-divider />
      <v-card-text>
        <p class="text-body-2 text-medium-emphasis mb-3">
          Отметьте документы, по которым формируется служебная записка на оплату.
          Сумма будет сложена автоматически.
        </p>
        <v-list density="compact">
          <v-list-item v-for="(doc, idx) in acceptanceDocs" :key="idx">
            <template #prepend>
              <v-checkbox-btn v-model="acceptanceSelected" :value="idx" />
            </template>
            <v-list-item-title class="text-body-2">
              {{ doc.name }} {{ doc.number }} от {{ doc.date || '—' }}
            </v-list-item-title>
            <v-list-item-subtitle v-if="doc.amount != null">
              {{ Number(doc.amount).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }} ₽
            </v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="text" @click="acceptanceOpen = false">Отмена</v-btn>
        <v-btn
          color="teal"
          variant="tonal"
          prepend-icon="mdi-download"
          :disabled="!acceptanceSelected.length"
          @click="$emit('confirm-acceptance')"
        >
          Скачать
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

const docPickerOpen = defineModel<boolean>('docPickerOpen', { default: false })
const acceptanceOpen = defineModel<boolean>('acceptanceOpen', { default: false })
const pickerInitiatorId = defineModel<number | null>('pickerInitiatorId', { default: null })
const pickerResponsibleName = defineModel<string>('pickerResponsibleName', { default: '' })
const pickerApproverIds = defineModel<number[]>('pickerApproverIds', { default: () => [] })
const acceptanceSelected = defineModel<number[]>('acceptanceSelected', { default: () => [] })

defineProps<{
  docPickerType: string
  loadingDocApprovers: boolean
  docApprovers: { id: number; role_name: string; full_name: string; order_num: number; is_default: boolean; can_initiate: boolean }[]
  actAsList: { id: number; full_name: string; position?: string | null }[]
  responsibleOptions: any[]
  docLoading: string | null
  acceptanceDocs: { name: string; number: string; date: string; amount: number | null }[]
}>()

defineEmits<{
  (e: 'download'): void
  (e: 'confirm-acceptance'): void
  (e: 'add-responsible'): void
}>()

const { mobile } = useDisplay()
</script>
