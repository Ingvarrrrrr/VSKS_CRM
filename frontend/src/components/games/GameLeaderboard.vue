<template>
  <div class="gl-panel" :class="{ 'gl-panel--arcade': theme === 'arcade' }">
    <div class="gl-tabs">
      <button
        type="button"
        class="gl-tab"
        :class="{ 'gl-tab--active': tab === 'account' }"
        @click="tab = 'account'"
      >
        В компании
      </button>
      <button
        type="button"
        class="gl-tab"
        :class="{ 'gl-tab--active': tab === 'global' }"
        @click="tab = 'global'"
      >
        Все
      </button>
    </div>

    <!-- Быстрое управление ником (скрыто, если передано hideNickEdit) -->
    <div v-if="!hideNickEdit" class="gl-nick-card">
      <div class="gl-nick-label">Ник в рейтинге:</div>
      <div v-if="!editingNickname" class="gl-nick-display">
        <span class="gl-nick-current">{{ currentNickname }}</span>
        <button type="button" class="gl-nick-edit-btn" title="Сменить ник" @click="startEditNickname">
          ✏️ Сменить
        </button>
      </div>
      <div v-else class="gl-nick-edit-row">
        <input
          v-model="nicknameDraft"
          class="gl-nick-input"
          maxlength="24"
          placeholder="Ник (2-24 симв.)"
          @keydown.enter="saveNicknameAction"
          @keydown.esc="editingNickname = false"
        />
        <button type="button" class="gl-nick-action-btn gl-nick-save" :disabled="saving" @click="saveNicknameAction">
          {{ saving ? '…' : '✓' }}
        </button>
        <button type="button" class="gl-nick-action-btn" @click="editingNickname = false">✕</button>
      </div>
      <div v-if="nicknameError" class="gl-error">{{ nicknameError }}</div>
    </div>

    <div class="gl-me">
      <span>Мой рекорд: <b>{{ data?.me.best ?? 0 }}</b></span>
      <span v-if="tab === 'global' && data?.my_global_rank" class="gl-me-rank">
        Место: #{{ data.my_global_rank }}
      </span>
    </div>

    <div v-if="loading" class="gl-empty">Загрузка…</div>
    <div v-else-if="tab === 'account'" class="gl-list">
      <div v-if="!data?.account.length" class="gl-empty">Пока нет результатов</div>
      <div
        v-for="(row, i) in data?.account"
        :key="i"
        class="gl-row"
        :class="{ 'gl-row--me': row.is_me }"
      >
        <span class="gl-rank">{{ i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : i + 1 }}</span>
        <span class="gl-name">{{ row.nickname || 'Игрок' }} <span v-if="row.is_me" class="gl-me-tag">(Вы)</span></span>
        <span class="gl-score">{{ row.score }}</span>
      </div>
    </div>
    <div v-else class="gl-list">
      <div v-if="!data?.global.length" class="gl-empty">Пока нет результатов</div>
      <div
        v-for="(row, i) in data?.global"
        :key="i"
        class="gl-row"
        :class="{ 'gl-row--me': row.is_me }"
      >
        <span class="gl-rank">{{ i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : i + 1 }}</span>
        <span class="gl-name">{{ row.nickname || 'Игрок' }} <span v-if="row.is_me" class="gl-me-tag">(Вы)</span></span>
        <span class="gl-score">{{ row.score }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Панель лидербордов мини-игр — только ники игроков (никакого ФИО!)
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { GameId } from './gameRegistry'
import {
  getLeaderboard,
  setNickname,
  getCachedNickname,
  onGameOver,
  type LeaderboardResponse,
} from './gameScores'

const props = withDefaults(
  defineProps<{
    game: GameId
    hideNickEdit?: boolean
    theme?: 'light' | 'arcade'
  }>(),
  {
    hideNickEdit: false,
    theme: 'light',
  }
)

const tab = ref<'account' | 'global'>('account')
const data = ref<LeaderboardResponse | null>(null)
const loading = ref(false)
const saving = ref(false)
const editingNickname = ref(false)
const nicknameDraft = ref('')
const nicknameError = ref('')

const currentNickname = computed(() => {
  if (data.value?.me.nickname && data.value.me.nickname !== 'Игрок') {
    return data.value.me.nickname
  }
  return getCachedNickname() || 'Игрок'
})

async function load() {
  loading.value = true
  try {
    data.value = await getLeaderboard(props.game)
  } catch (e) {
    console.warn('[GameLeaderboard] load failed', e)
  } finally {
    loading.value = false
  }
}

function startEditNickname() {
  const cur = currentNickname.value
  nicknameDraft.value = cur === 'Игрок' ? '' : cur
  nicknameError.value = ''
  editingNickname.value = true
}

async function saveNicknameAction() {
  nicknameError.value = ''
  saving.value = true
  try {
    const trimmed = nicknameDraft.value.trim()
    const result = await setNickname(trimmed.length ? trimmed : null)
    if (data.value) data.value.me.nickname = result
    editingNickname.value = false
    await load()
  } catch (e: any) {
    nicknameError.value = 'Ошибка (2-24 симв., буквы/цифры/._-)'
  } finally {
    saving.value = false
  }
}

let unsubscribe: (() => void) | null = null

watch(() => props.game, load)

onMounted(() => {
  load()
  unsubscribe = onGameOver((detail) => {
    if (detail.game === props.game) load()
  })
})

onUnmounted(() => {
  unsubscribe?.()
})

defineExpose({ load })
</script>

<style scoped>
.gl-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-family: inherit;
  font-size: 12px;
  background: #fff;
  border: 1px solid #111;
  padding: 8px;
  min-width: 220px;
  max-width: 100%;
  max-height: 100%;
  overflow-y: auto;
}

/* Arcade (Dark) Theme */
.gl-panel--arcade {
  background: #141419;
  border: 1px solid #333;
  color: #eee;
}
.gl-panel--arcade .gl-tab {
  background: #222;
  border-color: #444;
  color: #ccc;
}
.gl-panel--arcade .gl-tab--active {
  background: #ffcc00;
  color: #111;
  font-weight: 700;
  border-color: #ffcc00;
  text-decoration: none;
}
.gl-panel--arcade .gl-tab:hover:not(.gl-tab--active) {
  background: #333;
  color: #fff;
}
.gl-panel--arcade .gl-nick-card {
  background: #1c1c24;
  border-color: #333;
}
.gl-panel--arcade .gl-nick-label {
  color: #aaa;
}
.gl-panel--arcade .gl-nick-current {
  color: #ffcc00;
}
.gl-panel--arcade .gl-nick-input {
  background: #111;
  border-color: #555;
  color: #fff;
}
.gl-panel--arcade .gl-row {
  border-bottom: 1px solid #222;
}
.gl-panel--arcade .gl-row--me {
  background: rgba(255, 204, 0, 0.12);
  border: 1px solid #ffcc00;
  color: #fff;
}
.gl-panel--arcade .gl-me-tag {
  color: #ffcc00;
}
.gl-panel--arcade .gl-score {
  color: #4ade80;
}

.gl-tabs {
  display: flex;
  gap: 4px;
}

.gl-tab {
  flex: 1 1 auto;
  background: #fff;
  border: 1px solid #111;
  color: #111;
  font-family: inherit;
  font-size: 12px;
  padding: 4px 6px;
  cursor: pointer;
}

.gl-tab--active {
  font-weight: 700;
  text-decoration: underline;
  background: #f4f4f4;
}

.gl-tab:hover {
  background: #111;
  color: #fff;
}

.gl-nick-card {
  background: #fafafa;
  border: 1px solid #ddd;
  border-radius: 4px;
  padding: 6px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.gl-nick-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #666;
}

.gl-nick-display {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.gl-nick-current {
  font-weight: 700;
  color: #111;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gl-nick-edit-btn {
  background: none;
  border: none;
  color: #0284c7;
  font-size: 11px;
  cursor: pointer;
  padding: 0;
  font-family: inherit;
}
.gl-nick-edit-btn:hover {
  text-decoration: underline;
}

.gl-nick-edit-row {
  display: flex;
  gap: 4px;
}

.gl-nick-input {
  border: 1px solid #111;
  font-family: inherit;
  font-size: 12px;
  padding: 2px 6px;
  flex: 1 1 auto;
  min-width: 0;
  border-radius: 2px;
}

.gl-nick-action-btn {
  background: #fff;
  border: 1px solid #111;
  cursor: pointer;
  padding: 2px 6px;
  font-size: 11px;
  border-radius: 2px;
}
.gl-nick-action-btn:hover {
  background: #eee;
}

.gl-nick-save {
  background: #111;
  color: #fff;
}
.gl-nick-save:hover {
  background: #333;
}

.gl-me {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  padding: 2px 0;
}

.gl-me-rank {
  opacity: 0.85;
  font-weight: 600;
  color: #0284c7;
}

.gl-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 40px;
}

.gl-row {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 2px 4px;
  border-radius: 3px;
}

.gl-row--me {
  font-weight: 700;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
}

.gl-me-tag {
  font-size: 10px;
  color: #0284c7;
  font-weight: 600;
  margin-left: 2px;
}

.gl-rank {
  width: 1.8em;
  flex: 0 0 auto;
  text-align: center;
}

.gl-name {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gl-score {
  flex: 0 0 auto;
  font-weight: 700;
}

.gl-empty {
  opacity: 0.6;
  padding: 8px 0;
  text-align: center;
}

.gl-error {
  color: #b00020;
  font-size: 11px;
}
</style>