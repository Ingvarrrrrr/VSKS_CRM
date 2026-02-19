<template>
  <v-app>
    <app-bar v-if="isAuthenticated" />
    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import AppBar from './components/AppBar.vue'

const router = useRouter()
const isAuthenticated = computed(() => localStorage.getItem('auth_token') !== null)

// При старте приложения проверяем авторизацию
if (!isAuthenticated.value && router.currentRoute.value.path !== '/login') {
  router.push('/login')
}
</script>