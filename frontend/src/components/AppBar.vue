<template>
  <v-app-bar color="primary" density="compact">
    <v-app-bar-title class="text-h6 font-weight-bold">
      <v-icon icon="mdi-account-cash" class="mr-2" />
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
  
  <v-navigation-drawer permanent width="280" class="bg-grey-lighten-4">
    <v-list nav density="compact" class="mt-4">
      <v-list-item
        v-for="item in menuItems"
        :key="item.title"
        :to="item.route"
        :prepend-icon="item.icon"
        :title="item.title"
        active-class="bg-primary text-white"
      />
    </v-list>
    
    <v-divider class="my-4" />
    
    <!-- Быстрый доступ к субсидиям -->
    <v-list nav density="compact" subheader>
      <v-list-subheader>Быстрый доступ</v-list-subheader>
      <v-list-item
        v-for="subsidy in quickSubsidies"
        :key="subsidy.id"
        :title="subsidy.name"
        :subtitle="formatCurrency(subsidy.budget || 0)"
        prepend-icon="mdi-cash"
        @click="goToSubsidy(subsidy.id)"
      />
    </v-list>
    
    <template v-slot:append>
      <div class="pa-4 text-center">
        <v-chip size="small" color="primary" variant="flat">
          {{ userRole }}
        </v-chip>
      </div>
    </template>
  </v-navigation-drawer>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

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

const quickSubsidies = ref<any[]>([])

const menuItems = computed(() => {
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

const formatCurrency = (amount: number) => {
  return amount.toLocaleString() + ' ₽'
}

const logout = () => {
  localStorage.removeItem('auth_token')
  localStorage.removeItem('user_role')
  localStorage.removeItem('user_name')
  router.push('/login')
}

const goToSubsidy = (subsidyId: number) => {
  router.push(`/subsidies#${subsidyId}`)
}

const loadQuickSubsidies = async () => {
  try {
    const response = await fetch('/api/subsidies/')
    if (response.ok) {
      const data = await response.json()
      // Берем первые 3 субсидии для быстрого доступа
      quickSubsidies.value = data.slice(0, 3)
    }
  } catch (error) {
    console.error('Ошибка загрузки субсидий:', error)
  }
}

onMounted(() => {
  loadQuickSubsidies()
})
</script>

<style scoped>
.v-list-item--active {
  border-radius: 0 24px 24px 0;
}
</style>