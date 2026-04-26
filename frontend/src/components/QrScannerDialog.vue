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
          <div class="qr-overlay" />
        </div>

        <div class="d-flex flex-wrap ga-2 mt-3">
          <v-btn variant="tonal" color="primary" prepend-icon="mdi-image-multiple"
            @click="$refs.fileInput.click()">
            Загрузить QR
          </v-btn>
          <input ref="fileInput" type="file" accept="image/*" style="display:none"
            @change="onFilePick" />
        </div>

        <v-progress-linear v-if="busy" indeterminate color="primary" class="mt-3" />
        <div v-if="lastQr" class="text-caption text-medium-emphasis mt-2">
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

let stream: MediaStream | null = null
let raf = 0
let canvas: HTMLCanvasElement | null = null

async function start() {
  error.value = ''
  lastQr.value = ''
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

async function loadBitmap(file: File): Promise<{ bitmap: ImageBitmap | HTMLImageElement, width: number, height: number }> {
  // Prefer createImageBitmap with imageOrientation:'from-image' to respect EXIF
  // (iPhone snaps come rotated). Fallback: HTMLImageElement.
  if ('createImageBitmap' in window) {
    try {
      const bm = await createImageBitmap(file, { imageOrientation: 'from-image' as any })
      return { bitmap: bm, width: bm.width, height: bm.height }
    } catch { /* fallback below */ }
  }
  const url = URL.createObjectURL(file)
  try {
    const img = new Image()
    img.src = url
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej })
    return { bitmap: img, width: img.naturalWidth || img.width, height: img.naturalHeight || img.height }
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }
}

function decodeFromBitmap(bm: ImageBitmap | HTMLImageElement, w: number, h: number, rotate: 0 | 90 | 180 | 270 = 0): string | null {
  const MAX = 1600
  const scale = Math.min(1, MAX / Math.max(w, h))
  const dw = Math.max(1, Math.round(w * scale))
  const dh = Math.max(1, Math.round(h * scale))
  const c = document.createElement('canvas')
  if (rotate === 90 || rotate === 270) { c.width = dh; c.height = dw } else { c.width = dw; c.height = dh }
  const ctx = c.getContext('2d', { willReadFrequently: true })!
  ctx.translate(c.width / 2, c.height / 2)
  ctx.rotate((rotate * Math.PI) / 180)
  ctx.drawImage(bm as any, -dw / 2, -dh / 2, dw, dh)
  const data = ctx.getImageData(0, 0, c.width, c.height)
  const code = jsQR(data.data, data.width, data.height, { inversionAttempts: 'attemptBoth' })
  return code?.data || null
}

async function onFilePick(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  input.value = ''
  if (!f) return
  busy.value = true
  error.value = ''
  try {
    const { bitmap, width, height } = await loadBitmap(f)
    let result: string | null = null
    for (const r of [0, 90, 180, 270] as const) {
      result = decodeFromBitmap(bitmap, width, height, r)
      if (result) break
    }
    if (result) {
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
.qr-frame {
  position: relative;
  width: 100%;
  aspect-ratio: 1 / 1;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
}
.qr-frame video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.qr-overlay {
  position: absolute; inset: 0;
  border: 3px solid rgba(255,255,255,.6);
  border-radius: 8px;
  pointer-events: none;
}
</style>
