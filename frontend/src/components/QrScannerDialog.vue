<template>
  <v-dialog v-model="show" max-width="560" persistent>
    <v-card>
      <v-card-title class="d-flex align-center">
        <v-icon start>mdi-qrcode-scan</v-icon>
        Сканирование QR чека
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="close" />
      </v-card-title>
      <v-card-text>
        <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mb-3 text-caption">
          {{ error }}
        </v-alert>

        <div v-show="hasCamera && !error" class="qr-frame">
          <video ref="video" autoplay playsinline muted />

          <!-- Затемнение вокруг прицела -->
          <div class="qr-dimmer" />

          <!-- Центральное окно прицела -->
          <div class="qr-window">
            <!-- Угловые маркеры -->
            <span class="qr-corner qr-corner--tl" />
            <span class="qr-corner qr-corner--tr" />
            <span class="qr-corner qr-corner--bl" />
            <span class="qr-corner qr-corner--br" />

            <!-- Анимированная линия сканирования -->
            <div class="qr-scan-line" :class="{ paused: busy || !!lastQr }" />

            <!-- Оверлей успеха -->
            <div v-if="detectedOk" class="qr-success-overlay">
              <v-icon color="success" size="64">mdi-check-circle</v-icon>
            </div>
          </div>

          <!-- Подпись под прицелом -->
          <div class="qr-hint" v-if="!detectedOk">Наведите камеру на QR-код чека</div>
          <div class="qr-hint qr-hint--ok" v-else>QR распознан ✓</div>
        </div>

        <!-- Phase 30.6: предупреждение если getUserMedia недоступен (http без https на Android) -->
        <v-alert v-if="!hasCamera && !error" type="info" variant="tonal" density="compact" class="mb-3 text-caption">
          Realtime-камера недоступна (требуется HTTPS). Используйте «Снять камерой» — откроет приложение камеры, или «Загрузить» из галереи.
        </v-alert>

        <div class="d-flex flex-wrap ga-2 mt-3">
          <!-- Phase 30.6: capture=environment — на Android открывает приложение камеры
               напрямую (съёмка), а не галерею. Работает без https. -->
          <v-btn variant="flat" color="primary" prepend-icon="mdi-camera"
            @click="$refs.cameraInput.click()">
            Снять камерой
          </v-btn>
          <input ref="cameraInput" type="file" accept="image/*" capture="environment" style="display:none"
            @change="onFilePick" />

          <v-btn variant="tonal" color="primary" prepend-icon="mdi-image-multiple"
            @click="$refs.fileInput.click()">
            Загрузить из галереи
          </v-btn>
          <input ref="fileInput" type="file" accept="image/*" style="display:none"
            @change="onFilePick" />
        </div>

        <v-progress-linear v-if="busy" indeterminate color="primary" class="mt-3" />
        <div v-if="lastQr && !detectedOk" class="text-caption text-medium-emphasis mt-2">
          Распознано: {{ lastQr }}
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="tonal" color="error" @click="close">Отмена</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import jsQR from 'jsqr'
import { decodeQrFromImageFile } from '@/utils/qrDecode'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'detected', qr: string): void
}>()

const show = ref(props.modelValue)
watch(() => props.modelValue, v => { show.value = v; if (v) start(); else stop() })
watch(show, v => emit('update:modelValue', v))

const video = ref<HTMLVideoElement | null>(null)
const error = ref('')
const hasCamera = ref(true)
const busy = ref(false)
const lastQr = ref('')
const detectedOk = ref(false)

let stream: MediaStream | null = null
let raf = 0
let canvas: HTMLCanvasElement | null = null

async function start() {
  error.value = ''
  lastQr.value = ''
  detectedOk.value = false
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    hasCamera.value = false
    return
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } },
      audio: false,
    })
    if (!video.value) return
    video.value.srcObject = stream
    await video.value.play().catch(() => {})
    canvas = document.createElement('canvas')
    tick()
  } catch (e: any) {
    hasCamera.value = false
    error.value = e?.message || 'Не удалось включить камеру'
  }
}

function tick() {
  if (!video.value || !canvas || !show.value) return
  const v = video.value
  if (v.readyState === v.HAVE_ENOUGH_DATA) {
    canvas.width = v.videoWidth
    canvas.height = v.videoHeight
    const ctx = canvas.getContext('2d', { willReadFrequently: true })!
    ctx.drawImage(v, 0, 0, canvas.width, canvas.height)
    const img = ctx.getImageData(0, 0, canvas.width, canvas.height)
    const code = jsQR(img.data, img.width, img.height, { inversionAttempts: 'dontInvert' })
    if (code && code.data) {
      detectedOk.value = true
      lastQr.value = code.data
      emit('detected', code.data)
      stop()
      return
    }
  }
  raf = requestAnimationFrame(tick)
}

function stop() {
  if (raf) cancelAnimationFrame(raf)
  raf = 0
  if (stream) {
    stream.getTracks().forEach(t => t.stop())
    stream = null
  }
}

function close() {
  stop()
  show.value = false
}

async function onFilePick(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  input.value = ''
  if (!f) return
  busy.value = true
  error.value = ''
  try {
    const result = await decodeQrFromImageFile(f)
    if (result) {
      detectedOk.value = true
      lastQr.value = result
      emit('detected', result)
      stop()
      show.value = false
    } else {
      error.value = 'QR не распознан. Сфотографируйте чек ровно, без бликов, чтобы QR занимал большую часть кадра.'
    }
  } catch (e: any) {
    error.value = e?.message || 'Не удалось обработать файл'
  } finally {
    busy.value = false
  }
}

onBeforeUnmount(stop)
defineExpose({ start, stop })
</script>

<style scoped>
/* ── Контейнер видео ───────────────────────────────────────────── */
.qr-frame {
  position: relative;
  width: 100%;
  aspect-ratio: 1 / 1;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.qr-frame video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* ── Затемнение вокруг прицела ─────────────────────────────────── */
/* Используем псевдоэлемент, чтобы не перекрывать клики по кнопкам */
.qr-dimmer {
  position: absolute;
  inset: 0;
  /* Дырка в центре: box-shadow на центральном окне создаёт затемнение,
     но dimmer здесь — только фоновый слой без pointer-events */
  pointer-events: none;
}

/* ── Центральное прицельное окно (65% меньшей стороны) ────────── */
.qr-window {
  position: absolute;
  /* 65% от контейнера; aspect-ratio 1:1 задаётся через width/height */
  width: 65%;
  aspect-ratio: 1 / 1;
  /* Затемнение вокруг через box-shadow: заполняем 9999px вокруг */
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.55);
  border-radius: 4px;
  pointer-events: none;
  overflow: hidden;
}

/* ── Угловые L-образные маркеры ────────────────────────────────── */
.qr-corner {
  position: absolute;
  width: 24px;
  height: 24px;
  border-color: #fb923c;
  border-style: solid;
}

.qr-corner--tl {
  top: 0; left: 0;
  border-width: 3px 0 0 3px;
  border-top-left-radius: 3px;
}
.qr-corner--tr {
  top: 0; right: 0;
  border-width: 3px 3px 0 0;
  border-top-right-radius: 3px;
}
.qr-corner--bl {
  bottom: 0; left: 0;
  border-width: 0 0 3px 3px;
  border-bottom-left-radius: 3px;
}
.qr-corner--br {
  bottom: 0; right: 0;
  border-width: 0 3px 3px 0;
  border-bottom-right-radius: 3px;
}

/* ── Анимированная линия сканирования ──────────────────────────── */
.qr-scan-line {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 2px;
  background: #fb923c;
  box-shadow: 0 0 6px 2px rgba(251, 146, 60, 0.7);
  animation: scan-move 2s ease-in-out infinite;
}

.qr-scan-line.paused {
  animation-play-state: paused;
}

@keyframes scan-move {
  0%   { top: 0; }
  50%  { top: calc(100% - 2px); }
  100% { top: 0; }
}

/* ── Оверлей успеха (зелёная галочка) ─────────────────────────── */
.qr-success-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fade-in 0.2s ease;
}

@keyframes fade-in {
  from { opacity: 0; transform: scale(0.7); }
  to   { opacity: 1; transform: scale(1); }
}

/* ── Подпись под прицелом ──────────────────────────────────────── */
.qr-hint {
  position: absolute;
  bottom: 12%;
  left: 50%;
  transform: translateX(-50%);
  color: #fff;
  font-size: 0.78rem;
  white-space: nowrap;
  text-shadow: 0 1px 4px rgba(0,0,0,0.9);
  pointer-events: none;
}

.qr-hint--ok {
  color: #4ade80;
  font-weight: 600;
}
</style>
