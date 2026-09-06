// «Конец месяца» quick-fill для service_deadline_date. Вынесено из
// CreateOrderView.vue без изменения поведения — form передаётся тем же
// reactive-объектом, что и в родителе (мутация form.service_deadline_date
// видна родителю напрямую, второго источника истины нет).
import { ref } from 'vue'
import { numOrNull } from '@/utils/numberFormat'

export function useEndOfMonthFill(form: Record<string, any>) {
  const endOfMonthMenu = ref(false)
  const _now = new Date()
  const endOfMonthYear = ref(_now.getFullYear())
  const endOfMonthMonth = ref(_now.getMonth() + 1)
  const endOfMonthMonthItems = [
    { value: 1, label: 'Январь' },
    { value: 2, label: 'Февраль' },
    { value: 3, label: 'Март' },
    { value: 4, label: 'Апрель' },
    { value: 5, label: 'Май' },
    { value: 6, label: 'Июнь' },
    { value: 7, label: 'Июль' },
    { value: 8, label: 'Август' },
    { value: 9, label: 'Сентябрь' },
    { value: 10, label: 'Октябрь' },
    { value: 11, label: 'Ноябрь' },
    { value: 12, label: 'Декабрь' },
  ]
  function applyEndOfMonth() {
    // endOfMonthYear — v-model.number; при очистке поля Vue кладёт '', что уронило бы
    // service_deadline_date в 'NaN-MM-DD'/'-MM-DD' (Optional[date] на бэке). numOrNull
    // с фолбэком на текущий год — поле год всегда нужно, пустым смысла нет (2026-09-04).
    const year = numOrNull(endOfMonthYear.value) ?? new Date().getFullYear()
    const lastDay = new Date(year, endOfMonthMonth.value, 0).getDate()
    const mm = String(endOfMonthMonth.value).padStart(2, '0')
    const dd = String(lastDay).padStart(2, '0')
    form.service_deadline_date = `${year}-${mm}-${dd}`
    endOfMonthMenu.value = false
  }

  return { endOfMonthMenu, endOfMonthYear, endOfMonthMonth, endOfMonthMonthItems, applyEndOfMonth }
}
