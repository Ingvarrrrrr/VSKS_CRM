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
            v-if="canManageFields"
            variant="outlined"
            prepend-icon="mdi-tune-variant"
            size="small"
            @click="fieldsDialogOpen = true"
          >
            Состав полей
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
        <v-tab value="repairs">Ремонты<BlockHint block-key="repairs" /></v-tab>
        <v-tab value="odometer">Пробег</v-tab>
        <v-tab value="fuel">Заправки<BlockHint block-key="fuel_logs" /></v-tab>
        <v-tab value="trips">Путёвки<BlockHint block-key="trips" /></v-tab>
        <v-tab value="fines" prepend-icon="mdi-alert-octagon-outline">Штрафы<BlockHint block-key="fines" /></v-tab>
        <v-tab value="history">История<BlockHint block-key="field_history" /></v-tab>
        <v-tab value="purchases">Связанные закупки</v-tab>
      </v-tabs>
      <v-divider class="mb-4" />

      <v-tabs-window v-model="activeTab">

        <!-- ─────────── Tab: Общее (Phase 29.3 redesign) ─────────── -->
        <v-tabs-window-item value="general">

          <VehicleHeroBanner
            :vehicle="vehicle"
            :photo-url="heroPhotoUrl"
            :has-silhouette="heroHasSilhouette"
            :body-type="heroBodyType"
            :is-insurance-expiring-soon="isInsuranceExpiringSoon"
            :is-to-soon="isToSoon"
            :format-date="formatDate"
            @open-photos="activeTab = 'photos'"
          />

          <VehicleQuickStats
            :vehicle="vehicle"
            :is-to-soon="isToSoon"
            :docs-status="docsStatus"
            :format-date="formatDate"
            @open-odometer="activeTab = 'odometer'"
          />

          <!-- ── 2-column layout ── -->
          <v-row>
            <!-- LEFT column -->
            <v-col cols="12" md="7">

              <VehicleGeneralInfoCard
                :form="form"
                :vehicle-id="vehicle.id"
                :is-field-visible="isFieldVisible"
                v-model:history-comment="historyComment"
                :brand-suggestions="brandSuggestions"
                :filtered-model-suggestions="filteredModelSuggestions"
                :year-options="yearOptions"
                :color-suggestions="colorSuggestions"
                :type-options="typeOptions"
                :body-type-options="bodyTypeOptions"
                :pts-category-options="ptsCategoryOptions"
                :state-options="stateOptions"
                :assigned-text-suggestions="assignedTextSuggestions"
                :basis-suggestions="basisSuggestions"
                :owner-org-full-name="ownerOrgFullName"
                :owner-org-uid="ownerOrgUid"
                :owner-org-options="ownerOrgOptions"
                :owner-autofill="ownerAutofill"
                :contractors-store="contractorsStore"
                :assigned-org-full-name="assignedOrgFullName"
                :assigned-org-items-count="assignedOrgItems.length"
                :assigned-org-uid="assignedOrgUid"
                :assigned-org-options="assignedOrgOptions"
                :assigned-autofill="assignedAutofill"
                :operator-inn-display="operatorInnDisplay"
                :location-city-items="locationCityItems"
                :home-base-city-items="homeBaseCityItems"
                @owner-org-select="onOwnerOrgSelect"
                @assigned-org-select="onAssignedOrgSelect"
                @update:location-city-search="locationCitySearch = $event"
                @update:home-base-city-search="homeBaseCitySearch = $event"
              />

              <VehicleOwnershipCard
                :form="form"
                :vehicle-id="vehicle.id"
                :is-field-visible="isFieldVisible"
                :is-group-visible="isGroupVisible"
                :owner-inn-display="ownerInnDisplay"
                :ownership-basis-options="ownershipBasisOptions"
              />

              <VehicleEquipmentChecklistCard
                :form="form"
                :is-field-visible="isFieldVisible"
                :tires-type-options="tiresTypeOptions"
                :tires-condition-options="tiresConditionOptions"
                :paint-condition-options="paintConditionOptions"
                :brand-suggestions="brandSuggestions"
              />

              <VehicleTransferHistoryCard
                :items="transferHistory"
                :loading="loadingTransferHistory"
                :format-date="formatDate"
              />

              <VehicleLastChecklistCard
                :checklist="lastChecklist"
                :format-date="formatDate"
              />

              <VehicleOdometerSparklineCard
                :spark-points="sparkPoints"
                :spark-polyline="sparkPolyline"
                :spark-area-path="sparkAreaPath"
                :spark-last-point="sparkLastPoint"
                :spark-axis-labels="sparkAxisLabels"
                :spark-stats="sparkStats"
              />

              <VehicleEventsTimelineCard
                :events="timelineEvents"
                :format-date="formatDate"
              />

            </v-col>

            <!-- RIGHT column (aside) -->
            <v-col cols="12" md="5">

              <VehicleResponsibleCard :vehicle="vehicle" :resp-initials="respInitials" />

              <VehicleDocumentDeadlinesCard
                :vehicle="vehicle"
                :format-date="formatDate"
                :days-left="daysLeft"
                :doc-dot-class="docDotClass"
              />

              <VehicleDocumentsEditCard
                :form="form"
                :vehicle-id="vehicle.id"
                :is-field-visible="isFieldVisible"
                :pts-kind-options="ptsKindOptions"
                :tech-inspection-status-options="techInspectionStatusOptions"
                :fuel-type-select-items="fuelTypeSelectItems"
                :current-odometer-km="vehicle.current_odometer_km"
                @open-odometer="activeTab = 'odometer'"
              />

              <VehiclePassesCard
                :form="form"
                :vehicle-id="vehicle.id"
                :is-field-visible="isFieldVisible"
                :is-group-visible="isGroupVisible"
                :pass-field-defs="passFieldDefs"
                :pass-status-options="passStatusOptions"
              />

              <VehiclePhotoGalleryCard
                :photo-count="photoCount"
                @open-photos="activeTab = 'photos'"
              />

              <VehicleQuickActionsCard
                :saving="saving"
                :is-dirty="isDirty"
                :is-admin-or-above="isAdminOrAbove"
                @new-waybill="$router.push(`/fleet/waybills/new?vehicle_id=${vehicleId}`)"
                @save="save"
                @delete="deleteDialog = true"
              />

            </v-col>
          </v-row>

          <!-- Save bar -->
          <div class="d-flex justify-end gap-3 pb-6 vp-save-bar">
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
    <VehicleDeleteDialog v-model="deleteDialog" :deleting="deleting" @confirm="doDelete(() => router.push('/property/vehicles'))" />

    <!-- ── Состав полей карточки ТС ── -->
    <VehicleFieldsDialog v-model="fieldsDialogOpen" />

    <!-- ── Error dialog ── -->
    <VehicleErrorDialog
      v-model="errorDialogShow"
      :message="errorMsg"
      :code="errorCode"
      :correlation-id="errorCorrelationId"
    />

  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { resolveBodyTypeIcon } from '@/components/vehicles/bodyTypeIcon'
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
import VehicleFieldsDialog from '@/components/vehicles/VehicleFieldsDialog.vue'
import { useVehicleFields } from '@/composables/useVehicleFields'
import { loadCitiesCatalog } from '@/components/fleet/russiaCitiesCatalog'

import BlockHint from '@/components/fleet/vehicle-detail/BlockHint.vue'
import VehicleHeroBanner from '@/components/fleet/vehicle-detail/VehicleHeroBanner.vue'
import VehicleQuickStats from '@/components/fleet/vehicle-detail/VehicleQuickStats.vue'
import VehicleGeneralInfoCard from '@/components/fleet/vehicle-detail/VehicleGeneralInfoCard.vue'
import VehicleOwnershipCard from '@/components/fleet/vehicle-detail/VehicleOwnershipCard.vue'
import VehicleEquipmentChecklistCard from '@/components/fleet/vehicle-detail/VehicleEquipmentChecklistCard.vue'
import VehicleTransferHistoryCard from '@/components/fleet/vehicle-detail/VehicleTransferHistoryCard.vue'
import VehicleLastChecklistCard from '@/components/fleet/vehicle-detail/VehicleLastChecklistCard.vue'
import VehicleOdometerSparklineCard from '@/components/fleet/vehicle-detail/VehicleOdometerSparklineCard.vue'
import VehicleEventsTimelineCard from '@/components/fleet/vehicle-detail/VehicleEventsTimelineCard.vue'
import VehicleResponsibleCard from '@/components/fleet/vehicle-detail/VehicleResponsibleCard.vue'
import VehicleDocumentDeadlinesCard from '@/components/fleet/vehicle-detail/VehicleDocumentDeadlinesCard.vue'
import VehicleDocumentsEditCard from '@/components/fleet/vehicle-detail/VehicleDocumentsEditCard.vue'
import VehiclePassesCard from '@/components/fleet/vehicle-detail/VehiclePassesCard.vue'
import VehiclePhotoGalleryCard from '@/components/fleet/vehicle-detail/VehiclePhotoGalleryCard.vue'
import VehicleQuickActionsCard from '@/components/fleet/vehicle-detail/VehicleQuickActionsCard.vue'
import VehicleDeleteDialog from '@/components/fleet/vehicle-detail/VehicleDeleteDialog.vue'
import VehicleErrorDialog from '@/components/fleet/vehicle-detail/VehicleErrorDialog.vue'

import {
  TYPE_LABEL, STATE_LABEL, TYPE_COLOR, STATE_COLOR,
  typeOptions, stateOptions, fuelTypeSelectItems,
  ptsCategoryOptions, ownershipBasisOptions, ptsKindOptions, passFieldDefs,
  useVehicleFieldOptions,
} from '@/composables/fleet/useVehicleFieldOptions'
import { useVehicleRecord } from '@/composables/fleet/useVehicleRecord'
import { useVehicleOrgsList } from '@/composables/fleet/useVehicleOrgsList'
import { useVehicleSuggestions } from '@/composables/fleet/useVehicleSuggestions'
import { useVehicleOrgAssignment } from '@/composables/fleet/useVehicleOrgAssignment'
import { useVehicleCityAutocomplete } from '@/composables/fleet/useVehicleCityAutocomplete'
import { useVehicleOdometerHistory } from '@/composables/fleet/useVehicleOdometerHistory'
import { useVehicleLastChecklist } from '@/composables/fleet/useVehicleLastChecklist'
import { useVehicleFieldHistory } from '@/composables/fleet/useVehicleFieldHistory'
import { useVehicleTransferHistory } from '@/composables/fleet/useVehicleTransferHistory'
import { useVehiclePhotos } from '@/composables/fleet/useVehiclePhotos'
import { useVehicleTimeline } from '@/composables/fleet/useVehicleTimeline'
import { useVehicleDocsStatus } from '@/composables/fleet/useVehicleDocsStatus'
import { useVehicleErrorDialog } from '@/composables/fleet/useVehicleErrorDialog'

// ─────────────── Routing / auth ───────────────

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

// Phase 29.3-R3 (Д-3): удалять ТС может только admin+
const isAdminOrAbove = computed(() => {
  const r = (authStore as any).user?.role || (authStore as any).role
  return ['admin', 'superadmin', 'account_owner'].includes(r)
})

const vehicleId = computed(() => Number(route.params.id) || 0)
const activeTab = ref('general')

// ─────────────── Состав полей карточки (Autoblock) ───────────────

const { canManage: canManageFields, isFieldVisible, isGroupVisible, loadFields: loadVehicleFieldsConfig } = useVehicleFields()
const fieldsDialogOpen = ref(false)

// ─────────────── Справочники карточки ТС (единый источник — ПРАВИЛО №6) ───────────────

const {
  paintConditionOptions, tiresTypeOptions, bodyTypeOptions,
  tiresConditionOptions, techInspectionStatusOptions, passStatusOptions,
} = useVehicleFieldOptions()

// Годы от текущего до 1980 (reversed — новые сверху)
const currentYear = new Date().getFullYear()
const yearOptions = Array.from({ length: currentYear - 1980 + 1 }, (_, i) => currentYear - i)

// ─────────────── Карточка ТС: запись/форма ───────────────

const {
  form, historyComment, vehicle, loadingVehicle,
  saving, deleting, deleteDialog, isDirty,
  loadVehicle, save, resetForm, doDelete,
} = useVehicleRecord()

// ─────────────── Владелец / Эксплуатант ───────────────

const { orgsList, loadOrgs } = useVehicleOrgsList()
const {
  contractorsStore, assignedOrgItems, ownerOrgFullName, assignedOrgFullName,
  ownerAutofill, assignedAutofill, ownerOrgUid, assignedOrgUid, ownerOrgOptions, assignedOrgOptions,
  ownerInnDisplay, operatorInnDisplay, onOwnerOrgSelect, onAssignedOrgSelect,
} = useVehicleOrgAssignment(form, orgsList, vehicle)

// ─────────────── Автодополнение ───────────────

const {
  brandSuggestions, filteredModelSuggestions, colorSuggestions,
  assignedTextSuggestions, basisSuggestions, loadSuggestions,
} = useVehicleSuggestions(form)

const { locationCitySearch, locationCityItems, homeBaseCitySearch, homeBaseCityItems } = useVehicleCityAutocomplete()

// ─────────────── Slice-2 widgets ───────────────

const { odometerRows, loadOdometer, sparkPoints, sparkPolyline, sparkAreaPath, sparkLastPoint, sparkAxisLabels, sparkStats } = useVehicleOdometerHistory()
const { lastChecklist, loadLastChecklist } = useVehicleLastChecklist()
const { fieldHistory, loadFieldHistory } = useVehicleFieldHistory()
const { transferHistory, loadingTransferHistory, loadTransferHistory } = useVehicleTransferHistory()
const { photoCount, heroPhotoUrl, loadPhotoCount } = useVehiclePhotos()
const { timelineEvents } = useVehicleTimeline(odometerRows, lastChecklist, fieldHistory, transferHistory)
const { isInsuranceExpiringSoon, isToSoon, daysLeft, docDotClass, respInitials, docsStatus } = useVehicleDocsStatus(vehicle)

// ─────────────── Hero banner: силуэт по кузову ───────────────

// Текущее значение «Кузов» для картинки в hero-плашке — смотрим на форму
// (реактивные несохранённые правки пользователя), а не на уже сохранённый
// vehicle. Пока форма не проинициализирована (fillForm ещё не отработал) —
// запасной вариант vehicle.body_type. «Тип ТС» на картинку больше не влияет:
// это характеристика из ПТС, а не источник силуэта (запрос владельца, 2026-09).
const heroBodyType = computed(() => form.body_type || vehicle.value?.body_type || null)

// Есть ли что показать силуэтом по кузову — иначе заглушка-камера.
// resolveBodyTypeIcon сам отсеивает пустое значение и NO_DATA_LABEL.
const heroHasSilhouette = computed(() => !!resolveBodyTypeIcon(heroBodyType.value))

// ─────────────── Error dialog ───────────────

const { errorDialogShow, errorMsg, errorCode, errorCorrelationId } = useVehicleErrorDialog()

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
    loadCitiesCatalog()
    // Slice-2 widget loaders
    loadOdometer(id)
    loadLastChecklist(id)
    loadFieldHistory(id)
    loadPhotoCount(id)
    loadVehicleFieldsConfig()
  }
})

watch(() => route.params.id, (newId) => {
  const id = Number(newId)
  if (id) loadVehicle(id)
})

// Ушли с вкладки «Фото» — там могли загрузить/удалить фото, обновляем превью в hero-плашке.
watch(activeTab, (val, oldVal) => {
  if (oldVal === 'photos' && val !== 'photos' && vehicleId.value) {
    loadPhotoCount(vehicleId.value)
  }
})
</script>

<style>
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

/* ─── Save bar ─────────────────────────────────────────────────
   На узких экранах глобальный чат-FAB (App.vue, fixed bottom:90px right:24px,
   48×48) перекрывает правый край кнопки «Сохранить изменения». FAB общий для
   всего приложения — трогать его нельзя, поэтому здесь просто резервируем
   справа зону шире самого FAB (48px + отступ 24px + запас), чтобы кнопка не
   заходила под него. */
@media (max-width: 768px) {
  .vp-save-bar {
    padding-right: 80px;
    flex-wrap: wrap;
  }
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
  overflow: hidden;
}
.vp-hero__photo--clickable { cursor: pointer; }
.vp-hero__photo--clickable:hover { filter: brightness(0.96); }
.vp-hero__photo-icon { opacity: 0.35; }
.vp-hero__photo-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

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
.vp-qs--clickable { cursor: pointer; transition: background 0.15s, border-color 0.15s; }
.vp-qs--clickable:hover { background: rgba(0,0,0,0.05); border-color: rgba(0,0,0,0.16); }

.field-hint-icon { cursor: help; opacity: 0.9; vertical-align: middle; }

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
/* Владелец/Эксплуатант: полные юрлица-названия ("ДОНЕЦКОЕ РЕГИОНАЛЬНОЕ
   ОТДЕЛЕНИЕ ВСЕРОССИЙСКОЙ ОБЩЕСТВЕННОЙ МОЛОДЕЖНОЙ ОРГАНИЗАЦИИ...") могут
   растянуть строку карточки на весь экран — зажимаем визуально до 2 строк
   с многоточием (тот же приём, что .vl-clamp-2 в VehicleListView.vue),
   полный текст — во всплывающей подсказке (v-tooltip в шаблоне). Vuetify
   рендерит выбранное значение внутри .v-autocomplete__selection-text —
   именно этот узел (а не .v-field__input, он лишь flex-обёртка) нужно
   клампить, иначе побеждает встроенный однострочный white-space:nowrap. */
.vp-org-field :deep(.v-field__input) {
  align-items: flex-start;
  height: auto;
  min-height: 28px !important;
}
.vp-org-field :deep(.v-autocomplete__selection) {
  max-width: 100%;
}
.vp-org-field :deep(.v-autocomplete__selection-text) {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: normal;
  line-height: 1.3;
  max-height: 2.6em;
  text-align: right;
}
/* Скрыть невидимый текстовый input рядом с выбранным значением — при двух
   строках текста он занимал бы отдельное место во flex-строке и портил
   выравнивание по правому краю. */
.vp-org-field :deep(.v-autocomplete__selection) + input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
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
.v-theme--dark .vp-qs--clickable:hover { background: rgba(255,255,255,0.07); border-color: rgba(255,255,255,0.16); }

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
