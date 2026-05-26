<template>
  <v-card v-if="driver" class="dfd-card" elevation="0">
    <div class="dfd-header">
      <div class="dfd-title">
        <v-icon size="20" icon="mdi-alert-octagon" class="mr-2" />
        Штрафы водителя: <b>{{ driver.driver_name || '— Не определён —' }}</b>
      </div>
      <button class="dfd-close" @click="$emit('close')" title="Закрыть">×</button>
    </div>

    <div v-if="loading" class="dfd-empty">
      <v-progress-circular indeterminate size="24" color="primary" />
      <span class="ml-2">Загрузка штрафов…</span>
    </div>

    <div v-else-if="fines.length === 0" class="dfd-empty">
      Штрафов не найдено
    </div>

    <div v-else class="dfd-grid">
      <div
        v-for="fine in fines"
        :key="fine.id"
        class="dfd-card-item"
        :class="`dfd-card-item--${fine.status || 'unpaid'}`"
      >
        <div class="dfd-photo">
          <img
            v-if="fine.has_photo"
            :src="photoUrl(fine.id)"
            alt="Фото штрафа"
            class="dfd-photo__img"
            @click="openZoom(fine.id)"
            @error="onPhotoError($event)"
          />
          <div v-else class="dfd-photo__placeholder">
            <v-icon icon="mdi-image-off-outline" size="28" />
            <span>Нет фото</span>
          </div>
        </div>

        <div class="dfd-body">
          <div class="dfd-row">
            <span class="dfd-date">{{ fmtDate(fine.issued_at) }}</span>
            <span class="dfd-amount">{{ fmtRub(fine.amount) }}</span>
          </div>
          <div class="dfd-violation">{{ fine.violation_type || '—' }}</div>
          <div class="dfd-location" v-if="fine.location">
            <v-icon size="12" icon="mdi-map-marker-outline" />
            {{ fine.location }}
          </div>
          <div class="dfd-meta">
            <span class="dfd-status" :class="`dfd-status--${fine.status}`">
              {{ statusLabel(fine.status) }}
            </span>
            <span v-if="fine.vehicle_plate" class="dfd-plate">{{ fine.vehicle_plate }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Zoom overlay -->
    <div v-if="zoomFineId" class="dfd-zoom" @click="zoomFineId = null">
      <img :src="photoUrl(zoomFineId)" alt="Фото штрафа (увеличено)" class="dfd-zoom__img" />
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { apiFetch } from '@/api'

interface DriverInfo {
  driver_key: string
  driver_name: string | null
  driver_kind: string
}

interface FineItem {
  id: number
  issued_at: string
  amount: number
  doc_number?: string | null
  violation_type?: string | null
  location?: string | null
  status: string
  vehicle_plate?: string | null
  has_photo?: boolean
}

const props = defineProps<{
  driver: DriverInfo | null
}>()

defineEmits<{
  (e: 'close'): void
}>()

const fines = ref<FineItem[]>([])
const loading = ref(false)
const zoomFineId = ref<number | null>(null)

async function load() {
  if (!props.driver) {
    fines.value = []
    return
  }
  loading.value = true
  try {
    // driver_key: "user:5" / "external:12" / "unmatched"
    const [kind, idStr] = props.driver.driver_key.split(':')
    const id = parseInt(idStr || '', 10)
    const params: Record<string, any> = { limit: 100 }
    if (kind === 'user' && id) params.driver_user_id = id
    else if (kind === 'external' && id) params.driver_external_id = id
    else {
      // unmatched — невозможно отфильтровать через API; покажем пустой список
      fines.value = []
      loading.value = false
      return
    }
    const qs = new URLSearchParams(params).toString()
    const data = await apiFetch<FineItem[]>(`/vehicle-fines/?${qs}`)
    fines.value = Array.isArray(data) ? data : []
  } catch (e) {
    console.error('[DriverFinesDrill]', e)
    fines.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.driver?.driver_key, () => load(), { immediate: true })

function photoUrl(fineId: number): string {
  return `/api/vehicle-fines/${fineId}/photo`
}

function openZoom(fineId: number) {
  zoomFineId.value = fineId
}

function onPhotoError(e: Event) {
  // Photo 404 — гарантируем что img скрывается gracefully
  (e.target as HTMLImageElement).style.display = 'none'
}

function fmtDate(iso: string): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return iso }
}

function fmtRub(val: number): string {
  return Number(val).toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 })
}

function statusLabel(s: string): string {
  return { unpaid: 'Не оплачен', paid: 'Оплачен', disputed: 'Оспорен' }[s] || s
}
</script>

<style scoped>
.dfd-card {
  background: var(--panel, #141823);
  border: 1px solid var(--line, #222838);
  border-radius: 14px;
  padding: 16px 20px;
  color: var(--text, #e9edf5);
  margin-top: 14px;
}
.dfd-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line, #222838);
}
.dfd-title { font-size: 16px; font-weight: 600; }
.dfd-title b { color: #6aa6ff; }
.dfd-close {
  background: transparent;
  border: 1px solid var(--line, #222838);
  color: var(--text, #e9edf5);
  width: 30px; height: 30px;
  border-radius: 50%;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  font-weight: 600;
  transition: background 0.15s, border-color 0.15s;
}
.dfd-close:hover { background: rgba(255,91,106,0.18); border-color: #ff5b6a; }

.dfd-empty {
  padding: 24px;
  text-align: center;
  color: var(--muted, #8a93a8);
  font-size: 13px;
}

.dfd-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
}

.dfd-card-item {
  background: var(--bg-2, #0f131c);
  border: 1px solid var(--line, #222838);
  border-radius: 10px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: border-color 0.15s, transform 0.15s;
}
.dfd-card-item:hover {
  border-color: rgba(106, 166, 255, 0.4);
  transform: translateY(-2px);
}
.dfd-card-item--unpaid { border-left: 4px solid #ff5b6a; }
.dfd-card-item--paid   { border-left: 4px solid #22c997; }
.dfd-card-item--disputed { border-left: 4px solid #f6b34a; }

.dfd-photo {
  width: 100%;
  aspect-ratio: 16/9;
  background: #0a0d14;
  position: relative;
  overflow: hidden;
}
.dfd-photo__img {
  width: 100%; height: 100%;
  object-fit: cover;
  cursor: zoom-in;
  transition: transform 0.2s;
}
.dfd-photo__img:hover { transform: scale(1.03); }
.dfd-photo__placeholder {
  width: 100%; height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  color: var(--muted-2, #5d6478);
  font-size: 11px;
}

.dfd-body { padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 4px; }
.dfd-row { display: flex; justify-content: space-between; align-items: baseline; }
.dfd-date { font-size: 12px; color: var(--muted, #8a93a8); }
.dfd-amount {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  color: #ff5b6a;
  font-size: 15px;
}
.dfd-violation { font-size: 13px; font-weight: 500; line-height: 1.3; }
.dfd-location {
  font-size: 11.5px;
  color: var(--muted, #8a93a8);
  display: flex;
  align-items: center;
  gap: 3px;
}
.dfd-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 4px;
}
.dfd-status {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 600;
}
.dfd-status--unpaid { background: rgba(255,91,106,0.2); color: #ff5b6a; }
.dfd-status--paid   { background: rgba(34,201,151,0.2); color: #22c997; }
.dfd-status--disputed { background: rgba(246,179,74,0.2); color: #f6b34a; }
.dfd-plate {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  padding: 2px 6px;
  background: rgba(106,166,255,0.12);
  border-radius: 4px;
  color: #6aa6ff;
}

.dfd-zoom {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.88);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: zoom-out;
  padding: 24px;
}
.dfd-zoom__img {
  max-width: 92vw;
  max-height: 92vh;
  border-radius: 8px;
  box-shadow: 0 12px 64px rgba(0, 0, 0, 0.8);
}
</style>
