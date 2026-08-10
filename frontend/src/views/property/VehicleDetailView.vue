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
            variant="tonal"
            prepend-icon="mdi-clipboard-edit-outline"
            size="small"
            @click="$router.push(`/fleet/waybills/new?vehicle_id=${vehicleId}`)"
          >
            Создать путевой лист
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
            v-if="isAdminOrAbove"
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
        <v-tab value="checklists">
          <v-icon start>mdi-clipboard-check</v-icon>
          Чек-листы
        </v-tab>
        <v-tab value="repairs">Ремонты</v-tab>
        <v-tab value="odometer">Пробег</v-tab>
        <v-tab value="fuel">Заправки</v-tab>
        <v-tab value="trips">Путёвки</v-tab>
        <v-tab value="fines" prepend-icon="mdi-alert-octagon-outline">Штрафы</v-tab>
        <v-tab value="history">История</v-tab>
        <v-tab value="purchases">Связанные закупки</v-tab>
      </v-tabs>
      <v-divider class="mb-4" />

      <v-tabs-window v-model="activeTab">

        <!-- ─────────── Tab: Общее (Phase 29.3 redesign) ─────────── -->
        <v-tabs-window-item value="general">

          <!-- ── Hero banner ── -->
          <div class="vp-hero mb-4">
            <!-- Photo placeholder -->
            <div class="vp-hero__photo">
              <v-icon icon="mdi-camera" size="36" class="vp-hero__photo-icon" />
            </div>

            <!-- Info block -->
            <div class="vp-hero__info">
              <div class="vp-hero__title">
                {{ [vehicle.brand, vehicle.model].filter(Boolean).join(' ') || 'ТС' }}
                <span class="vp-hero__year" v-if="vehicle.year_of_manufacture">· {{ vehicle.year_of_manufacture }}</span>
              </div>
              <div class="vp-hero__meta">
                <template v-if="vehicle.color">{{ vehicle.color }}</template>
                <template v-if="vehicle.owner_org_name"> · {{ vehicle.owner_org_name }}</template>
                <template v-if="vehicle.vin"> · VIN: <span class="vp-hero__mono">{{ vehicle.vin }}</span></template>
              </div>
              <div class="d-flex align-center gap-2 flex-wrap mt-2">
                <LicensePlate :model-value="vehicle.plate" size="lg" />
                <v-chip
                  v-if="vehicle.type"
                  size="small"
                  variant="flat"
                  class="vp-chip-glass"
                  prepend-icon="mdi-car-info"
                >{{ TYPE_LABEL[vehicle.type] ?? vehicle.type }}</v-chip>
                <v-chip
                  v-if="vehicle.insurance_until"
                  size="small"
                  variant="flat"
                  :class="isInsuranceExpiringSoon ? 'vp-chip-warn' : 'vp-chip-glass'"
                  prepend-icon="mdi-shield-check"
                >ОСАГО до {{ formatDate(vehicle.insurance_until) }}</v-chip>
                <v-chip
                  v-if="vehicle.next_to_km && vehicle.current_odometer_km"
                  size="small"
                  variant="flat"
                  :class="isToSoon ? 'vp-chip-warn' : 'vp-chip-glass'"
                  prepend-icon="mdi-wrench"
                >ТО через {{ (vehicle.next_to_km - vehicle.current_odometer_km).toLocaleString('ru-RU') }} км</v-chip>
              </div>
            </div>

            <!-- Status pill (right) -->
            <div class="vp-hero__status">
              <div class="vp-status-pill" :class="`vp-status-pill--${vehicle.state ?? 'unknown'}`">
                <span class="vp-status-pill__dot"></span>
                {{ STATE_LABEL[vehicle.state ?? ''] ?? vehicle.state ?? 'Неизвестно' }}
              </div>
              <div class="vp-hero__status-sub">
                Состояние<br>
                <span v-if="vehicle.updated_at" class="vp-hero__status-date">{{ formatDate(vehicle.updated_at) }}</span>
              </div>
            </div>
          </div>

          <!-- ── Quick-stats strip ── -->
          <div class="vp-qstats mb-4">
            <!-- Пробег -->
            <div class="vp-qs">
              <div class="vp-qs__label">Пробег</div>
              <div class="vp-qs__value">
                {{ vehicle.current_odometer_km != null ? vehicle.current_odometer_km.toLocaleString('ru-RU') : '—' }}
                <span class="vp-qs__unit" v-if="vehicle.current_odometer_km != null">км</span>
              </div>
              <div class="vp-qs__sub">текущий одометр</div>
            </div>
            <!-- Последнее ТО -->
            <div class="vp-qs">
              <div class="vp-qs__label">Последнее ТО</div>
              <div class="vp-qs__value">{{ vehicle.last_to_date ? formatDate(vehicle.last_to_date) : '—' }}</div>
              <div class="vp-qs__sub" v-if="vehicle.last_to_mileage_km">на {{ vehicle.last_to_mileage_km.toLocaleString('ru-RU') }} км</div>
              <div class="vp-qs__sub" v-else>дата не указана</div>
            </div>
            <!-- След ТО -->
            <div class="vp-qs" :class="isToSoon ? 'vp-qs--warn' : ''">
              <div class="vp-qs__label">След. ТО (план)</div>
              <div class="vp-qs__value">
                {{ vehicle.next_to_km != null ? `~ ${vehicle.next_to_km.toLocaleString('ru-RU')} км` : '—' }}
              </div>
              <div class="vp-qs__sub" v-if="vehicle.next_to_km != null && vehicle.current_odometer_km != null">
                через ≈ {{ Math.max(0, vehicle.next_to_km - vehicle.current_odometer_km).toLocaleString('ru-RU') }} км
              </div>
              <div class="vp-qs__sub" v-else>данных нет</div>
            </div>
            <!-- Документы -->
            <div class="vp-qs" :class="docsStatus.hasProblems ? 'vp-qs--warn' : ''">
              <div class="vp-qs__label">Документы</div>
              <div class="vp-qs__value">{{ docsStatus.filled }} <span class="vp-qs__unit">/ 4</span></div>
              <div class="vp-qs__sub" :class="docsStatus.hasProblems ? 'vp-qs__sub--warn' : ''">
                {{ docsStatus.problemText }}
              </div>
            </div>
          </div>

          <!-- ── 2-column layout ── -->
          <v-row>
            <!-- LEFT column -->
            <v-col cols="12" md="7">

              <!-- Основные данные (inline-edit) -->
              <v-card class="vp-box mb-4">
                <v-card-title class="vp-box__title">
                  <v-icon icon="mdi-car-info" size="small" class="mr-2" />
                  Основные данные
                </v-card-title>
                <v-card-text class="pa-0">
                  <div class="vp-data-grid">
                    <!-- Гос. номер -->
                    <div class="vp-data-row">
                      <span class="vp-data-key">
                        <FieldLabel label="Гос. номер" field-key="plate" :vehicle-id="vehicle.id" />
                      </span>
                      <span class="vp-data-val">
                        <LicensePlate v-model="form.plate" :readonly="false" />
                      </span>
                    </div>
                    <!-- VIN -->
                    <div class="vp-data-row">
                      <span class="vp-data-key">
                        <FieldLabel label="VIN" field-key="vin" :vehicle-id="vehicle.id" />
                      </span>
                      <span class="vp-data-val">
                        <v-text-field v-model="form.vin" variant="underlined" density="compact" hide-details class="vp-inline-field vp-mono-field" placeholder="—" />
                      </span>
                    </div>
                    <!-- Марка -->
                    <div class="vp-data-row">
                      <span class="vp-data-key">
                        <FieldLabel label="Марка" field-key="brand" :vehicle-id="vehicle.id" />
                      </span>
                      <span class="vp-data-val">
                        <v-combobox v-model="form.brand" :items="brandSuggestions" variant="underlined" density="compact" hide-details clearable auto-select-first :return-object="false" class="vp-inline-field" placeholder="—" />
                      </span>
                    </div>
                    <!-- Модель -->
                    <div class="vp-data-row">
                      <span class="vp-data-key">
                        <FieldLabel label="Модель" field-key="model" :vehicle-id="vehicle.id" />
                      </span>
                      <span class="vp-data-val">
                        <v-combobox v-model="form.model" :items="filteredModelSuggestions" variant="underlined" density="compact" hide-details clearable auto-select-first :return-object="false" class="vp-inline-field" placeholder="—" />
                      </span>
                    </div>
                    <!-- Год -->
                    <div class="vp-data-row">
                      <span class="vp-data-key">
                        <FieldLabel label="Год выпуска" field-key="year_of_manufacture" :vehicle-id="vehicle.id" />
                      </span>
                      <span class="vp-data-val">
                        <v-combobox v-model="form.year_of_manufacture" :items="yearOptions" variant="underlined" density="compact" hide-details clearable auto-select-first :return-object="false" class="vp-inline-field" placeholder="—" />
                      </span>
                    </div>
                    <!-- Цвет -->
                    <div class="vp-data-row">
                      <span class="vp-data-key">
                        <FieldLabel label="Цвет" field-key="color" :vehicle-id="vehicle.id" />
                      </span>
                      <span class="vp-data-val">
                        <v-combobox v-model="form.color" :items="colorSuggestions" variant="underlined" density="compact" hide-details clearable auto-select-first :return-object="false" class="vp-inline-field" placeholder="—" />
                      </span>
                    </div>
                    <!-- Тип ТС -->
                    <div class="vp-data-row">
                      <span class="vp-data-key">
                        <FieldLabel label="Тип ТС" field-key="type" :vehicle-id="vehicle.id" />
                      </span>
                      <span class="vp-data-val">
                        <v-select v-model="form.type" :items="typeOptions" item-title="label" item-value="value" variant="underlined" density="compact" hide-details clearable class="vp-inline-field" placeholder="—" />
                      </span>
                    </div>
                    <!-- Состояние -->
                    <div class="vp-data-row">
                      <span class="vp-data-key">
                        <FieldLabel label="Состояние" field-key="state" :vehicle-id="vehicle.id" />
                      </span>
                      <span class="vp-data-val">
                        <v-select v-model="form.state" :items="stateOptions" item-title="label" item-value="value" variant="underlined" density="compact" hide-details clearable class="vp-inline-field" placeholder="—" />
                      </span>
                    </div>
                    <!-- Организация-владелец -->
                    <div class="vp-data-row">
                      <span class="vp-data-key">
                        <FieldLabel label="Владелец" field-key="owner_org_id" :vehicle-id="vehicle.id" />
                      </span>
                      <span class="vp-data-val">
                        <v-autocomplete v-model="form.owner_org_id" :items="orgsList" item-title="name" item-value="id" variant="underlined" density="compact" hide-details clearable class="vp-inline-field" placeholder="—" />
                      </span>
                    </div>
                    <!-- Эксплуатант -->
                    <div class="vp-data-row">
                      <span class="vp-data-key">
                        <FieldLabel label="Эксплуатант" field-key="assigned_org_id" :vehicle-id="vehicle.id" />
                      </span>
                      <span class="vp-data-val">
                        <v-autocomplete v-if="form.assigned_org_id || orgsList.length > 0" v-model="form.assigned_org_id" :items="orgsList" item-title="name" item-value="id" variant="underlined" density="compact" hide-details clearable class="vp-inline-field" placeholder="—" />
                        <v-combobox v-else v-model="form.assigned_text" :items="assignedTextSuggestions" variant="underlined" density="compact" hide-details clearable auto-select-first :return-object="false" class="vp-inline-field" placeholder="—" />
                      </span>
                    </div>
                    <!-- Эксплуатант текст если нет org_id -->
                    <div class="vp-data-row" v-if="!form.assigned_org_id">
                      <span class="vp-data-key">
                        <span class="text-caption text-medium-emphasis">Эксплуатант (текст)</span>
                      </span>
                      <span class="vp-data-val">
                        <v-combobox v-model="form.assigned_text" :items="assignedTextSuggestions" variant="underlined" density="compact" hide-details clearable auto-select-first :return-object="false" class="vp-inline-field" placeholder="—" />
                      </span>
                    </div>
                    <!-- Основание -->
                    <div class="vp-data-row">
                      <span class="vp-data-key">
                        <FieldLabel label="Основание" field-key="assignment_basis" :vehicle-id="vehicle.id" />
                      </span>
                      <span class="vp-data-val">
                        <v-combobox v-model="form.assignment_basis" :items="basisSuggestions" variant="underlined" density="compact" hide-details clearable auto-select-first :return-object="false" class="vp-inline-field" placeholder="Договор аренды, акт п/п..." />
                      </span>
                    </div>
                    <!-- Дата регистрации -->
                    <div class="vp-data-row">
                      <span class="vp-data-key">
                        <FieldLabel label="Дата регистрации" field-key="registered_at" :vehicle-id="vehicle.id" />
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

              <!-- Чек-лист оборудования -->
              <v-card class="vp-box mb-4">
                <v-card-title class="vp-box__title">
                  <v-icon icon="mdi-clipboard-check-outline" size="small" class="mr-2" />
                  Чек-лист оборудования
                </v-card-title>
                <v-card-text>
                  <div class="vp-check-grid">
                    <div class="vp-check-item" :class="form.has_tracker ? 'vp-check-item--ok' : 'vp-check-item--off'">
                      <v-checkbox v-model="form.has_tracker" label="Трекер" density="compact" hide-details color="success" />
                    </div>
                    <div class="vp-check-item" :class="form.akb_ok ? 'vp-check-item--ok' : 'vp-check-item--off'">
                      <v-checkbox v-model="form.akb_ok" label="АКБ исправен" density="compact" hide-details color="success" />
                    </div>
                    <div class="vp-check-item" :class="form.has_radio ? 'vp-check-item--ok' : 'vp-check-item--off'">
                      <v-checkbox v-model="form.has_radio" label="Радиостанция" density="compact" hide-details color="success" />
                    </div>
                    <div class="vp-check-item" :class="form.mirrors_ok ? 'vp-check-item--ok' : 'vp-check-item--off'">
                      <v-checkbox v-model="form.mirrors_ok" label="Зеркала OK" density="compact" hide-details color="success" />
                    </div>
                    <div class="vp-check-item" :class="form.has_keys ? 'vp-check-item--ok' : 'vp-check-item--off'">
                      <v-checkbox v-model="form.has_keys" label="Ключи" density="compact" hide-details color="success" />
                    </div>
                    <div class="vp-check-item" :class="form.has_first_aid_kit ? 'vp-check-item--ok' : 'vp-check-item--off'">
                      <v-checkbox v-model="form.has_first_aid_kit" label="Аптечка" density="compact" hide-details color="success" />
                    </div>
                    <div class="vp-check-item" :class="form.has_spare_wheel ? 'vp-check-item--ok' : 'vp-check-item--off'">
                      <v-checkbox v-model="form.has_spare_wheel" label="Зап. колесо" density="compact" hide-details color="success" />
                    </div>
                    <div class="vp-check-item" :class="form.has_extinguisher ? 'vp-check-item--ok' : 'vp-check-item--off'">
                      <v-checkbox v-model="form.has_extinguisher" label="Огнетушитель" density="compact" hide-details color="success" />
                    </div>
                  </div>

                  <!-- Доп. параметры -->
                  <v-divider class="my-3" />
                  <div class="text-subtitle-2 font-weight-bold mb-2">Доп. параметры</div>
                  <v-row dense>
                    <v-col cols="6">
                      <div class="text-caption text-medium-emphasis mb-1">Авторезина</div>
                      <v-combobox v-model="form.props_tires_type" :items="tiresTypeOptions" variant="outlined" density="compact" hide-details clearable auto-select-first :return-object="false" />
                    </v-col>
                    <v-col cols="6">
                      <div class="text-caption text-medium-emphasis mb-1">Брендирование</div>
                      <v-combobox v-model="form.props_branding" :items="brandSuggestions" variant="outlined" density="compact" hide-details clearable auto-select-first :return-object="false" />
                    </v-col>
                    <v-col cols="6">
                      <div class="text-caption text-medium-emphasis mb-1">ЛКП (состояние)</div>
                      <v-select v-model="form.props_paint_condition" :items="paintConditionOptions" variant="outlined" density="compact" hide-details clearable />
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

              <!-- История передач -->
              <v-card class="vp-box mb-4">
                <v-card-title class="vp-box__title">
                  <v-icon icon="mdi-swap-horizontal" size="small" class="mr-2" />
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
                        <template v-if="item.from_owner_org_id !== item.to_owner_org_id">— смена владельца</template>
                        <template v-else>— смена эксплуатанта</template>
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
                      <div v-if="item.comment" class="text-caption text-medium-emphasis">{{ item.comment }}</div>
                    </v-timeline-item>
                  </v-timeline>
                </v-card-text>
              </v-card>

              <!-- ── [Slice 2] Последний чек-лист водителя ── -->
              <v-card class="vp-box mb-4">
                <v-card-title class="vp-box__title">
                  <v-icon icon="mdi-clipboard-check-outline" size="small" class="mr-2" />
                  Последний чек-лист водителя
                  <v-chip
                    v-if="lastChecklist"
                    :color="overallStateColor(lastChecklist.overall_state)"
                    size="x-small"
                    variant="tonal"
                    class="ml-2"
                  >{{ OVERALL_STATE_LABELS[lastChecklist.overall_state ?? ''] ?? lastChecklist.overall_state ?? '—' }}</v-chip>
                  <span class="vp-box-sub ml-auto" v-if="lastChecklist">{{ formatDate(lastChecklist.created_at) }}</span>
                </v-card-title>
                <v-card-text>
                  <div v-if="!lastChecklist" class="text-medium-emphasis text-body-2 py-2">
                    Чек-листов пока нет
                  </div>
                  <template v-else>
                    <div class="vp-cl-grid">
                      <div
                        v-for="key in ['akb','tires','mirrors','radio','firstaid','extinguisher','spare','lkp']"
                        :key="key"
                        class="vp-cl-item"
                        :class="checkItemClass(clItemStatus(lastChecklist.items, key))"
                      >
                        <span class="vp-cl-label">{{ CHECKLIST_KEY_LABELS[key] }}</span>
                        <span class="vp-cl-badge">
                          <template v-if="clItemStatus(lastChecklist.items, key) === 'ok'">✓</template>
                          <template v-else-if="clItemStatus(lastChecklist.items, key) === 'issue'">?</template>
                          <template v-else>✗</template>
                        </span>
                      </div>
                    </div>
                    <div class="d-flex gap-2 flex-wrap mt-3">
                      <v-chip v-if="lastChecklist.fuel_level" size="small" variant="tonal" color="blue-grey">
                        Топливо: {{ FUEL_LABELS[lastChecklist.fuel_level] ?? lastChecklist.fuel_level }}
                      </v-chip>
                      <v-chip v-if="lastChecklist.paint_condition" size="small" variant="tonal" color="blue-grey">
                        ЛКП: {{ lastChecklist.paint_condition }}
                      </v-chip>
                    </div>
                    <div v-if="lastChecklist.notes" class="text-caption text-medium-emphasis mt-2">{{ lastChecklist.notes }}</div>
                  </template>
                </v-card-text>
              </v-card>

              <!-- ── [Slice 2] История пробега (sparkline) ── -->
              <v-card class="vp-box mb-4">
                <v-card-title class="vp-box__title">
                  <v-icon icon="mdi-chart-line" size="small" class="mr-2" />
                  История пробега
                  <span class="vp-box-sub ml-auto">последние {{ sparkPoints.length }} записей</span>
                </v-card-title>
                <v-card-text>
                  <div v-if="sparkPoints.length < 2" class="text-medium-emphasis text-body-2 py-2 text-center">
                    Недостаточно данных для графика (нужно минимум 2 записи)
                  </div>
                  <template v-else>
                    <div class="vp-spark-wrap">
                      <svg class="vp-spark" viewBox="0 0 600 96" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
                        <defs>
                          <linearGradient id="vp-spark-grad" x1="0" x2="0" y1="0" y2="1">
                            <stop offset="0%" stop-color="#6aa6ff" stop-opacity="0.5"/>
                            <stop offset="100%" stop-color="#6aa6ff" stop-opacity="0"/>
                          </linearGradient>
                        </defs>
                        <path :d="sparkAreaPath" fill="url(#vp-spark-grad)" />
                        <polyline :points="sparkPolyline" stroke="#6aa6ff" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round" />
                        <circle v-if="sparkLastPoint" :cx="sparkLastPoint.x" :cy="sparkLastPoint.y" r="4" fill="#6aa6ff" stroke="white" stroke-width="2" />
                      </svg>
                      <div class="vp-spark-axis">
                        <span v-for="(lbl, i) in sparkAxisLabels" :key="i">{{ lbl }}</span>
                      </div>
                    </div>
                    <div v-if="sparkStats" class="vp-spark-footer">
                      <div>
                        <span class="vp-spark-big">+{{ sparkStats.totalKm.toLocaleString('ru-RU') }} км</span>
                        <span class="vp-spark-sub">за период</span>
                      </div>
                      <div>
                        <span class="vp-spark-med">~{{ sparkStats.avgPerMonth.toLocaleString('ru-RU') }} км/мес</span>
                        <span class="vp-spark-sub">средний</span>
                      </div>
                      <div>
                        <span class="vp-spark-med vp-spark-ok">+{{ sparkStats.lastDelta.toLocaleString('ru-RU') }} км</span>
                        <span class="vp-spark-sub">последний интервал</span>
                      </div>
                    </div>
                  </template>
                </v-card-text>
              </v-card>

              <!-- ── [Slice 2] Лента событий (timeline) ── -->
              <v-card class="vp-box mb-4">
                <v-card-title class="vp-box__title">
                  <v-icon icon="mdi-timeline-text-outline" size="small" class="mr-2" />
                  Лента событий
                  <span class="vp-box-sub ml-auto">последние 8</span>
                </v-card-title>
                <v-card-text>
                  <div v-if="timelineEvents.length === 0" class="text-medium-emphasis text-body-2 py-2">
                    Событий пока нет
                  </div>
                  <div v-else class="vp-tl">
                    <div
                      v-for="(ev, i) in timelineEvents"
                      :key="i"
                      class="vp-tl-item"
                      :class="`vp-tl-item--${ev.dotClass}`"
                    >
                      <div class="vp-tl-dot" :class="`vp-tl-dot--${ev.dotClass}`"></div>
                      <div class="vp-tl-content">
                        <div class="vp-tl-title">{{ ev.title }}</div>
                        <div v-if="ev.body" class="vp-tl-body">{{ ev.body }}</div>
                        <time class="vp-tl-time">{{ formatDate(ev.date) }}</time>
                      </div>
                    </div>
                  </div>
                </v-card-text>
              </v-card>

            </v-col>

            <!-- RIGHT column (aside) -->
            <v-col cols="12" md="5">

              <!-- Ответственный за ТС -->
              <v-card class="vp-box mb-4">
                <v-card-title class="vp-box__title">
                  <v-icon icon="mdi-account-hard-hat" size="small" class="mr-2" />
                  Ответственный за ТС
                </v-card-title>
                <v-card-text>
                  <div class="vp-resp-card" v-if="vehicle.assigned_org_name || vehicle.owner_org_name">
                    <div class="vp-resp-avatar">
                      {{ respInitials }}
                    </div>
                    <div>
                      <div class="vp-resp-name">{{ vehicle.assigned_org_name || vehicle.owner_org_name }}</div>
                      <div class="vp-resp-role">
                        <span v-if="vehicle.assigned_org_name">Эксплуатант</span>
                        <span v-else>Владелец</span>
                      </div>
                    </div>
                  </div>
                  <div v-else class="text-medium-emphasis text-body-2">не назначен</div>
                </v-card-text>
              </v-card>

              <!-- Документы и сроки -->
              <v-card class="vp-box mb-4">
                <v-card-title class="vp-box__title">
                  <v-icon icon="mdi-file-document-outline" size="small" class="mr-2" />
                  Документы и сроки
                </v-card-title>
                <v-card-text class="px-3 py-2">
                  <div class="vp-docs">
                    <!-- ОСАГО -->
                    <div class="vp-doc-row">
                      <span class="vp-doc-dot" :class="docDotClass(vehicle.insurance_until)"></span>
                      <div class="vp-doc-info">
                        <div class="vp-doc-name">ОСАГО</div>
                        <div class="vp-doc-sub">
                          <span v-if="vehicle.insurance_until">до {{ formatDate(vehicle.insurance_until) }}</span>
                          <span v-else>не указано</span>
                        </div>
                      </div>
                      <div class="vp-doc-right">
                        <b v-if="vehicle.insurance_until">{{ daysLeft(vehicle.insurance_until) }}</b>
                        <b v-else style="opacity:.45">—</b>
                      </div>
                    </div>
                    <!-- Техосмотр -->
                    <div class="vp-doc-row">
                      <span class="vp-doc-dot" :class="docDotClass(vehicle.tech_inspection_until)"></span>
                      <div class="vp-doc-info">
                        <div class="vp-doc-name">Техосмотр</div>
                        <div class="vp-doc-sub">
                          <span v-if="vehicle.tech_inspection_until">до {{ formatDate(vehicle.tech_inspection_until) }}</span>
                          <span v-else>отсутствует</span>
                        </div>
                      </div>
                      <div class="vp-doc-right">
                        <b v-if="vehicle.tech_inspection_until">{{ daysLeft(vehicle.tech_inspection_until) }}</b>
                        <b v-else class="vp-doc-alert">нет</b>
                      </div>
                    </div>
                    <!-- ПТС -->
                    <div class="vp-doc-row">
                      <span class="vp-doc-dot" :class="vehicle.pts_number ? 'vp-dot--ok' : 'vp-dot--alert'"></span>
                      <div class="vp-doc-info">
                        <div class="vp-doc-name">ПТС</div>
                        <div class="vp-doc-sub">
                          <span v-if="vehicle.pts_number" class="vp-mono-sm">{{ vehicle.pts_number }}</span>
                          <span v-else>не указан</span>
                        </div>
                      </div>
                      <div class="vp-doc-right"><b v-if="vehicle.pts_number">OK</b><b v-else class="vp-doc-alert">—</b></div>
                    </div>
                    <!-- СТС -->
                    <div class="vp-doc-row">
                      <span class="vp-doc-dot" :class="vehicle.sts_number ? 'vp-dot--ok' : 'vp-dot--alert'"></span>
                      <div class="vp-doc-info">
                        <div class="vp-doc-name">СТС</div>
                        <div class="vp-doc-sub">
                          <span v-if="vehicle.sts_number" class="vp-mono-sm">{{ vehicle.sts_number }}</span>
                          <span v-else>не указан</span>
                        </div>
                      </div>
                      <div class="vp-doc-right"><b v-if="vehicle.sts_number">OK</b><b v-else class="vp-doc-alert">—</b></div>
                    </div>
                  </div>
                </v-card-text>
              </v-card>

              <!-- Документы для редактирования (свёрнуто) -->
              <v-card class="vp-box mb-4">
                <v-card-title class="vp-box__title">
                  <v-icon icon="mdi-pencil-outline" size="small" class="mr-2" />
                  Редактировать документы
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
                      <v-select v-model="form.fuel_type" :items="fuelTypeSelectItems" item-title="title" item-value="value" variant="outlined" density="compact" hide-details clearable />
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

              <!-- ── [Slice 2] Фотогалерея ── -->
              <v-card class="vp-box mb-4">
                <v-card-title class="vp-box__title">
                  <v-icon icon="mdi-camera-outline" size="small" class="mr-2" />
                  Фотогалерея
                  <span v-if="photoCount !== null" class="vp-box-sub ml-auto">{{ photoCount }} фото</span>
                </v-card-title>
                <v-card-text>
                  <div class="vp-photos-grid">
                    <div
                      v-for="n in 4"
                      :key="n"
                      class="vp-photo-cell"
                    >
                      <v-icon icon="mdi-image-outline" size="20" class="vp-photo-icon" />
                    </div>
                  </div>
                  <v-btn
                    class="mt-3"
                    variant="tonal"
                    color="primary"
                    block
                    prepend-icon="mdi-image-multiple-outline"
                    @click="activeTab = 'photos'"
                  >
                    {{ photoCount !== null ? `Все фото (${photoCount})` : 'Открыть фото' }}
                  </v-btn>
                </v-card-text>
              </v-card>

              <!-- Быстрые действия -->
              <v-card class="vp-box mb-4">
                <v-card-title class="vp-box__title">
                  <v-icon icon="mdi-lightning-bolt" size="small" class="mr-2" />
                  Быстрые действия
                </v-card-title>
                <v-card-text class="d-flex flex-column gap-2">
                  <v-btn
                    color="primary"
                    variant="tonal"
                    prepend-icon="mdi-clipboard-edit-outline"
                    block
                    @click="$router.push(`/fleet/waybills/new?vehicle_id=${vehicleId}`)"
                  >
                    Создать путевой лист
                  </v-btn>
                  <v-btn
                    color="success"
                    variant="tonal"
                    prepend-icon="mdi-content-save"
                    block
                    :loading="saving"
                    :disabled="!isDirty"
                    @click="save"
                  >
                    Сохранить изменения
                  </v-btn>
                  <v-btn
                    v-if="isAdminOrAbove"
                    color="error"
                    variant="outlined"
                    prepend-icon="mdi-delete"
                    block
                    @click="deleteDialog = true"
                  >
                    Удалить ТС
                  </v-btn>
                </v-card-text>
              </v-card>

            </v-col>
          </v-row>

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

        <!-- ─────────── Tab: Чек-листы ─────────── -->
        <v-tabs-window-item value="checklists" :eager="false">
          <VehicleChecklistsTab :vehicle-id="vehicleId" />
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

        <!-- ─────────── Tab: Штрафы ─────────── -->
        <v-tabs-window-item value="fines" :eager="false">
          <VehicleFinesTab :vehicle-id="vehicleId" />
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
import VehicleFinesTab from '@/components/vehicles/VehicleFinesTab.vue'
import VehicleHistoryTab from '@/components/vehicles/VehicleHistoryTab.vue'
import VehicleRelatedPurchasesTab from '@/components/vehicles/VehicleRelatedPurchasesTab.vue'
import VehicleChecklistsTab from '@/components/vehicles/VehicleChecklistsTab.vue'
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import { useToast, type ToastType } from '@/composables/useToast'

// ─────────────── Types ───────────────

// ── Widget types (Slice 2) ──
interface OdometerRow {
  id: number
  date: string
  odometer_km: number
  delta_km?: number | null
  source?: string | null
  note?: string | null
}

interface ChecklistItem { id: number; key: string; status: string; note?: string }
interface Checklist {
  id: number
  vehicle_id: number
  type: string
  overall_state?: string
  fuel_level?: string
  paint_condition?: string
  notes?: string
  created_at: string
  items?: ChecklistItem[]
}

interface FieldHistoryItem {
  id: number
  vehicle_id: number
  field_key: string
  old_value: string | null
  new_value: string | null
  changed_at: string
  changed_by_user_id: number | null
  comment: string | null
}

interface TimelineEvent {
  date: string
  dotClass: 'ok' | 'warn' | 'info' | 'alert'
  title: string
  body?: string
}

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
  suv:         'Внедорожник',
  pickup:      'Пикап',
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

// Полный список типов топлива для select в карточке ТС (Phase 29.3)
const fuelTypeSelectItems = [
  { value: 'AI-92',  title: 'АИ-92' },
  { value: 'AI-95',  title: 'АИ-95' },
  { value: 'AI-98',  title: 'АИ-98' },
  { value: 'AI-100', title: 'АИ-100' },
  { value: 'DT',     title: 'Дизель' },
  { value: 'GAS',    title: 'Газ' },
  { value: 'other',  title: 'Другое' },
]

// Опции состояния ЛКП для v-select
const paintConditionOptions = [
  'Отличное',
  'Хорошее',
  'Удовлетворительное',
  'Незначительные повреждения',
  'Значительные повреждения',
  'Среднее',
  'Требует покраски',
]

// Опции авторезины для v-combobox
const tiresTypeOptions = [
  'Летняя',
  'Зимняя',
  'Всесезонная',
  'Смешанная (зима/лето)',
]

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

// Phase 29.3-R3 (Д-3): удалять ТС может только admin+
const isAdminOrAbove = computed(() => {
  const r = (authStore as any).user?.role || (authStore as any).role
  return ['admin', 'superadmin', 'account_owner'].includes(r)
})

const vehicle = ref<Vehicle | null>(null)
const vehicleOriginal = ref<Vehicle | null>(null)
const loadingVehicle = ref(false)
const vehicleId = computed(() => Number(route.params.id) || 0)
const saving = ref(false)
const deleting = ref(false)
const activeTab = ref('general')
const orgsList = ref<OrgItem[]>([])
const historyComment = ref('')

// ─────────────── Autocomplete suggestions ───────────────

const brandSuggestions = ref<string[]>([])
const modelSuggestions = ref<string[]>([])
const colorSuggestions = ref<string[]>([])
const assignedTextSuggestions = ref<string[]>([])
const basisSuggestions = ref<string[]>([])

// ─────────────── Slice-2 widget state ───────────────

const odometerRows = ref<OdometerRow[]>([])
const lastChecklist = ref<Checklist | null>(null)
const fieldHistory = ref<FieldHistoryItem[]>([])
const photoCount = ref<number | null>(null)

// Sparkline computed — last 12 odometer records sorted asc by date
const sparkPoints = computed(() => {
  const rows = [...odometerRows.value]
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
    .slice(-12)
  return rows
})

// Build SVG polyline points for 600×96 viewBox
const sparkPolyline = computed(() => {
  const pts = sparkPoints.value
  if (pts.length < 2) return ''
  const minKm = Math.min(...pts.map(p => p.odometer_km))
  const maxKm = Math.max(...pts.map(p => p.odometer_km))
  const range = maxKm - minKm || 1
  const W = 600, H = 96, PAD = 8
  return pts.map((p, i) => {
    const x = pts.length === 1 ? W / 2 : (i / (pts.length - 1)) * W
    const y = PAD + ((maxKm - p.odometer_km) / range) * (H - PAD * 2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
})

// Area path (filled) under sparkline
const sparkAreaPath = computed(() => {
  const pts = sparkPoints.value
  if (pts.length < 2) return ''
  const minKm = Math.min(...pts.map(p => p.odometer_km))
  const maxKm = Math.max(...pts.map(p => p.odometer_km))
  const range = maxKm - minKm || 1
  const W = 600, H = 96, PAD = 8
  const coords = pts.map((p, i) => {
    const x = pts.length === 1 ? W / 2 : (i / (pts.length - 1)) * W
    const y = PAD + ((maxKm - p.odometer_km) / range) * (H - PAD * 2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  return `M${coords.join(' L')} L${W},${H} L0,${H} Z`
})

// Last spark point for the terminal dot
const sparkLastPoint = computed(() => {
  const pts = sparkPoints.value
  if (pts.length < 2) return null
  const minKm = Math.min(...pts.map(p => p.odometer_km))
  const maxKm = Math.max(...pts.map(p => p.odometer_km))
  const range = maxKm - minKm || 1
  const W = 600, H = 96, PAD = 8
  const last = pts[pts.length - 1]
  const i = pts.length - 1
  const x = (i / (pts.length - 1)) * W
  const y = PAD + ((maxKm - last.odometer_km) / range) * (H - PAD * 2)
  return { x, y }
})

// Axis labels for sparkline (first, middle, last dates)
const sparkAxisLabels = computed(() => {
  const pts = sparkPoints.value
  if (pts.length < 2) return []
  const fmt = (d: string) => {
    const dt = new Date(d)
    return `${String(dt.getMonth() + 1).padStart(2, '0')}.${String(dt.getFullYear()).slice(-2)}`
  }
  const indices = [0, Math.floor((pts.length - 1) / 2), pts.length - 1]
  return [...new Set(indices)].map(i => fmt(pts[i].date))
})

// Sparkline stats
const sparkStats = computed(() => {
  const pts = sparkPoints.value
  if (pts.length < 2) return null
  const totalKm = pts[pts.length - 1].odometer_km - pts[0].odometer_km
  const months = Math.max(1, Math.round(
    (new Date(pts[pts.length - 1].date).getTime() - new Date(pts[0].date).getTime()) / (30 * 24 * 3600 * 1000)
  ))
  const avgPerMonth = Math.round(totalKm / months)
  const lastDelta = pts[pts.length - 1].delta_km ?? (pts.length >= 2 ? pts[pts.length - 1].odometer_km - pts[pts.length - 2].odometer_km : 0)
  return { totalKm, avgPerMonth, lastDelta }
})

// Checklist key labels
const CHECKLIST_KEY_LABELS: Record<string, string> = {
  akb: 'АКБ', tires: 'Резина', mirrors: 'Зеркала', radio: 'Радио',
  firstaid: 'Аптечка', extinguisher: 'Огнет.', spare: 'Запаска', lkp: 'ЛКП',
}

const FUEL_LABELS: Record<string, string> = {
  quarter: '1/4 бака', half: '1/2 бака', threequarter: '3/4 бака', full: 'Полный',
}

const OVERALL_STATE_LABELS: Record<string, string> = {
  ok: 'Рабочее', with_remarks: 'С замечаниями', not_running: 'Не на ходу',
}

// Checklist key status → dot class
function checkItemClass(status: string): string {
  if (status === 'ok') return 'vp-cl-ok'
  if (status === 'issue') return 'vp-cl-warn'
  return 'vp-cl-alert'
}

// Overall state → chip color
function overallStateColor(s?: string): string {
  if (s === 'ok') return 'success'
  if (s === 'with_remarks') return 'warning'
  if (s === 'not_running') return 'error'
  return 'grey'
}

// Get status of a checklist item by key
function clItemStatus(items: ChecklistItem[] | undefined, key: string): string {
  return items?.find(i => i.key === key)?.status ?? 'ok'
}

// ── Timeline ──
const timelineEvents = computed((): TimelineEvent[] => {
  const events: TimelineEvent[] = []

  // Odometer rows
  for (const r of odometerRows.value) {
    const prev = odometerRows.value.find(x => x.id !== r.id && new Date(x.date) < new Date(r.date))
    const delta = r.delta_km != null ? r.delta_km : (prev ? r.odometer_km - prev.odometer_km : null)
    events.push({
      date: r.date,
      dotClass: 'info',
      title: `Пробег: ${r.odometer_km.toLocaleString('ru-RU')} км${delta != null ? ` (+${delta.toLocaleString('ru-RU')})` : ''}`,
      body: r.note ?? undefined,
    })
  }

  // Checklists (only last checklist in widget data - we loaded just the last one)
  if (lastChecklist.value) {
    const cl = lastChecklist.value
    const isWarn = cl.overall_state === 'with_remarks' || cl.overall_state === 'not_running'
    events.push({
      date: cl.created_at,
      dotClass: isWarn ? 'warn' : 'ok',
      title: isWarn ? 'Чек-лист с замечаниями' : 'Чек-лист пройден',
      body: cl.notes ?? undefined,
    })
  }

  // Field history
  for (const h of fieldHistory.value) {
    events.push({
      date: h.changed_at,
      dotClass: 'info',
      title: `Изменено: ${h.field_key}`,
      body: h.comment ?? undefined,
    })
  }

  // Transfer history
  for (const t of transferHistory.value) {
    events.push({
      date: t.changed_at,
      dotClass: 'info',
      title: 'Передача ТС',
      body: [t.from_assigned_text, t.to_assigned_text].filter(Boolean).join(' → ') || undefined,
    })
  }

  return events
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
    .slice(0, 8)
})

// Модели фильтруются по выбранной марке если марка задана
const filteredModelSuggestions = computed(() => {
  if (!form.brand || modelSuggestions.value.length === 0) return modelSuggestions.value
  // Простая фильтрация: показываем все (модели не привязаны к марке в distinct)
  return modelSuggestions.value
})

// Годы от текущего до 1980 (reversed — новые сверху)
const currentYear = new Date().getFullYear()
const yearOptions = Array.from({ length: currentYear - 1980 + 1 }, (_, i) => currentYear - i)

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

// ─────────────── Quick-stats helpers (Phase 29.3 redesign) ───────────────

/** Returns how many days remain until a date string. Negative = expired. */
function daysLeftNum(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null
  const diff = new Date(dateStr).getTime() - Date.now()
  return Math.round(diff / (24 * 3600 * 1000))
}

/** Human-readable days-left label */
function daysLeft(dateStr: string | null | undefined): string {
  const n = daysLeftNum(dateStr)
  if (n === null) return '—'
  if (n < 0) return `просрочен ${Math.abs(n)} дн.`
  if (n === 0) return 'сегодня'
  return `${n} дн.`
}

/** CSS class for document dot indicator */
function docDotClass(dateStr: string | null | undefined): string {
  if (!dateStr) return 'vp-dot--alert'
  const n = daysLeftNum(dateStr) ?? 0
  if (n < 0) return 'vp-dot--alert'
  if (n < 30) return 'vp-dot--warn'
  return 'vp-dot--ok'
}

/** Initials from org name for avatar */
const respInitials = computed(() => {
  const name = vehicle.value?.assigned_org_name || vehicle.value?.owner_org_name || ''
  if (!name) return '?'
  const words = name.trim().split(/\s+/)
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase()
  return name.slice(0, 2).toUpperCase()
})

/** Document status summary for quick-stats tile */
const docsStatus = computed(() => {
  const v = vehicle.value
  if (!v) return { filled: 0, hasProblems: false, problemText: 'нет данных' }

  const now = Date.now()
  const problems: string[] = []
  let filled = 0

  // ОСАГО
  if (v.insurance_until) {
    const ok = new Date(v.insurance_until).getTime() > now
    if (ok) filled++
    else problems.push('ОСАГО истёк')
  } else {
    problems.push('нет ОСАГО')
  }

  // Техосмотр
  if (v.tech_inspection_until) {
    const ok = new Date(v.tech_inspection_until).getTime() > now
    if (ok) filled++
    else problems.push('техосмотр истёк')
  } else {
    problems.push('нет техосмотра')
  }

  // ПТС
  if (v.pts_number) filled++
  else problems.push('нет ПТС')

  // СТС
  if (v.sts_number) filled++
  else problems.push('нет СТС')

  const hasProblems = problems.length > 0
  const problemText = hasProblems ? problems[0] : 'все документы OK'

  return { filled, hasProblems, problemText }
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

async function loadSuggestions() {
  try {
    const [brands, models, colors, assignedTexts, bases] = await Promise.all([
      apiFetch<string[]>('/vehicles/distinct/brand'),
      apiFetch<string[]>('/vehicles/distinct/model'),
      apiFetch<string[]>('/vehicles/distinct/color'),
      apiFetch<string[]>('/vehicles/distinct/assigned_text'),
      apiFetch<string[]>('/vehicles/distinct/assignment_basis'),
    ])
    brandSuggestions.value = Array.isArray(brands) ? brands : []
    modelSuggestions.value = Array.isArray(models) ? models : []
    const defaultColors = ['Белый', 'Чёрный', 'Серый', 'Серебристый', 'Синий', 'Красный', 'Зелёный', 'Жёлтый', 'Коричневый', 'Бежевый']
    colorSuggestions.value = Array.from(new Set([...defaultColors, ...(Array.isArray(colors) ? colors : [])]))
    assignedTextSuggestions.value = Array.isArray(assignedTexts) ? assignedTexts : []
    const defaultBases = [
      'Договор аренды',
      'Акт приёма-передачи',
      'Договор пожертвования',
      'Договор безвозмездного пользования',
      'Закупка',
      'Передача из другой организации',
    ]
    basisSuggestions.value = Array.from(new Set([...defaultBases, ...(Array.isArray(bases) ? bases : [])]))
  } catch (e) {
    console.warn('[VehicleDetailView] loadSuggestions failed (silent):', e)
  }
}

// ─────────────── Slice-2 loaders ───────────────

async function loadOdometer(id: number) {
  try {
    const data = await apiFetch<OdometerRow[]>(`/vehicle-odometer/?vehicle_id=${id}`)
    odometerRows.value = Array.isArray(data) ? data : []
  } catch (e) {
    console.warn('[VehicleDetailView] loadOdometer failed (silent):', e)
    odometerRows.value = []
  }
}

async function loadLastChecklist(id: number) {
  try {
    const data = await apiFetch<Checklist[]>(`/checklists/?vehicle_id=${id}`)
    const arr = Array.isArray(data) ? data : []
    if (arr.length > 0) {
      lastChecklist.value = arr.reduce((best, cur) =>
        new Date(cur.created_at) > new Date(best.created_at) ? cur : best
      )
    }
  } catch (e) {
    console.warn('[VehicleDetailView] loadLastChecklist failed (silent):', e)
  }
}

async function loadFieldHistory(id: number) {
  try {
    const data = await apiFetch<FieldHistoryItem[] | { items: FieldHistoryItem[]; total: number }>(
      `/vehicles/${id}/field-history?limit=20`
    )
    const arr = Array.isArray(data) ? data : (data as { items: FieldHistoryItem[] }).items ?? []
    fieldHistory.value = arr
  } catch (e) {
    console.warn('[VehicleDetailView] loadFieldHistory failed (silent):', e)
    fieldHistory.value = []
  }
}

async function loadPhotoCount(id: number) {
  try {
    const data = await apiFetch<unknown[]>(`/vehicle-attachments/?vehicle_id=${id}`)
    photoCount.value = Array.isArray(data) ? data.length : null
  } catch {
    photoCount.value = null
  }
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

const toast = useToast()

function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
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
    loadSuggestions()
    // Slice-2 widget loaders
    loadOdometer(id)
    loadLastChecklist(id)
    loadFieldHistory(id)
    loadPhotoCount(id)
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

/* ─── Hero ─────────────────────────────────────────────────── */
.vp-hero {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 20px;
  align-items: center;
  padding: 18px 20px;
  border-radius: 16px;
  border: 1px solid rgba(0,0,0,0.08);
  background: linear-gradient(135deg, rgba(25, 118, 210, 0.12), rgba(25, 118, 210, 0.04));
  flex-wrap: wrap;
}
@media (max-width: 768px) {
  .vp-hero { grid-template-columns: 1fr; }
  .vp-hero__status { text-align: left; }
}

.vp-hero__photo {
  width: 120px;
  height: 80px;
  border-radius: 12px;
  border: 1px solid rgba(0,0,0,0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,0.04);
  flex-shrink: 0;
}
.vp-hero__photo-icon { opacity: 0.35; }

.vp-hero__title {
  font-size: 1.3rem;
  font-weight: 800;
  letter-spacing: -0.3px;
  line-height: 1.2;
}
.vp-hero__year { font-weight: 400; opacity: 0.6; }

.vp-hero__meta {
  font-size: 0.82rem;
  opacity: 0.7;
  margin: 4px 0 0;
}
.vp-hero__mono { font-family: 'JetBrains Mono', 'Courier New', monospace; font-size: 0.78rem; }

.vp-chip-glass {
  background: rgba(0,0,0,0.06) !important;
}
.vp-chip-warn {
  background: rgba(255, 193, 7, 0.2) !important;
}

/* Status pill */
.vp-hero__status { text-align: right; }
.vp-status-pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.3px;
  text-transform: uppercase;
  border: 1px solid rgba(0,0,0,0.1);
}
.vp-status-pill__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}
.vp-status-pill--working   { color: #22c997; background: rgba(34,201,151,0.1); border-color: rgba(34,201,151,0.3); }
.vp-status-pill--broken    { color: #ff5b6a; background: rgba(255,91,106,0.1); border-color: rgba(255,91,106,0.3); }
.vp-status-pill--in_repair { color: #f6b34a; background: rgba(246,179,74,0.1); border-color: rgba(246,179,74,0.3); }
.vp-status-pill--needs_repair { color: #fb923c; background: rgba(251,146,60,0.1); border-color: rgba(251,146,60,0.3); }
.vp-status-pill--destroyed { color: #9e9e9e; background: rgba(158,158,158,0.1); border-color: rgba(158,158,158,0.3); }
.vp-status-pill--utilized  { color: #9e9e9e; background: rgba(158,158,158,0.1); border-color: rgba(158,158,158,0.3); }
.vp-status-pill--unknown   { color: #9e9e9e; background: rgba(158,158,158,0.1); border-color: rgba(158,158,158,0.3); }

.vp-hero__status-sub {
  font-size: 11px;
  opacity: 0.5;
  margin-top: 6px;
  text-align: right;
  line-height: 1.4;
}
.vp-hero__status-date { font-weight: 600; }

/* ─── Quick-stats strip ────────────────────────────────────── */
.vp-qstats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
@media (max-width: 900px) { .vp-qstats { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px) { .vp-qstats { grid-template-columns: 1fr; } }

.vp-qs {
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid rgba(0,0,0,0.08);
  background: rgba(0,0,0,0.02);
}
.vp-qs--warn { box-shadow: inset 0 0 0 1px rgba(246,179,74,0.4); }

.vp-qs__label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.3px;
  text-transform: uppercase;
  opacity: 0.55;
}
.vp-qs__value {
  font-size: 1.25rem;
  font-weight: 800;
  margin-top: 4px;
  letter-spacing: -0.3px;
  line-height: 1.2;
}
.vp-qs__unit { font-size: 0.75rem; font-weight: 600; opacity: 0.5; }
.vp-qs__sub { font-size: 11.5px; opacity: 0.55; margin-top: 2px; }
.vp-qs__sub--warn { color: #f6b34a; opacity: 1; }

/* ─── Box cards ────────────────────────────────────────────── */
.vp-box { border-radius: 14px !important; }
.vp-box__title {
  font-size: 13px !important;
  font-weight: 700 !important;
  display: flex;
  align-items: center;
  padding: 14px 16px 8px !important;
}

/* ─── Inline data-grid (основные данные) ────────────────────── */
.vp-data-grid {
  display: flex;
  flex-direction: column;
}
.vp-data-row {
  display: grid;
  grid-template-columns: 1fr 1.4fr;
  gap: 8px 16px;
  align-items: center;
  padding: 6px 16px;
  border-bottom: 1px solid rgba(0,0,0,0.06);
  min-height: 46px;
}
.vp-data-row:last-child { border-bottom: none; }

.vp-data-key {
  display: flex;
  align-items: center;
}
.vp-data-val {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

/* Inline fields — underlined variant, no padding */
.vp-inline-field :deep(.v-field__input) {
  font-size: 13px;
  font-weight: 600;
  text-align: right;
  padding-top: 0;
  min-height: 28px !important;
}
.vp-inline-field :deep(.v-field--variant-underlined .v-field__outline) {
  opacity: 0.3;
}
.vp-mono-field :deep(.v-field__input) {
  font-family: 'JetBrains Mono', 'Courier New', monospace;
  font-size: 12px;
}

/* ─── Check grid ───────────────────────────────────────────── */
.vp-check-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
@media (max-width: 600px) { .vp-check-grid { grid-template-columns: repeat(2, 1fr); } }

.vp-check-item {
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 10px;
  padding: 8px 10px;
}
.vp-check-item--ok  { border-color: rgba(34,201,151,0.25); background: rgba(34,201,151,0.05); }
.vp-check-item--off { background: rgba(0,0,0,0.02); }

/* ─── Responsible card ─────────────────────────────────────── */
.vp-resp-card { display: flex; align-items: center; gap: 12px; }
.vp-resp-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: linear-gradient(135deg, #22c997, #5dd0ff);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  color: #0a0d14;
  font-size: 14px;
  flex-shrink: 0;
}
.vp-resp-name { font-weight: 700; font-size: 14px; }
.vp-resp-role { font-size: 12px; opacity: 0.55; margin-top: 2px; }

/* ─── Documents list ───────────────────────────────────────── */
.vp-docs { display: flex; flex-direction: column; gap: 6px; }
.vp-doc-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border: 1px solid rgba(0,0,0,0.07);
  border-radius: 10px;
  background: rgba(0,0,0,0.02);
}
.vp-doc-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.vp-dot--ok    { background: #22c997; }
.vp-dot--warn  { background: #f6b34a; }
.vp-dot--alert { background: #ff5b6a; }

.vp-doc-info { flex: 1; min-width: 0; }
.vp-doc-name { font-weight: 700; font-size: 13px; }
.vp-doc-sub  { font-size: 11.5px; opacity: 0.55; margin-top: 1px; }
.vp-doc-right { font-size: 11.5px; font-weight: 600; opacity: 0.65; text-align: right; white-space: nowrap; }
.vp-doc-alert { color: #ff5b6a !important; opacity: 1 !important; }
.vp-mono-sm { font-family: 'JetBrains Mono', monospace; font-size: 11px; }

/* ─── Slice-2 box subtitle ────────────────────────────────── */
.vp-box-sub {
  font-size: 11.5px;
  font-weight: 500;
  opacity: 0.5;
}

/* ─── Checklist grid ───────────────────────────────────────── */
.vp-cl-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
@media (max-width: 500px) { .vp-cl-grid { grid-template-columns: repeat(2, 1fr); } }

.vp-cl-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  border: 1px solid rgba(0,0,0,0.07);
  border-radius: 10px;
  padding: 8px 10px;
  background: rgba(0,0,0,0.02);
}
.vp-cl-label { font-size: 12px; font-weight: 600; opacity: 0.7; }
.vp-cl-badge {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 13px;
  flex-shrink: 0;
}
.vp-cl-ok  .vp-cl-badge { background: rgba(34,201,151,0.15); color: #22c997; }
.vp-cl-warn .vp-cl-badge { background: rgba(246,179,74,0.15); color: #f6b34a; }
.vp-cl-alert .vp-cl-badge { background: rgba(255,91,106,0.15); color: #ff5b6a; }
.vp-cl-ok   { border-color: rgba(34,201,151,0.2); background: rgba(34,201,151,0.04); }
.vp-cl-warn { border-color: rgba(246,179,74,0.2); background: rgba(246,179,74,0.04); }
.vp-cl-alert { border-color: rgba(255,91,106,0.2); background: rgba(255,91,106,0.04); }

/* ─── Sparkline ────────────────────────────────────────────── */
.vp-spark-wrap {
  position: relative;
  height: 120px;
}
.vp-spark {
  width: 100%;
  height: 96px;
  display: block;
}
.vp-spark-axis {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  font-weight: 500;
  opacity: 0.5;
}
.vp-spark-footer {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(0,0,0,0.07);
  font-size: 12px;
  gap: 8px;
  flex-wrap: wrap;
}
.vp-spark-footer > div { display: flex; flex-direction: column; gap: 2px; }
.vp-spark-big { font-size: 17px; font-weight: 800; letter-spacing: -0.3px; }
.vp-spark-med { font-size: 13px; font-weight: 700; }
.vp-spark-ok  { color: #22c997; }
.vp-spark-sub { font-size: 11px; opacity: 0.5; }

/* ─── Timeline ─────────────────────────────────────────────── */
.vp-tl {
  display: flex;
  flex-direction: column;
  gap: 0;
  position: relative;
  padding-left: 20px;
}
.vp-tl::before {
  content: '';
  position: absolute;
  left: 5px;
  top: 8px;
  bottom: 8px;
  width: 1px;
  background: rgba(0,0,0,0.1);
}
.vp-tl-item {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 0 12px;
}
.vp-tl-dot {
  position: absolute;
  left: -20px;
  top: 13px;
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: white;
  border: 2px solid #9e9e9e;
  flex-shrink: 0;
}
.vp-tl-dot--ok    { border-color: #22c997; }
.vp-tl-dot--warn  { border-color: #f6b34a; }
.vp-tl-dot--alert { border-color: #ff5b6a; }
.vp-tl-dot--info  { border-color: #5dd0ff; }

.vp-tl-content { flex: 1; min-width: 0; }
.vp-tl-title { font-weight: 700; font-size: 13.5px; line-height: 1.3; }
.vp-tl-body  { font-size: 12.5px; opacity: 0.6; margin-top: 2px; line-height: 1.4; }
.vp-tl-time  { font-size: 11.5px; opacity: 0.45; font-weight: 500; display: block; margin-top: 3px; }

/* ─── Photo gallery ────────────────────────────────────────── */
.vp-photos-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.vp-photo-cell {
  aspect-ratio: 1;
  border-radius: 10px;
  border: 1px solid rgba(0,0,0,0.08);
  background: rgba(0,0,0,0.03);
  display: flex;
  align-items: center;
  justify-content: center;
}
.vp-photo-icon { opacity: 0.25; }

/* ─── Dark theme overrides ─────────────────────────────────── */
.v-theme--dark .vp-hero {
  background: linear-gradient(135deg, rgba(106,166,255,0.1), rgba(106,166,255,0.04));
  border-color: rgba(255,255,255,0.08);
}
.v-theme--dark .vp-hero__photo {
  background: rgba(255,255,255,0.06);
  border-color: rgba(255,255,255,0.1);
}
.v-theme--dark .vp-chip-glass { background: rgba(255,255,255,0.08) !important; }
.v-theme--dark .vp-chip-warn  { background: rgba(255,193,7,0.2)  !important; }

.v-theme--dark .vp-qs {
  background: rgba(255,255,255,0.03);
  border-color: rgba(255,255,255,0.08);
}
.v-theme--dark .vp-qs--warn { box-shadow: inset 0 0 0 1px rgba(246,179,74,0.35); }

.v-theme--dark .vp-box { background: rgba(255,255,255,0.03) !important; }

.v-theme--dark .vp-data-row { border-bottom-color: rgba(255,255,255,0.06); }

.v-theme--dark .vp-check-item {
  border-color: rgba(255,255,255,0.07);
  background: rgba(255,255,255,0.02);
}
.v-theme--dark .vp-check-item--ok {
  border-color: rgba(34,201,151,0.25);
  background: rgba(34,201,151,0.07);
}

.v-theme--dark .vp-doc-row {
  border-color: rgba(255,255,255,0.07);
  background: rgba(255,255,255,0.02);
}
.v-theme--dark .vp-status-pill { border-width: 1px; }

/* ─── Dark: Slice-2 widgets ───────────────────────────────── */
.v-theme--dark .vp-cl-item {
  background: rgba(255,255,255,0.03);
  border-color: rgba(255,255,255,0.07);
}
.v-theme--dark .vp-cl-ok    { border-color: rgba(34,201,151,0.25);  background: rgba(34,201,151,0.07); }
.v-theme--dark .vp-cl-warn  { border-color: rgba(246,179,74,0.25);  background: rgba(246,179,74,0.07); }
.v-theme--dark .vp-cl-alert { border-color: rgba(255,91,106,0.25);  background: rgba(255,91,106,0.07); }

.v-theme--dark .vp-spark-footer { border-top-color: rgba(255,255,255,0.07); }

.v-theme--dark .vp-tl::before { background: rgba(255,255,255,0.1); }
.v-theme--dark .vp-tl-dot { background: #1e2130; }

.v-theme--dark .vp-photo-cell {
  background: rgba(255,255,255,0.04);
  border-color: rgba(255,255,255,0.08);
}
</style>
