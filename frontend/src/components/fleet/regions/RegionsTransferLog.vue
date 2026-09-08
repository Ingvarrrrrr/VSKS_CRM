<template>
  <section class="rv-panel rv-transfers" style="margin-top:22px">
    <div class="rv-panel__head">
      <span>Журнал передач между организациями</span>
      <small>последние перемещения</small>
    </div>
    <div v-if="loading" class="rv-loading">
      <div class="rv-spinner"></div>
    </div>
    <div v-else-if="!transfers.length" class="rv-empty">
      Журнал передач пуст
    </div>
    <div v-else class="rv-tx-list">
      <div
        v-for="tx in transfers"
        :key="tx.id"
        class="rv-tx"
        @click="$emit('go-to-vehicle', tx.vehicle_id)"
      >
        <!-- 2026-09 (правка после ревью #2): у tx НЕТ полей from_type/to_type —
             backend (/vehicles-dashboard/transfer-history-recent) их не отдаёт,
             поэтому здесь всегда рендерился один и тот же фейковый фолбэк
             «филиал» под КАЖДОЙ записью независимо от реальных данных. Раз
             реальных данных нет — строку просто не показываем, а не подставляем
             выдуманную. -->
        <LicensePlate :modelValue="tx.plate" size="sm" />
        <div class="rv-tx__from">
          <div class="rv-tx__nm">{{ tx.from_org_name || tx.from_assigned_text || '—' }}</div>
        </div>
        <div class="rv-tx__arr">→</div>
        <div class="rv-tx__to">
          <div class="rv-tx__nm">{{ tx.to_org_name || tx.to_assigned_text || '—' }}</div>
        </div>
        <div class="rv-tx__detail">
          <span>{{ tx.brand_model || '' }}</span>
          <span v-if="tx.basis" class="rv-tx__basis"> · {{ tx.basis }}</span>
        </div>
        <div class="rv-tx__when">{{ formatDate(tx.changed_at) }}</div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import type { TransferRow } from '@/composables/fleet/regions/useRegionsData'

defineProps<{
  loading: boolean
  transfers: TransferRow[]
  formatDate: (iso: string) => string
}>()

defineEmits<{
  (e: 'go-to-vehicle', vehicleId: number): void
}>()
</script>

<style scoped></style>
