<template>
  <div
    v-if="open"
    class="duck-backdrop"
    @keydown.esc="handleClose"
  >
    <div
      class="duck-window"
      role="dialog"
      aria-label="Игра"
      tabindex="-1"
      ref="windowRef"
    >
      <div class="duck-titlebar">
        <div class="duck-tabs">
          <button
            v-for="g in GAME_REGISTRY"
            :key="g.id"
            type="button"
            class="duck-tab"
            :class="{ 'duck-tab--active': activeGame === g.id }"
            @click="selectGame(g.id)"
          >
            {{ g.title }}
          </button>
        </div>
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
// Окно мини-игр на время долгой загрузки (см. PlayWhileWaiting.vue — кнопка-
// триггер, и useLongWait.ts — единственный источник признака «долго
// грузится», ПРАВИЛО №6). Закрывается ТОЛЬКО крестиком или Esc — окончание
// загрузки его не закрывает, только меняет заголовок (иначе пользователь
// теряет игру ровно в момент, когда страница досчиталась).
//
// Игры переключаются вкладками в заголовке, список — единственный источник
// в gameRegistry.ts (Правило №6); переключение уничтожает текущую игру и
// создаёт другую в том же canvas-контейнере. Файл оставлен под старым именем
// DuckShootWindow.vue, чтобы не трогать единственный импорт в PlayWhileWaiting.vue.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { isBusy } from '../../composables/useLongWait'
import { GAME_REGISTRY, isGameId, type GameId, type GameInstance } from './gameRegistry'

const GAME_STORAGE_KEY = 'gala_last_game'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [boolean]; close: [] }>()

const canvasWrapperRef = ref<HTMLElement | null>(null)
const windowRef = ref<HTMLElement | null>(null)
let game: GameInstance | null = null

const activeGame = ref<GameId>(loadLastGame())

const titleText = computed(() => {
  const name = GAME_REGISTRY.find((g) => g.id === activeGame.value)?.title ?? ''
  return isBusy.value ? `${name} — пока грузится` : `${name} — страница загрузилась`
})

function loadLastGame(): GameId {
  try {
    const v = localStorage.getItem(GAME_STORAGE_KEY)
    return isGameId(v) ? v : 'duck'
  } catch {
    return 'duck'
  }
}

function saveLastGame(kind: GameId) {
  try {
    localStorage.setItem(GAME_STORAGE_KEY, kind)
  } catch {
    /* ignore */
  }
}

function handleClose() {
  emit('update:open', false)
  emit('close')
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) {
    handleClose()
  }
}

function createGame(kind: GameId, container: HTMLElement): GameInstance {
  const def = GAME_REGISTRY.find((g) => g.id === kind) ?? GAME_REGISTRY[0]!
  return def.create(container)
}

function mountGame() {
  if (!canvasWrapperRef.value) return
  game = createGame(activeGame.value, canvasWrapperRef.value)
  game.onEscape(handleClose)
  game.start()
}

function unmountGame() {
  game?.destroy()
  game = null
}

function selectGame(kind: GameId) {
  if (activeGame.value === kind) return
  activeGame.value = kind
  saveLastGame(kind)
  if (props.open) {
    unmountGame()
    // очищаем canvas прошлой игры, чтобы новая создала свой
    if (canvasWrapperRef.value) canvasWrapperRef.value.innerHTML = ''
    mountGame()
  }
}

watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      await nextTick()
      if (canvasWrapperRef.value) canvasWrapperRef.value.innerHTML = ''
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
  flex-wrap: wrap;
  row-gap: 4px;
  gap: 10px;
  padding: 6px 10px;
  border-bottom: 1px solid #111;
  font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
  font-size: 13px;
  flex: 0 0 auto;
}

/* Узкое окно (телефон): вкладок (4) + заголовка + ✕ не хватает места в одну
   строку — заголовок переносится на вторую строку (order+flex-basis:100%),
   вкладки остаются прокручиваемыми в первой строке, ✕ всегда виден справа
   в первой строке (Правило №8 п.7 — ничего не должно уезжать за экран). */
.duck-tabs {
  display: flex;
  gap: 4px;
  order: 1;
  flex: 1 1 auto;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: thin;
}

.duck-tab {
  background: #fff;
  border: 1px solid #111;
  color: #111;
  font-family: inherit;
  font-size: 12px;
  line-height: 1;
  padding: 4px 8px;
  cursor: pointer;
  flex: 0 0 auto;
  white-space: nowrap;
}

.duck-tab--active {
  font-weight: 700;
  text-decoration: underline;
}

.duck-tab:hover {
  background: #111;
  color: #fff;
}

.duck-title {
  order: 3;
  flex: 1 1 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: center;
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
  order: 2;
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
