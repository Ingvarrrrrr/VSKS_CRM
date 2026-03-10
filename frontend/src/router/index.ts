import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '../views/LoginView.vue'
import DashboardView from '../views/DashboardView.vue'
import SubsidiesView from '../views/SubsidiesView.vue'
import OrdersView from '../views/OrdersView.vue'
import CreateOrderView from '../views/CreateOrderView.vue'
import ContractorsView from '../views/ContractorsView.vue'
import FeoCategoriesView from '../views/FeoCategoriesView.vue'
import ProductsView from '../views/ProductsView.vue'
import PlanView from '../views/PlanView.vue'
import MemoriesView from '../views/MemoriesView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { requiresAuth: false, title: 'Авторизация' }
    },
    {
      path: '/',
      name: 'dashboard',
      component: DashboardView,
      meta: { requiresAuth: false, title: 'Дашборд' } // Временно отключена авторизация
    },
    {
      path: '/subsidies',
      name: 'subsidies',
      component: SubsidiesView,
      meta: { requiresAuth: false, title: 'Субсидии' }
    },
    {
      path: '/orders',
      name: 'orders',
      component: OrdersView,
      meta: { requiresAuth: false, title: 'Заказы' }
    },
    {
      path: '/create-order',
      name: 'create-order',
      component: CreateOrderView,
      meta: { requiresAuth: false, title: 'Новый заказ' }
    },
    {
      path: '/orders/:id/edit',
      name: 'edit-order',
      component: CreateOrderView,
      meta: { requiresAuth: false, title: 'Редактировать закупку' }
    },
    {
      path: '/orders/:id',
      name: 'view-order',
      component: CreateOrderView,
      meta: { requiresAuth: false, title: 'Закупка' }
    },
    {
      path: '/contractors',
      name: 'contractors',
      component: ContractorsView,
      meta: { requiresAuth: false, title: 'Контрагенты' }
    },
    {
      path: '/feo-categories',
      name: 'feo-categories',
      component: FeoCategoriesView,
      meta: { requiresAuth: false, title: 'Категории ФЭО' }
    },
    {
      path: '/products',
      name: 'products',
      component: ProductsView,
      meta: { requiresAuth: false, title: 'Каталог товаров' }
    },
    {
      path: '/memories',
      name: 'memories',
      component: MemoriesView,
      meta: { requiresAuth: false, title: 'База знаний' }
    },
    {
      path: '/plan',
      name: 'plan',
      component: PlanView,
      meta: { requiresAuth: false, title: 'План-график' }
    },
  ]
})

// Навигационные хуки для проверки авторизации
router.beforeEach((to, _, next) => {
  // Временно отключаем проверку авторизации для тестирования
  next()
  
  /* Восстановить позже:
  const token = localStorage.getItem('auth_token')
  
  // Проверяем, есть ли токен и выглядит ли он как JWT
  const isAuthenticated = token !== null && token.startsWith('eyJ')
  
  if (to.meta.requiresAuth && !isAuthenticated) {
    next('/login')
  } else if (to.path === '/login' && isAuthenticated) {
    next('/')
  } else {
    next()
  }
  */
})

export default router