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
import { useAuthStore } from '../stores/auth'

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
      meta: { requiresAuth: true, title: 'Дашборд', tab_key: 'dashboard' }
    },
    {
      path: '/dashboard/radar',
      name: 'radar-dashboard',
      component: () => import('../views/RiskRadarView.vue'),
      meta: { requiresAuth: true, title: 'Risk Radar', tab_key: 'dashboard.radar' }
    },
    {
      path: '/subsidies',
      name: 'subsidies',
      component: SubsidiesView,
      meta: { requiresAuth: true, title: 'Субсидии', tab_key: 'subsidies' }
    },
    {
      path: '/orders',
      name: 'orders',
      component: OrdersView,
      meta: { requiresAuth: true, title: 'Закупки', tab_key: 'purchases' }
    },
    {
      path: '/create-order',
      name: 'create-order',
      component: CreateOrderView,
      meta: { requiresAuth: true, title: 'Новый заказ', tab_key: 'purchases' }
    },
    {
      path: '/orders/:id/edit',
      name: 'edit-order',
      component: CreateOrderView,
      meta: { requiresAuth: true, title: 'Редактировать закупку', tab_key: 'purchases' }
    },
    {
      path: '/orders/:id',
      name: 'view-order',
      component: CreateOrderView,
      meta: { requiresAuth: true, title: 'Закупка', tab_key: 'purchases' }
    },
    {
      path: '/contractors',
      name: 'contractors',
      component: ContractorsView,
      meta: { requiresAuth: true, title: 'Контрагенты', tab_key: 'contractors' }
    },
    {
      path: '/contracts',
      name: 'contracts',
      component: () => import('../views/ContractsView.vue'),
      meta: { requiresAuth: true, title: 'Договоры', tab_key: 'contracts' }
    },
    {
      path: '/feo-categories',
      name: 'feo-categories',
      component: FeoCategoriesView,
      meta: { requiresAuth: true, title: 'Категории ФЭО', tab_key: 'feo_categories' }
    },
    {
      path: '/products',
      name: 'products',
      component: ProductsView,
      meta: { requiresAuth: true, title: 'Каталог товаров', tab_key: 'products' }
    },
    {
      path: '/products-summary',
      name: 'products-summary',
      component: () => import('../views/ProductSummaryView.vue'),
      meta: { requiresAuth: true, title: 'Сводная по продукции', tab_key: 'products.summary' }
    },
    {
      path: '/plan',
      name: 'plan',
      component: PlanView,
      meta: { requiresAuth: true, title: 'План-график', tab_key: 'plan' }
    },
    {
      path: '/commercial-requests',
      name: 'commercial-requests',
      component: CommercialRequestsView,
      meta: { requiresAuth: true, title: 'Запросы КП', tab_key: 'commercial_requests' }
    },
    {
      path: '/analytics',
      redirect: '/dashboard?tab=analytics',
    },
    {
      path: '/my-tasks',
      name: 'my-tasks',
      component: MyTasksView,
      meta: { requiresAuth: true, title: 'Мои задачи и закупки', tab_key: 'my_tasks' }
    },
    {
      path: '/reports',
      name: 'reports',
      component: ReportsView,
      meta: { requiresAuth: true, title: 'Отчёты', tab_key: 'reports' }
    },
    {
      path: '/reports/lists',
      name: 'reports-lists',
      component: () => import('@/views/ReportsListsListView.vue'),
      meta: { requiresAuth: true, title: 'Реестры', tab_key: 'reports' },
    },
    {
      path: '/reports/lists/new',
      name: 'reports-lists-new',
      component: () => import('@/views/ListBuilderView.vue'),
      meta: { requiresAuth: true, title: 'Новый реестр', tab_key: 'reports' },
    },
    {
      path: '/reports/lists/:id/edit',
      name: 'reports-lists-edit',
      component: () => import('@/views/ListBuilderView.vue'),
      meta: { requiresAuth: true, title: 'Редактор реестра', tab_key: 'reports' },
    },
    {
      path: '/reports/lists/:id/run',
      name: 'reports-lists-run',
      component: () => import('@/views/ReportRunView.vue'),
      meta: { requiresAuth: true, title: 'Запуск реестра', tab_key: 'reports' },
    },
    {
      path: '/reports/pivots',
      name: 'reports-pivots',
      component: () => import('@/views/ReportsPivotsListView.vue'),
      meta: { requiresAuth: true, title: 'Сводные', tab_key: 'reports' },
    },
    {
      path: '/reports/pivots/new',
      name: 'reports-pivots-new',
      component: () => import('@/views/PivotBuilderView.vue'),
      meta: { requiresAuth: true, title: 'Новая сводная', tab_key: 'reports' },
    },
    {
      path: '/reports/pivots/:id/edit',
      name: 'reports-pivots-edit',
      component: () => import('@/views/PivotBuilderView.vue'),
      meta: { requiresAuth: true, title: 'Редактор сводной', tab_key: 'reports' },
    },
    {
      path: '/reports/pivots/:id/run',
      name: 'reports-pivots-run',
      component: () => import('@/views/ReportRunView.vue'),
      meta: { requiresAuth: true, title: 'Запуск сводной', tab_key: 'reports' },
    },
    {
      path: '/dashboards',
      name: 'dashboards',
      component: () => import('@/views/ReportsDashboardsListView.vue'),
      meta: { requiresAuth: true, title: 'Дашборды', tab_key: 'reports' },
    },
    {
      path: '/dashboards/new',
      name: 'dashboards-new',
      component: () => import('@/views/DashboardBuilderView.vue'),
      meta: { requiresAuth: true, title: 'Новый дашборд', tab_key: 'reports' },
    },
    {
      path: '/dashboards/:id/edit',
      name: 'dashboards-edit',
      component: () => import('@/views/DashboardBuilderView.vue'),
      meta: { requiresAuth: true, title: 'Редактор дашборда', tab_key: 'reports' },
    },
    {
      path: '/staff',
      name: 'staff',
      component: () => import('../views/StaffView.vue'),
      meta: { requiresAuth: true, title: 'Персонал', tab_key: 'staff' }
    },
    {
      path: '/hierarchy',
      name: 'hierarchy',
      component: () => import('../views/HierarchyView.vue'),
      // Sub-view of /staff — shares tab_key
      meta: { requiresAuth: true, title: 'Иерархия', tab_key: 'staff' }
    },
    {
      path: '/users',
      redirect: '/staff?tab=users',
    },
    {
      path: '/suppliers',
      name: 'suppliers',
      component: SuppliersView,
      // Sub-view of /contractors — shares tab_key
      meta: { requiresAuth: true, title: 'Поставщики', tab_key: 'contractors' }
    },
    {
      path: '/system-incidents',
      name: 'system-incidents',
      component: SystemIncidentsView,
      meta: { requiresAuth: true, title: 'Системные инциденты', tab_key: 'system_incidents' }
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
      meta: { requiresAuth: true, title: 'Организации', tab_key: 'admin.organizations' }
    },
    // Service notes
    {
      path: '/service-notes',
      name: 'service-notes',
      component: ServiceNotesView,
      meta: { requiresAuth: true, title: 'Служебные записки', tab_key: 'service_notes' }
    },
    {
      path: '/service-notes/create',
      name: 'create-service-note',
      component: CreateOrderView,
      meta: { requiresAuth: true, title: 'Новая служебная записка', formMode: 'service_note_delivery', tab_key: 'service_notes' }
    },
    {
      path: '/service-notes/:id/edit',
      name: 'edit-service-note',
      component: CreateOrderView,
      meta: { requiresAuth: true, title: 'Служебная записка', formMode: 'service_note_delivery', tab_key: 'service_notes' }
    },
    // Advance reports
    {
      path: '/advance-reports',
      name: 'advance-reports',
      component: AdvanceReportsView,
      meta: { requiresAuth: true, title: 'Авансовые отчёты', tab_key: 'advance_reports' }
    },
    {
      path: '/advance-reports/create',
      name: 'create-advance-report',
      component: CreateOrderView,
      meta: { requiresAuth: true, title: 'Новый авансовый отчёт', formMode: 'advance_report', tab_key: 'advance_reports' }
    },
    {
      path: '/advance-reports/:id/edit',
      name: 'edit-advance-report',
      component: CreateOrderView,
      meta: { requiresAuth: true, title: 'Авансовый отчёт', formMode: 'advance_report', tab_key: 'advance_reports' }
    },
    // Billing
    {
      path: '/billing',
      name: 'billing',
      component: () => import('../views/BillingView.vue'),
      meta: { requiresAuth: true, title: 'Биллинг', tab_key: 'admin.billing' }
    },
    // Org settings
    {
      path: '/org-settings',
      name: 'org-settings',
      component: OrgSettingsView,
      meta: { requiresAuth: true, title: 'Настройки организации', tab_key: 'admin.settings' }
    },
    // Wishes
    {
      path: '/wishes',
      name: 'wishes',
      component: () => import('../views/WishesView.vue'),
      meta: { requiresAuth: true, title: 'Заявки', tab_key: 'wishes' }
    },
    // Internal chat
    {
      path: '/chat',
      name: 'chat',
      component: () => import('../views/ChatView.vue'),
      meta: { requiresAuth: true, title: 'Чат', tab_key: 'chat' }
    },
    // Admin roles matrix
    {
      path: '/admin/roles',
      name: 'admin-roles',
      component: () => import('../views/AdminRolesView.vue'),
      meta: { requiresAuth: true, title: 'Роли и права', tab_key: 'admin.roles' }
    },
    // Payment import (Phase 22)
    {
      path: '/payments/import',
      name: 'payment-import',
      component: () => import('../views/PaymentImportView.vue'),
      meta: { requiresAuth: true, title: 'Импорт платёжных реестров', tab_key: 'payment_registry' }
    },
    // Payment registry (Phase 22-06)
    {
      path: '/payments/registry',
      name: 'payment-registry',
      component: () => import('../views/PaymentRegistryView.vue'),
      meta: { requiresAuth: true, title: 'Реестр платежей', tab_key: 'payment_registry' }
    },
  ]
})

// Phase 17: Public paths allow-list replaces legacy EMPLOYEE_ALLOWED hardcoded array.
// Route-level gating now runs via meta.tab_key + authStore.hasTab() in beforeEach below.
const PUBLIC_PATHS = ['/', '/login', '/register', '/verify-email', '/reset-password']

// Навигационные хуки для проверки авторизации + tab_key permission gate (Phase 17)
router.beforeEach(async (to, _, next) => {
  const token = localStorage.getItem('auth_token')
  const isAuthenticated = token !== null && token.startsWith('eyJ')
  const role = localStorage.getItem('user_role')

  // Авторизован + лендинг → redirect по роли
  if (to.path === '/' && isAuthenticated) {
    return next(role === 'employee' ? '/my-tasks' : '/dashboard')
  }

  // Публичные маршруты доступны без токена
  if (PUBLIC_PATHS.includes(to.path) || to.meta.public) {
    return next()
  }

  // Не авторизован + закрытый маршрут → лендинг
  if (!isAuthenticated) {
    return next('/')
  }

  // Superadmin bypass (D-05.3)
  if (role === 'superadmin') {
    return next()
  }

  // Ensure permissions are loaded before enforcing tab_key guard
  const authStore = useAuthStore()
  if (!authStore.loaded) {
    await authStore.loadPermissions(localStorage.getItem('active_org_id'))
  }

  // D-01(a): route-level enforcement — if route declares a tab_key, user must have it
  const tabKey = to.meta.tab_key as string | undefined
  if (tabKey && !authStore.hasTab(tabKey)) {
    return next('/my-tasks')
  }

  next()
})

export default router
