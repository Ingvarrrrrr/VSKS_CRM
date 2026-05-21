<template>
  <v-card class="fine-leaders-widget h-100 d-flex flex-column" elevation="2" rounded="lg">
    <!-- Header -->
    <v-card-title class="d-flex align-center ga-2 pb-1 flex-wrap">
      <v-icon icon="mdi-podium" color="warning" size="20" />
      <span class="text-subtitle-1 font-weight-medium">Рекордсмены по штрафам</span>
      <v-spacer />
      <!-- Period selector -->
      <v-select
        v-model="selectedPeriod"
        :items="PERIODS"
        item-title="label"
        item-value="days"
        density="compact"
        variant="outlined"
        hide-details
        style="max-width:160px;font-size:12px"
        @update:model-value="fetchLeaders"
      />
    </v-card-title>

    <v-divider />

    <!-- Loading -->
    <div v-if="loading" class="d-flex justify-center align-center py-8 flex-grow-1">
      <v-progress-circular indeterminate color="warning" size="32" />
    </div>

    <!-- Empty state -->
    <div
      v-else-if="leaders.length === 0"
      class="d-flex flex-column align-center justify-center py-8 text-medium-emphasis flex-grow-1"
    >
      <v-icon icon="mdi-check-circle-outline" color="success" size="40" class="mb-2" />
      <span class="text-body-2">Штрафов пока нет</span>
    </div>

    <!-- Content -->
    <v-card-text v-else class="pa-3 d-flex flex-column ga-3 flex-grow-1 overflow-y-auto">

      <!-- Podium: top 3 -->
      <div class="podium-row" v-if="top3.length > 0">
        <!-- 2nd place (left) -->
        <div
          v-if="top3[1]"
          class="podium-card podium-card--silver"
          :style="{ '--podium-height': '80px' }"
        >
          <div class="podium-rank">2</div>
          <div class="podium-name text-truncate">{{ top3[1].driver_name || '— Не определён —' }}</div>
          <div class="podium-fines">{{ top3[1].fines_count }} шт.</div>
          <div class="podium-amount">{{ fmtRub(top3[1].fines_total) }}</div>
          <v-chip
            v-if="top3[1].unpaid_count > 0"
            color="error"
            size="x-small"
            variant="tonal"
            class="mt-1"
          >
            {{ top3[1].unpaid_count }} не оплачено
          </v-chip>
        </div>
        <div v-else class="podium-card podium-card--empty" />

        <!-- 1st place (center, tallest) -->
        <div
          class="podium-card podium-card--gold podium-card--first"
          :style="{ '--podium-height': '108px' }"
        >
          <div class="podium-rank">1</div>
          <div class="podium-name text-truncate">{{ top3[0].driver_name || '— Не определён —' }}</div>
          <div class="podium-fines">{{ top3[0].fines_count }} шт.</div>
          <div class="podium-amount">{{ fmtRub(top3[0].fines_total) }}</div>
          <v-chip
            v-if="top3[0].unpaid_count > 0"
            color="error"
            size="x-small"
            variant="tonal"
            class="mt-1"
          >
            {{ top3[0].unpaid_count }} не оплачено
          </v-chip>
        </div>

        <!-- 3rd place (right) -->
        <div
          v-if="top3[2]"
          class="podium-card podium-card--bronze"
          :style="{ '--podium-height': '64px' }"
        >
          <div class="podium-rank">3</div>
          <div class="podium-name text-truncate">{{ top3[2].driver_name || '— Не определён —' }}</div>
          <div class="podium-fines">{{ top3[2].fines_count }} шт.</div>
          <div class="podium-amount">{{ fmtRub(top3[2].fines_total) }}</div>
          <v-chip
            v-if="top3[2].unpaid_count > 0"
            color="error"
            size="x-small"
            variant="tonal"
            class="mt-1"
          >
            {{ top3[2].unpaid_count }} не оплачено
          </v-chip>
        </div>
        <div v-else class="podium-card podium-card--empty" />
      </div>

      <!-- Rest (4-10) -->
      <div v-if="rest.length > 0">
        <div class="text-caption text-medium-emphasis mb-1 px-1">Остальные</div>
        <v-list density="compact" class="pa-0 rounded border">
          <v-list-item
            v-for="(leader, idx) in rest"
            :key="leader.driver_key"
            class="px-3"
            :class="{ 'border-b': idx < rest.length - 1 }"
          >
            <template #prepend>
              <span class="text-caption text-medium-emphasis mr-2" style="min-width:20px">
                {{ idx + 4 }}.
              </span>
            </template>
            <v-list-item-title class="text-body-2">
              {{ leader.driver_name || '— Не определён —' }}
            </v-list-item-title>
            <template #append>
              <div class="d-flex align-center ga-2">
                <span class="text-caption text-medium-emphasis">{{ leader.fines_count }} шт.</span>
                <span class="text-body-2 font-weight-medium">{{ fmtRub(leader.fines_total) }}</span>
                <v-chip
                  v-if="leader.unpaid_count > 0"
                  color="error"
                  size="x-small"
                  variant="tonal"
                >{{ leader.unpaid_count }}</v-chip>
              </div>
            </template>
          </v-list-item>
        </v-list>
      </div>

    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiFetch } from '@/api'

interface FineLeader {
  driver_key: string
  driver_name: string | null
  driver_kind: 'user' | 'external' | 'unmatched'
  fines_count: number
  fines_total: number
  unpaid_count: number
  unpaid_total: number
}

const PERIODS = [
  { label: 'Всё время', days: null },
  { label: 'Год', days: 365 },
  { label: '6 мес.', days: 180 },
  { label: 'Месяц', days: 30 },
]

const selectedPeriod = ref<number | null>(null)
const leaders = ref<FineLeader[]>([])
const loading = ref(false)

const top3 = computed(() => leaders.value.slice(0, 3))
const rest = computed(() => leaders.value.slice(3))

function fmtRub(val: number): string {
  return val.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 })
}

async function fetchLeaders(): Promise<void> {
  loading.value = true
  try {
    const params = new URLSearchParams({ limit: '10' })
    if (selectedPeriod.value != null) {
      params.set('period_days', String(selectedPeriod.value))
    }
    leaders.value = await apiFetch<FineLeader[]>(`/vehicles-dashboard/fine-leaders?${params}`)
  } catch (e) {
    console.error('[FineLeaders]', e)
    leaders.value = []
  } finally {
    loading.value = false
  }
}

onMounted(fetchLeaders)
</script>

<style scoped>
.fine-leaders-widget {
  min-height: 260px;
}

/* Podium layout: 2-1-3 order */
.podium-row {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 8px;
  padding: 8px 4px 4px;
}

.podium-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  min-height: var(--podium-height, 80px);
  border-radius: 10px;
  padding: 8px 6px;
  text-align: center;
  position: relative;
}

.podium-card--empty {
  background: transparent;
  min-height: 80px;
}

.podium-card--gold {
  background: linear-gradient(160deg, #FFF8E1 0%, #FFE082 100%);
  border: 2px solid #FFC107;
}

.podium-card--silver {
  background: linear-gradient(160deg, #F5F5F5 0%, #E0E0E0 100%);
  border: 2px solid #9E9E9E;
}

.podium-card--bronze {
  background: linear-gradient(160deg, #FFF3E0 0%, #FFCC80 100%);
  border: 2px solid #CD7F32;
}

.podium-rank {
  font-size: 22px;
  font-weight: 800;
  line-height: 1;
  margin-bottom: 4px;
}

.podium-card--gold .podium-rank { color: #E65100; }
.podium-card--silver .podium-rank { color: #424242; }
.podium-card--bronze .podium-rank { color: #6D4C41; }

.podium-name {
  font-size: 11px;
  font-weight: 600;
  max-width: 90px;
  line-height: 1.2;
  margin-bottom: 2px;
}

.podium-fines {
  font-size: 10px;
  color: rgba(0, 0, 0, 0.55);
}

.podium-amount {
  font-size: 11px;
  font-weight: 700;
  color: rgba(0, 0, 0, 0.8);
}
</style>
