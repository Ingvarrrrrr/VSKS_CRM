<template>
  <v-app-bar color="surface" density="compact" elevation="1">
    <!-- Hamburger — только на мобильных -->
    <v-app-bar-nav-icon class="d-md-none" @click="drawerOpen = !drawerOpen" />

    <v-app-bar-title>
      <router-link to="/" class="gala-logo d-flex align-center text-decoration-none">
        <svg viewBox="0 0 44 44" width="28" height="28" fill="none" class="gala-mark">
          <path d="M30 8 L10 8 L10 36 L30 36 L30 24 L21 24"
                stroke="currentColor" stroke-width="3.5"
                stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <span class="gala-wordmark ml-2">GA<span class="gala-l">L</span>A</span>
      </router-link>
    </v-app-bar-title>

    <div class="nav-icons d-none d-md-flex">
      <v-btn
        v-for="nav in navShortcuts"
        :key="nav.route"
        :to="nav.route"
        variant="text"
        size="small"
        class="nav-icon-btn"
        :class="{ 'nav-icon-btn--active': $route.path === nav.route }"
      >
        <v-icon :icon="nav.icon" size="18" />
        <span class="nav-icon-label">{{ nav.label }}</span>
      </v-btn>

      <!-- Имущество submenu (Phase 30 — /fleet/* routes) -->
      <v-menu v-if="authStore.hasTab('vehicles')" open-on-hover :open-delay="100" :close-delay="150">
        <template v-slot:activator="{ props: menuProps }">
          <v-btn
            v-bind="menuProps"
            variant="text"
            size="small"
            class="nav-icon-btn"
            :class="{ 'nav-icon-btn--active': $route.path.startsWith('/fleet') }"
          >
            <v-icon icon="mdi-warehouse" size="18" />
            <span class="nav-icon-label">Имущество</span>
          </v-btn>
        </template>
        <v-list density="compact" min-width="200">
          <v-list-item
            :to="'/fleet'"
            prepend-icon="mdi-view-dashboard"
            title="Дашборд автопарка"
          />
          <v-list-item
            :to="'/fleet/vehicles'"
            prepend-icon="mdi-car-multiple"
            title="Реестр ТС"
          />
          <v-list-item
            :to="'/fleet/documents'"
            prepend-icon="mdi-file-document-multiple"
            title="Документы"
          />
          <v-list-item
            :to="'/fleet/regions'"
            prepend-icon="mdi-map"
            title="Регионы и филиалы"
          />
          <v-list-item
            :to="'/fleet/fines'"
            prepend-icon="mdi-alert-octagon"
            title="Штрафы"
          />
          <v-list-item
            :to="'/fleet/waybills'"
            prepend-icon="mdi-clipboard-list"
            title="Путевые листы"
          />
          <v-list-item
            :to="'/m/driver'"
            prepend-icon="mdi-cellphone"
            title="Мобильный кабинет водителя"
          />
          <v-divider />
          <v-list-item
            :to="'/property/equipment'"
            prepend-icon="mdi-toolbox-outline"
            title="Оборудование"
          />
          <v-list-item
            :to="'/property/misc'"
            prepend-icon="mdi-package-variant-closed"
            title="Прочее"
          />
        </v-list>
      </v-menu>
    </div>

    <v-select
      v-if="!isEmployee && allSubsidies.length > 0"
      v-model="globalSubsidyId"
      :items="allSubsidies"
      item-title="name" item-value="id"
      label="Субсидия"
      variant="solo-filled" density="compact" clearable hide-details
      style="max-width: 240px; min-width: 160px"
      class="ml-3 d-none d-md-flex"
      bg-color="rgba(255,255,255,0.15)"
      flat
    />

    <v-spacer />

    <!-- Тёмная тема — приоритет перед остальными иконками, чтобы не обрезалась на узких экранах -->
    <v-btn
      :icon="isDark ? 'mdi-weather-sunny' : 'mdi-weather-night'"
      variant="text"
      size="small"
      class="mr-1"
      :title="isDark ? 'Светлая тема' : 'Тёмная тема'"
      @click="toggleTheme"
    />

    <global-search class="mr-3 d-none d-sm-flex" />

    <!-- Superadmin: multi-org picker button -->
    <v-btn
      v-if="isSuperadmin"
      variant="text"
      size="small"
      class="mr-2"
      @click="openOrgPicker"
    >
      <v-icon icon="mdi-domain" class="mr-1" />
      <span v-if="selectedOrgNames.length === 0">Выбрать организации</span>
      <span v-else-if="selectedOrgNames.length === 1">{{ selectedOrgNames[0] }}</span>
      <span v-else>{{ selectedOrgNames.length }} орг.</span>
      <v-icon icon="mdi-chevron-down" class="ml-1" size="16" />
    </v-btn>

    <!-- Non-superadmin: single org switcher -->
    <v-menu v-else-if="myOrgs.length > 1">
      <template v-slot:activator="{ props }">
        <v-btn v-bind="props" variant="text" size="small" class="mr-2">
          <v-icon icon="mdi-domain" class="mr-1" />
          {{ userOrgName || 'Организация' }}
          <v-icon icon="mdi-swap-horizontal" class="ml-1" size="16" />
        </v-btn>
      </template>
      <v-list density="compact" max-width="300">
        <v-list-subheader>Переключить организацию</v-list-subheader>
        <v-list-item
          v-for="org in myOrgs" :key="org.id"
          :title="org.name"
          :active="org.id === activeOrgId"
          @click="switchOrgSingle(org)"
        >
          <template v-slot:prepend>
            <v-icon :icon="org.id === activeOrgId ? 'mdi-check-circle' : 'mdi-circle-outline'" :color="org.id === activeOrgId ? 'primary' : 'grey'" />
          </template>
        </v-list-item>
      </v-list>
    </v-menu>

    <v-menu>
      <template v-slot:activator="{ props }">
        <v-btn v-bind="props" variant="text" icon>
          <UserAvatar :photo-url="myPhotoUrl" :avatar="myAvatar" :size="32" />
        </v-btn>
      </template>
      <v-list>
        <v-list-item>
          <v-list-item-title class="d-flex align-center ga-2">
            <UserAvatar :photo-url="myPhotoUrl" :avatar="myAvatar" :size="28" />
            {{ userRole }}
          </v-list-item-title>
        </v-list-item>
        <v-divider />
        <v-list-item @click="photoUploadRef?.open()">
          <v-list-item-title class="d-flex align-center">
            <v-icon icon="mdi-camera-account" class="mr-2" />Моя фотография
            <v-chip v-if="myPhotoUrl" size="x-small" color="success" variant="tonal" class="ml-2">есть</v-chip>
          </v-list-item-title>
        </v-list-item>
        <v-list-item @click="openSignaturePad">
          <v-list-item-title class="d-flex align-center">
            <v-icon icon="mdi-draw" class="mr-2" />Моя подпись
            <v-chip v-if="hasSignature" size="x-small" color="success" variant="tonal" class="ml-2">есть</v-chip>
            <v-chip v-else size="x-small" color="warning" variant="tonal" class="ml-2">нет</v-chip>
          </v-list-item-title>
        </v-list-item>
        <v-divider />
        <!-- 27.4-24: ручная очистка кеша (для "502 на одном компьютере" — stale PWA SW) -->
        <v-list-item @click="forceClearCache" :title="'Очистить кеш SW и перезагрузить страницу'">
          <v-list-item-title>
            <v-icon icon="mdi-broom" class="mr-2" color="warning" />Очистить кеш браузера
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

  <!-- Signature Pad dialog -->
  <SignaturePad ref="sigPadRef" @saved="onSignatureSaved" />
  <!-- Profile Photo Upload dialog -->
  <ProfilePhotoUpload ref="photoUploadRef" @saved="onPhotoSaved" />
  </v-app-bar>

  <!-- Superadmin org picker dialog -->
  <v-dialog v-model="orgPickerDialog" max-width="520" :persistent="selectedOrgIds.length === 0" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon icon="mdi-domain" class="mr-2" />
        Выберите организации
      </v-card-title>
      <v-card-subtitle class="px-4 pb-2">
        Данные будут отфильтрованы по выбранным организациям
      </v-card-subtitle>

      <v-text-field
        v-model="orgSearch"
        placeholder="Поиск по названию или ИНН..."
        prepend-inner-icon="mdi-magnify"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        class="mx-4 mb-2"
      />

      <v-card-text class="pa-0" style="max-height: 400px; overflow-y: auto">
        <v-list density="compact">
          <v-list-item class="px-4 py-0" style="min-height: 32px">
            <template v-slot:prepend>
              <v-checkbox
                :model-value="allOrgsSelected"
                :indeterminate="someOrgsSelected && !allOrgsSelected"
                density="compact"
                hide-details
                class="mr-2"
                @update:model-value="toggleAllOrgs"
              />
            </template>
            <v-list-item-title class="text-body-2 font-weight-medium">
              Выбрать все ({{ filteredOrgs.length }})
            </v-list-item-title>
          </v-list-item>
          <v-divider />
          <v-list-item
            v-for="org in filteredOrgs" :key="org.id"
            class="px-4 py-0"
            style="min-height: 40px"
            @click="toggleOrgSelection(org.id)"
          >
            <template v-slot:prepend>
              <v-checkbox
                :model-value="pendingOrgIds.includes(org.id)"
                density="compact"
                hide-details
                class="mr-2"
                @click.stop="toggleOrgSelection(org.id)"
              />
            </template>
            <v-list-item-title class="text-body-2">{{ org.name }}</v-list-item-title>
          </v-list-item>
          <v-list-item v-if="filteredOrgs.length === 0" class="text-center text-medium-emphasis pa-4">
            Организации не найдены
          </v-list-item>
        </v-list>
      </v-card-text>

      <v-divider />
      <v-card-actions class="pa-4">
        <span class="text-caption text-medium-emphasis">
          Выбрано: {{ pendingOrgIds.length }}
        </span>
        <v-spacer />
        <v-btn variant="text" @click="cancelOrgPicker" :disabled="selectedOrgIds.length === 0">
          Отмена
        </v-btn>
        <v-btn color="primary" variant="flat" :loading="orgSwitching" :disabled="pendingOrgIds.length === 0" @click="applyOrgSelection">
          Применить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-navigation-drawer v-model="drawerOpen" :permanent="mdAndUp" width="280" color="surface">
    <v-list nav density="compact" class="mt-4" v-model:opened="openedNavGroups" open-strategy="multiple">
      <template v-for="(item, idx) in orderedMenuItems" :key="item.route">
        <v-list-item
          :to="item.route"
          :prepend-icon="item.icon"
          :title="item.title"
          active-class="bg-primary text-white"
          draggable="true"
          :class="{ 'sidebar-drag-over': dragOverIdx === idx, 'sidebar-dragging': dragIdx === idx }"
          @dragstart="onSidebarDragStart($event, idx)"
          @dragover.prevent="onSidebarDragOver(idx)"
          @dragleave="onSidebarDragLeave"
          @drop.prevent="onSidebarDrop(idx)"
          @dragend="onSidebarDragEnd"
        >
          <template v-slot:append>
            <div class="d-flex align-center ga-1">
              <span v-if="item.route === '/my-tasks' && badgeNewTasks > 0"
                class="sidebar-badge sidebar-badge--new" :title="`${badgeNewTasks} новых задач`">{{ badgeNewTasks }}</span>
              <span v-if="item.route === '/my-tasks' && badgeTaskChanges > 0"
                class="sidebar-badge sidebar-badge--changes" :title="`${badgeTaskChanges} изменений`">{{ badgeTaskChanges }}</span>
              <span v-if="item.route === '/orders' && badgeNewPurchases > 0"
                class="sidebar-badge sidebar-badge--new" :title="`${badgeNewPurchases} новых закупок`">{{ badgeNewPurchases }}</span>
              <span v-if="item.route === '/orders' && badgePurchaseChanges > 0"
                class="sidebar-badge sidebar-badge--changes" :title="`${badgePurchaseChanges} изменений`">{{ badgePurchaseChanges }}</span>
              <span v-if="item.route === '/chat' && badgeChatUnread > 0"
                class="sidebar-badge sidebar-badge--new" :title="`${badgeChatUnread} непрочитанных`">{{ badgeChatUnread }}</span>
              <v-icon icon="mdi-drag-horizontal-variant" size="16" class="sidebar-drag-handle" />
            </div>
          </template>
        </v-list-item>
      </template>

      <!-- Phase 30.2: Автопарк — collapsible group (vehicles tab) -->
      <v-list-group
        v-if="authStore.hasTab('vehicles')"
        value="fleet"
      >
        <template #activator="{ props: gProps }">
          <v-list-item
            v-bind="gProps"
            prepend-icon="mdi-car-multiple"
            title="Автопарк"
            :active="isFleetRouteActive"
            active-class="bg-primary text-white"
          />
        </template>
        <v-list-item to="/fleet"              prepend-icon="mdi-view-dashboard"          title="Дашборд"                    active-class="bg-primary text-white" />
        <v-list-item to="/fleet/vehicles"     prepend-icon="mdi-car"                     title="Реестр ТС"                  active-class="bg-primary text-white" />
        <v-list-item to="/fleet/documents"    prepend-icon="mdi-file-document-multiple"  title="Документы"                  active-class="bg-primary text-white" />
        <v-list-item to="/fleet/regions"      prepend-icon="mdi-map"                     title="Регионы и филиалы"            active-class="bg-primary text-white" />
        <v-list-item to="/fleet/fines"        prepend-icon="mdi-alert-octagon"           title="Штрафы"                     active-class="bg-primary text-white" />
        <v-list-item to="/fleet/waybills"     prepend-icon="mdi-clipboard-list"          title="Путевые листы"              active-class="bg-primary text-white" />
        <v-list-item to="/m/driver"           prepend-icon="mdi-cellphone"               title="Мобильный кабинет водителя" active-class="bg-primary text-white" />
      </v-list-group>
    </v-list>

    <v-divider v-if="!isEmployee" class="my-4" />

    <!-- Быстрый доступ к субсидиям (скрыто для employee) -->
    <div v-if="!isEmployee" class="quick-access-header px-4 mb-1">
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

    <v-list v-if="!isEmployee" nav density="compact">
      <v-list-item
        v-for="(subsidy, idx) in quickSubsidies"
        :key="subsidy.id"
        :title="subsidy.name"
        :subtitle="formatCurrency(subsidy.calculated_budget || subsidy.budget || 0)"
        draggable="true"
        :class="{ 'sidebar-drag-over': subDragOverIdx === idx, 'sidebar-dragging': subDragIdx === idx }"
        @dragstart="onSubDragStart($event, idx)"
        @dragover.prevent="onSubDragOver(idx)"
        @dragleave="subDragOverIdx = -1"
        @drop.prevent="onSubDrop(idx)"
        @dragend="subDragOverIdx = -1; subDragIdx = -1"
        @click="goToSubsidy(subsidy.id)"
      >
        <template v-slot:prepend>
          <v-icon icon="mdi-drag-horizontal-variant" size="14" class="me-1 cursor-grab" style="opacity:0.4" />
          <v-icon icon="mdi-cash" size="18" />
        </template>
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
        Нажмите карандаш для добавления
      </v-list-item>
    </v-list>

    <template v-slot:append>
      <div class="pa-3 drawer-user-footer">
        <div class="d-flex align-center ga-2" style="min-width:0">
          <UserAvatar :photo-url="myPhotoUrl" :avatar="myAvatar" :size="36" />
          <div style="min-width:0; flex:1 1 auto">
            <div class="text-body-2 font-weight-medium text-truncate" :title="userName">{{ userName }}</div>
            <div v-if="orgSummary" class="text-caption text-medium-emphasis text-truncate" :title="orgSummary">{{ orgSummary }}</div>
            <v-chip size="x-small" color="primary" variant="flat" class="mt-1">{{ userRole }}</v-chip>
          </div>
        </div>
      </div>
    </template>
  </v-navigation-drawer>

  <v-bottom-navigation
    v-if="mobile"
    grow
    color="primary"
    height="60"
    elevation="8"
    class="mobile-bottom-nav"
  >
    <v-btn
      v-for="item in bottomNavItems"
      :key="item.route"
      :to="item.route"
      :active="$route.path === item.route || $route.path.startsWith(item.route + '/')"
      size="small"
    >
      <v-icon :icon="item.icon" />
      <span class="text-caption">{{ item.label }}</span>
    </v-btn>
    <v-btn size="small" @click="drawerOpen = true">
      <v-icon icon="mdi-dots-horizontal" />
      <span class="text-caption">Ещё</span>
    </v-btn>
  </v-bottom-navigation>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useTheme, useDisplay } from 'vuetify'
import GlobalSearch from './GlobalSearch.vue'
import SignaturePad from './SignaturePad.vue'
import ProfilePhotoUpload from './ProfilePhotoUpload.vue'
import UserAvatar from './UserAvatar.vue'
import { useGlobalSubsidy } from '@/composables/useGlobalSubsidy'
import { apiFetch, forceClearCacheAndReload } from '@/api'
import { totalUnread, initChat, destroyChat } from '@/composables/useChat'
import { useAuthStore } from '../stores/auth'

const { globalSubsidyId } = useGlobalSubsidy()
const authStore = useAuthStore()

const router = useRouter()
const $route = useRoute()
const { mdAndUp, mobile } = useDisplay()

// Drawer: open by default on desktop, closed on mobile
const drawerOpen = ref(!mobile.value)

// Auto-close drawer on navigation (mobile)
watch(() => $route.path, () => {
  if (!mdAndUp.value) drawerOpen.value = false
})
const vuetifyTheme = useTheme()

const ADMIN_ROLES = ['superadmin', 'account_owner', 'org_admin', 'admin']
const MANAGER_ROLES = ['superadmin', 'account_owner', 'org_admin', 'admin', 'manager']
const ALL_ROLES = ['superadmin', 'account_owner', 'org_admin', 'admin', 'manager', 'employee']

const isEmployee = computed(() => userRoleRaw.value === 'employee')

const allNavShortcuts = [
  { label: 'Дашборд', icon: 'mdi-view-dashboard', route: '/dashboard', tab_key: 'dashboard' },
  { label: 'Radar', icon: 'mdi-radar', route: '/dashboard/radar', tab_key: 'dashboard.radar' },
  { label: 'Задачи и закупки', icon: 'mdi-clipboard-account', route: '/my-tasks', tab_key: 'my_tasks' },
  { label: 'Заявки на закупку', icon: 'mdi-hand-heart-outline', route: '/wishes', tab_key: 'wishes' },
  { label: 'Субсидии', icon: 'mdi-cash-multiple', route: '/subsidies', tab_key: 'subsidies' },
  { label: 'Закупки', icon: 'mdi-clipboard-list', route: '/orders', tab_key: 'purchases' },
  { label: 'Договоры', icon: 'mdi-file-document-multiple', route: '/contracts', tab_key: 'contracts' },
  { label: 'Контрагенты', icon: 'mdi-account-group', route: '/contractors', tab_key: 'contractors' },
  { label: 'Отчёты', icon: 'mdi-file-chart', route: '/reports', tab_key: 'reports' },
]
const navShortcuts = computed(() =>
  allNavShortcuts.filter(n => authStore.hasTab(n.tab_key))
)

const _allBottomNavItems = [
  { label: 'Дашборд',      icon: 'mdi-view-dashboard',    route: '/dashboard',    tab_key: 'dashboard' },
  { label: 'Чат',          icon: 'mdi-chat',              route: '/chat',         tab_key: 'chat' },
  { label: 'Закупки',      icon: 'mdi-clipboard-list',    route: '/orders',       tab_key: 'purchases' },
  { label: 'Задачи',       icon: 'mdi-clipboard-account', route: '/my-tasks',     tab_key: 'my_tasks' },
  { label: 'Автопарк',     icon: 'mdi-warehouse',         route: '/fleet',        tab_key: 'vehicles' },
  { label: 'Контрагенты',  icon: 'mdi-account-group',     route: '/contractors',  tab_key: 'contractors' },
]
const bottomNavItems = computed(() =>
  _allBottomNavItems.filter(item => authStore.hasTab(item.tab_key)).slice(0, 4)
)
// ── Sidebar badges ──
const badgeNewTasks = ref(0)
const badgeTaskChanges = ref(0)
const badgeNewPurchases = ref(0)
const badgePurchaseChanges = ref(0)
const badgeChatUnread = ref(0)
let _badgeInterval: ReturnType<typeof setInterval> | null = null

async function loadBadges() {
  try {
    const activeOrgId = localStorage.getItem('active_org_id')
    const url = activeOrgId ? `/tasks/badges?org_id=${activeOrgId}` : '/tasks/badges'
    const data = await apiFetch<any>(url)
    badgeNewTasks.value = data.new_tasks || 0
    badgeTaskChanges.value = data.task_changes || 0
    badgeNewPurchases.value = data.new_purchases || 0
    badgePurchaseChanges.value = data.purchase_changes || 0
    badgeChatUnread.value = data.chat_unread || 0
  } catch {}
}

const isDark = computed(() => vuetifyTheme.global.name.value === 'dark')
function toggleTheme() {
  const next = isDark.value ? 'light' : 'dark'
  vuetifyTheme.global.name.value = next
  localStorage.setItem('theme', next)
}

const userName = computed(() => localStorage.getItem('user_name') || 'Пользователь')
const userOrgName = computed(() => localStorage.getItem('user_org_name') || '')
const userRoleRaw = computed(() => localStorage.getItem('user_role') || '')
const userRole = computed(() => {
  const roles: Record<string, string> = {
    superadmin: 'Суперадмин',
    org_admin: 'Администратор',
    manager: 'Менеджер',
    employee: 'Сотрудник',
    admin: 'Администратор',
  }
  return roles[userRoleRaw.value] || userRoleRaw.value || 'Неизвестно'
})
const isSuperadmin = computed(() => userRoleRaw.value === 'superadmin')
const orgSummary = computed(() => {
  if (isSuperadmin.value) {
    const n = selectedOrgNames.value.length
    if (n === 0) return 'Организации не выбраны'
    if (n === 1) return selectedOrgNames.value[0]
    return `${n} организаций`
  }
  return userOrgName.value || ''
})

// Phase 30.2: fleet group — состояние раскрытия держит родительский v-list
// через opened. Открываем при переходе на /fleet/* или /m/, но НЕ убираем при
// уходе на другой раздел — схлопывается только когда пользователь сам свернул.
const openedNavGroups = ref<string[]>(
  ($route.path.startsWith('/fleet') || $route.path.startsWith('/m/')) ? ['fleet'] : []
)
watch(() => $route.path, (path) => {
  if ((path.startsWith('/fleet') || path.startsWith('/m/')) && !openedNavGroups.value.includes('fleet')) {
    openedNavGroups.value = [...openedNavGroups.value, 'fleet']
  }
})
const isFleetRouteActive = computed(() =>
  $route.path.startsWith('/fleet') || $route.path.startsWith('/m/')
)

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

const _allMenuItems = [
  { title: 'Дашборд', icon: 'mdi-view-dashboard', route: '/dashboard', tab_key: 'dashboard' },
  { title: 'Radar', icon: 'mdi-radar', route: '/dashboard/radar', tab_key: 'dashboard.radar' },
  { title: 'Мои задачи и закупки', icon: 'mdi-clipboard-account', route: '/my-tasks', tab_key: 'my_tasks' },
  { title: 'Заявки на закупку', icon: 'mdi-hand-heart-outline', route: '/wishes', tab_key: 'wishes' },
  { title: 'Субсидии', icon: 'mdi-cash-multiple', route: '/subsidies', tab_key: 'subsidies' },
  { title: 'Закупки', icon: 'mdi-clipboard-list', route: '/orders', tab_key: 'purchases' },
  { title: 'Новый заказ', icon: 'mdi-plus-circle', route: '/wishes?create=1', tab_key: 'wishes' },
  { title: 'Контрагенты', icon: 'mdi-account-group', route: '/contractors', tab_key: 'contractors' },
  { title: 'Договоры', icon: 'mdi-file-document-multiple', route: '/contracts', tab_key: 'contracts' },
  { title: 'Товары', icon: 'mdi-package-variant', route: '/products', tab_key: 'products' },
  { title: 'Сводная по продукции', icon: 'mdi-chart-box-outline', route: '/products-summary', tab_key: 'products.summary' },
  { title: 'Категории ФЭО', icon: 'mdi-folder-tree', route: '/feo-categories', tab_key: 'feo_categories' },
  { title: 'Запросы КП', icon: 'mdi-email-send-outline', route: '/commercial-requests', tab_key: 'commercial_requests' },
  { title: 'Персонал', icon: 'mdi-account-group', route: '/staff', tab_key: 'staff' },
  { title: 'Справочник', icon: 'mdi-account-multiple-outline', route: '/directory', tab_key: 'staff_directory' },
  { title: 'Отчёты', icon: 'mdi-file-chart', route: '/reports', tab_key: 'reports' },
  { title: 'Реестры', icon: 'mdi-table', route: '/reports/lists', tab_key: 'reports' },
  { title: 'Сводные', icon: 'mdi-pivot', route: '/reports/pivots', tab_key: 'reports' },
  { title: 'Дашборды', icon: 'mdi-view-dashboard', route: '/dashboards', tab_key: 'reports' },
  { title: 'План-график', icon: 'mdi-calendar-check', route: '/plan', tab_key: 'plan' },
  { title: 'Инциденты', icon: 'mdi-alert-circle-outline', route: '/system-incidents', tab_key: 'system_incidents' },
  { title: 'Организации', icon: 'mdi-domain', route: '/organizations', tab_key: 'admin.organizations' },
  { title: 'Биллинг', icon: 'mdi-currency-rub', route: '/billing', tab_key: 'admin.billing' },
  { title: 'Служебные записки', icon: 'mdi-file-account-outline', route: '/service-notes', tab_key: 'service_notes' },
  { title: 'Авансовый отчёт', icon: 'mdi-cash-plus', route: '/advance-reports/create', tab_key: 'advance_reports.create' },
  { title: 'Реестр авансовых отчётов', icon: 'mdi-cash-register', route: '/advance-reports', tab_key: 'advance_reports' },
  { title: 'Платежи', icon: 'mdi-bank-transfer', route: '/payments/import', tab_key: 'payment_registry' },
  { title: 'Настройки', icon: 'mdi-cog-outline', route: '/org-settings', tab_key: 'admin.settings' },
  // Phase 30.2: fleet routes moved to dedicated v-list-group «Автопарк» — removed from flat list to avoid duplication
  { title: 'Чат', icon: 'mdi-message-outline', route: '/chat', tab_key: 'chat' },
  { title: 'Роли', icon: 'mdi-shield-key-outline', route: '/admin/roles', tab_key: 'admin.roles' },
]
const menuItems = computed(() =>
  _allMenuItems.filter(i => authStore.hasTab(i.tab_key))
)

// ── Sidebar drag-and-drop reorder ──
const SIDEBAR_ORDER_KEY = 'sidebar_menu_order'
const savedSidebarOrder = ref<string[]>(
  JSON.parse(localStorage.getItem(SIDEBAR_ORDER_KEY) || '[]')
)

const orderedMenuItems = computed(() => {
  const items = menuItems.value
  const order = savedSidebarOrder.value
  if (order.length === 0) return items
  const sorted = [...items].sort((a, b) => {
    const ai = order.indexOf(a.route)
    const bi = order.indexOf(b.route)
    if (ai === -1 && bi === -1) return 0
    if (ai === -1) return 1
    if (bi === -1) return -1
    return ai - bi
  })
  return sorted
})

const dragIdx = ref<number | null>(null)
const dragOverIdx = ref<number | null>(null)

function onSidebarDragStart(e: DragEvent, idx: number) {
  dragIdx.value = idx
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(idx))
  }
}
function onSidebarDragOver(idx: number) {
  dragOverIdx.value = idx
}
function onSidebarDragLeave() {
  dragOverIdx.value = null
}
function onSidebarDrop(targetIdx: number) {
  dragOverIdx.value = null
  if (dragIdx.value === null || dragIdx.value === targetIdx) return
  const items = [...orderedMenuItems.value]
  const [moved] = items.splice(dragIdx.value, 1)
  items.splice(targetIdx, 0, moved)
  savedSidebarOrder.value = items.map(i => i.route)
  localStorage.setItem(SIDEBAR_ORDER_KEY, JSON.stringify(savedSidebarOrder.value))
  dragIdx.value = null
}
function onSidebarDragEnd() {
  dragIdx.value = null
  dragOverIdx.value = null
}

// ── Subsidy drag-and-drop reorder ──
const subDragIdx = ref(-1)
const subDragOverIdx = ref(-1)

function onSubDragStart(e: DragEvent, idx: number) {
  subDragIdx.value = idx
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}

function onSubDragOver(idx: number) {
  subDragOverIdx.value = idx
}

function onSubDrop(targetIdx: number) {
  const srcIdx = subDragIdx.value
  if (srcIdx < 0 || srcIdx === targetIdx) return
  const arr = [...pinnedIds.value]
  const [moved] = arr.splice(srcIdx, 1)
  arr.splice(targetIdx, 0, moved)
  pinnedIds.value = arr
  localStorage.setItem(STORAGE_KEY, JSON.stringify(arr))
  subDragOverIdx.value = -1
  subDragIdx.value = -1
}

const formatCurrency = (amount: number) =>
  amount.toLocaleString('ru-RU') + ' ₽'

// ── Signature ───────────────────────────────────────────────────────────────
const sigPadRef = ref<InstanceType<typeof SignaturePad> | null>(null)
const hasSignature = ref(false)

async function loadSignatureStatus() {
  try {
    const data = await apiFetch<{ signature: string | null }>('/users/me/signature')
    hasSignature.value = !!data.signature
  } catch { hasSignature.value = false }
}

function openSignaturePad() {
  sigPadRef.value?.open()
}

function onSignatureSaved(has: boolean) {
  hasSignature.value = has
}

// ── Profile photo ────────────────────────────────────────────────────────────
const photoUploadRef = ref<InstanceType<typeof ProfilePhotoUpload> | null>(null)
const myPhotoUrl = ref<string | null>(null)
const myAvatar = computed(() => localStorage.getItem('user_avatar') || null)

async function loadMyPhoto() {
  try {
    const data = await apiFetch<{ photo_url: string | null }>('/users/me/photo')
    myPhotoUrl.value = data.photo_url || null
  } catch { myPhotoUrl.value = null }
}

function onPhotoSaved(photoUrl: string | null) {
  myPhotoUrl.value = photoUrl
}

const logout = () => {
  authStore.clear()
  localStorage.removeItem('auth_token')
  localStorage.removeItem('user_role')
  localStorage.removeItem('user_name')
  localStorage.removeItem('user_org_id')
  localStorage.removeItem('user_org_name')
  localStorage.removeItem('selected_org_ids')
  localStorage.removeItem('selected_org_names')
  router.push('/login')
}

// 27.4-24: ручная очистка PWA-кеша при 502 на одном компе
async function forceClearCache() {
  if (!confirm('Очистить кеш и перезагрузить страницу? Авторизация сохранится.')) return
  await forceClearCacheAndReload()
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

// ── Org switcher (non-superadmin) ──
const myOrgs = ref<{id: number; name: string; is_active: boolean}[]>([])
const activeOrgId = computed(() => {
  const stored = localStorage.getItem('user_org_id')
  return stored ? parseInt(stored) : null
})

const loadMyOrgs = async () => {
  try {
    const token = localStorage.getItem('auth_token')
    if (!token) return
    const response = await fetch('/api/auth/my-orgs', {
      headers: { Authorization: `Bearer ${token}` }
    })
    if (response.ok) {
      myOrgs.value = await response.json()
    }
  } catch (e) {
    console.error('Ошибка загрузки организаций:', e)
  }
}

const switchOrgSingle = async (org: {id: number; name: string}) => {
  try {
    const token = localStorage.getItem('auth_token')
    const response = await fetch('/api/auth/switch-org', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ org_id: org.id })
    })
    if (response.ok) {
      const data = await response.json()
      localStorage.setItem('auth_token', data.access_token)
      localStorage.setItem('user_org_id', String(data.org_id))
      localStorage.setItem('active_org_id', String(data.org_id))
      localStorage.setItem('user_org_name', data.org_name)
      try {
        await authStore.loadPermissions(data.org_id)
      } catch (e) {
        console.error('[org-switch] loadPermissions failed, fail-open', e)
        authStore.loaded = true
      }
      window.location.reload()
    }
  } catch (e) {
    console.error('Ошибка переключения организации:', e)
  }
}

// ── Superadmin multi-org picker ──
const orgPickerDialog = ref(false)
const orgSearch = ref('')
const pendingOrgIds = ref<number[]>([])
const orgSwitching = ref(false)

const selectedOrgIds = ref<number[]>(
  JSON.parse(localStorage.getItem('selected_org_ids') || '[]')
)
const selectedOrgNames = computed(() => {
  try {
    return JSON.parse(localStorage.getItem('selected_org_names') || '[]') as string[]
  } catch { return [] }
})

const filteredOrgs = computed(() => {
  if (!orgSearch.value) return myOrgs.value
  const s = orgSearch.value.toLowerCase()
  return myOrgs.value.filter(o =>
    o.name.toLowerCase().includes(s)
  )
})

const allOrgsSelected = computed(() =>
  filteredOrgs.value.length > 0 && filteredOrgs.value.every(o => pendingOrgIds.value.includes(o.id))
)
const someOrgsSelected = computed(() =>
  filteredOrgs.value.some(o => pendingOrgIds.value.includes(o.id))
)

function openOrgPicker() {
  pendingOrgIds.value = [...selectedOrgIds.value]
  orgPickerDialog.value = true
}

function toggleAllOrgs(val: boolean) {
  if (val) {
    const ids = new Set(pendingOrgIds.value)
    filteredOrgs.value.forEach(o => ids.add(o.id))
    pendingOrgIds.value = [...ids]
  } else {
    const removeSet = new Set(filteredOrgs.value.map(o => o.id))
    pendingOrgIds.value = pendingOrgIds.value.filter(id => !removeSet.has(id))
  }
}

function toggleOrgSelection(id: number) {
  const idx = pendingOrgIds.value.indexOf(id)
  if (idx >= 0) {
    pendingOrgIds.value = pendingOrgIds.value.filter(x => x !== id)
  } else {
    pendingOrgIds.value = [...pendingOrgIds.value, id]
  }
}

function cancelOrgPicker() {
  pendingOrgIds.value = [...selectedOrgIds.value]
  orgPickerDialog.value = false
}

async function applyOrgSelection() {
  orgSwitching.value = true
  try {
    const token = localStorage.getItem('auth_token')
    const response = await fetch('/api/auth/select-orgs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ org_ids: pendingOrgIds.value })
    })
    if (response.ok) {
      const data = await response.json()
      localStorage.setItem('auth_token', data.access_token)
      localStorage.setItem('selected_org_ids', JSON.stringify(data.org_ids))
      localStorage.setItem('selected_org_names', JSON.stringify(data.org_names))
      selectedOrgIds.value = data.org_ids
      orgPickerDialog.value = false
      try {
        const primaryOrgId = data.org_ids?.[0] ?? null
        if (primaryOrgId != null) localStorage.setItem('active_org_id', String(primaryOrgId))
        await authStore.loadPermissions(primaryOrgId)
      } catch (e) {
        console.error('[org-select] loadPermissions failed, fail-open', e)
        authStore.loaded = true
      }
      window.location.reload()
    }
  } catch (e) {
    console.error('Ошибка выбора организаций:', e)
  } finally {
    orgSwitching.value = false
  }
}

const loadSubsidies = async () => {
  try {
    const token = localStorage.getItem('auth_token')
    const headers: Record<string, string> = {}
    if (token) headers.Authorization = `Bearer ${token}`
    const response = await fetch('/api/subsidies/', { headers })
    if (response.ok) {
      allSubsidies.value = await response.json()
      // Сбросить глобальный выбор, если субсидия стала недоступна (доступ отозван/
      // удалена) — иначе в селекторе залипал сырой id.
      if (globalSubsidyId.value && !allSubsidies.value.some((s: any) => s.id === globalSubsidyId.value)) {
        globalSubsidyId.value = null
      }
      if (pinnedIds.value.length === 0 && allSubsidies.value.length > 0) {
        pinnedIds.value = allSubsidies.value.slice(0, 3).map((s: any) => s.id)
        savePinned()
      }
    }
  } catch (error) {
    console.error('Ошибка загрузки субсидий:', error)
  }
}

onMounted(async () => {
  // Refresh user role/name from server
  try {
    const me = await apiFetch<any>('/users/me')
    if (me.role) localStorage.setItem('user_role', me.role)
    if (me.full_name || me.username) localStorage.setItem('user_name', me.full_name || me.username)
    if (me.can_publish !== undefined) localStorage.setItem('can_publish', me.can_publish ? 'true' : 'false')
  } catch {}

  await loadMyOrgs()
  loadSubsidies()
  loadSignatureStatus()
  loadMyPhoto()
  loadBadges()
  _badgeInterval = setInterval(loadBadges, 60_000)  // refresh every 60s
  initChat()  // start WS connection for chat badge updates

  // Superadmin: auto-open org picker if no orgs selected
  if (isSuperadmin.value && selectedOrgIds.value.length === 0 && myOrgs.value.length > 0) {
    await nextTick()
    pendingOrgIds.value = []
    orgPickerDialog.value = true
  } else {
    pendingOrgIds.value = [...selectedOrgIds.value]
  }
})

onUnmounted(() => {
  if (_badgeInterval) { clearInterval(_badgeInterval); _badgeInterval = null }
  destroyChat()
})

// Keep badgeChatUnread in sync with totalUnread from WS events (real-time)
watch(totalUnread, (val) => { badgeChatUnread.value = val })
</script>

<style scoped>
.mobile-bottom-nav {
  position: fixed !important;
  bottom: 0;
  left: 0;
  right: 0;
  width: 100% !important;
  transform: none !important;
  z-index: 2000;
  padding-bottom: env(safe-area-inset-bottom);
  height: calc(60px + env(safe-area-inset-bottom)) !important;
}
.v-list-item--active {
  border-radius: 0 24px 24px 0;
}
.quick-access-header {
  display: flex;
  align-items: center;
}
.nav-icons {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: 12px;
}
.nav-icon-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 56px;
  height: 44px !important;
  padding: 2px 8px !important;
  border-radius: 8px;
  opacity: 0.8;
  text-transform: none;
  letter-spacing: 0;
  position: relative;
  transition: all 0.2s ease;
}
.nav-icon-btn:hover {
  opacity: 1;
  background: rgba(255,255,255,0.15);
}
.nav-icon-btn--active {
  opacity: 1;
  background: rgba(255,255,255,0.2) !important;
}

/* ── Active nav glow (Wiza-inspired) ── */
.nav-icon-btn::after {
  content: '';
  position: absolute;
  bottom: 2px;
  left: 50%;
  width: 0;
  height: 2px;
  background: linear-gradient(90deg, #8B5CF6, #EC4899, #F59E0B);
  border-radius: 2px;
  transform: translateX(-50%);
  transition: width 0.25s cubic-bezier(0.22, 1, 0.36, 1);
}
.nav-icon-btn--active::after,
.nav-icon-btn:hover::after {
  width: 70%;
}
.nav-icon-label {
  font-size: 10px;
  line-height: 1.1;
  margin-top: 1px;
  white-space: nowrap;
}

/* Sidebar drag-and-drop */
.sidebar-drag-handle {
  opacity: 0;
  transition: opacity 0.15s;
  cursor: grab;
  color: var(--crm-text-muted, rgba(0,0,0,0.38));
}
.v-list-item:hover .sidebar-drag-handle {
  opacity: 0.6;
}
.sidebar-dragging {
  opacity: 0.4;
}
.sidebar-drag-over {
  border-top: 2px solid rgb(var(--v-theme-primary));
  margin-top: -2px;
}
.sidebar-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  border-radius: 9px;
  font-size: 10px;
  font-weight: 700;
  color: white;
  padding: 0 5px;
  line-height: 1;
}
.sidebar-badge--new {
  background: #4CAF50;
}
.sidebar-badge--changes {
  background: #FF9800;
}

/* ── AppBar glass effect ── */
:deep(.v-app-bar) {
  backdrop-filter: blur(8px) saturate(1.2);
  -webkit-backdrop-filter: blur(8px) saturate(1.2);
}

/* iOS standalone (black-translucent статус-бар + viewport-fit=cover): контент
   уходит под часы/нотч. Опускаем шапку на высоту safe-area, фон шапки закрывает
   зону статус-бара. На desktop/Android env()=0 → правило ничего не меняет. */
:deep(.v-app-bar.v-toolbar) {
  height: calc(48px + env(safe-area-inset-top)) !important;
  padding-top: env(safe-area-inset-top);
}
:deep(.v-app-bar .v-toolbar__content) {
  height: 48px !important;
}

/* ── Logo title hover ── */
:deep(.v-app-bar-title) {
  transition: opacity 0.2s ease;
  min-width: 140px;
  flex: 0 0 auto;
  margin-inline-end: 16px;
}
:deep(.v-app-bar-title:hover) {
  opacity: 0.85;
}
:deep(.v-app-bar-title__placeholder) {
  overflow: visible !important;
  text-overflow: clip !important;
  white-space: nowrap;
}

/* ── GALA brand mark ── */
.gala-logo {
  color: var(--gala-orange);
}
.v-theme--light .gala-logo {
  color: var(--gala-orange-dark);
}
.gala-wordmark {
  font-family: var(--font-brand);
  font-weight: 800;
  letter-spacing: 0.12em;
  font-size: 20px;
  color: rgb(var(--v-theme-on-surface));
  line-height: 1;
}
.gala-l {
  color: var(--gala-orange);
}
.v-theme--light .gala-l {
  color: var(--gala-orange-dark);
}
</style>
