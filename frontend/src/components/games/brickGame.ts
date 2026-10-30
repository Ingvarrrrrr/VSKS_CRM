// Based on lefrasso/Arkanoid (MIT License), Copyright (c) 2025 Arkanoid Game Contributors
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
// Порт убирает: debug-консоль, выбор темы, звук (Tone.js), степ-пауэрапы,
// внешние ассеты (кроме спрайтов ниже) и любые сетевые вызовы оригинала.
// Отрисовка — цветные спрайты Kenney "Puzzle Pack 2" (CC0, см.
// sprites/brick/License.txt) поверх мягкого градиентного фона.
//
// BrickGameWindow.vue (внутри DuckShootWindow.vue) создаёт контейнер и
// управляет жизненным циклом: constructor(container) → start() на открытии
// окна, destroy() на закрытии/unmount — та же схема, что у DuckShootGame.

import { loadSprite, isSpriteReady } from './spriteLoader'

const HUD_FONT_FAMILY = '"Segoe UI", Roboto, system-ui, sans-serif'

import paddleUrl from './sprites/brick/paddle.png'
import ballUrl from './sprites/brick/ball.png'
import brickRedUrl from './sprites/brick/brick_red.png'
import brickYellowUrl from './sprites/brick/brick_yellow.png'
import brickGreenUrl from './sprites/brick/brick_green.png'
import brickBlueUrl from './sprites/brick/brick_blue.png'
import brickPinkUrl from './sprites/brick/brick_pink.png'
import brickGreyUrl from './sprites/brick/brick_grey.png'

// Цветные спрайты кирпичей/паддла/мяча — Kenney "Puzzle Pack 2" (kenney.nl,
// CC0), см. sprites/brick/License.txt. Ряды кирпичей раскрашены по кругу
// через BRICK_ROW_SPRITES; подпись слова больше не нужна — цвет несёт роль.
const BRICK_ROW_SPRITES = [brickRedUrl, brickYellowUrl, brickGreenUrl, brickBlueUrl, brickPinkUrl, brickGreyUrl]
// Цвета для частиц разлёта при разрушении — приблизительно совпадают с цветом ряда.
const BRICK_ROW_COLORS = ['#e2504f', '#f6c445', '#8bc63f', '#3fa9d6', '#f48fb1', '#b9bcbe']

type GameState = 'level-intro' | 'playing' | 'game-over'

interface Brick {
  x: number
  y: number
  w: number
  h: number
  colorIdx: number
  hits: number
  maxHits: number
  alive: boolean
}

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  life: number
  maxLife: number
  color: string
}

interface Ball {
  x: number
  y: number
  dx: number
  dy: number
  radius: number
  onPaddle: boolean
}

interface Paddle {
  x: number
  y: number
  w: number
  h: number
}

interface Pointer {
  x: number
  y: number
  active: boolean
}

interface Rect {
  x: number
  y: number
  w: number
  h: number
}

const MAX_LEVELS = 15
// Базовая скорость — владелец: "слишком медленно", поднята ~1.7× (230→390);
// прирост за уровень (LEVEL_SPEED_STEP) не трогаем, но добавлен потолок
// MAX_BALL_SPEED, чтобы на старших уровнях не стало неиграбельно.
const BASE_BALL_SPEED = 390
const LEVEL_SPEED_STEP = 18
const MAX_BALL_SPEED = 560
const PADDLE_SPEED = 620 // px/sec, клавиатура
// Запуск мяча: при неподвижном паддле — строго вертикально (0°); движение
// паддла в момент запуска добавляет угол, до ±LAUNCH_MAX_ANGLE_DEG
// (классика — угол от положения/движения паддла, а не случайность).
const LAUNCH_MAX_ANGLE_DEG = 50

export class BrickGame {
  private canvas: HTMLCanvasElement
  private ctx: CanvasRenderingContext2D

  private dpr = 1
  private width = 0
  private height = 0

  private running = false
  private rafId: number | null = null
  private lastTime = 0

  private pointer: Pointer = { x: -9999, y: -9999, active: false }
  private leftPressed = false
  private rightPressed = false

  private state: GameState = 'level-intro'
  private stateTimer = 0

  private level = 1
  private score = 0
  private best: number
  private lives = 3

  private paddle: Paddle = { x: 0, y: 0, w: 0, h: 0 }
  // Скорость паддла (px/sec), посчитанная в _movePaddle — единственное
  // место (Правило №6); _launchOrRestart читает отсюда, чтобы угол запуска
  // зависел от движения паддла, а не от случайности.
  private _paddleVx = 0
  private ball: Ball = { x: 0, y: 0, dx: 0, dy: 0, radius: 6, onPaddle: true }
  private bricks: Brick[] = []
  private particles: Particle[] = []

  private _paddleImg = loadSprite(paddleUrl)
  private _ballImg = loadSprite(ballUrl)
  private _brickImgs = BRICK_ROW_SPRITES.map((u) => loadSprite(u))

  private _gameOverBtnRect: Rect | null = null
  private _wasRunning = false
  private _onEscape: (() => void) | null = null
  private _onGameOver: ((score: number) => void) | null = null

  private _onResize: () => void
  private _onVisibility: () => void
  private _onPointerMove: (e: PointerEvent) => void
  private _onPointerDown: (e: PointerEvent) => void
  private _onPointerLeave: () => void
  private _onKeyDown: (e: KeyboardEvent) => void
  private _onKeyUp: (e: KeyboardEvent) => void

  constructor(containerEl: HTMLElement) {
    const existing = containerEl.querySelector('canvas')
    this.canvas = existing || document.createElement('canvas')
    if (!this.canvas.parentElement) containerEl.appendChild(this.canvas)
    const ctx = this.canvas.getContext('2d')
    if (!ctx) throw new Error('BrickGame: canvas 2d context unavailable')
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
    this._onPointerMove = (e: PointerEvent) => this._updatePointer(e)
    this._onPointerDown = (e: PointerEvent) => {
      this._updatePointer(e)
      this._handleTapOrClick(this.pointer.x, this.pointer.y)
    }
    this._onPointerLeave = () => {
      this.pointer.active = false
    }
    this._onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && this._onEscape) { this._onEscape(); return }
      if (e.key === 'ArrowLeft') { this.leftPressed = true; e.preventDefault() }
      else if (e.key === 'ArrowRight') { this.rightPressed = true; e.preventDefault() }
      else if (e.key === ' ' || e.key === 'Spacebar') { e.preventDefault(); this._launchOrRestart() }
    }
    this._onKeyUp = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') this.leftPressed = false
      else if (e.key === 'ArrowRight') this.rightPressed = false
    }

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
    this.canvas.removeEventListener('pointermove', this._onPointerMove)
    this.canvas.removeEventListener('pointerdown', this._onPointerDown)
    this.canvas.removeEventListener('pointerleave', this._onPointerLeave)
    window.removeEventListener('keydown', this._onKeyDown)
    window.removeEventListener('keyup', this._onKeyUp)
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
    this.canvas.addEventListener('pointermove', this._onPointerMove)
    this.canvas.addEventListener('pointerdown', this._onPointerDown)
    this.canvas.addEventListener('pointerleave', this._onPointerLeave)
    window.addEventListener('keydown', this._onKeyDown)
    window.addEventListener('keyup', this._onKeyUp)
  }

  private _updatePointer(e: PointerEvent): void {
    const rect = this.canvas.getBoundingClientRect()
    this.pointer.x = e.clientX - rect.left
    this.pointer.y = e.clientY - rect.top
    this.pointer.active = true
  }

  private _resize(): void {
    const parent = this.canvas.parentElement
    if (!parent) return
    const rect = parent.getBoundingClientRect()
    this.dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1))
    const prevWidth = this.width
    const prevHeight = this.height
    this.width = Math.max(1, Math.round(rect.width))
    this.height = Math.max(1, Math.round(rect.height))
    this.canvas.width = Math.round(this.width * this.dpr)
    this.canvas.height = Math.round(this.height * this.dpr)
    // Без этого на экранах с devicePixelRatio > 1 canvas без CSS-размера
    // раздувается до своих пиксельных width/height атрибутов и вылезает за
    // рамки контейнера (тот же случай, что у DuckShootGame — см. его _resize).
    this.canvas.style.width = `${this.width}px`
    this.canvas.style.height = `${this.height}px`
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)

    this.paddle.w = Math.max(70, this.width / 7)
    this.paddle.h = Math.max(10, this.height / 38)
    if (prevWidth > 0) {
      const ratio = this.width / prevWidth
      this.paddle.x *= ratio
    } else {
      this.paddle.x = (this.width - this.paddle.w) / 2
    }
    this.paddle.x = Math.max(0, Math.min(this.width - this.paddle.w, this.paddle.x))
    this.paddle.y = this.height - this.paddle.h - 14

    this.ball.radius = Math.max(4, this.width / 140)
    if (this.ball.onPaddle) {
      this.ball.x = this.paddle.x + this.paddle.w / 2
      this.ball.y = this.paddle.y - this.ball.radius - 2
    } else if (prevWidth > 0 && prevHeight > 0) {
      this.ball.x = Math.max(this.ball.radius, Math.min(this.width - this.ball.radius, (this.ball.x / prevWidth) * this.width))
      this.ball.y = Math.max(this.ball.radius, Math.min(this.height - this.ball.radius, (this.ball.y / prevHeight) * this.height))
    }

    if (this.bricks.length > 0) this._relayoutBricks()
  }

  // ---------- level layout ----------

  // Единственное место, где считается раскладка кирпичей для уровня —
  // _setupLevel (новая раскладка) и _relayoutBricks (пересчёт координат при
  // resize) читают размеры отсюда, а не пересчитывают сами (Правило №6).
  private _levelGrid(level: number): { rows: number; cols: number } {
    const rows = Math.min(6, 3 + Math.floor((level - 1) / 3))
    const cols = 7
    return { rows, cols }
  }

  private _setupLevel(level: number): void {
    const { rows, cols } = this._levelGrid(level)
    const padding = 6
    const offsetTop = 56
    const offsetSide = Math.max(16, this.width * 0.03)
    const areaW = this.width - offsetSide * 2
    const brickW = (areaW - padding * (cols - 1)) / cols
    const brickH = Math.max(22, Math.min(this.height / 16, 34))

    this.bricks = []
    for (let r = 0; r < rows; r++) {
      // каждая третья строка — "крепкие" кирпичи (2 попадания), остальные — обычные
      const strongRow = r % 3 === 2
      const maxHits = strongRow ? 2 : 1
      for (let c = 0; c < cols; c++) {
        this.bricks.push({
          x: offsetSide + c * (brickW + padding),
          y: offsetTop + r * (brickH + padding),
          w: brickW,
          h: brickH,
          colorIdx: r % BRICK_ROW_SPRITES.length,
          hits: 0,
          maxHits,
          alive: true,
        })
      }
    }
  }

  // Пересчёт координат существующих кирпичей при resize — без потери
  // состояния (hits/alive), сетка совпадает с той, что строит _setupLevel.
  private _relayoutBricks(): void {
    const { rows, cols } = this._levelGrid(this.level)
    const padding = 6
    const offsetTop = 56
    const offsetSide = Math.max(16, this.width * 0.03)
    const areaW = this.width - offsetSide * 2
    const brickW = (areaW - padding * (cols - 1)) / cols
    const brickH = Math.max(22, Math.min(this.height / 16, 34))

    let i = 0
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const brick = this.bricks[i]
        if (brick) {
          brick.x = offsetSide + c * (brickW + padding)
          brick.y = offsetTop + r * (brickH + padding)
          brick.w = brickW
          brick.h = brickH
        }
        i++
      }
    }
  }

  private _ballSpeedForLevel(level: number): number {
    return Math.min(MAX_BALL_SPEED, BASE_BALL_SPEED + (level - 1) * LEVEL_SPEED_STEP)
  }

  private _placeBallOnPaddle(): void {
    this.ball.onPaddle = true
    this.ball.x = this.paddle.x + this.paddle.w / 2
    this.ball.y = this.paddle.y - this.ball.radius - 2
    this.ball.dx = 0
    this.ball.dy = 0
  }

  private _launchOrRestart(): void {
    if (this.state === 'game-over') {
      this._restartGame()
      return
    }
    if (this.state !== 'playing' && this.state !== 'level-intro') return
    if (!this.ball.onPaddle) return
    const speed = this._ballSpeedForLevel(this.level)
    // Паддл неподвижен → строго вверх (0°). Угол добавляет только движение
    // паддла в момент запуска (классика: не случайность) — доля скорости
    // паддла от его максимума, до ±LAUNCH_MAX_ANGLE_DEG.
    const vxNorm = Math.max(-1, Math.min(1, this._paddleVx / PADDLE_SPEED))
    const angleRad = (vxNorm * LAUNCH_MAX_ANGLE_DEG * Math.PI) / 180
    this.ball.dx = speed * Math.sin(angleRad)
    this.ball.dy = -Math.abs(speed * Math.cos(angleRad))
    this.ball.onPaddle = false
    this.state = 'playing'
  }

  private _handleTapOrClick(x: number, y: number): void {
    if (this.state === 'game-over') {
      const r = this._gameOverBtnRect
      if (r && x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) {
        this._restartGame()
      }
      return
    }
    this._launchOrRestart()
  }

  private _restartGame(): void {
    this.level = 1
    this.score = 0
    this.lives = 3
    this.state = 'level-intro'
    this.stateTimer = 0
    this.paddle.x = (this.width - this.paddle.w) / 2
    this._placeBallOnPaddle()
    this._setupLevel(this.level)
  }

  private _nextLevel(): void {
    this.level = Math.min(MAX_LEVELS, this.level + 1)
    this.state = 'level-intro'
    this.stateTimer = 0
    this.paddle.x = (this.width - this.paddle.w) / 2
    this._placeBallOnPaddle()
    this._setupLevel(this.level)
  }

  private _loseLife(): void {
    this.lives = Math.max(0, this.lives - 1)
    if (this.lives <= 0) {
      this.best = Math.max(this.best, this.score)
      this.state = 'game-over'
      if (this._onGameOver) this._onGameOver(this.score)
      return
    }
    this.paddle.x = (this.width - this.paddle.w) / 2
    this._placeBallOnPaddle()
    this.state = 'level-intro'
    this.stateTimer = 0
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
      if (this.stateTimer > 0.9) {
        this.stateTimer = 0
        this.state = 'playing'
      }
      // Пока показывается заставка уровня — паддл и мяч уже можно двигать,
      // мяч запускается пробелом/кликом (ball.onPaddle).
    }

    if (this.state === 'game-over') return

    this._movePaddle(dt)

    if (this.ball.onPaddle) {
      this.ball.x = this.paddle.x + this.paddle.w / 2
      this.ball.y = this.paddle.y - this.ball.radius - 2
    } else {
      this._moveBall(dt)
      this._brickCollisions()
    }

    this._updateParticles(dt)

    if (this.state === 'playing' && this._remainingBricks() === 0) {
      if (this.level >= MAX_LEVELS) {
        this.best = Math.max(this.best, this.score)
        this.state = 'game-over'
        if (this._onGameOver) this._onGameOver(this.score)
      } else {
        this._nextLevel()
      }
    }
  }

  // Маленький разлёт частиц при разрушении кирпича — своя процедурная анимация
  // (не спрайт), цвет берётся из BRICK_ROW_COLORS по цвету ряда.
  private _spawnParticles(x: number, y: number, color: string): void {
    const count = 6
    for (let i = 0; i < count; i++) {
      const angle = (Math.PI * 2 * i) / count + Math.random() * 0.4
      const speed = 60 + Math.random() * 90
      this.particles.push({
        x,
        y,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        life: 0.4,
        maxLife: 0.4,
        color,
      })
    }
  }

  private _updateParticles(dt: number): void {
    if (this.particles.length === 0) return
    for (const p of this.particles) {
      p.x += p.vx * dt
      p.y += p.vy * dt
      p.vy += 220 * dt
      p.life -= dt
    }
    this.particles = this.particles.filter((p) => p.life > 0)
  }

  private _remainingBricks(): number {
    let n = 0
    for (const b of this.bricks) if (b.alive) n++
    return n
  }

  private _movePaddle(dt: number): void {
    const prevX = this.paddle.x
    const targetX = this.pointer.active ? this.pointer.x - this.paddle.w / 2 : null
    if (targetX != null) {
      this.paddle.x = targetX
    } else if (this.rightPressed) {
      this.paddle.x += PADDLE_SPEED * dt
    } else if (this.leftPressed) {
      this.paddle.x -= PADDLE_SPEED * dt
    }
    this.paddle.x = Math.max(0, Math.min(this.width - this.paddle.w, this.paddle.x))
    this._paddleVx = dt > 0 ? (this.paddle.x - prevX) / dt : 0
  }

  private _moveBall(dt: number): void {
    const b = this.ball
    b.x += b.dx * dt
    b.y += b.dy * dt

    if (b.x - b.radius < 0) {
      b.x = b.radius
      b.dx = Math.abs(b.dx)
    } else if (b.x + b.radius > this.width) {
      b.x = this.width - b.radius
      b.dx = -Math.abs(b.dx)
    }
    if (b.y - b.radius < 0) {
      b.y = b.radius
      b.dy = Math.abs(b.dy)
    }

    // паддл
    if (
      b.dy > 0 &&
      b.y + b.radius >= this.paddle.y &&
      b.y - b.radius <= this.paddle.y + this.paddle.h &&
      b.x + b.radius >= this.paddle.x &&
      b.x - b.radius <= this.paddle.x + this.paddle.w
    ) {
      b.y = this.paddle.y - b.radius
      const collidePoint = (b.x - (this.paddle.x + this.paddle.w / 2)) / (this.paddle.w / 2)
      const angle = collidePoint * (Math.PI / 3) // до ±60°
      const speed = this._ballSpeedForLevel(this.level)
      b.dx = speed * Math.sin(angle)
      b.dy = -Math.abs(speed * Math.cos(angle))
    }

    // низ — потеря жизни
    if (b.y - b.radius > this.height) {
      this._loseLife()
    }
  }

  private _brickCollisions(): void {
    const b = this.ball
    for (const brick of this.bricks) {
      if (!brick.alive) continue
      if (
        b.x + b.radius > brick.x &&
        b.x - b.radius < brick.x + brick.w &&
        b.y + b.radius > brick.y &&
        b.y - b.radius < brick.y + brick.h
      ) {
        brick.hits++
        this.score += 10 * this.level
        if (brick.hits >= brick.maxHits) {
          brick.alive = false
          this._spawnParticles(brick.x + brick.w / 2, brick.y + brick.h / 2, BRICK_ROW_COLORS[brick.colorIdx % BRICK_ROW_COLORS.length] ?? '#999999')
        }

        const overlapX = b.x < brick.x + brick.w / 2
          ? b.x + b.radius - brick.x
          : brick.x + brick.w - (b.x - b.radius)
        const overlapY = b.y < brick.y + brick.h / 2
          ? b.y + b.radius - brick.y
          : brick.y + brick.h - (b.y - b.radius)

        if (overlapX < overlapY) {
          b.dx = -b.dx
          b.x = b.x < brick.x + brick.w / 2 ? brick.x - b.radius - 0.1 : brick.x + brick.w + b.radius + 0.1
        } else {
          b.dy = -b.dy
          b.y = b.y < brick.y + brick.h / 2 ? brick.y - b.radius - 0.1 : brick.y + brick.h + b.radius + 0.1
        }
        break // один кирпич за кадр — исходная механика Arkanoid так же считает по одному хиту
      }
    }
  }

  // ---------- rendering ----------

  private _render(): void {
    const ctx = this.ctx
    const w = this.width
    const h = this.height

    ctx.clearRect(0, 0, w, h)
    this._drawBackground(ctx, w, h)

    this._drawBricks(ctx)
    this._drawParticles(ctx)
    this._drawPaddle(ctx)
    this._drawBall(ctx)
    this._drawHud(ctx, w)

    if (this.state === 'level-intro') this._drawCenterText(ctx, w, h, `УРОВЕНЬ ${this.level}`, 'клик / пробел — бросить мяч')
    if (this.state === 'playing' && this.ball.onPaddle) this._drawCenterText(ctx, w, h, '', 'клик / пробел — бросить мяч')
    if (this.state === 'game-over') this._drawGameOver(ctx, w, h)
  }

  // Мягкий градиентный фон вместо "документной" страницы — нейтральный холст
  // под цветные спрайты Kenney, не спорит с цветами кирпичей.
  private _drawBackground(ctx: CanvasRenderingContext2D, w: number, h: number): void {
    const g = ctx.createLinearGradient(0, 0, 0, h)
    g.addColorStop(0, '#eaf4fb')
    g.addColorStop(1, '#d7e8f5')
    ctx.fillStyle = g
    ctx.fillRect(0, 0, w, h)
  }

  private _drawBricks(ctx: CanvasRenderingContext2D): void {
    ctx.save()
    for (const brick of this.bricks) {
      if (!brick.alive) continue
      const img = this._brickImgs[brick.colorIdx % this._brickImgs.length]
      if (img && isSpriteReady(img)) {
        ctx.drawImage(img, brick.x, brick.y, brick.w, brick.h)
      } else {
        ctx.fillStyle = '#9aa7b0'
        ctx.fillRect(brick.x, brick.y, brick.w, brick.h)
      }
      // крепкий кирпич после первого попадания — трещина поверх спрайта,
      // показывает, что кирпич ещё держится (maxHits > 1, hits уже есть)
      if (brick.maxHits > 1 && brick.hits > 0 && brick.hits < brick.maxHits) {
        ctx.save()
        ctx.globalAlpha = 0.55
        ctx.strokeStyle = '#2b2b2b'
        ctx.lineWidth = Math.max(1, brick.h / 14)
        ctx.beginPath()
        ctx.moveTo(brick.x + brick.w * 0.2, brick.y + brick.h * 0.15)
        ctx.lineTo(brick.x + brick.w * 0.45, brick.y + brick.h * 0.55)
        ctx.lineTo(brick.x + brick.w * 0.3, brick.y + brick.h * 0.85)
        ctx.moveTo(brick.x + brick.w * 0.45, brick.y + brick.h * 0.55)
        ctx.lineTo(brick.x + brick.w * 0.75, brick.y + brick.h * 0.35)
        ctx.stroke()
        ctx.restore()
      }
    }
    ctx.restore()
  }

  private _drawParticles(ctx: CanvasRenderingContext2D): void {
    if (this.particles.length === 0) return
    ctx.save()
    for (const p of this.particles) {
      const t = Math.max(0, p.life / p.maxLife)
      ctx.globalAlpha = t
      ctx.fillStyle = p.color
      const s = 3 + 3 * t
      ctx.fillRect(p.x - s / 2, p.y - s / 2, s, s)
    }
    ctx.restore()
  }

  private _drawPaddle(ctx: CanvasRenderingContext2D): void {
    const img = this._paddleImg
    if (isSpriteReady(img)) {
      ctx.drawImage(img, this.paddle.x, this.paddle.y, this.paddle.w, this.paddle.h)
    } else {
      ctx.save()
      ctx.fillStyle = '#3fa9d6'
      ctx.beginPath()
      const r = this.paddle.h / 2
      ctx.roundRect(this.paddle.x, this.paddle.y, this.paddle.w, this.paddle.h, r)
      ctx.fill()
      ctx.restore()
    }
  }

  private _drawBall(ctx: CanvasRenderingContext2D): void {
    const img = this._ballImg
    const d = this.ball.radius * 2
    if (isSpriteReady(img)) {
      ctx.drawImage(img, this.ball.x - this.ball.radius, this.ball.y - this.ball.radius, d, d)
    } else {
      ctx.save()
      ctx.fillStyle = '#e8e8e8'
      ctx.beginPath()
      ctx.arc(this.ball.x, this.ball.y, this.ball.radius, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()
    }
  }

  private _drawHud(ctx: CanvasRenderingContext2D, w: number): void {
    ctx.save()
    ctx.fillStyle = '#20343f'
    ctx.font = `700 14px ${HUD_FONT_FAMILY}`
    ctx.textAlign = 'left'
    ctx.textBaseline = 'alphabetic'
    ctx.fillText(`Уровень ${this.level}   Очки ${this.score}`, 14, 22)
    ctx.textAlign = 'right'
    ctx.fillText(`Рекорд ${this.best}`, w - 14, 22)
    ctx.restore()

    ctx.save()
    ctx.font = `700 14px ${HUD_FONT_FAMILY}`
    ctx.textAlign = 'left'
    ctx.fillStyle = '#20343f'
    let hearts = ''
    for (let i = 0; i < 3; i++) hearts += (i < this.lives ? '♥' : '♡') + ' '
    ctx.fillText(hearts.trim(), 14, 42)
    ctx.restore()
  }

  private _drawCenterText(ctx: CanvasRenderingContext2D, w: number, h: number, title: string, subtitle: string): void {
    ctx.save()
    ctx.textAlign = 'center'
    if (title) {
      ctx.fillStyle = '#20343f'
      ctx.font = `800 30px ${HUD_FONT_FAMILY}`
      ctx.fillText(title, w / 2, h / 2 - 8)
    }
    ctx.font = `500 13px ${HUD_FONT_FAMILY}`
    ctx.fillStyle = '#4c636f'
    ctx.fillText(subtitle, w / 2, h / 2 + (title ? 18 : 0))
    ctx.restore()
  }

  private _drawGameOver(ctx: CanvasRenderingContext2D, w: number, h: number): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.fillStyle = '#20343f'
    ctx.font = `800 24px ${HUD_FONT_FAMILY}`
    ctx.fillText('Игра окончена', w / 2, h / 2 - 30)
    ctx.font = `500 14px ${HUD_FONT_FAMILY}`
    ctx.fillText(`Очки ${this.score}   Рекорд ${this.best}`, w / 2, h / 2 - 4)

    const btnW = 170, btnH = 38
    const bx = w / 2 - btnW / 2, by = h / 2 + 16
    ctx.fillStyle = '#3fa9d6'
    ctx.beginPath()
    ctx.roundRect(bx, by, btnW, btnH, 8)
    ctx.fill()
    ctx.fillStyle = '#ffffff'
    ctx.font = `700 14px ${HUD_FONT_FAMILY}`
    ctx.fillText('Ещё раз', w / 2, by + btnH / 2 + 5)
    ctx.restore()

    this._gameOverBtnRect = { x: bx, y: by, w: btnW, h: btnH }
  }
}
