<template>
  <v-app>
    <app-bar v-if="isAuthenticated" />
    <v-main>
      <router-view />
      <api-error-dialog />
    </v-main>
  </v-app>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import AppBar from './components/AppBar.vue'
import ApiErrorDialog from './components/ApiErrorDialog.vue'

const router = useRouter()
const isAuthenticated = computed(() => localStorage.getItem('auth_token') !== null)

// При старте приложения проверяем авторизацию
if (!isAuthenticated.value && router.currentRoute.value.path !== '/login') {
  router.push('/login')
}
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
</style>