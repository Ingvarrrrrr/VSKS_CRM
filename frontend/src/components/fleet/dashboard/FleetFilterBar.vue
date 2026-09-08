<template>
  <div class="fleet-filterbar">
    <div class="fleet-filterbar__item">
      <label class="fleet-filterbar__label">Тип ТС</label>
      <select
        multiple
        :value="selectedTypes"
        @change="onTypesChange"
        class="fleet-filterbar__select"
        size="1"
      >
        <option v-for="t in vehicleTypeOptions" :key="t.value" :value="t.value">{{ t.label }}</option>
      </select>
      <div class="fleet-filterbar__chips" v-if="selectedTypes.length">
        <span
          v-for="t in selectedTypes"
          :key="t"
          class="fleet-filterbar__chip"
          @click="$emit('update:selectedTypes', selectedTypes.filter(x => x !== t))"
        >{{ vehicleTypeLabels[t] || t }} ×</span>
      </div>
    </div>
    <div class="fleet-filterbar__item">
      <label class="fleet-filterbar__label">Регион</label>
      <select
        multiple
        :value="selectedRegions"
        @change="onRegionsChange"
        class="fleet-filterbar__select"
        size="1"
      >
        <option v-for="reg in availableRegions" :key="reg" :value="reg">{{ reg }}</option>
      </select>
      <div class="fleet-filterbar__chips" v-if="selectedRegions.length">
        <span
          v-for="reg in selectedRegions"
          :key="reg"
          class="fleet-filterbar__chip"
          @click="$emit('update:selectedRegions', selectedRegions.filter(x => x !== reg))"
        >{{ reg }} ×</span>
      </div>
    </div>
    <button
      v-if="selectedTypes.length || selectedRegions.length"
      class="fleet-btn"
      style="align-self:flex-end"
      @click="$emit('update:selectedTypes', []); $emit('update:selectedRegions', [])"
    >Сбросить</button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  selectedTypes: string[]
  selectedRegions: string[]
  vehicleTypeOptions: { value: string; label: string }[]
  vehicleTypeLabels: Record<string, string>
  availableRegions: string[]
}>()

const emit = defineEmits<{
  (e: 'update:selectedTypes', value: string[]): void
  (e: 'update:selectedRegions', value: string[]): void
}>()

function onTypesChange(e: Event) {
  const opts = Array.from((e.target as HTMLSelectElement).selectedOptions).map(o => o.value)
  emit('update:selectedTypes', opts)
}
function onRegionsChange(e: Event) {
  const opts = Array.from((e.target as HTMLSelectElement).selectedOptions).map(o => o.value)
  emit('update:selectedRegions', opts)
}
</script>

<style scoped></style>
