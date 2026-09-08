<!-- Quick-stats strip карточки ТС: пробег, ТО, документы. -->
<template>
  <div class="vp-qstats mb-4">
    <!-- Пробег -->
    <div class="vp-qs vp-qs--clickable" title="Перейти на вкладку «Пробег»" @click="$emit('open-odometer')">
      <div class="vp-qs__label d-flex align-center">
        <span>Пробег</span>
        <FieldHint field-key="current_odometer_km" />
      </div>
      <div class="vp-qs__value">
        {{ vehicle.current_odometer_km != null ? vehicle.current_odometer_km.toLocaleString('ru-RU') : '—' }}
        <span class="vp-qs__unit" v-if="vehicle.current_odometer_km != null">км</span>
      </div>
      <div class="vp-qs__sub">текущий одометр — вкладка «Пробег»</div>
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
</template>

<script setup lang="ts">
import FieldHint from './FieldHint.vue'
import type { Vehicle } from '@/composables/fleet/vehicleDetailTypes'

defineProps<{
  vehicle: Vehicle
  isToSoon: boolean
  docsStatus: { filled: number; hasProblems: boolean; problemText: string }
  formatDate: (d?: string | null) => string
}>()

defineEmits<{
  (e: 'open-odometer'): void
}>()
</script>
