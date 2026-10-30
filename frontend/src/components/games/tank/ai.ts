// ИИ компьютерных танков — общий код и для «диких» врагов PvE (1 игрок /
// ко-оп), и для союзных танков в «версусе» (п.2 задания — 2 компьютерных
// союзника на каждой стороне). Единственное место, где считается выбор
// направления и стрельба компьютером (Правило №6) — вызывается из
// tankGame.ts с разной целью (база/танк противника).

import type { Dir, Tank } from './types'

const DIRS: Dir[] = ['up', 'down', 'left', 'right']

export function dirVector(dir: Dir): { dx: number; dy: number } {
  if (dir === 'up') return { dx: 0, dy: -1 }
  if (dir === 'down') return { dx: 0, dy: 1 }
  if (dir === 'left') return { dx: -1, dy: 0 }
  return { dx: 1, dy: 0 }
}

export interface AiMoveContext {
  // true, если клетка/другой танк блокируют перемещение в (nx,ny)
  blocked(nx: number, ny: number): boolean
  inBounds(nx: number, ny: number): boolean
}

export function pickAiDirection(t: Tank, target: { x: number; y: number }, ctx: AiMoveContext): Dir {
  const scored = DIRS.map((dir) => {
    const { dx, dy } = dirVector(dir)
    const nx = t.x + dx
    const ny = t.y + dy
    const free = ctx.inBounds(nx, ny) && !ctx.blocked(nx, ny)
    const towardScore = -(Math.abs(target.x - nx) + Math.abs(target.y - ny))
    return { dir, free, towardScore }
  }).filter((c) => c.free)

  if (scored.length === 0) return DIRS[Math.floor(Math.random() * DIRS.length)]!
  if (Math.random() < 0.55) {
    scored.sort((a, b) => b.towardScore - a.towardScore)
    return scored[0]!.dir
  }
  return scored[Math.floor(Math.random() * scored.length)]!.dir
}

export interface AiTickContext extends AiMoveContext {
  tile: number
  fire(t: Tank): void
  fireCooldownMin: number
  fireCooldownMax: number
}

// Один тик ИИ-танка: едет текущим курсом, на таймере/препятствии выбирает
// новый (с уклоном к цели), периодически стреляет. target — координата
// (в клетках) того, что танк атакует: база или ближайший живой противник.
export function updateAiTank(t: Tank, dt: number, target: { x: number; y: number }, speed: number, ctx: AiTickContext): void {
  if (t.frozenTimer > 0) {
    t.frozenTimer = Math.max(0, t.frozenTimer - dt)
    return
  }

  t.changeDirTimer -= dt
  const { dx, dy } = dirVector(t.dir)
  const step = (speed * t.speedMul * dt) / ctx.tile
  const nx = t.x + dx * step
  const ny = t.y + dy * step
  const blocked = !ctx.inBounds(nx, ny) || ctx.blocked(nx, ny)

  if (!blocked) {
    t.x = nx
    t.y = ny
  }

  if (blocked || t.changeDirTimer <= 0) {
    t.dir = pickAiDirection(t, target, ctx)
    t.changeDirTimer = 0.6 + Math.random() * 1.2
  }

  t.cooldown -= dt
  if (t.cooldown <= 0) {
    ctx.fire(t)
    t.cooldown = ctx.fireCooldownMin + Math.random() * (ctx.fireCooldownMax - ctx.fireCooldownMin)
  }
}
