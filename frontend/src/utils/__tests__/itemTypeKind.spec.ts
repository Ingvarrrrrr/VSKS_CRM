// Жалоба владельца 06.10.2026 («ХО (копия)»): карточка «Свободно» по типам
// показывала «превышение без типа 20 093 275,58» — ложная тревога, потому что
// «Бюджет (ФЭО)» почти всегда вводится на статьях целиком, без разбивки на
// товары/услуги (feo_goods/feo_services = 0), а «План» — из плановых позиций,
// у которых тип ЕСТЬ (plan_goods/plan_services > 0). Вычитание 0 − план давало
// фиктивное огромное превышение. freeByKindFromTypeTotals() — единственная
// формула «Свободно по типу» (см. её докстринг в ../itemTypeKind.ts), этот
// тест закрепляет три сценария из задания: бюджет по типу не введён вовсе,
// частично введён, и нормальный случай с реальным превышением.
import { describe, expect, it } from 'vitest'
import { freeByKindFromTypeTotals } from '../itemTypeKind'

describe('freeByKindFromTypeTotals', () => {
  it('без разбивки бюджета по типу вовсе (feo_goods=feo_services=0) — обе корзины "нет данных", не превышение', () => {
    const result = freeByKindFromTypeTotals({
      feo_goods: 0, feo_services: 0,
      plan_goods: 12_096_152.67, plan_services: 3_628_012.18,
    })
    expect(result.goods).toBeNull()
    expect(result.services).toBeNull()
  })

  it('бюджет по типу частично задан (только товары) — превышение считается ТОЛЬКО для товаров, услуги "нет данных"', () => {
    const result = freeByKindFromTypeTotals({
      feo_goods: 1_000_000, feo_services: 0,
      plan_goods: 1_200_000, plan_services: 500_000,
    })
    expect(result.goods).toBe(-200_000)
    expect(result.services).toBeNull()
  })

  it('бюджет по типу полностью задан — нормальный расчёт свободно/превышение по обеим корзинам', () => {
    const result = freeByKindFromTypeTotals({
      feo_goods: 1_000_000, feo_services: 500_000,
      plan_goods: 800_000, plan_services: 600_000,
    })
    expect(result.goods).toBe(200_000)   // свободно
    expect(result.services).toBe(-100_000) // превышение
  })

  it('округление шума плавающей точки (round передан явно) — 0 не превращается в мнимое превышение', () => {
    const result = freeByKindFromTypeTotals(
      { feo_goods: 1000, feo_services: 1000, plan_goods: 1000.0000000002, plan_services: 999.9999999998 },
      (v) => Math.round((v + Number.EPSILON) * 100) / 100,
    )
    expect(Math.abs(result.goods ?? NaN)).toBe(0)
    expect(Math.abs(result.services ?? NaN)).toBe(0)
  })
})
