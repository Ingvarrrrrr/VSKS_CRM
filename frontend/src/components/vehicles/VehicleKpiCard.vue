<template>
  <v-card class="vehicle-kpi-card h-100 d-flex flex-column justify-center" elevation="2" :color="cardBg">
    <v-card-text class="pa-3">
      <div class="d-flex align-center justify-space-between mb-1">
        <div class="kpi-icon-box" :style="{ background: iconBg }">
          <v-icon :icon="icon" :color="color || 'primary'" size="22" />
        </div>
        <div v-if="trendPct !== undefined" class="d-flex align-center gap-1">
          <v-icon
            :icon="trendPct >= 0 ? 'mdi-trending-up' : 'mdi-trending-down'"
            :color="trendPct >= 0 ? 'success' : 'error'"
            size="16"
          />
          <span class="text-caption" :class="trendPct >= 0 ? 'text-success' : 'text-error'">
            {{ Math.abs(trendPct).toFixed(1) }}%
          </span>
        </div>
      </div>
      <div class="kpi-value mt-2">{{ formattedValue }}</div>
      <div class="kpi-title text-medium-emphasis text-caption mt-1">{{ title }}</div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useTheme } from 'vuetify'

const props = defineProps<{
  title: string
  value: number
  unit?: string
  icon: string
  color?: string
  trendPct?: number
}>()

const theme = useTheme()
const isDark = computed(() => theme.global.name.value === 'dark')

const cardBg = computed(() => isDark.value ? 'surface-variant' : undefined)
const iconBg = computed(() => isDark.value ? 'rgba(255,255,255,0.08)' : 'rgba(25,118,210,0.08)')

const formattedValue = computed(() => {
  const v = props.value ?? 0
  const unit = props.unit ?? ''
  if (unit === '₽') {
    // Format currency: 1 234 567 ₽
    return v.toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽'
  }
  if (unit === 'км') {
    return v.toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' км'
  }
  if (unit) {
    return v.toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ' + unit
  }
  return v.toLocaleString('ru-RU', { maximumFractionDigits: 0 })
})
</script>

<style scoped>
.vehicle-kpi-card {
  min-height: 90px;
  border-radius: 10px !important;
  transition: box-shadow 0.2s ease;
}

.vehicle-kpi-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12) !important;
}

.kpi-icon-box {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.kpi-value {
  font-size: 1.3rem;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.3px;
}

.kpi-title {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  font-weight: 500;
}
</style>
