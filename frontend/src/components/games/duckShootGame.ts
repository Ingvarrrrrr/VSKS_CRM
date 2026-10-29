// Порт класса DuckShootGame из прототипа
// (scratchpad/duck.html, <script> часть) — логика игры (жизни/волны/патроны/скорость
// от уровня/хиттест/DPR) сохранена без изменений. Отрисовка переведена с глифов на
// цветные PNG-спрайты Kenney (CC0, см. sprites/duck/License.txt и License-animal-pack.txt).
//
// DuckShootWindow.vue создаёт контейнер и управляет жизненным циклом:
// constructor(container) → start() на открытии окна, destroy() на закрытии/unmount.

import { loadSprite, isSpriteReady } from './spriteLoader'
import duckUrl from './sprites/duck/duck.png'
import duckHitUrl from './sprites/duck/duck_hit.png'
import duckBackUrl from './sprites/duck/duck_back.png'
import bgSkyUrl from './sprites/duck/bg_sky.png'
import grass1Url from './sprites/duck/grass1.png'
import grass2Url from './sprites/duck/grass2.png'
import cloud1Url from './sprites/duck/cloud1.png'
import cloud2Url from './sprites/duck/cloud2.png'
import treePineUrl from './sprites/duck/tree_pine.png'
import crosshairUrl from './sprites/duck/crosshair.png'
import bearUrl from './sprites/duck/bear.png'

// Читаемый sans-шрифт HUD/текстов — единственное место, где задан (Правило №6);
// весь текстовый рендер ниже читает отсюда, а не задаёт шрифт заново по месту.
const GAME_FONT = "'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"

type DuckState = 'flying' | 'hit' | 'escaping' | 'done'
type GameState = 'round-intro' | 'playing' | 'round-result' | 'game-over'

export interface Duck {
  id: string
  x: number
  y: number
  vx: number
  vy: number
  ampl: number
  freq: number
  phase: number
  wingPhase: number
  wingSpeed: number
  state: DuckState
  t: number
  scale: number
  rotation: number
  vrot: number
  vrotFall?: number
  size: number
}

export interface Bear {
  x: number
  y: number
  t: number
  duration: number
}

export interface Effect {
  type: 'ring' | 'float'
  x: number
  y: number
  t: number
  duration: number
  text?: string
}

interface Cloud {
  x: number
  y: number
  scale: number
  speed: number
  variant: 0 | 1
}

interface LaunchPoint {
  x: number
  fromBush: boolean
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

export class DuckShootGame {
  private canvas: HTMLCanvasElement
  private ctx: CanvasRenderingContext2D

  private dpr = 1
  private width = 0
  private height = 0

  private running = false
  private rafId: number | null = null
  private lastTime = 0

  private pointer: Pointer = { x: -9999, y: -9999, active: false }

  private state: GameState = 'round-intro'
  private level = 1
  private score = 0
  private best: number

  private lives = 3

  private waveSize = 1
  private waveHits = 0
  private _waveSpawnedCount = 0
  private wavesCompletedInLevel = 0

  private ammoPool = 0

  private ducks: Duck[] = []
  private bears: Bear[] = []
  private effects: Effect[] = []
  private clouds: Cloud[] = []

  private stateTimer = 0

  private _launchPoints: LaunchPoint[] = []

  // Высота травяной полосы (экранные px) — единственное место, где задаётся константа;
  // _grassBandTop()/_drawGrassBand()/_duckBottomBound() читают отсюда (Правило №6).
  private readonly GRASS_BAND_H = 50
  private _grassPhase = 0

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
    if (!ctx) throw new Error('DuckShootGame: canvas 2d context unavailable')
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
      this._handleShot(this.pointer.x, this.pointer.y)
    }
    this._onPointerLeave = () => {
      this.pointer.active = false
    }
    this._onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && this._onEscape) this._onEscape()
    }

    this._initClouds()
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

  private _resize(): void {
    const parent = this.canvas.parentElement
    if (!parent) return
    const rect = parent.getBoundingClientRect()
    this.dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1))
    this.width = Math.max(1, Math.round(rect.width))
    this.height = Math.max(1, Math.round(rect.height))
    this.canvas.width = Math.round(this.width * this.dpr)
    this.canvas.height = Math.round(this.height * this.dpr)
    // Без этого на экранах с devicePixelRatio > 1 (почти все ноутбуки/телефоны)
    // canvas без CSS-размера раздувается до своих пиксельных width/height
    // атрибутов и вылезает за рамки контейнера — обязательная пара к dpr-апскейлу выше.
    this.canvas.style.width = `${this.width}px`
    this.canvas.style.height = `${this.height}px`
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    this._launchPoints = this._computeLaunchPoints()
  }

  // Базовая линия земли — единственное место, где считается (Правило №6);
  // _drawGrassBand/_drawGroundScenery и _grassBandTop читают отсюда.
  private _groundY(): number {
    return this.height - 22
  }

  // Верх травяной полосы — единственное место, где считается; _drawGrassBand (отрисовка),
  // _duckBottomBound (граница отскока/вылета утки из травы) читают отсюда.
  private _grassBandTop(): number {
    return this._groundY() - this.GRASS_BAND_H
  }

  // Нижняя граница полёта утки / точка вылета из травы — единственное место, где считается
  // (Правило №6): _spawnDuck (старт внутри травы) и _update (отскок снизу) читают отсюда.
  private _duckBottomBound(): number {
    return this._grassBandTop() + this.GRASS_BAND_H * 0.5
  }

  private _computeLaunchPoints(): LaunchPoint[] {
    // точки вылета уток вдоль травы: разные x, плюс точка из-за дерева справа
    const fracs = [0.10, 0.25, 0.40, 0.60, 0.75, 0.90]
    const points: LaunchPoint[] = fracs.map((f) => ({ x: f * this.width, fromBush: false }))
    points.push({ x: this.width - 60, fromBush: true })
    return points
  }

  private _initClouds(): void {
    this.clouds = []
    for (let i = 0; i < 2; i++) {
      this.clouds.push({
        x: 0.15 + i * 0.55 + Math.random() * 0.1,
        y: 0.1 + Math.random() * 0.12,
        scale: 0.8 + Math.random() * 0.5,
        speed: 0.008 + Math.random() * 0.01,
        variant: Math.random() < 0.5 ? 0 : 1,
      })
    }
  }

  // ---------- game flow ----------

  // Размер волны (число уток, стартующих одновременно) зависит от уровня.
  // Единственное место, где это считается — остальной код читает this.waveSize.
  private _computeWaveSize(level?: number): number {
    const lvl = level != null ? level : this.level
    if (lvl <= 3) return 1
    if (lvl <= 6) return 2
    if (lvl <= 9) return 3
    return 4
  }

  // Патроны волны — правило владельца буквально: волна до 3 уток — 3 патрона всего;
  // каждая утка сверх 3 добавляет 1 патрон. Единственное место, где это считается.
  private _computeWaveAmmo(waveSize: number): number {
    return 3 + Math.max(0, waveSize - 3)
  }

  private _resetWaveState(): void {
    this.waveSize = this._computeWaveSize()
    this.ammoPool = this._computeWaveAmmo(this.waveSize)
    this.waveHits = 0
    this._waveSpawnedCount = 0
    this.ducks = []
  }

  private _startWave(): void {
    this._resetWaveState()
    this.state = 'playing'
    this._spawnWave()
  }

  // Все утки волны стартуют одновременно из разных точек вылета.
  private _spawnWave(): void {
    const basePoints = this._launchPoints && this._launchPoints.length
      ? this._launchPoints
      : this._computeLaunchPoints()
    const points = basePoints.slice()
    for (let i = points.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      const tmp = points[i]!; points[i] = points[j]!; points[j] = tmp
    }
    for (let i = 0; i < this.waveSize; i++) {
      this._spawnDuck(points[i % points.length])
    }
  }

  // Множитель скорости от уровня — единственное место, где считается (Правило №6);
  // _spawnDuck читает его, а не пересчитывает заново.
  private _speedMultiplier(): number {
    return 1 + 0.18 * (this.level - 1)
  }

  private _spawnDuck(launchPoint?: LaunchPoint): void {
    const baseSpeed = 70 * this._speedMultiplier()
    const fallbackPoint: LaunchPoint = { x: this.width / 2, fromBush: false }
    const lp = launchPoint || (this._launchPoints && this._launchPoints.length
      ? this._launchPoints[Math.floor(Math.random() * this._launchPoints.length)]
      : this._computeLaunchPoints()[0]) || fallbackPoint
    const dir = Math.random() < 0.5 ? 1 : -1
    const duck: Duck = {
      id: Math.random().toString(36).slice(2),
      x: lp.x,
      // утка стартует внутри травяной полосы (см. _grassBandTop) — вылетает из травы, не с чистой земли
      y: this._duckBottomBound(),
      vx: dir * (baseSpeed * (0.8 + Math.random() * 0.5)),
      vy: -(baseSpeed * (0.9 + Math.random() * 0.4)),
      ampl: 30 + Math.random() * 40,
      freq: 1.2 + Math.random() * 1.0,
      phase: Math.random() * Math.PI * 2,
      wingPhase: Math.random() * Math.PI * 2,
      wingSpeed: 9 + Math.random() * 3,
      state: 'flying',
      t: 0,
      scale: 1,
      rotation: 0,
      vrot: 0,
      size: 26,
    }
    this.ducks.push(duck)
    this._waveSpawnedCount++
  }

  private _handleShot(x: number, y: number): void {
    if (this.state === 'game-over') {
      const r = this._gameOverBtnRect
      if (r && x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) {
        this._restartGame()
      }
      return
    }
    if (this.state !== 'playing') return
    this.effects.push({ type: 'ring', x, y, t: 0, duration: 0.3 })

    if (this.ammoPool <= 0) return // пул патронов волны уже исчерпан

    // каждый клик — 1 потраченный патрон из общего пула волны, попал или не попал
    this.ammoPool--

    // Хиттест ОБЯЗАН совпадать с тем, что видит игрок: прямоугольник видимого спрайта
    // утки (_duckHitTest) с небольшим допуском по краю — единственное место, где
    // считается хит (остальной код просто читает результат).
    let target: Duck | null = null
    let bestDist = Infinity
    for (const d of this.ducks) {
      if (d.state !== 'flying') continue
      if (!this._duckHitTest(d, x, y)) continue
      const dist = Math.hypot(d.x - x, d.y - y)
      if (dist < bestDist) {
        bestDist = dist
        target = d
      }
    }

    if (target) {
      target.state = 'hit'
      target.vx = 0
      target.vy = -40
      target.vrotFall = 6 + Math.random() * 4
      target.t = 0
      this._registerHit(target)
    }

    if (this.ammoPool <= 0) {
      // патроны волны кончились — все ещё летящие утки улетают (каждая будет стоить жизнь)
      for (const d of this.ducks) {
        if (d.state === 'flying') {
          d.state = 'escaping'
          d.t = 0
        }
      }
    }
  }

  private _registerHit(duck: Duck): void {
    this.waveHits++
    const gained = 100 * this.level
    this.score += gained
    this.effects.push({ type: 'float', x: duck.x, y: duck.y, t: 0, duration: 1.0, text: `+${gained}` })
  }

  // Единственное место, где утка улетевшая стоит жизнь — и таймаут полёта, и исчерпание патронов
  // приводят сюда через state='escaping'.
  private _resolveDuckEscaped(duck: Duck): void {
    // медведь поднимается из-за травы и хохочет над промахом — только при промахе
    this.bears.push({
      x: Math.max(30, Math.min(this.width - 30, duck.x)),
      y: this.height - 26,
      t: 0,
      duration: 1.4,
    })
    this.lives = Math.max(0, this.lives - 1)
    if (this.lives <= 0 && this.state === 'playing') {
      this.best = Math.max(this.best, this.score)
      this._saveBest()
      this.state = 'game-over'
    }
  }

  private _concludeWave(): void {
    this.best = Math.max(this.best, this.score)
    this._saveBest()

    if (this.waveHits === this.waveSize) {
      this.score += 500
      this.effects.push({ type: 'float', x: this.width / 2, y: this.height / 2, t: 0, duration: 1.2, text: '+500 Все!' })
    }

    this.wavesCompletedInLevel++
    if (this.wavesCompletedInLevel >= 2) { // уровень = 2 волны (было 3)
      this.wavesCompletedInLevel = 0
      this.level++
    }

    this.state = 'round-intro'
    this.stateTimer = 0
  }

  private _loadBest(): number {
    try {
      const v = localStorage.getItem('gala_duck_best')
      return v ? parseInt(v, 10) || 0 : 0
    } catch {
      return 0
    }
  }

  private _saveBest(): void {
    try {
      localStorage.setItem('gala_duck_best', String(this.best))
    } catch {
      /* ignore */
    }
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
    for (const c of this.clouds) {
      c.x += c.speed * dt
      if (c.x > 1.2) c.x = -0.2
    }
    this._grassPhase += dt // лёгкое покачивание верхнего края травы

    if (this.state === 'round-intro') {
      this.stateTimer += dt
      if (this.stateTimer > 1.0) {
        this.stateTimer = 0
        this._startWave()
      }
      return
    }

    if (this.state === 'round-result' || this.state === 'game-over') {
      return
    }

    if (this.state !== 'playing') return

    // Границы отскока — по реальной видимой утке (половина визуальной ширины/высоты
    // того же _duckVisualScale, что рисует _drawDuck), а не по фиксированным 20px.
    const duckVisualScale = this._duckVisualScale()
    const duckHalfW = (DUCK_NATURAL_W * duckVisualScale) / 2
    const duckHalfH = (DUCK_NATURAL_H * duckVisualScale) / 2
    const duckTopBound = 60 + duckHalfH // не выше 60px под HUD (целиком видна)

    // update ducks
    for (const d of this.ducks) {
      d.t += dt
      d.wingPhase += d.wingSpeed * dt

      if (d.state === 'flying') {
        d.x += d.vx * dt
        d.y += d.vy * dt + Math.sin(d.t * d.freq + d.phase) * d.ampl * dt * 0.6
        d.vy += 10 * dt // slight gravity pull to keep arcs natural
        if (d.y < duckTopBound) d.vy = Math.abs(d.vy) * 0.3
        if (d.y > this._duckBottomBound()) d.vy = -Math.abs(d.vy)

        if (d.x < duckHalfW || d.x > this.width - duckHalfW) {
          d.vx *= -1
          d.x = Math.max(duckHalfW, Math.min(this.width - duckHalfW, d.x))
        }

        // не стрелял игрок — утка не висит вечно, улетает после лимита времени
        const maxFlightTime = Math.max(4, 8 - this.level * 0.5)
        if (d.t > maxFlightTime) {
          d.state = 'escaping'
          d.t = 0
        }
      } else if (d.state === 'hit') {
        d.y += d.vy * dt
        d.vy += 220 * dt
        d.rotation += (d.vrotFall || 6) * dt
        if (d.y > this.height - 30 || d.t > 2.2) {
          // попал — никакого персонажа, только летящая вверх надпись "+100 × уровень" (эффект 'float')
          d.state = 'done'
        }
      } else if (d.state === 'escaping') {
        d.y -= 160 * dt
        d.x += d.vx * dt * 0.5
        if (d.y < -40 || d.t > 2.0) {
          d.state = 'done'
          this._resolveDuckEscaped(d)
        }
      }
    }
    this.ducks = this.ducks.filter(d => d.state !== 'done')

    // effects
    for (const fx of this.effects) fx.t += dt
    this.effects = this.effects.filter(fx => fx.t < fx.duration)

    for (const bear of this.bears) bear.t += dt
    this.bears = this.bears.filter(bear => bear.t < bear.duration)

    // wave completion check (пропускается, если game-over уже выставлен внутри _resolveDuckEscaped)
    if (this.state === 'playing' && this.ducks.length === 0 && this._waveSpawnedCount >= this.waveSize) {
      this._concludeWave()
    }
  }

  private _restartGame(): void {
    this.level = 1
    this.score = 0
    this.lives = 3
    this.wavesCompletedInLevel = 0
    this.ducks = []
    this.bears = []
    this.effects = []
    this.state = 'round-intro'
    this.stateTimer = 0
  }

  // ---------- rendering ----------

  private _render(): void {
    const ctx = this.ctx
    const w = this.width
    const h = this.height

    ctx.clearRect(0, 0, w, h)
    this._drawSky(ctx, w, h)

    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'

    this._drawClouds(ctx, w, h)
    this._drawGroundScenery(ctx, w, h)

    for (const d of this.ducks) this._drawDuck(ctx, d)
    for (const bear of this.bears) this._drawBear(ctx, bear)

    // Трава рисуется ПОСЛЕ уток/медведя: утки стартуют из травы, медведь прячет
    // в ней нижнюю часть тела, пока поднимается "из-за" неё (см. _drawGrassBand).
    this._drawGrassBand(ctx, w, h)

    for (const fx of this.effects) this._drawEffect(ctx, fx)

    this._drawHud(ctx, w, h)

    if (this.state === 'round-intro') this._drawCenterText(ctx, w, h, `Уровень ${this.level}`, 'Готовьтесь…')
    if (this.state === 'game-over') this._drawGameOver(ctx, w, h)

    if (this.pointer.active) this._drawCrosshair(ctx, this.pointer.x, this.pointer.y)
  }

  // Небо — тайловый фон из пака Kenney (sprites/duck/bg_sky.png), пока не загрузился —
  // сплошная заливка близкого по тону голубого (единственный fallback-цвет, Правило №6).
  private _drawSky(ctx: CanvasRenderingContext2D, w: number, h: number): void {
    const img = loadSprite(bgSkyUrl)
    if (isSpriteReady(img)) {
      const tile = 180
      for (let y = 0; y < h; y += tile) {
        for (let x = 0; x < w; x += tile) {
          ctx.drawImage(img, x, y, tile, tile)
        }
      }
    } else {
      ctx.fillStyle = '#5bb4e8'
      ctx.fillRect(0, 0, w, h)
    }
  }

  private _drawClouds(ctx: CanvasRenderingContext2D, w: number, h: number): void {
    for (const c of this.clouds) {
      const img = loadSprite(c.variant === 0 ? cloud1Url : cloud2Url)
      if (!isSpriteReady(img)) continue
      const cx = c.x * w
      const cy = c.y * h
      const drawW = 70 * c.scale
      const drawH = drawW * (img.naturalHeight / img.naturalWidth)
      ctx.drawImage(img, cx - drawW / 2, cy - drawH / 2, drawW, drawH)
    }
  }

  // Декор земли БЕЗ травы — ёлки Kenney по краям, рисуется до уток/медведя (трава
  // рисуется позже, см. _drawGrassBand, чтобы лечь НАД медведем и спрятать его низ).
  private _drawGroundScenery(ctx: CanvasRenderingContext2D, w: number, _h: number): void {
    const img = loadSprite(treePineUrl)
    if (!isSpriteReady(img)) return
    const grassTop = this._grassBandTop()
    // Дерево наполовину в траве (ствол прячется под заливкой _drawGrassBand,
    // рисуемой позже), крона — хорошо видна над травой, не крошечным кончиком.
    const drawH = 170 * (this.width / 1000)
    const drawW = drawH * (img.naturalWidth / img.naturalHeight)
    ctx.drawImage(img, w - 40 - drawW, grassTop - drawH + 55, drawW, drawH)
    const drawH2 = drawH * 0.7
    const drawW2 = drawH2 * (img.naturalWidth / img.naturalHeight)
    ctx.drawImage(img, 14, grassTop - drawH2 + 45, drawW2, drawH2)
  }

  // Травяная полоса ~50px высотой: сплошная заливка + тайловый волнистый верхний
  // край из grass1/grass2 (Kenney), тайлы чередуются и слегка покачиваются.
  // Рисуется ПОСЛЕ уток и медведя (см. порядок в _render) — утки стартуют из травы,
  // медведь прячет в ней нижнюю часть. Единственное место, где рисуется трава (Правило №6).
  private _drawGrassBand(ctx: CanvasRenderingContext2D, w: number, h: number): void {
    const topY = this._grassBandTop()
    ctx.save()
    ctx.fillStyle = '#3fa24a'
    ctx.fillRect(0, topY, w, h - topY)

    const img1 = loadSprite(grass1Url)
    const img2 = loadSprite(grass2Url)
    if (isSpriteReady(img1) && isSpriteReady(img2)) {
      const sway = Math.sin(this._grassPhase * 1.1) * 2
      const tileDrawH = h - topY + 14
      const tileDrawW = tileDrawH * (img1.naturalWidth / img1.naturalHeight)
      const step = tileDrawW * 0.82 // лёгкое перекрытие тайлов — чтобы не было щелей на стыках
      let x = -tileDrawW * 0.3
      let i = 0
      while (x < w) {
        const img = i % 2 === 0 ? img1 : img2
        ctx.drawImage(img, x, topY - 10 + sway, tileDrawW, tileDrawH)
        x += step
        i++
      }
    }
    ctx.restore()
  }

  private _drawCrosshair(ctx: CanvasRenderingContext2D, x: number, y: number): void {
    const img = loadSprite(crosshairUrl)
    const size = 34
    if (isSpriteReady(img)) {
      ctx.drawImage(img, x - size / 2, y - size / 2, size, size)
      return
    }
    ctx.save()
    ctx.strokeStyle = '#ff3b30'
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(x - 10, y); ctx.lineTo(x + 10, y)
    ctx.moveTo(x, y - 10); ctx.lineTo(x, y + 10)
    ctx.stroke()
    ctx.restore()
  }

  // Визуальный масштаб утки — ЕДИНСТВЕННОЕ место, где он считается (Правило №6):
  // _drawDuck (отрисовка), _duckHitTest (хиттест клика) и _update (границы отскока
  // от краёв экрана) читают это значение, а не пересчитывают каждый сам.
  // ~85px по ширине на холсте шириной 1000px, пропорционально на любой ширине.
  private _duckVisualScale(): number {
    const targetW = 85 * (this.width / 1000)
    return Math.max(0.35, targetW / DUCK_NATURAL_W)
  }

  // Хиттест клика по утке — прямоугольник видимого спрайта (DUCK_NATURAL_W/H из
  // реальных пикселей PNG, без прозрачных полей по краям — см. отчёт проверки bbox)
  // с небольшим допуском (инсет 0.84 вместо строгого края), чтобы не требовать
  // попадания пиксель-в-пиксель в самый угол силуэта.
  private _duckHitTest(d: Duck, clickX: number, clickY: number): boolean {
    const visualScale = this._duckVisualScale()
    const halfW = (DUCK_NATURAL_W * visualScale) / 2 * 0.84
    const halfH = (DUCK_NATURAL_H * visualScale) / 2 * 0.84
    return Math.abs(clickX - d.x) <= halfW && Math.abs(clickY - d.y) <= halfH
  }

  private _drawDuck(ctx: CanvasRenderingContext2D, d: Duck): void {
    ctx.save()
    ctx.translate(d.x, d.y)
    if (d.state === 'hit') {
      // Утка вращается ТОЛЬКО целиком, одним блоком, и только при падении после попадания.
      ctx.rotate(d.rotation)
    } else if (d.state === 'flying') {
      // Нет кадров взмаха крыльев в паке — лёгкое покачивание корпуса вместо анимации крыла.
      ctx.rotate(Math.sin(d.wingPhase) * 0.10)
    }

    const visualScale = this._duckVisualScale()
    const dir = d.vx < 0 ? -1 : 1
    ctx.scale(visualScale * dir, visualScale)

    const url = d.state === 'escaping' ? duckBackUrl : d.state === 'hit' ? duckHitUrl : duckUrl
    const img = loadSprite(url)
    if (isSpriteReady(img)) {
      ctx.drawImage(img, -img.naturalWidth / 2, -img.naturalHeight / 2)
    } else {
      ctx.fillStyle = 'rgba(214, 184, 96, 0.55)'
      ctx.beginPath()
      ctx.ellipse(0, 0, DUCK_NATURAL_W / 2.6, DUCK_NATURAL_H / 2.6, 0, 0, Math.PI * 2)
      ctx.fill()
    }
    ctx.restore()
  }

  private _drawBear(ctx: CanvasRenderingContext2D, bear: Bear): void {
    // Поднимается из травы только при промахе, хохочет "ХО-ХО-ХО!", трясясь
    // от смеха, и опускается обратно.
    const prog = Math.min(1, bear.t / bear.duration)
    const popUp = Math.min(1, bear.t / 0.25) // поднимается из травы
    const sinkFrom = 0.7
    const sinkProg = prog > sinkFrom ? (prog - sinkFrom) / (1 - sinkFrom) : 0
    const riseOffset = (1 - popUp) * 30 + sinkProg * 34
    const shakeAmount = Math.min(1, bear.t / 0.3) * (1 - sinkProg)
    const shake = Math.sin(bear.t * 24) * 2.4 * shakeAmount

    ctx.save()
    ctx.translate(bear.x + shake, bear.y + riseOffset)

    const img = loadSprite(bearUrl)
    const targetH = 130 * (this.width / 1000)
    if (isSpriteReady(img)) {
      const scale = targetH / img.naturalHeight
      const dw = img.naturalWidth * scale
      const dh = img.naturalHeight * scale
      // низ картинки у bear.y (после translate) — медведь "стоит" в траве, трава рисуется поверх
      ctx.drawImage(img, -dw / 2, -dh, dw, dh)
    } else {
      ctx.fillStyle = 'rgba(150, 110, 70, 0.5)'
      ctx.beginPath()
      ctx.ellipse(0, -targetH / 2, targetH * 0.42, targetH * 0.5, 0, 0, Math.PI * 2)
      ctx.fill()
    }

    // речевое облако со смехом — фиксированный экранный размер над головой медведя
    ctx.save()
    ctx.font = `800 15px ${GAME_FONT}`
    ctx.textAlign = 'center'
    ctx.lineJoin = 'round'
    ctx.lineWidth = 4
    ctx.strokeStyle = 'rgba(0,0,0,0.5)'
    ctx.fillStyle = '#ffffff'
    ctx.globalAlpha = Math.min(1, (bear.duration - bear.t) / 0.4 + 0.2)
    ctx.strokeText('ХО-ХО-ХО!', 0, -targetH - 8)
    ctx.fillText('ХО-ХО-ХО!', 0, -targetH - 8)
    ctx.restore()

    ctx.restore()
  }

  private _drawEffect(ctx: CanvasRenderingContext2D, fx: Effect): void {
    const prog = fx.t / fx.duration
    if (fx.type === 'ring') {
      ctx.save()
      ctx.globalAlpha = 1 - prog
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 3
      ctx.beginPath()
      ctx.arc(fx.x, fx.y, 6 + prog * 22, 0, Math.PI * 2)
      ctx.stroke()
      ctx.restore()
    } else if (fx.type === 'float') {
      ctx.save()
      ctx.globalAlpha = 1 - prog
      ctx.font = `800 16px ${GAME_FONT}`
      ctx.textAlign = 'center'
      ctx.lineJoin = 'round'
      ctx.lineWidth = 4
      ctx.strokeStyle = 'rgba(0,0,0,0.55)'
      ctx.fillStyle = '#ffffff'
      const text = fx.text || ''
      const y = fx.y - prog * 30
      ctx.strokeText(text, fx.x, y)
      ctx.fillText(text, fx.x, y)
      ctx.restore()
    }
  }

  private _drawHud(ctx: CanvasRenderingContext2D, w: number, h: number): void {
    void h
    ctx.save()
    ctx.font = `800 14px ${GAME_FONT}`
    ctx.lineJoin = 'round'
    ctx.lineWidth = 3.5
    ctx.strokeStyle = 'rgba(0,0,0,0.45)'
    ctx.fillStyle = '#ffffff'

    ctx.textAlign = 'left'
    const line1 = `УРОВЕНЬ ${this.level}   ОЧКИ ${this.score}`
    ctx.strokeText(line1, 14, 22)
    ctx.fillText(line1, 14, 22)

    ctx.textAlign = 'right'
    const line2 = `РЕКОРД ${this.best}`
    ctx.strokeText(line2, w - 14, 22)
    ctx.fillText(line2, w - 14, 22)

    // жизни — подпись белая, сами сердечки красные ("ЖИЗНИ ♥ ♥ ♡")
    ctx.textAlign = 'left'
    const label = 'ЖИЗНИ '
    ctx.strokeText(label, 14, 42)
    ctx.fillText(label, 14, 42)
    let hearts = ''
    for (let i = 0; i < 3; i++) hearts += (i < this.lives ? '♥' : '♡') + ' '
    const labelW = ctx.measureText(label).width
    ctx.fillStyle = '#ff4d4d'
    ctx.strokeText(hearts.trim(), 14 + labelW, 42)
    ctx.fillText(hearts.trim(), 14 + labelW, 42)

    // патроны — общий пул волны, до 15 значков "▮". Квадратные глифы обводкой
    // (strokeText) выглядят пустыми изнутри — вместо обводки тень для контраста,
    // строка собрана справа налево: сперва считаем общую ширину, затем рисуем
    // подпись и квадраты раздельно слева направо от общего правого края.
    const show = Math.min(15, Math.max(0, this.ammoPool))
    const squares = '▮'.repeat(show)
    const ammoLabel = 'ПАТРОНЫ '
    ctx.textAlign = 'left'
    const totalW = ctx.measureText(ammoLabel + squares).width
    const startX = w - 14 - totalW
    ctx.fillStyle = '#ffffff'
    ctx.strokeText(ammoLabel, startX, 42)
    ctx.fillText(ammoLabel, startX, 42)
    const labelW2 = ctx.measureText(ammoLabel).width
    ctx.shadowColor = 'rgba(0,0,0,0.55)'
    ctx.shadowBlur = 3
    ctx.fillText(squares, startX + labelW2, 42)
    ctx.shadowBlur = 0
    ctx.restore()
  }

  private _drawCenterText(ctx: CanvasRenderingContext2D, w: number, h: number, title: string, subtitle: string): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.lineJoin = 'round'
    ctx.strokeStyle = 'rgba(0,0,0,0.45)'
    ctx.fillStyle = '#ffffff'
    ctx.lineWidth = 6
    ctx.font = `800 32px ${GAME_FONT}`
    ctx.strokeText(title.toUpperCase(), w / 2, h / 2 - 8)
    ctx.fillText(title.toUpperCase(), w / 2, h / 2 - 8)
    ctx.lineWidth = 4
    ctx.font = `600 14px ${GAME_FONT}`
    ctx.strokeText(subtitle, w / 2, h / 2 + 18)
    ctx.fillStyle = '#f2f2f2'
    ctx.fillText(subtitle, w / 2, h / 2 + 18)
    ctx.restore()
  }

  private _drawGameOver(ctx: CanvasRenderingContext2D, w: number, h: number): void {
    ctx.save()
    ctx.fillStyle = 'rgba(0, 0, 0, 0.35)'
    ctx.fillRect(0, 0, w, h)

    ctx.textAlign = 'center'
    ctx.lineJoin = 'round'
    ctx.strokeStyle = 'rgba(0,0,0,0.5)'
    ctx.fillStyle = '#ffffff'
    ctx.lineWidth = 5
    ctx.font = `800 26px ${GAME_FONT}`
    ctx.strokeText('ИГРА ОКОНЧЕНА', w / 2, h / 2 - 30)
    ctx.fillText('ИГРА ОКОНЧЕНА', w / 2, h / 2 - 30)
    ctx.lineWidth = 3.5
    ctx.font = `600 15px ${GAME_FONT}`
    const scoreLine = `ОЧКИ ${this.score}   РЕКОРД ${this.best}`
    ctx.strokeText(scoreLine, w / 2, h / 2 - 4)
    ctx.fillText(scoreLine, w / 2, h / 2 - 4)

    // "ЕЩЁ РАЗ" — закруглённая кнопка со светлой заливкой
    const btnW = 170, btnH = 40
    const bx = w / 2 - btnW / 2, by = h / 2 + 16
    const r = 10
    ctx.beginPath()
    ctx.moveTo(bx + r, by)
    ctx.arcTo(bx + btnW, by, bx + btnW, by + btnH, r)
    ctx.arcTo(bx + btnW, by + btnH, bx, by + btnH, r)
    ctx.arcTo(bx, by + btnH, bx, by, r)
    ctx.arcTo(bx, by, bx + btnW, by, r)
    ctx.closePath()
    ctx.fillStyle = 'rgba(255,255,255,0.92)'
    ctx.fill()
    ctx.lineWidth = 2
    ctx.strokeStyle = 'rgba(0,0,0,0.3)'
    ctx.stroke()
    ctx.fillStyle = '#1a1a1a'
    ctx.font = `800 15px ${GAME_FONT}`
    ctx.fillText('ЕЩЁ РАЗ', w / 2, by + btnH / 2 + 5)
    ctx.restore()

    this._gameOverBtnRect = { x: bx, y: by, w: btnW, h: btnH }
  }

  // Публичный доступ только для DuckShootWindow.vue (заголовок окна читает
  // "идёт ли загрузка" из useLongWait.ts, а не из игры — этот геттер здесь
  // не нужен и не добавлен, чтобы не плодить второй источник того же флага).
}

// Натуральные размеры спрайта утки (duck.png/duck_hit.png/duck_back.png — все 99×95,
// один набор пикселей без прозрачных полей по краям) — единственное место, где заданы
// (Правило №6); _duckVisualScale/_duckHitTest/_update(границы отскока) читают отсюда.
const DUCK_NATURAL_W = 99
const DUCK_NATURAL_H = 95
