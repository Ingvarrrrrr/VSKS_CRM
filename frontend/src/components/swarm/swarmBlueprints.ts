// Высокоплотные чертёжные макеты GALA (42–56 элементов на экран: заголовки,
// кнопки, фильтры-чипы, строки дерева ФЭО, KPI-карточки, разделители пером,
// табличные строки с ячейками и статусами, графики) для Swarm Rebuild v2.

import { SWARM_AGENTS, type SwarmBlueprint, type SwarmBlueprintKind, type SwarmItem } from './swarmTypes'

export { SWARM_AGENTS } from './swarmTypes'
export type { SwarmAgent, SwarmBlueprint, SwarmBlueprintKind, SwarmItem } from './swarmTypes'

interface RouteDescriptor {
  kind: SwarmBlueprintKind
  title: string
  columns?: string[]
}

export function describeRouteForSwarm(path: string): RouteDescriptor {
  const clean = (path || '/').split('?')[0]

  if (clean.startsWith('/subsidies/') && clean.includes('/revisions')) {
    return { kind: 'form', title: 'Ревизия ФЭО', columns: ['Категория', 'Было', 'Стало', 'Δ ₽'] }
  }
  if (clean.startsWith('/subsidies')) {
    return { kind: 'subsidies', title: 'Субсидии и ФЭО', columns: ['Позиция ФЭО', 'План ₽', 'Договоры', 'Статус', 'Остаток ₽'] }
  }
  if (clean.startsWith('/feo-categories')) {
    return { kind: 'subsidies', title: 'Категории ФЭО', columns: ['Код', 'Наименование', 'Тип', 'Статус', 'Лимит ₽'] }
  }
  if (clean.startsWith('/plan')) {
    return { kind: 'subsidies', title: 'План-график закупок', columns: ['Позиция', 'Категория', 'Срок', 'Этап', 'Бюджет ₽'] }
  }
  if (/^\/orders\/[^/]+/.test(clean) || /^\/(service-notes|advance-reports)\/(create|[^/]+\/edit)/.test(clean)) {
    return { kind: 'form', title: 'Карточка закупки РЕЕ-2026-04884', columns: ['Наименование', 'Как в ТЗ', 'Как в договоре', 'Поставка', 'Сумма ₽'] }
  }
  if (/^\/fleet\/waybills\/[^/]+/.test(clean)) {
    return { kind: 'form', title: 'Путевой лист', columns: ['Маршрут', 'Пробег', 'Топливо', 'Водитель', 'Статус'] }
  }
  if (clean.startsWith('/orders')) {
    return { kind: 'registry', title: 'Реестр закупок', columns: ['Реестр №', 'Предмет закупки', 'Контрагент', 'Статус', 'Сумма ₽'] }
  }
  if (clean.startsWith('/wishes')) {
    return { kind: 'registry', title: 'Заявки на закупку', columns: ['Заявка', 'Позиции', 'Категория ФЭО', 'Этап', 'Сумма ₽'] }
  }
  if (clean.startsWith('/contracts')) {
    return { kind: 'registry', title: 'Реестр договоров', columns: ['№ договора', 'Контрагент', 'Предмет', 'Лимит ₽', 'Остаток ₽'] }
  }
  if (clean.startsWith('/contractors') || clean.startsWith('/suppliers')) {
    return { kind: 'registry', title: 'Контрагенты', columns: ['Наименование', 'ИНН', 'КПП', 'Договоры', 'Статус'] }
  }
  if (clean.startsWith('/payments')) {
    return { kind: 'registry', title: 'Выписки и платежи', columns: ['Дата', '№ п/п', 'Контрагент', 'Назначение', 'Сумма ₽'] }
  }
  if (clean.startsWith('/products')) {
    return { kind: 'registry', title: 'Каталог товаров', columns: ['Код', 'Наименование', 'Ед.', 'Цена ₽', 'Обновлено'] }
  }
  if (clean.startsWith('/commercial-requests')) {
    return { kind: 'registry', title: 'Запросы ТКП', columns: ['Процедура', 'Площадка', 'Заявки', 'Статус', 'НМЦ ₽'] }
  }
  if (clean.startsWith('/service-notes') || clean.startsWith('/advance-reports')) {
    return { kind: 'registry', title: 'Служебные документы', columns: ['Номер', 'Дата', 'Сотрудник', 'Статус', 'Сумма ₽'] }
  }
  if (clean === '/fleet' || clean === '/property/vehicles/dashboard') {
    return { kind: 'dashboard', title: 'Дашборд автопарка' }
  }
  if (clean.startsWith('/fleet') || clean.startsWith('/property')) {
    return { kind: 'registry', title: 'Автопарк и имущество', columns: ['Объект', 'Госномер', 'Филиал', 'Статус', 'Документы'] }
  }
  if (clean.startsWith('/dashboard/radar')) {
    return { kind: 'dashboard', title: 'Радар рисков' }
  }
  if (clean.startsWith('/dashboard') || clean.startsWith('/analytics') || clean.startsWith('/reports') || clean.startsWith('/dashboards')) {
    return { kind: 'dashboard', title: 'Сводная аналитика' }
  }
  if (clean.startsWith('/my-tasks') || clean.startsWith('/chat') || clean.startsWith('/staff-location')) {
    return { kind: 'tasks', title: clean.startsWith('/chat') ? 'Рабочий чат' : 'Мои задачи и контроль' }
  }
  if (clean.startsWith('/staff') || clean.startsWith('/directory') || clean.startsWith('/hierarchy') || clean.startsWith('/organizations') || clean.startsWith('/admin')) {
    return { kind: 'tasks', title: 'Структура и доступы' }
  }
  return { kind: 'boot', title: 'Рабочее пространство GALA' }
}

const REGISTRY_ROWS: Array<{ cells: string[]; status: string; color: string }> = [
  { cells: ['РЕЕ-2026-04884', 'Оборудование спасотряда ХРО', 'ООО «ТД ВОСТОК»', 'На подписании', '1 420 500 ₽'], status: 'Договор', color: '#2563eb' },
  { cells: ['РЕЕ-2026-04885', 'Светофильтры и оптика ЗРО', 'ООО «АВРОРА»', 'На ЭТП', '486 000 ₽'], status: 'Площадка', color: '#d97706' },
  { cells: ['РЕЕ-2026-04886', 'Спецодежда и СИЗ (комплект)', 'ООО «ТЕКСТИЛЬ М»', 'Поставлено', '2 180 000 ₽'], status: 'Поставка', color: '#0d9488' },
  { cells: ['РЕЕ-2026-04894', 'Предрейсовый медосмотр ДНР', 'ООО «ПРЕДРЕЙСОВЫЙ»', 'Оплачено', '119 000 ₽'], status: 'Оплачено', color: '#16a34a' },
  { cells: ['РЕЕ-2026-04901', 'Проживание участников слёта', 'ИП СОКОЛОВ А.В.', 'Согласование', '640 200 ₽'], status: 'Заявка', color: '#7c3aed' },
  { cells: ['РЕЕ-2026-04908', 'Питание добровольцев (этап 2)', 'ООО «КОМБИНАТ»', 'Договор', '915 000 ₽'], status: 'Договор', color: '#2563eb' },
  { cells: ['РЕЕ-2026-04912', 'Радиостанции цифровые VHF', 'АО «РАДИОТЕХ»', 'Оплачено', '1 750 000 ₽'], status: 'Оплачено', color: '#16a34a' },
  { cells: ['РЕЕ-2026-04919', 'ГСМ и ТО автотранспорта', 'ПАО «НК РОСНЕФТЬ»', 'Поставлено', '384 600 ₽'], status: 'Поставка', color: '#0d9488' },
]

const FEO_TREE_ROWS: Array<[string, string]> = [
  ['1. Оснащение формирований', '18 400 000 ₽'],
  ['1.1. Спецодежда и СИЗ', '6 250 000 ₽'],
  ['1.2. Спасательный инструмент', '8 920 000 ₽'],
  ['2. Проживание и питание', '9 600 000 ₽'],
  ['3. Транспорт и ГСМ', '5 140 000 ₽'],
  ['4. Связь, ИТ и навигация', '4 860 000 ₽'],
  ['5. Сборы и мероприятия ВСКС', '4 500 000 ₽'],
]

export function buildSwarmBlueprint(
  path: string,
  isMobile: boolean,
  booting: boolean,
  width = 1280,
  height = 760,
): SwarmBlueprint {
  const desc = booting && path === '/' ? { kind: 'boot' as const, title: 'Рабочее пространство GALA' } : describeRouteForSwarm(path)
  const cols = desc.columns || ['Реестр №', 'Наименование', 'Контрагент', 'Статус', 'Сумма ₽']
  const agentLimit = isMobile ? 3 : SWARM_AGENTS.length
  const c = (idx: number) => idx % agentLimit
  const padX = isMobile ? 16 : 36
  const topY = isMobile ? 30 : 34
  const cw = Math.max(300, width - padX * 2)
  const items: SwarmItem[] = []

  // 1. Шапка: заголовок (type), подзаголовок, кнопки действий (rect + dup)
  items.push({
    id: 'hdr-title', kind: 'heading', tool: 'type', x: padX, y: topY, w: isMobile ? cw * 0.65 : 360, h: 32,
    text: desc.title, subtext: 'GALA · Контур контроля субсидий', cursorIndex: c(0), startMs: 15, durationMs: 360,
  })
  if (!isMobile) {
    items.push({
      id: 'hdr-btn-0', kind: 'btn-primary', tool: 'rect', x: padX + cw - 154, y: topY, w: 154, h: 34, rx: 8,
      text: desc.kind === 'subsidies' ? '+ Импорт ФЭО' : '+ Новая запись', accent: true, cursorIndex: c(1), startMs: 55, durationMs: 320,
    })
    items.push({
      id: 'hdr-btn-1', kind: 'btn-outline', tool: 'dup', dupFromId: 'hdr-btn-0', x: padX + cw - 284, y: topY, w: 120, h: 34, rx: 8,
      text: 'Экспорт XLSX', cursorIndex: c(2), startMs: 110, durationMs: 280,
    })
    items.push({
      id: 'hdr-btn-2', kind: 'btn-outline', tool: 'dup', dupFromId: 'hdr-btn-1', x: padX + cw - 398, y: topY, w: 104, h: 34, rx: 8,
      text: 'Фильтры', cursorIndex: c(3), startMs: 165, durationMs: 280,
    })
  } else {
    items.push({
      id: 'hdr-btn-0', kind: 'btn-primary', tool: 'rect', x: padX + cw - 96, y: topY, w: 96, h: 32, rx: 8,
      text: '+ Создать', accent: true, cursorIndex: c(1), startMs: 70, durationMs: 300,
    })
  }

  // 2. Поисковая строка + чипы фильтров (первый rect, остальные dup ⌥-перетаскиванием)
  const filterY = topY + 48
  const searchW = isMobile ? cw : Math.min(340, cw * 0.32)
  items.push({
    id: 'tb-search', kind: 'input', tool: 'rect', x: padX, y: filterY, w: searchW, h: 34, rx: 8,
    text: 'Поиск по ИНН, номеру, предмету…', cursorIndex: c(4), startMs: 120, durationMs: 340,
  })
  const chipLabels = ['Все · 128', 'На согласовании · 14', 'На ЭТП · 19', 'Договор · 52', 'Оплачено · 43']
  let cx = isMobile ? padX : padX + searchW + 12
  const cy = isMobile ? filterY + 42 : filterY + 3
  chipLabels.slice(0, isMobile ? 3 : 5).forEach((lbl, idx) => {
    const chipW = Math.min(148, 44 + lbl.length * 6.5)
    if (cx + chipW > padX + cw) return
    items.push({
      id: `chip-${idx}`, kind: 'chip', tool: idx === 0 ? 'rect' : 'dup', dupFromId: idx === 0 ? undefined : `chip-${idx - 1}`,
      x: cx, y: cy, w: chipW, h: 28, rx: 999, text: lbl, accent: idx === 0,
      cursorIndex: c(idx + 1), startMs: 190 + idx * 70, durationMs: 260,
    })
    cx += chipW + 8
  })

  const bodyTop = (isMobile ? cy + 38 : filterY + 46)
  const bodyH = Math.max(260, height - bodyTop - 36)

  if (desc.kind === 'subsidies' && !isMobile) {
    const treeW = Math.round(cw * 0.31)
    const rightX = padX + treeW + 14
    const rightW = cw - treeW - 14
    items.push({
      id: 'sub-tree-card', kind: 'card', tool: 'rect', x: padX, y: bodyTop, w: treeW, h: bodyH, rx: 10,
      text: 'Дерево категорий ФЭО', cursorIndex: c(0), startMs: 240, durationMs: 400,
    })
    FEO_TREE_ROWS.forEach(([name, sum], idx) => {
      const ry = bodyTop + 42 + idx * 42
      if (ry + 36 > bodyTop + bodyH) return
      items.push({
        id: `tree-r-${idx}`, kind: 'tree-row', tool: idx === 0 ? 'rect' : 'dup', dupFromId: idx === 0 ? undefined : `tree-r-${idx - 1}`,
        x: padX + 10, y: ry, w: treeW - 20, h: 36, rx: 7, text: name, rightText: sum, accent: idx === 0,
        cursorIndex: c(idx + 1), startMs: 420 + idx * 95, durationMs: 300,
      })
    })
    const kpiW = Math.floor((rightW - 20) / 3)
    const kpis: Array<[string, string]> = [['Лимит ФЭО', '42 500 000 ₽'], ['Законтрактовано', '29 180 400 ₽'], ['Остаток', '13 319 600 ₽']]
    kpis.forEach(([t, v], idx) => {
      items.push({
        id: `kpi-${idx}`, kind: 'kpi', tool: idx === 0 ? 'rect' : 'dup', dupFromId: idx === 0 ? undefined : `kpi-${idx - 1}`,
        x: rightX + idx * (kpiW + 10), y: bodyTop, w: kpiW, h: 74, rx: 10, text: t, subtext: v, accent: idx === 0,
        cursorIndex: c(idx + 2), startMs: 320 + idx * 80, durationMs: 320,
      })
    })
    appendTableItems(items, rightX, bodyTop + 88, rightW, bodyH - 88, cols, c, 540, 7)
  } else if (desc.kind === 'form') {
    const stages = ['Заявка', 'Площадка ЭТП', 'Договор', 'Поставка', 'Оплата']
    const stepW = Math.floor((cw - (stages.length - 1) * 14) / stages.length)
    stages.forEach((st, idx) => {
      items.push({
        id: `stp-${idx}`, kind: 'step', tool: idx === 0 ? 'rect' : 'dup', dupFromId: idx === 0 ? undefined : `stp-${idx - 1}`,
        x: padX + idx * (stepW + 14), y: bodyTop, w: stepW, h: 38, rx: 8, text: `${idx + 1}. ${st}`, accent: idx <= 2,
        cursorIndex: c(idx), startMs: 260 + idx * 75, durationMs: 280,
      })
    })
    const cardTop = bodyTop + 50
    const colW = isMobile ? cw : Math.floor((cw - 14) / 2)
    items.push({ id: 'frm-c1', kind: 'card', tool: 'rect', x: padX, y: cardTop, w: colW, h: 158, rx: 10, text: 'Основные параметры и ФЭО', cursorIndex: c(1), startMs: 360, durationMs: 360 })
    if (!isMobile) {
      items.push({ id: 'frm-c2', kind: 'card', tool: 'dup', dupFromId: 'frm-c1', x: padX + colW + 14, y: cardTop, w: colW, h: 158, rx: 10, text: 'Контрагент, сроки и договор', cursorIndex: c(2), startMs: 430, durationMs: 360 })
    }
    const fields = ['Категория ФЭО: 1.2 Оснащение', 'Мероприятие: Сборы ЦФО', 'Контрагент: ООО «ТД ВОСТОК»', 'Договор № 1802-26 от 14.10.2026']
    fields.slice(0, isMobile ? 2 : 4).forEach((lbl, idx) => {
      const fx = isMobile ? padX + 12 : (idx < 2 ? padX + 12 : padX + colW + 26)
      const fy = cardTop + 44 + (idx % 2) * 48
      items.push({
        id: `fld-${idx}`, kind: 'input', tool: idx === 0 ? 'rect' : 'dup', dupFromId: idx === 0 ? undefined : `fld-${idx - 1}`,
        x: fx, y: fy, w: colW - 24, h: 36, rx: 7, text: lbl, cursorIndex: c(idx + 2), startMs: 560 + idx * 80, durationMs: 280,
      })
    })
    appendTableItems(items, padX, cardTop + 172, cw, Math.max(160, bodyH - 222), cols, c, 740, isMobile ? 4 : 5)
  } else if (desc.kind === 'dashboard') {
    const kpiCount = isMobile ? 2 : 4
    const kpiW = Math.floor((cw - (kpiCount - 1) * 12) / kpiCount)
    const dashKpis: Array<[string, string]> = [
      ['Лимит субсидий', '148,5 млн ₽'], ['Законтрактовано', '74,2%'], ['Поставлено', '92,4 млн ₽'], ['Экономия торгов', '3,84 млн ₽'],
    ]
    dashKpis.slice(0, kpiCount).forEach(([t, v], idx) => {
      items.push({
        id: `dkpi-${idx}`, kind: 'kpi', tool: idx === 0 ? 'rect' : 'dup', dupFromId: idx === 0 ? undefined : `dkpi-${idx - 1}`,
        x: padX + idx * (kpiW + 12), y: bodyTop, w: kpiW, h: 78, rx: 10, text: t, subtext: v, accent: idx === 0,
        cursorIndex: c(idx), startMs: 260 + idx * 75, durationMs: 320,
      })
    })
    const chY = bodyTop + 92
    const chH = Math.max(180, bodyH - 92)
    const mainChartW = isMobile ? cw : Math.round(cw * 0.61)
    items.push({
      id: 'd-chart', kind: 'chart', tool: 'pen', x: padX, y: chY, w: mainChartW, h: chH, rx: 10,
      text: 'Динамика контрактации и оплат по месяцам', cursorIndex: c(4), startMs: 480, durationMs: 650,
    })
    if (!isMobile) {
      const sideX = padX + mainChartW + 14
      const sideW = cw - mainChartW - 14
      items.push({ id: 'd-side', kind: 'card', tool: 'rect', x: sideX, y: chY, w: sideW, h: chH, rx: 10, text: 'Структура по статьям ФЭО', cursorIndex: c(5), startMs: 520, durationMs: 380 })
      FEO_TREE_ROWS.slice(0, 6).forEach(([name, sum], idx) => {
        const ry = chY + 44 + idx * 42
        if (ry + 36 > chY + chH) return
        items.push({
          id: `d-row-${idx}`, kind: 'tree-row', tool: idx === 0 ? 'rect' : 'dup', dupFromId: idx === 0 ? undefined : `d-row-${idx - 1}`,
          x: sideX + 10, y: ry, w: sideW - 20, h: 36, rx: 7, text: name, rightText: sum,
          cursorIndex: c(idx), startMs: 700 + idx * 90, durationMs: 280,
        })
      })
    }
  } else {
    // 'registry' | 'tasks' | 'boot'
    const kpiCount = isMobile ? 2 : 4
    const kpiW = Math.floor((cw - (kpiCount - 1) * 12) / kpiCount)
    const regKpis: Array<[string, string]> = [
      ['Всего в реестре', '128 поз.'], ['Законтрактовано', '29 180 400 ₽'], ['Поставлено', '21 405 000 ₽'], ['Оплачено', '18 940 200 ₽'],
    ]
    regKpis.slice(0, kpiCount).forEach(([t, v], idx) => {
      items.push({
        id: `rkpi-${idx}`, kind: 'kpi', tool: idx === 0 ? 'rect' : 'dup', dupFromId: idx === 0 ? undefined : `rkpi-${idx - 1}`,
        x: padX + idx * (kpiW + 12), y: bodyTop, w: kpiW, h: 74, rx: 10, text: t, subtext: v, accent: idx === 0,
        cursorIndex: c(idx), startMs: 260 + idx * 70, durationMs: 300,
      })
    })
    appendTableItems(items, padX, bodyTop + 88, cw, bodyH - 88, cols, c, 460, isMobile ? 5 : 8)
  }

  return { kind: desc.kind, screenTitle: desc.title, items, columns: cols }
}

function appendTableItems(
  items: SwarmItem[],
  x: number,
  y: number,
  w: number,
  h: number,
  cols: string[],
  c: (i: number) => number,
  baseStartMs: number,
  maxRows: number,
) {
  items.push({
    id: 'tbl-box', kind: 'card', tool: 'rect', x, y, w, h, rx: 10, cursorIndex: c(0), startMs: baseStartMs, durationMs: 360,
  })
  items.push({
    id: 'tbl-head', kind: 'table-head', tool: 'type', x: x + 10, y: y + 10, w: w - 20, h: 32, rx: 6,
    cells: cols, cursorIndex: c(1), startMs: baseStartMs + 90, durationMs: 360,
  })
  items.push({
    id: 'tbl-div', kind: 'divider', tool: 'pen', x: x + 10, y: y + 46, w: w - 20, h: 2,
    cursorIndex: c(2), startMs: baseStartMs + 180, durationMs: 260,
  })
  const rowH = 38
  const gap = 6
  const availRows = Math.min(maxRows, Math.max(2, Math.floor((h - 58) / (rowH + gap))))
  for (let i = 0; i < availRows; i++) {
    const sample = REGISTRY_ROWS[i % REGISTRY_ROWS.length]
    items.push({
      id: `tbl-row-${i}`, kind: 'table-row', tool: i === 0 ? 'rect' : 'dup', dupFromId: i === 0 ? undefined : `tbl-row-${i - 1}`,
      x: x + 10, y: y + 54 + i * (rowH + gap), w: w - 20, h: rowH, rx: 7,
      cells: sample.cells, statusText: sample.status, statusColor: sample.color,
      cursorIndex: c(i + 2), startMs: baseStartMs + 240 + i * 95, durationMs: 300,
    })
  }
}
