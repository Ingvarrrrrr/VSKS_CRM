// Отрисовка «Танчиков» — доска/танки/пули/взрывы/бонусы/HUD/меню/пэд.
// Чистые функции: принимают ctx и данные явными параметрами, ничего не
// хранят сами (состояние — в tankGame.ts), поэтому не создают циклических
// импортов с остальными модулями игры.

import { isSpriteReady } from '../spriteLoader'
import { drawPowerUpIcon, powerUpBlinkAlpha } from './powerups'
import type { Bullet, Dir, Explosion, PowerUp, Rect, Tank, Tile } from './types'

export const HUD_FONT_FAMILY = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
export const GLYPH_FONT_FAMILY = 'Consolas, "JetBrains Mono", "Courier New", monospace'
export const EXPLOSION_DURATION = 0.3

export interface TankSprites {
  grass: HTMLImageElement
  brickWall: HTMLImageElement
  steelWall: HTMLImageElement
  tree: HTMLImageElement
  bodyPlayer: HTMLImageElement
  barrelPlayer: HTMLImageElement
  bodyEnemy: HTMLImageElement
  barrelEnemy: HTMLImageElement
  bodyTough: HTMLImageElement
  barrelTough: HTMLImageElement
  bulletPlayer: HTMLImageElement
  bulletEnemy: HTMLImageElement
  explosion: HTMLImageElement[]
  base: HTMLImageElement
}

export function dirAngle(dir: Dir): number {
  if (dir === 'up') return 0
  if (dir === 'right') return Math.PI / 2
  if (dir === 'down') return Math.PI
  return -Math.PI / 2
}

export function tankRect(t: Pick<Tank, 'x' | 'y'>, tile: number): Rect {
  const size = tile * 0.92
  return { x: t.x * tile + (tile - size) / 2, y: t.y * tile + (tile - size) / 2, w: size, h: size }
}

export function drawGround(ctx: CanvasRenderingContext2D, sprites: TankSprites, tile: number, cols: number, rows: number): void {
  const img = sprites.grass
  if (isSpriteReady(img)) {
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) ctx.drawImage(img, x * tile, y * tile, tile, tile)
    }
  } else {
    ctx.fillStyle = '#eef3e8'
    ctx.fillRect(0, 0, cols * tile, rows * tile)
  }
}

export function drawBoard(ctx: CanvasRenderingContext2D, sprites: TankSprites, tile: number, grid: Tile[][], glyphFont: string): void {
  ctx.save()
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  const t = tile
  const brick = sprites.brickWall
  const steel = sprites.steelWall
  const base = sprites.base

  for (let y = 0; y < grid.length; y++) {
    const row = grid[y]!
    for (let x = 0; x < row.length; x++) {
      const tl = row[x]!
      if (tl.type === 'empty') continue
      const cx = x * t + t / 2
      const cy = y * t + t / 2

      if (tl.type === 'brick' && tl.damage < 4) {
        const half = t / 2
        const quads: Array<[number, number]> = [[0, 0], [half, 0], [0, half], [half, half]]
        ctx.save()
        ctx.beginPath()
        let any = false
        for (let i = 0; i < 4; i++) {
          if (i < tl.damage) continue
          any = true
          ctx.rect(x * t + (quads[i]?.[0] ?? 0), y * t + (quads[i]?.[1] ?? 0), half, half)
        }
        if (any) {
          ctx.clip()
          if (isSpriteReady(brick)) ctx.drawImage(brick, x * t, y * t, t, t)
          else { ctx.fillStyle = '#8b5a2b'; ctx.fillRect(x * t, y * t, t, t) }
        }
        ctx.restore()
      } else if (tl.type === 'steel') {
        if (isSpriteReady(steel)) ctx.drawImage(steel, x * t, y * t, t, t)
        else { ctx.fillStyle = '#777777'; ctx.fillRect(x * t, y * t, t, t) }
      } else if (tl.type === 'water') {
        ctx.fillStyle = '#3f7fc4'
        ctx.fillRect(x * t, y * t, t, t)
        ctx.strokeStyle = 'rgba(255,255,255,0.55)'
        ctx.lineWidth = Math.max(1, t * 0.07)
        ctx.beginPath()
        ctx.moveTo(x * t + t * 0.1, cy - t * 0.08)
        ctx.quadraticCurveTo(cx, cy + t * 0.12, x * t + t * 0.9, cy - t * 0.08)
        ctx.stroke()
      } else if (tl.type === 'base') {
        if (isSpriteReady(base)) {
          ctx.drawImage(base, x * t + t * 0.08, y * t + t * 0.08, t * 0.84, t * 0.84)
        } else {
          ctx.font = `700 ${Math.max(6, t * 0.85)}px ${glyphFont}`
          ctx.fillStyle = '#111111'
          ctx.fillText('★', cx, cy + 1)
        }
      }
    }
  }
  ctx.restore()
}

export function drawTrees(ctx: CanvasRenderingContext2D, sprites: TankSprites, tile: number, grid: Tile[][], glyphFont: string): void {
  const img = sprites.tree
  const t = tile
  ctx.save()
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  for (let y = 0; y < grid.length; y++) {
    const row = grid[y]!
    for (let x = 0; x < row.length; x++) {
      if (row[x]!.type !== 'tree') continue
      if (isSpriteReady(img)) {
        const size = t * 1.18
        ctx.drawImage(img, x * t + t / 2 - size / 2, y * t + t / 2 - size / 2, size, size)
      } else {
        ctx.font = `700 ${Math.max(6, t * 0.95)}px ${glyphFont}`
        ctx.fillStyle = '#999999'
        ctx.fillText('♣', x * t + t / 2, y * t + t / 2 + 1)
      }
    }
  }
  ctx.restore()
}

function tankGlyphBlock(dir: Dir): string[] {
  if (dir === 'up') return ['╔▲╗', '╠█╣', '╚╩╝']
  if (dir === 'down') return ['╔╦╗', '╠█╣', '╚▼╝']
  if (dir === 'left') return ['╔╦╗', '◄█╣', '╚╩╝']
  return ['╔╦╗', '╠█►', '╚╩╝']
}

function drawTankFallback(ctx: CanvasRenderingContext2D, t: Tank, tile: number, color: string, glyphFont: string): void {
  const r = tankRect(t, tile)
  const lines = tankGlyphBlock(t.dir)
  const fontPx = Math.max(6, r.w / 3.1)
  ctx.save()
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.font = `700 ${fontPx}px ${glyphFont}`
  ctx.fillStyle = color
  const lineH = r.h / 3
  for (let i = 0; i < 3; i++) {
    ctx.fillText(lines[i] ?? '', r.x + r.w / 2, r.y + lineH * i + lineH / 2 + 1)
  }
  ctx.restore()
}

// Какой спрайт и какой оттенок у танка — одна функция на игрока/союзника/
// врага, п.5-6 задания просят разные цвета Kenney-танков, а в комплекте
// их всего три расцветки (игрок/враг/«крепкий»): недостающие оттенки для
// 2-го игрока, союзников и «быстрого» врага получены CSS-фильтром
// hue-rotate на канве — без новых файлов спрайтов.
function tankVisual(t: Tank, sprites: TankSprites): { body: HTMLImageElement; barrel: HTMLImageElement; filter: string; fallback: string } {
  if (t.kind === 'player') {
    if (t.side === 'north') return { body: sprites.bodyPlayer, barrel: sprites.barrelPlayer, filter: 'hue-rotate(200deg) saturate(1.5)', fallback: '#1b3a8a' }
    return { body: sprites.bodyPlayer, barrel: sprites.barrelPlayer, filter: 'none', fallback: '#111111' }
  }
  if (t.kind === 'ally') {
    if (t.side === 'north') return { body: sprites.bodyTough, barrel: sprites.barrelTough, filter: 'hue-rotate(50deg)', fallback: '#6a4fb3' }
    return { body: sprites.bodyEnemy, barrel: sprites.barrelEnemy, filter: 'hue-rotate(90deg)', fallback: '#2e7d32' }
  }
  // враг PvE
  if (t.enemyType === 'armored') return { body: sprites.bodyTough, barrel: sprites.barrelTough, filter: 'none', fallback: '#000000' }
  if (t.enemyType === 'fast') return { body: sprites.bodyEnemy, barrel: sprites.barrelEnemy, filter: 'hue-rotate(300deg) saturate(1.7)', fallback: '#c66a00' }
  return { body: sprites.bodyEnemy, barrel: sprites.barrelEnemy, filter: 'none', fallback: '#555555' }
}

function drawOneTank(ctx: CanvasRenderingContext2D, t: Tank, tile: number, sprites: TankSprites, glyphFont: string): void {
  const v = tankVisual(t, sprites)
  if (!isSpriteReady(v.body) || !isSpriteReady(v.barrel)) {
    drawTankFallback(ctx, t, tile, v.fallback, glyphFont)
    return
  }
  const r = tankRect(t, tile)
  const cx = r.x + r.w / 2
  const cy = r.y + r.h / 2
  const size = r.w
  ctx.save()
  ctx.translate(cx, cy)
  ctx.rotate(dirAngle(t.dir))
  if (v.filter !== 'none') ctx.filter = v.filter
  ctx.drawImage(v.body, -size / 2, -size / 2, size, size)
  const barrelW = size * 0.22
  const barrelH = size * 0.68
  ctx.drawImage(v.barrel, -barrelW / 2, -size * 0.58, barrelW, barrelH)
  if (v.filter !== 'none') ctx.filter = 'none'
  ctx.restore()

  if (t.shieldTimer > 0) {
    ctx.save()
    ctx.strokeStyle = 'rgba(120,220,255,0.85)'
    ctx.lineWidth = Math.max(1, size * 0.08)
    ctx.beginPath()
    ctx.arc(cx, cy, size * 0.62, 0, Math.PI * 2)
    ctx.stroke()
    ctx.restore()
  }
  if (t.frozenTimer > 0) {
    ctx.save()
    ctx.fillStyle = 'rgba(160,220,255,0.35)'
    ctx.fillRect(r.x, r.y, r.w, r.h)
    ctx.restore()
  }

  if (t.level > 0 && t.kind === 'player') {
    ctx.save()
    ctx.textAlign = 'center'
    ctx.font = `700 ${Math.max(6, tile * 0.3)}px ${glyphFont}`
    ctx.fillStyle = '#ffffff'
    ctx.shadowColor = 'rgba(0,0,0,0.8)'
    ctx.shadowBlur = 2
    ctx.fillText(String(t.level + 1), cx, r.y - 2)
    ctx.restore()
  }
}

export function drawTanks(ctx: CanvasRenderingContext2D, sprites: TankSprites, tile: number, tanks: Tank[], grid: Tile[][], glyphFont: string): void {
  for (const t of tanks) {
    if (!t.alive) continue
    drawOneTank(ctx, t, tile, sprites, glyphFont)
  }
  drawTrees(ctx, sprites, tile, grid, glyphFont)
}

export function drawBullets(ctx: CanvasRenderingContext2D, sprites: TankSprites, tile: number, bullets: Bullet[], glyphFont: string): void {
  for (const b of bullets) {
    if (!b.alive) continue
    const img = b.owner === 'wild' ? sprites.bulletEnemy : b.owner === 'north' ? sprites.bulletEnemy : sprites.bulletPlayer
    if (isSpriteReady(img)) {
      const w = tile * 0.22
      const h = tile * 0.5
      ctx.save()
      ctx.translate(b.x, b.y)
      ctx.rotate(dirAngle(b.dir))
      ctx.drawImage(img, -w / 2, -h / 2, w, h)
      ctx.restore()
    } else {
      ctx.save()
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.font = `700 ${Math.max(8, tile * 0.5)}px ${glyphFont}`
      ctx.fillStyle = '#111111'
      ctx.fillText('•', b.x, b.y + 1)
      ctx.restore()
    }
  }
}

export function drawExplosions(ctx: CanvasRenderingContext2D, sprites: TankSprites, tile: number, explosions: Explosion[]): void {
  const frames = sprites.explosion
  if (frames.length === 0) return
  for (const ex of explosions) {
    const progress = Math.min(0.999, ex.t / EXPLOSION_DURATION)
    const img = frames[Math.floor(progress * frames.length)] ?? frames[0]
    if (!img || !isSpriteReady(img)) continue
    const size = tile * 1.3
    ctx.save()
    ctx.globalAlpha = Math.max(0.15, 1 - progress)
    ctx.drawImage(img, ex.x - size / 2, ex.y - size / 2, size, size)
    ctx.restore()
  }
}

export function drawPowerUps(ctx: CanvasRenderingContext2D, tile: number, powerUps: PowerUp[]): void {
  for (const p of powerUps) {
    const cx = (p.x + 0.5) * tile
    const cy = (p.y + 0.5) * tile
    ctx.save()
    ctx.globalAlpha = powerUpBlinkAlpha(p.t)
    drawPowerUpIcon(ctx, p.type, cx, cy, tile * 0.82)
    ctx.restore()
  }
}

export interface HudSideData {
  label: string
  lives?: number
  level?: number
  enemiesLeft?: number
  enemiesAlive?: number
  score: number
}

export function drawHud(ctx: CanvasRenderingContext2D, w: number, lines: string[]): void {
  ctx.save()
  ctx.font = `700 13px ${HUD_FONT_FAMILY}`
  ctx.shadowColor = 'rgba(0,0,0,0.75)'
  ctx.shadowBlur = 3
  ctx.shadowOffsetY = 1
  ctx.fillStyle = '#ffffff'
  ctx.textAlign = 'left'
  let y = 18
  for (const line of lines) {
    ctx.fillText(line, 14, y)
    y += 18
  }
  ctx.restore()
  void w
}

export function drawTouchPad(ctx: CanvasRenderingContext2D, pad: { up: Rect; down: Rect; left: Rect; right: Rect; fire: Rect }, touchDir: Dir | null, touchFire: boolean, glyphFont: string): void {
  ctx.save()
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.font = `700 16px ${glyphFont}`
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
  draw(pad.up, '▲', touchDir === 'up')
  draw(pad.down, '▼', touchDir === 'down')
  draw(pad.left, '◄', touchDir === 'left')
  draw(pad.right, '►', touchDir === 'right')
  draw(pad.fire, '●', touchFire)
  ctx.restore()
}

export function drawCenterText(ctx: CanvasRenderingContext2D, w: number, h: number, title: string, subtitle: string, glyphFont: string): void {
  ctx.save()
  ctx.textAlign = 'center'
  ctx.shadowColor = 'rgba(0,0,0,0.75)'
  ctx.shadowBlur = 4
  ctx.shadowOffsetY = 1
  if (title) {
    ctx.fillStyle = '#ffffff'
    ctx.font = `700 24px ${glyphFont}`
    ctx.fillText(title.toUpperCase(), w / 2, h / 2 - 8)
  }
  if (subtitle) {
    ctx.font = `13px ${glyphFont}`
    ctx.fillStyle = '#eeeeee'
    ctx.fillText(subtitle, w / 2, h / 2 + (title ? 18 : 0))
  }
  ctx.restore()
}

export interface MenuItem {
  mode: string
  title: string
}

// Расчёт прямоугольников пунктов меню — один раз здесь, читают и отрисовка
// (drawMenu), и обработчик клика в tankGame.ts (Правило №6: нет смысла
// держать те же числа в двух местах).
export function menuItemRects(w: number, h: number, count: number, itemH = 40): Rect[] {
  const startY = h / 2 - (count * itemH) / 2
  const rects: Rect[] = []
  for (let i = 0; i < count; i++) {
    rects.push({ x: w / 2 - 140, y: startY + i * itemH - itemH / 2 + 4, w: 280, h: itemH - 6 })
  }
  return rects
}

// Стартовое меню (п.2 задания) — рисуется прямо на канве, без DOM.
export function drawMenu(ctx: CanvasRenderingContext2D, w: number, h: number, items: MenuItem[], selected: number, glyphFont: string, hudFont: string): void {
  ctx.save()
  ctx.fillStyle = 'rgba(0,0,0,0.35)'
  ctx.fillRect(0, 0, w, h)

  ctx.textAlign = 'center'
  ctx.shadowColor = 'rgba(0,0,0,0.8)'
  ctx.shadowBlur = 4
  ctx.fillStyle = '#ffffff'
  ctx.font = `700 26px ${glyphFont}`
  ctx.fillText('ТАНЧИКИ', w / 2, h * 0.22)

  const itemH = 40
  const rects = menuItemRects(w, h, items.length, itemH)
  items.forEach((item, i) => {
    const y = rects[i]!.y + rects[i]!.h / 2 + 5
    const active = i === selected
    ctx.font = `${active ? '700' : '400'} 17px ${hudFont}`
    ctx.fillStyle = active ? '#ffe28a' : '#ffffff'
    ctx.fillText(active ? `▶ ${item.title}` : item.title, w / 2, y)
  })

  ctx.font = `13px ${hudFont}`
  ctx.fillStyle = '#dddddd'
  ctx.fillText('Игрок 1: WASD + Пробел      Игрок 2: стрелки + Enter', w / 2, h - 46)
  ctx.fillText('↑↓ — выбор, Enter — старт, P — пауза в игре', w / 2, h - 26)
  ctx.restore()
}

export function drawPaused(ctx: CanvasRenderingContext2D, w: number, h: number, glyphFont: string): void {
  ctx.save()
  ctx.fillStyle = 'rgba(0,0,0,0.45)'
  ctx.fillRect(0, 0, w, h)
  ctx.restore()
  drawCenterText(ctx, w, h, 'ПАУЗА', 'P — продолжить', glyphFont)
}

export function drawGameOverOverlay(ctx: CanvasRenderingContext2D, w: number, h: number, title: string, info: string, glyphFont: string): Rect {
  ctx.save()
  ctx.textAlign = 'center'
  ctx.shadowColor = 'rgba(0,0,0,0.75)'
  ctx.shadowBlur = 4
  ctx.shadowOffsetY = 1
  ctx.fillStyle = '#ffffff'
  ctx.font = `700 24px ${glyphFont}`
  ctx.fillText(title, w / 2, h / 2 - 30)
  ctx.font = `14px ${glyphFont}`
  ctx.fillText(info, w / 2, h / 2 - 4)

  const btnW = 200, btnH = 36
  const bx = w / 2 - btnW / 2, by = h / 2 + 16
  ctx.strokeStyle = '#ffffff'
  ctx.lineWidth = 1
  ctx.strokeRect(bx, by, btnW, btnH)
  ctx.fillStyle = '#ffffff'
  ctx.font = `700 14px ${glyphFont}`
  ctx.fillText('[ В МЕНЮ — ENTER ]', w / 2, by + btnH / 2 + 5)
  ctx.restore()

  return { x: bx, y: by, w: btnW, h: btnH }
}
