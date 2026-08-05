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
  it('ordered: включает статус "ordered" — правка 2026-08-04, формула на бэке починена', () => {
    // dashboard.py — total_ordered теперь фильтрует status.in_(["ordered", "delivered", "paid"])
    expect(kpiItemMatches('ordered', item({ purchase_status: 'ordered' }))).toBe(true)
  })

  it('ordered: НЕ требует purchase_contract_type — ветвление по типу договора убрано', () => {
    expect(kpiItemMatches('ordered', item({ purchase_status: 'ordered', purchase_contract_type: null }))).toBe(true)
    expect(kpiItemMatches('ordered', item({ purchase_status: 'ordered', purchase_contract_type: '' }))).toBe(true)
    expect(kpiItemMatches('ordered', item({ purchase_status: 'ordered', purchase_contract_type: 'single' }))).toBe(true)
  })

  it('ordered: покрывает ровно ordered/delivered/paid, но НЕ contracted (договор заключён — ещё не заказано)', () => {
    for (const status of KPI_ORDERED_STATUSES) {
      expect(kpiItemMatches('ordered', item({ purchase_status: status }))).toBe(true)
    }
    expect(kpiItemMatches('ordered', item({ purchase_status: 'contracted' }))).toBe(false)
    expect(kpiItemMatches('ordered', item({ purchase_status: 'work_in_progress' }))).toBe(false)
  })

  // ── contracts ──────────────────────────────────────────────────
  it('contracts: single/framework_with_amount matches ровно contracted/ordered/delivered/paid', () => {
    for (const contractType of ['single', 'framework_with_amount']) {
      for (const status of KPI_CONTRACTS_STATUSES) {
        expect(kpiItemMatches('contracts', item({
          purchase_status: status,
          contract_id: 1,
          contract_status: 'active',
          contract_type: contractType,
        }))).toBe(true)
      }
    }
  })

  it('contracts: не matches при plan_schedule даже для single/framework_with_amount', () => {
    for (const contractType of ['single', 'framework_with_amount']) {
      expect(kpiItemMatches('contracts', item({
        purchase_status: 'plan_schedule',
        contract_id: 1,
        contract_status: 'active',
        contract_type: contractType,
      }))).toBe(false)
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
  it('total_ordered: статусы ordered/delivered/paid, БЕЗ ветвления по purchase_contract_type, ежемесячные исключены', () => {
    // Окно между соседними .label(...) — блок total_ordered идёт сразу после total_plan_schedule
    const start = dashboardSrc.indexOf('label("total_plan_schedule")')
    const end = dashboardSrc.indexOf('label("total_ordered")')
    expect(start, 'не найден якорь total_plan_schedule в dashboard.py — переработай канарейку под новую структуру запроса').toBeGreaterThan(-1)
    expect(end, 'не найден label("total_ordered") в dashboard.py — total_ordered удалён или переименован, синхронизируй KPI_ORDERED_STATUSES/kpiItemMatches').toBeGreaterThan(start)
    const block = dashboardSrc.slice(start, end)

    expectContains(block, 'Purchase.status.in_(["ordered", "delivered", "paid"])',
      'total_ordered должен фильтровать по статусам ordered/delivered/paid (правка 2026-08-04 — раньше был "contracted" вместо "ordered")')
    expectContains(block, 'Purchase.is_monthly_payment.isnot(True)',
      'total_ordered должен исключать ежемесячные закупки (is_monthly_payment=true) — для них отдельное помесячное начисление (monthly_ordered_map)')
    expectContains(block, 'func.coalesce(Purchase.contract_price, Purchase.planned_total_price)',
      'total_ordered должен считать COALESCE(contract_price, planned_total_price) БЕЗ ветвления по purchase_contract_type — ' +
      'если ветвление по типу договора вернулось, синхронизируй kpiItemMatches("ordered") обратно на проверку purchase_contract_type')
    expect(
      block.includes('Purchase.purchase_contract_type'),
      'total_ordered НЕ должен ветвиться по purchase_contract_type (правка 2026-08-04 — раньше закупки с ' +
      'purchase_contract_type IS NULL тихо выпадали из суммы) — если ветвление вернулось, верни проверку в kpiItemMatches("ordered")'
    ).toBe(false)
  })

  it('маркер "known discrepancy, do not fix" у total_ordered убран — формула больше не намеренно сломана', () => {
    expect(
      dashboardSrc.includes('known discrepancy, do not fix'),
      'маркер устаревшего "не чини" комментария снова появился рядом с total_ordered — ' +
      'если формулу опять сломали намеренно, отмени это и почини как в правке 2026-08-04'
    ).toBe(false)
  })

  it('contract_single_q: single требует EXISTS закупки в «договорном» статусе, framework_with_amount — БЕЗУСЛОВНО при active', () => {
    const start = dashboardSrc.indexOf('_contracted_purchase_exists = (')
    const end = dashboardSrc.indexOf('cs_rows = (await db.execute(contract_single_q))')
    expect(start, 'не найден _contracted_purchase_exists в dashboard.py').toBeGreaterThan(-1)
    expect(end, 'не найден конец блока contract_single_q').toBeGreaterThan(start)
    const block = dashboardSrc.slice(start, end)

    expectContains(block, 'Contract.status == "active"',
      'contract_single_q должен фильтровать только активные договоры')
    expectContains(block, 'Purchase.status.in_(["contracted", "ordered", "delivered", "paid"])',
      'фильтр статуса закупки в EXISTS-подзапросе должен быть ровно KPI_CONTRACTS_STATUSES')
    expectContains(block, '_contracted_purchase_exists.exists()',
      'contract_single_q должен применять EXISTS-подзапрос для single (чтобы не размножить сумму при нескольких закупках на договоре)')
    // Правка 2026-08-04: EXISTS обязателен ТОЛЬКО для single. framework_with_amount считается
    // безусловно (рамочный договор с суммой подписывается заранее, закупки — потом) — раньше
    // EXISTS требовался для ОБОИХ типов, из-за чего рамочные договоры без единой закупки
    // ошибочно выпадали из виджета «Заключено договоров».
    expectContains(block, 'Contract.contract_type == "single", _contracted_purchase_exists.exists()',
      'single должен требовать EXISTS закупки — если это условие пропало, синхронизируй правило')
    expectContains(block, 'Contract.contract_type == "framework_with_amount"',
      'framework_with_amount должен фигурировать отдельной OR-веткой БЕЗ требования EXISTS закупки — ' +
      'если framework_with_amount снова требует EXISTS, отмени эту правку')
    expect(
      block.includes('Contract.contract_type.in_(["single", "framework_with_amount"])'),
      'contract_single_q больше НЕ должен применять единый .in_(["single","framework_with_amount"]) фильтр ' +
      'ко всем типам сразу — EXISTS для них теперь разный (см. правку 2026-08-04)'
    ).toBe(false)
  })

  it('widget «Заказано» согласован с total_ordered: строгий счётчик w_ordered_strict/so_amt_strict — ТОЛЬКО status=\'ordered\'', () => {
    // Правка 2026-08-04: раньше per-subsidy widget.ordered и глобальный widgets["ordered"] считали
    // contracted+ordered (через w_ordered/so_amt) — то есть иначе, чем total_ordered (ordered+delivered+paid).
    // w_ordered/so_amt НЕ убраны — они всё ещё нужны для total_work/widget.work, где contracted обязан входить.
    expectContains(dashboardSrc, 'label("w_ordered_strict")',
      'w_ordered_strict должен существовать — отдельный аккумулятор ТОЛЬКО статуса ordered для per-subsidy widget.ordered')
    expectContains(dashboardSrc, 'label("so_amt_strict")',
      'so_amt_strict должен существовать — отдельный аккумулятор ТОЛЬКО статуса ordered для глобального widgets["ordered"]')
    expectContains(dashboardSrc, 'float(row.w_ordered_strict) + float(row.w_delivered) + float(row.w_paid)',
      'per-subsidy widget.ordered.amount должен использовать w_ordered_strict, а не w_ordered (contracted+ordered)')
    expectContains(dashboardSrc, 'so_amt_strict + sd_amt + spd_amt',
      'глобальный widgets["ordered"].amount должен использовать so_amt_strict, а не so_amt (contracted+ordered)')
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
