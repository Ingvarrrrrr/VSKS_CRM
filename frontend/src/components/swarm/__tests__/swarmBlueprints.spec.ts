import { describe, expect, it } from 'vitest'
import { buildSwarmBlueprint, SWARM_AGENTS } from '../swarmBlueprints'

describe('swarmBlueprints v2', () => {
  it('генерирует плотные детальные чертежи (>=35 примитивов) с инструментами rect/type/dup', () => {
    const sub = buildSwarmBlueprint('/subsidies', false, false, 1280, 760)
    expect(sub.kind).toBe('subsidies')
    expect(sub.screenTitle).toBe('Субсидии и ФЭО')
    expect(sub.items.length).toBeGreaterThanOrEqual(30)
    expect(sub.items.some((i) => i.tool === 'dup' && i.dupFromId)).toBe(true)
    expect(sub.items.some((i) => i.kind === 'tree-row')).toBe(true)

    const orders = buildSwarmBlueprint('/orders', false, false, 1280, 760)
    expect(orders.kind).toBe('registry')
    expect(orders.items.filter((i) => i.kind === 'table-row').length).toBeGreaterThanOrEqual(6)
    expect(orders.columns).toContain('Сумма ₽')

    const card = buildSwarmBlueprint('/orders/4884/edit', false, false, 1280, 760)
    expect(card.kind).toBe('form')
    expect(card.items.some((i) => i.kind === 'step')).toBe(true)

    const dash = buildSwarmBlueprint('/dashboard/radar', false, false, 1280, 760)
    expect(dash.kind).toBe('dashboard')
    expect(dash.items.some((i) => i.kind === 'chart' && i.tool === 'pen')).toBe(true)
  })

  it('адаптирует количество курсоров и ширину под мобильные экраны', () => {
    const mobile = buildSwarmBlueprint('/orders', true, false, 390, 740)
    const usedCursors = new Set(mobile.items.map((b) => b.cursorIndex))
    expect(usedCursors.size).toBeLessThanOrEqual(3)
    expect(mobile.items.every((b) => b.x + b.w <= 390)).toBe(true)
    expect(SWARM_AGENTS).toHaveLength(6)
  })
})
