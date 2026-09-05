<template>
  <v-container class="pa-4" style="max-width: 640px">
    <div class="text-h5 font-weight-bold mb-1">Моё местоположение</div>
    <p class="text-body-2 text-medium-emphasis mb-4">
      Здесь видно то же, что видит диспетчер о вас: статус смены, последняя
      переданная точка и трек за выбранный период. Доступно без специального
      права — это ваши собственные данные.
    </p>

    <ShiftToggleButton class="mb-4" />

    <v-card variant="outlined" class="rounded-xl pa-4 mb-4">
      <div class="text-subtitle-2 font-weight-bold mb-2">Push-уведомления</div>
      <p class="text-caption text-medium-emphasis mb-3">
        Нужны, чтобы диспетчер мог мгновенно достучаться до вас (например,
        запросить местоположение) — уведомление придёт, даже если приложение
        закрыто.
      </p>
      <div v-if="pushStatus === 'subscribed'" class="d-flex align-center ga-1 text-body-2" style="color: #22c997">
        <v-icon icon="mdi-check-circle" size="16" /> Включены на этом устройстве
      </div>
      <div v-else-if="pushStatus === 'denied'" class="text-body-2 text-error">
        Уведомления заблокированы в настройках браузера — разрешите их для этого сайта, чтобы диспетчер мог до вас достучаться.
      </div>
      <div v-else-if="pushStatus === 'unsupported'" class="text-body-2 text-medium-emphasis">
        Этот браузер (или режим) не поддерживает push-уведомления на этом устройстве.
      </div>
      <v-btn v-else color="primary" variant="tonal" size="small" :loading="pushSubscribing" @click="enablePush">
        Включить уведомления
      </v-btn>
    </v-card>

    <v-card variant="outlined" class="rounded-xl pa-4 mb-4">
      <div class="text-subtitle-2 font-weight-bold mb-2">Последняя переданная точка</div>
      <div v-if="loadingLast" class="text-medium-emphasis text-body-2">Загрузка…</div>
      <div v-else-if="!lastPoint" class="text-medium-emphasis text-body-2">
        Точек ещё нет — начните смену, чтобы координаты начали появляться.
      </div>
      <div v-else class="d-flex flex-column ga-1">
        <div class="text-body-2">
          <b>Координаты:</b> {{ lastPoint.lat.toFixed(5) }}, {{ lastPoint.lon.toFixed(5) }}
          <span v-if="lastPoint.accuracy_m != null" class="text-medium-emphasis">(± {{ Math.round(lastPoint.accuracy_m) }} м)</span>
        </div>
        <div class="text-body-2">
          <b>Когда:</b> {{ formatRelativeTime(lastPoint.recorded_at) }}
          <span class="text-medium-emphasis"> · {{ fmtAbs(lastPoint.recorded_at) }}</span>
        </div>
      </div>
      <v-btn class="mt-3" variant="tonal" color="primary" size="small" @click="refreshLast">
        Обновить
      </v-btn>
    </v-card>

    <v-card variant="outlined" class="rounded-xl pa-4">
      <div class="text-subtitle-2 font-weight-bold mb-2">Мой трек</div>
      <p class="text-caption text-medium-emphasis mb-3">
        Посмотреть все переданные точки за выбранный период.
      </p>
      <v-btn color="primary" variant="flat" :disabled="!myUserId" @click="trackDialogOpen = true">
        Открыть трек
      </v-btn>
    </v-card>

    <StaffTrackDialog
      v-model="trackDialogOpen"
      :user-id="myUserId"
      :user-name="myUserName"
    />
  </v-container>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import { formatRelativeTime } from '@/utils/relativeTime'
import ShiftToggleButton from '@/components/staff/ShiftToggleButton.vue'
import StaffTrackDialog from '@/components/staff/StaffTrackDialog.vue'
import { subscribeToPush, getPushSubscriptionStatus } from '@/composables/useChat'

interface LastPoint {
  id: number
  lat: number
  lon: number
  accuracy_m: number | null
  recorded_at: string
  received_at: string
  source: string
}

const toast = useToast()
const loadingLast = ref(false)
const lastPoint = ref<LastPoint | null>(null)
const trackDialogOpen = ref(false)
const myUserId = ref<number | null>(null)
const myUserName = ref('Я')
const pushStatus = ref<'subscribed' | 'unsubscribed' | 'denied' | 'unsupported'>('unsubscribed')
const pushSubscribing = ref(false)

async function refreshPushStatus() {
  pushStatus.value = await getPushSubscriptionStatus()
}

async function enablePush() {
  pushSubscribing.value = true
  try {
    const result = await subscribeToPush()
    if (result === 'subscribed') {
      toast.success('Push-уведомления включены на этом устройстве')
    } else if (result === 'denied') {
      toast.error('Разрешение на уведомления не выдано — проверьте настройки браузера')
    } else if (result === 'unsupported') {
      toast.error('Этот браузер/режим не поддерживает push-уведомления')
    } else {
      toast.error('Не удалось включить уведомления — попробуйте ещё раз')
    }
  } finally {
    pushSubscribing.value = false
    await refreshPushStatus()
  }
}

async function refreshLast() {
  loadingLast.value = true
  try {
    lastPoint.value = await apiFetch<LastPoint | null>('/staff-location/mine/last')
  } catch (e: any) {
    toast.error(`Не удалось загрузить последнюю точку: ${e?.payload?.message || e?.message || 'ошибка сети'}`)
  } finally {
    loadingLast.value = false
  }
}

function fmtAbs(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

onMounted(async () => {
  try {
    const me = await apiFetch<{ id: number; full_name?: string; username?: string }>('/users/me')
    myUserId.value = me.id
    myUserName.value = me.full_name || me.username || 'Я'
  } catch {
    const stored = localStorage.getItem('user_id')
    if (stored) myUserId.value = parseInt(stored)
    myUserName.value = localStorage.getItem('user_name') || 'Я'
  }
  refreshLast()
  refreshPushStatus()
})
</script>
