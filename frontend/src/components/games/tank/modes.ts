// Режимы игры (п.2 задания) — единственное место, где собирается стартовый
// набор танков и баз для «1 игрок против компьютера», «2 игрока вместе» и
// «2 игрока друг против друга». tankGame.ts только читает результат отсюда,
// логика набора юнитов не продублирована в самом классе игры (Правило №6).

import { BASE_NORTH, BASE_SOUTH } from './maps'
import type { GameMode, Side, Tank } from './types'

export interface ModeBase {
  side: Side
  pos: { x: number; y: number }
}

export interface ModeSetup {
  tanks: Tank[]
  bases: ModeBase[]
  wave: boolean // есть ли волна «диких» врагов PvE (1 игрок / ко-оп)
}

let nextTankId = 1
function freshId(): number {
  return nextTankId++
}

function makeTank(partial: Partial<Tank> & Pick<Tank, 'x' | 'y' | 'kind' | 'side'>): Tank {
  return {
    id: freshId(),
    dir: 'up',
    alive: true,
    cooldown: 0,
    hp: 1,
    maxHp: 1,
    level: 0,
    shieldTimer: 0,
    frozenTimer: 0,
    changeDirTimer: 0.3 + Math.random() * 0.6,
    speedMul: 1,
    specialDrop: false,
    ...partial,
  }
}

export function buildModeSetup(mode: GameMode): ModeSetup {
  if (mode === 'solo') {
    return {
      wave: true,
      bases: [{ side: 'south', pos: BASE_SOUTH }],
      tanks: [
        makeTank({ x: BASE_SOUTH.x, y: BASE_SOUTH.y - 2, kind: 'player', side: 'south', playerId: 1, maxHp: 1, hp: 1 }),
      ],
    }
  }

  if (mode === 'coop') {
    return {
      wave: true,
      bases: [{ side: 'south', pos: BASE_SOUTH }],
      tanks: [
        makeTank({ x: BASE_SOUTH.x - 2, y: BASE_SOUTH.y - 2, kind: 'player', side: 'south', playerId: 1 }),
        makeTank({ x: BASE_SOUTH.x + 2, y: BASE_SOUTH.y - 2, kind: 'player', side: 'south', playerId: 2 }),
      ],
    }
  }

  // versus — каждая сторона: игрок + 2 компьютерных союзника (п.2),
  // своя база у каждой стороны.
  return {
    wave: false,
    bases: [
      { side: 'south', pos: BASE_SOUTH },
      { side: 'north', pos: BASE_NORTH },
    ],
    tanks: [
      makeTank({ x: BASE_SOUTH.x, y: BASE_SOUTH.y - 2, kind: 'player', side: 'south', playerId: 1, dir: 'up' }),
      makeTank({ x: BASE_SOUTH.x - 3, y: BASE_SOUTH.y - 2, kind: 'ally', side: 'south', dir: 'up' }),
      makeTank({ x: BASE_SOUTH.x + 3, y: BASE_SOUTH.y - 2, kind: 'ally', side: 'south', dir: 'up' }),
      makeTank({ x: BASE_NORTH.x, y: BASE_NORTH.y + 2, kind: 'player', side: 'north', playerId: 2, dir: 'down' }),
      makeTank({ x: BASE_NORTH.x - 3, y: BASE_NORTH.y + 2, kind: 'ally', side: 'north', dir: 'down' }),
      makeTank({ x: BASE_NORTH.x + 3, y: BASE_NORTH.y + 2, kind: 'ally', side: 'north', dir: 'down' }),
    ],
  }
}

export function makeWildEnemy(x: number, y: number, enemyType: 'basic' | 'fast' | 'armored', specialDrop: boolean): Tank {
  const hp = enemyType === 'armored' ? 4 : 1
  const speedMul = enemyType === 'fast' ? 1.5 : enemyType === 'armored' ? 0.8 : 1
  return makeTank({ x, y, kind: 'enemy', side: 'wild', enemyType, hp, maxHp: hp, speedMul, specialDrop, dir: 'down' })
}

export function opposingSideFor(side: Side, mode: GameMode): Side {
  if (side === 'south') return mode === 'versus' ? 'north' : 'wild'
  if (side === 'north') return 'south'
  return 'south'
}
