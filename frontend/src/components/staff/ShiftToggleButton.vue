<template>
  <!-- Компактный режим (шапка приложения): маленький чип с индикатором,
       клик открывает тот же виджет во всплывающем меню. -->
  <v-menu v-if="compact" v-model="menuOpen" :close-on-content-click="false" location="bottom end">
    <template v-slot:activator="{ props: menuProps }">
      <v-btn v-bind="menuProps" variant="text" size="small" class="stb-chip" :title="shiftActive ? 'На смене — координаты передаются' : 'Смена не начата'">
        <span class="stb-dot" :class="dotClass"></span>
        <span class="stb-chip__label d-none d-sm-inline">{{ shiftActive ? 'На смене' : 'Не на смене' }}</span>
      </v-btn>
    </template>
    <v-card min-width="300" max-width="360" class="pa-1">
      <v-card-text class="pa-3">
        <ShiftStatusPanel
          :shift-active="shiftActive"
          :toggling="togglingShift"
          :geo-supported="geoSupported"
          :geo-permission="geoPermission"
          :geo-error="geoErrorMessage"
          :last-sent-at="lastSentAt"
          :last-attempt-error="lastAttemptError"
          :pending-count="pendingPointsCount"
          :is-online="isOnline"
          :is-page-visible="isPageVisible"
          @toggle="onToggleClick"
        />
      </v-card-text>
    </v-card>
  </v-menu>

  <!-- Полный режим (мобильный кабинет / «Моё местоположение»): виджет прямо на странице. -->
  <v-card v-else variant="outlined" class="rounded-xl pa-4 stb-full">
    <ShiftStatusPanel
      :shift-active="shiftActive"
      :toggling="togglingShift"
      :geo-supported="geoSupported"
      :geo-permission="geoPermission"
      :geo-error="geoErrorMessage"
      :last-sent-at="lastSentAt"
      :last-attempt-error="lastAttemptError"
      :pending-count="pendingPointsCount"
      :is-online="isOnline"
      :is-page-visible="isPageVisible"
      big
      @toggle="onToggleClick"
    />
  </v-card>

  <!-- Объяснение перед первым запросом разрешения браузера — задание прямо
       требует «внятное объяснение по-русски, зачем это нужно» ДО системного
       промпта, а не полагаться на голый браузерный диалог. -->
  <v-dialog v-model="explainDialog" max-width="420" persistent>
    <v-card class="rounded-xl">
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon icon="mdi-map-marker-radius" color="primary" class="mr-2" />
        Передача местоположения
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <p class="mb-2">
          Пока идёт смена, приложение будет каждые 1–2 минуты определять ваше
          местоположение и передавать его диспетчеру.
        </p>
        <p class="mb-2 text-medium-emphasis">
          Это нужно, чтобы в аварийной ситуации было понятно, кто где находится.
          Точность — до нескольких сотен метров, координаты видны только
          диспетчеру и руководителю вашей организации.
        </p>
        <p class="text-medium-emphasis">
          Сейчас браузер спросит разрешение на геолокацию — нажмите «Разрешить»
          в его окне.
        </p>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0 gap-2">
        <v-btn variant="outlined" rounded="lg" @click="explainDialog = false">Отмена</v-btn>
        <v-btn color="primary" variant="flat" rounded="lg" @click="confirmStart">Начать смену</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useToast } from '@/composables/useToast'
import ShiftStatusPanel from './ShiftStatusPanel.vue'
import {
  shiftActive, togglingShift, geoSupported, geoPermission, geoErrorMessage,
  lastSentAt, lastAttemptError, pendingPointsCount, isOnline, isPageVisible,
  startShift, endShift,
} from '@/composables/useStaffLocationTracking'

withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })

const toast = useToast()
const menuOpen = ref(false)
const explainDialog = ref(false)

// Диалог-объяснение показываем только когда реально предстоит спросить браузер
// (разрешение ещё не 'granted') — повторные нажатия при уже выданном
// разрешении не должны каждый раз перекрываться лишним окном.
function onToggleClick() {
  if (shiftActive.value) {
    doEndShift()
    return
  }
  if (geoPermission.value === 'granted') {
    doStartShift()
  } else {
    explainDialog.value = true
  }
}

function confirmStart() {
  explainDialog.value = false
  doStartShift()
}

async function doStartShift() {
  try {
    await startShift()
    toast.success('Смена начата — передаём местоположение')
  } catch (e: any) {
    toast.error(`Не удалось начать смену: ${e?.payload?.message || e?.message || 'ошибка сети'}`)
  }
}

async function doEndShift() {
  try {
    await endShift()
    menuOpen.value = false
    toast.info('Смена закончена — передача остановлена')
  } catch (e: any) {
    toast.error(`Не удалось завершить смену: ${e?.payload?.message || e?.message || 'ошибка сети'}`)
  }
}

const dotClass = computed(() => {
  if (!shiftActive.value) return 'stb-dot--off'
  if (geoPermission.value === 'denied') return 'stb-dot--error'
  if (!isOnline.value) return 'stb-dot--offline'
  return 'stb-dot--on'
})
</script>

<style scoped>
.stb-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  text-transform: none;
}
.stb-chip__label {
  font-size: 12px;
  font-weight: 600;
}
.stb-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}
.stb-dot--off { background: #8a93a8; }
.stb-dot--on {
  background: #22c997;
  animation: stb-pulse 1.6s infinite;
}
.stb-dot--offline { background: #f6b34a; }
.stb-dot--error { background: #ff5b6a; }

@keyframes stb-pulse {
  0%   { box-shadow: 0 0 0 0 rgba(34, 201, 151, 0.55); }
  70%  { box-shadow: 0 0 0 7px rgba(34, 201, 151, 0); }
  100% { box-shadow: 0 0 0 0 rgba(34, 201, 151, 0); }
}

.stb-full {
  max-width: 480px;
}
</style>
