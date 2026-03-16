<template>
  <v-app>
    <app-bar v-if="showAppBar" />
    <v-main>
      <router-view />
    </v-main>
    <api-error-dialog />
  </v-app>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useTheme } from 'vuetify'
import AppBar from './components/AppBar.vue'
import ApiErrorDialog from './components/ApiErrorDialog.vue'
import { initTableResize } from './composables/useTableResize'

const route = useRoute()
const theme = useTheme()

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
      } else if (res.status === 401) {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('user_role')
        localStorage.removeItem('user_name')
        window.location.href = '/'
      }
    } catch {}
  }
})
</script>

<style>
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
}

.v-theme--dark {
  --crm-bg: #0F172A;
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
</style>