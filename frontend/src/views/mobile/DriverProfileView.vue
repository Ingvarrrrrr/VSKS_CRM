<template>
  <v-container class="pa-4">
    <div class="text-h6 font-weight-bold mb-1">Профиль</div>
    <div class="text-body-2 text-medium-emphasis mb-4">{{ userName }}</div>

    <!-- Отслеживание местоположения (владелец, 2026-09): у мобильных водителей
         нет десктопной шапки (см. MobileLayout.vue) — «Моё местоположение»
         живёт здесь же, в профиле, а не отдельным экраном, которого не видно
         в bottom-tab-bar. -->
    <div class="text-caption font-weight-bold text-uppercase mb-2" style="letter-spacing:0.4px; opacity:0.5">
      Моё местоположение
    </div>
    <ShiftToggleButton class="mb-4" />

    <v-card variant="outlined" class="rounded-xl pa-3 mb-4">
      <div class="text-body-2 font-weight-semibold mb-1">Последняя переданная точка</div>
      <div v-if="loadingLast" class="text-caption text-medium-emphasis">Загрузка…</div>
      <div v-else-if="!lastPoint" class="text-caption text-medium-emphasis">
        Точек ещё нет — начните смену выше.
      </div>
      <div v-else class="text-caption">
        {{ formatRelativeTime(lastPoint.recorded_at) }}
        <span class="text-medium-emphasis">
          · {{ lastPoint.lat.toFixed(4) }}, {{ lastPoint.lon.toFixed(4) }}
        </span>
      </div>
      <v-btn class="mt-2" size="small" variant="tonal" color="primary" :disabled="!myUserId" @click="trackDialogOpen = true">
        Мой трек
      </v-btn>
    </v-card>

    <v-divider class="mb-4" />

    <v-btn block variant="outlined" color="error" prepend-icon="mdi-logout" @click="logout">
      Выйти
    </v-btn>

    <StaffTrackDialog v-model="trackDialogOpen" :user-id="myUserId" :user-name="userName" />
  </v-container>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { formatRelativeTime } from '@/utils/relativeTime'
import ShiftToggleButton from '@/components/staff/ShiftToggleButton.vue'
import StaffTrackDialog from '@/components/staff/StaffTrackDialog.vue'
import { destroyStaffLocationTracking } from '@/composables/useStaffLocationTracking'

interface LastPoint {
  id: number
  lat: number
  lon: number
  accuracy_m: number | null
  recorded_at: string
  received_at: string
  source: string
}

const router = useRouter()
const userName = ref(localStorage.getItem('user_name') || 'Водитель')
const myUserId = ref<number | null>(null)
const loadingLast = ref(false)
const lastPoint = ref<LastPoint | null>(null)
const trackDialogOpen = ref(false)

async function loadLast() {
  loadingLast.value = true
  try {
    lastPoint.value = await apiFetch<LastPoint | null>('/staff-location/mine/last')
  } catch {
    lastPoint.value = null
  } finally {
    loadingLast.value = false
  }
}

function logout() {
  destroyStaffLocationTracking()
  localStorage.removeItem('auth_token')
  localStorage.removeItem('user_role')
  localStorage.removeItem('user_name')
  localStorage.removeItem('user_org_id')
  localStorage.removeItem('user_org_name')
  localStorage.removeItem('user_fleet_role')
  localStorage.removeItem('fleet_role')
  router.push('/login')
}

onMounted(async () => {
  try {
    const me = await apiFetch<{ id: number; full_name?: string; username?: string }>('/users/me')
    myUserId.value = me.id
    userName.value = me.full_name || me.username || userName.value
  } catch {
    const stored = localStorage.getItem('user_id')
    if (stored) myUserId.value = parseInt(stored)
  }
  loadLast()
})
</script>
