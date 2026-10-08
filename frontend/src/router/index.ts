import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '../views/LoginView.vue'
import LandingView from '../views/LandingView.vue'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/useToast'
import { consentGateRequired, ensureConsentGateLoaded } from '../composables/useConsentGate'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'landing',
      component: LandingView,
      meta: { requiresAuth: false, public: true, title: 'GALA' }
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
      component: () => import('../views/DashboardView.vue'),
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
      component: () => import('../views/SubsidiesView.vue'),
      meta: { requiresAuth: true, title: 'Субсидии', tab_key: 'subsidies' }
    },
    {
      // Волна 3C: экран проверяющего для «Корректировки утверждённой субсидии
      // через проверку» — ведут «Мои задачи» (kind=subsidy_revision) и плашка
      // «Есть корректировки на проверке» в SubsidiesView.vue.
      path: '/subsidies/:subsidyId/revisions/:revisionId',
      name: 'subsidy-revision-review',
      component: () => import('../views/SubsidyRevisionReviewView.vue'),
      meta: { requiresAuth: true, title: 'Корректировка субсидии', tab_key: 'subsidies' }
    },
    {
      path: '/orders',
      name: 'orders',
      component: () => import('../views/OrdersView.vue'),
      meta: { requiresAuth: true, title: 'Закупки', tab_key: 'purchases' }
    },
    {
      path: '/create-order',
      name: 'create-order',
      redirect: '/wishes?create=1',
    },
    {
      path: '/orders/:id/edit',
      name: 'edit-order',
      component: () => import('../views/CreateOrderView.vue'),
      meta: { requiresAuth: true, title: 'Редактировать закупку', tab_key: 'purchases' }
    },
    {
      path: '/orders/:id',
      name: 'view-order',
      component: () => import('../views/CreateOrderView.vue'),
      meta: { requiresAuth: true, title: 'Закупка', tab_key: 'purchases' }
    },
    {
      path: '/contractors',
      name: 'contractors',
      component: () => import('../views/ContractorsView.vue'),
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
      component: () => import('../views/FeoCategoriesView.vue'),
      meta: { requiresAuth: true, title: 'Категории ФЭО', tab_key: 'feo_categories' }
    },
    {
      path: '/products',
      name: 'products',
      component: () => import('../views/ProductsView.vue'),
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
      component: () => import('../views/PlanView.vue'),
      meta: { requiresAuth: true, title: 'План закупок', tab_key: 'plan' }
    },
    {
      path: '/commercial-requests',
      name: 'commercial-requests',
      component: () => import('../views/CommercialRequestsView.vue'),
      meta: { requiresAuth: true, title: 'Запросы КП', tab_key: 'commercial_requests' }
    },
    {
      path: '/analytics',
      redirect: '/dashboard?tab=analytics',
    },
    {
      path: '/my-tasks',
      name: 'my-tasks',
      component: () => import('../views/MyTasksView.vue'),
      meta: { requiresAuth: true, title: 'Мои задачи и закупки', tab_key: 'my_tasks' }
    },
    {
      path: '/reports',
      name: 'reports',
      component: () => import('../views/ReportsView.vue'),
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
      path: '/directory',
      name: 'staff-directory',
      component: () => import('@/views/StaffDirectoryView.vue'),
      meta: { requiresAuth: true, title: 'Справочник сотрудников', tab_key: 'staff_directory' },
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
      component: () => import('../views/SuppliersView.vue'),
      // Sub-view of /contractors — shares tab_key
      meta: { requiresAuth: true, title: 'Поставщики', tab_key: 'contractors' }
    },
    {
      path: '/system-incidents',
      name: 'system-incidents',
      component: () => import('../views/SystemIncidentsView.vue'),
      meta: { requiresAuth: true, title: 'Системные инциденты', tab_key: 'system_incidents' }
    },
    {
      path: '/departments',
      redirect: '/staff?tab=departments',
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('../views/RegisterView.vue'),
      meta: { requiresAuth: false, public: true, title: 'Регистрация' }
    },
    {
      // 152-ФЗ: гейт согласия после входа (beforeEach ниже). requiresAuth —
      // неавторизованный сюда попасть не должен (гейт проверяется только
      // после проверки токена), но сам маршрут НЕ public — иначе гейт-проверка
      // ниже решила бы его пропустить как публичный, не в этом смысл: страница
      // не для анонимов, просто сама не участвует в проверке "нужен ли гейт".
      path: '/consent-required',
      name: 'consent-required',
      component: () => import('../views/legal/ConsentRequiredView.vue'),
      meta: { requiresAuth: true, title: 'Подтвердите согласие' }
    },
    {
      path: '/verify-email',
      name: 'verify-email',
      component: () => import('../views/VerifyEmailView.vue'),
      meta: { requiresAuth: false, public: true, title: 'Подтверждение email' }
    },
    {
      path: '/reset-password',
      name: 'reset-password',
      component: () => import('../views/ResetPasswordView.vue'),
      meta: { requiresAuth: false, public: true, title: 'Сброс пароля' }
    },
    {
      // Правовые документы (политика ПДн, согласие, cookie, оферта) — публичные,
      // без входа в систему. meta.public пропускает guard ниже (не завязано на
      // PUBLIC_PATHS: маршрут динамический, to.path не совпадёт ни с одной строкой).
      path: '/legal/:slug',
      name: 'legal-doc',
      component: () => import('../views/legal/LegalDocView.vue'),
      meta: { requiresAuth: false, public: true, title: 'Правовые документы' }
    },
    {
      path: '/organizations',
      name: 'organizations',
      component: () => import('../views/OrganizationsView.vue'),
      meta: { requiresAuth: true, title: 'Организации', tab_key: 'admin.organizations' }
    },
    // Service notes
    {
      path: '/service-notes',
      name: 'service-notes',
      component: () => import('../views/ServiceNotesView.vue'),
      meta: { requiresAuth: true, title: 'Служебные записки', tab_key: 'service_notes' }
    },
    {
      path: '/service-notes/create',
      name: 'create-service-note',
      component: () => import('../views/CreateOrderView.vue'),
      meta: { requiresAuth: true, title: 'Новая служебная записка', formMode: 'service_note_delivery', tab_key: 'service_notes' }
    },
    {
      path: '/service-notes/:id/edit',
      name: 'edit-service-note',
      component: () => import('../views/CreateOrderView.vue'),
      meta: { requiresAuth: true, title: 'Служебная записка', formMode: 'service_note_delivery', tab_key: 'service_notes' }
    },
    // Advance reports
    {
      path: '/advance-reports',
      name: 'advance-reports',
      component: () => import('../views/AdvanceReportsView.vue'),
      meta: { requiresAuth: true, title: 'Реестр авансовых отчётов', tab_key: 'advance_reports' }
    },
    {
      path: '/advance-reports/create',
      name: 'create-advance-report',
      component: () => import('../views/CreateOrderView.vue'),
      meta: { requiresAuth: true, title: 'Новый авансовый отчёт', formMode: 'advance_report', tab_key: 'advance_reports.create' }
    },
    {
      path: '/advance-reports/:id/edit',
      name: 'edit-advance-report',
      component: () => import('../views/CreateOrderView.vue'),
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
      component: () => import('../views/OrgSettingsView.vue'),
      meta: { requiresAuth: true, title: 'Настройки организации', tab_key: 'admin.settings' }
    },
    {
      path: '/expense-codes',
      name: 'expense-codes',
      component: () => import('../views/ExpenseCodesView.vue'),
      meta: { requiresAuth: true, title: 'Коды расходов', tab_key: 'admin.settings' }
    },
    // Wishes
    {
      path: '/wishes',
      name: 'wishes',
      component: () => import('../views/WishesView.vue'),
      meta: { requiresAuth: true, title: 'Заявки на закупку', tab_key: 'wishes' }
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
    // Закрытый раздел «Документы» — внутренние документы 152-ФЗ, только
    // администратору (решение владельца 08.10.2026). Намеренно без
    // tab_key: право на tab_key настраивается в UI «Роли и права» и может
    // быть делегировано вниз по иерархии — для документов, которые сами
    // описывают модель угроз, доступ должен определяться только ролью
    // (requiresAccountAdmin в beforeEach ниже, та же проверка, что на
    // backend — require_role('superadmin', 'admin', 'account_owner') в
    // app/routers/admin_legal_docs.py), а не настраиваемым правом.
    {
      path: '/admin/legal-docs',
      name: 'admin-legal-docs',
      component: () => import('../views/legal/InternalLegalDocsView.vue'),
      meta: { requiresAuth: true, title: 'Правовые документы', requiresAccountAdmin: true }
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
    // Phase 30 — redirects: /property/vehicles/* → /fleet/*
    { path: '/property/vehicles', redirect: '/fleet/vehicles' },
    { path: '/property/vehicles/dashboard', redirect: '/fleet' },
    { path: '/property/vehicles/:id(\\d+)', redirect: (to) => `/fleet/vehicles/${to.params.id}` },
    { path: '/property/vehicles/:id(\\d+)/preview', redirect: (to) => `/fleet/vehicles/${to.params.id}` },

    // Phase 30 — Fleet module routes (/fleet/*)
    {
      path: '/fleet',
      name: 'fleet-dashboard',
      component: () => import('../views/fleet/FleetDashboardView.vue'),
      meta: { requiresAuth: true, title: 'Автопарк — Дашборд', tab_key: 'vehicles' },
    },
    {
      path: '/fleet/vehicles',
      name: 'fleet-vehicles-list',
      component: () => import('../views/property/VehicleListView.vue'),
      meta: { requiresAuth: true, title: 'Автопарк — Реестр ТС', tab_key: 'vehicles' },
    },
    {
      path: '/fleet/vehicles/:id(\\d+)',
      name: 'fleet-vehicle-detail',
      component: () => import('../views/property/VehicleDetailView.vue'),
      props: true,
      meta: { requiresAuth: true, title: 'Карточка ТС', tab_key: 'vehicles' },
    },
    {
      path: '/fleet/documents',
      name: 'fleet-documents',
      component: () => import('../views/fleet/FleetDocumentsView.vue'),
      meta: { requiresAuth: true, title: 'Документы парка', tab_key: 'vehicles' },
    },
    {
      path: '/fleet/regions',
      name: 'fleet-regions',
      component: () => import('../views/fleet/FleetRegionsView.vue'),
      meta: { requiresAuth: true, title: 'Регионы и филиалы', tab_key: 'vehicles' },
    },
    {
      path: '/fleet/fines',
      name: 'fleet-fines',
      component: () => import('../views/fleet/FleetFinesView.vue'),
      meta: { requiresAuth: true, title: 'Штрафы', tab_key: 'vehicles' },
    },
    {
      path: '/fleet/waybills',
      name: 'fleet-waybills',
      component: () => import('../views/fleet/FleetWaybillsListView.vue'),
      meta: { requiresAuth: true, title: 'Путевые листы', tab_key: 'vehicles' },
    },
    {
      path: '/fleet/waybills/:id(\\d+|new)',
      name: 'fleet-waybill-form',
      component: () => import('../views/fleet/FleetWaybillFormView.vue'),
      meta: { requiresAuth: true, title: 'Путевой лист', tab_key: 'vehicles' },
    },
    // Отслеживание местоположения сотрудников (владелец, 2026-09).
    // Диспетчерская карта «Где люди» — доступ по ДЕЙСТВИЮ (staff.location.view),
    // а не по tab_key: право отдельное от общей матрицы вкладок (см.
    // backend/app/routers/staff_location.py). Router-guard tab_key ниже (D-01a)
    // такие маршруты не проверяет вовсе — гейт ставим отдельным beforeEnter,
    // тем же принципом («не показывать вовсе», задание п.3): без права —
    // редирект, а не пустая страница.
    {
      path: '/staff-location',
      name: 'staff-location-map',
      component: () => import('../views/fleet/StaffLocationMapView.vue'),
      meta: { requiresAuth: true, title: 'Где люди' },
      beforeEnter: (_to, _from, next) => {
        const role = localStorage.getItem('user_role')
        if (role === 'superadmin' || role === 'admin') return next()
        const authStore = useAuthStore()
        if (authStore.hasAction('staff.location.view')) return next()
        useToast().warning('Нет права «Просмотр местоположения сотрудников» — обратитесь к администратору организации.')
        next('/dashboard')
      },
    },
    // Своя позиция/трек — доступно ВСЕМ без права staff.location.view (это
    // собственные данные пользователя, см. GET /staff-location/mine/last и
    // /staff-location/track/{self}).
    {
      path: '/my-location',
      name: 'my-location',
      component: () => import('../views/MyLocationView.vue'),
      meta: { requiresAuth: true, title: 'Моё местоположение' },
    },
    // Экран подтверждения отправки геопозиции — открывается по клику на push
    // (см. app/services/push_sender.py url=/location-request/{id}) или из
    // MAX/Telegram fallback-сообщения при желании. Доступен без права
    // staff.location.view — это ответ на СВОЙ запрос (backend проверяет
    // req.user_id == current_user.id, см. staff_location_requests.py).
    {
      path: '/location-request/:id(\\d+)',
      name: 'location-request-respond',
      component: () => import('../views/staff/LocationRequestRespondView.vue'),
      meta: { requiresAuth: true, title: 'Запрос местоположения' },
    },

    // Property / Vehicle fleet (Phase 29) — kept for backward-compat (redirected above)
    {
      path: '/property/vehicles',
      name: 'vehicles',
      component: () => import('../views/property/VehicleListView.vue'),
      meta: { requiresAuth: true, title: 'Автотранспорт', tab_key: 'vehicles' }
    },
    {
      path: '/property/vehicles/dashboard',
      name: 'vehicles-dashboard',
      component: () => import('../views/property/VehicleDashboardView.vue'),
      meta: { requiresAuth: true, title: 'Дашборд автопарка', tab_key: 'vehicles' }
    },
    {
      path: '/property/vehicles/:id(\\d+)',
      name: 'vehicle-detail',
      component: () => import('../views/property/VehicleDetailView.vue'),
      props: true,
      meta: { requiresAuth: true, title: 'Карточка ТС', tab_key: 'vehicles' }
    },
    {
      path: '/property/vehicles/:id(\\d+)/preview',
      name: 'vehicle-layout-preview',
      component: () => import('../views/property/VehicleLayoutPreview.vue'),
      meta: { requiresAuth: true, title: 'Сравнение layout', tab_key: 'vehicles' }
    },
    {
      path: '/property/equipment',
      name: 'equipment',
      component: () => import('../views/property/EquipmentPlaceholderView.vue'),
      meta: { requiresAuth: true, title: 'Оборудование', tab_key: 'vehicles' }
    },
    {
      path: '/property/misc',
      name: 'misc',
      component: () => import('../views/property/MiscPlaceholderView.vue'),
      meta: { requiresAuth: true, title: 'Прочее', tab_key: 'vehicles' }
    },

    // Phase 30 PR4 — Mobile Driver App (/m/driver/*)
    {
      path: '/m/driver',
      component: () => import('../layouts/MobileLayout.vue'),
      meta: { requiresAuth: true, mobileOnly: true },
      children: [
        {
          path: '',
          name: 'm-driver-home',
          component: () => import('../views/mobile/DriverHomeView.vue'),
          meta: { title: 'Моя машина' },
        },
        {
          path: 'checklist',
          name: 'm-driver-checklist',
          component: () => import('../views/mobile/DriverChecklistView.vue'),
          meta: { title: 'Чек-лист' },
        },
        {
          path: 'incident',
          name: 'm-driver-incident',
          component: () => import('../views/mobile/DriverIncidentView.vue'),
          meta: { title: 'Рапорт о ЧП' },
        },
        {
          path: 'history',
          name: 'm-driver-history',
          component: () => import('../views/mobile/DriverHistoryView.vue'),
          meta: { title: 'История' },
        },
        {
          path: 'profile',
          name: 'm-driver-profile',
          component: () => import('../views/mobile/DriverProfileView.vue'),
          meta: { title: 'Профиль' },
        },
      ],
    },
    // waybill detail — outside MobileLayout (full-screen), implemented by PR4-B
    {
      path: '/m/driver/waybills/:id',
      name: 'm-driver-waybill',
      component: () => import('../views/mobile/DriverWaybillView.vue'),
      meta: { mobileOnly: true },
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

  // Водитель (fleet_role='driver') → всегда в мобильный кабинет, если не /m/
  const fleetRole = localStorage.getItem('user_fleet_role') || localStorage.getItem('fleet_role') || ''
  if (isAuthenticated && fleetRole === 'driver' && !to.path.startsWith('/m/')) {
    return next('/m/driver')
  }

  // Публичные маршруты доступны без токена
  if (PUBLIC_PATHS.includes(to.path) || to.meta.public) {
    return next()
  }

  // Не авторизован + закрытый маршрут → лендинг
  if (!isAuthenticated) {
    return next('/')
  }

  // 152-ФЗ: гейт согласия после входа — ДО tab_key-проверки ниже и ДО
  // admin/superadmin bypass (согласие не зависит от роли). Публичные
  // маршруты (включая /legal/*) уже пропущены выше — сюда дошли только
  // защищённые. Сам /consent-required не проверяет себя (иначе
  // бесконечный редирект).
  if (to.path !== '/consent-required') {
    const gateStatus = await ensureConsentGateLoaded()
    if (consentGateRequired(gateStatus)) {
      return next({ path: '/consent-required', query: { redirect: to.fullPath } })
    }
  } else {
    // Сама страница гейта: ни tab_key у неё нет, ни admin/superadmin bypass
    // ей не нужен — выходим ЗДЕСЬ. Без этого выполнение проваливалось в блок
    // "Ensure permissions are loaded" ниже (admin bypass не срабатывает для
    // обычных ролей) и всё равно уводило /users/me ДО прохождения гейта —
    // тот самый запрос с данными пользователя, которого на этой странице не
    // должно быть (воспроизведено в Playwright: GET /users/me?org_id=...).
    return next()
  }

  // Superadmin / admin bypass (D-05.3 + защита от пустого effectiveTabs у admin без org_id —
  // на проде admin привязан к ВСКС и tabs наполнены, локально/после wipe LS admin может
  // оказаться без org → пустые tabs → бесконечный redirect на /my-tasks. Админ всё равно
  // имеет полный доступ по матрице, поэтому пропускаем guard).
  if (role === 'superadmin' || role === 'admin') {
    return next()
  }

  // Маршруты с meta.requiresAccountAdmin (сейчас только /admin/legal-docs —
  // закрытый раздел внутренних документов 152-ФЗ) не используют tab_key:
  // проверяем ТОТ ЖЕ набор ролей, что backend (require_role('superadmin',
  // 'admin', 'account_owner') в app/routers/admin_legal_docs.py); superadmin
  // и admin уже вышли через bypass выше, здесь остаётся дорешить account_owner.
  if (to.meta.requiresAccountAdmin) {
    return role === 'account_owner' ? next() : next('/my-tasks')
  }

  // Ensure permissions are loaded before enforcing tab_key guard
  const authStore = useAuthStore()
  if (!authStore.loaded) {
    await authStore.loadPermissions(localStorage.getItem('active_org_id'))
  }

  // D-01(a): route-level enforcement — if route declares a tab_key, user must have it
  const tabKey = to.meta.tab_key as string | undefined
  if (tabKey && !authStore.hasTab(tabKey)) {
    // Защита от бесконечного редиректа: если /my-tasks сам требует tab_key, которого нет,
    // не редиректим обратно на /my-tasks — пропускаем (fail-open для fallback роута).
    if (to.path === '/my-tasks') return next()
    return next('/my-tasks')
  }

  next()
})

export default router
