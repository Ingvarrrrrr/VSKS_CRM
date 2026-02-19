<template>
  <v-app-bar color="primary" density="compact">
    <template v-slot:prepend>
      <v-app-bar-nav-icon @click="drawer = !drawer" />
    </template>
    
    <v-app-bar-title class="text-h6 font-weight-bold">
      VSKS CRM
      <span class="text-caption ml-2">Патриотика 2025</span>
    </v-app-bar-title>
    
    <v-spacer />
    
    <v-menu>
      <template v-slot:activator="{ props }">
        <v-btn v-bind="props" variant="text">
          <v-avatar size="32" color="secondary" class="mr-2">
            <v-icon icon="mdi-account" />
          </v-avatar>
          {{ userName }}
          <v-icon icon="mdi-chevron-down" class="ml-2" />
        </v-btn>
      </template>
      <v-list>
        <v-list-item>
          <v-list-item-title>
            <v-icon icon="mdi-account" class="mr-2" />{{ userRole }}
          </v-list-item-title>
        </v-list-item>
        <v-divider />
        <v-list-item @click="logout">
          <v-list-item-title>
            <v-icon icon="mdi-logout" class="mr-2" />Выйти
          </v-list-item-title>
        </v-list-item>
      </v-list>
    </v-menu>
  </v-app-bar>
  
  <v-navigation-drawer v-model="drawer" temporary>
    <v-list>
      <v-list-item
        v-for="item in menuItems"
        :key="item.title"
        :to="item.route"
        :prepend-icon="item.icon"
        :title="item.title"
      />
    </v-list>
  </v-navigation-drawer>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const drawer = ref(false)

const userName = computed(() => localStorage.getItem('user_name') || 'Пользователь')
const userRole = computed(() => {
  const role = localStorage.getItem('user_role')
  const roles: Record<string, string> = {
    admin: 'Администратор',
    manager: 'Менеджер',
    employee: 'Сотрудник'
  }
  return roles[role || ''] || role || 'Неизвестно'
})

const menuItems = computed(() => {
  // Все пункты меню для всех ролей (для тестирования)
  const allItems = [
    { title: 'Дашборд', icon: 'mdi-view-dashboard', route: '/' },
    { title: 'Субсидии', icon: 'mdi-cash-multiple', route: '/subsidies' },
    { title: 'Заказы', icon: 'mdi-clipboard-list', route: '/orders' },
    { title: 'Новый заказ', icon: 'mdi-plus-circle', route: '/create-order' },
    { title: 'Контрагенты', icon: 'mdi-account-group', route: '/contractors' },
    { title: 'Категории ФЭО', icon: 'mdi-folder-tree', route: '/feo-categories' },
  ]
  
  return allItems
})

const logout = () => {
  localStorage.removeItem('auth_token')
  localStorage.removeItem('user_role')
  localStorage.removeItem('user_name')
  router.push('/login')
}
</script>