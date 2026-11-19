import { describe, expect, it } from 'vitest'
import { buildSwarmBlueprint, SWARM_AGENTS } from '../swarmBlueprints'

describe('swarmBlueprints v2 (реальные макеты GALA)', () => {
  it('строит реальную страницу Субсидий (/subsidies): карточки Абхазия/ДНР/ФАДМ и сводную полосу', () => {
    const sub = buildSwarmBlueprint('/subsidies', false, false, 1280, 760)
    expect(sub.kind).toBe('subsidies')
    expect(sub.screenTitle).toBe('Субсидии')
    expect(sub.items.length).toBeGreaterThanOrEqual(15)

    // Проверка реальных карточек субсидий
    const cardTexts = sub.items.filter((i) => i.kind === 'card').map((i) => i.text)
    expect(cardTexts).toContain('Абхазия')
    expect(cardTexts).toContain('ДНР')
    expect(cardTexts).toContain('ФАДМ_2026')

    // Проверка кнопок и чипов годов в шапке
    const headerChips = sub.items.filter((i) => i.kind === 'chip').map((i) => i.text)
    expect(headerChips).toContain('2026')
    expect(headerChips).toContain('2025')
    const buttons = sub.items.filter((i) => i.kind === 'btn-primary' || i.kind === 'btn-outline').map((i) => i.text)
    expect(buttons).toContain('+ ДОБАВИТЬ')
    expect(buttons).toContain('ШАБЛОН ФЭО')
    expect(buttons).toContain('ЭКСПОРТ')

    // Проверка нижней сводной полосы
    const summaryHead = sub.items.find((i) => i.id === 'sub-sum-head')
    expect(summaryHead).toBeDefined()
    expect(summaryHead?.cells?.some((c) => c.includes('СУБСИДИЙ: 15'))).toBe(true)
    expect(summaryHead?.cells?.some((c) => c.includes('ОБЩИЙ ЛИМИТ ВСКС'))).toBe(true)
  })

  it('строит реальную страницу Закупок (/orders): 6 кнопок, 4 KPI, фильтры, 8 вкладок и широкую таблицу', () => {
    const orders = buildSwarmBlueprint('/orders', false, false, 1280, 760)
    expect(orders.kind).toBe('registry')
    expect(orders.screenTitle).toBe('Закупки')

    // 6 кнопок шапки
    const buttons = orders.items.filter((i) => i.kind === 'btn-primary' || i.kind === 'btn-outline').map((i) => i.text)
    expect(buttons).toContain('+ ДОБАВИТЬ')
    expect(buttons).toContain('EXCEL')
    expect(buttons).toContain('РАЗНЕСТИ СТАТУСЫ')
    expect(buttons).toContain('СВЯЗИ')
    expect(buttons).toContain('ИМПОРТ')
    expect(buttons).toContain('ШАБЛОН')

    // 4 KPI карточки
    const kpis = orders.items.filter((i) => i.kind === 'kpi')
    expect(kpis.length).toBe(4)
    expect(kpis.some((k) => k.subtext?.includes('2 375 110,27 ₽'))).toBe(true)
    expect(kpis.some((k) => k.text === 'Заключено договоров')).toBe(true)

    // Фильтры и вкладки статусов
    expect(orders.items.some((i) => i.text === 'Субсидия: ФАДМ_2026')).toBe(true)
    const tabs = orders.items.filter((i) => i.id.startsWith('ord-tab-')).map((i) => i.text)
    expect(tabs).toContain('Все')
    expect(tabs).toContain('Желания сотрудников')
    expect(tabs).toContain('План закупок')
    expect(tabs).toContain('Ведётся работа')
    expect(tabs).toContain('Заключен договор')
    expect(tabs).toContain('Заказано')
    expect(tabs).toContain('Поставлено')
    expect(tabs).toContain('Оплачено')

    // Широкая таблица (10 колонок) и реальные строки
    expect(orders.columns).toContain('№ п/п')
    expect(orders.columns).toContain('РЕЕСТР. №')
    expect(orders.columns).toContain('ПРЕДМЕТ ДОГОВОРА')
    expect(orders.columns).toContain('КОНТРАГЕНТ')
    expect(orders.columns).toContain('СУБСИДИЯ')
    expect(orders.columns).toContain('ЦЕНА')
    expect(orders.columns).toContain('СТАТУС')

    const tableRows = orders.items.filter((i) => i.kind === 'table-row')
    expect(tableRows.length).toBeGreaterThanOrEqual(6)
    expect(tableRows.some((r) => r.cells?.includes('РЕЕ-2026-04999'))).toBe(true)
    expect(tableRows.some((r) => r.cells?.includes('ООО "Сигма"'))).toBe(true)
  })

  it('строит страницу Категорий ФЭО (/feo-categories) с деревом и селектором субсидии', () => {
    const feo = buildSwarmBlueprint('/feo-categories', false, false, 1280, 760)
    expect(feo.kind).toBe('subsidies')
    expect(feo.screenTitle).toBe('Категории ФЭО')
    expect(feo.items.some((i) => i.text?.includes('Субсидия: ФАДМ_2026'))).toBe(true)
    expect(feo.items.some((i) => i.kind === 'tree-row')).toBe(true)
  })

  it('поддерживает карточку закупки и дашборд аналитики', () => {
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
