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
    <div class="quick-access-header px-4 mb-1">
      <span class="text-caption text-medium-emphasis font-weight-medium text-uppercase" style="letter-spacing:0.06em">Быстрый доступ</span>
      <v-menu v-model="manageMenu" :close-on-content-click="false" max-height="320">
        <template v-slot:activator="{ props }">
          <v-btn v-bind="props" icon="mdi-pencil-outline" variant="text" size="x-small" density="compact" class="ml-auto" title="Настроить" />
        </template>
        <v-card min-width="240" max-width="280">
          <v-card-title class="text-body-2 pa-3 pb-1 font-weight-medium">Выберите субсидии</v-card-title>
          <v-divider />
          <v-list density="compact" style="max-height:220px; overflow-y:auto">
            <v-list-item
              v-for="s in allSubsidies"
              :key="s.id"
              :title="s.name"
              class="px-3"
            >
              <template v-slot:prepend>
                <v-checkbox
                  :model-value="pinnedIds.includes(s.id)"
                  density="compact"
                  hide-details
                  class="mr-1"
                  @update:model-value="togglePin(s.id)"
                />
              </template>
            </v-list-item>
            <v-list-item v-if="allSubsidies.length === 0" class="text-medium-emphasis text-caption px-3">
              Нет субсидий
            </v-list-item>
          </v-list>
          <v-divider />
          <div class="pa-2 text-right">
            <v-btn size="small" variant="text" @click="manageMenu = false">Готово</v-btn>
          </div>
        </v-card>
      </v-menu>
    </div>

    <v-list nav density="compact">
      <v-list-item
        v-for="subsidy in quickSubsidies"
        :key="subsidy.id"
        :title="subsidy.name"
        :subtitle="formatCurrency(subsidy.budget || 0)"
        prepend-icon="mdi-cash"
        @click="goToSubsidy(subsidy.id)"
      >
        <template v-slot:append>
          <v-btn
            icon="mdi-close"
            variant="text"
            size="x-small"
            density="compact"
            color="grey"
            title="Убрать"
            @click.stop="unpinSubsidy(subsidy.id)"
          />
        </template>
      </v-list-item>
      <v-list-item v-if="quickSubsidies.length === 0" class="text-medium-emphasis text-caption">
        Нажмите ✏️ для добавления
      </v-list-item>
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

const STORAGE_KEY = 'quick_access_ids'
const allSubsidies = ref<any[]>([])
const manageMenu = ref(false)

const pinnedIds = ref<number[]>(
  JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
)

const quickSubsidies = computed(() =>
  pinnedIds.value
    .map(id => allSubsidies.value.find(s => s.id === id))
    .filter(Boolean)
)

const menuItems = computed(() => [
  { title: 'Дашборд', icon: 'mdi-view-dashboard', route: '/' },
  { title: 'Субсидии', icon: 'mdi-cash-multiple', route: '/subsidies' },
  { title: 'Заказы', icon: 'mdi-clipboard-list', route: '/orders' },
  { title: 'Новый заказ', icon: 'mdi-plus-circle', route: '/create-order' },
  { title: 'Контрагенты', icon: 'mdi-account-group', route: '/contractors' },
  { title: 'Товары', icon: 'mdi-package-variant', route: '/products' },
  { title: 'Категории ФЭО', icon: 'mdi-folder-tree', route: '/feo-categories' },
  { title: 'План-график', icon: 'mdi-calendar-check', route: '/plan' },
  { title: 'База знаний', icon: 'mdi-brain', route: '/memories' },
])

const formatCurrency = (amount: number) =>
  amount.toLocaleString('ru-RU') + ' ₽'

const logout = () => {
  localStorage.removeItem('auth_token')
  localStorage.removeItem('user_role')
  localStorage.removeItem('user_name')
  router.push('/login')
}

const goToSubsidy = (subsidyId: number) => {
  router.push({ path: '/subsidies', query: { sid: String(subsidyId) } })
}

const savePinned = () => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(pinnedIds.value))
}

const togglePin = (id: number) => {
  const idx = pinnedIds.value.indexOf(id)
  if (idx >= 0) {
    pinnedIds.value = pinnedIds.value.filter(x => x !== id)
  } else {
    pinnedIds.value = [...pinnedIds.value, id]
  }
  savePinned()
}

const unpinSubsidy = (id: number) => {
  pinnedIds.value = pinnedIds.value.filter(x => x !== id)
  savePinned()
}

const loadSubsidies = async () => {
  try {
    const response = await fetch('/api/subsidies/')
    if (response.ok) {
      allSubsidies.value = await response.json()
      // Если впервые (нет сохранённых) — показать первые 3
      if (pinnedIds.value.length === 0 && allSubsidies.value.length > 0) {
        pinnedIds.value = allSubsidies.value.slice(0, 3).map((s: any) => s.id)
        savePinned()
      }
    }
  } catch (error) {
    console.error('Ошибка загрузки субсидий:', error)
  }
}

onMounted(() => {
  loadSubsidies()
})
</script>

<style scoped>
.v-list-item--active {
  border-radius: 0 24px 24px 0;
}
.quick-access-header {
  display: flex;
  align-items: center;
}
</style>
