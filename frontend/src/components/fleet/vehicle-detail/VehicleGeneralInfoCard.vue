<!-- Основные данные (inline-edit) — карточка «Общее» карточки ТС. -->
<template>
  <v-card class="vp-box mb-4">
    <v-card-title class="vp-box__title">
      <v-icon icon="mdi-car-info" size="small" class="mr-2" />
      Основные данные
    </v-card-title>
    <v-card-text class="pa-0">
      <div class="vp-data-grid">
        <!-- Гос. номер -->
        <div class="vp-data-row" v-if="isFieldVisible('plate')">
          <span class="vp-data-key">
            <FieldLabel label="Гос. номер" field-key="plate" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <LicensePlate v-model="form.plate" :readonly="false" />
          </span>
        </div>
        <!-- VIN -->
        <div class="vp-data-row" v-if="isFieldVisible('vin')">
          <span class="vp-data-key">
            <FieldLabel label="VIN" field-key="vin" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-text-field v-model="form.vin" variant="underlined" density="compact" hide-details class="vp-inline-field vp-mono-field" placeholder="—" />
          </span>
        </div>
        <!-- Марка -->
        <div class="vp-data-row" v-if="isFieldVisible('brand')">
          <span class="vp-data-key">
            <FieldLabel label="Марка" field-key="brand" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-combobox v-model="form.brand" :items="brandSuggestions" variant="underlined" density="compact" hide-details clearable auto-select-first :return-object="false" class="vp-inline-field" placeholder="—" />
          </span>
        </div>
        <!-- Модель -->
        <div class="vp-data-row" v-if="isFieldVisible('model')">
          <span class="vp-data-key">
            <FieldLabel label="Модель" field-key="model" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-combobox v-model="form.model" :items="filteredModelSuggestions" variant="underlined" density="compact" hide-details clearable auto-select-first :return-object="false" class="vp-inline-field" placeholder="—" />
          </span>
        </div>
        <!-- Год -->
        <div class="vp-data-row" v-if="isFieldVisible('year_of_manufacture')">
          <span class="vp-data-key">
            <FieldLabel label="Год выпуска" field-key="year_of_manufacture" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-combobox v-model="form.year_of_manufacture" :items="yearOptions" variant="underlined" density="compact" hide-details clearable auto-select-first :return-object="false" class="vp-inline-field" placeholder="—" />
          </span>
        </div>
        <!-- Цвет -->
        <div class="vp-data-row" v-if="isFieldVisible('color')">
          <span class="vp-data-key">
            <FieldLabel label="Цвет" field-key="color" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-combobox v-model="form.color" :items="colorSuggestions" variant="underlined" density="compact" hide-details clearable auto-select-first :return-object="false" class="vp-inline-field" placeholder="—" />
          </span>
        </div>
        <!-- Тип ТС -->
        <div class="vp-data-row" v-if="isFieldVisible('type')">
          <span class="vp-data-key">
            <FieldLabel label="Тип ТС" field-key="type" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-select v-model="form.type" :items="typeOptions" item-title="label" item-value="value" variant="underlined" density="compact" hide-details clearable class="vp-inline-field" placeholder="—" />
          </span>
        </div>
        <!-- Кузов -->
        <div class="vp-data-row" v-if="isFieldVisible('body_type')">
          <span class="vp-data-key">
            <FieldLabel label="Кузов" field-key="body_type" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-select v-model="form.body_type" :items="bodyTypeOptions" variant="underlined" density="compact" hide-details clearable class="vp-inline-field" placeholder="—" />
          </span>
        </div>
        <!-- Категория ТС по ПТС -->
        <div class="vp-data-row" v-if="isFieldVisible('pts_category')">
          <span class="vp-data-key">
            <FieldLabel label="Категория ТС по ПТС" field-key="pts_category" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-combobox v-model="form.pts_category" :items="ptsCategoryOptions" variant="underlined" density="compact" hide-details clearable auto-select-first :return-object="false" class="vp-inline-field" placeholder="—" />
          </span>
        </div>
        <!-- Состояние -->
        <div class="vp-data-row" v-if="isFieldVisible('state')">
          <span class="vp-data-key">
            <FieldLabel label="Состояние" field-key="state" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-select v-model="form.state" :items="stateOptions" item-title="label" item-value="value" variant="underlined" density="compact" hide-details clearable class="vp-inline-field" placeholder="—" />
          </span>
        </div>
        <!-- Организация-владелец. Длинные юрлица-названия (Донецкое
             региональное отделение...) зажимаем в 2 строки —
             тот же приём, что и в VehicleListView.vue (.vl-clamp-2),
             полное название — во всплывающей подсказке. -->
        <div class="vp-data-row" v-if="isFieldVisible('owner_org_id')">
          <span class="vp-data-key">
            <FieldLabel label="Владелец" field-key="owner_org_id" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-tooltip :text="ownerOrgFullName" location="top" :disabled="!ownerOrgFullName">
              <template #activator="{ props: tip }">
                <v-autocomplete
                  v-bind="tip"
                  :model-value="ownerOrgUid"
                  :items="ownerOrgOptions"
                  item-title="name" item-value="uid"
                  :custom-filter="ownerAutofill.customFilter"
                  :loading="contractorsStore.searching"
                  variant="underlined" density="compact" hide-details clearable
                  class="vp-inline-field vp-org-field" placeholder="—"
                  @update:search="ownerAutofill.search"
                  @update:model-value="$emit('owner-org-select', $event)"
                >
                  <template #item="{ item, props: itemProps }">
                    <v-list-item v-bind="itemProps" :title="undefined">
                      <template #title>
                        <span style="white-space:normal;word-break:break-word;line-height:1.4">{{ item.raw.name }}</span>
                      </template>
                      <template #subtitle>
                        <span class="text-caption">
                          <template v-if="item.raw.inn">ИНН: {{ item.raw.inn }}</template>
                          <template v-if="item.raw.kind === 'contractor'">{{ item.raw.inn ? ' · ' : '' }}контрагент{{ item.raw.inn ? '' : ' (без организации в аккаунте)' }}</template>
                        </span>
                      </template>
                    </v-list-item>
                  </template>
                </v-autocomplete>
              </template>
            </v-tooltip>
          </span>
        </div>
        <!-- Эксплуатант -->
        <div class="vp-data-row" v-if="isFieldVisible('assigned_org_id')">
          <span class="vp-data-key">
            <FieldLabel label="Эксплуатант" field-key="assigned_org_id" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-tooltip v-if="form.assigned_org_id || assignedOrgItemsCount > 0" :text="assignedOrgFullName" location="top" :disabled="!assignedOrgFullName">
              <template #activator="{ props: tip }">
                <v-autocomplete
                  v-bind="tip"
                  :model-value="assignedOrgUid"
                  :items="assignedOrgOptions"
                  item-title="name" item-value="uid"
                  :custom-filter="assignedAutofill.customFilter"
                  :loading="contractorsStore.searching"
                  variant="underlined" density="compact" hide-details clearable
                  class="vp-inline-field vp-org-field" placeholder="—"
                  @update:search="assignedAutofill.search"
                  @update:model-value="$emit('assigned-org-select', $event)"
                >
                  <template #item="{ item, props: itemProps }">
                    <v-list-item v-bind="itemProps" :title="undefined">
                      <template #title>
                        <span style="white-space:normal;word-break:break-word;line-height:1.4">{{ item.raw.name }}</span>
                      </template>
                      <template #subtitle>
                        <span class="text-caption">
                          <template v-if="item.raw.inn">ИНН: {{ item.raw.inn }}</template>
                          <template v-if="item.raw.kind === 'contractor'">{{ item.raw.inn ? ' · ' : '' }}контрагент{{ item.raw.inn ? '' : ' (без организации в аккаунте)' }}</template>
                        </span>
                      </template>
                    </v-list-item>
                  </template>
                </v-autocomplete>
              </template>
            </v-tooltip>
            <v-combobox v-else v-model="form.assigned_text" :items="assignedTextSuggestions" variant="underlined" density="compact" hide-details clearable auto-select-first :return-object="false" class="vp-inline-field" placeholder="—" />
          </span>
        </div>
        <!-- Эксплуатант текст если нет org_id -->
        <div class="vp-data-row" v-if="isFieldVisible('assigned_org_id') && !form.assigned_org_id">
          <span class="vp-data-key">
            <span class="text-caption text-medium-emphasis">Эксплуатант (текст)</span>
          </span>
          <span class="vp-data-val">
            <v-combobox v-model="form.assigned_text" :items="assignedTextSuggestions" variant="underlined" density="compact" hide-details clearable auto-select-first :return-object="false" class="vp-inline-field" placeholder="—" />
          </span>
        </div>
        <!-- ИНН эксплуатанта (computed, readonly) -->
        <div class="vp-data-row" v-if="isFieldVisible('operator_inn')">
          <span class="vp-data-key">
            <span class="text-caption text-medium-emphasis d-flex align-center">
              ИНН эксплуатанта
              <FieldHint field-key="operator_inn" />
              <v-chip size="x-small" variant="tonal" color="grey" class="ml-2">не редактируется</v-chip>
            </span>
          </span>
          <span class="vp-data-val">
            <v-text-field :model-value="operatorInnDisplay || '—'" variant="underlined" density="compact" hide-details readonly class="vp-inline-field text-medium-emphasis" />
          </span>
        </div>
        <!-- Место нахождения — город -->
        <div class="vp-data-row" v-if="isFieldVisible('location_city')">
          <span class="vp-data-key">
            <FieldLabel label="Место нахождения, город" field-key="location_city" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-combobox
              v-model="form.location_city"
              :items="locationCityItems"
              no-filter
              @update:search="$emit('update:location-city-search', $event)"
              variant="underlined" density="compact" hide-details clearable
              :return-object="false" class="vp-inline-field" placeholder="—"
            />
          </span>
        </div>
        <!-- Место нахождения — адрес -->
        <div class="vp-data-row" v-if="isFieldVisible('location_address')">
          <span class="vp-data-key">
            <FieldLabel label="Место нахождения, адрес" field-key="location_address" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-text-field v-model="form.location_address" variant="underlined" density="compact" hide-details class="vp-inline-field" placeholder="—" />
          </span>
        </div>
        <!-- Место постоянной приписки ТС (доделка 2026-09) — то же
             автодополнение по справочнику городов, что и «Текущее
             место нахождения» выше; свободный ввод разрешён. -->
        <div class="vp-data-row" v-if="isFieldVisible('home_base_city')">
          <span class="vp-data-key">
            <FieldLabel label="Место постоянной приписки ТС" field-key="home_base_city" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-combobox
              v-model="form.home_base_city"
              :items="homeBaseCityItems"
              no-filter
              @update:search="$emit('update:home-base-city-search', $event)"
              variant="underlined" density="compact" hide-details clearable
              :return-object="false" class="vp-inline-field" placeholder="—"
            />
          </span>
        </div>
        <!-- Ответственный (ФИО) -->
        <div class="vp-data-row" v-if="isFieldVisible('responsible_name')">
          <span class="vp-data-key">
            <FieldLabel label="Ответственный (ФИО)" field-key="responsible_name" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-text-field v-model="form.responsible_name" variant="underlined" density="compact" hide-details class="vp-inline-field" placeholder="—" />
          </span>
        </div>
        <!-- Основание -->
        <div class="vp-data-row" v-if="isFieldVisible('assignment_basis')">
          <span class="vp-data-key">
            <FieldLabel label="Основание" field-key="assignment_basis" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-combobox v-model="form.assignment_basis" :items="basisSuggestions" variant="underlined" density="compact" hide-details clearable auto-select-first :return-object="false" class="vp-inline-field" placeholder="Договор аренды, акт п/п..." />
          </span>
        </div>
        <!-- № документа основания права эксплуатации -->
        <div class="vp-data-row" v-if="isFieldVisible('assignment_doc_number')">
          <span class="vp-data-key">
            <FieldLabel label="№ документа основания" field-key="assignment_doc_number" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-text-field v-model="form.assignment_doc_number" variant="underlined" density="compact" hide-details class="vp-inline-field" placeholder="—" />
          </span>
        </div>
        <!-- Дата документа основания права эксплуатации -->
        <div class="vp-data-row" v-if="isFieldVisible('assignment_doc_date')">
          <span class="vp-data-key">
            <FieldLabel label="Дата документа основания" field-key="assignment_doc_date" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-text-field v-model="form.assignment_doc_date" type="date" variant="underlined" density="compact" hide-details class="vp-inline-field" />
          </span>
        </div>
        <!-- Дата регистрации -->
        <div class="vp-data-row" v-if="isFieldVisible('registered_at')">
          <span class="vp-data-key">
            <FieldLabel label="Дата регистрации" field-key="registered_at" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-text-field v-model="form.registered_at" type="date" variant="underlined" density="compact" hide-details class="vp-inline-field" />
          </span>
        </div>
      </div>

      <!-- Комментарий к изменению -->
      <div class="px-4 pb-3 mt-1">
        <v-text-field
          v-model="historyComment"
          label="Комментарий к изменению (необязательно)"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          prepend-inner-icon="mdi-comment-edit-outline"
        />
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import FieldLabel from './FieldLabel.vue'
import FieldHint from './FieldHint.vue'
import type { VehicleForm } from '@/composables/fleet/vehicleDetailTypes'

defineProps<{
  form: VehicleForm
  vehicleId: number
  isFieldVisible: (key: string) => boolean

  brandSuggestions: string[]
  filteredModelSuggestions: string[]
  yearOptions: number[]
  colorSuggestions: string[]
  typeOptions: { value: string; label: string }[]
  bodyTypeOptions: string[]
  ptsCategoryOptions: string[]
  stateOptions: { value: string; label: string }[]
  assignedTextSuggestions: string[]
  basisSuggestions: string[]

  ownerOrgFullName: string
  ownerOrgUid: string | null
  ownerOrgOptions: any[]
  ownerAutofill: { customFilter: any; search: (q: string) => void }
  contractorsStore: { searching: boolean }

  assignedOrgFullName: string
  assignedOrgItemsCount: number
  assignedOrgUid: string | null
  assignedOrgOptions: any[]
  assignedAutofill: { customFilter: any; search: (q: string) => void }

  operatorInnDisplay: string | null
  locationCityItems: string[]
  homeBaseCityItems: string[]
}>()

defineEmits<{
  (e: 'owner-org-select', uid: string | null): void
  (e: 'assigned-org-select', uid: string | null): void
  (e: 'update:location-city-search', v: string): void
  (e: 'update:home-base-city-search', v: string): void
}>()

const historyComment = defineModel<string>('historyComment', { default: '' })
</script>
