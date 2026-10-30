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
// Источник (kyuuzou/battle-city) — Unity-прототип на C#/3D-физике: реально
// портированы только текстовая сетка уровня, прямолинейный снаряд и
// "кирпич уничтожается первым попаданием" (см. предыдущую версию файла для
// подробного разбора). ИИ врагов/союзников, база с оградой, бонусы, режимы
// 1/2 игрока и «версус» — здесь нет аналога в первоисточнике, спроектированы
// заново под эту игру и разложены по модулям tank/*.ts (Правило №5 — не
// сваливать логику обратно в один файл).
//
// Карты уровней, бонусы, названия — свои; оригинальные стадии/ассеты Namco
// не используются, торговая марка держателя классики жанра в UI не
// используется. UI-имя игры — «Танчики».

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

import { BASE_NORTH, BASE_SOUTH, COLS, ROWS, buildGrid, carveBaseArea, MAX_LEVELS } from './tank/maps'
import { buildModeSetup, makeWildEnemy, opposingSideFor } from './tank/modes'
import { dirVector, updateAiTank } from './tank/ai'
import { applyPowerUp, randomPowerUpType, spawnPowerUp, updatePowerUps } from './tank/powerups'
import type { PowerUpHooks } from './tank/powerups'
import * as render from './tank/render'
import type { TankSprites } from './tank/render'
import type { Bullet, Dir, Explosion, GameMode, GameState, PowerUp, Rect, Side, Tank, Tile } from './tank/types'
import { SHIELD_SPAWN_SECONDS } from './tank/types'

const PLAYER_SPEED = 118
const ENEMY_SPEED_BASE = 72
const BULLET_SPEED_PLAYER = 340
const BULLET_SPEED_ENEMY = 230
const PLAYER_FIRE_COOLDOWN = 0.38
const ENEMY_FIRE_COOLDOWN_MIN = 1.1
const ENEMY_FIRE_COOLDOWN_MAX = 2.6
const ENEMIES_PER_STAGE = 20
const MAX_ENEMIES_ON_FIELD = 5
const PLAYER_LIVES_START = 3
const POWERUP_DROP_EVERY = 4 // каждый N-й враг волны — «мигающий», роняет бонус

interface PlayerStart {
  x: number
  y: number
  dir: Dir
}

export class TankGame {
  private canvas: HTMLCanvasElement
  private ctx: CanvasRenderingContext2D

  private dpr = 1
  private width = 0
  private height = 0
  private tile = 18
  private boardOffsetX = 0
  private boardOffsetY = 0

  private running = false
  private rafId: number | null = null
  private lastTime = 0

  private state: GameState = 'menu'
  private stateTimer = 0
  private menuSelected = 0
  private readonly menuItems = [
    { mode: 'solo' as GameMode, title: '1 игрок против компьютера' },
    { mode: 'coop' as GameMode, title: '2 игрока вместе против компьютера' },
    { mode: 'versus' as GameMode, title: '2 игрока друг против друга' },
  ]

  private mode: GameMode = 'solo'
  private level = 1
  private score: Record<Side, number> = { south: 0, north: 0, wild: 0 }
  private best: number

  private grid: Tile[][] = []
  private spawnPointsNorth: { x: number; y: number }[] = []
  private spawnPointsSouth: { x: number; y: number }[] = []
  private playerStarts = new Map<number, PlayerStart>() // ключ — id танка игрока
  private baseDestroyed: Record<Side, boolean> = { south: false, north: false, wild: false }
  private fenceTimer: Record<Side, number> = { south: 0, north: 0, wild: 0 }

  private units: Tank[] = []
  private bullets: Bullet[] = []
  private explosions: Explosion[] = []
  private powerUps: PowerUp[] = []

  private enemiesLeftToSpawn = 0
  private enemiesAliveCount = 0
  private enemySpawnTimer = 0
  private enemySpawnedTotal = 0

  private matchWinner: Side | null = null

  private _bg: HTMLCanvasElement | null = null
  private glyphFontFamily = render.GLYPH_FONT_FAMILY
  private hudFontFamily = render.HUD_FONT_FAMILY

  private _sprites: TankSprites = {
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
  private _menuRects: Rect[] = []
  private _wasRunning = false
  private _onEscape: (() => void) | null = null
  private _onGameOver: ((score: number) => void) | null = null

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

    // Рекорд приходит с сервера (DuckShootWindow.vue зовёт setBest() после
    // создания игры) — локально не хранится и не читается из localStorage
    // (Правило №6, единственный источник истины — сервер).
    this.best = 0

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
      const blocking = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' ', 'Spacebar', 'Enter', 'w', 'a', 's', 'd', 'W', 'A', 'S', 'D', 'p', 'P']
      if (blocking.includes(e.key)) e.preventDefault()

      if (e.key.toLowerCase() === 'p' && this.state === 'playing') { this.state = 'paused'; return }
      if (e.key.toLowerCase() === 'p' && this.state === 'paused') { this.state = 'playing'; return }

      if (this.state === 'menu') {
        if (e.key === 'ArrowUp' || e.key === 'w' || e.key === 'W') this.menuSelected = (this.menuSelected + this.menuItems.length - 1) % this.menuItems.length
        else if (e.key === 'ArrowDown' || e.key === 's' || e.key === 'S') this.menuSelected = (this.menuSelected + 1) % this.menuItems.length
        else if (e.key === 'Enter') this._startMode(this.menuItems[this.menuSelected]!.mode)
        return
      }
      if ((this.state === 'game-over' || this.state === 'match-over') && e.key === 'Enter') { this.state = 'menu'; return }

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

  onGameOver(fn: (score: number) => void): void {
    this._onGameOver = fn
  }

  setBest(best: number): void {
    this.best = Math.max(this.best, best)
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

  private _resize(): void {
    const parent = this.canvas.parentElement
    if (!parent) return
    const rect = parent.getBoundingClientRect()
    this.dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1))
    this.width = Math.max(1, Math.round(rect.width))
    this.height = Math.max(1, Math.round(rect.height))
    this.canvas.width = Math.round(this.width * this.dpr)
    this.canvas.height = Math.round(this.height * this.dpr)
    this.canvas.style.width = `${this.width}px`
    this.canvas.style.height = `${this.height}px`
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    this._bg = this._buildBackground(this.width, this.height, this.dpr)

    const hudH = this.mode === 'versus' ? 62 : 46
    const padH = this._isTouch() && this.mode === 'solo' ? 96 : 0
    const availW = this.width - 16
    const availH = this.height - hudH - padH - 10
    this.tile = Math.max(4, Math.floor(Math.min(availW / COLS, availH / ROWS)))
    this.boardOffsetX = Math.round((this.width - this.tile * COLS) / 2)
    this.boardOffsetY = hudH

    this._layoutTouchPad()
    this._menuRects = render.menuItemRects(this.width, this.height, this.menuItems.length)
  }

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
    if (!this._isTouch() || this.mode !== 'solo') { this._padRects = null; return }
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

    if (this.state === 'menu' && phase === 'down') {
      for (let i = 0; i < this._menuRects.length; i++) {
        if (this._inRect(x, y, this._menuRects[i]!)) { this._startMode(this.menuItems[i]!.mode); return }
      }
      return
    }

    if ((this.state === 'game-over' || this.state === 'match-over') && phase === 'down') {
      const r = this._gameOverBtnRect
      if (r && this._inRect(x, y, r)) { this.state = 'menu'; return }
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

  // ---------- mode / level setup ----------

  private _startMode(mode: GameMode): void {
    this.mode = mode
    this.level = 1
    this.score = { south: 0, north: 0, wild: 0 }
    this._setupLevel(this.level)
    this.state = 'level-intro'
    this.stateTimer = 0
    this._resize()
  }

  private _setupLevel(level: number): void {
    const built = buildGrid(level)
    this.grid = built.grid
    this.spawnPointsNorth = built.spawnPointsNorth
    this.spawnPointsSouth = built.spawnPointsSouth

    this.bullets = []
    this.explosions = []
    this.powerUps = []
    this.baseDestroyed = { south: false, north: false, wild: false }
    this.fenceTimer = { south: 0, north: 0, wild: 0 }

    const setup = buildModeSetup(this.mode)
    for (const base of setup.bases) carveBaseArea(this.grid, base.pos)

    this.units = setup.tanks
    // В «версусе» союзники встают на точки спавна карты у своей базы (те же
    // «E», что в PvE отдают диких врагов) — карта определяет расстановку,
    // а не константа в modes.ts (Правило №6, один источник точек спавна).
    if (this.mode === 'versus') {
      const byDistanceToBase = (base: { x: number; y: number }) => (a: { x: number; y: number }, b: { x: number; y: number }) =>
        Math.abs(a.x - base.x) - Math.abs(b.x - base.x)
      const southSpots = [...this.spawnPointsSouth].sort(byDistanceToBase(BASE_SOUTH)).slice(0, 2)
      const northSpots = [...this.spawnPointsNorth].sort(byDistanceToBase(BASE_NORTH)).slice(0, 2)
      const allies = this.units.filter((u) => u.kind === 'ally')
      allies.filter((u) => u.side === 'south').forEach((u, i) => { const sp = southSpots[i]; if (sp) { u.x = sp.x; u.y = sp.y } })
      allies.filter((u) => u.side === 'north').forEach((u, i) => { const sp = northSpots[i]; if (sp) { u.x = sp.x; u.y = sp.y } })
    }
    this.playerStarts.clear()
    for (const u of this.units) {
      if (u.kind === 'player') {
        u.lives = PLAYER_LIVES_START
        u.shieldTimer = SHIELD_SPAWN_SECONDS
        this.playerStarts.set(u.id, { x: u.x, y: u.y, dir: u.dir })
      }
    }

    this.enemiesLeftToSpawn = setup.wave ? ENEMIES_PER_STAGE : 0
    this.enemiesAliveCount = 0
    this.enemySpawnedTotal = 0
    this.enemySpawnTimer = 0.6
    this.matchWinner = null
  }

  private _nextLevel(): void {
    this.level = this.level >= MAX_LEVELS ? 1 : this.level + 1
    this._setupLevel(this.level)
    this.state = 'level-intro'
    this.stateTimer = 0
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

  private _blocksBullet(tile: Tile | null, piercesSteel: boolean): boolean {
    if (!tile) return true
    if (tile.type === 'tree') return false
    if (tile.type === 'steel') return !piercesSteel
    return tile.type === 'base' || (tile.type === 'brick' && tile.damage < 4)
  }

  private _tankRect(t: Pick<Tank, 'x' | 'y'>): Rect {
    return render.tankRect(t, this.tile)
  }

  private _rectsOverlap(a: Rect, b: Rect): boolean {
    return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
  }

  private _tankBlockedByTanks(self: Tank | null, nx: number, ny: number): boolean {
    const r = render.tankRect({ x: nx, y: ny }, this.tile)
    for (const u of this.units) {
      if (u === self || !u.alive) continue
      if (this._rectsOverlap(r, this._tankRect(u))) return true
    }
    return false
  }

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

  private _randomFreeCell(): { x: number; y: number } | null {
    for (let attempt = 0; attempt < 40; attempt++) {
      const x = 1 + Math.floor(Math.random() * (COLS - 2))
      const y = 1 + Math.floor(Math.random() * (ROWS - 2))
      if (!this._blocksMovement(this._tileAt(x, y))) return { x, y }
    }
    return null
  }

  // ---------- loop ----------

  private _loop = (now: number): void => {
    if (!this.running) return
    const dt = Math.min(0.05, (now - this.lastTime) / 1000)
    this.lastTime = now

    if (!document.hidden) this._update(dt)
    this._render()

    this.rafId = requestAnimationFrame(this._loop)
  }

  private _update(dt: number): void {
    if (this.state === 'menu' || this.state === 'paused') return

    if (this.state === 'level-intro') {
      this.stateTimer += dt
      if (this.stateTimer > 1.1) { this.stateTimer = 0; this.state = 'playing' }
      return
    }
    if (this.state === 'level-complete') {
      this.stateTimer += dt
      if (this.stateTimer > 1.3) this._nextLevel()
      return
    }
    if (this.state === 'game-over' || this.state === 'match-over') return

    this._updateFences(dt)
    this._updatePlayers(dt)
    this._updateAiUnits(dt)
    this._updateBullets(dt)
    this._updateExplosions(dt)
    this.powerUps = updatePowerUps(this.powerUps, dt)
    this._collectPowerUps()
    if (this.enemiesLeftToSpawn > 0 || this.enemiesAliveCount > 0) this._spawnWaveIfNeeded(dt)

    this._checkOutcome()
  }

  private _updateFences(dt: number): void {
    for (const side of ['south', 'north'] as Side[]) {
      if (this.fenceTimer[side] <= 0) continue
      this.fenceTimer[side] -= dt
      if (this.fenceTimer[side] <= 0) {
        this.fenceTimer[side] = 0
        const base = side === 'south' ? BASE_SOUTH : BASE_NORTH
        this._setFenceTiles(base, 'brick')
      }
    }
  }

  private _setFenceTiles(base: { x: number; y: number }, type: 'steel' | 'brick'): void {
    for (let dy = -1; dy <= 1; dy++) {
      for (let dx = -1; dx <= 1; dx++) {
        if (dx === 0 && dy === 0) continue
        const tile = this._tileAt(base.x + dx, base.y + dy)
        if (tile && tile.type !== 'empty') { tile.type = type; tile.damage = 0 }
      }
    }
  }

  // ---------- players ----------

  private _dirVector(dir: Dir) {
    return dirVector(dir)
  }

  private _wantedDirForPlayer(playerId: 1 | 2): Dir | null {
    const soloBoth = this.mode === 'solo'
    if ((playerId === 1 || soloBoth)) {
      if (this.touchDir) return this.touchDir
      if (this.keys.has('w')) return 'up'
      if (this.keys.has('s')) return 'down'
      if (this.keys.has('a')) return 'left'
      if (this.keys.has('d')) return 'right'
    }
    if (playerId === 2 || soloBoth) {
      if (this.keys.has('arrowup')) return 'up'
      if (this.keys.has('arrowdown')) return 'down'
      if (this.keys.has('arrowleft')) return 'left'
      if (this.keys.has('arrowright')) return 'right'
    }
    return null
  }

  private _wantsFireForPlayer(playerId: 1 | 2): boolean {
    const soloBoth = this.mode === 'solo'
    if ((playerId === 1 || soloBoth) && (this.keys.has(' ') || this.keys.has('spacebar') || this.touchFire)) return true
    if ((playerId === 2 || soloBoth) && this.keys.has('enter')) return true
    return false
  }

  private _updatePlayers(dt: number): void {
    for (const p of this.units) {
      if (p.kind !== 'player') continue
      if (p.shieldTimer > 0) p.shieldTimer = Math.max(0, p.shieldTimer - dt)
      if (!p.alive) continue
      if (p.frozenTimer > 0) { p.frozenTimer = Math.max(0, p.frozenTimer - dt); continue }

      const wanted = this._wantedDirForPlayer(p.playerId ?? 1)
      if (wanted) {
        p.dir = wanted
        const { dx, dy } = this._dirVector(wanted)
        const nx = p.x + (dx * PLAYER_SPEED * dt) / this.tile
        const ny = p.y + (dy * PLAYER_SPEED * dt) / this.tile
        if (!this._tileBlocksAt(nx, ny) && !this._tankBlockedByTanks(p, nx, ny)) {
          p.x = Math.max(0, Math.min(COLS - 1, nx))
          p.y = Math.max(0, Math.min(ROWS - 1, ny))
        }
      }

      p.cooldown = Math.max(0, p.cooldown - dt)
      if (this._wantsFireForPlayer(p.playerId ?? 1) && p.cooldown <= 0) {
        this._fireBullet(p)
        p.cooldown = PLAYER_FIRE_COOLDOWN
      }
    }
  }

  // ---------- AI (союзники в версусе + дикие враги PvE) ----------

  private _updateAiUnits(dt: number): void {
    for (const u of this.units) {
      if (u.kind === 'player' || !u.alive) continue
      const target = this._aiTargetFor(u)
      const speed = u.kind === 'enemy' ? ENEMY_SPEED_BASE + (this.level - 1) * 5 : PLAYER_SPEED * 0.72
      updateAiTank(u, dt, target, speed, {
        tile: this.tile,
        inBounds: (nx, ny) => nx >= 0 && nx <= COLS - 1 && ny >= 0 && ny <= ROWS - 1,
        blocked: (nx, ny) => this._tileBlocksAt(nx, ny) || this._tankBlockedByTanks(u, nx, ny),
        fire: (t) => this._fireBullet(t),
        fireCooldownMin: ENEMY_FIRE_COOLDOWN_MIN,
        fireCooldownMax: ENEMY_FIRE_COOLDOWN_MAX,
      })
    }
  }

  private _aiTargetFor(u: Tank): { x: number; y: number } {
    if (u.kind === 'enemy') {
      const player = this.units.find((x) => x.kind === 'player' && x.alive)
      return player ?? BASE_SOUTH
    }
    // союзник версуса: цель — противоположная база/ближайший живой противник
    const enemySide: Side = u.side === 'south' ? 'north' : 'south'
    const foe = this.units.find((x) => x.side === enemySide && x.alive)
    if (foe) return foe
    return u.side === 'south' ? BASE_NORTH : BASE_SOUTH
  }

  // ---------- bullets ----------

  private _fireBullet(t: Tank): void {
    if (t.kind === 'player') {
      const maxLive = t.level >= 2 ? 2 : 1
      const live = this.bullets.filter((b) => b.alive && b.fromTankId === t.id).length
      if (live >= maxLive) return
    }
    const { dx, dy } = this._dirVector(t.dir)
    const baseSpeed = t.kind === 'player' ? BULLET_SPEED_PLAYER : BULLET_SPEED_ENEMY
    const speed = t.kind === 'player' && t.level >= 1 ? baseSpeed * 1.25 : baseSpeed
    const piercesSteel = t.kind === 'player' && t.level >= 3

    const spawnOne = (lateral: number) => {
      const perpDx = dy !== 0 ? 1 : 0
      const perpDy = dx !== 0 ? 1 : 0
      this.bullets.push({
        x: (t.x + 0.5) * this.tile + dx * this.tile * 0.4 + perpDx * lateral,
        y: (t.y + 0.5) * this.tile + dy * this.tile * 0.4 + perpDy * lateral,
        dir: t.dir,
        owner: t.side,
        speed,
        alive: true,
        piercesSteel,
        fromTankId: t.id,
      })
    }

    if (t.kind === 'player' && t.level >= 2) {
      spawnOne(-this.tile * 0.22)
      spawnOne(this.tile * 0.22)
    } else {
      spawnOne(0)
    }
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
      if (tile && this._blocksBullet(tile, b.piercesSteel)) {
        if (tile.type === 'steel' && b.piercesSteel) {
          tile.type = 'empty'
        } else if (tile.type === 'brick') {
          tile.damage = Math.min(4, tile.damage + 1)
        } else if (tile.type === 'base') {
          this._damageBase(gx, gy, b.owner)
        }
        b.alive = false
        continue
      }

      for (const u of this.units) {
        if (!u.alive || u.side === b.owner) continue
        const ur = this._tankRect(u)
        if (b.x >= ur.x && b.x <= ur.x + ur.w && b.y >= ur.y && b.y <= ur.y + ur.h) {
          b.alive = false
          this._hitUnit(u, b.owner)
          break
        }
      }
    }
    this.bullets = this.bullets.filter((b) => b.alive)
  }

  private _damageBase(gx: number, gy: number, ownerSide: Side): void {
    const isSouth = gx === BASE_SOUTH.x && gy === BASE_SOUTH.y
    const isNorth = gx === BASE_NORTH.x && gy === BASE_NORTH.y
    const side: Side | null = isSouth ? 'south' : isNorth ? 'north' : null
    if (!side || side === ownerSide) return
    const tile = this._tileAt(gx, gy)
    if (tile) tile.type = 'empty'
    this.baseDestroyed[side] = true
    this._spawnExplosion(gx, gy)
  }

  private _hitUnit(u: Tank, bySide: Side): void {
    if (u.shieldTimer > 0) return
    u.hp -= 1
    if (u.hp > 0) return
    this._killUnit(u, bySide)
  }

  private _killUnit(u: Tank, bySide: Side | null): void {
    this._spawnExplosion(u.x, u.y)
    u.alive = false

    if (u.kind === 'enemy') {
      this.enemiesAliveCount = Math.max(0, this.enemiesAliveCount - 1)
      const points = u.enemyType === 'armored' ? 400 : u.enemyType === 'fast' ? 200 : 100
      if (bySide) this.score[bySide] += points
      if (u.specialDrop) {
        const cell = this._randomFreeCell()
        if (cell) spawnPowerUp(randomPowerUpType(), cell.x, cell.y, this.powerUps)
      }
      return
    }

    // игрок/союзник
    if (bySide) this.score[bySide] += u.kind === 'player' ? 0 : 150
    if (u.kind === 'player') {
      u.lives = Math.max(0, (u.lives ?? 0) - 1)
      u.level = 0
      if (u.lives > 0) {
        const start = this.playerStarts.get(u.id)
        if (start) { u.x = start.x; u.y = start.y; u.dir = start.dir }
        u.alive = true
        u.hp = u.maxHp
        u.shieldTimer = SHIELD_SPAWN_SECONDS
      }
    }
  }

  // ---------- бонусы ----------

  private _powerUpHooks(): PowerUpHooks {
    return {
      freezeSide: (side, seconds) => {
        for (const u of this.units) if (u.side === side && u.alive) u.frozenTimer = Math.max(u.frozenTimer, seconds)
      },
      fortifyBaseFence: (side, seconds) => {
        const base = side === 'south' ? BASE_SOUTH : side === 'north' ? BASE_NORTH : null
        if (!base) return
        this.fenceTimer[side] = seconds
        this._setFenceTiles(base, 'steel')
      },
      destroyTanksOfSide: (side) => {
        for (const u of this.units) if (u.side === side && u.alive) this._killUnit(u, null)
      },
      addLife: (collector) => {
        collector.lives = (collector.lives ?? 0) + 1
      },
    }
  }

  private _collectPowerUps(): void {
    if (this.powerUps.length === 0) return
    const hooks = this._powerUpHooks()
    for (const u of this.units) {
      if (!u.alive || u.kind === 'enemy') continue
      const r = this._tankRect(u)
      const idx = this.powerUps.findIndex((p) => {
        const cx = (p.x + 0.5) * this.tile
        const cy = (p.y + 0.5) * this.tile
        return cx >= r.x && cx <= r.x + r.w && cy >= r.y && cy <= r.y + r.h
      })
      if (idx < 0) continue
      const p = this.powerUps[idx]!
      this.powerUps.splice(idx, 1)
      const opposing = opposingSideFor(u.side, this.mode)
      applyPowerUp(p.type, u, opposing, hooks)
    }
  }

  // ---------- волна врагов PvE ----------

  private _spawnWaveIfNeeded(dt: number): void {
    this.enemySpawnTimer -= dt
    if (this.enemySpawnTimer > 0) return
    if (this.enemiesLeftToSpawn <= 0) return
    if (this.enemiesAliveCount >= MAX_ENEMIES_ON_FIELD) { this.enemySpawnTimer = 0.4; return }
    if (this.spawnPointsNorth.length === 0) return

    const sp = this.spawnPointsNorth[Math.floor(Math.random() * this.spawnPointsNorth.length)]!
    if (this._tankBlockedByTanks(null, sp.x, sp.y)) { this.enemySpawnTimer = 0.3; return }

    this.enemySpawnedTotal++
    const roll = Math.random()
    const enemyType = roll < 0.6 ? 'basic' : roll < 0.85 ? 'fast' : 'armored'
    const specialDrop = this.enemySpawnedTotal % POWERUP_DROP_EVERY === 0
    const enemy = makeWildEnemy(sp.x, sp.y, enemyType, specialDrop)
    enemy.cooldown = ENEMY_FIRE_COOLDOWN_MIN + Math.random() * (ENEMY_FIRE_COOLDOWN_MAX - ENEMY_FIRE_COOLDOWN_MIN)
    this.units.push(enemy)

    this.enemiesLeftToSpawn--
    this.enemiesAliveCount++
    this.enemySpawnTimer = 0.55 + Math.random() * 0.4
  }

  // ---------- взрывы ----------

  private _spawnExplosion(gx: number, gy: number): void {
    this.explosions.push({ x: (gx + 0.5) * this.tile, y: (gy + 0.5) * this.tile, t: 0 })
  }

  private _updateExplosions(dt: number): void {
    for (const ex of this.explosions) ex.t += dt
    this.explosions = this.explosions.filter((ex) => ex.t < render.EXPLOSION_DURATION)
  }

  // ---------- исход ----------

  private _teamAliveCount(side: Side): number {
    return this.units.filter((u) => u.side === side && u.alive).length
  }

  private _teamDepleted(side: Side): boolean {
    return this.baseDestroyed[side] || this._teamAliveCount(side) === 0
  }

  private _checkOutcome(): void {
    if (this.mode === 'versus') {
      if (this._teamDepleted('south')) { this._endMatch('north'); return }
      if (this._teamDepleted('north')) { this._endMatch('south'); return }
      return
    }

    if (this._teamDepleted('south')) { this._endRun(); return }
    if (this.enemiesLeftToSpawn === 0 && this.enemiesAliveCount === 0 && this.state === 'playing') {
      this.state = 'level-complete'
      this.stateTimer = 0
      this.score.south += 500
    }
  }

  private _endRun(): void {
    // PvE (solo/coop) — единственный режим, где счёт отправляется на сервер.
    const total = this.score.south
    this.best = Math.max(this.best, total)
    this.state = 'game-over'
    if (this._onGameOver) this._onGameOver(total)
  }

  private _endMatch(winner: Side): void {
    // Версус (игрок против игрока) — своего счёта для лидерборда нет
    // (владелец: "versus has no single-player score"), onGameOver не зовём.
    this.matchWinner = winner
    const total = Math.max(this.score.south, this.score.north)
    this.best = Math.max(this.best, total)
    this.state = 'match-over'
  }

  // ---------- rendering ----------

  private _render(): void {
    const ctx = this.ctx
    const w = this.width
    const h = this.height

    ctx.clearRect(0, 0, w, h)
    if (this._bg && this._bg.width > 0) ctx.drawImage(this._bg, 0, 0, w, h)
    else { ctx.fillStyle = '#2f7d4a'; ctx.fillRect(0, 0, w, h) }

    if (this.state === 'menu') {
      render.drawMenu(ctx, w, h, this.menuItems, this.menuSelected, this.glyphFontFamily, this.hudFontFamily)
      return
    }

    ctx.save()
    ctx.translate(this.boardOffsetX, this.boardOffsetY)
    render.drawGround(ctx, this._sprites, this.tile, COLS, ROWS)
    render.drawBoard(ctx, this._sprites, this.tile, this.grid, this.glyphFontFamily)
    render.drawTanks(ctx, this._sprites, this.tile, this.units, this.grid, this.glyphFontFamily)
    render.drawBullets(ctx, this._sprites, this.tile, this.bullets, this.glyphFontFamily)
    render.drawExplosions(ctx, this._sprites, this.tile, this.explosions)
    render.drawPowerUps(ctx, this.tile, this.powerUps)
    ctx.restore()

    this._drawHud(ctx, w)
    if (this._padRects) render.drawTouchPad(ctx, this._padRects, this.touchDir, this.touchFire, this.glyphFontFamily)

    if (this.state === 'level-intro') render.drawCenterText(ctx, w, h, `УРОВЕНЬ ${this.level}`, 'P — пауза', this.glyphFontFamily)
    if (this.state === 'level-complete') render.drawCenterText(ctx, w, h, 'УРОВЕНЬ ПРОЙДЕН', '', this.glyphFontFamily)
    if (this.state === 'paused') render.drawPaused(ctx, w, h, this.glyphFontFamily)
    if (this.state === 'game-over') {
      this._gameOverBtnRect = render.drawGameOverOverlay(ctx, w, h, 'ИГРА ОКОНЧЕНА', `ОЧКИ ${this.score.south}   РЕКОРД ${this.best}`, this.glyphFontFamily)
    }
    if (this.state === 'match-over') {
      const winnerLabel = this.matchWinner === 'south' ? 'ИГРОК 1' : 'ИГРОК 2'
      this._gameOverBtnRect = render.drawGameOverOverlay(ctx, w, h, `ПОБЕДИЛ ${winnerLabel}`, `ОЧКИ ${this.score.south} : ${this.score.north}`, this.glyphFontFamily)
    }
  }

  private _drawHud(ctx: CanvasRenderingContext2D, w: number): void {
    const lines: string[] = []
    if (this.mode === 'versus') {
      const p1 = this.units.find((u) => u.kind === 'player' && u.side === 'south')
      const p2 = this.units.find((u) => u.kind === 'player' && u.side === 'north')
      lines.push(`ИГРОК 1  ♥${p1?.lives ?? 0}  Ур.${(p1?.level ?? 0) + 1}  ОЧКИ ${this.score.south}`)
      lines.push(`ИГРОК 2  ♥${p2?.lives ?? 0}  Ур.${(p2?.level ?? 0) + 1}  ОЧКИ ${this.score.north}`)
    } else {
      const players = this.units.filter((u) => u.kind === 'player')
      const livesInfo = players.map((p) => `П${p.playerId ?? 1}:♥${p.lives ?? 0}`).join('  ')
      lines.push(`УРОВЕНЬ ${this.level}   ${livesInfo}   ВРАГИ ${this.enemiesLeftToSpawn + this.enemiesAliveCount}`)
      lines.push(`ОЧКИ ${this.score.south}   РЕКОРД ${this.best}`)
    }
    render.drawHud(ctx, w, lines)
  }
}
