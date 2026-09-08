// Dark-mode aware цвета для ApexCharts на дашборде.
// Перенесено без изменений из DashboardView.vue при разбиении на модули.
import { computed } from 'vue'
import { useTheme } from 'vuetify'

export function useDashboardChartTheme() {
  const theme = useTheme()
  const isDark = computed(() => theme.global.name.value === 'dark')
  const chartText = computed(() => isDark.value ? '#CBD5E1' : '#374151')
  const chartMuted = computed(() => isDark.value ? '#94A3B8' : '#6B7280')
  const chartGrid = computed(() => isDark.value ? 'rgba(255,255,255,0.08)' : '#E2E8F0')
  const chartTrack = computed(() => isDark.value ? '#334155' : '#E2E8F0')

  return { isDark, chartText, chartMuted, chartGrid, chartTrack }
}
