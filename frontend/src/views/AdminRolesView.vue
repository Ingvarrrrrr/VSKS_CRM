<template>
  <v-container fluid class="pa-4">
    <v-card elevation="2">
      <v-card-title class="text-h6">Роли и права доступа</v-card-title>
      <v-card-subtitle class="pb-2">
        Матрица прав: галочка = роль имеет доступ к вкладке / действию.
        Изменения сохраняются автоматически через ~0.3 сек после каждого клика.
        <br />
        <v-chip
          size="small"
          color="info"
          variant="tonal"
          class="mt-2"
          prepend-icon="mdi-information-outline"
        >
          Действие «Публикации» задаётся индивидуально в карточке пользователя и здесь не отображается.
        </v-chip>
      </v-card-subtitle>

      <v-tabs v-model="activeTab" color="primary">
        <v-tab value="tabs">Доступ к листам</v-tab>
        <v-tab value="actions">Критичные действия</v-tab>
      </v-tabs>

      <v-divider />

      <v-card-text>
        <!-- Loading state -->
        <div v-if="loading" class="d-flex justify-center align-center py-8">
          <v-progress-circular indeterminate color="primary" />
          <span class="ml-4 text-body-2">Загрузка матрицы прав...</span>
        </div>

        <!-- Error state -->
        <v-alert v-else-if="loadError" type="error" variant="tonal" class="mb-4">
          {{ loadError }}
          <template #append>
            <v-btn size="small" variant="text" @click="loadAll">Повторить</v-btn>
          </template>
        </v-alert>

        <!-- Matrix -->
        <v-window v-else v-model="activeTab">
          <v-window-item value="tabs">
            <div v-if="tabs.length === 0" class="text-body-2 text-medium-emphasis py-4">
              Нет доступных вкладок.
            </div>
            <div v-else class="overflow-x-auto">
              <PermissionTable
                :roles="visibleRoles"
                :columns="tabs"
                :granted="tabsGranted"
                :current-role="currentRole"
                :protected-keys="SELF_LOCKOUT"
                @change="onCellChange"
              />
            </div>
          </v-window-item>

          <v-window-item value="actions">
            <div v-if="visibleActions.length === 0" class="text-body-2 text-medium-emphasis py-4">
              Нет доступных действий.
            </div>
            <div v-else class="overflow-x-auto">
              <PermissionTable
                :roles="visibleRoles"
                :columns="visibleActions"
                :granted="actionsGranted"
                :current-role="currentRole"
                :protected-keys="SELF_LOCKOUT"
                @change="onCellChange"
              />
            </div>
          </v-window-item>
        </v-window>

        <!-- Save status -->
        <div class="save-status mt-3 text-caption" aria-live="polite">
          <span v-if="saving" class="text-info">
            <v-icon size="14" class="mr-1">mdi-loading</v-icon>Сохранение...
          </span>
          <span v-else-if="saved" class="text-success">
            <v-icon size="14" class="mr-1">mdi-check-circle-outline</v-icon>Сохранено ✓
          </span>
          <span v-else-if="saveError" class="text-error">
            <v-icon size="14" class="mr-1">mdi-alert-circle-outline</v-icon>{{ saveError }}
          </span>
        </div>
      </v-card-text>
    </v-card>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiFetch } from '../api'
import PermissionTable from '../components/PermissionTable.vue'

// D-05.2: self-lockout keys — cannot revoke own role's access to these tabs
const SELF_LOCKOUT = ['admin.roles', 'staff']

// W5: per-user-only action — EXCLUDE from role matrix, configure per user in user card
const PER_USER_ONLY_ACTIONS = ['publication.create']

// D-09: superadmin excluded; D-07: only these 5 roles visible
const VISIBLE_ROLES = ['account_owner', 'admin', 'org_admin', 'manager', 'employee']

// ---- State ----
const tabs = ref<{ tab_key: string; title: string }[]>([])
const actions = ref<{ action_key: string; description: string }[]>([])
const matrix = ref<Record<string, { tabs: Set<string>; actions: Set<string> }>>({})

const activeTab = ref<'tabs' | 'actions'>('tabs')
const loading = ref(true)
const loadError = ref<string | null>(null)
const saving = ref(false)
const saved = ref(false)
const saveError = ref<string | null>(null)

// Current user's role for self-lockout check
const currentRole = localStorage.getItem('user_role') ?? ''

// ---- Computed ----
const visibleRoles = computed(() => VISIBLE_ROLES)

// W5: filter out per-user-only actions from the role matrix
const visibleActions = computed(() =>
  actions.value.filter((a) => !PER_USER_ONLY_ACTIONS.includes(a.action_key))
)

const tabsGranted = computed<Record<string, Set<string>>>(() => {
  const out: Record<string, Set<string>> = {}
  for (const role of VISIBLE_ROLES) {
    out[role] = matrix.value[role]?.tabs ?? new Set()
  }
  return out
})

const actionsGranted = computed<Record<string, Set<string>>>(() => {
  const out: Record<string, Set<string>> = {}
  for (const role of VISIBLE_ROLES) {
    out[role] = matrix.value[role]?.actions ?? new Set()
  }
  return out
})

// ---- Data loading ----
async function loadAll() {
  loading.value = true
  loadError.value = null
  try {
    const [tabList, actList, roleRows] = await Promise.all([
      apiFetch<{ tab_key: string; title: string }[]>('/permissions/tabs'),
      apiFetch<{ action_key: string; description: string }[]>('/permissions/actions'),
      apiFetch<{ role_name: string; tabs: string[]; actions: string[] }[]>('/permissions/roles'),
    ])
    tabs.value = tabList
    actions.value = actList

    const m: Record<string, { tabs: Set<string>; actions: Set<string> }> = {}
    for (const r of roleRows) {
      m[r.role_name] = {
        tabs: new Set(r.tabs),
        actions: new Set(r.actions),
      }
    }
    matrix.value = m
  } catch (e: any) {
    loadError.value = `Не удалось загрузить матрицу прав: ${e?.message ?? e}`
  } finally {
    loading.value = false
  }
}

// ---- Debounced save ----
// Per-role pending update queue + timers for 300ms debounce
const pending: Record<string, { key: string; granted: boolean }[]> = {}
const timers: Record<string, ReturnType<typeof setTimeout>> = {}

function onCellChange(roleName: string, key: string, granted: boolean) {
  // Optimistically update local matrix
  if (!matrix.value[roleName]) {
    matrix.value[roleName] = { tabs: new Set(), actions: new Set() }
  }
  const bucket = tabs.value.some((t) => t.tab_key === key) ? 'tabs' : 'actions'
  if (granted) {
    matrix.value[roleName][bucket].add(key)
  } else {
    matrix.value[roleName][bucket].delete(key)
  }

  // Queue the update, replacing any previous pending entry for this (role, key)
  pending[roleName] = (pending[roleName] ?? []).filter((u) => u.key !== key)
  pending[roleName].push({ key, granted })

  // Debounce: 300ms
  if (timers[roleName]) clearTimeout(timers[roleName])
  timers[roleName] = setTimeout(() => flush(roleName), 300)
}

async function flush(roleName: string) {
  const updates = pending[roleName]
  if (!updates || updates.length === 0) return
  pending[roleName] = []

  saving.value = true
  saved.value = false
  saveError.value = null

  try {
    await apiFetch(`/permissions/roles/${roleName}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    })
    saved.value = true
    // Auto-hide "Сохранено" after 1.5s
    setTimeout(() => {
      saved.value = false
    }, 1500)
  } catch (e: any) {
    saveError.value = `Не удалось сохранить: ${e?.message ?? e}`
    // Revert optimistic update by reloading from server
    await loadAll()
  } finally {
    saving.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.save-status {
  min-height: 20px;
}
</style>
