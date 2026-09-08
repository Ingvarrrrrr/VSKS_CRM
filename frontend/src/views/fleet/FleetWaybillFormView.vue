<template>
  <div
    class="wbf-page"
    :class="{ 'print-a5': isLightVehicle, 'print-a4': !isLightVehicle }"
  >
    <WaybillTopbar
      :is-new="isNew"
      :form="form"
      :saving="saving"
      :downloading-docx="downloadingDocx"
      :primary-action-label="primaryActionLabel"
      @save-draft="saveDraft"
      @download-docx="downloadDocx"
      @print="onPrint"
      @primary-action="handlePrimaryAction"
    />

    <!-- Stage stepper -->
    <div class="wbf-stepper-wrap no-print">
      <StageStepper :current-stage="(form.status as any) || 'created'" />
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="wbf-loading no-print">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- ═══ FORM ═══ -->
    <div v-else class="wbf-layout wbf-print-area">

      <!-- ── MAIN column ── -->
      <div class="wbf-main">

        <WaybillHeaderCard
          :form="form"
          :is-new="isNew"
          :form-readonly="formReadonly"
          @dirty="scheduleAutosave"
        />

        <WaybillVehicleCard
          :form="form"
          :vehicles="vehicles"
          :form-readonly="formReadonly"
          :is-new="isNew"
          :selected-vehicle="selectedVehicle"
          @select="onVehicleSelect(selectedVehicle)"
        />

        <WaybillDriverCard
          :form="form"
          :drivers="drivers"
          :form-readonly="formReadonly"
          :selected-driver="selectedDriver"
          @dirty="scheduleAutosave"
        />

        <WaybillRouteCard
          :form="form"
          :form-readonly="formReadonly"
          @dirty="scheduleAutosave"
        />

        <WaybillOdometerFuelCard
          :form="form"
          :form-readonly="formReadonly"
          :selected-vehicle="selectedVehicle"
          :actual-mileage="actualMileage"
        />

        <WaybillCargoCard
          :form="form"
          :form-readonly="formReadonly"
          @dirty="scheduleAutosave"
        />

        <WaybillInspectionsCard
          phase="pre"
          title="Предрейсовые осмотры"
          icon="mdi-clipboard-check-outline"
          icon-color="success"
          v-model:mechanic-id="form.pre_mechanic_id"
          v-model:mechanic-at="form.pre_mechanic_at"
          v-model:mechanic-result="form.pre_mechanic_result"
          v-model:doctor-id="form.pre_doctor_id"
          v-model:doctor-at="form.pre_doctor_at"
          v-model:doctor-result="form.pre_doctor_result"
          :mechanic-users="mechanicUsers"
          :doctor-users="doctorUsers"
          :readonly="preInspectReadonly"
        />

        <WaybillInspectionsCard
          phase="post"
          title="Послерейсовые осмотры"
          icon="mdi-clipboard-alert-outline"
          icon-color="error"
          v-model:mechanic-id="form.post_mechanic_id"
          v-model:mechanic-at="form.post_mechanic_at"
          v-model:mechanic-result="form.post_mechanic_result"
          v-model:doctor-id="form.post_doctor_id"
          v-model:doctor-at="form.post_doctor_at"
          v-model:doctor-result="form.post_doctor_result"
          :mechanic-users="mechanicUsers"
          :doctor-users="doctorUsers"
          :readonly="postInspectReadonly"
        />

        <WaybillSignatureCard
          :form="form"
          :signing-loading="signingLoading"
          @driver-sign="driverSign"
        />

        <WaybillWorkflowActions
          :form="form"
          :action-loading="actionLoading"
          @submit-tech-inspect="submitTechInspect"
          @confirm-tech-inspect="confirmTechInspect"
          @confirm-med-inspect="confirmMedInspect"
          @close-waybill="closeWaybill"
        />
      </div>

      <!-- ── ASIDE column ── -->
      <div class="wbf-aside no-print">
        <div class="wbf-aside-sticky">
          <WaybillSummaryAside :waybill="asideWaybill" />
        </div>
      </div>

    </div><!-- /wbf-layout -->

  </div>
</template>

<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'

import StageStepper from '@/components/fleet/StageStepper.vue'
import WaybillSummaryAside from '@/components/fleet/WaybillSummaryAside.vue'
import WaybillTopbar from '@/components/fleet/waybill/WaybillTopbar.vue'
import WaybillHeaderCard from '@/components/fleet/waybill/WaybillHeaderCard.vue'
import WaybillVehicleCard from '@/components/fleet/waybill/WaybillVehicleCard.vue'
import WaybillDriverCard from '@/components/fleet/waybill/WaybillDriverCard.vue'
import WaybillRouteCard from '@/components/fleet/waybill/WaybillRouteCard.vue'
import WaybillOdometerFuelCard from '@/components/fleet/waybill/WaybillOdometerFuelCard.vue'
import WaybillCargoCard from '@/components/fleet/waybill/WaybillCargoCard.vue'
import WaybillInspectionsCard from '@/components/fleet/waybill/WaybillInspectionsCard.vue'
import WaybillSignatureCard from '@/components/fleet/waybill/WaybillSignatureCard.vue'
import WaybillWorkflowActions from '@/components/fleet/waybill/WaybillWorkflowActions.vue'

import { useWaybillData } from '@/composables/fleet/waybill/useWaybillData'
import { useWaybillForm } from '@/composables/fleet/waybill/useWaybillForm'
import { useWaybillAutosave } from '@/composables/fleet/waybill/useWaybillAutosave'
import { useWaybillVehicleAutofill } from '@/composables/fleet/waybill/useWaybillVehicleAutofill'
import { useWaybillWorkflow } from '@/composables/fleet/waybill/useWaybillWorkflow'
import { useWaybillDocxPrint } from '@/composables/fleet/waybill/useWaybillDocxPrint'

import '@/styles/fleet-waybill.css'

// ─── Routing ──────────────────────────────────────────────────────────────────
const route = useRoute()
const router = useRouter()
const idParam = route.params.id as string
const isNew = idParam === 'new'
const queryVehicleId = isNew ? (Number(route.query.vehicle_id) || null) : null

// ─── Toast ────────────────────────────────────────────────────────────────────
const toast = useToast()
function showError(msg: string) {
  toast.error(msg)
}

// ─── Справочники (ТС/водители/пользователи) ───────────────────────────────────
const { vehicles, drivers, mechanicUsers, doctorUsers, loadVehicles, loadDrivers, loadUsers } = useWaybillData()

// ─── Состояние формы ──────────────────────────────────────────────────────────
const {
  loading,
  form,
  selectedVehicle,
  selectedDriver,
  actualMileage,
  formReadonly,
  preInspectReadonly,
  postInspectReadonly,
  primaryActionLabel,
  asideWaybill,
  isLightVehicle,
  mapServerToForm,
  loadWaybill,
  buildPayload,
} = useWaybillForm(vehicles, drivers, isNew)

// ─── Автосохранение ───────────────────────────────────────────────────────────
const { scheduleAutosave } = useWaybillAutosave(form, buildPayload)

// ─── Автоподстановка полей при выборе ТС ──────────────────────────────────────
const { autoPopulateFromVehicle, onVehicleSelect } = useWaybillVehicleAutofill(form, vehicles, scheduleAutosave)

// ─── Действия жизненного цикла путевого листа ─────────────────────────────────
const {
  saving,
  actionLoading,
  signingLoading,
  saveDraft,
  handlePrimaryAction,
  submitTechInspect,
  confirmTechInspect,
  confirmMedInspect,
  driverSign,
  closeWaybill,
} = useWaybillWorkflow(form, buildPayload, mapServerToForm, router, showError)

// ─── .docx / печать ───────────────────────────────────────────────────────────
const { downloadingDocx, downloadDocx, onPrint } = useWaybillDocxPrint(form, isLightVehicle)

// ─── Инициализация ────────────────────────────────────────────────────────────
onMounted(async () => {
  await Promise.all([loadVehicles(), loadDrivers(), loadUsers()])
  if (!isNew) {
    await loadWaybill(idParam)
  } else {
    // Phase 30.3: авто-подстановка текущего пользователя как водителя, если can_drive=true
    try {
      const me = await apiFetch<any>('/users/me')
      if (me?.can_drive && me?.id) {
        if (!drivers.value.find(d => d.id === me.id)) {
          drivers.value = [{ id: me.id, full_name: me.full_name || me.username || `User #${me.id}` }, ...drivers.value]
        }
        if (!(form.value as any).driver_id) (form.value as any).driver_id = me.id
      }
    } catch (e) {
      console.warn('[wbf] me fetch error', e)
    }
    if (queryVehicleId) {
      await autoPopulateFromVehicle(queryVehicleId)
    }
  }
})

// Watch спидометра/топлива для автосохранения (watcher остаётся во view —
// как и было в исходном FleetWaybillFormView.vue до разбиения на секции)
watch([() => form.value.odometer_start, () => form.value.odometer_finish,
       () => form.value.fuel_remaining_start, () => form.value.fuel_issued_l,
       () => form.value.fuel_remaining_finish], scheduleAutosave)
</script>

<style scoped></style>
