// Шаг доработки (владелец, 23.10.2026, субсидия ФАДМ 2026) — текст красной
// строки «план выше ФЭО» под карточкой «Запланировано» (SubsidyKpiCards.vue)
// лгал в сценарии «план ещё НЕ выше бюджета, но превысит, если согласовать
// всё, что ждёт решения»: plan_over_ceiling_amount (backend/app/services/
// subsidy_ceiling.py::feo_entered_ceiling_and_plan) считает план ВМЕСТЕ с
// несогласованным превышением (plan+over), а карточка «Запланировано»
// показывает план БЕЗ него (см. docstring display/_clamped в
// feo_plan_tree.py) — до этой правки фронт видел несовпадение чисел и писал
// «уменьшите план», хотя план карточки ещё не превысил бюджет.
//
// Три случая (ПРАВИЛО №6 — одна чистая функция, вызывается из ОДНОГО места
// в SubsidyKpiCards.vue, числа для неё берутся из уже существующих
// источников — planOverCeilingAmount/ceilingOverMatchesCards остаются
// готовыми полями бэкенда, pendingTotal — тот же usePendingExcessTotal.ts,
// что и у PendingExcessNote.vue, не вторая формула):
//   а) план карточки + «на согласовании» − бюджет ≈ plan_over_ceiling_amount
//      (±0.01), И план карточки САМ по себе ещё не выше бюджета — предупреждение
//      о БУДУЩЕМ превышении, если согласовать всё разом.
//   б) план карточки уже выше бюджета (ceilingOverMatchesCards) — «уменьшите план».
//   в) иначе — расхождение из-за статей без введённого ФЭО (не входят в
//      сравнение) — прежний текст «в статьях с ФЭО план выше».
export interface PlanCeilingNoteParams {
  planOverCeilingAmount: number
  planCardValue: number
  budgetCardValue: number
  pendingTotal: number
  ceilingOverMatchesCards: boolean
  formatCurrency: (amount: number) => string
}

export type PlanCeilingNoteCase = 'pending_would_exceed' | 'already_over' | 'excess_feo_only'

export interface PlanCeilingNote {
  case: PlanCeilingNoteCase
  text: string
}

export function planCeilingNote(params: PlanCeilingNoteParams): PlanCeilingNote {
  const { planOverCeilingAmount, planCardValue, budgetCardValue, pendingTotal, ceilingOverMatchesCards, formatCurrency } = params
  const amountStr = formatCurrency(planOverCeilingAmount)
  const planAlreadyOverBudget = planCardValue - budgetCardValue > 0.005
  const matchesPlanPlusPending = Math.abs(planOverCeilingAmount - (planCardValue + pendingTotal - budgetCardValue)) <= 0.01

  if (!planAlreadyOverBudget && matchesPlanPlusPending) {
    return {
      case: 'pending_would_exceed',
      text: `если согласовать всё, что на согласовании, план превысит бюджет на ${amountStr}`,
    }
  }
  if (ceilingOverMatchesCards) {
    return { case: 'already_over', text: `план выше бюджета на ${amountStr} — уменьшите план` }
  }
  return { case: 'excess_feo_only', text: `в статьях, где задан бюджет ФЭО, план выше на ${amountStr} — уменьшите план` }
}
