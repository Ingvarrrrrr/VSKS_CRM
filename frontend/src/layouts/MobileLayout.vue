<template>
  <v-app class="mobile-app">
    <!-- Top mini-header -->
    <v-app-bar
      class="mobile-header"
      flat
      height="56"
    >
      <div class="mobile-header__inner">
        <div class="mobile-header__logo">
          <v-icon icon="mdi-shield-car" color="primary" size="22" />
          <span class="mobile-header__brand">FleetOps</span>
        </div>
        <div class="mobile-header__title">{{ pageTitle }}</div>
        <div class="mobile-header__date">{{ todayStr }}</div>
      </div>
    </v-app-bar>

    <!-- Main content -->
    <v-main class="mobile-main">
      <div class="mobile-scroll-area">
        <router-view />
      </div>
    </v-main>

    <!-- Bottom tab bar -->
    <v-bottom-navigation
      v-model="activeTab"
      class="mobile-bottom-nav"
      color="primary"
      grow
      elevation="0"
    >
      <v-btn value="home" :to="{ name: 'm-driver-home' }" exact>
        <v-icon icon="mdi-car" />
        <span>Машина</span>
      </v-btn>

      <v-btn value="checklist" :to="{ name: 'm-driver-checklist' }" exact>
        <v-icon icon="mdi-clipboard-check" />
        <span>Чек-лист</span>
      </v-btn>

      <v-btn value="history" :to="{ name: 'm-driver-history' }" exact>
        <v-icon icon="mdi-history" />
        <span>История</span>
      </v-btn>

      <v-btn value="profile" :to="{ name: 'm-driver-profile' }" exact>
        <v-icon icon="mdi-account" />
        <span>Профиль</span>
      </v-btn>
    </v-bottom-navigation>
  </v-app>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { initStaffLocationTracking } from '@/composables/useStaffLocationTracking'

const route = useRoute()

// Отслеживание местоположения (владелец, 2026-09): водителей роутер сразу
// уводит в /m/driver, минуя десктопный AppBar.vue (там же обычно живёт
// initStaffLocationTracking) — без этого вызова у водителей передача вообще
// никогда бы не стартовала. initStaffLocationTracking() идемпотентен (см.
// composable) — повторный вызов при переключении раскладок безопасен.
onMounted(() => {
  initStaffLocationTracking()
})

const pageTitle = computed(() => (route.meta?.title as string) || 'FleetOps')

const todayStr = computed(() => {
  return new Date().toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    weekday: 'short',
  })
})

// Determine active tab from current route
const activeTab = computed(() => {
  const name = route.name as string
  if (!name) return 'home'
  if (name.includes('checklist')) return 'checklist'
  if (name.includes('incident')) return 'checklist'
  if (name.includes('history')) return 'history'
  if (name.includes('profile')) return 'profile'
  return 'home'
})
</script>

<style scoped>
.mobile-app {
  max-width: 480px;
  margin: 0 auto;
}

.mobile-header {
  background: rgb(var(--v-theme-surface)) !important;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.mobile-header__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 0 16px;
  gap: 8px;
}

.mobile-header__logo {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.mobile-header__brand {
  font-weight: 800;
  font-size: 15px;
  letter-spacing: -0.3px;
}

.mobile-header__title {
  font-weight: 600;
  font-size: 14px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  text-align: center;
  flex: 1;
}

.mobile-header__date {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  flex-shrink: 0;
  text-align: right;
}

.mobile-main {
  padding-top: 56px !important;
  padding-bottom: 56px !important;
}

.mobile-scroll-area {
  min-height: 100%;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.mobile-bottom-nav {
  max-width: 480px;
  margin: 0 auto;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding-bottom: env(safe-area-inset-bottom, 0);
}

/* Touch-friendly sizes */
:deep(.v-bottom-navigation__content .v-btn) {
  min-height: 56px;
  font-size: 11px;
}
</style>
