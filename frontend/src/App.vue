<template>
  <v-app>
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
        -->
        <transition name="page">
          <component :is="Component" :key="route.fullPath" />
        </transition>
      </router-view>
    </v-main>
    <api-error-dialog />
    <!-- Global chat FAB -->
    <v-btn
      v-if="isAuthenticated && route.path !== '/chat'"
      icon
      style="position: fixed; bottom: 90px; right: 24px; z-index: 999"
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
  </v-app>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useTheme } from 'vuetify'
import AppBar from './components/AppBar.vue'
import ApiErrorDialog from './components/ApiErrorDialog.vue'
import { initTableResize } from './composables/useTableResize'
import { totalUnread } from './composables/useChat'
import ToastContainer from './components/ToastContainer.vue'
import InstallPwaBanner from './components/InstallPwaBanner.vue'
import { useAuthStore } from './stores/auth'

const route = useRoute()
const theme = useTheme()
const authStore = useAuthStore()

const PUBLIC_ROUTES = ['/', '/login', '/register', '/verify-email', '/reset-password']

const isAuthenticated = computed(() => localStorage.getItem('auth_token') !== null)
const showAppBar = computed(() => isAuthenticated.value && !PUBLIC_ROUTES.includes(route.path))

// Restore theme preference + init global table resize
onMounted(async () => {
  const saved = localStorage.getItem('theme')
  if (saved && (saved === 'dark' || saved === 'light')) {
    theme.global.name.value = saved
  }
  initTableResize()

  // Refresh role/profile from server on every app load
  const token = localStorage.getItem('auth_token')
  if (token && token.startsWith('eyJ')) {
    try {
      const res = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        const user = await res.json()
        localStorage.setItem('user_role', user.role || '')
        if (user.full_name) localStorage.setItem('user_name', user.full_name)
        if (user.id) localStorage.setItem('user_id', String(user.id))
        localStorage.setItem('can_publish', user.can_publish ? 'true' : 'false')
      } else if (res.status === 401) {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('user_role')
        localStorage.removeItem('user_name')
        window.location.href = '/'
      }
    } catch {}

    // Load effective permissions from /users/me
    try {
      await authStore.loadPermissions(localStorage.getItem('active_org_id') || localStorage.getItem('user_org_id'))
    } catch (e) {
      console.error('[app] loadPermissions failed on mount, fail-open', e)
      authStore.loaded = true
    }
  }
})
</script>

<style>
/* ── v-data-table: table-layout fixed чтобы width на th/td реально применялся ── */
/* Без этого браузер применяет auto layout и игнорирует inline width когда content большой.
   ВАЖНО: только на desktop (≥960px). На mobile fixed-layout превращает текст в
   вертикальный «по букве на строку» из-за узких viewport-ширин и overflow-wrap.
   На mobile оставляем auto-layout — таблица сама подгоняет ширины под контент,
   при необходимости включается горизонтальный scroll. */
@media (min-width: 960px) {
  /* Phase 26-NNN/OOO: ограничиваем высоту scroll-обёртки таблицы → горизонтальный
     ползунок всегда виден в нижней части viewport, а не «спрятан» после
     последней строки + пагинации. 100vh - 280px оставляет место под header (64) +
     breadcrumbs/title (~70) + filters (~80) + pagination (~60).
     OOO: убран '>' (direct child) — в OrdersView/AdvanceReports v-data-table
     обёрнут в v-card, и Vuetify иногда вставляет промежуточные wrapper'ы между
     .v-data-table и .v-table__wrapper. Loose селектор покрывает оба случая. */
  @media (min-height: 600px) {
    .v-data-table .v-table__wrapper,
    .v-data-table-virtual .v-table__wrapper,
    .v-table .v-table__wrapper {
      max-height: calc(100vh - 280px) !important;
      overflow: auto !important;
    }
    /* Sticky header → при вертикальной прокрутке внутри таблицы заголовки колонок
       остаются вверху видимыми (иначе скролл по строкам теряет контекст). */
    .v-data-table thead th,
    .v-data-table-virtual thead th,
    .v-table thead th {
      position: sticky !important;
      top: 0 !important;
      z-index: 2 !important;
      background: rgb(var(--v-theme-surface)) !important;
    }
    /* v-card-обёртка над таблицей: убираем overflow:hidden чтобы sticky-эффекты
       и тени скроллбара не клиппировались скруглёнными углами карточки. */
    .v-card:has(> .v-data-table),
    .v-card:has(> .v-table) {
      overflow: visible !important;
    }
  }
  .v-data-table > .v-table__wrapper > table,
  .v-data-table-virtual > .v-table__wrapper > table {
    table-layout: fixed;
  }
  /* Phase 26-HHH: nuclear CSS с !important — пробивает любые scoped стили,
     Vuetify defaults, inline styles от useColumnConfig. Перенос ТОЛЬКО по
     пробелам/дефисам, целые слова остаются неразорваны.
     word-break: keep-all не позволяет ломать слово даже посреди слова
     (CJK тоже не ломаются). overflow-wrap: break-word — только по пробелу. */
  .v-data-table td,
  .v-data-table-virtual td {
    white-space: normal !important;
    word-break: normal !important;
    overflow-wrap: anywhere !important;
    text-overflow: clip !important;
    vertical-align: top !important;
  }
  .v-data-table th,
  .v-data-table-virtual th {
    white-space: normal !important;
    word-break: normal !important;
    overflow-wrap: anywhere !important;
    text-overflow: clip !important;
    vertical-align: middle !important;
    line-height: 1.2 !important;
  }
  /* Заголовки колонок через ColumnHeaderMenu: разрешаем 2 строки */
  .col-header-menu__title {
    white-space: normal !important;
    word-break: normal !important;
    overflow-wrap: anywhere !important;
    text-overflow: clip !important;
    display: -webkit-box !important;
    -webkit-line-clamp: 2 !important;
    -webkit-box-orient: vertical !important;
    overflow: hidden !important;
    line-height: 1.15 !important;
  }
}
/* На mobile отменяем agressive overflow-wrap (видимо унаследовано) и принудительный wrap
   чтобы текст не ломался посимвольно. Контент перепрыгивает horizontal-scroll. */
@media (max-width: 959.98px) {
  /* Глобально снимаем inline width/min-width/max-width на td и th — они задаются
     через useColumnConfig.cellProps и перебивают media query без !important.
     На mobile позволяем auto-layout таблицы. */
  .v-data-table td,
  .v-data-table th,
  .v-data-table-virtual td,
  .v-data-table-virtual th {
    width: auto !important;
    min-width: auto !important;
    max-width: 280px !important;
    /* word-break: keep-all не ломает слова по букве (ИНН/UUID останутся целыми);
       overflow-wrap: break-word ломает только по пробелам. */
    white-space: normal !important;
    word-break: normal !important;
    overflow-wrap: anywhere !important;
  }
  /* Header bars views (Реестр договоров + кнопки) — на mobile flex-wrap, чтобы
     заголовок и кнопки не наезжали друг на друга. */
  .v-container > .d-flex.justify-space-between {
    flex-wrap: wrap !important;
    gap: 8px;
  }
  /* Фильтр-карточки: внутренние v-text-field/v-autocomplete не должны быть уже 100% */
  .v-card .d-flex.flex-wrap > .v-input,
  .v-card .d-flex.flex-wrap > .v-autocomplete,
  .v-card .d-flex.flex-wrap > .v-text-field,
  .v-card .d-flex.flex-wrap > .v-select {
    min-width: 100% !important;
    max-width: 100% !important;
  }
}
/* ── Global: wrap long text in all Vuetify dropdowns / overlays ── */
.v-overlay__content .v-list-item-title,
.v-overlay__content .v-list-item__content .v-list-item-title {
  white-space: normal !important;
  word-break: break-word !important;
  line-height: 1.4 !important;
}
.v-overlay__content .v-list-item {
  min-height: unset !important;
}
/* Cap max-width of all select/autocomplete menus */
.v-overlay__content.v-select__content,
.v-overlay__content.v-autocomplete__content {
  max-width: min(600px, 90vw) !important;
}

/* ══════════════════════════════════════════════════════════════════
   DARK MODE global overrides
   Uses Vuetify's .v-theme--dark class to scope all fixes
   ══════════════════════════════════════════════════════════════════ */

/* ── CSS custom properties for theme-aware colors ── */
:root {
  --crm-bg: #ffffff;
  --crm-surface: #ffffff;
  --crm-surface-alt: #F9FAFB;
  --crm-surface-hover: #F3F4F6;
  --crm-border: rgba(0,0,0,0.07);
  --crm-border-strong: rgba(0,0,0,0.12);
  --crm-text: #111827;
  --crm-text-secondary: #374151;
  --crm-text-muted: #6B7280;
  --crm-text-faint: #9CA3AF;
  --crm-shadow: rgba(0,0,0,0.07);
  --crm-shadow-hover: rgba(0,0,0,0.12);
  --crm-input-bg: #F3F4F6;
  --crm-table-header: #F9FAFB;
  --crm-table-stripe: #F3F4F6;
  --crm-kpi-bg-blue: #EFF6FF;
  --crm-kpi-bg-sky: #E0F2FE;
  --crm-kpi-bg-green: #F0FDF4;
  --crm-kpi-bg-amber: #FFF7ED;
  --crm-tz-header: #F0F7FF;
  --crm-tz-footer: #F9FAFB;
  /* Semantic status colors */
  --color-planned:    #F59E0B;
  --color-contracted: #3B82F6;
  --color-paid:       #22C55E;
  --color-savings:    #8B5CF6;
  --color-profit:     #166534;
  --color-loss:       #DC2626;
}

.v-theme--dark {
  --crm-bg: #0F172A;
  /* Semantic status colors — lighter for dark backgrounds */
  --color-planned:    #FCD34D;
  --color-contracted: #60A5FA;
  --color-paid:       #4ADE80;
  --color-savings:    #C4B5FD;
  --color-profit:     #86EFAC;
  --color-loss:       #FCA5A5;
  --crm-surface: #1E293B;
  --crm-surface-alt: #1E293B;
  --crm-surface-hover: #334155;
  --crm-border: rgba(255,255,255,0.08);
  --crm-border-strong: rgba(255,255,255,0.15);
  --crm-text: #F1F5F9;
  --crm-text-secondary: #CBD5E1;
  --crm-text-muted: #94A3B8;
  --crm-text-faint: #64748B;
  --crm-shadow: rgba(0,0,0,0.3);
  --crm-shadow-hover: rgba(0,0,0,0.5);
  --crm-input-bg: #334155;
  --crm-table-header: #1E293B;
  --crm-table-stripe: #1E293B;
  --crm-kpi-bg-blue: rgba(59,130,246,0.15);
  --crm-kpi-bg-sky: rgba(2,132,199,0.15);
  --crm-kpi-bg-green: rgba(34,197,94,0.15);
  --crm-kpi-bg-amber: rgba(245,158,11,0.15);
  --crm-tz-header: rgba(59,130,246,0.1);
  --crm-tz-footer: #1E293B;
}

/* ── Dark mode: Vuetify component overrides ── */
.v-theme--dark .v-card {
  background-color: rgb(var(--v-theme-surface)) !important;
}
.v-theme--dark .v-data-table {
  background-color: rgb(var(--v-theme-surface)) !important;
}
.v-theme--dark .v-table {
  background-color: rgb(var(--v-theme-surface)) !important;
}
.v-theme--dark .bg-grey-lighten-4 {
  background-color: var(--crm-surface) !important;
}
.v-theme--dark .bg-grey-lighten-5 {
  background-color: var(--crm-surface) !important;
}
.v-theme--dark .v-text-field[bg-color="grey-lighten-4"],
.v-theme--dark .v-text-field .v-field--variant-outlined.bg-grey-lighten-4 {
  background-color: var(--crm-input-bg) !important;
}

/* ── Global column resize handles (v-resizable-columns directive) ── */
.vrc-handle {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 10px;
  cursor: col-resize;
  z-index: 2;
}
.vrc-handle::before {
  content: '';
  position: absolute;
  right: 3px;
  top: 20%;
  bottom: 20%;
  width: 2px;
  background: rgba(0, 0, 0, 0.18);
  border-radius: 2px;
  transition: all 0.15s ease;
}
.v-theme--dark .vrc-handle::before {
  background: rgba(255, 255, 255, 0.22);
}
.vrc-handle:hover::before,
.vrc-handle.vrc-active::before {
  right: 2px;
  top: 5%;
  bottom: 5%;
  width: 3px;
  background: rgb(59, 130, 246);
}

/* ── Page transitions ── */
.page-enter-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.page-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(12px);
}
.page-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>