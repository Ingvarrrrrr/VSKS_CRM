// Клиент API лидербордов мини-игр окна ожидания (/api/games/*, см.
// backend/app/routers/games.py). Единственное место, откуда фронт зовёт эти
// ручки — Правило №6, второй клиент не заводим.
//
// reportGameOver(game, score) — функция для будущего шага (owner: "другой
// шаг добавит onGameOver hooks"), которую должны вызывать сами игры при
// game over. Сама по себе не вызывается из *Game.ts сейчас (это НЕ в этой
// задаче) — только публикуется отсюда и даёт знать GameLeaderboard.vue через
// простую шину событий ниже, что нужно перерисовать панель.

import { apiFetch } from '../../api'
import type { GameId } from './gameRegistry'

export interface SubmitScoreResult {
  best: number
  rank_account: number
  rank_global: number
}

export interface LeaderboardEntryAccount {
  fio: string
  score: number
  is_me: boolean
}

export interface LeaderboardEntryGlobal {
  nickname: string
  score: number
  is_me: boolean
}

export interface LeaderboardResponse {
  me: { best: number; nickname: string }
  account: LeaderboardEntryAccount[]
  global: LeaderboardEntryGlobal[]
  my_global_rank: number | null
}

export async function submitScore(game: GameId, score: number): Promise<SubmitScoreResult> {
  return apiFetch<SubmitScoreResult>(`/games/${game}/score`, {
    method: 'POST',
    body: JSON.stringify({ score }),
  })
}

export async function getLeaderboard(game: GameId): Promise<LeaderboardResponse> {
  return apiFetch<LeaderboardResponse>(`/games/${game}/leaderboard`)
}

export async function getNickname(): Promise<string> {
  const r = await apiFetch<{ nickname: string }>('/games/nickname')
  return r.nickname
}

export async function setNickname(nickname: string | null): Promise<string> {
  const r = await apiFetch<{ nickname: string }>('/games/nickname', {
    method: 'PUT',
    body: JSON.stringify({ nickname }),
  })
  return r.nickname
}

// --- простая шина "счёт только что отправлен" -------------------------------
// GameLeaderboard.vue слушает это событие, чтобы перечитать таблицу сразу
// после того, как reportGameOver отработал — без второго источника данных.
const GAME_OVER_EVENT = 'gala-game-over'

export async function reportGameOver(game: GameId, score: number): Promise<SubmitScoreResult | null> {
  try {
    const result = await submitScore(game, score)
    try {
      window.dispatchEvent(new CustomEvent(GAME_OVER_EVENT, { detail: { game, score, result } }))
    } catch {
      /* ignore — тестовое/не-браузерное окружение */
    }
    return result
  } catch (e) {
    console.warn('[games] reportGameOver failed', e)
    return null
  }
}

export function onGameOver(fn: (detail: { game: GameId; score: number; result: SubmitScoreResult }) => void): () => void {
  const handler = (e: Event) => fn((e as CustomEvent).detail)
  window.addEventListener(GAME_OVER_EVENT, handler)
  return () => window.removeEventListener(GAME_OVER_EVENT, handler)
}
