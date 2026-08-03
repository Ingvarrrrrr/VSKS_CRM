import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import {
  kpiItemMatches,
  KPI_WORK_STATUSES,
  KPI_ORDERED_STATUSES,
  KPI_CONTRACTS_STATUSES,
  KPI_DELIVERED_STATUSES,
  type KpiMatchableItem,
} from '../kpiMetrics'

// Базовая «валидная» позиция — по умолчанию удовлетворяет большинству метрик,
// каждый тест переопределяет только те поля, которые проверяет.
function item(overrides: Partial<KpiMatchableItem> = {}): KpiMatchableItem {
  return {
    purchase_status: 'plan_schedule',
    purchase_contract_type: null,
    contract_id: null,
    contract_status: null,
    contract_type: null,
    ...overrides,
  }
}

describe('kpiItemMatches — поведенческие тесты по каждой item-метрике', () => {
  // ── plan_schedule ──────────────────────────────────────────────
  it('plan_schedule: включает любую позицию независимо от статуса закупки', () => {
    expect(kpiItemMatches('plan_schedule', item({ purchase_status: 'plan_schedule' }))).toBe(true)
    expect(kpiItemMatches('plan_schedule', item({ purchase_status: 'paid' }))).toBe(true)
    expect(kpiItemMatches('plan_schedule', item({ purchase_status: 'anything_unknown' }))).toBe(true)
  })

  // ── work ───────────────────────────────────────────────────────
  it('work: включает work_in_progress/contracted/ordered/delivered/paid, но НЕ plan_schedule', () => {
    for (const status of KPI_WORK_STATUSES) {
      expect(kpiItemMatches('work', item({ purchase_status: status }))).toBe(true)
    }
    expect(kpiItemMatches('work', item({ purchase_status: 'plan_schedule' }))).toBe(false)
  })

  // ── ordered ────────────────────────────────────────────────────
  it('ordered: НЕ включает статус "ordered" — известное расхождение с dashboard.py (do not fix)', () => {
    // dashboard.py:251 — total_ordered намеренно исключает status='ordered'
    expect(kpiItemMatches('ordered', item({ purchase_status: 'ordered', purchase_contract_type: 'single' }))).toBe(false)
  })

  it('ordered: требует непустой purchase_contract_type даже при подходящем статусе', () => {
    expect(kpiItemMatches('ordered', item({ purchase_status: 'contracted', purchase_contract_type: null }))).toBe(false)
    expect(kpiItemMatches('ordered', item({ purchase_status: 'contracted', purchase_contract_type: '' }))).toBe(false)
    expect(kpiItemMatches('ordered', item({ purchase_status: 'contracted', purchase_contract_type: 'single' }))).toBe(true)
  })

  it('ordered: покрывает ровно contracted/delivered/paid', () => {
    for (const status of KPI_ORDERED_STATUSES) {
      expect(kpiItemMatches('ordered', item({ purchase_status: status, purchase_contract_type: 'single' }))).toBe(true)
    }
    expect(kpiItemMatches('ordered', item({ purchase_status: 'work_in_progress', purchase_contract_type: 'single' }))).toBe(false)
  })

  // ── contracts ──────────────────────────────────────────────────
  it('contracts: single/framework_with_amount matches ЛЮБОЙ статус закупки, включая plan_schedule', () => {
    for (const contractType of ['single', 'framework_with_amount']) {
      expect(kpiItemMatches('contracts', item({
        purchase_status: 'plan_schedule',
        contract_id: 1,
        contract_status: 'active',
        contract_type: contractType,
      }))).toBe(true)
    }
  })

  it('contracts: framework_cumulative matches только contracted/ordered/delivered/paid', () => {
    for (const status of KPI_CONTRACTS_STATUSES) {
      expect(kpiItemMatches('contracts', item({
        purchase_status: status,
        contract_id: 1,
        contract_status: 'active',
        contract_type: 'framework_cumulative',
      }))).toBe(true)
    }
    expect(kpiItemMatches('contracts', item({
      purchase_status: 'plan_schedule',
      contract_id: 1,
      contract_status: 'active',
      contract_type: 'framework_cumulative',
    }))).toBe(false)
    expect(kpiItemMatches('contracts', item({
      purchase_status: 'work_in_progress',
      contract_id: 1,
      contract_status: 'active',
      contract_type: 'framework_cumulative',
    }))).toBe(false)
  })

  it('contracts: не matches при contract_status !== "active"', () => {
    expect(kpiItemMatches('contracts', item({
      purchase_status: 'contracted',
      contract_id: 1,
      contract_status: 'terminated',
      contract_type: 'single',
    }))).toBe(false)
    expect(kpiItemMatches('contracts', item({
      purchase_status: 'contracted',
      contract_id: 1,
      contract_status: null,
      contract_type: 'single',
    }))).toBe(false)
  })

  it('contracts: не matches при contract_id == null', () => {
    expect(kpiItemMatches('contracts', item({
      purchase_status: 'contracted',
      contract_id: null,
      contract_status: 'active',
      contract_type: 'single',
    }))).toBe(false)
  })

  // ── delivered / delivered_unpaid / paid ─────────────────────────
  it('delivered: покрывает delivered и paid', () => {
    for (const status of KPI_DELIVERED_STATUSES) {
      expect(kpiItemMatches('delivered', item({ purchase_status: status }))).toBe(true)
    }
    expect(kpiItemMatches('delivered', item({ purchase_status: 'contracted' }))).toBe(false)
  })

  it('delivered_unpaid: только статус delivered (paid уже оплачен)', () => {
    expect(kpiItemMatches('delivered_unpaid', item({ purchase_status: 'delivered' }))).toBe(true)
    expect(kpiItemMatches('delivered_unpaid', item({ purchase_status: 'paid' }))).toBe(false)
  })

  it('paid: только статус paid', () => {
    expect(kpiItemMatches('paid', item({ purchase_status: 'paid' }))).toBe(true)
    expect(kpiItemMatches('paid', item({ purchase_status: 'delivered' }))).toBe(false)
  })

  // ── budget / free (режим nodes — по позициям никогда не считаются) ──
  it('budget и free всегда возвращают false для item-based проверки (считаются по узлам дерева)', () => {
    const anyItem = item({ purchase_status: 'paid', contract_id: 1, contract_status: 'active', contract_type: 'single' })
    expect(kpiItemMatches('budget', anyItem)).toBe(false)
    expect(kpiItemMatches('free', anyItem)).toBe(false)
  })
})

// ── (б) Канарейка на паритет с backend/app/routers/dashboard.py ─────────────
// Если формула на бэке поменяется — этот тест должен упасть и явно сказать,
// что синхронизировать в kpiMetrics.ts. Сравнение — по нормализованным пробелам,
// не по форматированию (перенос строк в Python не должен ронять тест).

function normalize(s: string): string {
  return s.replace(/\s+/g, ' ').trim()
}

const repoRoot = path.resolve(fileURLToPath(import.meta.url), '../../../../../')
const dashboardPath = path.join(repoRoot, 'backend', 'app', 'routers', 'dashboard.py')
const purchaseBudgetPath = path.join(repoRoot, 'backend', 'app', 'routers', 'purchase_budget.py')

const dashboardSrc = normalize(readFileSync(dashboardPath, 'utf-8'))
const purchaseBudgetSrc = normalize(readFileSync(purchaseBudgetPath, 'utf-8'))

function expectContains(haystack: string, needle: string, hint: string) {
  const normalizedNeedle = normalize(needle)
  expect(
    haystack.includes(normalizedNeedle),
    `Не найдено в backend: "${needle}". ${hint} — формула в dashboard.py изменилась, синхронизируй kpiItemMatches в frontend/src/constants/kpiMetrics.ts`
  ).toBe(true)
}

describe('kpiItemMatches — канарейка на паритет с backend/app/routers/dashboard.py', () => {
  it('total_ordered: статусы contracted/delivered/paid + типы договора framework_cumulative/framework_with_amount/single', () => {
    // Окно между соседними .label(...) — блок total_ordered идёт сразу после total_plan_schedule
    const start = dashboardSrc.indexOf('label("total_plan_schedule")')
    const end = dashboardSrc.indexOf('label("total_ordered")')
    expect(start, 'не найден якорь total_plan_schedule в dashboard.py — переработай канарейку под новую структуру запроса').toBeGreaterThan(-1)
    expect(end, 'не найден label("total_ordered") в dashboard.py — total_ordered удалён или переименован, синхронизируй KPI_ORDERED_STATUSES/kpiItemMatches').toBeGreaterThan(start)
    const block = dashboardSrc.slice(start, end)

    expectContains(block, 'Purchase.status.in_(["contracted", "delivered", "paid"])',
      'total_ordered должен фильтровать по статусам contracted/delivered/paid')
    expectContains(block, 'Purchase.purchase_contract_type.in_(["framework_cumulative", "framework_with_amount"])',
      'total_ordered должен учитывать framework_cumulative/framework_with_amount отдельной веткой')
    expectContains(block, 'Purchase.purchase_contract_type == "single"',
      'total_ordered должен учитывать single отдельной веткой')
  })

  it('известное расхождение status=\'ordered\' задокументировано маркером "known discrepancy, do not fix"', () => {
    expectContains(dashboardSrc, 'known discrepancy, do not fix',
      'маркер-комментарий должен присутствовать рядом с total_ordered — если его убрали и «починили» ordered, kpiItemMatches тоже надо чинить')
  })

  it('contract_single_q: single/framework_with_amount, active, БЕЗ фильтра по Purchase.status', () => {
    const start = dashboardSrc.indexOf('contract_single_q = (')
    const end = dashboardSrc.indexOf('cs_rows = (await db.execute(contract_single_q))')
    expect(start, 'не найден contract_single_q в dashboard.py').toBeGreaterThan(-1)
    expect(end, 'не найден конец блока contract_single_q').toBeGreaterThan(start)
    const block = dashboardSrc.slice(start, end)

    expectContains(block, 'Contract.contract_type.in_(["single", "framework_with_amount"])',
      'contract_single_q должен фильтровать типы договора single/framework_with_amount')
    expectContains(block, 'Contract.status == "active"',
      'contract_single_q должен фильтровать только активные договоры')
    expect(
      block.includes('Purchase.status'),
      'contract_single_q НЕ должен фильтровать по Purchase.status (single/framework_with_amount считаются целиком по max_amount) — ' +
      'если фильтр появился, синхронизируй ветку contracts в kpiItemMatches'
    ).toBe(false)
  })

  it('contract_fc_q: framework_cumulative + Purchase.status in contracted/ordered/delivered/paid', () => {
    const start = dashboardSrc.indexOf('contract_fc_q = (')
    const end = dashboardSrc.indexOf('cfc_rows = (await db.execute(contract_fc_q))')
    expect(start, 'не найден contract_fc_q в dashboard.py').toBeGreaterThan(-1)
    expect(end, 'не найден конец блока contract_fc_q').toBeGreaterThan(start)
    const block = dashboardSrc.slice(start, end)

    expectContains(block, 'Contract.contract_type == "framework_cumulative"',
      'contract_fc_q должен фильтровать тип договора framework_cumulative')
    expectContains(block, 'Purchase.status.in_(["contracted", "ordered", "delivered", "paid"])',
      'contract_fc_q должен фильтровать статусы contracted/ordered/delivered/paid — это ровно KPI_CONTRACTS_STATUSES')
  })

  it('total_work = total_plan_schedule (work_in_progress) + w_ordered + w_delivered + w_paid', () => {
    expectContains(dashboardSrc, 'Purchase.status == "work_in_progress"',
      'total_plan_schedule должен считаться по статусу work_in_progress')
    expectContains(
      dashboardSrc,
      'float(row.total_plan_schedule) + float(row.w_ordered) + float(row.w_delivered) + float(row.w_paid)',
      'total_work должен складываться из work_in_progress + ordered/contracted + delivered + paid — это ровно KPI_WORK_STATUSES'
    )
  })

  it('PLANNED_STATUSES в purchase_budget.py — ровно 6 статусов, на которые рассчитан фронт', () => {
    const match = purchaseBudgetSrc.match(/PLANNED_STATUSES:\s*set\s*=\s*\{([^}]*)\}/)
    expect(
      match,
      'не найдено объявление PLANNED_STATUSES в purchase_budget.py — если его переименовали/убрали, сверь набор статусов вручную с frontend/src/constants/kpiMetrics.ts'
    ).not.toBeNull()
    const statuses = (match![1].match(/"([a-z_]+)"/g) ?? []).map(s => s.replace(/"/g, ''))
    expect(
      new Set(statuses),
      'PLANNED_STATUSES в purchase_budget.py изменился — сверь состав с frontend/src/constants/kpiMetrics.ts (KPI_WORK_STATUSES + plan_schedule)'
    ).toEqual(new Set(['plan_schedule', 'work_in_progress', 'contracted', 'ordered', 'delivered', 'paid']))
  })
})
