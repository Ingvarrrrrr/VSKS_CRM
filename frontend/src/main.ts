import { createApp } from 'vue'
import App from './App.vue'
import vuetify from './plugins/vuetify'
import './styles/gala.css'
import { createPinia } from 'pinia'
import router from './router'
import { vResizableColumns } from './directives/resizable-columns'
import { vNumberOnly } from './directives/numberOnly'
import { initSwUpdate, initChunkLoadRecovery } from './composables/useSwUpdate'
import VDialogWithClose from './components/global/VDialogWithClose.vue'
import { migrateLegacyToken } from './composables/useLegacyTokenMigration'
import { initLastUserAction } from './utils/lastUserAction'

// Трекер «последнее действие пользователя» — для ApiErrorDialog.vue (строка
// «Произошло после: …» под JS-ошибкой). Один раз на всё приложение, до
// монтирования, чтобы не пропустить клики во время первой загрузки.
initLastUserAction()

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)      // MUST be before app.use(router) so router guards can use the store
app.use(vuetify)
// vue3-apexcharts больше не регистрируется глобально (весило в главном чанке
// для всех страниц, включая те без графиков) — компонент <apexchart> теперь
// подключается локально через defineAsyncComponent в каждом виджете, где
// используется (BudgetDrillDownDialog, dashboard/*Widget, WidgetRenderer,
// PlanView, RiskRadarView).

app.directive('resizable-columns', vResizableColumns)
// Владелец (29.10.2026): «Кол-во»/«Цена ед.» — только число, браузерный
// type="number" пропускал e/+/-/вставку текста (directives/numberOnly.ts).
app.directive('number-only', vNumberOnly)

// Глобально подменяем VDialog обёрткой с крестиком закрытия (см. комментарий
// в components/global/VDialogWithClose.vue — почему обёрткой компонента, а не
// MutationObserver + внутренним __vueParentComponent, который в prod-сборке
// отсутствует). Регистрация ПОСЛЕ app.use(vuetify), чтобы перекрыть штатный
// VDialog, который Vuetify зарегистрировал первым.
app.component('VDialog', VDialogWithClose)

// 2026-10-13: перенос JWT в httpOnly-cookie — пока не доиграна миграция
// старого localStorage('auth_token') (POST /api/auth/session-from-token),
// router-гварды не должны решать «не вошёл» по пустому gala_auth. app.use(router)
// и mount() — ПОСЛЕ await, иначе первая навигация гонится с migrateLegacyToken().
migrateLegacyToken().finally(() => {
  app.use(router)
  app.mount('#app')
})

// 2026-09-16: обработчик устаревших ленивых чанков нужен ВСЕГДА, даже на
// localhost — это не про SW-кэш, а про Vue Router `() => import(...)` не
// находящий на сервере файл по старому хэшу после того как исходники
// пересобрались у него под ногами (типичная dev-петля: правишь код, HMR не
// подхватил конкретный чанк, роутер тянет старую ссылку). Дешёвая защита,
// никак не пересекается с логикой ниже.
initChunkLoadRecovery()

// Phase 26-DDD: PWA auto-update без необходимости Ctrl+F5.
// Workbox `registerType: 'autoUpdate' + skipWaiting + clientsClaim` гарантирует
// что новый SW активируется немедленно. НО для обнаружения нового SW нужен
// явный update() — без него браузер проверяет только при загрузке страницы.
// initSwUpdate() (composables/useSwUpdate.ts) делает: poll каждые 60s + на
// focus вкладки, и показывает тост «Обновить» при смене контроллера.
const isLocalhost = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)

if ('serviceWorker' in navigator) {
  if (isLocalhost) {
    // Dev: убиваем любой SW + Cache Storage, чтобы localhost никогда не отдавал
    // протухшие ассеты (перезагрузка ПК не чистит SW — он на диске).
    navigator.serviceWorker.getRegistrations()
      .then(regs => regs.forEach(r => r.unregister()))
      .catch(() => {})
    if (window.caches) {
      caches.keys().then(keys => keys.forEach(k => caches.delete(k))).catch(() => {})
    }
  } else {
    // Прод: регистрируем SW вручную (injectRegister:false в vite.config),
    // чтобы на localhost он вообще не поднимался.
    initSwUpdate()
  }
}
