<template>
  <div
    v-if="open"
    class="duck-backdrop"
    @keydown.esc="handleClose"
  >
    <div
      class="duck-window"
      role="dialog"
      aria-label="Утиная охота"
      tabindex="-1"
      ref="windowRef"
    >
      <div class="duck-titlebar">
        <span class="duck-title">{{ titleText }}</span>
        <button
          type="button"
          class="duck-close"
          aria-label="Закрыть игру"
          @click="handleClose"
        >
          ✕
        </button>
      </div>
      <div ref="canvasWrapperRef" class="duck-canvas-wrapper" />
    </div>
  </div>
</template>

<script setup lang="ts">
// Окно мини-игры «Утиная охота», которую можно открыть во время долгой
// загрузки (см. PlayWhileWaiting.vue — кнопка-триггер, и useLongWait.ts —
// единственный источник признака «долго грузится», ПРАВИЛО №6). Закрывается
// ТОЛЬКО крестиком или Esc — окончание загрузки его не закрывает, только
// меняет заголовок (иначе пользователь теряет игру ровно в момент, когда
// страница досчиталась).
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { isBusy } from '../../composables/useLongWait'
import { DuckShootGame } from './duckShootGame'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [boolean]; close: [] }>()

const canvasWrapperRef = ref<HTMLElement | null>(null)
const windowRef = ref<HTMLElement | null>(null)
let game: DuckShootGame | null = null

const titleText = computed(() =>
  isBusy.value ? 'Утиная охота — пока грузится' : 'Утиная охота — страница загрузилась'
)

function handleClose() {
  emit('update:open', false)
  emit('close')
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) {
    handleClose()
  }
}

function mountGame() {
  if (!canvasWrapperRef.value) return
  game = new DuckShootGame(canvasWrapperRef.value)
  game.onEscape(handleClose)
  game.start()
}

function unmountGame() {
  game?.destroy()
  game = null
}

watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      await nextTick()
      mountGame()
      windowRef.value?.focus()
    } else {
      unmountGame()
    }
  },
  { immediate: true }
)

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  unmountGame()
})
</script>

<style scoped>
.duck-backdrop {
  position: fixed;
  inset: 0;
  z-index: 2500;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
}

.duck-window {
  width: 80vw;
  height: 80vh;
  max-width: 1100px;
  max-height: 700px;
  min-width: 320px;
  min-height: 360px;
  background: #fff;
  border: 1px solid #111;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.duck-titlebar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  border-bottom: 1px solid #111;
  font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
  font-size: 13px;
  flex: 0 0 auto;
}

.duck-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.duck-close {
  background: #fff;
  border: 1px solid #111;
  font-family: inherit;
  font-size: 13px;
  line-height: 1;
  width: 24px;
  height: 24px;
  cursor: pointer;
  flex: 0 0 auto;
  margin-left: 8px;
}
.duck-close:hover {
  background: #111;
  color: #fff;
}

.duck-canvas-wrapper {
  flex: 1 1 auto;
  min-height: 0;
  position: relative;
}
</style>
