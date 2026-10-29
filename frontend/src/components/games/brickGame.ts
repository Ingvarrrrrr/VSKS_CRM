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
// внешние ассеты и любые сетевые вызовы оригинала. Стиль отрисовки — свой,
// "документный" чёрно-белый, общий с DuckShootGame (см. docBackground.ts).
//
// BrickGameWindow.vue (внутри DuckShootWindow.vue) создаёт контейнер и
// управляет жизненным циклом: constructor(container) → start() на открытии
// окна, destroy() на закрытии/unmount — та же схема, что у DuckShootGame.

import { buildDocumentBackground, DOC_BG_FONT_FAMILY } from './docBackground'

type GameState = 'level-intro' | 'playing' | 'game-over'

interface Brick {
  x: number
  y: number
  w: number
  h: number
  word: string
  hits: number
  maxHits: number
  alive: boolean
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

// Слова, из которых набираются кирпичи — только документная лексика,
// без упоминания первоисточника игры (торговая марка держателя оригинала
// в UI не используется — см. ПРАВИЛО в задании).
const BRICK_WORDS = ['ДОГОВОР', 'СЧЁТ', 'АКТ', 'НДС', '2026', '№17', 'ИТОГО', 'ПЕНЯ']

const MAX_LEVELS = 15
const BASE_BALL_SPEED = 230
const LEVEL_SPEED_STEP = 18
const PADDLE_SPEED = 620 // px/sec, клавиатура

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
  private ball: Ball = { x: 0, y: 0, dx: 0, dy: 0, radius: 6, onPaddle: true }
  private bricks: Brick[] = []

  private _docBg: HTMLCanvasElement | null = null
  private glyphFontFamily = DOC_BG_FONT_FAMILY

  private _gameOverBtnRect: Rect | null = null
  private _wasRunning = false
  private _onEscape: (() => void) | null = null

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

    this.best = this._loadBest()

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
    this._docBg = buildDocumentBackground(this.width, this.height, this.dpr)

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

  private _loadBest(): number {
    try {
      const v = localStorage.getItem('gala_brick_best')
      return v ? parseInt(v, 10) || 0 : 0
    } catch {
      return 0
    }
  }

  private _saveBest(): void {
    try {
      localStorage.setItem('gala_brick_best', String(this.best))
    } catch {
      /* ignore */
    }
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
    let wordIdx = 0
    for (let r = 0; r < rows; r++) {
      // каждая третья строка — "крепкие" кирпичи (2 попадания), остальные — обычные
      const strongRow = r % 3 === 2
      for (let c = 0; c < cols; c++) {
        const word = BRICK_WORDS[wordIdx % BRICK_WORDS.length] ?? 'АКТ'
        wordIdx++
        const maxHits = strongRow ? 2 : 1
        this.bricks.push({
          x: offsetSide + c * (brickW + padding),
          y: offsetTop + r * (brickH + padding),
          w: brickW,
          h: brickH,
          word,
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
    return BASE_BALL_SPEED + (level - 1) * LEVEL_SPEED_STEP
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
    let angleDeg = 60 + Math.random() * 30 // 60..90° от горизонтали
    if (Math.random() < 0.5) angleDeg = -angleDeg
    const angleRad = (angleDeg * Math.PI) / 180
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
      this._saveBest()
      this.state = 'game-over'
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

    if (this.state === 'playing' && this._remainingBricks() === 0) {
      if (this.level >= MAX_LEVELS) {
        this.best = Math.max(this.best, this.score)
        this._saveBest()
        this.state = 'game-over'
      } else {
        this._nextLevel()
      }
    }
  }

  private _remainingBricks(): number {
    let n = 0
    for (const b of this.bricks) if (b.alive) n++
    return n
  }

  private _movePaddle(dt: number): void {
    const targetX = this.pointer.active ? this.pointer.x - this.paddle.w / 2 : null
    if (targetX != null) {
      this.paddle.x = targetX
    } else if (this.rightPressed) {
      this.paddle.x += PADDLE_SPEED * dt
    } else if (this.leftPressed) {
      this.paddle.x -= PADDLE_SPEED * dt
    }
    this.paddle.x = Math.max(0, Math.min(this.width - this.paddle.w, this.paddle.x))
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
        if (brick.hits >= brick.maxHits) brick.alive = false

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
    if (this._docBg && this._docBg.width > 0) {
      ctx.drawImage(this._docBg, 0, 0, w, h)
    } else {
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, w, h)
    }

    this._drawBricks(ctx)
    this._drawPaddle(ctx)
    this._drawBall(ctx)
    this._drawHud(ctx, w)

    if (this.state === 'level-intro') this._drawCenterText(ctx, w, h, `УРОВЕНЬ ${this.level}`, 'клик / пробел — бросить мяч')
    if (this.state === 'playing' && this.ball.onPaddle) this._drawCenterText(ctx, w, h, '', 'клик / пробел — бросить мяч')
    if (this.state === 'game-over') this._drawGameOver(ctx, w, h)
  }

  private _drawBricks(ctx: CanvasRenderingContext2D): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    for (const brick of this.bricks) {
      if (!brick.alive) continue
      const hitLeft = brick.maxHits - brick.hits
      ctx.fillStyle = '#111111'
      ctx.fillRect(brick.x, brick.y, brick.w, brick.h)
      // крепкий кирпич, ещё не тронутый — двойная белая рамка внутри (виден запас прочности)
      if (brick.maxHits > 1 && hitLeft > 1) {
        ctx.strokeStyle = '#ffffff'
        ctx.lineWidth = 1
        ctx.strokeRect(brick.x + 3, brick.y + 3, brick.w - 6, brick.h - 6)
      }
      const fontPx = Math.max(9, Math.min(13, brick.w / 7))
      ctx.font = `700 ${fontPx}px ${this.glyphFontFamily}`
      ctx.fillStyle = '#ffffff'
      ctx.fillText(brick.word, brick.x + brick.w / 2, brick.y + brick.h / 2 + 1)
    }
    ctx.restore()
  }

  private _drawPaddle(ctx: CanvasRenderingContext2D): void {
    ctx.save()
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#111111'
    const fontPx = Math.max(10, this.paddle.h)
    ctx.font = `700 ${fontPx}px ${this.glyphFontFamily}`
    // "[══════]" растянутый по ширине паддла глифами "═"
    const innerW = Math.max(1, this.paddle.w - fontPx)
    const barChar = '═'
    const barCharW = ctx.measureText(barChar).width || fontPx * 0.6
    const barCount = Math.max(1, Math.round(innerW / barCharW))
    const bar = barChar.repeat(barCount)
    ctx.fillText(`[${bar}]`, this.paddle.x, this.paddle.y + this.paddle.h / 2 + 1)
    ctx.restore()
  }

  private _drawBall(ctx: CanvasRenderingContext2D): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#111111'
    const fontPx = Math.max(10, this.ball.radius * 2.4)
    ctx.font = `700 ${fontPx}px ${this.glyphFontFamily}`
    ctx.fillText('●', this.ball.x, this.ball.y + 1)
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
    ctx.fillText(`ЖИЗНИ ${hearts.trim()}`, 14, 42)
    ctx.restore()
  }

  private _drawCenterText(ctx: CanvasRenderingContext2D, w: number, h: number, title: string, subtitle: string): void {
    ctx.save()
    ctx.textAlign = 'center'
    if (title) {
      ctx.fillStyle = '#111111'
      ctx.font = `700 30px ${this.glyphFontFamily}`
      ctx.fillText(title.toUpperCase(), w / 2, h / 2 - 8)
    }
    ctx.font = `13px ${this.glyphFontFamily}`
    ctx.fillStyle = '#444444'
    ctx.fillText(subtitle, w / 2, h / 2 + (title ? 18 : 0))
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
