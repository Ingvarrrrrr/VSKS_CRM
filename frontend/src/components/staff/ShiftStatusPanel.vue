<template>
  <div class="ssp">
    <!-- Статус-строка -->
    <div class="ssp__status d-flex align-center ga-2 mb-3">
      <span class="ssp__dot ssp__dot--lg" :class="dotClass"></span>
      <div>
        <div class="text-subtitle-2 font-weight-bold">
          {{ shiftActive ? 'На смене — передача идёт' : 'Смена не начата' }}
        </div>
        <div class="text-caption text-medium-emphasis">
          {{ shiftActive ? `Последняя отправка: ${lastSentLabel}` : 'Местоположение не передаётся' }}
        </div>
      </div>
    </div>

    <div v-if="!geoSupported" class="ssp__alert ssp__alert--error mb-3">
      Этот браузер не поддерживает геолокацию — передача невозможна.
    </div>

    <div v-if="geoError" class="ssp__alert ssp__alert--error mb-3">{{ geoError }}</div>

    <div v-if="shiftActive && !isOnline" class="ssp__alert ssp__alert--warn mb-3">
      Нет сети — координаты копятся на устройстве{{ pendingCount ? ` (${pendingCount})` : '' }} и отправятся, когда связь появится.
    </div>

    <div v-if="shiftActive && isOnline && pendingCount > 0" class="ssp__alert ssp__alert--info mb-3">
      Досылаем накопленные точки: {{ pendingCount }} в очереди.
    </div>

    <div v-if="shiftActive && !isPageVisible" class="ssp__alert ssp__alert--warn mb-3">
      Приложение свёрнуто — передача приостановлена. Откройте вкладку/приложение, чтобы отправить актуальные координаты.
    </div>

    <div v-if="lastAttemptError" class="ssp__alert ssp__alert--warn mb-3">{{ lastAttemptError }}</div>

    <v-btn
      block
      :size="big ? 'large' : 'default'"
      :color="shiftActive ? 'error' : 'primary'"
      :variant="shiftActive ? 'tonal' : 'flat'"
      rounded="lg"
      :loading="toggling"
      :disabled="!geoSupported"
      @click="$emit('toggle')"
    >
      {{ shiftActive ? 'Смену закончил' : 'Я на смене' }}
    </v-btn>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatRelativeTime } from '@/utils/relativeTime'

const props = defineProps<{
  shiftActive: boolean
  toggling: boolean
  geoSupported: boolean
  geoPermission: string
  geoError: string | null
  lastSentAt: Date | null
  lastAttemptError: string | null
  pendingCount: number
  isOnline: boolean
  isPageVisible: boolean
  big?: boolean
}>()

defineEmits<{ (e: 'toggle'): void }>()

const lastSentLabel = computed(() => formatRelativeTime(props.lastSentAt))

const dotClass = computed(() => {
  if (!props.shiftActive) return 'ssp__dot--off'
  if (props.geoPermission === 'denied') return 'ssp__dot--error'
  if (!props.isOnline) return 'ssp__dot--offline'
  return 'ssp__dot--on'
})
</script>

<style scoped>
.ssp__dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}
.ssp__dot--lg {
  width: 12px;
  height: 12px;
}
.ssp__dot--off { background: #8a93a8; }
.ssp__dot--on {
  background: #22c997;
  animation: ssp-pulse 1.6s infinite;
}
.ssp__dot--offline { background: #f6b34a; }
.ssp__dot--error { background: #ff5b6a; }

@keyframes ssp-pulse {
  0%   { box-shadow: 0 0 0 0 rgba(34, 201, 151, 0.55); }
  70%  { box-shadow: 0 0 0 7px rgba(34, 201, 151, 0); }
  100% { box-shadow: 0 0 0 0 rgba(34, 201, 151, 0); }
}

.ssp__alert {
  font-size: 12.5px;
  padding: 8px 10px;
  border-radius: 8px;
  line-height: 1.4;
}
.ssp__alert--error {
  background: rgba(255, 91, 106, 0.1);
  color: #ff5b6a;
  border: 1px solid rgba(255, 91, 106, 0.25);
}
.ssp__alert--warn {
  background: rgba(246, 179, 74, 0.1);
  color: #b8791f;
  border: 1px solid rgba(246, 179, 74, 0.3);
}
.ssp__alert--info {
  background: rgba(106, 166, 255, 0.1);
  color: #3d6fbf;
  border: 1px solid rgba(106, 166, 255, 0.25);
}
</style>
