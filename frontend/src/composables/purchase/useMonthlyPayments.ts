// Итог по ежемесячным платежам договора (Кол-во × Сумма платежа) — единственное
// вычисление в секции «Договор/Счёт», не относящееся к рамочным счетам/чекам.
// Вынесено из CreateOrderView.vue без изменения поведения; form передаётся тем
// же reactive-объектом, что и в родителе (второго источника истины нет).
import { computed } from 'vue'

export interface MonthlyPaymentsFormSlice {
  monthly_payment_count: number | null
  monthly_payment_amount: number | null
}

export function useMonthlyPayments(form: MonthlyPaymentsFormSlice) {
  const monthlyTotal = computed(() => {
    if (form.monthly_payment_count && form.monthly_payment_amount) {
      return form.monthly_payment_count * form.monthly_payment_amount
    }
    return null
  })

  // Заглушка-триггер реактивности на @update:model-value — monthlyTotal уже computed
  // и пересчитывается сам; оставлено ради того же обработчика в шаблоне (не менять
  // поведение — раньше это тоже было no-op).
  const calcMonthlyTotal = () => { /* reactivity trigger — monthlyTotal is computed */ }

  return { monthlyTotal, calcMonthlyTotal }
}
