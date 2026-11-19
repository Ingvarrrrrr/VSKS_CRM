// Высокоплотные чертёжные макеты реальных страниц GALA для Swarm Rebuild v2.
import {
  FEO_CATEGORIES_TREE,
  ORDERS_FILTERS,
  ORDERS_HEADER_BUTTONS,
  ORDERS_KPIS,
  ORDERS_STATUS_TABS,
  ORDERS_TABLE_COLS,
  ORDERS_TABLE_ROWS,
  ROUTE_CONFIGS,
  SUBSIDY_CARDS,
  SUBSIDY_SUMMARY_METRICS,
  type TableRowData,
} from './swarmBlueprintData'
import { SWARM_AGENTS, type SwarmBlueprint, type SwarmBlueprintKind, type SwarmItem } from './swarmTypes'

export { SWARM_AGENTS } from './swarmTypes'
export type { SwarmAgent, SwarmBlueprint, SwarmBlueprintKind, SwarmItem } from './swarmTypes'

interface RouteDescriptor {
  kind: SwarmBlueprintKind
  title: string
  subtitle?: string
  columns?: string[]
}

export function describeRouteForSwarm(path: string): RouteDescriptor {
  const clean = (path || '/').split('?')[0]
  if (clean.startsWith('/subsidies/') && clean.includes('/revisions')) {
    return { kind: 'form', title: 'Ревизия ФЭО', columns: ['Категория', 'Было', 'Стало', 'Δ ₽'] }
  }
  if (clean === '/subsidies' || clean === '/subsidies/') {
    return { kind: 'subsidies', title: 'Субсидии', subtitle: 'Управление субсидиями и распределением бюджета - 2026' }
  }
  if (clean.startsWith('/feo-categories')) {
    return { kind: 'subsidies', title: 'Категории ФЭО', subtitle: 'Справочник категорий ФЭО · ФАДМ_2026', columns: ['Код', 'Наименование', 'Тип', 'Статус', 'Лимит ₽'] }
  }
  if (clean.startsWith('/orders') && !/^\/orders\/[^/]+/.test(clean)) {
    return { kind: 'registry', title: 'Закупки', subtitle: '724 записей', columns: ORDERS_TABLE_COLS }
  }
  if (/^\/orders\/[^/]+/.test(clean) || /^\/(service-notes|advance-reports)\/(create|[^/]+\/edit)/.test(clean)) {
    return { kind: 'form', title: 'Карточка закупки РЕЕ-2026-04884', columns: ['Наименование', 'Как в ТЗ', 'Как в договоре', 'Поставка', 'Сумма ₽'] }
  }
  if (ROUTE_CONFIGS[clean]) {
    const cfg = ROUTE_CONFIGS[clean]
    return { kind: 'registry', title: cfg.title, subtitle: cfg.subtitle, columns: cfg.columns }
  }
  if (clean.startsWith('/dashboard') || clean.startsWith('/analytics') || clean.startsWith('/reports')) {
    return { kind: 'dashboard', title: clean.startsWith('/dashboard/radar') ? 'Радар рисков' : 'Сводная аналитика' }
  }
  if (clean.startsWith('/my-tasks') || clean.startsWith('/chat')) {
    return { kind: 'tasks', title: clean.startsWith('/chat') ? 'Рабочий чат' : 'Мои задачи и контроль' }
  }
  return { kind: 'boot', title: 'Рабочее пространство GALA' }
}

export function buildSwarmBlueprint(path: string, isMobile: boolean, booting: boolean, width = 1280, height = 760): SwarmBlueprint {
  const clean = (path || '/').split('?')[0]
  const desc = booting && clean === '/' ? { kind: 'boot' as const, title: 'Рабочее пространство GALA' } : describeRouteForSwarm(clean)
  const cols = desc.columns || ORDERS_TABLE_COLS
  const agentLimit = isMobile ? 3 : SWARM_AGENTS.length
  const c = (i: number) => i % agentLimit
  const padX = isMobile ? 14 : 32
  const topY = isMobile ? 26 : 30
  const cw = Math.max(300, width - padX * 2)
  const items: SwarmItem[] = []

  // 1. Маршрут /subsidies: Шапка + Сетка 6 колонок субсидий + Сводная полоса
  if (desc.kind === 'subsidies' && (clean === '/subsidies' || clean === '/subsidies/')) {
    items.push({
      id: 'sub-title', kind: 'heading', tool: 'type', x: padX, y: topY, w: isMobile ? cw * 0.7 : 460, h: 32,
      text: desc.title, subtext: desc.subtitle || 'Управление субсидиями и распределением бюджета - 2026', cursorIndex: c(0), startMs: 20, durationMs: 340,
    })
    if (!isMobile) {
      items.push({ id: 'yr-26', kind: 'chip', tool: 'rect', x: padX + 470, y: topY + 2, w: 68, h: 28, rx: 999, text: '2026', accent: true, cursorIndex: c(1), startMs: 70, durationMs: 220 })
      items.push({ id: 'yr-25', kind: 'chip', tool: 'dup', dupFromId: 'yr-26', x: padX + 544, y: topY + 2, w: 68, h: 28, rx: 999, text: '2025', cursorIndex: c(2), startMs: 110, durationMs: 220 })
      items.push({ id: 'btn-add', kind: 'btn-primary', tool: 'rect', x: padX + cw - 146, y: topY, w: 146, h: 34, rx: 8, text: '+ ДОБАВИТЬ', accent: true, cursorIndex: c(3), startMs: 80, durationMs: 300 })
      items.push({ id: 'btn-tmpl', kind: 'btn-outline', tool: 'dup', dupFromId: 'btn-add', x: padX + cw - 280, y: topY, w: 126, h: 34, rx: 8, text: 'ШАБЛОН ФЭО', cursorIndex: c(4), startMs: 140, durationMs: 260 })
      items.push({ id: 'btn-exp', kind: 'btn-outline', tool: 'dup', dupFromId: 'btn-tmpl', x: padX + cw - 388, y: topY, w: 100, h: 34, rx: 8, text: 'ЭКСПОРТ', cursorIndex: c(5), startMs: 180, durationMs: 260 })
    } else {
      items.push({ id: 'btn-add', kind: 'btn-primary', tool: 'rect', x: padX + cw - 110, y: topY, w: 110, h: 32, rx: 8, text: '+ ДОБАВИТЬ', accent: true, cursorIndex: c(1), startMs: 70, durationMs: 260 })
    }

    const gridTop = topY + 46
    const gridBottom = height - (isMobile ? 74 : 58)
    const gridH = Math.max(220, gridBottom - gridTop)
    const colsCount = isMobile ? 2 : Math.max(4, Math.min(12, Math.floor((cw + 10) / 190)))
    const cardLimit = isMobile ? 6 : SUBSIDY_CARDS.length
    const rowsCount = Math.max(1, Math.ceil(cardLimit / colsCount))
    const gapX = 10
    const gapY = 8
    const cardW = Math.floor((cw - (colsCount - 1) * gapX) / colsCount)
    const cardH = isMobile ? 140 : Math.min(245, Math.max(180, Math.floor((gridH - (rowsCount - 1) * gapY) / Math.max(2, rowsCount))))

    for (let i = 0; i < cardLimit; i++) {
      const card = SUBSIDY_CARDS[i]
      const col = i % colsCount
      const row = Math.floor(i / colsCount)
      const cx = padX + col * (cardW + gapX)
      const cy = gridTop + row * (cardH + gapY)
      items.push({
        id: `sub-card-${i}`, kind: 'card', tool: i === 0 ? 'rect' : 'dup', dupFromId: i === 0 ? undefined : 'sub-card-0',
        x: cx, y: cy, w: cardW, h: cardH, rx: 10, text: card.name,
        subtext: card.budget.replace(' · Бюджет ВСКС', ''),
        cells: [card.planned, card.ordered, card.paid, card.feoNote || '✓ ФЭО = план', card.org || 'ВСКС', card.pctText || '100% запланировано'],
        rightText: isMobile ? undefined : `Заказ: ${card.ordered}`, statusText: card.feoStatus, statusColor: card.statusColor,
        cursorIndex: c(i), startMs: 160 + i * 55, durationMs: 280,
      })
    }

    const barY = Math.min(height - (isMobile ? 64 : 50), gridTop + rowsCount * (cardH + gapY) + 10)
    const barH = isMobile ? 54 : 42
    items.push({ id: 'sub-sum-box', kind: 'card', tool: 'rect', x: padX, y: barY, w: cw, h: barH, rx: 8, cursorIndex: c(0), startMs: 650, durationMs: 320 })
    items.push({
      id: 'sub-sum-head', kind: 'table-head', tool: 'type', x: padX + 6, y: barY + 4, w: cw - 12, h: barH - 8, rx: 6,
      cells: SUBSIDY_SUMMARY_METRICS.slice(0, isMobile ? 3 : 10).map((m) => `${m[0]}: ${m[1]}`),
      cursorIndex: c(1), startMs: 720, durationMs: 360,
    })
    return { kind: desc.kind, screenTitle: desc.title, items, columns: cols }
  }

  // 2. Маршрут /orders: Шапка (6 кнопок) + 4 KPI + Фильтры + 8 вкладок + Таблица 10 колонок
  if (clean.startsWith('/orders') && !/^\/orders\/[^/]+/.test(clean)) {
    items.push({
      id: 'ord-title', kind: 'heading', tool: 'type', x: padX, y: topY, w: isMobile ? cw * 0.6 : 320, h: 32,
      text: desc.title, subtext: desc.subtitle || '724 записей', cursorIndex: c(0), startMs: 15, durationMs: 300,
    })
    if (!isMobile) {
      const btnDefs = [
        { label: '+ ДОБАВИТЬ', w: 120, accent: true, kind: 'btn-primary' as const },
        { label: 'EXCEL', w: 86, accent: false, kind: 'btn-outline' as const },
        { label: 'РАЗНЕСТИ СТАТУСЫ', w: 162, accent: false, kind: 'btn-outline' as const },
        { label: 'СВЯЗИ', w: 86, accent: false, kind: 'btn-outline' as const },
        { label: 'ИМПОРТ', w: 94, accent: false, kind: 'btn-outline' as const },
        { label: 'ШАБЛОН', w: 98, accent: false, kind: 'btn-outline' as const },
      ]
      let bx = padX + cw
      btnDefs.forEach((b, idx) => {
        bx -= (b.w + 8)
        items.push({
          id: `ord-btn-${idx}`, kind: b.kind, tool: idx === 0 ? 'rect' : 'dup', dupFromId: idx === 0 ? undefined : `ord-btn-0`,
          x: bx, y: topY, w: b.w, h: 34, rx: 8, text: b.label, accent: b.accent,
          cursorIndex: c(idx + 1), startMs: 45 + idx * 45, durationMs: 260,
        })
      })
    } else {
      items.push({ id: 'ord-btn-0', kind: 'btn-primary', tool: 'rect', x: padX + cw - 110, y: topY, w: 110, h: 32, rx: 8, text: '+ ДОБАВИТЬ', accent: true, cursorIndex: c(1), startMs: 60, durationMs: 260 })
    }

    // Ряд 1: 4 широкие KPI карточки
    const kpiY = topY + 44
    const kpiCount = isMobile ? 2 : 4
    const kpiW = Math.floor((cw - (kpiCount - 1) * 10) / kpiCount)
    ORDERS_KPIS.slice(0, kpiCount).forEach(([val, lbl], idx) => {
      items.push({
        id: `ord-kpi-${idx}`, kind: 'kpi', tool: idx === 0 ? 'rect' : 'dup', dupFromId: idx === 0 ? undefined : `ord-kpi-0`,
        x: padX + idx * (kpiW + 10), y: kpiY, w: kpiW, h: 68, rx: 10, text: lbl, subtext: val, accent: idx === 0,
        cursorIndex: c(idx), startMs: 140 + idx * 60, durationMs: 280,
      })
    })

    // Ряд 2: Фильтры
    const filtY = kpiY + 74
    const filtCount = isMobile ? 2 : Math.min(ORDERS_FILTERS.length, Math.max(6, Math.floor(cw / 160)))
    const filtW = Math.floor((cw - (filtCount - 1) * 8) / filtCount)
    ORDERS_FILTERS.slice(0, filtCount).forEach((lbl, idx) => {
      items.push({
        id: `ord-fld-${idx}`, kind: idx === 0 ? 'chip' : 'input', tool: idx === 0 ? 'rect' : 'dup', dupFromId: idx === 0 ? undefined : `ord-fld-0`,
        x: padX + idx * (filtW + 8), y: filtY, w: filtW, h: 32, rx: 7, text: lbl, accent: idx === 0,
        cursorIndex: c(idx + 1), startMs: 280 + idx * 50, durationMs: 240,
      })
    })

    // Ряд 3: 8 вкладок статусов
    const tabY = filtY + 38
    let tabX = padX
    const maxTabs = isMobile ? 3 : 8
    ORDERS_STATUS_TABS.slice(0, maxTabs).forEach((tab, idx) => {
      const tw = Math.min(150, 24 + tab.length * 7.5)
      if (tabX + tw > padX + cw) return
      items.push({
        id: `ord-tab-${idx}`, kind: 'chip', tool: idx === 0 ? 'rect' : 'dup', dupFromId: idx === 0 ? undefined : `ord-tab-${idx - 1}`,
        x: tabX, y: tabY, w: tw, h: 28, rx: 999, text: tab, accent: idx === 0,
        cursorIndex: c(idx), startMs: 420 + idx * 40, durationMs: 220,
      })
      tabX += tw + 6
    })

    // Ряд 4: Таблица закупок
    const tblY = tabY + 34
    const tblH = Math.max(180, height - tblY - 18)
    appendRowsTable(items, padX, tblY, cw, tblH, ORDERS_TABLE_COLS, ORDERS_TABLE_ROWS, c, 520, isMobile ? 4 : 7)
    return { kind: desc.kind, screenTitle: desc.title, items, columns: cols }
  }

  // 3. /feo-categories: Дерево слева + таблица справа
  if (clean.startsWith('/feo-categories')) {
    items.push({ id: 'fc-title', kind: 'heading', tool: 'type', x: padX, y: topY, w: 380, h: 32, text: desc.title, subtext: desc.subtitle, cursorIndex: c(0), startMs: 20, durationMs: 320 })
    items.push({ id: 'fc-chip', kind: 'chip', tool: 'rect', x: padX + 390, y: topY + 2, w: 160, h: 28, rx: 999, text: 'Субсидия: ФАДМ_2026', accent: true, cursorIndex: c(1), startMs: 80, durationMs: 220 })
    const treeW = isMobile ? cw : Math.round(cw * 0.32)
    const rightX = padX + treeW + 12
    const rightW = cw - treeW - 12
    const bodyTop = topY + 46
    const bodyH = Math.max(240, height - bodyTop - 24)
    items.push({ id: 'fc-tree-box', kind: 'card', tool: 'rect', x: padX, y: bodyTop, w: treeW, h: bodyH, rx: 10, text: 'Дерево статей ФЭО', cursorIndex: c(2), startMs: 140, durationMs: 300 })
    FEO_CATEGORIES_TREE.forEach(([nm, val], idx) => {
      const ry = bodyTop + 40 + idx * 38
      if (ry + 34 > bodyTop + bodyH) return
      items.push({ id: `fc-trow-${idx}`, kind: 'tree-row', tool: idx === 0 ? 'rect' : 'dup', dupFromId: idx === 0 ? undefined : 'fc-trow-0', x: padX + 8, y: ry, w: treeW - 16, h: 34, rx: 6, text: nm, rightText: val, cursorIndex: c(idx), startMs: 240 + idx * 60, durationMs: 240 })
    })
    if (!isMobile) {
      appendRowsTable(items, rightX, bodyTop, rightW, bodyH, cols, ORDERS_TABLE_ROWS, c, 380, 6)
    }
    return { kind: desc.kind, screenTitle: desc.title, items, columns: cols }
  }

  // 4. Другие настроенные маршруты (Договоры, Контрагенты, План, Заявки, Товары, Выписки)
  const cfg = ROUTE_CONFIGS[clean]
  if (cfg) {
    items.push({ id: 'cfg-title', kind: 'heading', tool: 'type', x: padX, y: topY, w: 360, h: 32, text: cfg.title, subtext: cfg.subtitle, cursorIndex: c(0), startMs: 20, durationMs: 300 })
    let curY = topY + 44
    if (cfg.kpis?.length) {
      const kc = isMobile ? 2 : Math.min(4, cfg.kpis.length)
      const kw = Math.floor((cw - (kc - 1) * 10) / kc)
      cfg.kpis.slice(0, kc).forEach(([v, l], i) => {
        items.push({ id: `ckpi-${i}`, kind: 'kpi', tool: i === 0 ? 'rect' : 'dup', dupFromId: i === 0 ? undefined : 'ckpi-0', x: padX + i * (kw + 10), y: curY, w: kw, h: 68, rx: 10, text: l, subtext: v, accent: i === 0, cursorIndex: c(i), startMs: 120 + i * 60, durationMs: 260 })
      })
      curY += 76
    }
    const remH = Math.max(200, height - curY - 20)
    appendRowsTable(items, padX, curY, cw, remH, cfg.columns, cfg.rows, c, 320, isMobile ? 4 : 7)
    return { kind: desc.kind, screenTitle: desc.title, items, columns: cfg.columns }
  }

  // 5. Форма / карточка закупки
  if (desc.kind === 'form') {
    const stages = ['1. Заявка', '2. ЭТП', '3. Договор', '4. Поставка', '5. Оплата']
    const sw = Math.floor((cw - (stages.length - 1) * 10) / stages.length)
    stages.forEach((st, idx) => {
      items.push({ id: `st-${idx}`, kind: 'step', tool: idx === 0 ? 'rect' : 'dup', dupFromId: idx === 0 ? undefined : 'st-0', x: padX + idx * (sw + 10), y: topY + 42, w: sw, h: 36, rx: 8, text: st, accent: idx <= 2, cursorIndex: c(idx), startMs: 80 + idx * 50, durationMs: 240 })
    })
    const cardTop = topY + 86
    const colW = isMobile ? cw : Math.floor((cw - 12) / 2)
    items.push({ id: 'fc1', kind: 'card', tool: 'rect', x: padX, y: cardTop, w: colW, h: 140, rx: 10, text: 'Параметры закупки и ФЭО', cursorIndex: c(1), startMs: 240, durationMs: 300 })
    if (!isMobile) items.push({ id: 'fc2', kind: 'card', tool: 'dup', dupFromId: 'fc1', x: padX + colW + 12, y: cardTop, w: colW, h: 140, rx: 10, text: 'Контрагент и договор', cursorIndex: c(2), startMs: 290, durationMs: 300 })
    appendRowsTable(items, padX, cardTop + 150, cw, Math.max(160, height - cardTop - 164), cols, ORDERS_TABLE_ROWS, c, 440, 5)
    return { kind: desc.kind, screenTitle: desc.title, items, columns: cols }
  }

  // 6. Дашборд / Аналитика
  if (desc.kind === 'dashboard') {
    const dkpis = [['Лимит субсидий', '277,0 млн ₽'], ['Законтрактовано', '46,1 млн ₽'], ['Поставлено', '25,7 млн ₽'], ['Оплачено', '18,9 млн ₽']]
    const kw = Math.floor((cw - (dkpis.length - 1) * 10) / (isMobile ? 2 : 4))
    dkpis.slice(0, isMobile ? 2 : 4).forEach(([lbl, val], i) => {
      items.push({ id: `dkpi-${i}`, kind: 'kpi', tool: i === 0 ? 'rect' : 'dup', dupFromId: i === 0 ? undefined : 'dkpi-0', x: padX + i * (kw + 10), y: topY + 44, w: kw, h: 72, rx: 10, text: lbl, subtext: val, accent: i === 0, cursorIndex: c(i), startMs: 80 + i * 60, durationMs: 280 })
    })
    const chY = topY + 124
    items.push({ id: 'd-chart', kind: 'chart', tool: 'pen', x: padX, y: chY, w: cw, h: Math.max(220, height - chY - 24), rx: 10, text: 'Динамика контрактации и оплат по месяцам', cursorIndex: c(4), startMs: 320, durationMs: 580 })
    return { kind: desc.kind, screenTitle: desc.title, items, columns: cols }
  }

  // 7. По умолчанию (задачи / загрузка)
  appendRowsTable(items, padX, topY + 44, cw, Math.max(220, height - topY - 60), cols, ORDERS_TABLE_ROWS, c, 160, isMobile ? 5 : 8)
  return { kind: desc.kind, screenTitle: desc.title, items, columns: cols }
}

function appendRowsTable(
  items: SwarmItem[], x: number, y: number, w: number, h: number,
  cols: string[], rows: TableRowData[], c: (i: number) => number, baseStartMs: number, maxRows: number,
) {
  items.push({ id: `tb-card-${baseStartMs}`, kind: 'card', tool: 'rect', x, y, w, h, rx: 10, cursorIndex: c(0), startMs: baseStartMs, durationMs: 320 })
  items.push({ id: `tb-head-${baseStartMs}`, kind: 'table-head', tool: 'type', x: x + 8, y: y + 8, w: w - 16, h: 32, rx: 6, cells: cols, cursorIndex: c(1), startMs: baseStartMs + 70, durationMs: 300 })
  items.push({ id: `tb-div-${baseStartMs}`, kind: 'divider', tool: 'pen', x: x + 8, y: y + 42, w: w - 16, h: 2, cursorIndex: c(2), startMs: baseStartMs + 140, durationMs: 220 })
  const rowH = 36
  const gap = 5
  const avail = Math.min(maxRows, Math.max(2, Math.floor((h - 52) / (rowH + gap))))
  for (let i = 0; i < avail; i++) {
    const sample = rows[i % rows.length]
    items.push({
      id: `tb-row-${baseStartMs}-${i}`, kind: 'table-row', tool: i === 0 ? 'rect' : 'dup', dupFromId: i === 0 ? undefined : `tb-row-${baseStartMs}-0`,
      x: x + 8, y: y + 48 + i * (rowH + gap), w: w - 16, h: rowH, rx: 6, cells: sample.cells, statusText: sample.status, statusColor: sample.color,
      cursorIndex: c(i + 3), startMs: baseStartMs + 200 + i * 75, durationMs: 260,
    })
  }
}
