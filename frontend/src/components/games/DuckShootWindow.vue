<template>
  <div
    v-if="open"
    class="duck-backdrop"
    @pointerdown.stop
    @mousedown.stop
    @click.stop
    @focusin.stop
    @keydown.esc.stop="handleClose"
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
          class="duck-score-toggle"
          :class="{ 'duck-score-toggle--active': showLeaderboard }"
          aria-label="Показать/скрыть рекорды"
          @click="showLeaderboard = !showLeaderboard"
        >
          🏆 Рекорды
        </button>
        <button
          type="button"
          class="duck-close"
          aria-label="Закрыть игру"
          @click="handleClose"
        >
          ✕
        </button>
      </div>
      <div class="duck-body">
        <div class="duck-canvas-wrapper">
          <div ref="canvasWrapperRef" class="duck-canvas-container" />

          <!-- Модальное окно по окончании игры (Game Over) -->
          <div v-if="gameOverCard" class="duck-gameover-overlay">
            <div class="duck-gameover-card">
              <div class="duck-gameover-badge">ИГРА ОКОНЧЕНА</div>

              <div class="duck-gameover-score-row">
                <div class="duck-gameover-score-box">
                  <span class="duck-gameover-score-label">Счёт</span>
                  <span class="duck-gameover-score-val">{{ gameOverCard.score }}</span>
                </div>
                <div class="duck-gameover-score-box">
                  <span class="duck-gameover-score-label">Рекорд</span>
                  <span class="duck-gameover-score-val">{{ Math.max(currentBest, gameOverCard.score) }}</span>
                </div>
              </div>

              <div v-if="gameOverCard.isNewRecord" class="duck-gameover-newrecord">
                🎉 Новый личный рекорд!
              </div>

              <div class="duck-gameover-nick-box">
                <label class="duck-gameover-nick-label">Ваш ник для таблицы рекордов:</label>
                <div class="duck-gameover-nick-row">
                  <input
                    v-model="playerNickname"
                    type="text"
                    maxlength="24"
                    placeholder="Введите ник (2-24 симв.)"
                    class="duck-gameover-input"
                    @keydown.enter.stop="saveGameOverNickname"
                  />
                  <button
                    type="button"
                    class="duck-gameover-save-btn"
                    :class="{ 'duck-gameover-save-btn--saved': nickSaved }"
                    :disabled="savingNick"
                    @click="saveGameOverNickname"
                  >
                    {{ savingNick ? '...' : (nickSaved ? '✓ Сохранено' : 'Сохранить') }}
                  </button>
                </div>
                <div v-if="nickError" class="duck-gameover-error">{{ nickError }}</div>
              </div>

              <div class="duck-gameover-actions">
                <button
                  type="button"
                  class="duck-action-btn duck-action-btn--primary"
                  @click="restartCurrentGame"
                >
                  ▶ Сыграть ещё раз
                </button>
                <button
                  type="button"
                  class="duck-action-btn"
                  @click="openLeaderboard"
                >
                  🏆 Рекорды
                </button>
                <button
                  type="button"
                  class="duck-action-btn duck-action-btn--dismiss"
                  title="Скрыть окно"
                  @click="gameOverCard = null"
                >
                  ✕
                </button>
              </div>
            </div>
          </div>
        </div>

        <GameLeaderboard v-if="showLeaderboard" :game="activeGame" class="duck-leaderboard" />
      </div>
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
// создаёт другую в том же canvas-контейнере.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { isBusy } from '../../composables/useLongWait'
import { GAME_REGISTRY, isGameId, type GameId, type GameInstance } from './gameRegistry'
import {
  getLeaderboard,
  reportGameOver,
  getCachedNickname,
  setNickname,
  submitScore,
} from './gameScores'
import GameLeaderboard from './GameLeaderboard.vue'

const GAME_STORAGE_KEY = 'gala_last_game'
const showLeaderboard = ref(true)

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [boolean]; close: [] }>()

const canvasWrapperRef = ref<HTMLElement | null>(null)
const windowRef = ref<HTMLElement | null>(null)
let game: GameInstance | null = null

const activeGame = ref<GameId>(loadLastGame())
const currentBest = ref(0)
const playerNickname = ref(getCachedNickname())
const gameOverCard = ref<{ score: number; isNewRecord: boolean } | null>(null)
const savingNick = ref(false)
const nickSaved = ref(false)
const nickError = ref('')

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
  gameOverCard.value = null
  emit('update:open', false)
  emit('close')
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) {
    e.stopImmediatePropagation()
    e.preventDefault()
    handleClose()
  }
}

function createGame(kind: GameId, container: HTMLElement): GameInstance {
  const def = GAME_REGISTRY.find((g) => g.id === kind) ?? GAME_REGISTRY[0]!
  return def.create(container)
}

function wireGameScore(g: GameInstance, kind: GameId) {
  getLeaderboard(kind)
    .then((board) => {
      g.setBest(board.me.best)
      currentBest.value = board.me.best
      if (board.me.nickname && board.me.nickname !== 'Игрок') {
        playerNickname.value = board.me.nickname
      }
    })
    .catch((e) => console.warn('[games] getLeaderboard failed', e))

  g.onGameOver((score) => {
    const isNew = score > currentBest.value
    gameOverCard.value = { score, isNewRecord: isNew }
    if (isNew) {
      currentBest.value = score
    }
    const nickToSend = playerNickname.value?.trim() || undefined
    reportGameOver(kind, score, nickToSend).then((result) => {
      if (result) {
        g.setBest(result.best)
        currentBest.value = result.best
      }
    })
  })
}

async function saveGameOverNickname() {
  const nick = playerNickname.value.trim()
  if (!nick || nick.length < 2 || nick.length > 24) {
    nickError.value = 'Ник: от 2 до 24 символов'
    return
  }
  savingNick.value = true
  nickError.value = ''
  try {
    const saved = await setNickname(nick)
    playerNickname.value = saved
    nickSaved.value = true
    if (gameOverCard.value) {
      await submitScore(activeGame.value, gameOverCard.value.score, saved)
    }
    setTimeout(() => {
      nickSaved.value = false
    }, 2500)
  } catch (e: any) {
    nickError.value = 'Ошибка (2-24 симв., буквы/цифры/._-)'
  } finally {
    savingNick.value = false
  }
}

function openLeaderboard() {
  showLeaderboard.value = true
}

function restartCurrentGame() {
  gameOverCard.value = null
  if (props.open) {
    unmountGame()
    if (canvasWrapperRef.value) canvasWrapperRef.value.innerHTML = ''
    mountGame()
  }
}

function mountGame() {
  if (!canvasWrapperRef.value) return
  game = createGame(activeGame.value, canvasWrapperRef.value)
  game.onEscape(handleClose)
  wireGameScore(game, activeGame.value)
  game.start()
}

function unmountGame() {
  game?.destroy()
  game = null
}

function selectGame(kind: GameId) {
  if (activeGame.value === kind) return
  gameOverCard.value = null
  activeGame.value = kind
  saveLastGame(kind)
  if (props.open) {
    unmountGame()
    if (canvasWrapperRef.value) canvasWrapperRef.value.innerHTML = ''
    mountGame()
  }
}

watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      await nextTick()
      gameOverCard.value = null
      if (canvasWrapperRef.value) canvasWrapperRef.value.innerHTML = ''
      mountGame()
      windowRef.value?.focus()
    } else {
      gameOverCard.value = null
      unmountGame()
    }
  },
  { immediate: true }
)

onMounted(() => {
  window.addEventListener('keydown', handleKeydown, true)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown, true)
  unmountGame()
})
</script>

<style scoped>
.duck-backdrop {
  position: fixed;
  inset: 0;
  /* Поверх кнопки .duck-play-btn (10000) и любых полноэкранных v-dialog (2400+). */
  z-index: 10100;
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

.duck-score-toggle {
  background: #fff;
  border: 1px solid #111;
  color: #111;
  font-family: inherit;
  font-size: 12px;
  line-height: 1;
  padding: 4px 8px;
  cursor: pointer;
  order: 2;
  flex: 0 0 auto;
  white-space: nowrap;
}

.duck-score-toggle--active {
  font-weight: 700;
  text-decoration: underline;
}

.duck-score-toggle:hover {
  background: #111;
  color: #fff;
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

.duck-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: row;
  overflow: hidden;
}

@media (max-width: 560px) {
  .duck-body {
    flex-direction: column;
    overflow-y: auto;
  }
}

.duck-canvas-wrapper {
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
  position: relative;
}

.duck-canvas-container {
  width: 100%;
  height: 100%;
}

/* Модальный оверлей Game Over */
.duck-gameover-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
  padding: 16px;
  animation: duckFadeIn 0.15s ease-out;
}

@keyframes duckFadeIn {
  from {
    opacity: 0;
    transform: scale(0.97);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.duck-gameover-card {
  background: #1e1e24;
  color: #fff;
  border: 2px solid #ffcc00;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(255, 204, 0, 0.2);
  border-radius: 8px;
  padding: 20px 24px;
  max-width: 360px;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 14px;
  font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
}

.duck-gameover-badge {
  text-align: center;
  font-size: 18px;
  font-weight: 800;
  letter-spacing: 2px;
  color: #ffcc00;
  text-transform: uppercase;
}

.duck-gameover-score-row {
  display: flex;
  justify-content: space-around;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 6px;
  padding: 8px 12px;
}

.duck-gameover-score-box {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.duck-gameover-score-label {
  font-size: 11px;
  text-transform: uppercase;
  color: #aaa;
}

.duck-gameover-score-val {
  font-size: 22px;
  font-weight: 700;
  color: #fff;
}

.duck-gameover-newrecord {
  text-align: center;
  color: #4ade80;
  font-weight: 700;
  font-size: 13px;
  background: rgba(74, 222, 128, 0.12);
  border: 1px dashed #4ade80;
  border-radius: 4px;
  padding: 4px 8px;
}

.duck-gameover-nick-box {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.duck-gameover-nick-label {
  font-size: 11px;
  color: #ccc;
}

.duck-gameover-nick-row {
  display: flex;
  gap: 6px;
}

.duck-gameover-input {
  flex: 1 1 auto;
  min-width: 0;
  background: #111;
  border: 1px solid #555;
  color: #fff;
  padding: 6px 10px;
  font-size: 13px;
  font-family: inherit;
  border-radius: 4px;
  outline: none;
}
.duck-gameover-input:focus {
  border-color: #ffcc00;
}

.duck-gameover-save-btn {
  background: #333;
  color: #ffcc00;
  border: 1px solid #ffcc00;
  border-radius: 4px;
  padding: 6px 12px;
  font-size: 12px;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}
.duck-gameover-save-btn:hover:not(:disabled) {
  background: #ffcc00;
  color: #111;
}
.duck-gameover-save-btn--saved {
  background: #166534;
  border-color: #22c55e;
  color: #fff;
}

.duck-gameover-error {
  font-size: 11px;
  color: #f87171;
}

.duck-gameover-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.duck-action-btn {
  flex: 1 1 auto;
  background: #2a2a32;
  color: #fff;
  border: 1px solid #555;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 12px;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  text-align: center;
  transition: all 0.15s;
}
.duck-action-btn:hover {
  background: #3a3a44;
}
.duck-action-btn--primary {
  background: #ffcc00;
  color: #111;
  border-color: #ffcc00;
}
.duck-action-btn--primary:hover {
  background: #ffe066;
}
.duck-action-btn--dismiss {
  flex: 0 0 34px;
  padding: 8px 0;
}

.duck-leaderboard {
  flex: 0 0 auto;
  border-left: 1px solid #111;
  max-width: 280px;
}

@media (max-width: 560px) {
  .duck-leaderboard {
    border-left: none;
    border-top: 1px solid #111;
    max-width: none;
    max-height: 45%;
  }
}
</style>