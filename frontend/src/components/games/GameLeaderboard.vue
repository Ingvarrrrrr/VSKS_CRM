<template>
  <div class="gl-panel">
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

    <div class="gl-me">
      <span>Мой лучший результат: <b>{{ data?.me.best ?? 0 }}</b></span>
      <span v-if="tab === 'global' && data?.my_global_rank" class="gl-me-rank">
        Место: {{ data.my_global_rank }}
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
        <span class="gl-rank">{{ i + 1 }}</span>
        <span class="gl-name">{{ row.fio }}</span>
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
        <span class="gl-rank">{{ i + 1 }}</span>
        <span class="gl-name">{{ row.nickname }}</span>
        <span class="gl-score">{{ row.score }}</span>
      </div>
    </div>

    <div class="gl-nickname">
      <template v-if="!editingNickname">
        <span>Ник: {{ data?.me.nickname ?? 'Игрок' }}</span>
        <button type="button" class="gl-link-btn" @click="startEditNickname">изменить</button>
      </template>
      <template v-else>
        <input
          v-model="nicknameDraft"
          class="gl-nick-input"
          maxlength="24"
          placeholder="Ник (2-24 символа)"
          @keydown.enter="saveNickname"
          @keydown.esc="editingNickname = false"
        />
        <button type="button" class="gl-link-btn" @click="saveNickname">сохранить</button>
        <button type="button" class="gl-link-btn" @click="editingNickname = false">отмена</button>
      </template>
      <span v-if="nicknameError" class="gl-error">{{ nicknameError }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
// Компактная панель лидербордов для активной мини-игры (владелец, 30.10.2026).
// Данные — ТОЛЬКО через gameScores.ts (Правило №6, единственный клиент).
import { onMounted, onUnmounted, ref, watch } from 'vue'
import type { GameId } from './gameRegistry'
import {
  getLeaderboard,
  setNickname,
  onGameOver,
  type LeaderboardResponse,
} from './gameScores'

const props = defineProps<{ game: GameId }>()

const tab = ref<'account' | 'global'>('account')
const data = ref<LeaderboardResponse | null>(null)
const loading = ref(false)
const editingNickname = ref(false)
const nicknameDraft = ref('')
const nicknameError = ref('')

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
  nicknameDraft.value = data.value?.me.nickname === 'Игрок' ? '' : (data.value?.me.nickname ?? '')
  nicknameError.value = ''
  editingNickname.value = true
}

async function saveNickname() {
  nicknameError.value = ''
  try {
    const trimmed = nicknameDraft.value.trim()
    const result = await setNickname(trimmed.length ? trimmed : null)
    if (data.value) data.value.me.nickname = result
    editingNickname.value = false
  } catch (e: any) {
    nicknameError.value = 'Не удалось сохранить ник'
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
  min-width: 200px;
  max-width: 260px;
  max-height: 100%;
  overflow-y: auto;
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
}

.gl-tab:hover {
  background: #111;
  color: #fff;
}

.gl-me {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.gl-me-rank {
  opacity: 0.8;
}

.gl-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 40px;
}

.gl-row {
  display: flex;
  gap: 6px;
  align-items: baseline;
}

.gl-row--me {
  font-weight: 700;
}

.gl-rank {
  width: 1.6em;
  flex: 0 0 auto;
  opacity: 0.7;
}

.gl-name {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gl-score {
  flex: 0 0 auto;
}

.gl-empty {
  opacity: 0.6;
  padding: 4px 0;
}

.gl-nickname {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  border-top: 1px solid #ccc;
  padding-top: 6px;
}

.gl-link-btn {
  background: none;
  border: none;
  color: #111;
  text-decoration: underline;
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
  padding: 0;
}

.gl-nick-input {
  border: 1px solid #111;
  font-family: inherit;
  font-size: 12px;
  padding: 2px 4px;
  width: 110px;
}

.gl-error {
  color: #b00020;
  flex: 1 1 100%;
}
</style>
