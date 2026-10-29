// Своя игра "Лови яйца" — чёрно-белая "документная" механика в духе классических
// карманных электронных игр (4 положения ловца, яйца едут по жёлобам ступенями),
// без заимствования персонажей/названий у каких-либо конкретных игр.
// Ссылка-референс для понимания механики (НЕ код, НЕ текст — только идея):
// https://github.com/lil-zon/egg-catcher-rl (All rights reserved у автора, идеи
// не защищены копирайтом) — реализация здесь написана с нуля, своя разметка,
// свой рендер, свой персонаж (медведь в галстуке с корзиной, не волк).
//
// Персонаж стоит в центре и переключается между 4 позициями: TL (верх-лево),
// BL (низ-лево), TR (верх-право), BR (низ-право). Слева одна курица наверху
// кладёт яйца, которые едут по двум жёлобам ("╲"): короткому — в TL, и
// длинному — дальше вниз, в BL. Справа симметрично курица и жёлоба "╱" в TR/BR.
// Общий стиль/фон/шрифт — тот же модуль docBackground.ts, что у DuckShootGame
// и BrickGame (Правило №6: один источник для "документного" фона).
//
// EggGameWindow.vue (если будет) создаёт контейнер и управляет жизненным
// циклом: constructor(container) → start() на открытии окна, destroy() на
// закрытии/unmount — та же схема, что у DuckShootGame/BrickGame.

import { buildDocumentBackground, DOC_BG_FONT_FAMILY } from './docBackground'

type ChuteId = 'TL' | 'BL' | 'TR' | 'BR'
type GameState = 'intro' | 'playing' | 'game-over'
type EggState = 'rolling' | 'broken'

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
  glyphSeed: number
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

  private pointer: Pointer = { x: -9999, y: -9999, active: false }

  private glyphFontFamily = DOC_BG_FONT_FAMILY
  private _docBg: HTMLCanvasElement | null = null

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
    this._docBg = buildDocumentBackground(this.width, this.height, this.dpr)
    this.chutes = this._computeChutes()
  }

  // Геометрия 4 жёлобов — единственное место, где считается (Правило №6);
  // _update (движение яиц) и рендер читают отсюда, а не пересчитывают сами.
  private _computeChutes(): Record<ChuteId, ChuteDef> {
    const w = this.width
    const h = this.height
    const henL: Point = { x: w * 0.08, y: h * 0.16 }
    const henR: Point = { x: w * 0.92, y: h * 0.16 }
    const totalSteps = 9
    return {
      TL: { hen: henL, catchPoint: { x: w * 0.40, y: h * 0.40 }, side: 'left', totalSteps },
      BL: { hen: henL, catchPoint: { x: w * 0.40, y: h * 0.64 }, side: 'left', totalSteps },
      TR: { hen: henR, catchPoint: { x: w * 0.60, y: h * 0.40 }, side: 'right', totalSteps },
      BR: { hen: henR, catchPoint: { x: w * 0.60, y: h * 0.64 }, side: 'right', totalSteps },
    }
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
      glyphSeed: Math.floor(Math.random() * 997),
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

    this._drawChuteLines(ctx)
    this._drawHens(ctx)
    this._drawEggs(ctx)
    this._drawCharacter(ctx)
    for (const fx of this.effects) this._drawEffect(ctx, fx)
    this._drawHud(ctx, w)

    if (this.state === 'intro') this._drawCenterText(ctx, w, h, 'ГОТОВЬТЕСЬ')
    if (this.state === 'game-over') this._drawGameOver(ctx, w, h)
  }

  private _drawChuteLines(ctx: CanvasRenderingContext2D): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#111111'
    ctx.font = `700 14px ${this.glyphFontFamily}`
    for (const id of ALL_CHUTES) {
      const def = this.chutes[id]
      const glyph = def.side === 'left' ? '╲' : '╱'
      const dx = def.catchPoint.x - def.hen.x
      const dy = def.catchPoint.y - def.hen.y
      const dist = Math.hypot(dx, dy)
      const n = Math.max(2, Math.round(dist / 16))
      for (let i = 1; i < n; i++) {
        const t = i / n
        ctx.fillText(glyph, def.hen.x + dx * t, def.hen.y + dy * t)
      }
    }
    ctx.restore()
  }

  // Курицы на верхних концах жёлобов — маленькие птичьи силуэты из глифов.
  private _drawHens(ctx: CanvasRenderingContext2D): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#111111'
    const hens = [this.chutes.TL.hen, this.chutes.TR.hen]
    for (const p of hens) {
      ctx.font = `700 11px ${this.glyphFontFamily}`
      ctx.fillText('v', p.x, p.y - 10) // гребень
      ctx.font = `700 16px ${this.glyphFontFamily}`
      ctx.fillText('(0)', p.x, p.y)
    }
    ctx.restore()
  }

  private _drawEggs(ctx: CanvasRenderingContext2D): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    for (const egg of this.eggs) {
      if (egg.state === 'rolling') {
        const p = this._eggPos(egg)
        ctx.fillStyle = '#111111'
        ctx.font = `700 15px ${this.glyphFontFamily}`
        ctx.fillText(egg.glyphSeed % 2 === 0 ? '0' : 'О', p.x, p.y)
      } else {
        const p = this.chutes[egg.chute].catchPoint
        const prog = egg.breakT / EGG_BREAK_DURATION
        ctx.save()
        ctx.globalAlpha = Math.max(0, 1 - prog)
        ctx.fillStyle = '#111111'
        ctx.font = `700 18px ${this.glyphFontFamily}`
        ctx.fillText('※', p.x, p.y)
        ctx.restore()
      }
    }
    ctx.restore()
  }

  // Медведь в офисном галстуке с корзиной — собран из моноширинных глифов,
  // стоит в центре на текущей позиции (this.slot) и "перепрыгивает" между
  // 4 точками без промежуточной анимации — как в классических карманных играх.
  private _drawCharacter(ctx: CanvasRenderingContext2D): void {
    const p = this.chutes[this.slot].catchPoint
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#111111'

    ctx.font = `700 13px ${this.glyphFontFamily}`
    ctx.fillText('◠   ◠', p.x, p.y - 22) // уши
    ctx.font = `700 15px ${this.glyphFontFamily}`
    ctx.fillText('( • • )', p.x, p.y - 10) // голова/глаза
    ctx.font = `700 11px ${this.glyphFontFamily}`
    ctx.fillText('▼', p.x, p.y - 1) // узел галстука
    ctx.font = `700 14px ${this.glyphFontFamily}`
    ctx.fillText('[ § § ]', p.x, p.y + 11) // туловище/лапы держат корзину
    ctx.font = `700 17px ${this.glyphFontFamily}`
    ctx.fillText('\\_/', p.x, p.y + 25) // корзина

    ctx.restore()
  }

  private _drawEffect(ctx: CanvasRenderingContext2D, fx: FloatEffect): void {
    const prog = fx.t / fx.duration
    ctx.save()
    ctx.globalAlpha = 1 - prog
    ctx.fillStyle = '#111111'
    ctx.font = `700 14px ${this.glyphFontFamily}`
    ctx.textAlign = 'center'
    ctx.fillText(fx.text, fx.x, fx.y - prog * 28)
    ctx.restore()
  }

  private _drawHud(ctx: CanvasRenderingContext2D, _w: number): void {
    let marks = ''
    for (let i = 0; i < MISS_LIMIT; i++) marks += (i < this.misses ? '✕' : '·') + ' '
    ctx.save()
    ctx.fillStyle = '#111111'
    ctx.font = `700 13px ${this.glyphFontFamily}`
    ctx.textAlign = 'left'
    ctx.fillText(`ОЧКИ ${this.score}   РЕКОРД ${this.best}   ПРОМАХИ ${marks.trim()}`, 14, 22)
    ctx.restore()
  }

  private _drawCenterText(ctx: CanvasRenderingContext2D, w: number, h: number, title: string): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.fillStyle = '#111111'
    ctx.font = `700 26px ${this.glyphFontFamily}`
    ctx.fillText(title, w / 2, h / 2 - 8)
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
