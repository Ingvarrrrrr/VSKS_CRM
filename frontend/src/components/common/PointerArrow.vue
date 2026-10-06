<template>
  <!-- Анимированная стрелка-указатель — тот же оранжевый кружок + mdi-arrow-
       down-bold + «вьющаяся» анимация, что .hv-pointer в
       HierarchyGraphCanvas.vue (frontend/src/components/hierarchy/
       HierarchyGraphCanvas.vue:270-297), только параметризована направлением
       и переиспользуется инлайн (не абсолютным позиционированием над узлом
       графа) — задание владельца 06.10.2026, «где превышение»
       (useExcessDrilldown.ts, FeoTreeRow.vue). Правило №6 — второй CSS с этой
       же анимацией не завели, цвет/тайминг списаны с оригинала. -->
  <span
    class="pointer-arrow"
    :class="{ 'pointer-arrow--current': current }"
    :title="title"
  >
    <span class="pointer-arrow__circle" :style="{ transform: `rotate(${baseRotateDeg}deg)` }">
      <v-icon icon="mdi-arrow-down-bold" :size="current ? 20 : 15" />
    </span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  direction?: 'down' | 'up' | 'left' | 'right'
  current?: boolean
  title?: string
}>(), {
  direction: 'down',
  current: false,
  title: '',
})

// Базовая икона — всегда mdi-arrow-down-bold (как в HierarchyGraphCanvas.vue),
// направление — поворотом, а не второй иконкой.
const baseRotateDeg = computed(() => ({ down: 0, up: 180, left: 90, right: -90 }[props.direction]))
</script>

<style scoped>
.pointer-arrow {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.35));
  /* «Вьющаяся» анимация — не rotate (тот уже занят направлением), а
     пульсация — тот же ритм 0.9s, что и hv-pointer-wiggle. */
  animation: pointer-arrow-pulse 0.9s ease-in-out infinite;
}
.pointer-arrow__circle {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(251, 146, 60, 0.22);
  color: #fb923c;
}
.pointer-arrow--current {
  animation-duration: 0.7s;
}
.pointer-arrow--current .pointer-arrow__circle {
  width: 28px;
  height: 28px;
  background: rgba(251, 146, 60, 0.35);
  color: #ea580c;
}
@keyframes pointer-arrow-pulse {
  0%, 100% { transform: scale(1) translateY(0); }
  50%      { transform: scale(1.12) translateY(-2px); }
}
</style>
