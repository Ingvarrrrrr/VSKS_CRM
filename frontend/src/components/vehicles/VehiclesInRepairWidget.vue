<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'

interface InRepairItem {
  vehicle_id: number
  brand: string | null
  model: string | null
  plate: string
  photo_attachment_id: number | null
  repair_id: number
  repair_status: 'planned' | 'in_progress' | string
  repair_description: string | null
  mileage_at_repair: number | null
  repair_date: string | null
  expected_finish_date: string | null
}

const router = useRouter()

const items = ref<InRepairItem[]>([])
const loading = ref(false)
const blobUrls = ref<Record<number, string>>({})

// ── Fetch list ────────────────────────────────────────────────────────────────

async function fetchList() {
  loading.value = true
  try {
    const res = await fetch('/api/vehicles-dashboard/in-repair', {
      credentials: 'include',
    })
    if (!res.ok) return
    const data: InRepairItem[] = await res.json()
    items.value = data
    for (const item of data) {
      if (item.photo_attachment_id && !blobUrls.value[item.photo_attachment_id]) {
        loadPhoto(item.photo_attachment_id)
      }
    }
  } catch (e) {
    console.error('VehiclesInRepairWidget fetch error', e)
  } finally {
    loading.value = false
  }
}

async function loadPhoto(attachmentId: number) {
  try {
    const res = await fetch(`/api/vehicle-attachments/${attachmentId}/download`, {
      credentials: 'include',
    })
    if (!res.ok) return
    const blob = await res.blob()
    blobUrls.value = { ...blobUrls.value, [attachmentId]: URL.createObjectURL(blob) }
  } catch {
    // silently skip — thumbnail stays placeholder
  }
}

// ── Progress bar helpers ──────────────────────────────────────────────────────

function progressValue(item: InRepairItem): number {
  if (!item.repair_date || !item.expected_finish_date) return 0
  const start = new Date(item.repair_date).getTime()
  const end = new Date(item.expected_finish_date).getTime()
  const now = Date.now()
  if (end <= start) return 0
  const pct = ((now - start) / (end - start)) * 100
  return Math.min(100, Math.max(0, Math.round(pct)))
}

function hasProgress(item: InRepairItem): boolean {
  return !!item.repair_date && !!item.expected_finish_date
}

function progressColor(pct: number): string {
  if (pct >= 90) return 'error'
  if (pct >= 70) return 'warning'
  return 'primary'
}

// ── Formatting ────────────────────────────────────────────────────────────────

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

function vehicleTitle(item: InRepairItem): string {
  const parts = [item.brand, item.model].filter(Boolean)
  return parts.length ? parts.join(' ') : item.plate
}

// ── Status chip ───────────────────────────────────────────────────────────────

function statusLabel(status: string): string {
  return status === 'in_progress' ? 'В ремонте' : 'Запланирован'
}

function statusColor(status: string): string {
  return status === 'in_progress' ? 'blue' : 'grey'
}

// ── Navigation ────────────────────────────────────────────────────────────────

function openVehicle(vehicleId: number) {
  router.push({ path: `/property/vehicles/${vehicleId}`, query: { tab: 'repairs' } })
}

// ── Computed ──────────────────────────────────────────────────────────────────

const count = computed(() => items.value.length)

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(() => {
  fetchList()
})

onUnmounted(() => {
  for (const url of Object.values(blobUrls.value)) {
    URL.revokeObjectURL(url)
  }
  blobUrls.value = {}
})
</script>

<template>
  <v-card class="vehicles-in-repair-widget h-100 d-flex flex-column" elevation="2">
    <!-- Header -->
    <v-card-title class="d-flex align-center gap-2 pb-1">
      <v-icon icon="mdi-wrench" color="primary" size="20" />
      <span class="text-subtitle-1 font-weight-medium">Машины в ремонте</span>
      <v-badge
        v-if="count > 0"
        :content="count"
        color="primary"
        inline
        class="ml-1"
      />
      <v-spacer />
      <v-btn
        icon="mdi-refresh"
        variant="text"
        size="x-small"
        :loading="loading"
        @click="fetchList"
      />
    </v-card-title>

    <v-divider />

    <!-- Loading skeleton -->
    <div v-if="loading && !items.length" class="pa-3">
      <v-row dense>
        <v-col v-for="n in 3" :key="n" cols="12" sm="6" md="4">
          <v-skeleton-loader type="card" />
        </v-col>
      </v-row>
    </div>

    <!-- Empty state -->
    <div
      v-else-if="!loading && !items.length"
      class="d-flex flex-column align-center justify-center flex-grow-1 py-8 text-success"
    >
      <v-icon icon="mdi-check-circle-outline" size="48" color="success" class="mb-2" />
      <span class="text-body-1 font-weight-medium">Все машины в строю ✓</span>
    </div>

    <!-- Cards grid -->
    <v-card-text v-else class="pa-2 flex-grow-1 overflow-y-auto">
      <v-row dense>
        <v-col
          v-for="item in items"
          :key="item.vehicle_id"
          cols="12"
          sm="6"
          md="4"
        >
          <v-card
            class="repair-card cursor-pointer"
            variant="outlined"
            hover
            @click="openVehicle(item.vehicle_id)"
          >
            <!-- Photo / Placeholder -->
            <div class="repair-card__photo">
              <v-img
                v-if="item.photo_attachment_id && blobUrls[item.photo_attachment_id]"
                :src="blobUrls[item.photo_attachment_id]"
                cover
                height="100"
              />
              <div
                v-else
                class="d-flex align-center justify-center bg-grey-lighten-4"
                style="height: 100px;"
              >
                <v-icon icon="mdi-car" size="48" color="grey-lighten-1" />
              </div>
            </div>

            <v-card-text class="pa-2">
              <!-- Title + plate -->
              <div class="d-flex align-center gap-1 flex-wrap mb-1">
                <span class="text-body-2 font-weight-medium text-truncate" style="max-width: 120px;">
                  {{ vehicleTitle(item) }}
                </span>
                <v-chip size="x-small" variant="tonal" color="secondary" label>
                  {{ item.plate }}
                </v-chip>
              </div>

              <!-- Status chip -->
              <v-chip
                size="x-small"
                :color="statusColor(item.repair_status)"
                variant="tonal"
                label
                class="mb-1"
              >
                {{ statusLabel(item.repair_status) }}
              </v-chip>

              <!-- Dates -->
              <div class="text-caption text-medium-emphasis mt-1">
                <div v-if="item.repair_date">
                  Начат {{ formatDate(item.repair_date) }}
                </div>
                <div v-if="item.expected_finish_date">
                  План: {{ formatDate(item.expected_finish_date) }}
                </div>
              </div>

              <!-- Progress bar -->
              <v-progress-linear
                v-if="hasProgress(item)"
                :model-value="progressValue(item)"
                :color="progressColor(progressValue(item))"
                height="4"
                rounded
                class="mt-2"
              />
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>

<style scoped>
.vehicles-in-repair-widget {
  min-height: 200px;
}

.repair-card {
  transition: box-shadow 0.2s ease;
}

.repair-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
}

.repair-card__photo {
  overflow: hidden;
  border-radius: 4px 4px 0 0;
}

.cursor-pointer {
  cursor: pointer;
}
</style>
