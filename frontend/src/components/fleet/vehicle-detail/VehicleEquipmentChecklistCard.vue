<!-- Чек-лист оборудования + доп. параметры — карточка «Общее» карточки ТС. -->
<template>
  <v-card class="vp-box mb-4">
    <v-card-title class="vp-box__title">
      <v-icon icon="mdi-clipboard-check-outline" size="small" class="mr-2" />
      Чек-лист оборудования
    </v-card-title>
    <v-card-text>
      <div class="vp-check-grid">
        <div v-if="isFieldVisible('has_tracker')" class="vp-check-item" :class="form.has_tracker ? 'vp-check-item--ok' : 'vp-check-item--off'">
          <v-checkbox v-model="form.has_tracker" label="Трекер" density="compact" hide-details color="success" />
        </div>
        <div v-if="isFieldVisible('akb_ok')" class="vp-check-item" :class="form.akb_ok ? 'vp-check-item--ok' : 'vp-check-item--off'">
          <v-checkbox v-model="form.akb_ok" label="АКБ исправен" density="compact" hide-details color="success" />
        </div>
        <div v-if="isFieldVisible('has_radio')" class="vp-check-item" :class="form.has_radio ? 'vp-check-item--ok' : 'vp-check-item--off'">
          <v-checkbox v-model="form.has_radio" label="Радиостанция" density="compact" hide-details color="success" />
        </div>
        <div v-if="isFieldVisible('mirrors_ok')" class="vp-check-item" :class="form.mirrors_ok ? 'vp-check-item--ok' : 'vp-check-item--off'">
          <v-checkbox v-model="form.mirrors_ok" label="Зеркала OK" density="compact" hide-details color="success" />
        </div>
        <div v-if="isFieldVisible('has_mirrors')" class="vp-check-item" :class="form.has_mirrors ? 'vp-check-item--ok' : 'vp-check-item--off'">
          <v-checkbox v-model="form.has_mirrors" label="Наличие зеркал" density="compact" hide-details color="success" />
        </div>
        <div v-if="isFieldVisible('has_keys')" class="vp-check-item" :class="form.has_keys ? 'vp-check-item--ok' : 'vp-check-item--off'">
          <v-checkbox v-model="form.has_keys" label="Ключи" density="compact" hide-details color="success" />
        </div>
        <div v-if="isFieldVisible('has_first_aid_kit')" class="vp-check-item" :class="form.has_first_aid_kit ? 'vp-check-item--ok' : 'vp-check-item--off'">
          <v-checkbox v-model="form.has_first_aid_kit" label="Аптечка" density="compact" hide-details color="success" />
        </div>
        <div v-if="isFieldVisible('has_spare_wheel')" class="vp-check-item" :class="form.has_spare_wheel ? 'vp-check-item--ok' : 'vp-check-item--off'">
          <v-checkbox v-model="form.has_spare_wheel" label="Зап. колесо" density="compact" hide-details color="success" />
        </div>
        <div v-if="isFieldVisible('has_spare_tires')" class="vp-check-item" :class="form.has_spare_tires ? 'vp-check-item--ok' : 'vp-check-item--off'">
          <v-checkbox v-model="form.has_spare_tires" label="Сменная резина" density="compact" hide-details color="success" />
        </div>
        <div v-if="isFieldVisible('has_extinguisher')" class="vp-check-item" :class="form.has_extinguisher ? 'vp-check-item--ok' : 'vp-check-item--off'">
          <v-checkbox v-model="form.has_extinguisher" label="Огнетушитель" density="compact" hide-details color="success" />
        </div>
        <div v-if="isFieldVisible('has_tachograph')" class="vp-check-item" :class="form.has_tachograph ? 'vp-check-item--ok' : 'vp-check-item--off'">
          <v-checkbox v-model="form.has_tachograph" label="Тахограф" density="compact" hide-details color="success" />
        </div>
        <div v-if="isFieldVisible('repair_required')" class="vp-check-item" :class="form.repair_required ? 'vp-check-item--off' : 'vp-check-item--ok'">
          <v-checkbox v-model="form.repair_required" label="Требуется ремонт" density="compact" hide-details color="error" />
        </div>
      </div>

      <!-- Доп. параметры -->
      <v-divider class="my-3" />
      <div class="text-subtitle-2 font-weight-bold mb-2">Доп. параметры</div>
      <v-row dense>
        <v-col v-if="isFieldVisible('props_tires_type')" cols="6">
          <div class="text-caption text-medium-emphasis mb-1 d-flex align-center">
            <span>Авторезина</span>
            <FieldHint field-key="tires_type" />
          </div>
          <v-select v-model="form.props_tires_type" :items="tiresTypeOptions" variant="outlined" density="compact" hide-details clearable />
        </v-col>
        <v-col v-if="isFieldVisible('tires_condition')" cols="6">
          <div class="text-caption text-medium-emphasis mb-1">Состояние резины</div>
          <v-select v-model="form.tires_condition" :items="tiresConditionOptions" variant="outlined" density="compact" hide-details clearable />
        </v-col>
        <v-col v-if="isFieldVisible('props_branding')" cols="6">
          <div class="text-caption text-medium-emphasis mb-1">Брендирование</div>
          <v-combobox v-model="form.props_branding" :items="brandSuggestions" variant="outlined" density="compact" hide-details clearable auto-select-first :return-object="false" />
        </v-col>
        <v-col v-if="isFieldVisible('props_paint_condition')" cols="6">
          <div class="text-caption text-medium-emphasis mb-1">ЛКП (состояние)</div>
          <v-select v-model="form.props_paint_condition" :items="paintConditionOptions" variant="outlined" density="compact" hide-details clearable />
        </v-col>
        <v-col v-if="isFieldVisible('first_aid_kit_until')" cols="6">
          <div class="text-caption text-medium-emphasis mb-1">Аптечка — срок использования до</div>
          <v-text-field v-model="form.first_aid_kit_until" type="date" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('extinguisher_check_date')" cols="6">
          <div class="text-caption text-medium-emphasis mb-1">Огнетушитель — дата поверки</div>
          <v-text-field v-model="form.extinguisher_check_date" type="date" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('tracker_paid_until')" cols="6">
          <div class="text-caption text-medium-emphasis mb-1">Трекер — оплачен до</div>
          <v-text-field v-model="form.tracker_paid_until" type="date" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('tachograph_check_date')" cols="6">
          <div class="text-caption text-medium-emphasis mb-1">Тахограф — дата поверки</div>
          <v-text-field v-model="form.tachograph_check_date" type="date" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col v-if="isFieldVisible('props_defect_description')" cols="6">
          <div class="text-caption text-medium-emphasis mb-1">Неисправности</div>
          <v-textarea v-model="form.props_defect_description" variant="outlined" density="compact" hide-details rows="2" auto-grow />
        </v-col>
        <v-col v-if="isFieldVisible('tech_condition_info')" cols="12">
          <div class="text-caption text-medium-emphasis mb-1">Сведения о техническом состоянии</div>
          <v-textarea v-model="form.tech_condition_info" variant="outlined" density="compact" hide-details rows="2" auto-grow />
        </v-col>
        <v-col v-if="isFieldVisible('props_note')" cols="12">
          <div class="text-caption text-medium-emphasis mb-1">Примечание</div>
          <v-textarea v-model="form.props_note" variant="outlined" density="compact" hide-details rows="2" auto-grow />
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import FieldHint from './FieldHint.vue'
import type { VehicleForm } from '@/composables/fleet/vehicleDetailTypes'

defineProps<{
  form: VehicleForm
  isFieldVisible: (key: string) => boolean
  tiresTypeOptions: string[]
  tiresConditionOptions: string[]
  paintConditionOptions: string[]
  brandSuggestions: string[]
}>()
</script>
