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
    navigator.serviceWorker.register('/sw.js').catch(() => {})
    const tryUpdate = () => {
      navigator.serviceWorker.getRegistration().then(reg => reg?.update()).catch(() => {})
    }
    setInterval(tryUpdate, 60 * 1000)
    window.addEventListener('focus', tryUpdate)
    // controllerchange стреляет и при ПЕРВОЙ установке SW (clientsClaim берёт
    // страницу под контроль) — это НЕ обновление. Реагируем только если у
    // страницы уже был контроллер на старте (= реально сменилась версия SW).
    // Иначе на iOS WebClip (Safari периодически сбрасывает SW-хранилище) диалог
    // «новая версия» + reload выскакивали при каждом запуске — вечное моргание.
    let hadController = !!navigator.serviceWorker.controller
    let _reloadOnControllerChange = false
    const RELOAD_TS_KEY = 'sw_auto_reload_ts'
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (!hadController) {
        hadController = true
        return
      }
      if (_reloadOnControllerChange) return
      _reloadOnControllerChange = true
      // Страховка от reload-цикла: не чаще одного авто-reload в 60 секунд.
      const last = Number(sessionStorage.getItem(RELOAD_TS_KEY) || 0)
      if (Date.now() - last < 60_000) return
      sessionStorage.setItem(RELOAD_TS_KEY, String(Date.now()))
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
}
