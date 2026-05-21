<template>
  <div class="sig-pad" :class="{ 'sig-pad--readonly': readonly }">
    <!-- Readonly: display image -->
    <template v-if="readonly && modelValue">
      <img class="sig-pad__img" :src="modelValue" :width="width" :height="height" alt="Подпись" />
    </template>

    <!-- Empty readonly -->
    <template v-else-if="readonly && !modelValue">
      <div class="sig-pad__empty" :style="{ width: width + 'px', height: height + 'px' }">
        Подпись отсутствует
      </div>
    </template>

    <!-- Editable canvas -->
    <template v-else>
      <div class="sig-pad__wrapper" :style="{ width: width + 'px' }">
        <canvas
          ref="canvasEl"
          class="sig-pad__canvas"
          :width="width"
          :height="height"
          @mousedown="startDraw"
          @mousemove="draw"
          @mouseup="stopDraw"
          @mouseleave="stopDraw"
          @touchstart.prevent="touchStart"
          @touchmove.prevent="touchMove"
          @touchend.prevent="stopDraw"
        />
        <div class="sig-pad__hint" v-if="!hasSigned">Подпишите здесь</div>
        <div class="sig-pad__actions">
          <button type="button" class="sig-pad__clear" @click="clear">Очистить</button>
        </div>
      </div>
      <div v-if="!isValid && hasTouched" class="sig-pad__error">Подпись обязательна</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'

const props = withDefaults(defineProps<{
  modelValue?: string
  width?: number
  height?: number
  readonly?: boolean
}>(), {
  width: 400,
  height: 150,
  readonly: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', v: string | null): void
}>()

const canvasEl = ref<HTMLCanvasElement | null>(null)
const isDrawing = ref(false)
const hasSigned = ref(false)
const hasTouched = ref(false)
const isValid = ref(false)

let ctx: CanvasRenderingContext2D | null = null

onMounted(() => {
  if (!canvasEl.value) return
  ctx = canvasEl.value.getContext('2d')!
  ctx.strokeStyle = '#e9edf5'
  ctx.lineWidth = 2
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'

  // Restore existing value
  if (props.modelValue) {
    const img = new Image()
    img.onload = () => ctx!.drawImage(img, 0, 0)
    img.src = props.modelValue
    hasSigned.value = true
    isValid.value = true
  }
})

watch(() => props.modelValue, (v) => {
  if (!v && ctx) {
    ctx.clearRect(0, 0, props.width, props.height)
    hasSigned.value = false
    isValid.value = false
  }
})

function getPos(e: MouseEvent): { x: number; y: number } {
  const rect = canvasEl.value!.getBoundingClientRect()
  return { x: e.clientX - rect.left, y: e.clientY - rect.top }
}

function getTouchPos(e: TouchEvent): { x: number; y: number } {
  const rect = canvasEl.value!.getBoundingClientRect()
  const t = e.touches[0]
  return { x: t.clientX - rect.left, y: t.clientY - rect.top }
}

function startDraw(e: MouseEvent) {
  if (!ctx) return
  isDrawing.value = true
  hasTouched.value = true
  const { x, y } = getPos(e)
  ctx.beginPath()
  ctx.moveTo(x, y)
}

function draw(e: MouseEvent) {
  if (!isDrawing.value || !ctx) return
  const { x, y } = getPos(e)
  ctx.lineTo(x, y)
  ctx.stroke()
}

function touchStart(e: TouchEvent) {
  if (!ctx) return
  isDrawing.value = true
  hasTouched.value = true
  const { x, y } = getTouchPos(e)
  ctx.beginPath()
  ctx.moveTo(x, y)
}

function touchMove(e: TouchEvent) {
  if (!isDrawing.value || !ctx) return
  const { x, y } = getTouchPos(e)
  ctx.lineTo(x, y)
  ctx.stroke()
}

function stopDraw() {
  if (!isDrawing.value) return
  isDrawing.value = false
  hasSigned.value = true
  isValid.value = true
  const dataUrl = canvasEl.value!.toDataURL('image/png')
  emit('update:modelValue', dataUrl)
}

function clear() {
  if (!ctx) return
  ctx.clearRect(0, 0, props.width, props.height)
  hasSigned.value = false
  isValid.value = false
  hasTouched.value = true
  emit('update:modelValue', null)
}
</script>

<style scoped>
.sig-pad {
  display: inline-block;
}

.sig-pad__wrapper {
  position: relative;
  border: 1px solid var(--line-2, #2b3245);
  border-radius: 10px;
  overflow: hidden;
  background: rgba(17, 21, 33, 0.8);
}

.sig-pad__canvas {
  display: block;
  cursor: crosshair;
}

.sig-pad__hint {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: var(--muted, #8a93a8);
  font-size: 12px;
  font-weight: 600;
  pointer-events: none;
  user-select: none;
}

.sig-pad__actions {
  display: flex;
  justify-content: flex-end;
  padding: 4px 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.sig-pad__clear {
  background: transparent;
  border: none;
  color: var(--muted, #8a93a8);
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 6px;
  font-family: inherit;
  transition: color 0.15s;
}
.sig-pad__clear:hover {
  color: var(--alert, #ff5b6a);
}

.sig-pad__img {
  display: block;
  border: 1px solid var(--line, #222838);
  border-radius: 10px;
  background: rgba(17, 21, 33, 0.6);
}

.sig-pad__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed var(--line, #222838);
  border-radius: 10px;
  color: var(--muted, #8a93a8);
  font-size: 12px;
  font-style: italic;
}

.sig-pad__error {
  margin-top: 4px;
  font-size: 11.5px;
  color: var(--alert, #ff5b6a);
  font-weight: 600;
}
</style>
