// Бонусы (п.4 задания) — один источник истины для типов, тайминга и эффекта
// каждого бонуса; применение (applyPowerUp) и отрисовка иконки читают
// отсюда, не дублируют список типов где-то ещё (Правило №6).

import type { PowerUp, PowerUpType, Side, Tank } from './types'
import { FENCE_STEEL_SECONDS, FREEZE_SECONDS, POWERUP_LIFETIME, POWERUP_UPGRADE_MAX, SHIELD_POWERUP_SECONDS } from './types'

export const POWERUP_TYPES: PowerUpType[] = ['star', 'helmet', 'clock', 'shovel', 'grenade', 'tank']

export function randomPowerUpType(): PowerUpType {
  return POWERUP_TYPES[Math.floor(Math.random() * POWERUP_TYPES.length)]!
}

export function spawnPowerUp(type: PowerUpType, x: number, y: number, list: PowerUp[]): void {
  list.push({ type, x, y, t: 0 })
}

export function updatePowerUps(list: PowerUp[], dt: number): PowerUp[] {
  for (const p of list) p.t += dt
  return list.filter((p) => p.t < POWERUP_LIFETIME)
}

export interface PowerUpHooks {
  freezeSide(side: Side, seconds: number): void
  fortifyBaseFence(side: Side, seconds: number): void
  destroyTanksOfSide(side: Side): void
  addLife(collector: Tank): void
}

// Эффект бонуса (п.4): звезда — апгрейд, каска — щит, часы — заморозка
// противника, лопата — стальная ограда базы, гранат — уничтожить вражеские
// танки на поле, танк — +1 жизнь. opposingSide считает вызывающий код
// (tankGame.ts), т.к. зависит от режима (PvE противник — 'wild', в
// «версусе» — противоположная сторона).
export function applyPowerUp(type: PowerUpType, collector: Tank, opposingSide: Side, hooks: PowerUpHooks): void {
  switch (type) {
    case 'star':
      collector.level = Math.min(POWERUP_UPGRADE_MAX, collector.level + 1)
      break
    case 'helmet':
      collector.shieldTimer = Math.max(collector.shieldTimer, SHIELD_POWERUP_SECONDS)
      break
    case 'clock':
      hooks.freezeSide(opposingSide, FREEZE_SECONDS)
      break
    case 'shovel':
      hooks.fortifyBaseFence(collector.side, FENCE_STEEL_SECONDS)
      break
    case 'grenade':
      hooks.destroyTanksOfSide(opposingSide)
      break
    case 'tank':
      hooks.addLife(collector)
      break
  }
}

// Иконки бонусов — свои векторные рисунки на канве (п.4 допускает это как
// альтернативу спрайт-паку, если подходящего набора под рукой нет).
export function drawPowerUpIcon(ctx: CanvasRenderingContext2D, type: PowerUpType, cx: number, cy: number, size: number): void {
  const r = size / 2
  ctx.save()
  ctx.translate(cx, cy)

  const bg: Record<PowerUpType, string> = {
    star: '#f4c430',
    helmet: '#5b7fa6',
    clock: '#eeeeee',
    shovel: '#a67c52',
    grenade: '#4a7c40',
    tank: '#d6436e',
  }
  ctx.beginPath()
  ctx.arc(0, 0, r, 0, Math.PI * 2)
  ctx.fillStyle = bg[type]
  ctx.fill()
  ctx.strokeStyle = 'rgba(0,0,0,0.55)'
  ctx.lineWidth = Math.max(1, size * 0.06)
  ctx.stroke()

  ctx.fillStyle = '#1a1a1a'
  ctx.strokeStyle = '#1a1a1a'
  ctx.lineWidth = Math.max(1, size * 0.08)

  if (type === 'star') {
    ctx.beginPath()
    for (let i = 0; i < 5; i++) {
      const a1 = -Math.PI / 2 + (i * 2 * Math.PI) / 5
      const a2 = a1 + Math.PI / 5
      const x1 = Math.cos(a1) * r * 0.55
      const y1 = Math.sin(a1) * r * 0.55
      const x2 = Math.cos(a2) * r * 0.22
      const y2 = Math.sin(a2) * r * 0.22
      if (i === 0) ctx.moveTo(x1, y1)
      else ctx.lineTo(x1, y1)
      ctx.lineTo(x2, y2)
    }
    ctx.closePath()
    ctx.fillStyle = '#7a4e00'
    ctx.fill()
  } else if (type === 'helmet') {
    ctx.beginPath()
    ctx.arc(0, r * 0.05, r * 0.5, Math.PI, 0)
    ctx.fillStyle = '#eef2f7'
    ctx.fill()
    ctx.beginPath()
    ctx.moveTo(-r * 0.55, r * 0.1)
    ctx.lineTo(r * 0.55, r * 0.1)
    ctx.lineWidth = Math.max(1, size * 0.1)
    ctx.strokeStyle = '#2a3a4a'
    ctx.stroke()
  } else if (type === 'clock') {
    ctx.beginPath()
    ctx.arc(0, 0, r * 0.55, 0, Math.PI * 2)
    ctx.strokeStyle = '#333333'
    ctx.lineWidth = Math.max(1, size * 0.08)
    ctx.stroke()
    ctx.beginPath()
    ctx.moveTo(0, 0)
    ctx.lineTo(0, -r * 0.4)
    ctx.moveTo(0, 0)
    ctx.lineTo(r * 0.3, r * 0.08)
    ctx.stroke()
  } else if (type === 'shovel') {
    ctx.save()
    ctx.rotate(Math.PI / 4)
    ctx.fillStyle = '#6b4a2b'
    ctx.fillRect(-r * 0.1, -r * 0.55, r * 0.2, r * 0.75)
    ctx.beginPath()
    ctx.moveTo(-r * 0.3, r * 0.2)
    ctx.lineTo(r * 0.3, r * 0.2)
    ctx.lineTo(r * 0.18, r * 0.55)
    ctx.lineTo(-r * 0.18, r * 0.55)
    ctx.closePath()
    ctx.fillStyle = '#c7c7c7'
    ctx.fill()
    ctx.restore()
  } else if (type === 'grenade') {
    ctx.beginPath()
    ctx.arc(0, r * 0.1, r * 0.45, 0, Math.PI * 2)
    ctx.fillStyle = '#2f5c2a'
    ctx.fill()
    ctx.beginPath()
    ctx.moveTo(0, -r * 0.35)
    ctx.lineTo(r * 0.15, -r * 0.6)
    ctx.strokeStyle = '#1a1a1a'
    ctx.lineWidth = Math.max(1, size * 0.07)
    ctx.stroke()
  } else if (type === 'tank') {
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(-r * 0.4, -r * 0.3, r * 0.8, r * 0.55)
    ctx.fillRect(-r * 0.12, -r * 0.55, r * 0.24, r * 0.3)
  }
  ctx.restore()
}

export function powerUpBlinkAlpha(t: number): number {
  const remaining = POWERUP_LIFETIME - t
  if (remaining > 4) return 1
  const freq = remaining > 1.5 ? 4 : 8
  return 0.4 + 0.6 * Math.abs(Math.sin(t * freq))
}
