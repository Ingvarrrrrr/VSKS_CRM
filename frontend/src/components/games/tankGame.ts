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
// спроектированы заново под наш чёрно-белый "документный" канвас-стиль —
// общий с BrickGame/DuckShootGame (см. docBackground.ts).
//
// Карты уровней, текстуры, звук и названия — свои; оригинальные стадии/ассеты
// Namco (которых в этом Unity-репо и не было) не используются. Торговая марка
// держателя классической игры жанра в UI не используется — см. ПРАВИЛО ниже.
// UI-имя игры — «Танчики».

import { buildDocumentBackground, DOC_BG_FONT_FAMILY } from './docBackground'

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

  private _docBg: HTMLCanvasElement | null = null
  private glyphFontFamily = DOC_BG_FONT_FAMILY

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
    this._docBg = buildDocumentBackground(this.width, this.height, this.dpr)

    const hudH = 46
    const padH = this._isTouch() ? 96 : 0
    const availW = this.width - 16
    const availH = this.height - hudH - padH - 10
    this.tile = Math.max(10, Math.floor(Math.min(availW / COLS, availH / ROWS)))
    this.boardOffsetX = Math.round((this.width - this.tile * COLS) / 2)
    this.boardOffsetY = hudH

    this._layoutTouchPad()
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
    if (this._docBg && this._docBg.width > 0) {
      ctx.drawImage(this._docBg, 0, 0, w, h)
    } else {
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, w, h)
    }

    ctx.save()
    ctx.translate(this.boardOffsetX, this.boardOffsetY)
    this._drawBoard(ctx)
    this._drawTanks(ctx)
    this._drawBullets(ctx)
    ctx.restore()

    this._drawHud(ctx, w)
    if (this._padRects) this._drawTouchPad(ctx)

    if (this.state === 'level-intro') this._drawCenterText(ctx, w, h, `УРОВЕНЬ ${this.level}`, 'стрелки/WASD — движение, пробел — огонь')
    if (this.state === 'level-complete') this._drawCenterText(ctx, w, h, 'УРОВЕНЬ ПРОЙДЕН', '')
    if (this.state === 'game-over') this._drawGameOver(ctx, w, h)
  }

  private _drawBoard(ctx: CanvasRenderingContext2D): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    const t = this.tile
    for (let y = 0; y < ROWS; y++) {
      for (let x = 0; x < COLS; x++) {
        const tile = this.grid[y]?.[x]
        if (!tile || tile.type === 'empty') continue
        const cx = x * t + t / 2
        const cy = y * t + t / 2
        if (tile.type === 'brick' && tile.damage < 4) {
          ctx.fillStyle = '#111111'
          // четверти кирпича "выбиваются" по мере damage (0..3)
          const half = t / 2
          const quads: Array<[number, number]> = [[0, 0], [half, 0], [0, half], [half, half]]
          for (let i = 0; i < 4; i++) {
            if (i < tile.damage) continue
            ctx.fillRect(x * t + (quads[i]?.[0] ?? 0), y * t + (quads[i]?.[1] ?? 0), half, half)
          }
          ctx.strokeStyle = '#ffffff'
          ctx.lineWidth = 1
          ctx.strokeRect(x * t + 1, y * t + 1, t - 2, t - 2)
        } else if (tile.type === 'steel') {
          ctx.font = `700 ${Math.max(8, t * 0.9)}px ${this.glyphFontFamily}`
          ctx.fillStyle = '#444444'
          ctx.fillText('█', cx, cy + 1)
        } else if (tile.type === 'water') {
          ctx.font = `700 ${Math.max(8, t * 0.8)}px ${this.glyphFontFamily}`
          ctx.fillStyle = '#777777'
          ctx.fillText('≈', cx, cy + 1)
        } else if (tile.type === 'base') {
          ctx.font = `700 ${Math.max(8, t * 0.85)}px ${this.glyphFontFamily}`
          ctx.fillStyle = this.baseAlive ? '#111111' : '#bbbbbb'
          ctx.fillText('★', cx, cy + 1)
        }
      }
    }
    ctx.restore()
  }

  private _drawTrees(ctx: CanvasRenderingContext2D): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    const t = this.tile
    for (let y = 0; y < ROWS; y++) {
      for (let x = 0; x < COLS; x++) {
        const tile = this.grid[y]?.[x]
        if (!tile || tile.type !== 'tree') continue
        ctx.font = `700 ${Math.max(8, t * 0.95)}px ${this.glyphFontFamily}`
        ctx.fillStyle = '#999999'
        ctx.fillText('♣', x * t + t / 2, y * t + t / 2 + 1)
      }
    }
    ctx.restore()
  }

  private _tankGlyphBlock(dir: Dir): string[] {
    // 3×3 глиф-блок, "дуло" смотрит по направлению
    if (dir === 'up') return ['╔▲╗', '╠█╣', '╚╩╝']
    if (dir === 'down') return ['╔╦╗', '╠█╣', '╚▼╝']
    if (dir === 'left') return ['╔╦╗', '◄█╣', '╚╩╝']
    return ['╔╦╗', '╠█►', '╚╩╝']
  }

  private _drawTank(ctx: CanvasRenderingContext2D, t: Tank, color: string): void {
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

  private _drawTanks(ctx: CanvasRenderingContext2D): void {
    for (const e of this.enemies) {
      if (!e.alive) continue
      this._drawTank(ctx, e, e.tough ? '#000000' : '#555555')
    }
    if (this.player.alive) this._drawTank(ctx, this.player, '#111111')
    this._drawTrees(ctx) // кусты рисуются над танками — перекрывают силуэт
  }

  private _drawBullets(ctx: CanvasRenderingContext2D): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.font = `700 ${Math.max(8, this.tile * 0.5)}px ${this.glyphFontFamily}`
    ctx.fillStyle = '#111111'
    for (const b of this.bullets) {
      if (!b.alive) continue
      ctx.fillText('•', b.x, b.y + 1)
    }
    ctx.restore()
  }

  private _drawHud(ctx: CanvasRenderingContext2D, w: number): void {
    ctx.save()
    ctx.fillStyle = '#111111'
    ctx.font = `700 13px ${this.glyphFontFamily}`
    ctx.textAlign = 'left'
    ctx.fillText(`УРОВЕНЬ ${this.level}   ОЧКИ ${this.score}`, 14, 22)
    ctx.textAlign = 'right'
    ctx.fillText(`РЕКОРД ${this.best}`, w - 14, 22)
    ctx.restore()

    ctx.save()
    ctx.font = `700 13px ${this.glyphFontFamily}`
    ctx.textAlign = 'left'
    ctx.fillStyle = '#111111'
    let hearts = ''
    for (let i = 0; i < 3; i++) hearts += (i < this.lives ? '♥' : '♡') + ' '
    const enemyBlocks = '▮'.repeat(Math.min(20, this.enemiesLeftToSpawn + this.enemiesAlive))
    ctx.fillText(`ЖИЗНИ ${hearts.trim()}   ВРАГИ ${enemyBlocks}`, 14, 42)
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
      ctx.fillStyle = active ? 'rgba(17,17,17,0.18)' : 'rgba(17,17,17,0.06)'
      ctx.fillRect(r.x, r.y, r.w, r.h)
      ctx.strokeStyle = '#111111'
      ctx.lineWidth = 1
      ctx.strokeRect(r.x, r.y, r.w, r.h)
      ctx.fillStyle = '#111111'
      ctx.fillText(label, r.x + r.w / 2, r.y + r.h / 2 + 1)
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
    if (title) {
      ctx.fillStyle = '#111111'
      ctx.font = `700 26px ${this.glyphFontFamily}`
      ctx.fillText(title.toUpperCase(), w / 2, h / 2 - 8)
    }
    if (subtitle) {
      ctx.font = `13px ${this.glyphFontFamily}`
      ctx.fillStyle = '#444444'
      ctx.fillText(subtitle, w / 2, h / 2 + (title ? 18 : 0))
    }
    ctx.restore()
  }

  private _drawGameOver(ctx: CanvasRenderingContext2D, w: number, h: number): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.fillStyle = '#111111'
    ctx.font = `700 24px ${this.glyphFontFamily}`
    ctx.fillText('ИГРА ОКОНЧЕНА', w / 2, h / 2 - 30)
    ctx.font = `14px ${this.glyphFontFamily}`
    ctx.fillText(`ОЧКИ ${this.score}   РЕКОРД ${this.best}`, w / 2, h / 2 - 4)

    const btnW = 160, btnH = 36
    const bx = w / 2 - btnW / 2, by = h / 2 + 16
    ctx.strokeStyle = '#111111'
    ctx.lineWidth = 1
    ctx.strokeRect(bx, by, btnW, btnH)
    ctx.fillStyle = '#111111'
    ctx.font = `700 14px ${this.glyphFontFamily}`
    ctx.fillText('[ ЕЩЁ РАЗ ]', w / 2, by + btnH / 2 + 5)
    ctx.restore()

    this._gameOverBtnRect = { x: bx, y: by, w: btnW, h: btnH }
  }
}
