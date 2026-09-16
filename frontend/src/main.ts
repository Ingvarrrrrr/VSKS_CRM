import { createApp } from 'vue'
import App from './App.vue'
import vuetify from './plugins/vuetify'
import './styles/gala.css'
import { createPinia } from 'pinia'
import router from './router'
import VueApexCharts from 'vue3-apexcharts'
import { vResizableColumns } from './directives/resizable-columns'
import { initSwUpdate, initChunkLoadRecovery } from './composables/useSwUpdate'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)      // MUST be before app.use(router) so router guards can use the store
app.use(vuetify)
app.use(router)
app.use(VueApexCharts)

app.directive('resizable-columns', vResizableColumns)

app.mount('#app')

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
