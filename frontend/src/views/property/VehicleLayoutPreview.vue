<template>
  <v-container fluid class="pa-6" style="max-width:1200px">

    <!-- Loading -->
    <div v-if="loading" class="text-center py-16">
      <v-progress-circular indeterminate size="48" color="primary" />
    </div>

    <template v-else-if="vehicle">

      <!-- ── Top bar ── -->
      <div class="d-flex align-center justify-space-between mb-4 flex-wrap gap-2">
        <div>
          <h1 class="text-h5 font-weight-bold">
            {{ [vehicle.brand, vehicle.model].filter(Boolean).join(' ') || 'ТС' }}
            <span class="text-medium-emphasis">· {{ vehicle.plate }}</span>
          </h1>
          <span class="text-caption text-medium-emphasis">Сравнение вариантов layout карточки</span>
        </div>
        <div class="d-flex align-center gap-2">
          <v-chip color="warning" variant="tonal" size="small" prepend-icon="mdi-test-tube">
            Тестовый режим — для согласования дизайна
          </v-chip>
          <v-btn variant="outlined" prepend-icon="mdi-arrow-left" size="small"
            @click="router.push('/property/vehicles')">
            Назад к списку
          </v-btn>
        </div>
      </div>

      <!-- ── Variant switcher ── -->
      <v-card variant="outlined" class="mb-6 pa-4">
        <div class="text-subtitle-2 font-weight-bold mb-3">Выберите вариант layout:</div>
        <v-btn-toggle v-model="variant" mandatory color="primary" variant="outlined" divided class="flex-wrap mb-3">
          <v-btn value="1" size="small">Вариант 1 — Stacked</v-btn>
          <v-btn value="2" size="small">Вариант 2 — 2-column grid</v-btn>
          <v-btn value="3" size="small">
            Вариант 3 — Hero + 2-col
            <v-chip size="x-small" color="success" class="ml-2">Рекомендую</v-chip>
          </v-btn>
          <v-btn value="4" size="small">Вариант 4 — Accordion</v-btn>
        </v-btn-toggle>
        <div class="text-body-2 text-medium-emphasis">{{ variantDesc }}</div>
      </v-card>

      <!-- ════════════════════════════════════════════════════════
           ВАРИАНТ 1 — Stacked
           ════════════════════════════════════════════════════════ -->
      <template v-if="variant === '1'">

        <!-- Идентификация -->
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
            <v-icon icon="mdi-car-info" size="small" class="mr-1" />
            Идентификация
          </v-card-title>
          <v-card-text>
            <v-row dense>
              <v-col cols="12" md="4">
                <div class="text-caption text-medium-emphasis mb-1">Гос. номер</div>
                <div class="font-weight-bold font-mono text-body-1 pa-2 rounded"
                  style="background:#1f2937;color:#fff;display:inline-block;letter-spacing:2px">
                  {{ vehicle.plate }}
                </div>
              </v-col>
              <v-col cols="12" md="4">
                <ReadField label="Марка" :value="vehicle.brand" />
              </v-col>
              <v-col cols="12" md="4">
                <ReadField label="Модель" :value="vehicle.model" />
              </v-col>
              <v-col cols="12" md="4">
                <ReadField label="Цвет" :value="vehicle.color" />
              </v-col>
              <v-col cols="12" md="4">
                <ReadField label="VIN" :value="vehicle.vin" />
              </v-col>
              <v-col cols="12" md="4">
                <ReadField label="Год выпуска" :value="vehicle.year_of_manufacture?.toString()" />
              </v-col>
              <v-col cols="12" md="4">
                <ReadField label="Тип ТС" :value="typeLabel(vehicle.type)" />
              </v-col>
              <v-col cols="12" md="4">
                <div class="text-caption text-medium-emphasis mb-1">Состояние</div>
                <v-chip :color="stateColor(vehicle.state)" size="small" variant="tonal">
                  {{ stateLabel(vehicle.state) }}
                </v-chip>
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>

        <!-- Принадлежность -->
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
            <v-icon icon="mdi-office-building" size="small" class="mr-1" />
            Принадлежность
          </v-card-title>
          <v-card-text>
            <v-row dense>
              <v-col cols="12" md="6">
                <ReadField label="Организация-владелец" :value="vehicle.owner_org_name" />
              </v-col>
              <v-col cols="12" md="6">
                <ReadField label="Организация-эксплуатант" :value="vehicle.assigned_org_name" />
              </v-col>
              <v-col cols="12">
                <ReadField label="Эксплуатант (текст)" :value="vehicle.assigned_text" />
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>

        <!-- Документы и топливо -->
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
            <v-icon icon="mdi-file-document-outline" size="small" class="mr-1" />
            Документы и топливо
          </v-card-title>
          <v-card-text>
            <v-row dense>
              <v-col cols="12" md="4">
                <ReadField label="ПТС" :value="vehicle.pts_number" />
              </v-col>
              <v-col cols="12" md="4">
                <ReadField label="СТС" :value="vehicle.sts_number" />
              </v-col>
              <v-col cols="12" md="4">
                <ReadField label="ОСАГО до" :value="formatDate(vehicle.insurance_until)" />
              </v-col>
              <v-col cols="12" md="4">
                <ReadField label="Техосмотр до" :value="formatDate(vehicle.tech_inspection_until)" />
              </v-col>
              <v-col cols="12" md="4">
                <ReadField label="Тип топлива" :value="fuelLabel(vehicle.fuel_type)" />
              </v-col>
              <v-col cols="12" md="4">
                <ReadField label="Текущий пробег, км" :value="fmtKm(vehicle.current_odometer_km)" />
              </v-col>
              <v-col cols="12" md="4">
                <ReadField label="Последнее ТО, км" :value="fmtKm(vehicle.last_to_mileage_km)" />
              </v-col>
              <v-col cols="12" md="4">
                <ReadField label="Дата последнего ТО" :value="formatDate(vehicle.last_to_date)" />
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>

        <!-- Закупка -->
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
            <v-icon icon="mdi-cart-outline" size="small" class="mr-1" />
            Закупка / прочее
          </v-card-title>
          <v-card-text>
            <ReadField label="Данные о закупке" :value="vehicle.purchase_info" />
          </v-card-text>
        </v-card>

      </template>

      <!-- ════════════════════════════════════════════════════════
           ВАРИАНТ 2 — 2-column grid
           ════════════════════════════════════════════════════════ -->
      <template v-else-if="variant === '2'">

        <v-row>
          <!-- Идентификация -->
          <v-col cols="12" md="6">
            <v-card variant="outlined" class="h-100">
              <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
                <v-icon icon="mdi-car-info" size="small" class="mr-1" />
                Идентификация
              </v-card-title>
              <v-card-text>
                <div class="mb-3">
                  <div class="text-caption text-medium-emphasis mb-1">Гос. номер</div>
                  <div class="font-weight-bold font-mono text-body-1 pa-2 rounded"
                    style="background:#1f2937;color:#fff;display:inline-block;letter-spacing:2px">
                    {{ vehicle.plate }}
                  </div>
                </div>
                <v-row dense>
                  <v-col cols="6"><ReadField label="Марка" :value="vehicle.brand" /></v-col>
                  <v-col cols="6"><ReadField label="Модель" :value="vehicle.model" /></v-col>
                  <v-col cols="6"><ReadField label="Цвет" :value="vehicle.color" /></v-col>
                  <v-col cols="6"><ReadField label="Год вып." :value="vehicle.year_of_manufacture?.toString()" /></v-col>
                  <v-col cols="12"><ReadField label="VIN" :value="vehicle.vin" /></v-col>
                  <v-col cols="6"><ReadField label="Тип ТС" :value="typeLabel(vehicle.type)" /></v-col>
                  <v-col cols="6">
                    <div class="text-caption text-medium-emphasis mb-1">Состояние</div>
                    <v-chip :color="stateColor(vehicle.state)" size="small" variant="tonal">
                      {{ stateLabel(vehicle.state) }}
                    </v-chip>
                  </v-col>
                </v-row>
              </v-card-text>
            </v-card>
          </v-col>

          <!-- Принадлежность -->
          <v-col cols="12" md="6">
            <v-card variant="outlined" class="h-100">
              <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
                <v-icon icon="mdi-office-building" size="small" class="mr-1" />
                Принадлежность
              </v-card-title>
              <v-card-text>
                <ReadField label="Организация-владелец" :value="vehicle.owner_org_name" />
                <ReadField label="Организация-эксплуатант" :value="vehicle.assigned_org_name" />
                <ReadField label="Эксплуатант (текст)" :value="vehicle.assigned_text" />
              </v-card-text>
            </v-card>
          </v-col>

          <!-- Документы и топливо -->
          <v-col cols="12" md="6">
            <v-card variant="outlined" class="h-100">
              <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
                <v-icon icon="mdi-file-document-outline" size="small" class="mr-1" />
                Документы и топливо
              </v-card-title>
              <v-card-text>
                <v-row dense>
                  <v-col cols="6"><ReadField label="ПТС" :value="vehicle.pts_number" /></v-col>
                  <v-col cols="6"><ReadField label="СТС" :value="vehicle.sts_number" /></v-col>
                  <v-col cols="6"><ReadField label="ОСАГО до" :value="formatDate(vehicle.insurance_until)" /></v-col>
                  <v-col cols="6"><ReadField label="Техосмотр до" :value="formatDate(vehicle.tech_inspection_until)" /></v-col>
                  <v-col cols="6"><ReadField label="Тип топлива" :value="fuelLabel(vehicle.fuel_type)" /></v-col>
                  <v-col cols="6"><ReadField label="Текущий пробег, км" :value="fmtKm(vehicle.current_odometer_km)" /></v-col>
                  <v-col cols="6"><ReadField label="Последнее ТО, км" :value="fmtKm(vehicle.last_to_mileage_km)" /></v-col>
                  <v-col cols="6"><ReadField label="Дата последнего ТО" :value="formatDate(vehicle.last_to_date)" /></v-col>
                </v-row>
              </v-card-text>
            </v-card>
          </v-col>

          <!-- Закупка -->
          <v-col cols="12" md="6">
            <v-card variant="outlined" class="h-100">
              <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
                <v-icon icon="mdi-cart-outline" size="small" class="mr-1" />
                Закупка / прочее
              </v-card-title>
              <v-card-text>
                <ReadField label="Данные о закупке" :value="vehicle.purchase_info" />
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>

      </template>

      <!-- ════════════════════════════════════════════════════════
           ВАРИАНТ 3 — Hero + 2-col (РЕКОМЕНДУЕТСЯ)
           ════════════════════════════════════════════════════════ -->
      <template v-else-if="variant === '3'">

        <!-- Hero card -->
        <v-card class="mb-5" style="background: linear-gradient(135deg, #1e3a8a 0%, #1976d2 100%);">
          <v-card-text class="pa-5">
            <div class="d-flex align-start gap-5 flex-wrap">
              <!-- Photo placeholder -->
              <div class="rounded d-flex align-center justify-center flex-shrink-0"
                style="width:140px;height:90px;background:rgba(255,255,255,0.15)">
                <v-icon icon="mdi-camera" color="rgba(255,255,255,0.6)" size="36" />
              </div>

              <!-- Info -->
              <div class="flex-1-1">
                <div class="text-h5 font-weight-bold text-white mb-1">
                  {{ [vehicle.brand, vehicle.model].filter(Boolean).join(' ') || 'ТС' }}
                </div>
                <div class="text-body-2 mb-3" style="color:rgba(255,255,255,0.8)">
                  {{ [vehicle.year_of_manufacture, vehicle.color, vehicle.owner_org_name].filter(Boolean).join(' · ') }}
                  <template v-if="vehicle.assigned_org_name || vehicle.assigned_text">
                    · {{ vehicle.assigned_org_name || vehicle.assigned_text }}
                  </template>
                </div>

                <!-- Chips row -->
                <div class="d-flex align-center gap-2 flex-wrap">
                  <!-- Plate -->
                  <div class="px-3 py-1 rounded font-weight-bold"
                    style="background:rgba(255,255,255,0.95);color:#1f2937;font-family:monospace;font-size:15px;letter-spacing:2px">
                    {{ vehicle.plate }}
                  </div>

                  <!-- State chip -->
                  <v-chip
                    v-if="vehicle.state"
                    style="background:rgba(255,255,255,0.2);color:white"
                    size="small"
                    variant="flat"
                  >
                    {{ stateLabel(vehicle.state) }}
                  </v-chip>

                  <!-- ОСАГО chip -->
                  <v-chip
                    v-if="vehicle.insurance_until"
                    style="background:rgba(255,255,255,0.2);color:white"
                    size="small"
                    variant="flat"
                    prepend-icon="mdi-shield-check"
                  >
                    ОСАГО до {{ formatDate(vehicle.insurance_until) }}
                  </v-chip>

                  <!-- ТО chip -->
                  <v-chip
                    v-if="vehicle.last_to_mileage_km || vehicle.current_odometer_km"
                    style="background:rgba(255,255,255,0.2);color:white"
                    size="small"
                    variant="flat"
                    prepend-icon="mdi-wrench"
                  >
                    <template v-if="vehicle.current_odometer_km && vehicle.next_to_km">
                      ТО через {{ (vehicle.next_to_km - vehicle.current_odometer_km).toLocaleString('ru-RU') }} км
                    </template>
                    <template v-else>
                      ТО: {{ fmtKm(vehicle.last_to_mileage_km) }}
                    </template>
                  </v-chip>
                </div>
              </div>
            </div>
          </v-card-text>
        </v-card>

        <!-- 2-col sections -->
        <v-row>
          <!-- Идентификация -->
          <v-col cols="12" md="6">
            <v-card variant="outlined" class="h-100">
              <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
                <v-icon icon="mdi-car-info" size="small" class="mr-1" />
                Идентификация
              </v-card-title>
              <v-card-text>
                <v-row dense>
                  <v-col cols="6"><ReadField label="Марка" :value="vehicle.brand" /></v-col>
                  <v-col cols="6"><ReadField label="Модель" :value="vehicle.model" /></v-col>
                  <v-col cols="6"><ReadField label="Год вып." :value="vehicle.year_of_manufacture?.toString()" /></v-col>
                  <v-col cols="6"><ReadField label="Цвет" :value="vehicle.color" /></v-col>
                  <v-col cols="12"><ReadField label="VIN" :value="vehicle.vin" /></v-col>
                  <v-col cols="6"><ReadField label="Тип ТС" :value="typeLabel(vehicle.type)" /></v-col>
                  <v-col cols="6">
                    <div class="text-caption text-medium-emphasis mb-1">Состояние</div>
                    <v-chip :color="stateColor(vehicle.state)" size="small" variant="tonal">
                      {{ stateLabel(vehicle.state) }}
                    </v-chip>
                  </v-col>
                </v-row>
              </v-card-text>
            </v-card>
          </v-col>

          <!-- Принадлежность -->
          <v-col cols="12" md="6">
            <v-card variant="outlined" class="h-100">
              <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
                <v-icon icon="mdi-office-building" size="small" class="mr-1" />
                Принадлежность
              </v-card-title>
              <v-card-text>
                <ReadField label="Организация-владелец" :value="vehicle.owner_org_name" />
                <ReadField label="Организация-эксплуатант" :value="vehicle.assigned_org_name" />
                <ReadField label="Эксплуатант (текст)" :value="vehicle.assigned_text" />
              </v-card-text>
            </v-card>
          </v-col>

          <!-- Документы -->
          <v-col cols="12" md="6">
            <v-card variant="outlined" class="h-100">
              <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
                <v-icon icon="mdi-file-document-outline" size="small" class="mr-1" />
                Документы
              </v-card-title>
              <v-card-text>
                <v-row dense>
                  <v-col cols="6"><ReadField label="ПТС" :value="vehicle.pts_number" /></v-col>
                  <v-col cols="6"><ReadField label="СТС" :value="vehicle.sts_number" /></v-col>
                  <v-col cols="6"><ReadField label="ОСАГО до" :value="formatDate(vehicle.insurance_until)" /></v-col>
                  <v-col cols="6"><ReadField label="Техосмотр до" :value="formatDate(vehicle.tech_inspection_until)" /></v-col>
                </v-row>
              </v-card-text>
            </v-card>
          </v-col>

          <!-- Топливо и пробег -->
          <v-col cols="12" md="6">
            <v-card variant="outlined" class="h-100">
              <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 pb-2">
                <v-icon icon="mdi-fuel" size="small" class="mr-1" />
                Топливо и пробег
              </v-card-title>
              <v-card-text>
                <v-row dense>
                  <v-col cols="6"><ReadField label="Тип топлива" :value="fuelLabel(vehicle.fuel_type)" /></v-col>
                  <v-col cols="6"><ReadField label="Текущий пробег, км" :value="fmtKm(vehicle.current_odometer_km)" /></v-col>
                  <v-col cols="6"><ReadField label="Последнее ТО, км" :value="fmtKm(vehicle.last_to_mileage_km)" /></v-col>
                  <v-col cols="6"><ReadField label="Дата последнего ТО" :value="formatDate(vehicle.last_to_date)" /></v-col>
                  <v-col cols="12"><ReadField label="Данные о закупке" :value="vehicle.purchase_info" /></v-col>
                </v-row>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>

      </template>

      <!-- ════════════════════════════════════════════════════════
           ВАРИАНТ 4 — Accordion
           ════════════════════════════════════════════════════════ -->
      <template v-else-if="variant === '4'">

        <!-- Mini-hero -->
        <v-card class="mb-4" style="background:#1a1d23">
          <v-card-text class="pa-4">
            <div class="d-flex align-center gap-4 flex-wrap">
              <div class="rounded d-flex align-center justify-center flex-shrink-0"
                style="width:60px;height:40px;background:rgba(255,255,255,0.1)">
                <v-icon icon="mdi-car" color="rgba(255,255,255,0.5)" size="20" />
              </div>
              <div>
                <div class="text-body-1 font-weight-bold text-white">
                  {{ [vehicle.brand, vehicle.model].filter(Boolean).join(' ') || 'ТС' }}
                  &nbsp;·&nbsp;
                  <span class="px-2 py-1 rounded font-weight-bold"
                    style="background:rgba(255,255,255,0.9);color:#1f2937;font-family:monospace;font-size:13px;letter-spacing:1.5px">
                    {{ vehicle.plate }}
                  </span>
                </div>
                <div class="text-caption" style="color:rgba(255,255,255,0.65)">
                  {{ vehicle.owner_org_name || '—' }}
                  <template v-if="vehicle.assigned_org_name || vehicle.assigned_text">
                    → {{ vehicle.assigned_org_name || vehicle.assigned_text }}
                  </template>
                  · {{ stateLabel(vehicle.state) }}
                  <template v-if="vehicle.insurance_until">
                    · ОСАГО до {{ formatDate(vehicle.insurance_until) }}
                  </template>
                </div>
              </div>
            </div>
          </v-card-text>
        </v-card>

        <v-expansion-panels v-model="accordionOpen" multiple>

          <!-- 1. Идентификация -->
          <v-expansion-panel value="ident">
            <v-expansion-panel-title>
              <div class="d-flex align-center gap-2">
                <v-icon icon="mdi-car-info" size="small" />
                <span class="font-weight-semibold">Идентификация</span>
                <span class="text-caption text-medium-emphasis ml-1">
                  {{ vehicle.brand }} {{ vehicle.model }}
                  <template v-if="vehicle.year_of_manufacture"> · {{ vehicle.year_of_manufacture }} г.</template>
                </span>
              </div>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <v-row dense>
                <v-col cols="12" md="4">
                  <div class="text-caption text-medium-emphasis mb-1">Гос. номер</div>
                  <div class="font-weight-bold font-mono pa-2 rounded mb-3"
                    style="background:#1f2937;color:#fff;display:inline-block;letter-spacing:2px">
                    {{ vehicle.plate }}
                  </div>
                </v-col>
                <v-col cols="12" md="4"><ReadField label="Марка" :value="vehicle.brand" /></v-col>
                <v-col cols="12" md="4"><ReadField label="Модель" :value="vehicle.model" /></v-col>
                <v-col cols="12" md="4"><ReadField label="Цвет" :value="vehicle.color" /></v-col>
                <v-col cols="12" md="4"><ReadField label="Год выпуска" :value="vehicle.year_of_manufacture?.toString()" /></v-col>
                <v-col cols="12" md="4"><ReadField label="VIN" :value="vehicle.vin" /></v-col>
                <v-col cols="12" md="4"><ReadField label="Тип ТС" :value="typeLabel(vehicle.type)" /></v-col>
                <v-col cols="12" md="4">
                  <div class="text-caption text-medium-emphasis mb-1">Состояние</div>
                  <v-chip :color="stateColor(vehicle.state)" size="small" variant="tonal">
                    {{ stateLabel(vehicle.state) }}
                  </v-chip>
                </v-col>
              </v-row>
            </v-expansion-panel-text>
          </v-expansion-panel>

          <!-- 2. Принадлежность -->
          <v-expansion-panel value="ownership">
            <v-expansion-panel-title>
              <div class="d-flex align-center gap-2">
                <v-icon icon="mdi-office-building" size="small" />
                <span class="font-weight-semibold">Принадлежность</span>
                <span class="text-caption text-medium-emphasis ml-1">
                  {{ vehicle.owner_org_name || '—' }}
                  <template v-if="vehicle.assigned_org_name || vehicle.assigned_text">
                    → {{ vehicle.assigned_org_name || vehicle.assigned_text }}
                  </template>
                </span>
              </div>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <v-row dense>
                <v-col cols="12" md="6"><ReadField label="Организация-владелец" :value="vehicle.owner_org_name" /></v-col>
                <v-col cols="12" md="6"><ReadField label="Организация-эксплуатант" :value="vehicle.assigned_org_name" /></v-col>
                <v-col cols="12"><ReadField label="Эксплуатант (текст)" :value="vehicle.assigned_text" /></v-col>
              </v-row>
            </v-expansion-panel-text>
          </v-expansion-panel>

          <!-- 3. Документы и топливо -->
          <v-expansion-panel value="docs">
            <v-expansion-panel-title>
              <div class="d-flex align-center gap-2">
                <v-icon icon="mdi-file-document-outline" size="small" />
                <span class="font-weight-semibold">Документы и топливо</span>
                <span class="text-caption text-medium-emphasis ml-1">
                  <template v-if="vehicle.insurance_until">ОСАГО до {{ formatDate(vehicle.insurance_until) }}</template>
                  <template v-else>нет данных</template>
                </span>
              </div>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <v-row dense>
                <v-col cols="12" md="4"><ReadField label="ПТС" :value="vehicle.pts_number" /></v-col>
                <v-col cols="12" md="4"><ReadField label="СТС" :value="vehicle.sts_number" /></v-col>
                <v-col cols="12" md="4"><ReadField label="ОСАГО до" :value="formatDate(vehicle.insurance_until)" /></v-col>
                <v-col cols="12" md="4"><ReadField label="Техосмотр до" :value="formatDate(vehicle.tech_inspection_until)" /></v-col>
                <v-col cols="12" md="4"><ReadField label="Тип топлива" :value="fuelLabel(vehicle.fuel_type)" /></v-col>
                <v-col cols="12" md="4"><ReadField label="Текущий пробег, км" :value="fmtKm(vehicle.current_odometer_km)" /></v-col>
                <v-col cols="12" md="4"><ReadField label="Последнее ТО, км" :value="fmtKm(vehicle.last_to_mileage_km)" /></v-col>
                <v-col cols="12" md="4"><ReadField label="Дата последнего ТО" :value="formatDate(vehicle.last_to_date)" /></v-col>
              </v-row>
            </v-expansion-panel-text>
          </v-expansion-panel>

          <!-- 4. Закупка -->
          <v-expansion-panel value="purchase">
            <v-expansion-panel-title>
              <div class="d-flex align-center gap-2">
                <v-icon icon="mdi-cart-outline" size="small" />
                <span class="font-weight-semibold">Закупка / прочее</span>
                <span class="text-caption text-medium-emphasis ml-1">
                  {{ vehicle.purchase_info ? vehicle.purchase_info.slice(0, 40) + (vehicle.purchase_info.length > 40 ? '…' : '') : 'нет данных' }}
                </span>
              </div>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <ReadField label="Данные о закупке" :value="vehicle.purchase_info" />
            </v-expansion-panel-text>
          </v-expansion-panel>

          <!-- 5. Дополнительные параметры -->
          <v-expansion-panel value="extra">
            <v-expansion-panel-title>
              <div class="d-flex align-center gap-2">
                <v-icon icon="mdi-tune" size="small" />
                <span class="font-weight-semibold">Дополнительные параметры</span>
              </div>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <v-row dense>
                <v-col cols="12" md="4">
                  <ReadField label="Норма топлива (лето), л/100км" :value="vehicle.fuel_norm_summer?.toString()" />
                </v-col>
                <v-col cols="12" md="4">
                  <ReadField label="Норма топлива (зима), л/100км" :value="vehicle.fuel_norm_winter?.toString()" />
                </v-col>
                <v-col cols="12" md="4">
                  <ReadField label="Следующее ТО (км-план)" :value="fmtKm(vehicle.next_to_km)" />
                </v-col>
              </v-row>
            </v-expansion-panel-text>
          </v-expansion-panel>

        </v-expansion-panels>

      </template>

      <!-- ── Bottom back button ── -->
      <div class="mt-6">
        <v-btn variant="outlined" prepend-icon="mdi-arrow-left" @click="router.push('/property/vehicles')">
          Назад к списку
        </v-btn>
      </div>

    </template>

    <!-- Error state -->
    <div v-else class="text-center py-16">
      <v-icon icon="mdi-alert-circle-outline" size="64" color="error" />
      <div class="text-h6 mt-4">Не удалось загрузить данные ТС</div>
      <v-btn class="mt-4" variant="outlined" @click="router.push('/property/vehicles')">К списку</v-btn>
    </div>

  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, defineComponent, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'

// ─────────────── Types ───────────────

interface Vehicle {
  id: number
  owner_org_id: number
  owner_org_name: string | null
  assigned_org_id: number | null
  assigned_org_name: string | null
  assigned_text: string | null
  brand: string | null
  model: string | null
  color: string | null
  plate: string
  vin: string | null
  type: string | null
  state: string | null
  registered_at: string | null
  year_of_manufacture: number | null
  insurance_until: string | null
  tech_inspection_until: string | null
  fuel_type: string | null
  fuel_norm_summer: number | null
  fuel_norm_winter: number | null
  current_odometer_km: number | null
  next_to_km: number | null
  last_to_mileage_km: number | null
  last_to_date: string | null
  pts_number: string | null
  sts_number: string | null
  purchase_info: string | null
  has_tracker: boolean
  akb_ok: boolean
  has_radio: boolean
  mirrors_ok: boolean
  has_keys: boolean
  has_first_aid_kit: boolean
  has_spare_wheel: boolean
  has_extinguisher: boolean
}

// ─────────────── Lookup maps ───────────────

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

const STATE_COLOR: Record<string, string> = {
  working:      'success',
  broken:       'error',
  in_repair:    'warning',
  needs_repair: 'orange',
  destroyed:    'grey',
  utilized:     'grey',
}

const FUEL_LABEL: Record<string, string> = {
  petrol: 'Бензин',
  diesel: 'ДТ',
  gas:    'ГАЗ',
  hybrid: 'Гибрид',
  electric: 'Электро',
}

function typeLabel(t: string | null | undefined): string | null {
  return t ? (TYPE_LABEL[t] ?? t) : null
}
function stateLabel(s: string | null | undefined): string {
  return s ? (STATE_LABEL[s] ?? s) : '—'
}
function stateColor(s: string | null | undefined): string {
  return s ? (STATE_COLOR[s] ?? 'grey') : 'grey'
}
function fuelLabel(f: string | null | undefined): string | null {
  return f ? (FUEL_LABEL[f] ?? f) : null
}

function formatDate(d: string | null | undefined): string | null {
  if (!d) return null
  try {
    const dt = new Date(d)
    return dt.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
  } catch {
    return d
  }
}

function fmtKm(n: number | null | undefined): string | null {
  if (n == null) return null
  return n.toLocaleString('ru-RU') + ' км'
}

// ─────────────── Inline ReadField component ───────────────

const ReadField = defineComponent({
  props: {
    label: { type: String, required: true },
    value: { type: String as () => string | null | undefined, default: null },
  },
  setup(props) {
    return () => h('div', { class: 'mb-3' }, [
      h('div', { class: 'text-caption text-medium-emphasis mb-1' }, props.label),
      h('div', {
        class: props.value ? 'text-body-2' : 'text-body-2 text-disabled',
      }, props.value ?? '—'),
    ])
  },
})

// ─────────────── Composables ───────────────

const route = useRoute()
const router = useRouter()

const vehicle = ref<Vehicle | null>(null)
const loading = ref(false)

const variant = ref<'1' | '2' | '3' | '4'>('3')

// Accordion: open first panel by default
const accordionOpen = ref<string[]>(['ident'])

const variantDesc = computed(() => {
  const descs: Record<string, string> = {
    '1': 'Секции одна под другой, поля внутри — в 3 колонки. Простой, привычный, длинный скролл.',
    '2': 'Секции попарно в 2 колонки — меньше скролла на широких экранах. На мобильном — стэком.',
    '3': 'Сверху hero-плашка с градиентом: номер + статус + ОСАГО. Ниже секции в 2 колонки. Рекомендуется: ключевые данные видны сразу.',
    '4': 'Все секции свёрнуты, в заголовке — краткое summary. Компактно; лишний клик для детализации.',
  }
  return descs[variant.value] ?? ''
})

// ─────────────── Load vehicle ───────────────

async function loadVehicle() {
  const id = Number(route.params.id)
  if (!id) return
  loading.value = true
  try {
    const data = await apiFetch<Vehicle>(`/vehicles/${id}`)
    vehicle.value = data
  } catch (e) {
    console.error('[VehicleLayoutPreview] load error', e)
    vehicle.value = null
  } finally {
    loading.value = false
  }
}

onMounted(loadVehicle)
</script>
