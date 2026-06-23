<template>
  <v-card class="maintenance-warning-widget h-100 d-flex flex-column" elevation="2">
    <v-card-title class="d-flex align-center ga-2 pb-1">
      <v-icon icon="mdi-alert-circle-outline" color="warning" size="20" />
      <span class="text-subtitle-1 font-weight-medium">Предупреждения</span>
      <v-spacer />
      <v-chip v-if="warnings.length > 0" :color="hasHighSeverity ? 'error' : 'warning'" size="x-small" variant="tonal">
        {{ warnings.length }}
      </v-chip>
    </v-card-title>

    <v-divider />

    <div class="flex-grow-1 overflow-y-auto pa-2">
      <!-- Loading state -->
      <div v-if="loading" class="d-flex justify-center align-center py-6">
        <v-progress-circular indeterminate color="warning" size="32" />
      </div>

      <!-- Error state -->
      <v-alert v-else-if="error" type="error" density="compact" variant="tonal" class="ma-1">
        {{ error }}
      </v-alert>

      <!-- Empty state -->
      <div v-else-if="warnings.length === 0" class="d-flex flex-column align-center justify-center py-8 text-medium-emphasis">
        <v-icon icon="mdi-check-circle-outline" color="success" size="40" class="mb-2" />
        <span class="text-body-2">Нет просрочек</span>
      </div>

      <!-- Warning cards -->
      <template v-else>
        <div
          v-for="(w, idx) in warnings"
          :key="idx"
          class="warn-card"
          :class="cardClass(w)"
          @click="navigateTo(w)"
        >
          <div class="d-flex align-center ga-2">
            <v-icon :icon="typeIcon(w.warning_type)" :color="typeColor(w.warning_type)" size="20" />
            <div class="flex-grow-1 min-width-0">
              <div class="text-body-2 font-weight-medium text-truncate">
                {{ cardTitle(w) }}
              </div>
              <div class="text-caption text-medium-emphasis">
                {{ cardSubtitle(w) }}
              </div>
            </div>
            <v-chip
              :color="severityColor(w)"
              size="x-small"
              variant="tonal"
              class="flex-shrink-0"
            >
              {{ severityLabel(w) }}
            </v-chip>
          </div>
        </div>
      </template>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

interface Warning {
  vehicle_id: number
  brand: string | null
  model: string | null
  plate: string
  warning_type: 'TO_SOON' | 'OSAGO_EXPIRY' | 'LICENSE_EXPIRY' | 'MED_CERT_EXPIRY'
  days_left: number | null
  km_left: number | null
}

const router = useRouter()

const warnings = ref<Warning[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const hasHighSeverity = computed(() =>
  warnings.value.some(w => isHigh(w))
)

function isHigh(w: Warning): boolean {
  if (w.km_left !== null) return w.km_left < 500
  if (w.days_left !== null) return w.days_left < 7
  return false
}

function isExpired(w: Warning): boolean {
  if (w.km_left !== null) return w.km_left <= 0
  if (w.days_left !== null) return w.days_left <= 0
  return false
}

function cardClass(w: Warning): string {
  if (isExpired(w)) return 'warn-card-expired'
  if (isHigh(w)) return 'warn-card-high'
  return 'warn-card-medium'
}

function typeIcon(type: Warning['warning_type']): string {
  switch (type) {
    case 'TO_SOON': return 'mdi-tools'
    case 'OSAGO_EXPIRY': return 'mdi-shield-alert'
    case 'LICENSE_EXPIRY': return 'mdi-card-account-details'
    case 'MED_CERT_EXPIRY': return 'mdi-medical-bag'
    default: return 'mdi-alert'
  }
}

function typeColor(type: Warning['warning_type']): string {
  switch (type) {
    case 'TO_SOON': return 'orange'
    case 'OSAGO_EXPIRY': return 'error'
    case 'LICENSE_EXPIRY': return 'error'
    case 'MED_CERT_EXPIRY': return 'warning'
    default: return 'warning'
  }
}

function cardTitle(w: Warning): string {
  const parts = [w.plate]
  if (w.brand) parts.push(w.brand)
  if (w.model) parts.push(w.model)
  return parts.join(' ')
}

function cardSubtitle(w: Warning): string {
  switch (w.warning_type) {
    case 'TO_SOON':
      return w.km_left !== null
        ? `ТО через ${w.km_left} км`
        : 'ТО скоро'
    case 'OSAGO_EXPIRY':
      return w.days_left !== null
        ? (w.days_left <= 0 ? 'ОСАГО истекло' : `ОСАГО через ${w.days_left} дн.`)
        : 'ОСАГО истекает'
    case 'LICENSE_EXPIRY':
      return w.days_left !== null
        ? (w.days_left <= 0 ? 'ВУ водителя истекло' : `ВУ водителя через ${w.days_left} дн.`)
        : 'ВУ водителя истекает'
    case 'MED_CERT_EXPIRY':
      return w.days_left !== null
        ? (w.days_left <= 0 ? 'Медсправка истекла' : `Медсправка через ${w.days_left} дн.`)
        : 'Медсправка истекает'
    default:
      return ''
  }
}

function severityColor(w: Warning): string {
  if (isExpired(w)) return 'error'
  if (isHigh(w)) return 'error'
  return 'warning'
}

function severityLabel(w: Warning): string {
  if (isExpired(w)) return 'Истекло'
  if (isHigh(w)) return 'Критично'
  return 'Скоро'
}

function navigateTo(w: Warning): void {
  router.push(`/property/vehicles/${w.vehicle_id}`)
}

async function fetchWarnings(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const token = localStorage.getItem('auth_token') ?? ''
    const res = await fetch('/api/vehicles-dashboard/maintenance-warning', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data?.detail || `HTTP ${res.status}`)
    }
    warnings.value = await res.json()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Ошибка загрузки'
  } finally {
    loading.value = false
  }
}

onMounted(fetchWarnings)
</script>

<style scoped>
@keyframes pulse-glow-high {
  0%, 100% { box-shadow: 0 0 0 0 rgba(244, 67, 54, 0.7); }
  50% { box-shadow: 0 0 12px 4px rgba(244, 67, 54, 0.3); }
}

@keyframes pulse-glow-medium {
  0%, 100% { box-shadow: 0 0 0 0 rgba(255, 152, 0, 0.5); }
  50% { box-shadow: 0 0 8px 2px rgba(255, 152, 0, 0.2); }
}

.warn-card {
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: opacity 0.15s;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid transparent;
}

.warn-card:hover {
  opacity: 0.85;
  animation-play-state: paused !important;
}

.warn-card-high {
  animation: pulse-glow-high 1.4s ease-in-out infinite;
  border-color: rgba(244, 67, 54, 0.35);
}

.warn-card-medium {
  animation: pulse-glow-medium 2.4s ease-in-out infinite;
  border-color: rgba(255, 152, 0, 0.3);
}

.warn-card-expired {
  animation: none;
  border: 2px solid rgba(244, 67, 54, 0.6);
}

.overflow-y-auto {
  overflow-y: auto;
}

.min-width-0 {
  min-width: 0;
}
</style>
