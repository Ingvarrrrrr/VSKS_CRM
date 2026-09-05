<template>
  <v-dialog :model-value="modelValue" max-width="760" scrollable @update:model-value="$emit('update:modelValue', $event)">
    <v-card class="rounded-xl">
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon icon="mdi-map-marker-path" class="mr-2" />
        Трек: {{ userName }}
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="$emit('update:modelValue', false)" />
      </v-card-title>

      <v-card-text class="pa-4 pt-2">
        <div class="d-flex flex-wrap ga-3 mb-3 align-end">
          <v-text-field
            v-model="dateFrom" type="date" label="С" density="compact" variant="outlined"
            hide-details style="max-width: 170px"
          />
          <v-text-field
            v-model="dateTo" type="date" label="По" density="compact" variant="outlined"
            hide-details style="max-width: 170px"
          />
          <v-btn color="primary" variant="tonal" :loading="loading" @click="load">Показать</v-btn>
        </div>

        <div v-if="loading" class="text-center pa-6">
          <v-progress-circular indeterminate color="primary" />
        </div>

        <template v-else>
          <div v-if="!points.length" class="text-medium-emphasis text-body-2 pa-4 text-center">
            За выбранный период точек нет.
          </div>
          <template v-else>
            <div class="text-caption text-medium-emphasis mb-2">
              Точек: {{ points.length }} · с {{ fmtDateTime(points[0].recorded_at) }} по {{ fmtDateTime(points[points.length - 1].recorded_at) }}
            </div>

            <!-- Мини-карта: та же проекция, что и «Где люди» / регионы автопарка —
                 точность в сотни метров, карта показывает МАКРО-перемещение
                 (в каком районе/городе был человек), не пошаговую навигацию. -->
            <div class="std-map mb-3">
              <RussiaMapSvg :pins="trackPins" :connections="trackConnections" />
            </div>

            <div class="std-list">
              <div v-for="p in reversedPoints" :key="p.id" class="std-row">
                <span class="std-row__time">{{ fmtDateTime(p.recorded_at) }}</span>
                <span class="std-row__coords">{{ p.lat.toFixed(5) }}, {{ p.lon.toFixed(5) }}</span>
                <span class="std-row__acc">{{ p.accuracy_m != null ? `±${Math.round(p.accuracy_m)} м` : '—' }}</span>
              </div>
            </div>
          </template>
        </template>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import RussiaMapSvg from '@/components/fleet/RussiaMapSvg.vue'
import { projectLatLonToSvg, type MapPin, type MapConnection } from '@/components/fleet/russiaMapPins'

interface TrackPoint {
  id: number
  user_id: number
  lat: number
  lon: number
  accuracy_m: number | null
  recorded_at: string
  received_at: string
  source: string
}

const props = defineProps<{
  modelValue: boolean
  userId: number | null
  userName: string
}>()

defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const toast = useToast()
const loading = ref(false)
const points = ref<TrackPoint[]>([])

function todayStr(): string {
  return new Date().toISOString().slice(0, 10)
}

const dateFrom = ref(todayStr())
const dateTo = ref(todayStr())

const reversedPoints = computed(() => [...points.value].reverse())

// Пины трека: старые — приглушённый цвет, самая свежая точка — акцентный
// оранжевый и крупнее, чтобы сразу читалось «человек СЕЙЧАС здесь».
const trackPins = computed<MapPin[]>(() => {
  const n = points.value.length
  return points.value.map((p, idx) => {
    const { x, y } = projectLatLonToSvg(p.lat, p.lon)
    const isLast = idx === n - 1
    return {
      id: p.id,
      x, y,
      radius: isLast ? 10 : 5,
      count: 0,
      glyph: '',
      color: isLast ? '#fb923c' : '#6aa6ff',
      hint: fmtDateTime(p.recorded_at),
    } as MapPin
  })
})

const trackConnections = computed<MapConnection[]>(() => {
  const pins = trackPins.value
  const out: MapConnection[] = []
  for (let i = 1; i < pins.length; i++) {
    out.push({ from: { x: pins[i - 1].x, y: pins[i - 1].y }, to: { x: pins[i].x, y: pins[i].y } })
  }
  return out
})

function fmtDateTime(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function load() {
  if (props.userId == null) return
  loading.value = true
  try {
    const from = `${dateFrom.value}T00:00:00`
    const to = `${dateTo.value}T23:59:59`
    const data = await apiFetch<TrackPoint[]>(
      `/staff-location/track/${props.userId}?date_from=${encodeURIComponent(from)}&date_to=${encodeURIComponent(to)}`
    )
    points.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    toast.error(`Не удалось загрузить трек: ${e?.payload?.message || e?.message || 'ошибка сети'}`)
    points.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, (open) => {
  if (open && props.userId != null) {
    dateFrom.value = todayStr()
    dateTo.value = todayStr()
    load()
  }
})
</script>

<style scoped>
.std-map {
  height: 260px;
  border-radius: 12px;
  overflow: hidden;
}
.std-map :deep(.russia-map svg) {
  height: 260px;
}
.std-list {
  max-height: 260px;
  overflow-y: auto;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}
.std-row {
  display: grid;
  grid-template-columns: 100px 1fr 80px;
  gap: 8px;
  padding: 6px 10px;
  font-size: 12.5px;
  font-family: 'JetBrains Mono', monospace;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.std-row:last-child { border-bottom: none; }
.std-row__acc { text-align: right; opacity: 0.7; }
</style>
