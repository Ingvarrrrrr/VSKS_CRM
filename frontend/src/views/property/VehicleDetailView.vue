<template>
  <v-container fluid class="pa-6" style="max-width:1400px">

    <!-- Loading skeleton -->
    <div v-if="loadingVehicle" class="text-center py-16">
      <v-progress-circular indeterminate size="48" color="primary" />
    </div>

    <template v-else-if="vehicle">

      <!-- ── Предупреждения ── -->
      <v-alert
        v-if="isInsuranceExpiringSoon"
        type="warning" variant="tonal" density="compact" class="mb-3"
        prepend-icon="mdi-shield-alert-outline"
      >
        ОСАГО истекает {{ formatDate(vehicle.insurance_until) }} — до истечения менее 30 дней
      </v-alert>
      <v-alert
        v-if="isToSoon"
        type="info" variant="tonal" density="compact" class="mb-3"
        prepend-icon="mdi-wrench-clock"
      >
        Пробег до следующего ТО менее 1000 км
      </v-alert>

      <!-- ── Header ── -->
      <div class="d-flex align-start justify-space-between mb-4 flex-wrap gap-3">
        <div>
          <v-breadcrumbs
            :items="[
              { title: 'Автотранспорт', to: '/property/vehicles' },
              { title: `${vehicle.brand ?? ''} ${vehicle.model ?? ''} (${vehicle.plate})`.trim() },
            ]"
            density="compact"
            class="pa-0 mb-1"
          />
          <div class="d-flex align-center gap-3 flex-wrap">
            <h1 class="text-h5 font-weight-bold">
              {{ [vehicle.brand, vehicle.model].filter(Boolean).join(' ') || 'ТС' }}
              <span class="text-medium-emphasis">· {{ vehicle.plate }}</span>
            </h1>
            <v-chip
              v-if="vehicle.state"
              :color="STATE_COLOR[vehicle.state] ?? 'grey'"
              size="small"
              variant="tonal"
            >
              {{ STATE_LABEL[vehicle.state] ?? vehicle.state }}
            </v-chip>
            <v-chip
              v-if="vehicle.type"
              :color="TYPE_COLOR[vehicle.type] ?? 'grey'"
              size="small"
              variant="outlined"
            >
              {{ TYPE_LABEL[vehicle.type] ?? vehicle.type }}
            </v-chip>
          </div>
        </div>

        <div class="d-flex gap-2 flex-wrap">
          <v-btn variant="outlined" prepend-icon="mdi-arrow-left" to="/property/vehicles" size="small">
            К списку
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            prepend-icon="mdi-content-save"
            size="small"
            :loading="saving"
            :disabled="!isDirty"
            @click="save"
          >
            Сохранить
          </v-btn>
          <v-btn
            v-if="authStore.hasAction('vehicle.delete')"
            color="error"
            variant="outlined"
            prepend-icon="mdi-delete"
            size="small"
            @click="deleteDialog = true"
          >
            Удалить
          </v-btn>
        </div>
      </div>

      <!-- ── Tabs ── -->
      <v-tabs v-model="activeTab" color="primary" class="mb-1">
        <v-tab value="general">Общее</v-tab>
        <v-tab value="documents">Документы</v-tab>
        <v-tab value="photos">Фото</v-tab>
        <v-tab value="repairs">Ремонты</v-tab>
        <v-tab value="odometer">Пробег</v-tab>
        <v-tab value="fuel">Заправки</v-tab>
        <v-tab value="trips">Путёвки</v-tab>
        <v-tab value="history">История</v-tab>
        <v-tab value="purchases">Связанные закупки</v-tab>
      </v-tabs>
      <v-divider class="mb-4" />

      <v-tabs-window v-model="activeTab">

        <!-- ─────────── Tab: Общее (Hero+2-col layout, Phase 29.3) ─────────── -->
        <v-tabs-window-item value="general">

          <!-- ── Hero banner ── -->
          <v-card class="mb-5" :style="heroBgStyle" rounded="lg">
            <v-card-text class="pa-5">
              <div class="d-flex align-start gap-5 flex-wrap">
                <!-- Photo placeholder -->
                <div class="rounded d-flex align-center justify-center flex-shrink-0"
                  style="width:160px;height:100px;background:rgba(255,255,255,0.15)">
                  <v-icon icon="mdi-camera" color="rgba(255,255,255,0.6)" size="40" />
                </div>

                <!-- Info -->
                <div class="flex-1-1" style="min-width:200px">
                  <div class="text-h5 font-weight-bold text-white mb-1">
                    {{ [vehicle.brand, vehicle.model].filter(Boolean).join(' ') || 'ТС' }}
                  </div>
                  <div class="text-body-2 mb-3" style="color:rgba(255,255,255,0.85)">
                    {{ [vehicle.year_of_manufacture, vehicle.color].filter(Boolean).join(' · ') }}
                    <template v-if="vehicle.owner_org_name">· {{ vehicle.owner_org_name }}</template>
                    <template v-if="vehicle.assigned_org_name || vehicle.assigned_text">
                      · {{ vehicle.assigned_org_name || vehicle.assigned_text }}
                    </template>
                  </div>

                  <!-- Chips row -->
                  <div class="d-flex align-center gap-2 flex-wrap">
                    <LicensePlate :model-value="vehicle.plate" size="lg" />

                    <v-chip
                      v-if="vehicle.state"
                      style="background:rgba(255,255,255,0.2);color:white"
                      size="small"
                      variant="flat"
                    >
                      {{ STATE_LABEL[vehicle.state] ?? vehicle.state }}
                    </v-chip>

                    <v-chip
                      v-if="vehicle.type"
                      style="background:rgba(255,255,255,0.15);color:white"
                      size="small"
                      variant="flat"
                      prepend-icon="mdi-car-info"
                    >
                      {{ TYPE_LABEL[vehicle.type] ?? vehicle.type }}
                    </v-chip>

                    <v-chip
                      v-if="vehicle.insurance_until"
                      :style="isInsuranceExpiringSoon
                        ? 'background:rgba(255,193,7,0.35);color:white'
                        : 'background:rgba(255,255,255,0.2);color:white'"
                      size="small"
                      variant="flat"
                      prepend-icon="mdi-shield-check"
                    >
                      ОСАГО до {{ formatDate(vehicle.insurance_until) }}
                    </v-chip>

                    <v-chip
                      v-if="vehicle.next_to_km && vehicle.current_odometer_km"
                      :style="isToSoon
                        ? 'background:rgba(255,193,7,0.35);color:white'
                        : 'background:rgba(255,255,255,0.2);color:white'"
                      size="small"
                      variant="flat"
                      prepend-icon="mdi-wrench"
                    >
                      ТО через {{ (vehicle.next_to_km - vehicle.current_odometer_km).toLocaleString('ru-RU') }} км
                    </v-chip>

                    <v-chip
                      v-if="vehicle.engine_power_hp"
                      style="background:rgba(255,255,255,0.2);color:white"
                      size="small"
                      variant="flat"
                      prepend-icon="mdi-engine"
                    >
                      {{ vehicle.engine_power_hp }} л.с.
                    </v-chip>

                    <v-chip
                      v-if="vehicle.engine_volume_l"
                      style="background:rgba(255,255,255,0.2);color:white"
                      size="small"
                      variant="flat"
                    >
                      {{ vehicle.engine_volume_l }}л
                    </v-chip>
                  </div>
                </div>
              </div>
            </v-card-text>
          </v-card>

          <!-- Комментарий к изменению -->
          <v-text-field
            v-model="historyComment"
            label="Комментарий к изменению (необязательно)"
            variant="outlined"
            density="compact"
            class="mb-4"
            clearable
            prepend-inner-icon="mdi-comment-edit-outline"
            style="max-width:600px"
          />

          <!-- ── 4 секции в 2 колонки ── -->
          <v-row>
            <!-- Идентификация -->
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="mb-4 h-100">
                <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
                  <v-icon icon="mdi-car-info" size="small" class="mr-1" />
                  Идентификация
                </v-card-title>
                <v-card-text>
                  <v-row dense>
                    <v-col cols="12">
                      <FieldLabel label="Гос. номер" field-key="plate" :vehicle-id="vehicle.id" />
                      <div class="mt-1">
                        <LicensePlate v-model="form.plate" :readonly="false" />
                      </div>
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Марка" field-key="brand" :vehicle-id="vehicle.id" />
                      <v-text-field v-model="form.brand" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Модель" field-key="model" :vehicle-id="vehicle.id" />
                      <v-text-field v-model="form.model" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Год выпуска" field-key="year_of_manufacture" :vehicle-id="vehicle.id" />
                      <v-text-field v-model.number="form.year_of_manufacture" type="number" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Цвет" field-key="color" :vehicle-id="vehicle.id" />
                      <v-text-field v-model="form.color" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="12">
                      <FieldLabel label="VIN" field-key="vin" :vehicle-id="vehicle.id" />
                      <v-text-field v-model="form.vin" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Тип ТС" field-key="type" :vehicle-id="vehicle.id" />
                      <v-select v-model="form.type" :items="typeOptions" item-title="label" item-value="value" variant="outlined" density="compact" hide-details clearable />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Состояние" field-key="state" :vehicle-id="vehicle.id" />
                      <v-select v-model="form.state" :items="stateOptions" item-title="label" item-value="value" variant="outlined" density="compact" hide-details clearable />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Дата регистрации" field-key="registered_at" :vehicle-id="vehicle.id" />
                      <v-text-field v-model="form.registered_at" type="date" variant="outlined" density="compact" hide-details />
                    </v-col>
                  </v-row>
                </v-card-text>
              </v-card>
            </v-col>

            <!-- Принадлежность -->
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="mb-4 h-100">
                <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
                  <v-icon icon="mdi-office-building" size="small" class="mr-1" />
                  Принадлежность
                </v-card-title>
                <v-card-text>
                  <v-row dense>
                    <v-col cols="12">
                      <FieldLabel label="Организация-владелец" field-key="owner_org_id" :vehicle-id="vehicle.id" />
                      <v-autocomplete v-model="form.owner_org_id" :items="orgsList" item-title="name" item-value="id" variant="outlined" density="compact" hide-details clearable />
                    </v-col>
                    <v-col cols="12">
                      <FieldLabel label="Организация-эксплуатант" field-key="assigned_org_id" :vehicle-id="vehicle.id" />
                      <v-autocomplete v-model="form.assigned_org_id" :items="orgsList" item-title="name" item-value="id" variant="outlined" density="compact" hide-details clearable />
                    </v-col>
                    <v-col v-if="!form.assigned_org_id" cols="12">
                      <div class="text-caption text-medium-emphasis mb-1">Эксплуатант (текст)</div>
                      <v-text-field v-model="form.assigned_text" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="12">
                      <FieldLabel label="Основание для использования" field-key="assignment_basis" :vehicle-id="vehicle.id" />
                      <v-text-field v-model="form.assignment_basis" variant="outlined" density="compact" hide-details placeholder="Договор аренды, акт п/п..." />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Номер документа" field-key="assignment_doc_number" :vehicle-id="vehicle.id" />
                      <v-text-field v-model="form.assignment_doc_number" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Дата документа" field-key="assignment_doc_date" :vehicle-id="vehicle.id" />
                      <v-text-field v-model="form.assignment_doc_date" type="date" variant="outlined" density="compact" hide-details />
                    </v-col>
                  </v-row>
                </v-card-text>
              </v-card>
            </v-col>

            <!-- Документы и топливо -->
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="mb-4 h-100">
                <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
                  <v-icon icon="mdi-file-document-outline" size="small" class="mr-1" />
                  Документы и топливо
                </v-card-title>
                <v-card-text>
                  <v-row dense>
                    <v-col cols="6">
                      <FieldLabel label="ПТС" field-key="pts_number" :vehicle-id="vehicle.id" />
                      <v-text-field v-model="form.pts_number" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="СТС" field-key="sts_number" :vehicle-id="vehicle.id" />
                      <v-text-field v-model="form.sts_number" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="ОСАГО до" field-key="insurance_until" :vehicle-id="vehicle.id" />
                      <v-text-field v-model="form.insurance_until" type="date" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Техосмотр до" field-key="tech_inspection_until" :vehicle-id="vehicle.id" />
                      <v-text-field v-model="form.tech_inspection_until" type="date" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Тип топлива" field-key="fuel_type" :vehicle-id="vehicle.id" />
                      <v-select v-model="form.fuel_type" :items="fuelTypeOptions" item-title="label" item-value="value" variant="outlined" density="compact" hide-details clearable />
                    </v-col>
                    <v-col cols="6">
                      <div class="text-caption text-medium-emphasis mb-1">Текущий пробег, км</div>
                      <v-text-field :model-value="vehicle.current_odometer_km ?? '—'" variant="outlined" density="compact" hide-details readonly class="text-medium-emphasis" />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Последнее ТО, км" field-key="last_to_mileage_km" :vehicle-id="vehicle.id" />
                      <v-text-field v-model.number="form.last_to_mileage_km" type="number" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Дата последнего ТО" field-key="last_to_date" :vehicle-id="vehicle.id" />
                      <v-text-field v-model="form.last_to_date" type="date" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Следующее ТО, км" field-key="next_to_km" :vehicle-id="vehicle.id" />
                      <v-text-field v-model.number="form.next_to_km" type="number" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Мощность, л.с." field-key="engine_power_hp" :vehicle-id="vehicle.id" />
                      <v-text-field v-model.number="form.engine_power_hp" type="number" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Объём двигателя, л" field-key="engine_volume_l" :vehicle-id="vehicle.id" />
                      <v-text-field v-model.number="form.engine_volume_l" type="number" step="0.1" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Норма расхода (лето)" field-key="fuel_norm_summer" :vehicle-id="vehicle.id" />
                      <v-text-field v-model.number="form.fuel_norm_summer" type="number" step="0.1" suffix="л/100км" variant="outlined" density="compact" hide-details />
                    </v-col>
                    <v-col cols="6">
                      <FieldLabel label="Норма расхода (зима)" field-key="fuel_norm_winter" :vehicle-id="vehicle.id" />
                      <v-text-field v-model.number="form.fuel_norm_winter" type="number" step="0.1" suffix="л/100км" variant="outlined" density="compact" hide-details />
                    </v-col>
                  </v-row>
                </v-card-text>
              </v-card>
            </v-col>

            <!-- Чек-лист оборудования -->
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="mb-4 h-100">
                <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
                  <v-icon icon="mdi-clipboard-check-outline" size="small" class="mr-1" />
                  Чек-лист оборудования
                </v-card-title>
                <v-card-text>
                  <v-row dense>
                    <v-col cols="12" sm="6">
                      <v-checkbox v-model="form.has_tracker" label="Трекер" density="compact" hide-details />
                    </v-col>
                    <v-col cols="12" sm="6">
                      <v-checkbox v-model="form.akb_ok" label="АКБ исправен" density="compact" hide-details />
                    </v-col>
                    <v-col cols="12" sm="6">
                      <v-checkbox v-model="form.has_radio" label="Радиостанция" density="compact" hide-details />
                    </v-col>
                    <v-col cols="12" sm="6">
                      <v-checkbox v-model="form.mirrors_ok" label="Зеркала OK" density="compact" hide-details />
                    </v-col>
                    <v-col cols="12" sm="6">
                      <v-checkbox v-model="form.has_keys" label="Ключи" density="compact" hide-details />
                    </v-col>
                    <v-col cols="12" sm="6">
                      <v-checkbox v-model="form.has_first_aid_kit" label="Аптечка" density="compact" hide-details />
                    </v-col>
                    <v-col cols="12" sm="6">
                      <v-checkbox v-model="form.has_spare_wheel" label="Запасное колесо" density="compact" hide-details />
                    </v-col>
                    <v-col cols="12" sm="6">
                      <v-checkbox v-model="form.has_extinguisher" label="Огнетушитель" density="compact" hide-details />
                    </v-col>
                  </v-row>

                  <!-- Дополнительные параметры (JSONB) -->
                  <v-divider class="my-3" />
                  <div class="text-subtitle-2 font-weight-bold mb-2">Доп. параметры</div>
                  <v-row dense>
                    <v-col cols="6">
                      <div class="text-caption text-medium-emphasis mb-1">Авторезина</div>
                      <v-text-field v-model="form.props_tires_type" variant="outlined" density="compact" hide-details clearable />
                    </v-col>
                    <v-col cols="6">
                      <div class="text-caption text-medium-emphasis mb-1">Брендирование</div>
                      <v-text-field v-model="form.props_branding" variant="outlined" density="compact" hide-details clearable />
                    </v-col>
                    <v-col cols="6">
                      <div class="text-caption text-medium-emphasis mb-1">ЛКП</div>
                      <v-textarea v-model="form.props_paint_condition" variant="outlined" density="compact" hide-details rows="2" auto-grow />
                    </v-col>
                    <v-col cols="6">
                      <div class="text-caption text-medium-emphasis mb-1">Неисправности</div>
                      <v-textarea v-model="form.props_defect_description" variant="outlined" density="compact" hide-details rows="2" auto-grow />
                    </v-col>
                    <v-col cols="12">
                      <div class="text-caption text-medium-emphasis mb-1">Примечание</div>
                      <v-textarea v-model="form.props_note" variant="outlined" density="compact" hide-details rows="2" auto-grow />
                    </v-col>
                  </v-row>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>

          <!-- ── История передач ── -->
          <v-card variant="outlined" class="mb-4">
            <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
              <v-icon icon="mdi-swap-horizontal" size="small" class="mr-1" />
              История передач
            </v-card-title>
            <v-card-text>
              <div v-if="loadingTransferHistory" class="text-center py-4">
                <v-progress-circular indeterminate size="28" color="primary" />
              </div>
              <div v-else-if="transferHistory.length === 0" class="text-medium-emphasis text-body-2">
                История пуста — передачи не фиксировались
              </div>
              <v-timeline v-else density="compact" side="end">
                <v-timeline-item
                  v-for="item in transferHistory"
                  :key="item.id"
                  :dot-color="item.from_owner_org_id !== item.to_owner_org_id ? 'orange' : 'blue'"
                  size="small"
                >
                  <div class="text-body-2 font-weight-medium">
                    {{ formatDate(item.changed_at) }}
                    <template v-if="item.from_owner_org_id !== item.to_owner_org_id">
                      — смена владельца
                    </template>
                    <template v-else>
                      — смена эксплуатанта
                    </template>
                  </div>
                  <div class="text-body-2 text-medium-emphasis">
                    <template v-if="item.from_assigned_org_id || item.to_assigned_org_id">
                      {{ item.from_assigned_text || '—' }} → {{ item.to_assigned_text || '—' }}
                    </template>
                  </div>
                  <div v-if="item.basis" class="text-caption text-medium-emphasis">
                    {{ item.basis }}<template v-if="item.doc_number"> № {{ item.doc_number }}</template>
                    <template v-if="item.doc_date"> от {{ formatDate(item.doc_date) }}</template>
                  </div>
                  <div v-if="item.comment" class="text-caption text-medium-emphasis">
                    {{ item.comment }}
                  </div>
                </v-timeline-item>
              </v-timeline>
            </v-card-text>
          </v-card>

          <!-- Save bar -->
          <div class="d-flex justify-end gap-3 pb-6">
            <v-btn variant="text" :disabled="!isDirty || saving" @click="resetForm">Сбросить</v-btn>
            <v-btn
              color="primary"
              variant="flat"
              prepend-icon="mdi-content-save"
              :loading="saving"
              :disabled="!isDirty"
              @click="save"
            >
              Сохранить изменения
            </v-btn>
          </div>

        </v-tabs-window-item>

        <!-- ─────────── Tab: Документы ─────────── -->
        <v-tabs-window-item value="documents" :eager="false">
          <VehicleDocumentsTab :vehicle-id="vehicleId" />
        </v-tabs-window-item>

        <!-- ─────────── Tab: Фото ─────────── -->
        <v-tabs-window-item value="photos" :eager="false">
          <VehiclePhotosTab :vehicle-id="vehicleId" />
        </v-tabs-window-item>

        <!-- ─────────── Tab: Ремонты ─────────── -->
        <v-tabs-window-item value="repairs" :eager="false">
          <VehicleRepairsTab :vehicle-id="vehicleId" />
        </v-tabs-window-item>

        <!-- ─────────── Tab: Пробег ─────────── -->
        <v-tabs-window-item value="odometer" :eager="false">
          <VehicleOdometerTab :vehicle-id="vehicleId" />
        </v-tabs-window-item>

        <!-- ─────────── Tab: Заправки ─────────── -->
        <v-tabs-window-item value="fuel" :eager="false">
          <VehicleFuelLogTab :vehicle-id="vehicleId" />
        </v-tabs-window-item>

        <!-- ─────────── Tab: Путёвки ─────────── -->
        <v-tabs-window-item value="trips" :eager="false">
          <VehicleTripsTab :vehicle-id="vehicleId" />
        </v-tabs-window-item>

        <!-- ─────────── Tab: История ─────────── -->
        <v-tabs-window-item value="history" :eager="false">
          <VehicleHistoryTab :vehicle-id="vehicleId" />
        </v-tabs-window-item>

        <!-- ─────────── Tab: Закупки ─────────── -->
        <v-tabs-window-item value="purchases" :eager="false">
          <VehicleRelatedPurchasesTab :vehicle-id="vehicleId" />
        </v-tabs-window-item>

      </v-tabs-window>
    </template>

    <!-- Not found -->
    <div v-else-if="!loadingVehicle" class="text-center py-16">
      <v-icon size="64" color="grey-lighten-1" icon="mdi-car-off" class="mb-4" />
      <div class="text-h6 text-medium-emphasis">ТС не найдено</div>
      <v-btn class="mt-4" to="/property/vehicles" variant="outlined" prepend-icon="mdi-arrow-left">К списку</v-btn>
    </div>

    <!-- ── Confirm delete dialog ── -->
    <v-dialog v-model="deleteDialog" max-width="440">
      <v-card>
        <v-card-title class="d-flex align-center gap-2 pa-5 pb-2">
          <v-icon icon="mdi-delete-alert" color="error" />
          Удалить ТС?
        </v-card-title>
        <v-card-text class="px-5">
          Действие необратимо. Будут удалены все связанные документы, ремонты, пробег и история.
        </v-card-text>
        <v-card-actions class="px-5 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="deleting" @click="doDelete">
            Удалить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Error dialog ── -->
    <v-dialog v-model="errorDialogShow" max-width="520">
      <v-card>
        <v-card-title class="d-flex align-center gap-2 pa-5 pb-2">
          <v-icon icon="mdi-alert-circle-outline" color="error" />
          Ошибка
        </v-card-title>
        <v-card-text class="px-5">
          <p class="mb-2">{{ errorMsg }}</p>
          <div v-if="errorCode" class="text-caption text-medium-emphasis">Код: {{ errorCode }}</div>
          <div v-if="errorCorrelationId" class="text-caption text-medium-emphasis">ID: {{ errorCorrelationId }}</div>
        </v-card-text>
        <v-card-actions class="px-5 pb-4">
          <v-btn size="small" variant="tonal" prepend-icon="mdi-content-copy" @click="copyError">
            Скопировать
          </v-btn>
          <v-spacer />
          <v-btn variant="text" @click="errorDialogShow = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Snackbar ── -->
    <v-snackbar
      v-model="snack.show"
      :color="snack.color"
      :timeout="snack.color === 'error' ? -1 : 3000"
      location="bottom right"
    >
      {{ snack.text }}
      <template #actions>
        <v-btn v-if="snack.color === 'error'" variant="text" @click="snack.show = false">Закрыть</v-btn>
      </template>
    </v-snackbar>

  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, reactive, defineComponent, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useAuthStore } from '@/stores/auth'
import FieldHistoryPopover from '@/components/vehicles/FieldHistoryPopover.vue'
import VehicleDocumentsTab from '@/components/vehicles/VehicleDocumentsTab.vue'
import VehiclePhotosTab from '@/components/vehicles/VehiclePhotosTab.vue'
import VehicleRepairsTab from '@/components/vehicles/VehicleRepairsTab.vue'
import VehicleOdometerTab from '@/components/vehicles/VehicleOdometerTab.vue'
import VehicleFuelLogTab from '@/components/vehicles/VehicleFuelLogTab.vue'
import VehicleTripsTab from '@/components/vehicles/VehicleTripsTab.vue'
import VehicleHistoryTab from '@/components/vehicles/VehicleHistoryTab.vue'
import VehicleRelatedPurchasesTab from '@/components/vehicles/VehicleRelatedPurchasesTab.vue'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'

// ─────────────── Types ───────────────

interface OrgItem {
  id: number
  name: string
}

interface Vehicle {
  id: number
  owner_org_id: number
  owner_org_name?: string | null
  assigned_org_id: number | null
  assigned_org_name?: string | null
  assigned_text: string | null
  brand: string | null
  model: string | null
  color: string | null
  plate: string
  vin: string | null
  type: string | null
  state: string | null
  registered_at: string | null
  insurance_until: string | null
  fuel_type: string | null
  fuel_norm_summer: number | null
  fuel_norm_winter: number | null
  current_odometer_km: number | null
  next_to_km: number | null
  year_of_manufacture: number | null
  last_to_mileage_km: number | null
  last_to_date: string | null
  pts_number: string | null
  sts_number: string | null
  tech_inspection_until: string | null
  purchase_info: string | null
  assignment_basis: string | null
  assignment_doc_number: string | null
  assignment_doc_date: string | null
  engine_power_hp: number | null
  engine_volume_l: number | null
  has_tracker: boolean
  akb_ok: boolean
  has_radio: boolean
  mirrors_ok: boolean
  has_keys: boolean
  has_first_aid_kit: boolean
  has_spare_wheel: boolean
  has_extinguisher: boolean
  props: Record<string, string> | null
  created_at: string
  updated_at: string
}

interface TransferHistoryItem {
  id: number
  vehicle_id: number
  from_owner_org_id: number | null
  to_owner_org_id: number | null
  from_assigned_org_id: number | null
  to_assigned_org_id: number | null
  from_assigned_text: string | null
  to_assigned_text: string | null
  basis: string | null
  doc_number: string | null
  doc_date: string | null
  comment: string | null
  changed_at: string
  changed_by_user_id: number | null
}

// ─────────────── Lookup Maps ───────────────

const TYPE_LABEL: Record<string, string> = {
  car_light:   'Легковой',
  minivan:     'Минивэн',
  truck_van:   'Фургон',
  truck_board: 'Грузовой',
  truck_tank:  'Цистерна',
  truck_metal: 'Металловоз',
  bus:         'Автобус',
  special:     'Спецтехника',
  snowmobile:  'Снегоход',
  boat:        'Лодка',
  boat_motor:  'Лодка (мотор)',
  quadbike:    'Квадроцикл',
  trailer:     'Прицеп',
  other:       'Другой',
}

const STATE_LABEL: Record<string, string> = {
  working:      'Рабочее',
  broken:       'Неисправно',
  in_repair:    'В ремонте',
  needs_repair: 'Требует ремонта',
  destroyed:    'Уничтожено',
  utilized:     'Утилизировано',
}

const FUEL_TYPE_LABEL: Record<string, string> = {
  petrol:   'Бензин',
  diesel:   'Дизель',
  gas:      'Газ',
  hybrid:   'Гибрид',
  electric: 'Электро',
  other:    'Другое',
}

const TYPE_COLOR: Record<string, string> = {
  car_light:   'blue',
  minivan:     'cyan',
  truck_van:   'indigo',
  truck_board: 'brown',
  truck_tank:  'teal',
  bus:         'purple',
  special:     'orange',
  other:       'grey',
}

const STATE_COLOR: Record<string, string> = {
  working:      'success',
  broken:       'error',
  in_repair:    'warning',
  needs_repair: 'orange',
  destroyed:    'grey',
  utilized:     'grey',
}

const typeOptions = Object.entries(TYPE_LABEL).map(([value, label]) => ({ value, label }))
const stateOptions = Object.entries(STATE_LABEL).map(([value, label]) => ({ value, label }))
const fuelTypeOptions = Object.entries(FUEL_TYPE_LABEL).map(([value, label]) => ({ value, label }))

// ─────────────── Inline component: FieldLabel ───────────────

// Renders "<label text> + FieldHistoryPopover icon" as a compact label row
const FieldLabel = defineComponent({
  props: {
    label: { type: String, required: true },
    fieldKey: { type: String, required: true },
    vehicleId: { type: Number, required: true },
  },
  setup(props) {
    return () => h('div', { class: 'text-caption text-medium-emphasis mb-1 d-flex align-center' }, [
      h('span', props.label),
      h(FieldHistoryPopover, {
        vehicleId: props.vehicleId,
        fieldKey: props.fieldKey,
        fieldLabel: props.label,
      }),
    ])
  },
})

// ─────────────── Composables / State ───────────────

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const vehicle = ref<Vehicle | null>(null)
const vehicleOriginal = ref<Vehicle | null>(null)
const loadingVehicle = ref(false)
const vehicleId = computed(() => Number(route.params.id) || 0)
const saving = ref(false)
const deleting = ref(false)
const activeTab = ref('general')
const orgsList = ref<OrgItem[]>([])
const historyComment = ref('')

// ─────────────── Form model ───────────────

interface VehicleForm {
  plate: string
  brand: string
  model: string
  color: string
  vin: string
  type: string | null
  state: string | null
  registered_at: string
  owner_org_id: number | null
  assigned_org_id: number | null
  assigned_text: string
  insurance_until: string
  next_to_km: number | null
  fuel_type: string | null
  fuel_norm_summer: number | null
  fuel_norm_winter: number | null
  year_of_manufacture: number | null
  last_to_mileage_km: number | null
  last_to_date: string
  pts_number: string
  sts_number: string
  tech_inspection_until: string
  purchase_info: string
  assignment_basis: string
  assignment_doc_number: string
  assignment_doc_date: string
  engine_power_hp: number | null
  engine_volume_l: number | null
  has_tracker: boolean
  akb_ok: boolean
  has_radio: boolean
  mirrors_ok: boolean
  has_keys: boolean
  has_first_aid_kit: boolean
  has_spare_wheel: boolean
  has_extinguisher: boolean
  props_tires_type: string
  props_branding: string
  props_paint_condition: string
  props_defect_description: string
  props_note: string
}

const form = reactive<VehicleForm>({
  plate: '',
  brand: '',
  model: '',
  color: '',
  vin: '',
  type: null,
  state: null,
  registered_at: '',
  owner_org_id: null,
  assigned_org_id: null,
  assigned_text: '',
  insurance_until: '',
  next_to_km: null,
  fuel_type: null,
  fuel_norm_summer: null,
  fuel_norm_winter: null,
  year_of_manufacture: null,
  last_to_mileage_km: null,
  last_to_date: '',
  pts_number: '',
  sts_number: '',
  tech_inspection_until: '',
  purchase_info: '',
  assignment_basis: '',
  assignment_doc_number: '',
  assignment_doc_date: '',
  engine_power_hp: null,
  engine_volume_l: null,
  has_tracker: false,
  akb_ok: false,
  has_radio: false,
  mirrors_ok: false,
  has_keys: false,
  has_first_aid_kit: false,
  has_spare_wheel: false,
  has_extinguisher: false,
  props_tires_type: '',
  props_branding: '',
  props_paint_condition: '',
  props_defect_description: '',
  props_note: '',
})

// ─────────────── isDirty ───────────────

function formSnapshot(): string {
  return JSON.stringify({ ...form })
}

const originalSnapshot = ref('')

const isDirty = computed(() => {
  if (!vehicle.value) return false
  return formSnapshot() !== originalSnapshot.value
})

// ─────────────── Populate form from vehicle ───────────────

function toDateInput(v: string | null): string {
  if (!v) return ''
  try { return v.slice(0, 10) } catch { return '' }
}

function fillForm(v: Vehicle) {
  form.plate                  = v.plate ?? ''
  form.brand                  = v.brand ?? ''
  form.model                  = v.model ?? ''
  form.color                  = v.color ?? ''
  form.vin                    = v.vin ?? ''
  form.type                   = v.type ?? null
  form.state                  = v.state ?? null
  form.registered_at          = toDateInput(v.registered_at)
  form.owner_org_id           = v.owner_org_id ?? null
  form.assigned_org_id        = v.assigned_org_id ?? null
  form.assigned_text          = v.assigned_text ?? ''
  form.insurance_until        = toDateInput(v.insurance_until)
  form.next_to_km             = v.next_to_km ?? null
  form.fuel_type              = v.fuel_type ?? null
  form.fuel_norm_summer       = v.fuel_norm_summer ?? null
  form.fuel_norm_winter       = v.fuel_norm_winter ?? null
  form.year_of_manufacture    = v.year_of_manufacture ?? null
  form.last_to_mileage_km     = v.last_to_mileage_km ?? null
  form.last_to_date           = toDateInput(v.last_to_date)
  form.pts_number             = v.pts_number ?? ''
  form.sts_number             = v.sts_number ?? ''
  form.tech_inspection_until  = toDateInput(v.tech_inspection_until)
  form.purchase_info          = v.purchase_info ?? ''
  form.assignment_basis       = v.assignment_basis ?? ''
  form.assignment_doc_number  = v.assignment_doc_number ?? ''
  form.assignment_doc_date    = toDateInput(v.assignment_doc_date)
  form.engine_power_hp        = v.engine_power_hp ?? null
  form.engine_volume_l        = v.engine_volume_l ?? null
  form.has_tracker            = !!v.has_tracker
  form.akb_ok                 = !!v.akb_ok
  form.has_radio              = !!v.has_radio
  form.mirrors_ok             = !!v.mirrors_ok
  form.has_keys               = !!v.has_keys
  form.has_first_aid_kit      = !!v.has_first_aid_kit
  form.has_spare_wheel        = !!v.has_spare_wheel
  form.has_extinguisher       = !!v.has_extinguisher
  form.props_tires_type        = v.props?.tires_type ?? ''
  form.props_branding          = v.props?.branding ?? ''
  form.props_paint_condition   = v.props?.paint_condition ?? ''
  form.props_defect_description = v.props?.defect_description ?? ''
  form.props_note              = v.props?.note ?? ''
  originalSnapshot.value = formSnapshot()
}

function resetForm() {
  if (vehicle.value) fillForm(vehicle.value)
}

// ─────────────── Build PATCH delta ───────────────

function buildDelta(): Record<string, any> {
  if (!vehicle.value) return {}
  const v = vehicle.value
  const delta: Record<string, any> = {}

  const strField = (key: keyof VehicleForm, orig: string | null) => {
    const cur = (form[key] as string) || null
    const origNorm = orig || null
    if (cur !== origNorm) delta[key] = cur
  }
  const numField = (key: keyof VehicleForm, orig: number | null) => {
    const cur = (form[key] as number | null) ?? null
    if (cur !== orig) delta[key] = cur
  }
  const boolField = (key: keyof VehicleForm, orig: boolean) => {
    const cur = form[key] as boolean
    if (cur !== orig) delta[key] = cur
  }
  const dateField = (key: keyof VehicleForm, orig: string | null) => {
    const cur = (form[key] as string) || null
    const origNorm = orig ? orig.slice(0, 10) : null
    if (cur !== origNorm) delta[key] = cur
  }

  strField('plate', v.plate)
  strField('brand', v.brand)
  strField('model', v.model)
  strField('color', v.color)
  strField('vin', v.vin)
  strField('type', v.type)
  strField('state', v.state)
  strField('assigned_text', v.assigned_text)
  strField('fuel_type', v.fuel_type)
  strField('pts_number', v.pts_number)
  strField('sts_number', v.sts_number)
  strField('purchase_info', v.purchase_info)
  strField('assignment_basis', v.assignment_basis)
  strField('assignment_doc_number', v.assignment_doc_number)
  dateField('registered_at', v.registered_at)
  dateField('insurance_until', v.insurance_until)
  dateField('last_to_date', v.last_to_date)
  dateField('tech_inspection_until', v.tech_inspection_until)
  dateField('assignment_doc_date', v.assignment_doc_date)
  numField('next_to_km', v.next_to_km)
  numField('fuel_norm_summer', v.fuel_norm_summer)
  numField('fuel_norm_winter', v.fuel_norm_winter)
  numField('owner_org_id', v.owner_org_id ?? null)
  numField('assigned_org_id', v.assigned_org_id)
  numField('year_of_manufacture', v.year_of_manufacture)
  numField('last_to_mileage_km', v.last_to_mileage_km)
  numField('engine_power_hp', v.engine_power_hp)
  numField('engine_volume_l', v.engine_volume_l)
  boolField('has_tracker', v.has_tracker)
  boolField('akb_ok', v.akb_ok)
  boolField('has_radio', v.has_radio)
  boolField('mirrors_ok', v.mirrors_ok)
  boolField('has_keys', v.has_keys)
  boolField('has_first_aid_kit', v.has_first_aid_kit)
  boolField('has_spare_wheel', v.has_spare_wheel)
  boolField('has_extinguisher', v.has_extinguisher)

  // JSONB props — send full object if any prop field changed
  const origProps = v.props ?? {}
  const newProps = {
    ...origProps,
    tires_type:         form.props_tires_type || undefined,
    branding:           form.props_branding || undefined,
    paint_condition:    form.props_paint_condition || undefined,
    defect_description: form.props_defect_description || undefined,
    note:               form.props_note || undefined,
  }
  // Remove undefined keys
  Object.keys(newProps).forEach(k => { if (newProps[k] === undefined) delete newProps[k] })

  const propsChanged = (
    (form.props_tires_type || null) !== (origProps.tires_type || null) ||
    (form.props_branding || null) !== (origProps.branding || null) ||
    (form.props_paint_condition || null) !== (origProps.paint_condition || null) ||
    (form.props_defect_description || null) !== (origProps.defect_description || null) ||
    (form.props_note || null) !== (origProps.note || null)
  )
  if (propsChanged) {
    delta.props = newProps
  }

  return delta
}

// ─────────────── Hero background ───────────────

const heroBgStyle = computed(() => {
  const color = (vehicle.value as any)?.assigned_org?.color
    ?? (vehicle.value as any)?.assigned_org_color
    ?? '#1976d2'
  return {
    background: `linear-gradient(135deg, ${color}88 0%, ${color} 100%)`,
  }
})

// ─────────────── Transfer history ───────────────

const transferHistory = ref<TransferHistoryItem[]>([])
const loadingTransferHistory = ref(false)

async function loadTransferHistory(id: number) {
  loadingTransferHistory.value = true
  try {
    const data = await apiFetch<TransferHistoryItem[]>(`/vehicles/${id}/transfer-history`)
    transferHistory.value = Array.isArray(data) ? data : []
  } catch {
    transferHistory.value = []
  } finally {
    loadingTransferHistory.value = false
  }
}

// ─────────────── Alerts ───────────────

const isInsuranceExpiringSoon = computed(() => {
  if (!vehicle.value?.insurance_until) return false
  const diff = new Date(vehicle.value.insurance_until).getTime() - Date.now()
  return diff < 30 * 24 * 3600 * 1000
})

const isToSoon = computed(() => {
  if (vehicle.value?.next_to_km == null || vehicle.value?.current_odometer_km == null) return false
  return (vehicle.value.next_to_km - vehicle.value.current_odometer_km) < 1000
})

// ─────────────── API calls ───────────────

async function loadVehicle(id: number) {
  loadingVehicle.value = true
  vehicle.value = null
  try {
    const data = await apiFetch<Vehicle>(`/vehicles/${id}`)
    vehicle.value = data
    vehicleOriginal.value = JSON.parse(JSON.stringify(data))
    fillForm(data)
  } catch (err: any) {
    showError(err)
  } finally {
    loadingVehicle.value = false
  }
}

async function loadOrgs() {
  try {
    const data = await apiFetch<{ items: OrgItem[] }>('/organizations/?limit=500')
    orgsList.value = data.items ?? []
  } catch {}
}

async function save() {
  if (!vehicle.value) return
  const delta = buildDelta()
  if (Object.keys(delta).length === 0) return
  if (historyComment.value.trim()) {
    delta._history_comment = historyComment.value.trim()
  }
  saving.value = true
  try {
    const updated = await apiFetch<Vehicle>(`/vehicles/${vehicle.value.id}`, {
      method: 'PATCH',
      body: JSON.stringify(delta),
    })
    vehicle.value = updated
    vehicleOriginal.value = JSON.parse(JSON.stringify(updated))
    fillForm(updated)
    historyComment.value = ''
    showSnack('Сохранено')
  } catch (err: any) {
    showError(err)
  } finally {
    saving.value = false
  }
}

const deleteDialog = ref(false)

async function doDelete() {
  if (!vehicle.value) return
  deleting.value = true
  try {
    await apiFetch(`/vehicles/${vehicle.value.id}`, { method: 'DELETE' })
    router.push('/property/vehicles')
  } catch (err: any) {
    deleteDialog.value = false
    showError(err)
  } finally {
    deleting.value = false
  }
}

// ─────────────── Error handling ───────────────

const errorDialogShow = ref(false)
const errorMsg = ref('')
const errorCode = ref('')
const errorCorrelationId = ref('')

function showError(err: any) {
  const payload = err?.payload ?? err?.detail ?? err
  errorMsg.value = payload?.message ?? payload?.detail ?? String(err)
  errorCode.value = payload?.code ?? ''
  errorCorrelationId.value = payload?.correlation_id ?? ''
  errorDialogShow.value = true
}

function copyError() {
  const text = [
    errorMsg.value,
    errorCode.value ? `Код: ${errorCode.value}` : '',
    errorCorrelationId.value ? `ID: ${errorCorrelationId.value}` : '',
  ].filter(Boolean).join('\n')
  navigator.clipboard.writeText(text).catch(() => {})
}

// ─────────────── Snackbar ───────────────

const snack = reactive({ show: false, text: '', color: 'success' })

function showSnack(text: string, color = 'success') {
  snack.text = text
  snack.color = color
  snack.show = true
}

// ─────────────── Helpers ───────────────

function formatDate(d?: string | null): string {
  if (!d) return '—'
  try { return new Date(d).toLocaleDateString('ru-RU') } catch { return d }
}

// ─────────────── Lifecycle ───────────────

onMounted(() => {
  const id = Number(route.params.id)
  if (id) {
    loadVehicle(id)
    loadOrgs()
    loadTransferHistory(id)
  }
})

watch(() => route.params.id, (newId) => {
  const id = Number(newId)
  if (id) loadVehicle(id)
})
</script>

<style scoped>
.cursor-pointer {
  cursor: pointer;
}
</style>
