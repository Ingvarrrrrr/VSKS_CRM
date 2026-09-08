<!-- Собственность (Autoblock §2) — карточка «Общее» карточки ТС. -->
<template>
  <v-card v-if="isGroupVisible('ownership')" class="vp-box mb-4">
    <v-card-title class="vp-box__title">
      <v-icon icon="mdi-file-certificate-outline" size="small" class="mr-2" />
      Собственность
    </v-card-title>
    <v-card-text class="pa-0">
      <div class="vp-data-grid">
        <!-- ИНН собственника (computed, readonly) -->
        <div class="vp-data-row" v-if="isFieldVisible('owner_inn')">
          <span class="vp-data-key">
            <span class="text-caption text-medium-emphasis d-flex align-center">
              ИНН собственника
              <FieldHint field-key="owner_inn" />
              <v-chip size="x-small" variant="tonal" color="grey" class="ml-2">не редактируется</v-chip>
            </span>
          </span>
          <span class="vp-data-val">
            <v-text-field :model-value="ownerInnDisplay || '—'" variant="underlined" density="compact" hide-details readonly class="vp-inline-field text-medium-emphasis" />
          </span>
        </div>
        <!-- Основание возникновения собственности -->
        <div class="vp-data-row" v-if="isFieldVisible('ownership_basis')">
          <span class="vp-data-key">
            <FieldLabel label="Основание возникновения собственности" field-key="ownership_basis" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-combobox v-model="form.ownership_basis" :items="ownershipBasisOptions" variant="underlined" density="compact" hide-details clearable auto-select-first :return-object="false" class="vp-inline-field" placeholder="—" />
          </span>
        </div>
        <!-- № документа основания собственности -->
        <div class="vp-data-row" v-if="isFieldVisible('ownership_doc_number')">
          <span class="vp-data-key">
            <FieldLabel label="№ документа основания собственности" field-key="ownership_doc_number" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-text-field v-model="form.ownership_doc_number" variant="underlined" density="compact" hide-details class="vp-inline-field" placeholder="—" />
          </span>
        </div>
        <!-- Дата документа основания собственности -->
        <div class="vp-data-row" v-if="isFieldVisible('ownership_doc_date')">
          <span class="vp-data-key">
            <FieldLabel label="Дата документа основания собственности" field-key="ownership_doc_date" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-text-field v-model="form.ownership_doc_date" type="date" variant="underlined" density="compact" hide-details class="vp-inline-field" />
          </span>
        </div>
        <!-- Дата, когда организация стала собственником -->
        <div class="vp-data-row" v-if="isFieldVisible('owner_since')">
          <span class="vp-data-key">
            <FieldLabel label="Собственник с" field-key="owner_since" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-text-field v-model="form.owner_since" type="date" variant="underlined" density="compact" hide-details class="vp-inline-field" />
          </span>
        </div>
        <!-- Кто субсидировал -->
        <div class="vp-data-row" v-if="isFieldVisible('purchase_info')">
          <span class="vp-data-key">
            <FieldLabel label="Кто субсидировал" field-key="purchase_info" :vehicle-id="vehicleId" />
          </span>
          <span class="vp-data-val">
            <v-text-field v-model="form.purchase_info" variant="underlined" density="compact" hide-details class="vp-inline-field" placeholder="—" />
          </span>
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import FieldLabel from './FieldLabel.vue'
import FieldHint from './FieldHint.vue'
import type { VehicleForm } from '@/composables/fleet/vehicleDetailTypes'

defineProps<{
  form: VehicleForm
  vehicleId: number
  isFieldVisible: (key: string) => boolean
  isGroupVisible: (key: string) => boolean
  ownerInnDisplay: string | null
  ownershipBasisOptions: string[]
}>()
</script>
