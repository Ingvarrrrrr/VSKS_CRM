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
    // Переименовано 15.10.2026 (план abstract-noodling-pelican.md):
    // contracted_not_ordered → monthly_future_not_started («ещё уйдёт
    // помесячно до конца года»). Перерасход по категориям — не трогается.
    monthly_future_not_started: s.monthly_future_not_started ?? null,
    // Шаг 2 плана humble-stirring-emerson.md (23.10.2026) — 5-я строка
    // карточки «Можно перераспределить»: «задано на категорию, но не
    // расписано позициями» (готовое поле /dashboard/charts, ничего не
    // считаем). Без этой записи поле терялось бы точно так же, как
    // committed/balance_by_marks до него (см. докстринг модуля выше) —
    // найдено живой приёмкой: карточка на экране показывала Σ четырёх
    // строк МЕНЬШЕ итога ровно на эту сумму.
    manual_plan_gap: s.manual_plan_gap ?? null,
    over_plan_categories: s.over_plan_categories ?? [],
    // feo_entered (владелец 07.10.2026, план .planning/quick/2026-10-07-dnr-
    // feo-cards/PLAN.md шаг 1) — см. docstring у поля в composables/subsidies/
    // types.ts. ?? true — старый бэк без этого поля продолжает считаться
    // «ФЭО введено» (прежнее поведение), не ломаем карточки задним числом.
    feo_entered: s.feo_entered ?? true,
    // Жёсткий потолок субсидии (задача владельца 15.10.2026, карточка
    // «Запланировано») — готовые поля /dashboard/charts, ничего не считаем
    // (Правило №6). Без этой записи поля терялись бы так же, как
    // committed/balance_by_marks до них (см. докстринг модуля выше).
    plan_over_ceiling_amount: s.plan_over_ceiling_amount ?? 0,
    feo_ceiling: s.feo_ceiling ?? 0,
    // Плашка «Оплачено больше, чем поставлено» (владелец, 07.10.2026, прод
    // id=74 «ЛНР») — готовые поля /dashboard/charts (dashboard_charts.py::
    // subsidy_stats, см. backend app/services/paid_over_delivered.py),
    // ничего не считаем здесь (Правило №6). Без этой записи поле терялось бы
    // точно так же, как committed/balance_by_marks до него (см. докстринг
    // модуля выше) — SubsidyKpiCards.vue читает его напрямую с ctx.selectedSubsidy.
    paid_over_delivered: s.paid_over_delivered ?? 0,
    paid_over_delivered_prepayment: s.paid_over_delivered_prepayment ?? 0,
    paid_over_delivered_by_kind: s.paid_over_delivered_by_kind ?? null,
    // «Бюджет (ФЭО)»/«Запланировано» по видам (ПРАВИЛО №6, находка приёмки
    // 23.10.2026, SubsidyKpiCards.vue::rawSplitFor/splitRowsFor('free')) —
    // готовые поля /dashboard/charts (?type_split=true), ничего не считаем.
    // undefined (не ?? 0) — КОГДА НЕ ЗАПРОШЕНЫ (?type_split не включён) —
    // rawSplitFor проверяет именно `=== undefined`, чтобы отличить «не
    // загружено» от «загружено и равно нулю»; без этой записи поля терялись
    // бы точно так же, как committed/balance_by_marks до них (см. докстринг
    // модуля выше) — ровно это и произошло при первой попытке переноса
    // карточек на /dashboard/charts (загрузка по типам висела вечно и у
    // admin, т.к. поля уходили в s напрямую, а не в локальную строку).
    budget_goods: s.budget_goods,
    budget_services: s.budget_services,
    budget_payroll: s.budget_payroll,
    budget_unspecified: s.budget_unspecified,
    planned_goods: s.planned_goods,
    planned_services: s.planned_services,
    planned_payroll: s.planned_payroll,
    planned_unspecified: s.planned_unspecified,
  }
}
