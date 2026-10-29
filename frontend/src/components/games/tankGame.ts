// Based on kyuuzou/battle-city (MIT License), Copyright (c) 2023 Nelson Rodrigues
//
// MIT License
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.
//
// Источник (kyuuzou/battle-city) — это Unity-прототип на C#/3D-физике, в котором
// реально реализованы лишь три куска логики, они и портированы сюда:
//   - LevelLoader.cs: уровень описывается текстовой сеткой символов, символ
//     однозначно определяет объект в клетке (у нас — тип тайла в grid[y][x]);
//   - Projectile.cs: снаряд летит с постоянной скоростью по прямой и исчезает
//     при первом столкновении (у нас — Bullet.move + alive=false на хите);
//   - Destructible.cs: объект уничтожается от первого попадания (у нас —
//     кирпич выбивается четвертью за попадание, что ближе к оригинальной игре
//     жанра, чем 3D-прототип, но механика "снаряд уничтожает препятствие при
//     столкновении" — оттуда).
// В прототипе NET AI врагов, базы для защиты, жизней и подсчёта уровня — этого
// в репозитории просто нет (TankOnRails/TankReallistic — только ручное
// управление человеком на свободной физике, Rigidbody/AddForce, не сеточное).
// Эти части (сеточное 4-направленное движение, ИИ врагов, база, жизни, волны)
// спроектированы заново под цветной спрайтовый стиль игры — фон под доской
// тёмно-зелёный (трава), свой для этой игры (см. _buildBackground), без
// общего "документного" фона, который остался у игр без цветных спрайтов.
//
// Карты уровней, текстуры, звук и названия — свои; оригинальные стадии/ассеты
// Namco (которых в этом Unity-репо и не было) не используются. Торговая марка
// держателя классической игры жанра в UI не используется — см. ПРАВИЛО ниже.
// UI-имя игры — «Танчики».

import { loadSprite, isSpriteReady } from './spriteLoader'

import tileGrassUrl from './sprites/tank/tileGrass.png'
import brickWallUrl from './sprites/tank/brickWall.png'
import steelWallUrl from './sprites/tank/steelWall.png'
import treeUrl from './sprites/tank/tree.png'
import tankBodyPlayerUrl from './sprites/tank/tankBodyPlayer.png'
import tankBarrelPlayerUrl from './sprites/tank/tankBarrelPlayer.png'
import tankBodyEnemyUrl from './sprites/tank/tankBodyEnemy.png'
import tankBarrelEnemyUrl from './sprites/tank/tankBarrelEnemy.png'
import tankBodyToughUrl from './sprites/tank/tankBodyTough.png'
import tankBarrelToughUrl from './sprites/tank/tankBarrelTough.png'
import bulletPlayerUrl from './sprites/tank/bulletPlayer.png'
import bulletEnemyUrl from './sprites/tank/bulletEnemy.png'
import explosion1Url from './sprites/tank/explosion1.png'
import explosion2Url from './sprites/tank/explosion2.png'
import explosion3Url from './sprites/tank/explosion3.png'
import baseUrl from './sprites/tank/base.png'

// Спрайты — набор Kenney "Top-down Tanks Redux" (kenney.nl), лицензия CC0,
// см. sprites/tank/License.txt и THIRD_PARTY_LICENSES.md. Загрузка —
// общий spriteLoader.ts (как в DuckShootGame), пока не готово — fallback
// прямоугольниками/глифами, игра не блокируется ожиданием картинок.

type GameState = 'level-intro' | 'playing' | 'level-complete' | 'game-over'
type Dir = 'up' | 'down' | 'left' | 'right'
type TileType = 'empty' | 'brick' | 'steel' | 'water' | 'tree' | 'base'

interface Tile {
  type: TileType
  // для brick: 0 = целый, 1..3 = сколько четвертей выбито, 4 = нет тайла
  damage: number
}

interface Rect {
  x: number
  y: number
  w: number
  h: number
}

interface Bullet {
  x: number
  y: number
  dir: Dir
  owner: 'player' | 'enemy'
  speed: number
  alive: boolean
}

interface Tank {
  x: number
  y: number
  dir: Dir
  alive: boolean
  cooldown: number
  // только для врагов
  isEnemy: boolean
  changeDirTimer: number
  tough: boolean // "крепкий" враг — 2 попадания
  hp: number
}

const COLS = 13
const ROWS = 13
const DIRS: Dir[] = ['up', 'down', 'left', 'right']
const MAX_LEVELS = 5
const PLAYER_SPEED = 118 // px/sec
const ENEMY_SPEED_BASE = 70
const BULLET_SPEED_PLAYER = 340
const BULLET_SPEED_ENEMY = 230
const PLAYER_FIRE_COOLDOWN = 0.38
const ENEMY_FIRE_COOLDOWN_MIN = 1.1
const ENEMY_FIRE_COOLDOWN_MAX = 2.6
const ENEMIES_PER_LEVEL = [8, 10, 12, 14, 16]
const MAX_ENEMIES_ON_FIELD = 4

// Карты уровней — свои, без оригинальных стадий первоисточника.
// Символы: . пусто, B кирпич, S сталь, W вода, T дерево(куст), E точка спавна
// врага, P старт игрока, X база (защищаемый объект в центре низа).
// Буквенные/словесные узоры кирпичных стен — вместо копирования чьих-либо
// стадий (ПРАВИЛО задания: свои 5 карт, не Namco-макеты).
const LEVEL_MAPS: string[][] = [
  // Уровень 1 — рамка + слово "АКТ" кирпичом в центре
  [
    'E.........E.',
    '.BBBBBBBBB..',
    '.B.......B..',
    '.B.BB.B..B..',
    '.B.B..B..B..',
    '.B.BB.BB.B..',
    '............',
    '.TT.....TT..',
    '.B...SS...B.',
    '.B...SS...B.',
    '............',
    '.....P......',
    '.....X......',
  ].map((r) => r.padEnd(COLS, '.')),
  // Уровень 2 — слово "НДС"
  [
    'E....E....E.',
    '............',
    '.B.BB.B.BB..',
    '.B.B..B.B.B.',
    '.B.BB.B.BB..',
    '.B.B..B.B.B.',
    '.B.BB.B.BB..',
    '............',
    'WW...SS...WW',
    'WW........WW',
    '............',
    '.....P......',
    '.....X......',
  ].map((r) => r.padEnd(COLS, '.')),
  // Уровень 3 — водная преграда + стальной бункер базы
  [
    'E..E....E..E',
    '.BB.BBBB.BB.',
    '.B.........B',
    '.B.T.BB.T..B',
    '............',
    'WWWW....WWWW',
    'WWWW....WWWW',
    '............',
    '.BB.S..S.BB.',
    '.BB.S..S.BB.',
    '....S..S....',
    '.....P......',
    '.....X......',
  ].map((r) => r.padEnd(COLS, '.')),
  // Уровень 4 — слово "ИТОГО" стеной, плотнее
  [
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
    '.....P......',
    '.....X......',
  ].map((r) => r.padEnd(COLS, '.')),
  // Уровень 5 — крепость из стали вокруг базы, кирпич и вода по краям
  [
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
    '.....P......',
    '.....X......',
  ].map((r) => r.padEnd(COLS, '.')),
]

// Сансериф для HUD — цифры/счёт читаются лучше глиф-шрифта, который остаётся
// только на титульных экранах/fallback-рисовании танков (общий стиль с
// другими играми).
const HUD_FONT_FAMILY = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
// Моноширинный шрифт для глиф-рамок танков/базы (fallback, пока спрайты не
// загрузились) и титульных экранов — свой для этой игры, не общий импорт.
const GLYPH_FONT_FAMILY = 'Consolas, "JetBrains Mono", "Courier New", monospace'
const EXPLOSION_DURATION = 0.3 // сек, 3 кадра спрайт-анимации на попадание

interface Explosion {
  x: number
  y: number
  t: number
}

export class TankGame {
  private canvas: HTMLCanvasElement
  private ctx: CanvasRenderingContext2D

  private dpr = 1
  private width = 0
  private height = 0
  private tile = 24
  private boardOffsetX = 0
  private boardOffsetY = 0

  private running = false
  private rafId: number | null = null
  private lastTime = 0

  private state: GameState = 'level-intro'
  private stateTimer = 0

  private level = 1
  private score = 0
  private best: number
  private lives = 3
  private enemiesLeftToSpawn = 0
  private enemiesAlive = 0

  private grid: Tile[][] = []
  private player: Tank = { x: 0, y: 0, dir: 'up', alive: true, cooldown: 0, isEnemy: false, changeDirTimer: 0, tough: false, hp: 1 }
  private enemies: Tank[] = []
  private bullets: Bullet[] = []
  private spawnPoints: { x: number; y: number }[] = []
  private basePos: { x: number; y: number } = { x: 0, y: 0 }
  private baseAlive = true
  private enemySpawnTimer = 0
  private explosions: Explosion[] = []

  private _bg: HTMLCanvasElement | null = null
  private glyphFontFamily = GLYPH_FONT_FAMILY

  // Спрайты Kenney "Top-down Tanks Redux" (CC0) — загружаются асинхронно
  // через общий spriteLoader; пока isSpriteReady() = false, рисуем fallback
  // прямоугольник/глиф тем же методом, что до этой правки.
  private _sprites = {
    grass: loadSprite(tileGrassUrl),
    brickWall: loadSprite(brickWallUrl),
    steelWall: loadSprite(steelWallUrl),
    tree: loadSprite(treeUrl),
    bodyPlayer: loadSprite(tankBodyPlayerUrl),
    barrelPlayer: loadSprite(tankBarrelPlayerUrl),
    bodyEnemy: loadSprite(tankBodyEnemyUrl),
    barrelEnemy: loadSprite(tankBarrelEnemyUrl),
    bodyTough: loadSprite(tankBodyToughUrl),
    barrelTough: loadSprite(tankBarrelToughUrl),
    bulletPlayer: loadSprite(bulletPlayerUrl),
    bulletEnemy: loadSprite(bulletEnemyUrl),
    explosion: [loadSprite(explosion1Url), loadSprite(explosion2Url), loadSprite(explosion3Url)],
    base: loadSprite(baseUrl),
  }

  private keys = new Set<string>()
  private touchDir: Dir | null = null
  private touchFire = false

  private _padRects: { up: Rect; down: Rect; left: Rect; right: Rect; fire: Rect } | null = null
  private _gameOverBtnRect: Rect | null = null
  private _wasRunning = false
  private _onEscape: (() => void) | null = null

  private _onResize: () => void
  private _onVisibility: () => void
  private _onKeyDown: (e: KeyboardEvent) => void
  private _onKeyUp: (e: KeyboardEvent) => void
  private _onPointerDown: (e: PointerEvent) => void
  private _onPointerMove: (e: PointerEvent) => void
  private _onPointerUp: (e: PointerEvent) => void
  private _activePointers = new Map<number, 'pad' | 'fire'>()

  constructor(containerEl: HTMLElement) {
    const existing = containerEl.querySelector('canvas')
    this.canvas = existing || document.createElement('canvas')
    if (!this.canvas.parentElement) containerEl.appendChild(this.canvas)
    const ctx = this.canvas.getContext('2d')
    if (!ctx) throw new Error('TankGame: canvas 2d context unavailable')
    this.ctx = ctx

    this.best = this._loadBest()

    this._onResize = () => this._resize()
    this._onVisibility = () => {
      if (document.hidden) {
        this._wasRunning = this.running
      } else if (this._wasRunning) {
        this.lastTime = performance.now()
      }
    }
    this._onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && this._onEscape) { this._onEscape(); return }
      const blocking = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' ', 'Spacebar', 'Enter', 'w', 'a', 's', 'd', 'W', 'A', 'S', 'D']
      if (blocking.includes(e.key)) e.preventDefault()
      if (e.key === 'Enter' && this.state === 'game-over') { this._restartGame(); return }
      this.keys.add(e.key.toLowerCase())
    }
    this._onKeyUp = (e: KeyboardEvent) => {
      this.keys.delete(e.key.toLowerCase())
    }
    this._onPointerDown = (e: PointerEvent) => this._handlePointer(e, 'down')
    this._onPointerMove = (e: PointerEvent) => this._handlePointer(e, 'move')
    this._onPointerUp = (e: PointerEvent) => this._handlePointer(e, 'up')

    this._bindHandlers()
    this._resize()
    this._setupLevel(this.level)
  }

  // ---------- public API ----------

  start(): void {
    if (this.running) return
    this.running = true
    this.lastTime = performance.now()
    this.rafId = requestAnimationFrame(this._loop)
  }

  destroy(): void {
    this.running = false
    if (this.rafId != null) {
      cancelAnimationFrame(this.rafId)
      this.rafId = null
    }
    window.removeEventListener('resize', this._onResize)
    document.removeEventListener('visibilitychange', this._onVisibility)
    window.removeEventListener('keydown', this._onKeyDown)
    window.removeEventListener('keyup', this._onKeyUp)
    this.canvas.removeEventListener('pointerdown', this._onPointerDown)
    this.canvas.removeEventListener('pointermove', this._onPointerMove)
    this.canvas.removeEventListener('pointerup', this._onPointerUp)
    this.canvas.removeEventListener('pointercancel', this._onPointerUp)
    this.canvas.removeEventListener('pointerleave', this._onPointerUp)
  }

  onEscape(fn: () => void): void {
    this._onEscape = fn
  }

  // ---------- setup ----------

  private _bindHandlers(): void {
    window.addEventListener('resize', this._onResize)
    document.addEventListener('visibilitychange', this._onVisibility)
    window.addEventListener('keydown', this._onKeyDown)
    window.addEventListener('keyup', this._onKeyUp)
    this.canvas.addEventListener('pointerdown', this._onPointerDown)
    this.canvas.addEventListener('pointermove', this._onPointerMove)
    this.canvas.addEventListener('pointerup', this._onPointerUp)
    this.canvas.addEventListener('pointercancel', this._onPointerUp)
    this.canvas.addEventListener('pointerleave', this._onPointerUp)
  }

  private _loadBest(): number {
    try {
      const v = localStorage.getItem('gala_tank_best')
      return v ? parseInt(v, 10) || 0 : 0
    } catch {
      return 0
    }
  }

  private _saveBest(): void {
    try {
      localStorage.setItem('gala_tank_best', String(this.best))
    } catch {
      /* ignore */
    }
  }

  private _resize(): void {
    const parent = this.canvas.parentElement
    if (!parent) return
    const rect = parent.getBoundingClientRect()
    this.dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1))
    this.width = Math.max(1, Math.round(rect.width))
    this.height = Math.max(1, Math.round(rect.height))
    this.canvas.width = Math.round(this.width * this.dpr)
    this.canvas.height = Math.round(this.height * this.dpr)
    // DPR-фикс как в BrickGame._resize: canvas.width/height = css*dpr, плюс
    // canvas.style.width/height в css px — иначе canvas раздувается на
    // экранах с devicePixelRatio > 1.
    this.canvas.style.width = `${this.width}px`
    this.canvas.style.height = `${this.height}px`
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    this._bg = this._buildBackground(this.width, this.height, this.dpr)

    const hudH = 46
    const padH = this._isTouch() ? 96 : 0
    const availW = this.width - 16
    const availH = this.height - hudH - padH - 10
    this.tile = Math.max(10, Math.floor(Math.min(availW / COLS, availH / ROWS)))
    this.boardOffsetX = Math.round((this.width - this.tile * COLS) / 2)
    this.boardOffsetY = hudH

    this._layoutTouchPad()
  }

  // Фон под всей канвой (не только доской) — тот же травяной тайл Kenney,
  // что и доска, но затемнённый полупрозрачной тёмной заливкой, чтобы доска
  // (светлее) читалась на нём отдельным слоем. Раньше здесь был общий
  // чёрно-белый "документный" фон (docBackground.ts) — не подходит цветным
  // спрайтам. Строится один раз на resize, как и доска, и просто копируется
  // в каждом кадре (ctx.drawImage), без пересчёта.
  private _buildBackground(width: number, height: number, dpr: number): HTMLCanvasElement {
    const off = document.createElement('canvas')
    const w = Math.max(1, width)
    const h = Math.max(1, height)
    off.width = Math.max(1, Math.round(w * dpr))
    off.height = Math.max(1, Math.round(h * dpr))
    const c = off.getContext('2d')
    if (!c) return off
    c.setTransform(dpr, 0, 0, dpr, 0, 0)

    const grass = this._sprites.grass
    if (isSpriteReady(grass)) {
      const size = 48
      for (let y = 0; y < h; y += size) {
        for (let x = 0; x < w; x += size) c.drawImage(grass, x, y, size, size)
      }
      c.fillStyle = 'rgba(0,0,0,0.45)'
      c.fillRect(0, 0, w, h)
    } else {
      c.fillStyle = '#2f7d4a'
      c.fillRect(0, 0, w, h)
    }
    return off
  }

  private _isTouch(): boolean {
    return 'ontouchstart' in window || navigator.maxTouchPoints > 0
  }

  private _layoutTouchPad(): void {
    if (!this._isTouch()) { this._padRects = null; return }
    const pad = 12
    const btn = 40
    const baseY = this.height - btn * 2 - pad * 2
    const padX = pad
    this._padRects = {
      up: { x: padX + btn, y: baseY, w: btn, h: btn },
      left: { x: padX, y: baseY + btn, w: btn, h: btn },
      down: { x: padX + btn, y: baseY + btn, w: btn, h: btn },
      right: { x: padX + btn * 2, y: baseY + btn, w: btn, h: btn },
      fire: { x: this.width - pad - btn * 1.6, y: baseY + btn / 2, w: btn * 1.6, h: btn * 1.6 },
    }
  }

  private _inRect(x: number, y: number, r: Rect): boolean {
    return x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h
  }

  private _handlePointer(e: PointerEvent, phase: 'down' | 'move' | 'up'): void {
    const rect = this.canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top

    if (this.state === 'game-over' && phase === 'down') {
      const r = this._gameOverBtnRect
      if (r && this._inRect(x, y, r)) { this._restartGame(); return }
    }

    const pad = this._padRects
    if (phase === 'up') {
      const kind = this._activePointers.get(e.pointerId)
      this._activePointers.delete(e.pointerId)
      if (kind === 'fire') {
        if (![...this._activePointers.values()].includes('fire')) this.touchFire = false
      } else if (kind === 'pad') {
        if (![...this._activePointers.values()].includes('pad')) this.touchDir = null
      }
      return
    }

    if (!pad) return
    if (this._inRect(x, y, pad.fire)) {
      this._activePointers.set(e.pointerId, 'fire')
      this.touchFire = true
      return
    }
    let dir: Dir | null = null
    if (this._inRect(x, y, pad.up)) dir = 'up'
    else if (this._inRect(x, y, pad.down)) dir = 'down'
    else if (this._inRect(x, y, pad.left)) dir = 'left'
    else if (this._inRect(x, y, pad.right)) dir = 'right'
    if (dir) {
      this._activePointers.set(e.pointerId, 'pad')
      this.touchDir = dir
    }
  }

  // ---------- level ----------

  private _tileMap(level: number): string[] {
    const idx = Math.min(LEVEL_MAPS.length - 1, Math.max(0, level - 1))
    return LEVEL_MAPS[idx] ?? LEVEL_MAPS[0]!
  }

  private _setupLevel(level: number): void {
    const rows = this._tileMap(level)
    this.grid = []
    this.spawnPoints = []
    this.enemies = []
    this.bullets = []
    this.explosions = []
    this.baseAlive = true

    for (let y = 0; y < ROWS; y++) {
      const row: Tile[] = []
      const line = rows[y] ?? ''.padEnd(COLS, '.')
      for (let x = 0; x < COLS; x++) {
        const ch = line[x] ?? '.'
        let type: TileType = 'empty'
        if (ch === 'B') type = 'brick'
        else if (ch === 'S') type = 'steel'
        else if (ch === 'W') type = 'water'
        else if (ch === 'T') type = 'tree'
        else if (ch === 'X') type = 'base'
        row.push({ type, damage: 0 })
        if (ch === 'E') this.spawnPoints.push({ x, y })
        if (ch === 'P') { this.player.x = x; this.player.y = y }
        if (ch === 'X') this.basePos = { x, y }
      }
      this.grid.push(row)
    }

    this.player.alive = true
    this.player.dir = 'up'
    this.player.cooldown = 0

    this.enemiesLeftToSpawn = ENEMIES_PER_LEVEL[Math.min(ENEMIES_PER_LEVEL.length - 1, level - 1)] ?? 10
    this.enemiesAlive = 0
    this.enemySpawnTimer = 0.4
  }

  private _restartGame(): void {
    this.level = 1
    this.score = 0
    this.lives = 3
    this.state = 'level-intro'
    this.stateTimer = 0
    this._setupLevel(this.level)
  }

  private _nextLevel(): void {
    this.level = Math.min(MAX_LEVELS, this.level === MAX_LEVELS ? 1 : this.level + 1)
    this.state = 'level-intro'
    this.stateTimer = 0
    this._setupLevel(this.level)
  }

  // ---------- helpers: grid/world ----------

  private _tileAt(gx: number, gy: number): Tile | null {
    if (gx < 0 || gy < 0 || gx >= COLS || gy >= ROWS) return null
    return this.grid[gy]?.[gx] ?? null
  }

  private _blocksMovement(tile: Tile | null): boolean {
    if (!tile) return true
    return tile.type === 'steel' || tile.type === 'water' || tile.type === 'base' || (tile.type === 'brick' && tile.damage < 4)
  }

  private _blocksBullet(tile: Tile | null): boolean {
    if (!tile) return true
    if (tile.type === 'tree') return false
    return tile.type === 'steel' || tile.type === 'base' || (tile.type === 'brick' && tile.damage < 4)
  }

  // Прямоугольник танка в пикселях мира (без смещения доски) — единственное
  // место, где считается хитбокс танка, все проверки читают отсюда.
  private _tankRect(t: Tank): Rect {
    const size = this.tile * 0.92
    return { x: t.x * this.tile + (this.tile - size) / 2, y: t.y * this.tile + (this.tile - size) / 2, w: size, h: size }
  }

  private _rectsOverlap(a: Rect, b: Rect): boolean {
    return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
  }

  private _tankBlockedByTanks(t: Tank, nx: number, ny: number): boolean {
    const probe: Tank = { ...t, x: nx, y: ny }
    const r = this._tankRect(probe)
    if (this.player.alive && this.player !== t) {
      if (this._rectsOverlap(r, this._tankRect(this.player))) return true
    }
    for (const e of this.enemies) {
      if (e === t || !e.alive) continue
      if (this._rectsOverlap(r, this._tankRect(e))) return true
    }
    return false
  }

  // Любая клетка, перекрытая прямоугольником танка в новой позиции, должна
  // пропускать движение — единая проверка для игрока и врагов.
  private _tileBlocksAt(nx: number, ny: number): boolean {
    const size = this.tile * 0.92
    const left = nx * this.tile + (this.tile - size) / 2
    const top = ny * this.tile + (this.tile - size) / 2
    const gx0 = Math.floor(left / this.tile)
    const gx1 = Math.floor((left + size - 0.01) / this.tile)
    const gy0 = Math.floor(top / this.tile)
    const gy1 = Math.floor((top + size - 0.01) / this.tile)
    for (let gy = gy0; gy <= gy1; gy++) {
      for (let gx = gx0; gx <= gx1; gx++) {
        if (this._blocksMovement(this._tileAt(gx, gy))) return true
      }
    }
    return false
  }

  // ---------- update ----------

  private _loop = (now: number): void => {
    if (!this.running) return
    const dt = Math.min(0.05, (now - this.lastTime) / 1000)
    this.lastTime = now

    if (!document.hidden) {
      this._update(dt)
    }
    this._render()

    this.rafId = requestAnimationFrame(this._loop)
  }

  private _update(dt: number): void {
    if (this.state === 'level-intro') {
      this.stateTimer += dt
      if (this.stateTimer > 1.1) {
        this.stateTimer = 0
        this.state = 'playing'
      }
      return
    }

    if (this.state === 'level-complete') {
      this.stateTimer += dt
      if (this.stateTimer > 1.3) {
        this.stateTimer = 0
        this._nextLevel()
      }
      return
    }

    if (this.state === 'game-over') return

    this._updatePlayer(dt)
    this._updateEnemies(dt)
    this._updateBullets(dt)
    this._updateExplosions(dt)
    this._spawnEnemiesIfNeeded(dt)

    if (!this.baseAlive && this.player.alive) {
      this._onBaseDestroyed()
    }

    if (this.enemiesLeftToSpawn === 0 && this.enemiesAlive === 0 && this.state === 'playing') {
      this.state = 'level-complete'
      this.stateTimer = 0
      this.score += 500
    }
  }

  private _wantedDir(): Dir | null {
    if (this.touchDir) return this.touchDir
    if (this.keys.has('arrowup') || this.keys.has('w')) return 'up'
    if (this.keys.has('arrowdown') || this.keys.has('s')) return 'down'
    if (this.keys.has('arrowleft') || this.keys.has('a')) return 'left'
    if (this.keys.has('arrowright') || this.keys.has('d')) return 'right'
    return null
  }

  private _dirVector(dir: Dir): { dx: number; dy: number } {
    if (dir === 'up') return { dx: 0, dy: -1 }
    if (dir === 'down') return { dx: 0, dy: 1 }
    if (dir === 'left') return { dx: -1, dy: 0 }
    return { dx: 1, dy: 0 }
  }

  private _updatePlayer(dt: number): void {
    const p = this.player
    if (!p.alive) return

    const wanted = this._wantedDir()
    if (wanted) {
      p.dir = wanted
      const { dx, dy } = this._dirVector(wanted)
      const nx = p.x + dx * PLAYER_SPEED * dt / this.tile
      const ny = p.y + dy * PLAYER_SPEED * dt / this.tile
      if (!this._tileBlocksAt(nx, ny) && !this._tankBlockedByTanks(p, nx, ny)) {
        p.x = Math.max(0, Math.min(COLS - 1, nx))
        p.y = Math.max(0, Math.min(ROWS - 1, ny))
      }
    }

    p.cooldown = Math.max(0, p.cooldown - dt)
    const wantsFire = this.keys.has(' ') || this.keys.has('spacebar') || this.keys.has('enter') || this.touchFire
    if (wantsFire && p.cooldown <= 0) {
      this._fireBullet(p, 'player')
      p.cooldown = PLAYER_FIRE_COOLDOWN
    }
  }

  private _fireBullet(t: Tank, owner: 'player' | 'enemy'): void {
    // не больше одного живого снаряда от игрока — ближе к оригинальной
    // механике жанра (Projectile.cs первоисточника снаряд один раз
    // инстанцируется и сам уничтожается при столкновении — здесь это
    // ограничение на игрока, у врагов снарядов чуть больше для темпа игры).
    if (owner === 'player' && this.bullets.some((b) => b.alive && b.owner === 'player')) return
    const { dx, dy } = this._dirVector(t.dir)
    const speed = owner === 'player' ? BULLET_SPEED_PLAYER : BULLET_SPEED_ENEMY
    this.bullets.push({
      x: (t.x + 0.5) * this.tile + dx * this.tile * 0.4,
      y: (t.y + 0.5) * this.tile + dy * this.tile * 0.4,
      dir: t.dir,
      owner,
      speed,
      alive: true,
    })
  }

  private _spawnEnemiesIfNeeded(dt: number): void {
    this.enemySpawnTimer -= dt
    if (this.enemySpawnTimer > 0) return
    if (this.enemiesLeftToSpawn <= 0) return
    if (this.enemiesAlive >= MAX_ENEMIES_ON_FIELD) { this.enemySpawnTimer = 0.4; return }
    if (this.spawnPoints.length === 0) return

    const sp = this.spawnPoints[Math.floor(Math.random() * this.spawnPoints.length)]!
    const probe: Tank = { x: sp.x, y: sp.y, dir: 'down', alive: true, cooldown: 0, isEnemy: true, changeDirTimer: 0, tough: false, hp: 1 }
    if (this._tankBlockedByTanks(probe, sp.x, sp.y)) { this.enemySpawnTimer = 0.3; return }

    const tough = this.enemiesLeftToSpawn % 5 === 0
    this.enemies.push({
      x: sp.x,
      y: sp.y,
      dir: 'down',
      alive: true,
      cooldown: ENEMY_FIRE_COOLDOWN_MIN + Math.random() * (ENEMY_FIRE_COOLDOWN_MAX - ENEMY_FIRE_COOLDOWN_MIN),
      isEnemy: true,
      changeDirTimer: 0.3 + Math.random() * 0.6,
      tough,
      hp: tough ? 2 : 1,
    })
    this.enemiesLeftToSpawn--
    this.enemiesAlive++
    this.enemySpawnTimer = 0.55 + Math.random() * 0.4
  }

  // ИИ врага: едет по текущему направлению, на таймере/препятствии выбирает
  // новое — с уклоном в сторону игрока (targeting) пополам со случайным
  // (аналог классического поведения жанра: часть врагов преследует, часть
  // блуждает) + периодически стреляет в своём направлении.
  private _updateEnemies(dt: number): void {
    for (const e of this.enemies) {
      if (!e.alive) continue

      e.changeDirTimer -= dt
      const { dx, dy } = this._dirVector(e.dir)
      const speed = ENEMY_SPEED_BASE + (this.level - 1) * 6
      const nx = e.x + dx * speed * dt / this.tile
      const ny = e.y + dy * speed * dt / this.tile
      const blocked = this._tileBlocksAt(nx, ny) || this._tankBlockedByTanks(e, nx, ny) || nx < 0 || nx > COLS - 1 || ny < 0 || ny > ROWS - 1

      if (!blocked) {
        e.x = nx
        e.y = ny
      }

      if (blocked || e.changeDirTimer <= 0) {
        e.dir = this._pickEnemyDirection(e)
        e.changeDirTimer = 0.6 + Math.random() * 1.2
      }

      e.cooldown -= dt
      if (e.cooldown <= 0) {
        this._fireBullet(e, 'enemy')
        e.cooldown = ENEMY_FIRE_COOLDOWN_MIN + Math.random() * (ENEMY_FIRE_COOLDOWN_MAX - ENEMY_FIRE_COOLDOWN_MIN)
      }
    }
    this.enemies = this.enemies.filter((e) => e.alive || true)
  }

  private _pickEnemyDirection(e: Tank): Dir {
    // 55% — в сторону игрока/базы по доминирующей оси, иначе случайно;
    // всегда проверяем, что выбранное направление не ведёт прямо в стену.
    const targetX = this.player.alive ? this.player.x : this.basePos.x
    const targetY = this.player.alive ? this.player.y : this.basePos.y
    const candidates: Dir[] = [...DIRS]
    const scored = candidates
      .map((dir) => {
        const { dx, dy } = this._dirVector(dir)
        const nx = e.x + dx
        const ny = e.y + dy
        const free = !this._tileBlocksAt(nx, ny) && nx >= 0 && nx <= COLS - 1 && ny >= 0 && ny <= ROWS - 1
        const towardScore = -(Math.abs(targetX - nx) + Math.abs(targetY - ny))
        return { dir, free, towardScore }
      })
      .filter((c) => c.free)

    if (scored.length === 0) return DIRS[Math.floor(Math.random() * DIRS.length)]!
    if (Math.random() < 0.55) {
      scored.sort((a, b) => b.towardScore - a.towardScore)
      return scored[0]!.dir
    }
    return scored[Math.floor(Math.random() * scored.length)]!.dir
  }

  private _spawnExplosion(gx: number, gy: number): void {
    this.explosions.push({ x: (gx + 0.5) * this.tile, y: (gy + 0.5) * this.tile, t: 0 })
  }

  private _updateExplosions(dt: number): void {
    for (const ex of this.explosions) ex.t += dt
    this.explosions = this.explosions.filter((ex) => ex.t < EXPLOSION_DURATION)
  }

  private _updateBullets(dt: number): void {
    for (const b of this.bullets) {
      if (!b.alive) continue
      const { dx, dy } = this._dirVector(b.dir)
      b.x += dx * b.speed * dt
      b.y += dy * b.speed * dt

      const boardW = COLS * this.tile
      const boardH = ROWS * this.tile
      if (b.x < 0 || b.x > boardW || b.y < 0 || b.y > boardH) { b.alive = false; continue }

      const gx = Math.floor(b.x / this.tile)
      const gy = Math.floor(b.y / this.tile)
      const tile = this._tileAt(gx, gy)
      if (tile && this._blocksBullet(tile)) {
        if (tile.type === 'brick') {
          tile.damage = Math.min(4, tile.damage + 1)
          if (tile.damage >= 4) tile.type = 'brick' // остаётся пустое место, damage=4 трактуется как "нет тайла"
        } else if (tile.type === 'base') {
          this.baseAlive = false
          this._spawnExplosion(gx, gy)
        }
        b.alive = false
        continue
      }

      // снаряд врага по игроку
      if (b.owner === 'enemy' && this.player.alive) {
        const pr = this._tankRect(this.player)
        if (b.x >= pr.x && b.x <= pr.x + pr.w && b.y >= pr.y && b.y <= pr.y + pr.h) {
          b.alive = false
          this._onPlayerHit()
          continue
        }
      }

      // снаряд игрока по врагам
      if (b.owner === 'player') {
        for (const e of this.enemies) {
          if (!e.alive) continue
          const er = this._tankRect(e)
          if (b.x >= er.x && b.x <= er.x + er.w && b.y >= er.y && b.y <= er.y + er.h) {
            b.alive = false
            e.hp--
            if (e.hp <= 0) {
              e.alive = false
              this.enemiesAlive = Math.max(0, this.enemiesAlive - 1)
              this.score += e.tough ? 300 : 100
              this._spawnExplosion(e.x, e.y)
            }
            break
          }
        }
      }
    }
    this.bullets = this.bullets.filter((b) => b.alive)
    this.enemies = this.enemies.filter((e) => e.alive)
  }

  private _onPlayerHit(): void {
    this._spawnExplosion(this.player.x, this.player.y)
    this.player.alive = false
    this.lives = Math.max(0, this.lives - 1)
    if (this.lives <= 0) {
      this._gameOver()
      return
    }
    // возрождение на старте карты
    const rows = this._tileMap(this.level)
    for (let y = 0; y < ROWS; y++) {
      const line = rows[y] ?? ''
      const idx = line.indexOf('P')
      if (idx >= 0) { this.player.x = idx; this.player.y = y; break }
    }
    this.player.alive = true
    this.player.dir = 'up'
  }

  private _onBaseDestroyed(): void {
    this._gameOver()
  }

  private _gameOver(): void {
    this.best = Math.max(this.best, this.score)
    this._saveBest()
    this.state = 'game-over'
  }

  // ---------- rendering ----------

  private _render(): void {
    const ctx = this.ctx
    const w = this.width
    const h = this.height

    ctx.clearRect(0, 0, w, h)
    if (this._bg && this._bg.width > 0) {
      ctx.drawImage(this._bg, 0, 0, w, h)
    } else {
      ctx.fillStyle = '#2f7d4a'
      ctx.fillRect(0, 0, w, h)
    }

    ctx.save()
    ctx.translate(this.boardOffsetX, this.boardOffsetY)
    this._drawGround(ctx)
    this._drawBoard(ctx)
    this._drawTanks(ctx)
    this._drawBullets(ctx)
    this._drawExplosions(ctx)
    ctx.restore()

    this._drawHud(ctx, w)
    if (this._padRects) this._drawTouchPad(ctx)

    if (this.state === 'level-intro') this._drawCenterText(ctx, w, h, `УРОВЕНЬ ${this.level}`, 'стрелки/WASD — движение, пробел — огонь')
    if (this.state === 'level-complete') this._drawCenterText(ctx, w, h, 'УРОВЕНЬ ПРОЙДЕН', '')
    if (this.state === 'game-over') this._drawGameOver(ctx, w, h)
  }

  // Направление танка/пули → угол поворота canvas (по часовой от "вверх" —
  // спрайты Kenney по умолчанию смотрят вверх, см. sprites/tank/).
  private _dirAngle(dir: Dir): number {
    if (dir === 'up') return 0
    if (dir === 'right') return Math.PI / 2
    if (dir === 'down') return Math.PI
    return -Math.PI / 2 // left
  }

  // Земля — травяной тайл Kenney под всей доской, рисуется первым слоем.
  private _drawGround(ctx: CanvasRenderingContext2D): void {
    const img = this._sprites.grass
    const t = this.tile
    if (isSpriteReady(img)) {
      for (let y = 0; y < ROWS; y++) {
        for (let x = 0; x < COLS; x++) ctx.drawImage(img, x * t, y * t, t, t)
      }
    } else {
      ctx.fillStyle = '#eef3e8'
      ctx.fillRect(0, 0, COLS * t, ROWS * t)
    }
  }

  private _drawBoard(ctx: CanvasRenderingContext2D): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    const t = this.tile
    const brick = this._sprites.brickWall
    const steel = this._sprites.steelWall
    const base = this._sprites.base
    for (let y = 0; y < ROWS; y++) {
      for (let x = 0; x < COLS; x++) {
        const tile = this.grid[y]?.[x]
        if (!tile || tile.type === 'empty') continue
        const cx = x * t + t / 2
        const cy = y * t + t / 2
        if (tile.type === 'brick' && tile.damage < 4) {
          // четверти кирпича "выбиваются" по мере damage (0..3) — клипуем
          // по уцелевшим четвертям и рисуем в них полный тайл текстуры,
          // чтобы рисунок не "сжимался", а честно обрезался.
          const half = t / 2
          const quads: Array<[number, number]> = [[0, 0], [half, 0], [0, half], [half, half]]
          ctx.save()
          ctx.beginPath()
          let any = false
          for (let i = 0; i < 4; i++) {
            if (i < tile.damage) continue
            any = true
            ctx.rect(x * t + (quads[i]?.[0] ?? 0), y * t + (quads[i]?.[1] ?? 0), half, half)
          }
          if (any) {
            ctx.clip()
            if (isSpriteReady(brick)) {
              ctx.drawImage(brick, x * t, y * t, t, t)
            } else {
              ctx.fillStyle = '#8b5a2b'
              ctx.fillRect(x * t, y * t, t, t)
            }
          }
          ctx.restore()
        } else if (tile.type === 'steel') {
          if (isSpriteReady(steel)) {
            ctx.drawImage(steel, x * t, y * t, t, t)
          } else {
            ctx.fillStyle = '#777777'
            ctx.fillRect(x * t, y * t, t, t)
          }
        } else if (tile.type === 'water') {
          // в наборе Kenney нет отдельного тайла воды — заливка + светлая
          // волна поверх (разрешено заданием как альтернатива спрайту).
          ctx.fillStyle = '#3f7fc4'
          ctx.fillRect(x * t, y * t, t, t)
          ctx.strokeStyle = 'rgba(255,255,255,0.55)'
          ctx.lineWidth = Math.max(1, t * 0.07)
          ctx.beginPath()
          ctx.moveTo(x * t + t * 0.1, cy - t * 0.08)
          ctx.quadraticCurveTo(cx, cy + t * 0.12, x * t + t * 0.9, cy - t * 0.08)
          ctx.stroke()
        } else if (tile.type === 'base') {
          if (isSpriteReady(base)) {
            ctx.save()
            if (!this.baseAlive) ctx.globalAlpha = 0.35
            ctx.drawImage(base, x * t + t * 0.08, y * t + t * 0.08, t * 0.84, t * 0.84)
            ctx.restore()
          } else {
            ctx.font = `700 ${Math.max(8, t * 0.85)}px ${this.glyphFontFamily}`
            ctx.fillStyle = this.baseAlive ? '#111111' : '#bbbbbb'
            ctx.fillText('★', cx, cy + 1)
          }
        }
      }
    }
    ctx.restore()
  }

  private _drawTrees(ctx: CanvasRenderingContext2D): void {
    const img = this._sprites.tree
    const t = this.tile
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    for (let y = 0; y < ROWS; y++) {
      for (let x = 0; x < COLS; x++) {
        const tile = this.grid[y]?.[x]
        if (!tile || tile.type !== 'tree') continue
        if (isSpriteReady(img)) {
          const size = t * 1.18
          ctx.drawImage(img, x * t + t / 2 - size / 2, y * t + t / 2 - size / 2, size, size)
        } else {
          ctx.font = `700 ${Math.max(8, t * 0.95)}px ${this.glyphFontFamily}`
          ctx.fillStyle = '#999999'
          ctx.fillText('♣', x * t + t / 2, y * t + t / 2 + 1)
        }
      }
    }
    ctx.restore()
  }

  private _tankGlyphBlock(dir: Dir): string[] {
    // 3×3 глиф-блок — fallback, пока PNG-спрайты ещё не загрузились
    if (dir === 'up') return ['╔▲╗', '╠█╣', '╚╩╝']
    if (dir === 'down') return ['╔╦╗', '╠█╣', '╚▼╝']
    if (dir === 'left') return ['╔╦╗', '◄█╣', '╚╩╝']
    return ['╔╦╗', '╠█►', '╚╩╝']
  }

  private _drawTankFallback(ctx: CanvasRenderingContext2D, t: Tank, color: string): void {
    const r = this._tankRect(t)
    const lines = this._tankGlyphBlock(t.dir)
    const fontPx = Math.max(6, r.w / 3.1)
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.font = `700 ${fontPx}px ${this.glyphFontFamily}`
    ctx.fillStyle = color
    const lineH = r.h / 3
    for (let i = 0; i < 3; i++) {
      const line = lines[i] ?? ''
      ctx.fillText(line, r.x + r.w / 2, r.y + lineH * i + lineH / 2 + 1)
    }
    ctx.restore()
  }

  // Цветной танк Kenney: корпус + ствол, повёрнуты на направление движения.
  // Пока картинки не готовы — старый чёрно-белый глиф-блок, игра не ждёт.
  private _drawTankSprite(ctx: CanvasRenderingContext2D, t: Tank, bodyImg: HTMLImageElement, barrelImg: HTMLImageElement, fallbackColor: string): void {
    if (!isSpriteReady(bodyImg) || !isSpriteReady(barrelImg)) {
      this._drawTankFallback(ctx, t, fallbackColor)
      return
    }
    const r = this._tankRect(t)
    const cx = r.x + r.w / 2
    const cy = r.y + r.h / 2
    const size = r.w
    ctx.save()
    ctx.translate(cx, cy)
    ctx.rotate(this._dirAngle(t.dir))
    ctx.drawImage(bodyImg, -size / 2, -size / 2, size, size)
    const barrelW = size * 0.22
    const barrelH = size * 0.68
    ctx.drawImage(barrelImg, -barrelW / 2, -size * 0.58, barrelW, barrelH)
    ctx.restore()
  }

  private _drawTanks(ctx: CanvasRenderingContext2D): void {
    for (const e of this.enemies) {
      if (!e.alive) continue
      if (e.tough) this._drawTankSprite(ctx, e, this._sprites.bodyTough, this._sprites.barrelTough, '#000000')
      else this._drawTankSprite(ctx, e, this._sprites.bodyEnemy, this._sprites.barrelEnemy, '#555555')
    }
    if (this.player.alive) this._drawTankSprite(ctx, this.player, this._sprites.bodyPlayer, this._sprites.barrelPlayer, '#111111')
    this._drawTrees(ctx) // кусты рисуются над танками — перекрывают силуэт
  }

  private _drawBullets(ctx: CanvasRenderingContext2D): void {
    const playerImg = this._sprites.bulletPlayer
    const enemyImg = this._sprites.bulletEnemy
    for (const b of this.bullets) {
      if (!b.alive) continue
      const img = b.owner === 'player' ? playerImg : enemyImg
      if (isSpriteReady(img)) {
        const w = this.tile * 0.22
        const h = this.tile * 0.5
        ctx.save()
        ctx.translate(b.x, b.y)
        ctx.rotate(this._dirAngle(b.dir))
        ctx.drawImage(img, -w / 2, -h / 2, w, h)
        ctx.restore()
      } else {
        ctx.save()
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.font = `700 ${Math.max(8, this.tile * 0.5)}px ${this.glyphFontFamily}`
        ctx.fillStyle = '#111111'
        ctx.fillText('•', b.x, b.y + 1)
        ctx.restore()
      }
    }
  }

  // Короткая анимация взрыва (3 кадра Kenney) на попадании по танку/базе.
  private _drawExplosions(ctx: CanvasRenderingContext2D): void {
    const frames = this._sprites.explosion
    if (frames.length === 0) return
    for (const ex of this.explosions) {
      const progress = Math.min(0.999, ex.t / EXPLOSION_DURATION)
      const img = frames[Math.floor(progress * frames.length)] ?? frames[0]
      if (!img || !isSpriteReady(img)) continue
      const size = this.tile * 1.3
      ctx.save()
      ctx.globalAlpha = Math.max(0.15, 1 - progress)
      ctx.drawImage(img, ex.x - size / 2, ex.y - size / 2, size, size)
      ctx.restore()
    }
  }

  private _drawHud(ctx: CanvasRenderingContext2D, w: number): void {
    // Читаемый сансериф для HUD (счёт/жизни/враги) — белый текст с тёмной
    // тенью, как в DuckShootGame, т.к. фон под HUD теперь тёмно-зелёная
    // трава, а не светлый "документный" фон.
    ctx.save()
    ctx.font = `700 13px ${HUD_FONT_FAMILY}`
    ctx.shadowColor = 'rgba(0,0,0,0.75)'
    ctx.shadowBlur = 3
    ctx.shadowOffsetY = 1
    ctx.fillStyle = '#ffffff'
    ctx.textAlign = 'left'
    ctx.fillText(`УРОВЕНЬ ${this.level}   ОЧКИ ${this.score}`, 14, 22)
    ctx.textAlign = 'right'
    ctx.fillText(`РЕКОРД ${this.best}`, w - 14, 22)
    ctx.restore()

    ctx.save()
    ctx.font = `700 13px ${HUD_FONT_FAMILY}`
    ctx.shadowColor = 'rgba(0,0,0,0.75)'
    ctx.shadowBlur = 3
    ctx.shadowOffsetY = 1
    ctx.textAlign = 'left'
    ctx.fillStyle = '#ffffff'
    let hearts = ''
    for (let i = 0; i < 3; i++) hearts += (i < this.lives ? '♥' : '♡') + ' '
    ctx.fillText(`ЖИЗНИ ${hearts.trim()}`, 14, 42)

    ctx.fillText('ВРАГИ', 150, 42)
    const labelW = ctx.measureText('ВРАГИ').width
    const iconSize = 13
    const iconGap = 3
    const iconStartX = 150 + labelW + 8
    const remaining = this.enemiesLeftToSpawn + this.enemiesAlive
    const maxIcons = Math.max(1, Math.min(6, Math.floor((w - iconStartX - 40) / (iconSize + iconGap))))
    const shown = Math.min(maxIcons, remaining)
    const bodyImg = this._sprites.bodyEnemy
    for (let i = 0; i < shown; i++) {
      const ix = iconStartX + i * (iconSize + iconGap)
      if (isSpriteReady(bodyImg)) {
        ctx.drawImage(bodyImg, ix, 42 - iconSize / 2 - 1, iconSize, iconSize)
      } else {
        ctx.fillStyle = '#eeeeee'
        ctx.fillRect(ix, 42 - iconSize / 2 - 1, iconSize, iconSize)
        ctx.fillStyle = '#ffffff'
      }
    }
    if (remaining > shown) {
      ctx.fillText(`+${remaining - shown}`, iconStartX + shown * (iconSize + iconGap) + 2, 42)
    }
    ctx.restore()
  }

  private _drawTouchPad(ctx: CanvasRenderingContext2D): void {
    const pad = this._padRects
    if (!pad) return
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.font = `700 16px ${this.glyphFontFamily}`
    const draw = (r: Rect, label: string, active: boolean) => {
      ctx.fillStyle = active ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.12)'
      ctx.fillRect(r.x, r.y, r.w, r.h)
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 1
      ctx.strokeRect(r.x, r.y, r.w, r.h)
      ctx.shadowColor = 'rgba(0,0,0,0.75)'
      ctx.shadowBlur = 3
      ctx.fillStyle = '#ffffff'
      ctx.fillText(label, r.x + r.w / 2, r.y + r.h / 2 + 1)
      ctx.shadowBlur = 0
    }
    draw(pad.up, '▲', this.touchDir === 'up')
    draw(pad.down, '▼', this.touchDir === 'down')
    draw(pad.left, '◄', this.touchDir === 'left')
    draw(pad.right, '►', this.touchDir === 'right')
    draw(pad.fire, '●', this.touchFire)
    ctx.restore()
  }

  private _drawCenterText(ctx: CanvasRenderingContext2D, w: number, h: number, title: string, subtitle: string): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.shadowColor = 'rgba(0,0,0,0.75)'
    ctx.shadowBlur = 4
    ctx.shadowOffsetY = 1
    if (title) {
      ctx.fillStyle = '#ffffff'
      ctx.font = `700 26px ${this.glyphFontFamily}`
      ctx.fillText(title.toUpperCase(), w / 2, h / 2 - 8)
    }
    if (subtitle) {
      ctx.font = `13px ${this.glyphFontFamily}`
      ctx.fillStyle = '#eeeeee'
      ctx.fillText(subtitle, w / 2, h / 2 + (title ? 18 : 0))
    }
    ctx.restore()
  }

  private _drawGameOver(ctx: CanvasRenderingContext2D, w: number, h: number): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.shadowColor = 'rgba(0,0,0,0.75)'
    ctx.shadowBlur = 4
    ctx.shadowOffsetY = 1
    ctx.fillStyle = '#ffffff'
    ctx.font = `700 24px ${this.glyphFontFamily}`
    ctx.fillText('ИГРА ОКОНЧЕНА', w / 2, h / 2 - 30)
    ctx.font = `14px ${this.glyphFontFamily}`
    ctx.fillText(`ОЧКИ ${this.score}   РЕКОРД ${this.best}`, w / 2, h / 2 - 4)

    const btnW = 160, btnH = 36
    const bx = w / 2 - btnW / 2, by = h / 2 + 16
    ctx.strokeStyle = '#ffffff'
    ctx.lineWidth = 1
    ctx.strokeRect(bx, by, btnW, btnH)
    ctx.fillStyle = '#ffffff'
    ctx.font = `700 14px ${this.glyphFontFamily}`
    ctx.fillText('[ ЕЩЁ РАЗ ]', w / 2, by + btnH / 2 + 5)
    ctx.restore()

    this._gameOverBtnRect = { x: bx, y: by, w: btnW, h: btnH }
  }
}
