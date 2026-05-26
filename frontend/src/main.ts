import { createApp } from 'vue'
import App from './App.vue'
import vuetify from './plugins/vuetify'
import './styles/gala.css'
import { createPinia } from 'pinia'
import router from './router'
import VueApexCharts from 'vue3-apexcharts'
import { vResizableColumns } from './directives/resizable-columns'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)      // MUST be before app.use(router) so router guards can use the store
app.use(vuetify)
app.use(router)
app.use(VueApexCharts)

app.directive('resizable-columns', vResizableColumns)

app.mount('#app')

// Phase 26-DDD: PWA auto-update без необходимости Ctrl+F5.
// Workbox `registerType: 'autoUpdate' + skipWaiting + clientsClaim` гарантирует
// что новый SW активируется немедленно. НО для обнаружения нового SW нужен
// явный update() — без него браузер проверяет только при загрузке страницы.
// Делаем: poll каждые 60s + на focus вкладки. Когда controllerchange — reload
// (только если вкладка не активна, иначе теряются несохранённые изменения).
if ('serviceWorker' in navigator) {
  const tryUpdate = () => {
    navigator.serviceWorker.getRegistration().then(reg => reg?.update()).catch(() => {})
  }
  setInterval(tryUpdate, 60 * 1000)
  window.addEventListener('focus', tryUpdate)
  let _reloadOnControllerChange = false
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (_reloadOnControllerChange) return
    _reloadOnControllerChange = true
    // Тихий reload если вкладка не видна — пользователь ничего не заметит,
    // но при возврате во вкладку получит свежую версию.
    if (document.visibilityState === 'hidden') {
      window.location.reload()
    } else {
      // Активная вкладка — показываем баннер обновления через 5s (даём время сохранить).
      setTimeout(() => {
        if (confirm('Доступна новая версия приложения. Обновить сейчас?')) {
          window.location.reload()
        }
      }, 5000)
    }
  })
}
