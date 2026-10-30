// Карты уровней «Танчиков» — поле ×4 (26×26 вместо 13×13, п.1 задания).
// Вместо того чтобы вручную расписывать все 26×26 символов на 5 уровней
// (и рисковать разъехаться по симметрии между верхом/низом поля), каждый
// уровень описан один раз как четверть поля QUADRANTS[i] (верхний левый
// угол, 13×13), а buildFullMap зеркалит её по вертикали и горизонтали —
// единственное место, где считается полная карта (Правило №6). Это даёт
// честную симметрию верх/низ, нужную режиму «друг против друга» (у обеих
// баз одинаковые укрытия).
//
// Символы четверти: . пусто, B кирпич, S сталь, W вода, T дерево(куст),
// E точка спавна (у верхнего края после зеркалирования появится и у
// нижнего — это и есть точки появления «диких» врагов в PvE и союзников
// в «версусе» у обеих баз). Базы и их ограда в карту не зашиты — считаются
// программно в buildGrid/carveBaseArea, т.к. база всегда в одном месте
// независимо от уровня (вынесено как BASE_SOUTH/BASE_NORTH).

import type { Tile, TileType } from './types'

export const QUADRANT_SIZE = 13
export const COLS = QUADRANT_SIZE * 2
export const ROWS = QUADRANT_SIZE * 2

function q(rows: string[]): string[] {
  return rows.map((r) => r.padEnd(QUADRANT_SIZE, '.'))
}

// Уровень 1 — слово «АКТ» кирпичом, кусты и стальной мини-бункер в глубине.
const Q1 = q([
  'E....E....E.',
  '.BBBBBBBBBB.',
  '.B.........B',
  '.B.BB.B..B.B',
  '.B.B..B..B.B',
  '.B.BB.BB.B.B',
  '............',
  '.TT......TT.',
  '.B..SS....B.',
  '.B..SS....B.',
  '............',
  '............',
  '............',
])

// Уровень 2 — слово «НДС», водные карманы по краям.
const Q2 = q([
  'E...E...E...',
  '............',
  '.B.BB.B.BB..',
  '.B.B..B.B.B.',
  '.B.BB.B.BB..',
  '.B.B..B.B.B.',
  '.B.BB.B.BB..',
  '............',
  'WW...SS...W.',
  'WW........W.',
  '............',
  '............',
  '............',
])

// Уровень 3 — водная преграда поперёк четверти + стальные карманы.
const Q3 = q([
  'E..E....E..E',
  '.BB.BBBB.BB.',
  '.B.........B',
  '.B.T.BB.T..B',
  '............',
  'WWWW....WWW.',
  'WWWW....WWW.',
  '............',
  '.BB.S..S.BB.',
  '.BB.S..S.BB.',
  '....S..S....',
  '............',
  '............',
])

// Уровень 4 — слово «ИТОГО», плотнее остальных.
const Q4 = q([
  'E.E.....E.E.',
  '.B.BB.B.B.B.',
  '.B.B..B.B.B.',
  '.B.BB.B.B.B.',
  '.B.B..B.B.B.',
  '.B.BB.BB.BB.',
  '............',
  '.T........T.',
  '.B.S....S.B.',
  '.B.S....S.B.',
  '.B.SS..SS.B.',
  '............',
  '............',
])

// Уровень 5 — стальная крепость и вода по углам.
const Q5 = q([
  'E.E.E.E.E.E.',
  '.B........B.',
  'B.WWWW..WW.B',
  'B.WW......B.',
  '............',
  '.TT.BBBB.TT.',
  '....B..B....',
  '....B..B....',
  '...SS..SS...',
  '...S....S...',
  '...S....S...',
  '............',
  '............',
])

const QUADRANTS: string[][] = [Q1, Q2, Q3, Q4, Q5]

function reverseStr(s: string): string {
  return s.split('').reverse().join('')
}

function buildFullMap(quadrant: string[]): string[] {
  const top = quadrant.map((r) => r + reverseStr(r))
  const bottom = [...top].reverse()
  return [...top, ...bottom]
}

export const LEVEL_MAPS: string[][] = QUADRANTS.map(buildFullMap)
export const MAX_LEVELS = LEVEL_MAPS.length

export function tileMapForLevel(level: number): string[] {
  const idx = Math.min(LEVEL_MAPS.length - 1, Math.max(0, level - 1))
  return LEVEL_MAPS[idx] ?? LEVEL_MAPS[0]!
}

export interface BuiltGrid {
  grid: Tile[][]
  spawnPointsNorth: { x: number; y: number }[]
  spawnPointsSouth: { x: number; y: number }[]
}

export function buildGrid(level: number): BuiltGrid {
  const rows = tileMapForLevel(level)
  const grid: Tile[][] = []
  const spawnPointsNorth: { x: number; y: number }[] = []
  const spawnPointsSouth: { x: number; y: number }[] = []

  for (let y = 0; y < ROWS; y++) {
    const row: Tile[] = []
    const line = (rows[y] ?? '').padEnd(COLS, '.')
    for (let x = 0; x < COLS; x++) {
      const ch = line[x] ?? '.'
      let type: TileType = 'empty'
      if (ch === 'B') type = 'brick'
      else if (ch === 'S') type = 'steel'
      else if (ch === 'W') type = 'water'
      else if (ch === 'T') type = 'tree'
      row.push({ type, damage: 0 })
      if (ch === 'E') {
        if (y < ROWS / 2) spawnPointsNorth.push({ x, y })
        else spawnPointsSouth.push({ x, y })
      }
    }
    grid.push(row)
  }

  return { grid, spawnPointsNorth, spawnPointsSouth }
}

// Базы — одно и то же место на всех уровнях (Правило №6: нет смысла хранить
// координату базы в каждой из 5 карт). BASE_SOUTH — база игрока 1 / ко-опа,
// всегда существует; BASE_NORTH — база игрока 2, используется только в
// режиме «друг против друга».
export const BASE_SOUTH = { x: Math.floor(COLS / 2) - 1, y: ROWS - 2 }
export const BASE_NORTH = { x: Math.floor(COLS / 2) - 1, y: 1 }

// Ограда базы (п.3 задания) — кольцо кирпича вокруг базы, разрушаемое.
// Расчищает площадку 5×5 вокруг базы независимо от того, что было на карте
// в этом месте, иначе на части уровней база оказалась бы замурована.
export function carveBaseArea(grid: Tile[][], base: { x: number; y: number }): void {
  const h = grid.length
  const w = grid[0]?.length ?? 0
  for (let dy = -2; dy <= 2; dy++) {
    for (let dx = -2; dx <= 2; dx++) {
      const gx = base.x + dx
      const gy = base.y + dy
      if (gy < 0 || gy >= h || gx < 0 || gx >= w) continue
      const tile = grid[gy]![gx]!
      const ring = Math.max(Math.abs(dx), Math.abs(dy)) === 1
      const isCenter = dx === 0 && dy === 0
      if (isCenter) {
        tile.type = 'base'
        tile.damage = 0
      } else if (ring) {
        tile.type = 'brick'
        tile.damage = 0
      } else {
        tile.type = 'empty'
        tile.damage = 0
      }
    }
  }
}
