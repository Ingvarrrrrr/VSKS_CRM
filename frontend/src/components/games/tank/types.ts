// Общие типы «Танчиков» — единственное место, где описаны форма танка, пули,
// тайла и т.п. (Правило №6: все модули читают эти типы отсюда, не заводят
// параллельных).

export type Dir = 'up' | 'down' | 'left' | 'right'
export type TileType = 'empty' | 'brick' | 'steel' | 'water' | 'tree' | 'base'

export interface Tile {
  type: TileType
  // для brick: 0 = целый, 1..3 = сколько четвертей выбито, 4 = нет тайла
  damage: number
}

export interface Rect {
  x: number
  y: number
  w: number
  h: number
}

// 'south' — нижняя база (игрок 1 / ко-оп союзники), 'north' — верхняя база
// (игрок 2 в режиме «друг против друга»), 'wild' — враги компьютера в PvE
// (1 игрок / ко-оп), у них нет своей базы и союзников.
export type Side = 'south' | 'north' | 'wild'
export type TankKind = 'player' | 'ally' | 'enemy'
export type EnemyType = 'basic' | 'fast' | 'armored'

export interface Tank {
  id: number
  x: number
  y: number
  dir: Dir
  alive: boolean
  cooldown: number
  hp: number
  maxHp: number
  kind: TankKind
  side: Side
  playerId?: 1 | 2
  enemyType?: EnemyType
  level: number // 0..2, апгрейд от звезды — только у игроков
  shieldTimer: number
  frozenTimer: number
  changeDirTimer: number
  speedMul: number
  specialDrop: boolean // этот враг роняет бонус при уничтожении
  lives?: number // только у игроков — сколько осталось жизней на респаун
}

export interface Bullet {
  x: number
  y: number
  dir: Dir
  owner: Side
  speed: number
  alive: boolean
  piercesSteel: boolean
  fromTankId: number
}

export interface Explosion {
  x: number
  y: number
  t: number
}

export type PowerUpType = 'star' | 'helmet' | 'clock' | 'shovel' | 'grenade' | 'tank'

export interface PowerUp {
  type: PowerUpType
  x: number
  y: number
  t: number // секунд с появления
}

export type GameMode = 'solo' | 'coop' | 'versus'
export type GameState =
  | 'menu'
  | 'level-intro'
  | 'playing'
  | 'paused'
  | 'level-complete'
  | 'game-over'
  | 'match-over'

export const POWERUP_LIFETIME = 12
// 0 — база, 1 — быстрее пуля, 2 — две пули сразу, 3 — пули пробивают сталь
// (п.4 задания: «levels 1→2→3»).
export const POWERUP_UPGRADE_MAX = 3
export const SHIELD_SPAWN_SECONDS = 3
export const SHIELD_POWERUP_SECONDS = 10
export const FREEZE_SECONDS = 8
export const FENCE_STEEL_SECONDS = 15
