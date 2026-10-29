// Порт класса DuckShootGame из прототипа
// (scratchpad/duck.html, <script> часть) — логика и отрисовка оставлены
// идентичными оригиналу, только добавлена типизация и убран demo-бутстрап
// страницы (overlay/closeBtn/replayBtn/?debug=1 — служебный флаг прототипа
// для визуальной проверки стиля, в CRM-версии не читаем location вообще).
//
// DuckShootWindow.vue создаёт контейнер и управляет жизненным циклом:
// constructor(container) → start() на открытии окна, destroy() на закрытии/unmount.

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
  glyphSeed: number
}

export interface Bear {
  x: number
  y: number
  t: number
  duration: number
  glyphSeed: number
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
  glyphSeed: number
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
  private _docBg: HTMLCanvasElement | null = null

  // Окно игры строго чёрно-белое "документное" — только эти два поля из набора
  // цветов оригинала фактически читаются где-либо в отрисовке (colorInk/colorSoft/
  // colorAccent/colorDoc в прототипе задавались, но нигде не читались — не портируем
  // мёртвый код, Правило №6: раз значение не используется, второго места для него нет).
  private colorBg = '#ffffff'
  private colorLine = '#bbbbbb'
  private glyphFontFamily = 'Consolas, "JetBrains Mono", "Courier New", monospace'

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
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    this._readColors()
    this._launchPoints = this._computeLaunchPoints()
    this._buildDocumentBackground()
  }

  private _computeLaunchPoints(): LaunchPoint[] {
    // точки вылета уток вдоль травы: разные x, плюс точка из-за куста справа
    const fracs = [0.10, 0.25, 0.40, 0.60, 0.75, 0.90]
    const points: LaunchPoint[] = fracs.map((f) => ({ x: f * this.width, fromBush: false }))
    points.push({ x: this.width - 60, fromBush: true })
    return points
  }

  // Окно игры — строго чёрно-белое "документное" оформление, цвета зашиты явно
  // (не берутся из CSS-переменных CRM), поэтому тема CRM на вид игры не влияет.
  private _readColors(): void {
    this.colorBg = '#ffffff'
    this.colorLine = '#bbbbbb'
    this.glyphFontFamily = 'Consolas, "JetBrains Mono", "Courier New", monospace'
  }

  // ---------- "документный" фон (рисуется один раз на resize в offscreen canvas) ----------

  private _buildDocumentBackground(): void {
    const w = this.width
    const h = this.height
    if (w <= 0 || h <= 0) return
    let off = this._docBg
    if (!off) {
      off = document.createElement('canvas')
      this._docBg = off
    }
    off.width = Math.max(1, Math.round(w * this.dpr))
    off.height = Math.max(1, Math.round(h * this.dpr))
    const c = off.getContext('2d')
    if (!c) return
    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    c.clearRect(0, 0, w, h)
    c.fillStyle = '#ffffff'
    c.fillRect(0, 0, w, h)

    const mono = this.glyphFontFamily
    const marginX = Math.max(26, w * 0.07)
    let y = 34

    c.textAlign = 'center'
    c.fillStyle = '#cfcfcf'
    c.font = `700 15px ${mono}`
    c.fillText('ДОГОВОР ПОСТАВКИ № 17/2026', w / 2, y); y += 18
    c.font = `12px ${mono}`
    c.fillText('г. Москва', w / 2, y); y += 26

    const paragraphs = [
      '1.1. Поставщик обязуется передать в собственность Покупателя товар',
      'в количестве и ассортименте согласно Спецификации, а Покупатель',
      'обязуется принять и оплатить товар на условиях настоящего Договора.',
      '1.2. Качество товара должно соответствовать требованиям, обычно',
      'предъявляемым к товарам такого рода, и подтверждается сертификатом.',
      '2.1. Цена товара устанавливается в рублях и включает НДС, расходы',
      'на упаковку, маркировку и доставку до склада Покупателя.',
      '2.2. Оплата производится в безналичном порядке в течение 10',
      'рабочих дней с момента подписания товарной накладной.',
      '3.1. Срок поставки — не позднее 30 календарных дней с даты',
      'подписания настоящего Договора обеими Сторонами.',
      '3.2. Приёмка товара по количеству и качеству производится',
      'представителем Покупателя в месте поставки с составлением акта.',
      '4.1. За нарушение сроков поставки Поставщик уплачивает пеню',
      'в размере 0,1% от стоимости недопоставленного товара за день.',
    ]
    c.textAlign = 'left'
    c.font = `11px ${mono}`
    c.fillStyle = '#dddddd'
    const lineH = 15.5
    const colW = w - marginX * 2
    const approxCharsPerLine = Math.max(10, Math.floor(colW / 6.6))
    outer:
    for (const para of paragraphs) {
      const words = para.split(' ')
      let line = ''
      for (const word of words) {
        const test = line ? line + ' ' + word : word
        if (test.length > approxCharsPerLine && line) {
          c.fillText(line, marginX, y); y += lineH
          if (y > h - 90) break outer
          line = word
        } else {
          line = test
        }
      }
      if (line) { c.fillText(line, marginX, y); y += lineH }
      y += lineH * 0.35
      if (y > h - 90) break
    }

    // маленькая таблица с цифрами
    if (y < h - 70) {
      const tableY = y + 6
      const tableW = colW
      const tableH = 46
      const cols = 4
      c.strokeStyle = '#d9d9d9'
      c.lineWidth = 1
      c.beginPath()
      c.rect(marginX, tableY, tableW, tableH)
      for (let i = 1; i < cols; i++) {
        const lx = marginX + (tableW / cols) * i
        c.moveTo(lx, tableY); c.lineTo(lx, tableY + tableH)
      }
      c.moveTo(marginX, tableY + tableH / 2); c.lineTo(marginX + tableW, tableY + tableH / 2)
      c.stroke()
      c.font = `10px ${mono}`
      c.textAlign = 'center'
      const heads = ['№ п/п', 'Кол-во', 'Цена, руб.', 'Сумма, руб.']
      const rows2 = ['1', '120', '540,00', '64 800,00']
      for (let i = 0; i < cols; i++) {
        const cx = marginX + (tableW / cols) * (i + 0.5)
        c.fillText(heads[i] ?? '', cx, tableY + tableH / 4 + 3)
        c.fillText(rows2[i] ?? '', cx, tableY + tableH * 0.75 + 3)
      }
    }

    // подпись — заметно выше нижнего края страницы, чтобы не тонуть в траве по низу холста
    c.textAlign = 'left'
    c.font = `11px ${mono}`
    c.fillStyle = '#d4d4d4'
    c.fillText('______________________ / Иванов И.И.', marginX, h - 64)
    c.font = `10px ${mono}`
    c.fillText('Поставщик', marginX, h - 50)
    c.textAlign = 'right'
    c.fillText('Покупатель', w - marginX, h - 50)
  }

  // ---------- глифовый рендер персонажей ----------

  // maskFn(localX, localY) -> 0 (нет), 1 (край, плотный глиф), 2 (внутри, буква документа)
  // bbox в локальных координатах (до текущего ctx.scale/rotate — координаты
  // те же, что использует maskFn, поэтому сетка жёстко привязана к фигуре и едет с ней).
  private _drawGlyphShape(
    ctx: CanvasRenderingContext2D,
    maskFn: (x: number, y: number) => number,
    bbox: Rect,
    cell: number,
    seed: number,
  ): void {
    const edgeChars = ['#', '@', '8', '0', 'Ж', 'Ш', 'М']
    const interiorChars = 'ДОГОВОРСЧЁТАКТ2026НДС№'
    const cols = Math.max(1, Math.ceil(bbox.w / cell))
    const rows = Math.max(1, Math.ceil(bbox.h / cell))
    // Плотная заливка: шрифт НЕМНОГО крупнее шага сетки (6.5px сетка / 7px шрифт),
    // силуэт должен складываться из плотности глифов, а не из редких отдельных точек.
    const fontPx = cell * (7 / 6.5)
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.font = `700 ${fontPx}px ${this.glyphFontFamily}`
    for (let r = 0; r < rows; r++) {
      for (let col = 0; col < cols; col++) {
        const x = bbox.x + col * cell + cell / 2
        const y = bbox.y + r * cell + cell / 2
        const m = maskFn(x, y)
        if (!m) continue
        const idx = Math.abs((col * 31 + r * 17 + seed) % 997)
        if (m === 1) {
          ctx.fillStyle = '#111111'
          ctx.fillText(edgeChars[idx % edgeChars.length] ?? '#', x, y)
        } else {
          ctx.fillStyle = '#666666'
          ctx.fillText(interiorChars[idx % interiorChars.length] ?? '', x, y)
        }
      }
    }
    ctx.restore()
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

  private _initClouds(): void {
    this.clouds = []
    for (let i = 0; i < 2; i++) {
      this.clouds.push({
        x: 0.15 + i * 0.55 + Math.random() * 0.1,
        y: 0.1 + Math.random() * 0.12,
        scale: 0.8 + Math.random() * 0.5,
        speed: 0.008 + Math.random() * 0.01,
        glyphSeed: Math.floor(Math.random() * 997),
      })
    }
  }

  // ---------- game flow ----------

  // Размер волны (число уток, стартующих одновременно) зависит от уровня.
  // Единственное место, где это считается — остальной код читает this.waveSize.
  private _computeWaveSize(level?: number): number {
    const lvl = level != null ? level : this.level
    if (lvl <= 2) return 1
    if (lvl <= 4) return 2
    if (lvl <= 6) return 3
    if (lvl <= 8) return 4
    return 5
  }

  private _resetWaveState(): void {
    this.waveSize = this._computeWaveSize()
    this.ammoPool = this.waveSize * 3 // общий пул патронов волны
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

  private _spawnDuck(launchPoint?: LaunchPoint): void {
    const baseSpeed = 70 + this.level * 12
    const fallbackPoint: LaunchPoint = { x: this.width / 2, fromBush: false }
    const lp = launchPoint || (this._launchPoints && this._launchPoints.length
      ? this._launchPoints[Math.floor(Math.random() * this._launchPoints.length)]
      : this._computeLaunchPoints()[0]) || fallbackPoint
    const dir = Math.random() < 0.5 ? 1 : -1
    const duck: Duck = {
      id: Math.random().toString(36).slice(2),
      x: lp.x,
      y: this.height - 40,
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
      glyphSeed: Math.floor(Math.random() * 997), // только для рендера — какие буквы попадут в сетку
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

    // Хиттест ОБЯЗАН совпадать с тем, что видит игрок: сначала проверяем реальную
    // маску силуэта (_duckMask) в координатах утки, с небольшим допуском по краю.
    // d.size (радиус клика независимо от визуального размера) — только запасной
    // вариант, если под кликом не нашлось маски ни у одной утки (единственное
    // место, где считается хит — остальной код просто читает результат).
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
    if (!target) {
      for (const d of this.ducks) {
        if (d.state !== 'flying') continue
        const dist = Math.hypot(d.x - x, d.y - y)
        const radius = d.size * 1.6
        if (dist < radius && dist < bestDist) {
          bestDist = dist
          target = d
        }
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
    // медведь поднимается из-за куста/травы и хохочет над промахом — только при промахе
    this.bears.push({
      x: Math.max(30, Math.min(this.width - 30, duck.x)),
      y: this.height - 26,
      t: 0,
      duration: 1.4,
      glyphSeed: Math.floor(Math.random() * 997), // только для рендера
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
    if (this.wavesCompletedInLevel >= 3) {
      this.wavesCompletedInLevel = 0
      this.level++
    }

    this.state = 'round-intro'
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
    for (const c of this.clouds) {
      c.x += c.speed * dt
      if (c.x > 1.2) c.x = -0.2
    }

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
    // того же _duckVisualScale, что рисует _drawDuck), а не по фиксированным 20px:
    // при baseBoxW=72/baseBoxH=49 утка больше не "высовывается" за край холста.
    const duckVisualScale = this._duckVisualScale()
    const duckHalfW = (72 * duckVisualScale) / 2
    const duckHalfH = (49 * duckVisualScale) / 2
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
        if (d.y > this.height - 50) d.vy = -Math.abs(d.vy)

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
    if (this._docBg && this._docBg.width > 0) {
      ctx.drawImage(this._docBg, 0, 0, w, h)
    } else {
      ctx.fillStyle = this.colorBg
      ctx.fillRect(0, 0, w, h)
    }

    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'

    this._drawClouds(ctx, w, h)
    this._drawGroundScenery(ctx, w, h)

    for (const d of this.ducks) this._drawDuck(ctx, d)
    for (const bear of this.bears) this._drawBear(ctx, bear)
    for (const fx of this.effects) this._drawEffect(ctx, fx)

    this._drawHud(ctx, w, h)

    if (this.state === 'round-intro') this._drawCenterText(ctx, w, h, `Уровень ${this.level}`, 'Готовьтесь…')
    if (this.state === 'game-over') this._drawGameOver(ctx, w, h)

    if (this.pointer.active) this._drawCrosshair(ctx, this.pointer.x, this.pointer.y)
  }

  private _drawClouds(ctx: CanvasRenderingContext2D, _w: number, _h: number): void {
    // одно-два ясных облака, контур из "~" в светло-сером — не "пыль"
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#bbbbbb'
    for (const c of this.clouds) {
      const cx = c.x * this.width
      const cy = c.y * this.height
      const s = c.scale * 16
      ctx.font = `700 ${s * 0.8}px ${this.glyphFontFamily}`
      ctx.fillText('~~~~', cx, cy)
      ctx.font = `700 ${s * 0.7}px ${this.glyphFontFamily}`
      ctx.fillText('~~~~~~', cx + s * 0.55, cy + s * 0.32)
      ctx.fillText('~~~', cx - s * 0.7, cy + s * 0.3)
    }
    ctx.restore()
  }

  private _drawGroundScenery(ctx: CanvasRenderingContext2D, w: number, h: number): void {
    const groundY = h - 22

    // трава — ряд глифов "|", "/", "\", "ı", "і" по всей ширине
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'alphabetic'
    const grassChars = ['|', '/', '\\', 'ı', 'і']
    for (let x = 6, i = 0; x < w; x += 11, i++) {
      const seed = (x * 13 + i * 7) % 997
      const ch = grassChars[seed % grassChars.length] ?? '|'
      const size = 9 + (seed % 5)
      ctx.font = `${size}px ${this.glyphFontFamily}`
      ctx.fillStyle = '#111111'
      ctx.fillText(ch, x, groundY + size * 0.3)
    }
    ctx.restore()

    // лёгкий контур куста справа (не глиф — просто ориентир на карте)
    ctx.strokeStyle = this.colorLine
    ctx.lineWidth = 1.5
    const tx = w - 60
    const ty = groundY
    ctx.beginPath()
    ctx.arc(tx - 8, ty - 22, 16, 0, Math.PI * 2)
    ctx.arc(tx + 6, ty - 28, 14, 0, Math.PI * 2)
    ctx.arc(tx + 18, ty - 18, 15, 0, Math.PI * 2)
    ctx.stroke()

    // камышовые кустики у части точек вылета — выше обычной травы
    if (this._launchPoints && this._launchPoints.length) {
      const reedSlots = [0, 1, 3, 5]
      for (const idx of reedSlots) {
        const lp = this._launchPoints[idx]
        if (lp && !lp.fromBush) this._drawReedClump(ctx, lp.x, groundY)
      }
    }
  }

  // Камышовый кустик — веер из 3-5 стеблей, каждый стебель — столбик из нескольких
  // мелких глифов "|"/"ı", расставленных вдоль стебля с шагом больше их высоты,
  // поэтому глифы никогда не перекрывают друг друга (ни внутри стебля, ни между ними).
  private _drawReedClump(ctx: CanvasRenderingContext2D, x: number, groundY: number): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#111111'
    const stems = 4
    const glyphPx = 10
    for (let s = 0; s < stems; s++) {
      const fanAngle = (s - (stems - 1) / 2) * 0.22 // раскрыв веера, рад
      const stemLen = 20 + (s % 2) * 8
      const steps = Math.max(3, Math.round(stemLen / (glyphPx * 0.95)))
      for (let k = 0; k < steps; k++) {
        const t = k / Math.max(1, steps - 1)
        const dx = Math.sin(fanAngle) * t * stemLen
        const dy = -t * stemLen
        ctx.font = `700 ${glyphPx}px ${this.glyphFontFamily}`
        ctx.fillText(k === steps - 1 ? 'ı' : '|', x + dx, groundY + dy)
      }
    }
    ctx.restore()
  }

  private _drawCrosshair(ctx: CanvasRenderingContext2D, x: number, y: number): void {
    // перекрестие из символов: "─ ┼ ─" с короткими штрихами сверху/снизу
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#111111'
    ctx.font = `700 16px ${this.glyphFontFamily}`
    ctx.fillText('─', x - 13, y)
    ctx.fillText('┼', x, y)
    ctx.fillText('─', x + 13, y)
    ctx.font = `700 13px ${this.glyphFontFamily}`
    ctx.fillText('│', x, y - 13)
    ctx.fillText('│', x, y + 13)
    ctx.restore()
  }

  // Маска силуэта утки — классический профиль: пухлое тело, голова-круг впереди-сверху,
  // плоский клюв, вздёрнутый хвостик, крыло на спине. dir зеркалит всё по направлению
  // полёта через "вперёд-пространство" bx = dir*x. Глифы НИКОГДА не поворачиваются сами:
  // крыло анимируется тем, что для его эллипса поворачивается только тестовая точка —
  // сама сетка (и символы в её ячейках) остаётся на месте, прямой и невращающейся.
  private _duckMask(x: number, y: number, dir: number, wingAngle: number): number {
    const bx = dir * x // "вперёд" всегда положительное bx, не зависит от направления полёта

    // голова — круг над и чуть впереди тела
    const headCx = 25, headCy = -15, headR = 10
    const headD = ((bx - headCx) * (bx - headCx) + (y - headCy) * (y - headCy)) / (headR * headR)
    if (headD <= 1) return headD > 0.72 ? 1 : 2

    // клюв — плоский прямоугольник, ширина = 0.35 × ширины головы
    const beakW = headR * 2 * 0.35
    const beakX0 = headCx + headR * 0.25
    if (bx >= beakX0 && bx <= beakX0 + 7 && Math.abs(y - headCy) <= beakW / 2) return 1

    // хвост — маленький вздёрнутый кончик сзади
    const tailBaseX = -20, tailTipX = -33
    if (bx <= tailBaseX && bx >= tailTipX) {
      const t = (tailBaseX - bx) / (tailBaseX - tailTipX)
      const halfW = 4 * (1 - t)
      const tailY = -2 - t * 5 // кончик приподнят вверх
      if (Math.abs(y - tailY) <= halfW) return 1
    }

    // крыло — эллипс на спине, хлопает ±35°: вращается ТОЛЬКО точка (x,y) вокруг центра
    // крыла перед проверкой, глиф в этой ячейке сетки как рисовался прямо, так и остаётся
    const pivotX = -6, pivotY = -2
    const ca = Math.cos(-wingAngle), sa = Math.sin(-wingAngle)
    const rx0 = bx - pivotX, ry0 = y - pivotY
    const wx = rx0 * ca - ry0 * sa, wy = rx0 * sa + ry0 * ca
    const wingD = (wx * wx) / (16 * 16) + (wy * wy) / (9 * 9)
    if (wingD <= 1) return wingD > 0.72 ? 1 : 2

    // тело — пухлый эллипс
    const bodyCx = -2, bodyCy = 6, bodyRx = 25, bodyRy = 16
    const bodyD = ((bx - bodyCx) * (bx - bodyCx)) / (bodyRx * bodyRx) + ((y - bodyCy) * (y - bodyCy)) / (bodyRy * bodyRy)
    if (bodyD <= 1) return bodyD > 0.8 ? 1 : 2

    return 0
  }

  // Визуальный масштаб утки — ЕДИНСТВЕННОЕ место, где он считается (Правило №6):
  // _drawDuck (отрисовка), _duckHitTest (хиттест клика) и _update (границы отскока
  // от краёв экрана) читают это значение, а не пересчитывают каждый сам.
  // ~150×102 px на холсте шириной 1000px, пропорционально на любой ширине.
  private _duckVisualScale(): number {
    const baseBoxW = 72 // ширина маски в локальных координатах при scale=1
    const targetW = 150 * (this.width / 1000)
    return Math.max(0.6, targetW / baseBoxW)
  }

  // Хиттест клика по утке — в тех же локальных координатах, что рисует _drawDuck:
  // снимаем translate(d.x,d.y) и scale(visualScale), зеркалим по dir внутри _duckMask.
  // Плюс небольшой допуск (~8 экранных px) по краю силуэта — попадание "почти впритык"
  // засчитывается, игроку не нужно попадать пиксель-в-пиксель в самый край.
  private _duckHitTest(d: Duck, clickX: number, clickY: number): boolean {
    const visualScale = this._duckVisualScale()
    const dir = d.vx < 0 ? -1 : 1
    const wingAngle = Math.sin(d.wingPhase) * 0.61
    const localX = (clickX - d.x) / visualScale
    const localY = (clickY - d.y) / visualScale
    if (this._duckMask(localX, localY, dir, wingAngle) > 0) return true

    // допуск по краю тела (основной, самой крупной части силуэта)
    const bx = dir * localX
    const bodyCx = -2, bodyCy = 6, bodyRx = 25, bodyRy = 16
    const bodyD = ((bx - bodyCx) * (bx - bodyCx)) / (bodyRx * bodyRx) + ((localY - bodyCy) * (localY - bodyCy)) / (bodyRy * bodyRy)
    const toleranceLocal = 8 / visualScale // 8 экранных px → локальные единицы
    const avgR = (bodyRx + bodyRy) / 2
    const normTolerance = toleranceLocal / avgR
    return bodyD <= (1 + normTolerance) * (1 + normTolerance)
  }

  private _drawDuck(ctx: CanvasRenderingContext2D, d: Duck): void {
    ctx.save()
    ctx.translate(d.x, d.y)
    // Утка вращается ТОЛЬКО целиком, одним блоком, и только при падении после попадания —
    // отдельные глифы или части силуэта (крыло) сами по себе никогда не поворачиваются.
    if (d.state === 'hit') ctx.rotate(d.rotation)

    const visualScale = this._duckVisualScale()
    ctx.scale(visualScale, visualScale)
    const dir = d.vx < 0 ? -1 : 1
    const seed = d.glyphSeed || 0
    const cellPx = 6.5 // плотная сетка — силуэт складывается из плотности, не из редких точек
    const cell = cellPx / visualScale
    const wingAngle = d.state === 'hit' ? -0.5 : Math.sin(d.wingPhase) * 0.61 // ±35° ≈ 0.61 рад

    // тело + голова + клюв + хвост + крыло — одна сетка, один проход, никаких вращений сетки
    this._drawGlyphShape(ctx, (x, y) => this._duckMask(x, y, dir, wingAngle), { x: -36, y: -27, w: 72, h: 49 }, cell, seed)

    // глаз — один фиксированный символ поверх сетки, всегда прямой: "•" в полёте, "x" при попадании
    ctx.save()
    ctx.font = `700 11px ${this.glyphFontFamily}`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#111111'
    ctx.fillText(d.state === 'hit' ? 'x' : '•', dir * 25, -15)
    ctx.restore()

    ctx.restore()
  }

  // Расстояние до скруглённого прямоугольника (0 на границе, <0 внутри, >0 снаружи) —
  // стандартная SDF-формула для прямоугольника hw×hh с радиусом скругления углов r.
  private _roundedRectDist(x: number, y: number, hw: number, hh: number, r: number): number {
    const qx = Math.abs(x) - (hw - r)
    const qy = Math.abs(y) - (hh - r)
    return Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) - r
  }

  // Маска силуэта медведя: голова-круг + 2 уха-круга НАД телом, тело — скруглённый
  // прямоугольник. Между головой и телом — нарочно узкая "шея", чтобы круглая голова
  // читалась явно шире шеи, а не сливалась в единый прямоугольник.
  private _bearMask(x: number, y: number): number {
    // уши — два круга над головой
    const earL = ((x + 13) * (x + 13) + (y + 34) * (y + 34)) / (6 * 6)
    if (earL <= 1) return earL > 0.55 ? 1 : 2
    const earR = ((x - 13) * (x - 13) + (y + 34) * (y + 34)) / (6 * 6)
    if (earR <= 1) return earR > 0.55 ? 1 : 2

    // узкая шея — соединяет круглую голову со скруглённым телом, специально уже обоих
    if (y > -14 && y < -7 && Math.abs(x) <= 6) return 2

    // голова — круг
    const headD = (x * x + (y + 22) * (y + 22)) / (13 * 13)
    if (headD <= 1) return headD > 0.72 ? 1 : 2

    // тело — скруглённый прямоугольник
    const bodyDist = this._roundedRectDist(x, y - 10, 16, 18, 8)
    if (bodyDist <= 0) return bodyDist > -2.4 ? 1 : 2

    return 0
  }

  private _drawBear(ctx: CanvasRenderingContext2D, bear: Bear): void {
    // Поднимается из-за камышей только при промахе, хохочет "ХО-ХО-ХО!", трясясь
    // от смеха, и опускается обратно. Тело целиком собрано из букв/цифр документа.
    const prog = Math.min(1, bear.t / bear.duration)
    const popUp = Math.min(1, bear.t / 0.25) // поднимается из травы
    const sinkFrom = 0.7
    const sinkProg = prog > sinkFrom ? (prog - sinkFrom) / (1 - sinkFrom) : 0
    const riseOffset = (1 - popUp) * 30 + sinkProg * 34
    const shakeAmount = Math.min(1, bear.t / 0.3) * (1 - sinkProg)
    const shake = Math.sin(bear.t * 24) * 2.4 * shakeAmount
    const seed = bear.glyphSeed || 0

    ctx.save()
    ctx.translate(bear.x + shake, bear.y + riseOffset)

    // камыши, из-за которых поднимается медведь — в мировом масштабе, до увеличения медведя
    this._drawReedClump(ctx, -22, 16)
    this._drawReedClump(ctx, 22, 16)

    // Медведь ~260px высотой на холсте шириной 1000px, пропорционально на любой ширине
    // (та же логика масштаба, что у утки — хитбоксов/таймингов это не касается).
    const baseBoxH = 72 // высота маски ниже в локальных координатах при scale=1 (ушки..низ тела)
    const targetH = 260 * (this.width / 1000)
    const visualScale = Math.max(0.6, targetH / baseBoxH)
    ctx.scale(visualScale, visualScale)
    const cellPx = 6.5 // та же плотная сетка, что у утки
    const cell = cellPx / visualScale

    // уши/голова/шея/тело — одна глифовая сетка, глифы не вращаются
    this._drawGlyphShape(ctx, (x, y) => this._bearMask(x, y), { x: -20, y: -42, w: 40, h: 72 }, cell, seed)

    // нос — точка, крупнее
    ctx.save()
    ctx.font = `700 11px ${this.glyphFontFamily}`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#111111'
    ctx.fillText('•', 0, -20)

    // глаза, прищуренные от смеха — крупные "^ ^"
    ctx.font = `700 14px ${this.glyphFontFamily}`
    ctx.fillText('^', -6, -26)
    ctx.fillText('^', 6, -26)

    // широко открытый смеющийся рот — крупное "О"
    ctx.font = `700 14px ${this.glyphFontFamily}`
    ctx.fillText('О', 0, -15)
    ctx.restore()

    // речевое облако со смехом — рисуется ВНУТРИ того же масштаба/переноса, что и сам
    // медведь (не отдельным save с фиксированным офсетом), иначе на крупном медведе
    // текст оказывается поверх мордочки вместо места над головой.
    ctx.save()
    // фиксированный экранный размер текста: делим на visualScale, чтобы при любом
    // масштабе медведя облако читалось как обычная 13px-подпись, а не разрасталось вместе с ним
    ctx.font = `700 ${13 / visualScale}px ${this.glyphFontFamily}`
    ctx.fillStyle = '#111111'
    ctx.textAlign = 'center'
    ctx.globalAlpha = Math.min(1, (bear.duration - bear.t) / 0.4 + 0.2)
    ctx.fillText('ХО-ХО-ХО!', 0, -50) // чуть выше макушки головы (bbox начинается с y=-42)
    ctx.restore()

    ctx.restore() // снимаем translate(bear.x+shake, bear.y+riseOffset) + scale(visualScale)
  }

  private _drawEffect(ctx: CanvasRenderingContext2D, fx: Effect): void {
    const prog = fx.t / fx.duration
    if (fx.type === 'ring') {
      // расширяющееся кольцо выстрела — из точек "·"
      ctx.save()
      ctx.globalAlpha = 1 - prog
      ctx.fillStyle = '#111111'
      ctx.font = `700 11px ${this.glyphFontFamily}`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      const r = 4 + prog * 22
      const n = 10
      for (let i = 0; i < n; i++) {
        const a = (i / n) * Math.PI * 2
        ctx.fillText('·', fx.x + Math.cos(a) * r, fx.y + Math.sin(a) * r)
      }
      ctx.restore()
    } else if (fx.type === 'float') {
      ctx.save()
      ctx.globalAlpha = 1 - prog
      ctx.fillStyle = '#111111'
      ctx.font = `700 14px ${this.glyphFontFamily}`
      ctx.textAlign = 'center'
      ctx.fillText(fx.text || '', fx.x, fx.y - prog * 30)
      ctx.restore()
    }
  }

  private _drawHud(ctx: CanvasRenderingContext2D, w: number, h: number): void {
    void h
    ctx.save()
    ctx.fillStyle = '#111111'
    ctx.font = `700 13px ${this.glyphFontFamily}`
    ctx.textAlign = 'left'
    ctx.fillText(`УРОВЕНЬ ${this.level}   ОЧКИ ${this.score}`, 14, 22)
    ctx.textAlign = 'right'
    ctx.fillText(`РЕКОРД ${this.best}`, w - 14, 22)
    ctx.restore()

    // жизни — подписаны явно: "ЖИЗНИ ♥ ♥ ♡"
    ctx.save()
    ctx.font = `700 13px ${this.glyphFontFamily}`
    ctx.textAlign = 'left'
    ctx.fillStyle = '#111111'
    let hearts = ''
    for (let i = 0; i < 3; i++) hearts += (i < this.lives ? '♥' : '♡') + ' '
    ctx.fillText(`ЖИЗНИ ${hearts.trim()}`, 14, 42)
    ctx.restore()

    // патроны — подписаны явно: "ПАТРОНЫ ▮▮▮" (общий пул волны, до 15 значков)
    ctx.save()
    ctx.font = `700 13px ${this.glyphFontFamily}`
    ctx.textAlign = 'right'
    ctx.fillStyle = '#111111'
    const show = Math.min(15, Math.max(0, this.ammoPool))
    ctx.fillText(`ПАТРОНЫ ${'▮'.repeat(show)}`, w - 14, 42)
    ctx.restore()
  }

  private _drawCenterText(ctx: CanvasRenderingContext2D, w: number, h: number, title: string, subtitle: string): void {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.fillStyle = '#111111'
    ctx.font = `700 30px ${this.glyphFontFamily}`
    ctx.fillText(title.toUpperCase(), w / 2, h / 2 - 8)
    ctx.font = `13px ${this.glyphFontFamily}`
    ctx.fillStyle = '#444444'
    ctx.fillText(subtitle, w / 2, h / 2 + 18)
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

    // "[ ЕЩЁ РАЗ ]" — тонкая чёрная рамка-кнопка
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

  // Публичный доступ только для DuckShootWindow.vue (заголовок окна читает
  // "идёт ли загрузка" из useLongWait.ts, а не из игры — этот геттер здесь
  // не нужен и не добавлен, чтобы не плодить второй источник того же флага).
}
