<template>
  <div class="fuel-readout">
    <!-- 3 inputs row -->
    <div class="fuel-readout__row">
      <div class="fuel-readout__field">
        <div class="fuel-readout__label">При выезде</div>
        <template v-if="readonly">
          <div class="fuel-readout__val" :class="fuelStartClass">
            {{ fmt(fuelStart) }} <span class="unit">л</span>
          </div>
        </template>
        <template v-else>
          <v-text-field
            :model-value="fuelStart"
            label="При выезде"
            type="number"
            variant="outlined"
            density="compact"
            hide-spin-buttons
            hide-details
            @update:model-value="v => emit('update:fuelStart', toNum(v))"
          >
            <template #append-inner><span class="fuel-readout__unit">л</span></template>
          </v-text-field>
        </template>
      </div>

      <div class="fuel-readout__field">
        <div class="fuel-readout__label">Выдано</div>
        <template v-if="readonly">
          <div class="fuel-readout__val fuel-readout__val--warn">
            {{ fmt(fuelIssued) }} <span class="unit">л</span>
          </div>
        </template>
        <template v-else>
          <v-text-field
            :model-value="fuelIssued"
            label="Выдано"
            type="number"
            variant="outlined"
            density="compact"
            hide-spin-buttons
            hide-details
            @update:model-value="v => emit('update:fuelIssued', toNum(v))"
          >
            <template #append-inner><span class="fuel-readout__unit">л</span></template>
          </v-text-field>
        </template>
      </div>

      <div class="fuel-readout__field">
        <div class="fuel-readout__label">При возврате</div>
        <template v-if="readonly">
          <div class="fuel-readout__val" :class="fuelEndClass">
            {{ fuelEnd !== undefined ? `${fmt(fuelEnd)} л` : '—' }}
          </div>
        </template>
        <template v-else>
          <v-text-field
            :model-value="fuelEnd"
            label="При возврате"
            type="number"
            variant="outlined"
            density="compact"
            hide-spin-buttons
            hide-details
            @update:model-value="v => emit('update:fuelEnd', toNum(v))"
          >
            <template #append-inner><span class="fuel-readout__unit">л</span></template>
          </v-text-field>
        </template>
      </div>
    </div>

    <!-- Computed stats -->
    <div v-if="showStats" class="fuel-readout__stats">
      <div class="fuel-readout__stat">
        <span class="fuel-readout__stat-label">Расход</span>
        <span class="fuel-readout__stat-val">{{ consumedLabel }}</span>
      </div>
      <div v-if="mileageKm && mileageKm > 0" class="fuel-readout__stat">
        <span class="fuel-readout__stat-label">л / 100 км</span>
        <span class="fuel-readout__stat-val" :class="per100Class">{{ per100Label }}</span>
      </div>
      <div v-if="normPer100km && mileageKm && mileageKm > 0" class="fuel-readout__stat">
        <span class="fuel-readout__stat-label">Экономия / перерасход</span>
        <span class="fuel-readout__stat-val" :class="diffClass">{{ diffLabel }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  fuelStart?: number
  fuelIssued?: number
  fuelEnd?: number
  mileageKm?: number
  normPer100km?: number
  readonly?: boolean
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  (e: 'update:fuelStart',  v: number | undefined): void
  (e: 'update:fuelIssued', v: number | undefined): void
  (e: 'update:fuelEnd',    v: number | undefined): void
}>()

function toNum(v: string | number | null | undefined): number | undefined {
  if (v === '' || v === null || v === undefined) return undefined
  const n = Number(v)
  return isNaN(n) ? undefined : n
}

function fmt(v?: number): string {
  if (v === undefined) return '—'
  return v.toLocaleString('ru-RU')
}

// consumed = start + issued - end
const consumed = computed<number | undefined>(() => {
  if (props.fuelStart === undefined || props.fuelEnd === undefined) return undefined
  return (props.fuelStart ?? 0) + (props.fuelIssued ?? 0) - props.fuelEnd
})

const consumedLabel = computed(() =>
  consumed.value !== undefined ? `${fmt(consumed.value)} л` : '—'
)

const per100 = computed<number | undefined>(() => {
  if (consumed.value === undefined || !props.mileageKm || props.mileageKm === 0) return undefined
  return (consumed.value / props.mileageKm) * 100
})

const per100Label = computed(() =>
  per100.value !== undefined ? `${per100.value.toFixed(1)} л` : '—'
)

// diff vs norm
const normConsumed = computed<number | undefined>(() => {
  if (!props.normPer100km || !props.mileageKm) return undefined
  return (props.normPer100km / 100) * props.mileageKm
})

const diff = computed<number | undefined>(() => {
  if (consumed.value === undefined || normConsumed.value === undefined) return undefined
  return normConsumed.value - consumed.value // positive = economy, negative = overrun
})

const diffLabel = computed(() => {
  if (diff.value === undefined) return '—'
  const abs = Math.abs(diff.value).toFixed(1)
  return diff.value >= 0 ? `+${abs} л экономия` : `-${abs} л перерасход`
})

const diffClass = computed(() => {
  if (diff.value === undefined) return ''
  return diff.value >= 0 ? 'fuel-readout__stat-val--ok' : 'fuel-readout__stat-val--alert'
})

const per100Class = computed(() => {
  if (per100.value === undefined || !props.normPer100km) return ''
  return per100.value > props.normPer100km ? 'fuel-readout__stat-val--alert' : 'fuel-readout__stat-val--ok'
})

const fuelStartClass = computed(() =>
  props.fuelStart !== undefined ? 'fuel-readout__val--ok' : 'fuel-readout__val--muted'
)

const fuelEndClass = computed(() =>
  props.fuelEnd !== undefined ? 'fuel-readout__val--ok' : 'fuel-readout__val--muted'
)

const showStats = computed(() =>
  consumed.value !== undefined || per100.value !== undefined
)
</script>

<style scoped>
.fuel-readout {
  display: grid;
  gap: 10px;
}

.fuel-readout__row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px;
}

.fuel-readout__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.fuel-readout__label {
  font-size: 10.5px;
  color: var(--muted, #8a93a8);
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.3px;
}

.fuel-readout__val {
  font-weight: 800;
  font-size: 18px;
  letter-spacing: -0.3px;
  color: var(--muted, #8a93a8);
}

.fuel-readout__val--ok    { color: var(--ok,    #22c997); }
.fuel-readout__val--warn  { color: var(--warn,  #f6b34a); }
.fuel-readout__val--muted { color: var(--muted, #8a93a8); }

.fuel-readout__unit {
  font-size: 12px;
  color: var(--muted, #8a93a8);
  font-weight: 500;
}

.unit {
  font-size: 12px;
  color: var(--muted, #8a93a8);
  font-weight: 500;
}

.fuel-readout__stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--line, #222838);
  border-radius: 10px;
}

.fuel-readout__stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.fuel-readout__stat-label {
  font-size: 10.5px;
  color: var(--muted, #8a93a8);
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.3px;
}

.fuel-readout__stat-val {
  font-weight: 700;
  font-size: 14px;
  color: var(--text, #e9edf5);
}

.fuel-readout__stat-val--ok    { color: var(--ok,    #22c997); }
.fuel-readout__stat-val--alert { color: var(--alert, #ff5b6a); }
</style>
