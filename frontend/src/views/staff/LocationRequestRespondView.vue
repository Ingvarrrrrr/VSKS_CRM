<template>
  <v-container class="pa-4" style="max-width: 480px">
    <div v-if="loading" class="text-center pa-8">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <template v-else-if="loadError">
      <v-alert type="error" variant="tonal" class="mb-4">{{ loadError }}</v-alert>
    </template>

    <template v-else-if="req">
      <v-card variant="outlined" class="rounded-xl pa-5 text-center">
        <v-icon icon="mdi-map-marker-radius" size="48" color="primary" class="mb-3" />

        <template v-if="req.status === 'sent'">
          <div class="text-h6 font-weight-bold mb-2">Запрос местоположения</div>
          <p class="text-body-2 text-medium-emphasis mb-5">
            <b>{{ req.requested_by_name || 'Диспетчер' }}</b> просит ваше текущее
            местоположение — разово, это не постоянная передача координат.
          </p>

          <v-alert v-if="geoError" type="warning" variant="tonal" density="compact" class="mb-4 text-left">
            {{ geoError }}
          </v-alert>

          <v-btn
            color="primary" variant="flat" size="large" block class="mb-3"
            :loading="sending" prepend-icon="mdi-crosshairs-gps"
            @click="sendLocation"
          >
            Отправить моё местоположение
          </v-btn>
          <v-btn
            variant="text" color="default" size="small" block
            :loading="declining" @click="decline"
          >
            Отказаться
          </v-btn>
        </template>

        <template v-else-if="req.status === 'answered'">
          <v-icon icon="mdi-check-circle" size="40" color="success" class="mb-2" />
          <div class="text-h6 font-weight-bold mb-1">Спасибо!</div>
          <p class="text-body-2 text-medium-emphasis">Местоположение уже отправлено диспетчеру.</p>
        </template>

        <template v-else-if="req.status === 'declined'">
          <v-icon icon="mdi-close-circle" size="40" color="grey" class="mb-2" />
          <div class="text-h6 font-weight-bold mb-1">Отказ зафиксирован</div>
          <p class="text-body-2 text-medium-emphasis">Диспетчер увидит, что вы отказались ответить.</p>
        </template>

        <template v-else-if="req.status === 'expired'">
          <v-icon icon="mdi-timer-off-outline" size="40" color="grey" class="mb-2" />
          <div class="text-h6 font-weight-bold mb-1">Запрос истёк</div>
          <p class="text-body-2 text-medium-emphasis">Попросите диспетчера отправить запрос ещё раз.</p>
        </template>

        <template v-else>
          <div class="text-h6 font-weight-bold mb-1">Запрос уже не активен</div>
          <p class="text-body-2 text-medium-emphasis">Отменён диспетчером.</p>
        </template>
      </v-card>
    </template>
  </v-container>
</template>

<script setup lang="ts">
/**
 * Экран подтверждения отправки геопозиции — открывается по клику на push
 * (владелец, задание 2026-09: push первый канал запроса местоположения,
 * должен вести на именно этот экран, не на общую карту).
 *
 * Доступен и без права staff.location.view — это ответ НА СВОЙ запрос,
 * backend (GET/POST .../self, .../respond, .../decline в
 * app/routers/staff_location_requests.py) проверяет req.user_id ==
 * current_user.id, а не право диспетчера.
 */
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { apiFetch } from '@/api'

interface LocationRequestOut {
  id: number
  requested_by_id: number
  requested_by_name: string | null
  user_id: number
  status: 'sent' | 'answered' | 'declined' | 'expired' | 'cancelled'
  channels_sent: string | null
  created_at: string
  expires_at: string
  responded_at: string | null
}

const route = useRoute()
const requestId = Number(route.params.id)

const loading = ref(true)
const loadError = ref<string | null>(null)
const req = ref<LocationRequestOut | null>(null)
const sending = ref(false)
const declining = ref(false)
const geoError = ref<string | null>(null)

async function load() {
  loading.value = true
  loadError.value = null
  try {
    req.value = await apiFetch<LocationRequestOut>(`/staff-location/requests/${requestId}/self`)
  } catch (e: any) {
    loadError.value = e?.payload?.message || e?.message || 'Не удалось загрузить запрос — возможно, ссылка устарела.'
  } finally {
    loading.value = false
  }
}

function getPosition(): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    if (!('geolocation' in navigator)) {
      reject(new Error('Геолокация не поддерживается этим браузером'))
      return
    }
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: true,
      timeout: 20_000,
      maximumAge: 0,
    })
  })
}

function describeGeoError(err: any): string {
  if (err && typeof err.code === 'number') {
    if (err.code === err.PERMISSION_DENIED) {
      return 'Доступ к геолокации запрещён в браузере — разрешите его в настройках сайта и попробуйте снова.'
    }
    if (err.code === err.POSITION_UNAVAILABLE) {
      return 'Не удалось определить местоположение устройства — проверьте, включена ли геолокация на телефоне.'
    }
    return 'Истекло время ожидания ответа от GPS — попробуйте ещё раз.'
  }
  return err?.message || 'Не удалось определить местоположение.'
}

async function sendLocation() {
  if (!req.value) return
  geoError.value = null
  sending.value = true
  try {
    const pos = await getPosition()
    req.value = await apiFetch<LocationRequestOut>(`/staff-location/requests/${requestId}/respond`, {
      method: 'POST',
      body: {
        lat: pos.coords.latitude,
        lon: pos.coords.longitude,
        accuracy_m: pos.coords.accuracy ?? null,
      },
    })
  } catch (e: any) {
    geoError.value = e?.payload?.message || describeGeoError(e)
  } finally {
    sending.value = false
  }
}

async function decline() {
  if (!req.value) return
  declining.value = true
  try {
    req.value = await apiFetch<LocationRequestOut>(`/staff-location/requests/${requestId}/decline`, { method: 'POST' })
  } catch (e: any) {
    geoError.value = e?.payload?.message || e?.message || 'Не удалось зафиксировать отказ — попробуйте ещё раз.'
  } finally {
    declining.value = false
  }
}

onMounted(load)
</script>
