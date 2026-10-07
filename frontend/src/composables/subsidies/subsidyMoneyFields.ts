// ПРАВИЛО №6: один источник истины для списка денежных полей карточек
// субсидии, которые приходят ГОТОВЫМИ с /dashboard/charts (committed_amounts.py,
// purchase_economy.py, subsidy_balance.py и т.д.) и просто переносятся в
// строку субсидии на фронте — здесь ничего не считаем.
//
// История: поля из этого набора уже дважды терялись при раскладке ответа
// /dashboard/charts (committed/redistributable_unplanned/not_committed_likely,
// затем balance_by_marks), потому что список переносимых полей был продублирован
// в двух местах SubsidiesView.vue и расходился. См.
// VAULT_for_LLM/Projects/VSKS_CRM/Lessons.md: feedback_single_source_of_truth.
//
// Добавлено 2026-10-06: contracted_not_ordered, over_plan_categories —
// см. задачу «Поля субсидии теряются при раскладке».
export function pickSubsidyMoneyFields(s: any) {
  return {
    committed: s.committed ?? null,
    committed_by_kind: s.committed_by_kind ?? null,
    planned_not_committed: s.planned_not_committed ?? null,
    planned_not_committed_by_kind: s.planned_not_committed_by_kind ?? null,
    redistributable: s.redistributable ?? null,
    redistributable_by_kind: s.redistributable_by_kind ?? null,
    redistributable_unplanned: s.redistributable_unplanned ?? null,
    // Задачи 2-3 (владелец, 04.10.2026): разбивка «в плане без договоров»
    // по need_level + остаток помесячного до конца года — готовые поля
    // /dashboard/charts, ничего не считаем (Правило №6).
    not_committed_likely: s.not_committed_likely ?? null,
    not_committed_nice: s.not_committed_nice ?? null,
    monthly_future_to_year_end: s.monthly_future_to_year_end ?? null,
    economy_total: s.economy_total ?? null,
    economy_no_planned_price_items: s.economy_no_planned_price_items ?? null,
    economy_unmeasured_by_reason: s.economy_unmeasured_by_reason ?? null,
    committed_missing_fact_items: s.committed_missing_fact_items ?? null,
    // «Остаток субсидии» (владелец, 06.10.2026) — готовые поля бэкенда,
    // фронт не считает (Правило №6, см. composables/subsidies/types.ts).
    balance_paid_marked: s.balance_paid_marked ?? null,
    balance_paid_confirmed: s.balance_paid_confirmed ?? null,
    balance_by_marks: s.balance_by_marks ?? null,
    balance_by_statement: s.balance_by_statement ?? null,
    // 2026-10-06: «Законтрактовано, не заказано» и перерасход по категориям.
    contracted_not_ordered: s.contracted_not_ordered ?? null,
    over_plan_categories: s.over_plan_categories ?? [],
    // feo_entered (владелец 07.10.2026, план .planning/quick/2026-10-07-dnr-
    // feo-cards/PLAN.md шаг 1) — см. docstring у поля в composables/subsidies/
    // types.ts. ?? true — старый бэк без этого поля продолжает считаться
    // «ФЭО введено» (прежнее поведение), не ломаем карточки задним числом.
    feo_entered: s.feo_entered ?? true,
  }
}
