// Единственный список мини-игр окна «пока грузится» (DuckShootWindow.vue читает
// отсюда вкладки/заголовки, второго списка с теми же данными не заводим — Правило №6).
// Любая игра, добавленная сюда, обязана реализовать GameInstance ниже — этому
// контракту уже соответствуют все четыре класса без изменений их кода.

import { DuckShootGame } from './duckShootGame'
import { BrickGame } from './brickGame'
import { TankGame } from './tankGame'
import { EggGame } from './eggGame'

export type GameId = 'duck' | 'brick' | 'tank' | 'egg'

export interface GameInstance {
  start(): void
  destroy(): void
  onEscape(fn: () => void): void
  // Рекорд ("best") больше не хранится в localStorage самой игрой — единственный
  // источник истины — сервер (Правило №6). DuckShootWindow.vue засевает рекорд
  // через setBest() сразу после создания игры (из getLeaderboard) и обновляет
  // его повторно после отправки счёта через onGameOver (из ответа submitScore).
  onGameOver(fn: (score: number) => void): void
  setBest(best: number): void
}

export interface GameDefinition {
  id: GameId
  title: string
  create(container: HTMLElement): GameInstance
}

export const GAME_REGISTRY: GameDefinition[] = [
  { id: 'duck', title: 'Утиная охота', create: (c) => new DuckShootGame(c) },
  { id: 'brick', title: 'Кирпичики', create: (c) => new BrickGame(c) },
  { id: 'tank', title: 'Танчики', create: (c) => new TankGame(c) },
  { id: 'egg', title: 'Лови яйца', create: (c) => new EggGame(c) },
]

export function isGameId(v: string | null): v is GameId {
  return !!v && GAME_REGISTRY.some((g) => g.id === v)
}
