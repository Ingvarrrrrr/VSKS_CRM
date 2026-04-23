import { createApp } from 'vue'
import App from './App.vue'
import vuetify from './plugins/vuetify'
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
