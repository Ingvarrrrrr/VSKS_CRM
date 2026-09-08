<template>
  <div class="fleet-panel">
    <h3 class="fleet-panel__title">
      География эксплуатации
      <small>распределение по филиалам и регионам</small>
    </h3>
    <!-- Phase 29.3-R3: top-5 строк + 6-я "Прочее" (collapsible, persistent state) -->
    <div class="fleet-reg-rows" v-if="regionItems.length">
      <!-- Top-5 regions as rows -->
      <div
        v-for="reg in topRegions"
        :key="reg.region"
        class="fleet-reg-row"
        :class="{ 'fleet-reg-row--active': selectedRegions.includes(reg.region) }"
        @click="$emit('apply-region-filter', reg.region)"
      >
        <div class="fleet-reg-row__nm">{{ reg.region }}</div>
        <div class="fleet-reg-row__bar">
          <div class="fleet-reg-row__bar-fill" :style="`width: ${Math.round((reg.count / maxRegCount) * 100)}%`"></div>
        </div>
        <div class="fleet-reg-row__cnt">{{ reg.count }}</div>
      </div>

      <!-- 6-я строка: «Прочее» (только если есть остальные) -->
      <template v-if="otherRegions.length">
        <div
          class="fleet-reg-row fleet-reg-row--other"
          :class="{ 'fleet-reg-row--expanded': showOtherRegions }"
          @click="$emit('toggle-other')"
        >
          <div class="fleet-reg-row__nm">
            <span class="fleet-reg-row__caret">{{ showOtherRegions ? '▼' : '▶' }}</span>
            Прочее ({{ otherRegions.length }})
          </div>
          <div class="fleet-reg-row__bar">
            <div class="fleet-reg-row__bar-fill fleet-reg-row__bar-fill--other" :style="`width: ${Math.round((otherRegionsTotalCount / maxRegCount) * 100)}%`"></div>
          </div>
          <div class="fleet-reg-row__cnt">{{ otherRegionsTotalCount }}</div>
        </div>
        <!-- Раскрытое содержимое «Прочее» — остаётся открытым пока пользователь сам не свернёт -->
        <div
          v-for="reg in otherRegions"
          v-show="showOtherRegions"
          :key="reg.region"
          class="fleet-reg-row fleet-reg-row--nested"
          :class="{ 'fleet-reg-row--active': selectedRegions.includes(reg.region) }"
          @click="$emit('apply-region-filter', reg.region)"
        >
          <div class="fleet-reg-row__nm">{{ reg.region }}</div>
          <div class="fleet-reg-row__bar">
            <div class="fleet-reg-row__bar-fill" :style="`width: ${Math.round((reg.count / maxRegCount) * 100)}%`"></div>
          </div>
          <div class="fleet-reg-row__cnt">{{ reg.count }}</div>
        </div>
      </template>
    </div>
    <div class="fleet-empty" v-if="!regionItems.length">
      <v-progress-circular v-if="loadingRegions" indeterminate color="#6aa6ff" size="24" />
      <span v-else>Нет данных о регионах</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RegionItem } from '@/composables/fleet/dashboard/useFleetRegions'

defineProps<{
  regionItems: RegionItem[]
  topRegions: RegionItem[]
  otherRegions: RegionItem[]
  otherRegionsTotalCount: number
  maxRegCount: number
  selectedRegions: string[]
  showOtherRegions: boolean
  loadingRegions: boolean
}>()

defineEmits<{
  (e: 'apply-region-filter', region: string): void
  (e: 'toggle-other'): void
}>()
</script>

<style scoped></style>
