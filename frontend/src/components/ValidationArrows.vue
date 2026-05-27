<template>
  <Teleport to="body">
    <svg v-if="visible" class="va-overlay" :width="sz.w" :height="sz.h" :viewBox="`0 0 ${sz.w} ${sz.h}`" @click.self="dismiss">
      <defs>
        <marker id="va-head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#fb923c" />
        </marker>
      </defs>
      <path
        v-for="(d, i) in paths"
        :key="i"
        :d="d"
        stroke="#fb923c"
        stroke-width="2.5"
        stroke-dasharray="9 5"
        fill="none"
        marker-end="url(#va-head)"
        class="va-path"
      />
    </svg>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = defineProps<{
  active: boolean
  fromEl: HTMLElement | null
  toEls: HTMLElement[]
}>()
const emit = defineEmits<{ (e: 'dismiss'): void }>()

const tick = ref(0)
const sz = ref({ w: typeof window !== 'undefined' ? window.innerWidth : 0, h: typeof window !== 'undefined' ? window.innerHeight : 0 })

const visible = computed(() => props.active && !!props.fromEl && props.toEls.length > 0)

const paths = computed(() => {
  void tick.value
  if (!props.fromEl) return []
  const fr = props.fromEl.getBoundingClientRect()
  const fx = fr.left + fr.width / 2
  const fy = fr.top + fr.height / 2
  return props.toEls.map((el, idx) => {
    const r = el.getBoundingClientRect()
    // целимся в правый край поля (немного внутрь), чтобы стрелка читалась
    const tx = r.right - Math.min(20, r.width / 4)
    const ty = r.top + r.height / 2
    const dx = tx - fx
    const dy = ty - fy
    const dist = Math.hypot(dx, dy) || 1
    // нормаль к прямой (перпендикуляр) — длина 1
    const nx = -dy / dist
    const ny = dx / dist
    // S-образная кривая через cubic Bezier: оба control-point смещены перпендикулярно,
    // в противоположные стороны → красивый «слалом». Амплитуда зависит от расстояния.
    const amp = Math.min(Math.max(dist * 0.35, 80), 220)
    // чередуем направление изгиба по индексу — стрелки расходятся веером
    const sign = idx % 2 === 0 ? 1 : -1
    const c1x = fx + dx * 0.25 + nx * amp * sign
    const c1y = fy + dy * 0.25 + ny * amp * sign
    const c2x = fx + dx * 0.75 - nx * amp * sign * 0.6
    const c2y = fy + dy * 0.75 - ny * amp * sign * 0.6
    return `M ${fx} ${fy} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${tx} ${ty}`
  })
})

function rerender() {
  sz.value = { w: window.innerWidth, h: window.innerHeight }
  tick.value++
}
function dismiss() { emit('dismiss') }

onMounted(() => {
  window.addEventListener('scroll', rerender, true)
  window.addEventListener('resize', rerender)
})
onUnmounted(() => {
  window.removeEventListener('scroll', rerender, true)
  window.removeEventListener('resize', rerender)
})
</script>

<style scoped>
.va-overlay {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 9999;
  animation: va-fade 250ms ease-out;
}
.va-path {
  animation: va-dash 1.4s linear infinite;
}
@keyframes va-fade {
  from { opacity: 0; }
  to   { opacity: 1; }
}
@keyframes va-dash {
  to { stroke-dashoffset: -28; }
}
</style>
