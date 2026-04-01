import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '../views/LoginView.vue'
import LandingView from '../views/LandingView.vue'
import DashboardView from '../views/DashboardView.vue'
import SubsidiesView from '../views/SubsidiesView.vue'
import OrdersView from '../views/OrdersView.vue'
import CreateOrderView from '../views/CreateOrderView.vue'
import ContractorsView from '../views/ContractorsView.vue'
import FeoCategoriesView from '../views/FeoCategoriesView.vue'
import ProductsView from '../views/ProductsView.vue'
import PlanView from '../views/PlanView.vue'
import CommercialRequestsView from '../views/CommercialRequestsView.vue'
import MyTasksView from '../views/MyTasksView.vue'
import ReportsView from '../views/ReportsView.vue'
import SuppliersView from '../views/SuppliersView.vue'
import SystemIncidentsView from '../views/SystemIncidentsView.vue'
import RegisterView from '../views/RegisterView.vue'
import VerifyEmailView from '../views/VerifyEmailView.vue'
import ResetPasswordView from '../views/ResetPasswordView.vue'
import OrganizationsView from '../views/OrganizationsView.vue'
import ServiceNotesView from '../views/ServiceNotesView.vue'
import AdvanceReportsView from '../views/AdvanceReportsView.vue'
import OrgSettingsView from '../views/OrgSettingsView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'landing',
      component: LandingView,
      meta: { requiresAuth: false, public: true, title: 'VSKS CRM' }
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { requiresAuth: false, public: true, title: 'Авторизация' }
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: DashboardView,
      meta: { requiresAuth: false, title: 'Дашборд' }
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
      meta: { requiresAuth: false, title: 'Закупки' }
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
      path: '/contracts',
      name: 'contracts',
      component: () => import('../views/ContractsView.vue'),
      meta: { requiresAuth: false, title: 'Договоры' }
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
      path: '/products-summary',
      name: 'products-summary',
      component: () => import('../views/ProductSummaryView.vue'),
      meta: { requiresAuth: false, title: 'Сводная по продукции' }
    },
    {
      path: '/plan',
      name: 'plan',
      component: PlanView,
      meta: { requiresAuth: false, title: 'План-график' }
    },
    {
      path: '/commercial-requests',
      name: 'commercial-requests',
      component: CommercialRequestsView,
      meta: { requiresAuth: false, title: 'Запросы КП' }
    },
    {
      path: '/analytics',
      redirect: '/dashboard?tab=analytics',
    },
    {
      path: '/my-tasks',
      name: 'my-tasks',
      component: MyTasksView,
      meta: { requiresAuth: false, title: 'Мои задачи' }
    },
    {
      path: '/reports',
      name: 'reports',
      component: ReportsView,
      meta: { requiresAuth: false, title: 'Отчёты' }
    },
    {
      path: '/staff',
      name: 'staff',
      component: () => import('../views/StaffView.vue'),
      meta: { requiresAuth: false, title: 'Персонал' }
    },
    {
      path: '/hierarchy',
      name: 'hierarchy',
      component: () => import('../views/HierarchyView.vue'),
      meta: { requiresAuth: false, title: 'Иерархия' }
    },
    {
      path: '/users',
      redirect: '/staff?tab=users',
    },
    {
      path: '/suppliers',
      name: 'suppliers',
      component: SuppliersView,
      meta: { requiresAuth: false, title: 'Поставщики' }
    },
    {
      path: '/system-incidents',
      name: 'system-incidents',
      component: SystemIncidentsView,
      meta: { requiresAuth: false, title: 'Системные инциденты' }
    },
    {
      path: '/departments',
      redirect: '/staff?tab=departments',
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterView,
      meta: { requiresAuth: false, public: true, title: 'Регистрация' }
    },
    {
      path: '/verify-email',
      name: 'verify-email',
      component: VerifyEmailView,
      meta: { requiresAuth: false, public: true, title: 'Подтверждение email' }
    },
    {
      path: '/reset-password',
      name: 'reset-password',
      component: ResetPasswordView,
      meta: { requiresAuth: false, public: true, title: 'Сброс пароля' }
    },
    {
      path: '/organizations',
      name: 'organizations',
      component: OrganizationsView,
      meta: { requiresAuth: false, title: 'Организации' }
    },
    // Service notes
    {
      path: '/service-notes',
      name: 'service-notes',
      component: ServiceNotesView,
      meta: { requiresAuth: false, title: 'Служебные записки' }
    },
    {
      path: '/service-notes/create',
      name: 'create-service-note',
      component: CreateOrderView,
      meta: { requiresAuth: false, title: 'Новая служебная записка', formMode: 'service_note_delivery' }
    },
    {
      path: '/service-notes/:id/edit',
      name: 'edit-service-note',
      component: CreateOrderView,
      meta: { requiresAuth: false, title: 'Служебная записка', formMode: 'service_note_delivery' }
    },
    // Advance reports
    {
      path: '/advance-reports',
      name: 'advance-reports',
      component: AdvanceReportsView,
      meta: { requiresAuth: false, title: 'Авансовые отчёты' }
    },
    {
      path: '/advance-reports/create',
      name: 'create-advance-report',
      component: CreateOrderView,
      meta: { requiresAuth: false, title: 'Новый авансовый отчёт', formMode: 'advance_report' }
    },
    {
      path: '/advance-reports/:id/edit',
      name: 'edit-advance-report',
      component: CreateOrderView,
      meta: { requiresAuth: false, title: 'Авансовый отчёт', formMode: 'advance_report' }
    },
    // Billing
    {
      path: '/billing',
      name: 'billing',
      component: () => import('../views/BillingView.vue'),
      meta: { requiresAuth: false, title: 'Биллинг' }
    },
    // Org settings
    {
      path: '/org-settings',
      name: 'org-settings',
      component: OrgSettingsView,
      meta: { requiresAuth: false, title: 'Настройки организации' }
    },
  ]
})

// Разрешённые маршруты для employee
const EMPLOYEE_ALLOWED = ['/my-tasks', '/orders/', '/login', '/register', '/', '/verify-email', '/reset-password']

// Навигационные хуки для проверки авторизации
router.beforeEach((to, _, next) => {
  const token = localStorage.getItem('auth_token')
  const isAuthenticated = token !== null && token.startsWith('eyJ')
  const role = localStorage.getItem('user_role')

  // Авторизован + лендинг → redirect по роли
  if (to.path === '/' && isAuthenticated) {
    return next(role === 'employee' ? '/my-tasks' : '/dashboard')
  }

  // Не авторизован + закрытый маршрут → лендинг
  if (!isAuthenticated && !to.meta.public) {
    return next('/')
  }

  // Employee guard: ограниченный доступ
  if (isAuthenticated && role === 'employee') {
    const path = to.path
    const allowed = path === '/my-tasks'
      || path === '/products'
      || path === '/contractors'
      || path === '/orders'
      || path === '/create-order'
      || path.startsWith('/orders/')
      || path.startsWith('/service-notes')
      || path.startsWith('/advance-reports')
      || to.meta.public
    if (!allowed) {
      return next('/my-tasks')
    }
  }

  next()
})

export default router