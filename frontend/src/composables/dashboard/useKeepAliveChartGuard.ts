// Единый хелпер: заставляет <apexchart> внутри страницы, закэшированной
// через <keep-alive> в App.vue (CACHED_PAGE_NAMES — Dashboard, Subsidies и
// т.д., см. composables/pageCache.ts), по-настоящему размонтироваться при
// деактивации страницы вместо того, чтобы «зависать» живым внутри кэша.
//
// Причина (баг «TypeError: Cannot read properties of null (reading
// 'querySelectorAll')» при переходе Дашборд → Субсидии, воспроизведено
// 2026-10-20 через e2e):
// vue3-apexcharts создаёт реальный экземпляр ApexCharts в onMounted и
// уничтожает его (chart.destroy()) только в onBeforeUnmount. Когда
// родительская страница лежит в <keep-alive>, Vue при уходе со страницы НЕ
// вызывает onBeforeUnmount — только onDeactivated — так что экземпляр
// ApexCharts остаётся живым: его window-resize-листенер и ResizeObserver
// (ApexCharts registers их сам в core.js) продолжают быть подписаны, а
// реактивные watch(options)/watch(series) того же компонента ПРОДОЛЖАЮТ
// запускаться даже у деактивированного компонента (Vue останавливает только
// патч DOM, не сами watcher'ы) и планируют updateOptions()/updateSeries()
// через nextTick(). Когда такой отложенный вызов срабатывает уже после того,
// как пользователь ушёл с дашборда (например, во время взаимодействия с
// другой закэшированной страницей — раскрытие дерева ФЭО на «Субсидиях»,
// которое меняет layout и могло попутно дёрнуть ResizeObserver того же
// дашборда), ApexCharts обращается к собственным внутренним ссылкам на DOM
// графика, которые к этому моменту частично расчищены — и падает на
// querySelectorAll(null).
//
// Фикс одним общим механизмом: каждый компонент-виджет с <apexchart>
// вызывает этот хелпер и получает ref `chartAlive`; `<apexchart v-if=
// "chartAlive && …">` — при onDeactivated флаг уходит в false СИНХРОННО,
// Vue тут же (в рамках того же тика, до реальной деактивации) размонтирует
// <apexchart> по-настоящему через v-if, вызывая его onBeforeUnmount и честный
// chart.destroy() (снимает resize-листенер, отключает ResizeObserver,
// чистит window.Apex._chartInstances) — никаких «зомби»-экземпляров не
// остаётся. При onActivated флаг возвращается в true, и <apexchart>
// создаётся заново с нуля (как будто страница открыта впервые) — дешевле,
// чем держать мёртвую ссылку, которая рано или поздно уронит страницу.
import { ref, onActivated, onDeactivated, type Ref } from 'vue'

export function useKeepAliveChartGuard(): Ref<boolean> {
  const chartAlive = ref(true)

  onDeactivated(() => {
    chartAlive.value = false
  })
  onActivated(() => {
    chartAlive.value = true
  })

  return chartAlive
}
