<template>
  <v-dialog v-model="dialog" max-width="520" persistent>
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between pt-4 px-5">
        <span class="text-subtitle-1 font-weight-bold">
          <v-icon icon="mdi-draw" size="18" class="mr-2" />Моя подпись
        </span>
        <v-btn icon="mdi-close" variant="text" size="small" @click="close" />
      </v-card-title>

      <v-card-text class="px-5 pb-2">
        <!-- Current saved signature -->
        <div v-if="savedSignature && !editing" class="mb-4">
          <div class="text-caption text-medium-emphasis mb-2">Текущая подпись:</div>
          <div class="sig-preview">
            <img :src="savedSignature" alt="подпись" class="sig-img" />
          </div>
          <div class="d-flex ga-2 mt-3">
            <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-pencil"
              @click="startEditing">Изменить</v-btn>
            <v-btn color="error" variant="text" size="small" prepend-icon="mdi-delete"
              :loading="deleting" @click="deleteSignature">Удалить</v-btn>
          </div>
        </div>

        <!-- Canvas drawing area -->
        <div v-if="!savedSignature || editing">
          <div class="text-caption text-medium-emphasis mb-2">
            Нарисуйте подпись мышью или пальцем:
          </div>
          <div class="canvas-wrap">
            <canvas
              ref="canvasRef"
              :width="canvasW"
              :height="canvasH"
              class="sig-canvas"
              @mousedown="startDraw"
              @mousemove="draw"
              @mouseup="stopDraw"
              @mouseleave="stopDraw"
              @touchstart.prevent="startDrawTouch"
              @touchmove.prevent="drawTouch"
              @touchend.prevent="stopDraw"
            />
          </div>
          <div class="d-flex ga-2 mt-3">
            <v-btn variant="text" size="small" prepend-icon="mdi-eraser" @click="clearCanvas">
              Очистить
            </v-btn>
          </div>
        </div>
      </v-card-text>

      <v-card-actions class="px-5 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="close">Закрыть</v-btn>
        <v-btn v-if="!savedSignature || editing"
          color="primary" variant="flat" :loading="saving" :disabled="!hasDrawing"
          @click="saveSignature">
          Сохранить подпись
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, watch } from 'vue'
import { apiFetch } from '@/api'

const dialog = ref(false)
const canvasRef = ref<HTMLCanvasElement | null>(null)
const canvasW = 460
const canvasH = 150
const isDrawing = ref(false)
const hasDrawing = ref(false)
const savedSignature = ref<string | null>(null)
const editing = ref(false)
const saving = ref(false)
const deleting = ref(false)

const emit = defineEmits<{
  'saved': [hasSignature: boolean]
}>()

let ctx: CanvasRenderingContext2D | null = null

function initCanvas() {
  const canvas = canvasRef.value
  if (!canvas) return
  ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.strokeStyle = '#1a237e'
  ctx.lineWidth = 2
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  clearCanvas()
}

function clearCanvas() {
  if (!ctx || !canvasRef.value) return
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, canvasW, canvasH)
  hasDrawing.value = false
}

function getPos(e: MouseEvent) {
  const rect = canvasRef.value!.getBoundingClientRect()
  const scaleX = canvasW / rect.width
  const scaleY = canvasH / rect.height
  return { x: (e.clientX - rect.left) * scaleX, y: (e.clientY - rect.top) * scaleY }
}

function getTouchPos(e: TouchEvent) {
  const rect = canvasRef.value!.getBoundingClientRect()
  const scaleX = canvasW / rect.width
  const scaleY = canvasH / rect.height
  const t = e.touches[0]
  return { x: (t.clientX - rect.left) * scaleX, y: (t.clientY - rect.top) * scaleY }
}

function startDraw(e: MouseEvent) {
  if (!ctx) return
  isDrawing.value = true
  const { x, y } = getPos(e)
  ctx.beginPath()
  ctx.moveTo(x, y)
}

function draw(e: MouseEvent) {
  if (!isDrawing.value || !ctx) return
  const { x, y } = getPos(e)
  ctx.lineTo(x, y)
  ctx.stroke()
  hasDrawing.value = true
}

function startDrawTouch(e: TouchEvent) {
  if (!ctx) return
  isDrawing.value = true
  const { x, y } = getTouchPos(e)
  ctx.beginPath()
  ctx.moveTo(x, y)
}

function drawTouch(e: TouchEvent) {
  if (!isDrawing.value || !ctx) return
  const { x, y } = getTouchPos(e)
  ctx.lineTo(x, y)
  ctx.stroke()
  hasDrawing.value = true
}

function stopDraw() {
  isDrawing.value = false
}

async function loadSignature() {
  try {
    const data = await apiFetch<{ signature: string | null }>('/users/me/signature')
    savedSignature.value = data.signature || null
  } catch {
    savedSignature.value = null
  }
}

async function saveSignature() {
  if (!canvasRef.value || !hasDrawing.value) return
  saving.value = true
  try {
    const dataUrl = canvasRef.value.toDataURL('image/png')
    await apiFetch('/users/me/signature', { method: 'PUT', body: { signature: dataUrl } })
    savedSignature.value = dataUrl
    editing.value = false
    emit('saved', true)
  } catch (e: any) {
    console.error('Save signature error:', e)
  } finally {
    saving.value = false
  }
}

async function deleteSignature() {
  deleting.value = true
  try {
    await apiFetch('/users/me/signature', { method: 'DELETE' })
    savedSignature.value = null
    editing.value = false
    emit('saved', false)
    await nextTick()
    initCanvas()
  } catch { /* ignore */ } finally {
    deleting.value = false
  }
}

function startEditing() {
  editing.value = true
  nextTick(() => initCanvas())
}

function close() {
  dialog.value = false
  editing.value = false
}

function open() {
  dialog.value = true
  loadSignature()
  nextTick(() => {
    if (!savedSignature.value) initCanvas()
  })
}

watch(dialog, (val) => {
  if (val && (!savedSignature.value)) {
    nextTick(() => initCanvas())
  }
})

defineExpose({ open })
</script>

<style scoped>
.canvas-wrap {
  border: 1.5px solid rgba(0,0,0,0.15);
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
  cursor: crosshair;
  width: 100%;
}
.sig-canvas {
  display: block;
  width: 100%;
  touch-action: none;
}
.sig-preview {
  border: 1px solid rgba(0,0,0,0.1);
  border-radius: 8px;
  padding: 8px;
  background: #fafafa;
  display: inline-block;
  width: 100%;
}
.sig-img {
  max-height: 100px;
  max-width: 100%;
  display: block;
  margin: 0 auto;
}
</style>
