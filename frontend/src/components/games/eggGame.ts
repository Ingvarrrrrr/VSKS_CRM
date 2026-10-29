// Своя игра "Лови яйца" — ферма с медведем-ловцом в центре и 4 жёлобами
// (2 слева, 2 справа), по которым катятся яйца от куриц (идея — своя, без
// заимствования персонажей/названий у каких-либо конкретных игр).
//
// Персонаж стоит в центре и переключается между 4 позициями: TL (верх-лево),
// BL (низ-лево), TR (верх-право), BR (низ-право). Слева одна курица наверху
// кладёт яйца, которые едут по двум жёлобам: короткому — в TL, и длинному —
// дальше вниз, в BL. Справа симметрично курица и жёлоба в TR/BR.
//
// Графика — цветные спрайты Kenney (CC0, лицензия в sprites/egg/License-*.txt,
// см. также THIRD_PARTY_LICENSES.md): медведь и курица из "Animal Pack
// Remastered", яйцо — рендер из "Food Kit". Жёлоба, корзина, фон фермы и
// брызги от разбитого яйца — свой рисунок на canvas.
//
// EggGameWindow.vue (если будет) создаёт контейнер и управляет жизненным
// циклом: constructor(container) → start() на открытии окна, destroy() на
// закрытии/unmount — та же схема, что у DuckShootGame/BrickGame.

import { loadSprite, isSpriteReady } from './spriteLoader'
import bearUrl from './sprites/egg/bear.png'
import chickenUrl from './sprites/egg/chicken.png'
import eggUrl from './sprites/egg/egg.png'

type ChuteId = 'TL' | 'BL' | 'TR' | 'BR'
type GameState = 'intro' | 'playing' | 'game-over'
type EggState = 'rolling' | 'broken'

const HUD_FONT_FAMILY = '"Segoe UI", system-ui, -apple-system, Roboto, sans-serif'

interface Point {
  x: number
  y: number
}

interface ChuteDef {
  hen: Point
  catchPoint: Point
  side: 'left' | 'right'
  totalSteps: number
}

interface Egg {
  id: string
  chute: ChuteId
  step: number
  tAccum: number
  state: EggState
  breakT: number
  spinSeed: number
}

interface FloatEffect {
  x: number
  y: number
  t: number
  duration: number
  text: string
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

const ALL_CHUTES: ChuteId[] = ['TL', 'BL', 'TR', 'BR']
const MISS_LIMIT = 3
const EGG_BREAK_DURATION = 0.45

export class EggGame {
  private canvas: HTMLCanvasElement
  private ctx: CanvasRenderingContext2D

  private dpr = 1
  private width = 0
  private height = 0

  private running = false
  private rafId: number | null = null
  private lastTime = 0

  private state: GameState = 'intro'
  private stateTimer = 0

  private score = 0
  private best: number
  private misses = 0
  // Сколько прощений по правилу "каждые 100 очков — минус 1 промах" уже
  // применено — единственное место, где считается (Правило №6): _applyForgiveness
  // читает отсюда и отсюда же обновляет, остальной код не трогает эту логику.
  private _forgivenessApplied = 0

  // Текущая позиция ловца — единственный источник (Правило №6): рендер персонажа
  // и проверка "попал/промахнулся" при прибытии яйца читают это поле.
  private slot: ChuteId = 'TL'

  private eggs: Egg[] = []
  private spawnTimer = 0
  private effects: FloatEffect[] = []

  private chutes: Record<ChuteId, ChuteDef>
  private center: Point = { x: 0, y: 0 }

  private pointer: Pointer = { x: -9999, y: -9999, active: false }

  // Спрайты — общий загрузчик (Правило №6: один механизм на все игры), сам
  // EggGame только читает isSpriteReady и рисует запасные фигуры, пока не готово.
  private _bearImg = loadSprite(bearUrl)
  private _chickenImg = loadSprite(chickenUrl)
  private _eggImg = loadSprite(eggUrl)

  private _bgCanvas: HTMLCanvasElement | null = null

  private _gameOverBtnRect: Rect | null = null
  private _wasRunning = false
  private _onEscape: (() => void) | null = null

  private _onResize: () => void
  private _onVisibility: () => void
  private _onPointerMove: (e: PointerEvent) => void
  private _onPointerDown: (e: PointerEvent) => void
  private _onPointerLeave: () => void
  private _onKeyDown: (e: KeyboardEvent) => void

  constructor(containerEl: HTMLElement) {
    const existing = containerEl.querySelector('canvas')
    this.canvas = existing || document.createElement('canvas')
    if (!this.canvas.parentElement) containerEl.appendChild(this.canvas)
    const ctx = this.canvas.getContext('2d')
    if (!ctx) throw new Error('EggGame: canvas 2d context unavailable')
    this.ctx = ctx

    this.best = this._loadBest()
    this.chutes = this._computeChutes()

    this._onResize = () => this._resize()
    this._onVisibility = () => {
      if (document.hidden) {
        this._wasRunning = this.running
      } else if (this._wasRunning) {
        this.lastTime = performance.now()
      }
    }
    this._onPointerMove = (e: PointerEvent) => {
      this._updatePointer(e)
      if (this.pointer.active && this.state === 'playing') {
        this.slot = this._quadrantAt(this.pointer.x, this.pointer.y)
      }
    }
    this._onPointerDown = (e: PointerEvent) => {
      this._updatePointer(e)
      this._handleTap(this.pointer.x, this.pointer.y)
    }
    this._onPointerLeave = () => {
      this.pointer.active = false
    }
    this._onKeyDown = (e: KeyboardEvent) => this._handleKeyDown(e)

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
    this.canvas.removeEventListener('pointermove', this._onPointerMove)
    this.canvas.removeEventListener('pointerdown', this._onPointerDown)
    this.canvas.removeEventListener('pointerleave', this._onPointerLeave)
    window.removeEventListener('keydown', this._onKeyDown)
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
  }

  private _updatePointer(e: PointerEvent): void {
    const rect = this.canvas.getBoundingClientRect()
    this.pointer.x = e.clientX - rect.left
    this.pointer.y = e.clientY - rect.top
    this.pointer.active = true
  }

  // 4 касательные зоны — просто четверти холста, без видимой разметки.
  private _quadrantAt(x: number, y: number): ChuteId {
    const left = x < this.width / 2
    const top = y < this.height / 2
    if (left && top) return 'TL'
    if (left && !top) return 'BL'
    if (!left && top) return 'TR'
    return 'BR'
  }

  private _handleKeyDown(e: KeyboardEvent): void {
    if (e.key === 'Escape' && this._onEscape) { this._onEscape(); return }
    if (e.key === 'Enter') {
      if (this.state === 'game-over') { this._restartGame(); return }
    }

    const arrowKeys = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown']
    if (this.state === 'playing' && arrowKeys.includes(e.key)) e.preventDefault()
    if (this.state !== 'playing') return

    const key = e.key.toLowerCase()
    // Q/A/P/L — четыре прямых клавиши-позиции (расклад как на старых карманных
    // играх: Q верх-лево, A низ-лево, P верх-право, L низ-право).
    if (key === 'q') { this.slot = 'TL'; return }
    if (key === 'a') { this.slot = 'BL'; return }
    if (key === 'p') { this.slot = 'TR'; return }
    if (key === 'l') { this.slot = 'BR'; return }

    // Стрелки/W-S-A-D — независимо переключают горизонталь и вертикаль
    // текущей позиции (комбо ←↑/→↓ и W/S + A/D из задания).
    const h = this.slot === 'TL' || this.slot === 'BL' ? 'left' : 'right'
    const v = this.slot === 'TL' || this.slot === 'TR' ? 'top' : 'bottom'
    let nh = h
    let nv = v
    if (e.key === 'ArrowLeft') nh = 'left'
    else if (e.key === 'ArrowRight') nh = 'right'
    else if (e.key === 'ArrowUp') nv = 'top'
    else if (e.key === 'ArrowDown') nv = 'bottom'
    else if (key === 'd') nh = 'right'
    else if (key === 'w') nv = 'top'
    else if (key === 's') nv = 'bottom'
    else return
    this.slot = nh === 'left'
      ? (nv === 'top' ? 'TL' : 'BL')
      : (nv === 'top' ? 'TR' : 'BR')
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
    // Без этого на экранах с devicePixelRatio > 1 canvas без CSS-размера
    // раздувается до своих пиксельных width/height атрибутов и вылезает за
    // рамки контейнера (тот же случай, что у DuckShootGame/BrickGame — см. их _resize).
    this.canvas.style.width = `${this.width}px`
    this.canvas.style.height = `${this.height}px`
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    this.chutes = this._computeChutes()
    this._bgCanvas = this._buildFarmBackground(this.width, this.height, this.dpr)
  }

  // Геометрия 4 жёлобов — единственное место, где считается (Правило №6);
  // _update (движение яиц) и рендер читают отсюда, а не пересчитывают сами.
  private _computeChutes(): Record<ChuteId, ChuteDef> {
    const w = this.width
    const h = this.height
    const henL: Point = { x: w * 0.08, y: h * 0.16 }
    const henR: Point = { x: w * 0.92, y: h * 0.16 }
    const totalSteps = 9
    const chutes: Record<ChuteId, ChuteDef> = {
      TL: { hen: henL, catchPoint: { x: w * 0.40, y: h * 0.40 }, side: 'left', totalSteps },
      BL: { hen: henL, catchPoint: { x: w * 0.40, y: h * 0.64 }, side: 'left', totalSteps },
      TR: { hen: henR, catchPoint: { x: w * 0.60, y: h * 0.40 }, side: 'right', totalSteps },
      BR: { hen: henR, catchPoint: { x: w * 0.60, y: h * 0.64 }, side: 'right', totalSteps },
    }
    // Ловец стоит ровно в центре между концами всех 4 жёлобов — симметрично
    // по 2 слева/справа (требование владельца), единственное место расчёта.
    this.center = {
      x: (chutes.TL.catchPoint.x + chutes.TR.catchPoint.x) / 2,
      y: (chutes.TL.catchPoint.y + chutes.BL.catchPoint.y) / 2,
    }
    return chutes
  }

  private _loadBest(): number {
    try {
      const v = localStorage.getItem('gala_egg_best')
      return v ? parseInt(v, 10) || 0 : 0
    } catch {
      return 0
    }
  }

  private _saveBest(): void {
    try {
      localStorage.setItem('gala_egg_best', String(this.best))
    } catch {
      /* ignore */
    }
  }

  // ---------- game flow ----------

  private _handleTap(x: number, y: number): void {
    if (this.state === 'game-over') {
      const r = this._gameOverBtnRect
      if (r && x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) {
        this._restartGame()
      }
      return
    }
    if (this.state === 'playing') this.slot = this._quadrantAt(x, y)
  }

  private _restartGame(): void {
    this.score = 0
    this.misses = 0
    this._forgivenessApplied = 0
    this.eggs = []
    this.effects = []
    this.spawnTimer = 0
    this.slot = 'TL'
    this.state = 'intro'
    this.stateTimer = 0
  }

  // Скорость шага яйца (с/шаг) и интервал между спавнами — единственные места,
  // где считаются (Правило №6); растут (уменьшаются интервалы) со счётом.
  private _stepInterval(): number {
    return Math.max(0.085, 0.22 - this.score * 0.0006)
  }

  private _spawnInterval(): number {
    return Math.max(0.45, 1.5 - this.score * 0.0035)
  }

  private _spawnEgg(): void {
    const free = ALL_CHUTES.filter(id => !this.eggs.some(e => e.chute === id && e.state === 'rolling'))
    if (free.length === 0) return
    const chute = free[Math.floor(Math.random() * free.length)] as ChuteId
    this.eggs.push({
      id: Math.random().toString(36).slice(2),
      chute,
      step: 0,
      tAccum: 0,
      state: 'rolling',
      breakT: 0,
      spinSeed: Math.random() < 0.5 ? -1 : 1,
    })
  }

  private _applyForgiveness(): void {
    const earned = Math.floor(this.score / 100)
    if (earned > this._forgivenessApplied) {
      const diff = earned - this._forgivenessApplied
      this._forgivenessApplied = earned
      this.misses = Math.max(0, this.misses - diff)
    }
  }

  private _registerCatch(egg: Egg): void {
    this.score += 1
    this.best = Math.max(this.best, this.score)
    this._saveBest()
    this._applyForgiveness()
    const p = this.chutes[egg.chute].catchPoint
    this.effects.push({ x: p.x, y: p.y, t: 0, duration: 0.8, text: '+1' })
  }

  private _registerMiss(egg: Egg): void {
    egg.state = 'broken'
    egg.breakT = 0
    this.misses++
    if (this.misses >= MISS_LIMIT && this.state === 'playing') {
      this.best = Math.max(this.best, this.score)
      this._saveBest()
      this.state = 'game-over'
    }
  }

  // ---------- update ----------

  private _loop = (now: number): void => {
    if (!this.running) return
    const dt = Math.min(0.05, (now - this.lastTime) / 1000)
    this.lastTime = now

    if (!document.hidden) this._update(dt)
    this._render()

    this.rafId = requestAnimationFrame(this._loop)
  }

  private _update(dt: number): void {
    for (const fx of this.effects) fx.t += dt
    this.effects = this.effects.filter(fx => fx.t < fx.duration)

    if (this.state === 'intro') {
      this.stateTimer += dt
      if (this.stateTimer > 0.9) {
        this.stateTimer = 0
        this.state = 'playing'
      }
      return
    }

    if (this.state === 'game-over') return

    // яйца, едущие по жёлобу — дискретные шаги по таймеру
    const stepInterval = this._stepInterval()
    for (const egg of this.eggs) {
      if (egg.state !== 'rolling') continue
      egg.tAccum += dt
      while (egg.tAccum >= stepInterval && egg.state === 'rolling') {
        egg.tAccum -= stepInterval
        egg.step++
        const def = this.chutes[egg.chute]
        if (egg.step >= def.totalSteps) {
          if (this.slot === egg.chute) this._registerCatch(egg)
          else this._registerMiss(egg)
          break
        }
      }
    }

    // разбитые яйца — короткая анимация, потом исчезают
    for (const egg of this.eggs) {
      if (egg.state === 'broken') egg.breakT += dt
    }
    this.eggs = this.eggs.filter(e => e.state === 'rolling' || e.breakT < EGG_BREAK_DURATION)

    this.spawnTimer -= dt
    if (this.spawnTimer <= 0) {
      this._spawnEgg()
      this.spawnTimer = this._spawnInterval()
    }
  }

  // ---------- rendering ----------

  private _eggPos(egg: Egg): Point {
    const def = this.chutes[egg.chute]
    const t = Math.min(1, egg.step / def.totalSteps)
    return {
      x: def.hen.x + (def.catchPoint.x - def.hen.x) * t,
      y: def.hen.y + (def.catchPoint.y - def.hen.y) * t,
    }
  }

  // Офскрин-фон фермы (небо + трава) — считается один раз на resize, как и
  // у остальных игр окна ожидания, но свой (без заимствования docBackground,
  // который для "документной" чёрно-белой механики, а здесь цветная ферма).
  private _buildFarmBackground(width: number, height: number, dpr: number): HTMLCanvasElement {
    const off = document.createElement('canvas')
    const w = Math.max(1, width)
    const h = Math.max(1, height)
    off.width = Math.max(1, Math.round(w * dpr))
    off.height = Math.max(1, Math.round(h * dpr))
    const c = off.getContext('2d')
    if (!c) return off
    c.setTransform(dpr, 0, 0, dpr, 0, 0)

    const horizon = h * 0.78
    const sky = c.createLinearGradient(0, 0, 0, horizon)
    sky.addColorStop(0, '#8fd3f4')
    sky.addColorStop(1, '#d7f0ff')
    c.fillStyle = sky
    c.fillRect(0, 0, w, horizon)

    // облака — мягкие овалы
    c.fillStyle = 'rgba(255,255,255,0.85)'
    const clouds: Array<[number, number, number]> = [
      [w * 0.18, h * 0.12, 22], [w * 0.24, h * 0.12, 16],
      [w * 0.78, h * 0.09, 18], [w * 0.84, h * 0.1, 13],
    ]
    for (const [cx, cy, r] of clouds) {
      c.beginPath()
      c.ellipse(cx, cy, r, r * 0.62, 0, 0, Math.PI * 2)
      c.fill()
    }

    const grass = c.createLinearGradient(0, horizon, 0, h)
    grass.addColorStop(0, '#8fd14f')
    grass.addColorStop(1, '#6cb23a')
    c.fillStyle = grass
    c.fillRect(0, horizon, w, h - horizon)

    // линия забора вдоль горизонта — простые деревянные столбики и жердь
    c.strokeStyle = '#a9733f'
    c.lineWidth = Math.max(2, h * 0.006)
    c.beginPath()
    c.moveTo(0, horizon + 6)
    c.lineTo(w, horizon + 6)
    c.stroke()
    const postW = Math.max(3, w * 0.01)
    const postH = h * 0.05
    for (let x = w * 0.04; x < w; x += w * 0.11) {
      c.fillStyle = '#8a5a30'
      c.fillRect(x - postW / 2, horizon - postH * 0.3, postW, postH)
    }

    return off
  }

  private _render(): void {
    const ctx = this.ctx
    const w = this.width
    const h = this.height

    ctx.clearRect(0, 0, w, h)
    if (this._bgCanvas && this._bgCanvas.width > 0) {
      ctx.drawImage(this._bgCanvas, 0, 0, w, h)
    } else {
      ctx.fillStyle = '#d7f0ff'
      ctx.fillRect(0, 0, w, h)
    }

    this._drawChutes(ctx)
    this._drawHens(ctx)
    this._drawEggs(ctx)
    this._drawCharacter(ctx)
    for (const fx of this.effects) this._drawEffect(ctx, fx)
    this._drawHud(ctx, w)

    if (this.state === 'intro') this._drawCenterText(ctx, w, h, 'ГОТОВЬТЕСЬ')
    if (this.state === 'game-over') this._drawGameOver(ctx, w, h)
  }

  // Деревянные жёлоба — скруглённые доски от курицы к точке ловли, с
  // бортиками и светлой канавкой посередине, куда "вложено" катящееся яйцо.
  private _drawChutes(ctx: CanvasRenderingContext2D): void {
    ctx.save()
    for (const id of ALL_CHUTES) {
      const def = this.chutes[id]
      const dx = def.catchPoint.x - def.hen.x
      const dy = def.catchPoint.y - def.hen.y
      const len = Math.hypot(dx, dy)
      const angle = Math.atan2(dy, dx)
      const plankW = Math.max(14, this.width * 0.045)

      ctx.save()
      ctx.translate(def.hen.x, def.hen.y)
      ctx.rotate(angle)

      // доска
      ctx.fillStyle = '#b5793f'
      this._roundRectPath(ctx, 0, -plankW / 2, len, plankW, plankW * 0.3)
      ctx.fill()
      ctx.strokeStyle = '#8a5a30'
      ctx.lineWidth = 2
      ctx.stroke()

      // канавка посередине
      ctx.fillStyle = '#d9a86a'
      this._roundRectPath(ctx, len * 0.03, -plankW * 0.16, len * 0.94, plankW * 0.32, plankW * 0.14)
      ctx.fill()

      ctx.restore()
    }
    ctx.restore()
  }

  private _roundRectPath(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
    const rr = Math.min(r, w / 2, h / 2)
    ctx.beginPath()
    ctx.moveTo(x + rr, y)
    ctx.arcTo(x + w, y, x + w, y + h, rr)
    ctx.arcTo(x + w, y + h, x, y + h, rr)
    ctx.arcTo(x, y + h, x, y, rr)
    ctx.arcTo(x, y, x + w, y, rr)
    ctx.closePath()
  }

  // Курицы на верхних концах жёлобов — круглый вариант спрайта (Round) сам по
  // себе без фоновой "карточки" (кадрирован в круг, не квадрат), подложка не нужна.
  private _drawHens(ctx: CanvasRenderingContext2D): void {
    const size = Math.max(34, this.width * 0.07)
    const hens = [this.chutes.TL.hen, this.chutes.TR.hen]
    for (const p of hens) {
      this._drawSprite(ctx, this._chickenImg, p.x, p.y, size, () => {
        ctx.save()
        ctx.fillStyle = '#ffffff'
        ctx.beginPath()
        ctx.ellipse(p.x, p.y, size * 0.4, size * 0.4, 0, 0, Math.PI * 2)
        ctx.fill()
        ctx.fillStyle = '#e03a2f'
        ctx.beginPath()
        ctx.ellipse(p.x, p.y - size * 0.3, size * 0.16, size * 0.2, 0, 0, Math.PI * 2)
        ctx.fill()
        ctx.restore()
      })
    }
  }

  private _drawEggs(ctx: CanvasRenderingContext2D): void {
    const size = Math.max(34, this.width * 0.045)
    for (const egg of this.eggs) {
      if (egg.state === 'rolling') {
        const p = this._eggPos(egg)
        const rot = egg.spinSeed * egg.step * 0.9
        ctx.save()
        ctx.translate(p.x, p.y)
        ctx.rotate(rot)
        if (isSpriteReady(this._eggImg)) {
          ctx.drawImage(this._eggImg, -size / 2, -size / 2, size, size)
        } else {
          ctx.fillStyle = '#fdf6e3'
          ctx.strokeStyle = '#d8c48a'
          ctx.lineWidth = 1.5
          ctx.beginPath()
          ctx.ellipse(0, 0, size * 0.38, size * 0.48, 0, 0, Math.PI * 2)
          ctx.fill()
          ctx.stroke()
        }
        ctx.restore()
      } else {
        this._drawSplat(ctx, egg)
      }
    }
  }

  // Брызги разбитого яйца — растекающееся жёлто-белое пятно, затухает.
  private _drawSplat(ctx: CanvasRenderingContext2D, egg: Egg): void {
    const p = this.chutes[egg.chute].catchPoint
    const prog = egg.breakT / EGG_BREAK_DURATION
    const spread = 14 + prog * 20
    ctx.save()
    ctx.globalAlpha = Math.max(0, 1 - prog)
    ctx.fillStyle = '#fffaf0'
    ctx.beginPath()
    ctx.ellipse(p.x, p.y + 6, spread, spread * 0.42, 0, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = '#f2c94c'
    ctx.beginPath()
    ctx.ellipse(p.x, p.y + 6, spread * 0.4, spread * 0.22, 0, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()
  }

  // Медведь стоит в центре (симметрично между всеми 4 жёлобами) на круглой
  // голове-спрайте (Round, без "карточки") и нарисованном на canvas теле,
  // слегка наклоняется в сторону текущей позиции; рука тянется к корзине,
  // которая едет точно к концу активного жёлоба — туда, где должно поймать яйцо.
  private _drawCharacter(ctx: CanvasRenderingContext2D): void {
    const target = this.chutes[this.slot].catchPoint
    const lean = 0.22
    const bx = this.center.x + (target.x - this.center.x) * lean
    const by = this.center.y + (target.y - this.center.y) * lean
    const bearSize = Math.max(46, this.width * 0.1)
    const tiltX = target.x < this.center.x ? -1 : 1
    const headY = by - bearSize * 0.18
    const bodyY = by + bearSize * 0.42

    ctx.save()
    ctx.translate(bx, by)
    ctx.rotate(tiltX * 0.05)
    ctx.translate(-bx, -by)

    // рука — от тела к корзине у конца жёлоба
    ctx.strokeStyle = '#9a6a3a'
    ctx.lineWidth = Math.max(8, bearSize * 0.16)
    ctx.lineCap = 'round'
    ctx.beginPath()
    ctx.moveTo(bx + tiltX * bearSize * 0.3, bodyY - bearSize * 0.1)
    ctx.lineTo(target.x, target.y)
    ctx.stroke()

    // тело — скруглённый силуэт под головой
    ctx.fillStyle = '#a9733f'
    this._roundRectPath(ctx, bx - bearSize * 0.38, bodyY - bearSize * 0.3, bearSize * 0.76, bearSize * 0.68, bearSize * 0.3)
    ctx.fill()
    ctx.strokeStyle = '#8a5a30'
    ctx.lineWidth = 2
    ctx.stroke()
    // светлое пузико
    ctx.fillStyle = '#d9b27a'
    ctx.beginPath()
    ctx.ellipse(bx, bodyY + bearSize * 0.06, bearSize * 0.2, bearSize * 0.24, 0, 0, Math.PI * 2)
    ctx.fill()

    // голова — спрайт Kenney поверх тела
    this._drawSprite(ctx, this._bearImg, bx, headY, bearSize, () => {
      ctx.save()
      ctx.fillStyle = '#9a6a3a'
      ctx.beginPath()
      ctx.ellipse(bx, headY, bearSize * 0.4, bearSize * 0.42, 0, 0, Math.PI * 2)
      ctx.fill()
      ctx.fillStyle = '#efe3d3'
      ctx.beginPath()
      ctx.ellipse(bx - bearSize * 0.14, headY - bearSize * 0.02, bearSize * 0.08, bearSize * 0.1, 0, 0, Math.PI * 2)
      ctx.ellipse(bx + bearSize * 0.14, headY - bearSize * 0.02, bearSize * 0.08, bearSize * 0.1, 0, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()
    })
    ctx.restore()

    // корзина — прямо в точке ловли, на конце активного жёлоба
    this._drawBasket(ctx, target.x, target.y)
  }

  private _drawBasket(ctx: CanvasRenderingContext2D, x: number, y: number): void {
    const w = Math.max(28, this.width * 0.062)
    const h = w * 0.62
    ctx.save()
    ctx.translate(x, y)

    ctx.fillStyle = '#c98a44'
    this._roundRectPath(ctx, -w / 2, -h / 2, w, h, h * 0.22)
    ctx.fill()
    ctx.strokeStyle = '#8a5a30'
    ctx.lineWidth = 1.5
    ctx.stroke()

    // плетение
    ctx.strokeStyle = '#a9733f'
    ctx.lineWidth = 1
    for (let i = 1; i < 4; i++) {
      const lx = -w / 2 + (w / 4) * i
      ctx.beginPath()
      ctx.moveTo(lx, -h / 2 + 2)
      ctx.lineTo(lx, h / 2 - 2)
      ctx.stroke()
    }

    // ручка
    ctx.strokeStyle = '#8a5a30'
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.arc(0, -h / 2, w * 0.32, Math.PI, 0)
    ctx.stroke()

    ctx.restore()
  }

  // Рисует спрайт по центру в квадрат side×side (вписывая с сохранением
  // пропорций); пока спрайт не загрузился — вызывает fallback-рисование фигур.
  private _drawSprite(
    ctx: CanvasRenderingContext2D,
    img: HTMLImageElement,
    cx: number,
    cy: number,
    side: number,
    fallback: () => void,
  ): void {
    if (!isSpriteReady(img)) {
      fallback()
      return
    }
    const scale = side / Math.max(img.naturalWidth, img.naturalHeight)
    const dw = img.naturalWidth * scale
    const dh = img.naturalHeight * scale
    ctx.drawImage(img, cx - dw / 2, cy - dh / 2, dw, dh)
  }

  private _drawEffect(ctx: CanvasRenderingContext2D, fx: FloatEffect): void {
    const prog = fx.t / fx.duration
    ctx.save()
    ctx.globalAlpha = 1 - prog
    ctx.fillStyle = '#2e7d32'
    ctx.font = `700 15px ${HUD_FONT_FAMILY}`
    ctx.textAlign = 'center'
    ctx.fillText(fx.text, fx.x, fx.y - prog * 28)
    ctx.restore()
  }

  private _drawHud(ctx: CanvasRenderingContext2D, w: number): void {
    ctx.save()
    ctx.fillStyle = 'rgba(255,255,255,0.78)'
    this._roundRectPath(ctx, 8, 6, Math.min(w - 16, 330), 30, 8)
    ctx.fill()

    ctx.fillStyle = '#2b2b2b'
    ctx.font = `700 13px ${HUD_FONT_FAMILY}`
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    ctx.fillText(`Очки ${this.score}   Рекорд ${this.best}`, 18, 21)

    // промахи — мелкие иконки яйца, разбитый промах темнее/перечёркнут
    const eggIconSize = 14
    let ex = w - 18 - MISS_LIMIT * (eggIconSize + 6)
    ex = Math.max(ex, 180)
    for (let i = 0; i < MISS_LIMIT; i++) {
      const x = ex + i * (eggIconSize + 6)
      const y = 21
      const used = i < this.misses
      ctx.save()
      ctx.globalAlpha = used ? 0.35 : 1
      if (isSpriteReady(this._eggImg)) {
        ctx.drawImage(this._eggImg, x, y - eggIconSize / 2, eggIconSize, eggIconSize)
      } else {
        ctx.fillStyle = '#fdf6e3'
        ctx.beginPath()
        ctx.ellipse(x + eggIconSize / 2, y, eggIconSize * 0.4, eggIconSize * 0.5, 0, 0, Math.PI * 2)
        ctx.fill()
      }
      if (used) {
        ctx.strokeStyle = '#c0392b'
        ctx.lineWidth = 2
        ctx.beginPath()
        ctx.moveTo(x, y - eggIconSize / 2)
        ctx.lineTo(x + eggIconSize, y + eggIconSize / 2)
        ctx.stroke()
      }
      ctx.restore()
    }
    ctx.restore()
  }

  private _drawCenterText(ctx: CanvasRenderingContext2D, w: number, h: number, title: string): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.fillStyle = '#ffffff'
    ctx.strokeStyle = '#2b2b2b'
    ctx.lineWidth = 4
    ctx.font = `800 28px ${HUD_FONT_FAMILY}`
    ctx.strokeText(title, w / 2, h / 2 - 8)
    ctx.fillText(title, w / 2, h / 2 - 8)
    ctx.restore()
  }

  private _drawGameOver(ctx: CanvasRenderingContext2D, w: number, h: number): void {
    ctx.save()
    ctx.fillStyle = 'rgba(255,255,255,0.88)'
    this._roundRectPath(ctx, w / 2 - 150, h / 2 - 70, 300, 150, 14)
    ctx.fill()

    ctx.textAlign = 'center'
    ctx.fillStyle = '#2b2b2b'
    ctx.font = `800 22px ${HUD_FONT_FAMILY}`
    ctx.fillText('Игра окончена', w / 2, h / 2 - 32)
    ctx.font = `14px ${HUD_FONT_FAMILY}`
    ctx.fillText(`Очки ${this.score}   Рекорд ${this.best}`, w / 2, h / 2 - 4)

    const btnW = 160, btnH = 36
    const bx = w / 2 - btnW / 2, by = h / 2 + 16
    ctx.fillStyle = '#6cb23a'
    this._roundRectPath(ctx, bx, by, btnW, btnH, 8)
    ctx.fill()
    ctx.fillStyle = '#ffffff'
    ctx.font = `700 14px ${HUD_FONT_FAMILY}`
    ctx.fillText('Ещё раз', w / 2, by + btnH / 2 + 5)
    ctx.restore()

    this._gameOverBtnRect = { x: bx, y: by, w: btnW, h: btnH }
  }
}
