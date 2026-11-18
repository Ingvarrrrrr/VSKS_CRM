<template>
  <v-app>
    <v-progress-linear
      v-if="apiLoading"
      indeterminate
      color="primary"
      height="3"
      style="position:fixed;top:0;left:0;right:0;z-index:99999"
    />
    <app-bar v-if="showAppBar" />
    <v-main>
      <router-view v-slot="{ Component, route }">
        <!--
          NO `mode="out-in"` and explicit `:key="route.fullPath"`.

          Previously this was `mode="out-in"` + no key: Vue waited for the old
          view to finish its leave transition before mounting the new one, so
          any hang in the old view's unmount (classic case: ApexCharts tooltip
          Teleport still holding references after leaving /dashboard/radar)
          froze the transition in the "out" phase and the new view never
          mounted — user sees an empty main area while sidebar/app bar remain.

          The key forces Vue to treat each route as a fresh component instance
          (no accidental re-use of state across routes), and the default
          transition mode lets enter/leave run in parallel so the new view
          becomes visible even if the old one is slow to tear down.

          keep-alive (2026-10-13, план «мгновенный возврат на главные
          страницы»): CACHED_PAGE_NAMES (composables/pageCache.ts) — пять
          «главных» страниц (Сводная/Субсидии/Закупки/Заявки/Мои задачи) не
          размонтируются при уходе, а деактивируются — повторный заход
          показывает прежний DOM мгновенно, без нового запроса к серверу;
          каждая страница сама тихо обновляет свои данные в onActivated (см.
          composables/usePageCache.ts и useSubsidiesPageCache.ts). Остальные
          страницы (формы, карточки — например CreateOrderView) в include не
          входят и продолжают монтироваться с нуля каждый раз, как раньше.
          :key="route.fullPath" на <component> ниже остаётся — он не мешает
          keep-alive: Vue матчит кэш по имени компонента, а не по этому ключу,
          ключ только гарантирует, что смена ПАРАМЕТРОВ route у ОДНОЙ и той же
          некэшируемой страницы (например ?sid=) всё равно пересоздаёт её.
          cacheScopeKey на самом <keep-alive> — иначе уровень: смена
          пользователя (logout/login) или организации должна стереть ВЕСЬ
          кэш целиком (оставшиеся экземпляры могли принадлежать другому
          пользователю/org) — другой cacheScopeKey заставляет Vue пересоздать
          сам <keep-alive> с нуля, не заботясь про include/exclude.
        -->
        <transition name="page">
          <keep-alive :include="CACHED_PAGE_NAMES" :max="CACHED_PAGE_MAX" :key="cacheScopeKey">
            <component :is="Component" :key="route.fullPath" />
          </keep-alive>
        </transition>
      </router-view>
    </v-main>
    <api-error-dialog />
    <!-- Global chat FAB -->
    <v-btn
      v-if="isAuthenticated && route.path !== '/chat' && route.path !== '/consent-required'"
      icon
      style="position: fixed; bottom: var(--gala-fab-bottom-base); right: var(--gala-fab-right); z-index: var(--gala-fab-zindex)"
      color="primary"
      size="default"
      :to="'/chat'"
      elevation="6"
    >
      <v-badge
        v-if="totalUnread > 0"
        :content="totalUnread > 99 ? '99+' : totalUnread"
        color="error"
        floating
      >
        <v-icon icon="mdi-chat" />
      </v-badge>
      <v-icon v-else icon="mdi-chat" />
    </v-btn>
    <toast-container />
    <install-pwa-banner />
    <funding-sources-dialog />
    <!-- Cookie-баннер смонтирован ОДИН раз глобально (152-ФЗ) — раньше жил
         отдельно в LandingView/RegisterView и не показывался ни на /login,
         ни внутри приложения. См. CookieBanner.vue про z-index относительно
         install-баннера выше. -->
    <cookie-banner />
    <play-while-waiting />
    <swarm-rebuild-overlay />
  </v-app>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTheme } from 'vuetify'
import AppBar from './components/AppBar.vue'
import ApiErrorDialog from './components/ApiErrorDialog.vue'
import { initTableResize } from './composables/useTableResize'
import { totalUnread } from './composables/useChat'
import ToastContainer from './components/ToastContainer.vue'
import InstallPwaBanner from './components/InstallPwaBanner.vue'
// «Где взять деньги» (план .planning/quick/2026-10-05-funding-sources/PLAN.md)
// — смонтирован один раз глобально, как ToastContainer/ApiErrorDialog, потому
// что открывается из нескольких несвязанных страниц (дерево ФЭО, форма
// закупки, панель подтверждений оплаты) через module-level singleton
// useFundingSources.ts (Правило №6).
import FundingSourcesDialog from './components/subsidies/FundingSourcesDialog.vue'
import CookieBanner from './components/legal/CookieBanner.vue'
import PlayWhileWaiting from './components/games/PlayWhileWaiting.vue'
import SwarmRebuildOverlay from './components/swarm/SwarmRebuildOverlay.vue'
import { useAuthStore } from './stores/auth'
import { CACHED_PAGE_NAMES, CACHED_PAGE_MAX } from './composables/pageCache'
import { isLoggedIn, setLoggedIn, clearLoggedIn } from './composables/useAuthFlag'
import { setSwarmBooting } from './composables/useLongWait'

const route = useRoute()
const router = useRouter()
const theme = useTheme()
const authStore = useAuthStore()

const apiLoading = ref(false)
function onApiLoading(e: Event) {
  const count = (e as CustomEvent).detail?.count ?? 0
  apiLoading.value = count > 0
}

// 152-ФЗ: /consent-required тоже скрывает AppBar — страница гейта согласия
// обязана быть «голой», как /login (та же переменная/механизм, не второй):
// AppBar.vue onMounted сам запускает чат/бейджи/геолокацию/счётчики/выбор
// организаций — пока AppBar не смонтирован, ничего из этого не стартует.
const PUBLIC_ROUTES = ['/', '/login', '/register', '/verify-email', '/reset-password', '/consent-required']

const isAuthenticated = computed(() => isLoggedIn())
// Phase 30 PR4: /m/* routes используют собственный MobileLayout с bottom-tab-bar —
// desktop AppBar не показывать
const showAppBar = computed(() =>
  isAuthenticated.value
  && !PUBLIC_ROUTES.includes(route.path)
  && !route.path.startsWith('/m/')
)

// keep-alive cache scope (2026-10-13): id пользователя + активная
// организация, из localStorage (та же пара ключей, что уже читает
// authStore.loadPermissions выше). Смена ключа заставляет <keep-alive>
// пересоздаться целиком — весь кэш пяти главных страниц сбрасывается, чтобы
// следующий пользователь (или та же учётка после смены организации) не
// увидел чужой/устаревший экран на миг до фонового обновления.
// localStorage не реактивен сам по себе — значение пересчитывается при
// каждой навигации (route.fullPath как зависимость), а logout (router.push
// '/login') и switchOrgSingle (window.location.reload()) — оба пути, которыми
// меняются user_id/active_org_id, — проходят через навигацию/полный reload,
// так что пересчёт успевает случиться до того, как закэшированная страница
// снова станет видимой.
const cacheScopeKey = computed(() => {
  void route.fullPath
  const userId = localStorage.getItem('user_id') || ''
  const orgId = localStorage.getItem('active_org_id') || localStorage.getItem('user_org_id') || ''
  return `${userId}:${orgId}`
})

// Restore theme preference + init global table resize
onMounted(async () => {
  window.addEventListener('api-loading', onApiLoading)
  const saved = localStorage.getItem('theme')
  if (saved && (saved === 'dark' || saved === 'light')) {
    theme.global.name.value = saved
  }
  initTableResize()

  try {
    await (async () => {
      // Refresh role/profile from server on every app load. Авторизация — через
      // httpOnly-cookie gala_session (браузер шлёт сам, same-origin), признак
      // «есть смысл спрашивать» — только useAuthFlag (сам токен фронту не виден).
      if (isLoggedIn()) {
        try {
          const res = await fetch('/api/auth/me')
          if (res.ok) {
            const user = await res.json()
            setLoggedIn()
            localStorage.setItem('user_role', user.role || '')
            if (user.full_name) localStorage.setItem('user_name', user.full_name)
            if (user.id) localStorage.setItem('user_id', String(user.id))
            localStorage.setItem('can_publish', user.can_publish ? 'true' : 'false')
            localStorage.setItem('can_merge_purchases', user.can_merge_purchases ? 'true' : 'false')
          } else if (res.status === 401) {
            clearLoggedIn()
            localStorage.removeItem('user_role')
            localStorage.removeItem('user_name')
            window.location.href = '/'
          }
        } catch {}

        await router.isReady()
        if (route.path !== '/consent-required') {
          try {
            await authStore.loadPermissions(localStorage.getItem('active_org_id') || localStorage.getItem('user_org_id'))
          } catch (e) {
            console.error('[app] loadPermissions failed on mount, fail-open', e)
            authStore.loaded = true
          }
        }
      } else {
        await router.isReady()
      }
    })()
  } finally {
    setSwarmBooting(false)
    try { (window as any).__galaStopBootSwarm?.() } catch {}
  }
})

onUnmounted(() => {
  window.removeEventListener('api-loading', onApiLoading)
})
</script>

<style>
/* Высота статус-бара iOS вынесена в переменную: в десктопном браузере env() всегда
   0 и проверить вёрстку под нотч нельзя — с переменной её можно подставить в тесте. */
:root {
  --gala-safe-top: env(safe-area-inset-top, 0px);
}

/* Стек плавающих кнопок (чат + «+» создания заявки, WishesView.vue) —
   владелец (чек-лист С16, 2026-10-14): «+» был крупнее кнопки мессенджера и
   стоял не в одну колонку с ней. Единый источник геометрии (ПРАВИЛО №6):
   обе кнопки читают эти переменные, а не свои хардкод-числа — чат остаётся
   на месте (--gala-fab-bottom-base не менялась на desktop: было inline
   "bottom:90px"), «+» вычисляется от той же базы минус свой размер и зазор
   (90 - 48 - 12 = 30px), так что смена размера/отступа чата автоматически
   сдвигает «+». --gala-fab-size: 48px — реальная высота v-btn icon
   size="default" в Vuetify 3 (замерено в браузере, не 40px по наивному
   предположению). На mobile база поднята над нижним меню (AppBar.vue
   .mobile-bottom-nav, 60px + safe-area): +72px даёт «+» зазор 12px над
   таб-баром (нижней кнопке стека) — проверено замером getBoundingClientRect
   на 390×844, см. e2e/zz-wishes-new-fab-c16.spec.ts.
   z-index 1060 > cookie-banner (1050, CookieBanner.vue) — до выбора cookie
   баннер лежит поверх нижней части экрана и на 1440×900 реально закрывает
   нижнюю кнопку стека («+», z-index был 999 < 1050) — замечено при приёмке
   чек-листа С16. Выше install-баннера (1100) не поднимаем специально: тот
   и так закрывает cookie-баннер целиком, а FAB-стек с install-баннером
   не пересекается по месту. */
:root {
  --gala-fab-right: 24px;
  --gala-fab-size: 48px;
  --gala-fab-gap: 12px;
  --gala-fab-bottom-base: 90px;
  --gala-fab-zindex: 1060;
}
@media (max-width: 959.98px) {
  :root {
    --gala-fab-bottom-base: calc(60px + env(safe-area-inset-bottom, 0px) + 72px);
  }
}

/* iOS safe-area: к layout-отступу под app-bar добавляем высоту статус-бара,
   чтобы верх контента (KPI дашборда и пр.) не прятался под часами. env()=0 на
   desktop/Android → сводится к обычному var(--v-layout-top). */
.v-main {
  padding-top: calc(var(--v-layout-top) + var(--gala-safe-top)) !important;
}

/* iOS standalone (black-translucent + viewport-fit=cover): статус-бар рисуется
   поверх страницы. Опускаем шапку на высоту safe-area, её фон закрывает зону
   часов/нотча. Правила ДОЛЖНЫ быть глобальными: в AppBar.vue v-app-bar —
   корневой элемент, и scoped `:deep()` до него не достаёт.
   env()=0 на desktop/Android → сводится к обычным 48px. */
.v-application .v-app-bar.v-toolbar {
  height: calc(48px + var(--gala-safe-top)) !important;
  padding-top: var(--gala-safe-top) !important;
}
.v-application .v-app-bar .v-toolbar__content {
  height: 48px !important;
}
.v-application .v-app-bar {
  backdrop-filter: blur(8px) saturate(1.2);
  -webkit-backdrop-filter: blur(8px) saturate(1.2);
}

/* Mobile bottom-nav (AppBar.vue) фиксирован внизу — освобождаем место под него */
@media (max-width: 959px) {
  .v-main {
    padding-bottom: calc(60px + env(safe-area-inset-bottom)) !important;
  }
  /* Без этого широкая таблица/тулбар раздвигают layout-viewport (innerWidth>375),
     ломают fixed bottom-nav и показывают desktop-элементы (d-sm-flex).
     Полностраничный горизонтальный скролл = «сайт, а не приложение». */
  html, body, .v-application, .v-main {
    overflow-x: hidden !important;
    max-width: 100vw;
  }
  /* широкий контент (таблицы) скроллится внутри своего контейнера, не страницы */
  .v-main .v-table__wrapper,
  .v-main .v-data-table__wrapper {
    overflow-x: auto !important;
  }
}

</style>
