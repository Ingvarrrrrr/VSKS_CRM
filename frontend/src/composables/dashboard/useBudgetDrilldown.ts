// Диалог разбивки бюджета по субсидиям (BudgetDrillDownDialog) — открывается из
// Сводной таблицы («Аналитика») и из бар-графика Донат-виджета (breakdownBarOptions).
// Перенесено без изменений из DashboardView.vue при разбиении на модули.
import { ref } from 'vue'

export function useBudgetDrilldown() {
  const showBreakdownDialog = ref(false)
  const breakdownMetric = ref('budget')
  // Drill-down: scoped dialog subsidiaries
  const drillDialogSubsidies = ref<any[]>([])

  function openBreakdown(metric = 'budget') {
    breakdownMetric.value = metric
    showBreakdownDialog.value = true
  }

  return { showBreakdownDialog, breakdownMetric, drillDialogSubsidies, openBreakdown }
}
