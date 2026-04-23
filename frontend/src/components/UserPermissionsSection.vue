<template>
  <v-card variant="outlined" class="mt-4">
    <v-card-title class="d-flex align-center pa-4">
      <span>Доступ</span>
      <v-spacer />
      <v-chip
        v-if="hasOverrides"
        color="warning"
        size="small"
        prepend-icon="mdi-account-cog"
      >Индивидуально</v-chip>
      <v-chip v-else color="primary" size="small">{{ roleLabel(userRole) }}</v-chip>
    </v-card-title>

    <v-card-text class="pa-4 pt-0">
      <v-select
        v-model="selectedOrgId"
        :items="orgOptions"
        item-title="label"
        item-value="value"
        label="Организация"
        density="compact"
        variant="outlined"
        class="mb-3"
        hide-details
        @update:model-value="onOrgChange"
      />

      <v-tabs v-model="activeTab" density="compact" class="mb-2">
        <v-tab value="tabs">Листы ({{ tabs.length }})</v-tab>
        <v-tab value="actions">Критичные действия ({{ actions.length }})</v-tab>
      </v-tabs>

      <v-window v-model="activeTab">
        <!-- Tabs (page visibility) -->
        <v-window-item value="tabs">
          <div v-if="loading" class="d-flex justify-center py-4">
            <v-progress-circular indeterminate size="24" />
          </div>
          <div v-else>
            <div
              v-for="t in tabs"
              :key="t.tab_key"
              class="d-flex align-center py-1"
            >
              <v-tooltip
                :text="isLocked(t.tab_key) ? 'Нельзя снять с себя доступ к Ролям/Персоналу' : ''"
                location="top"
                :disabled="!isLocked(t.tab_key)"
              >
                <template #activator="{ props: tipProps }">
                  <div v-bind="tipProps" style="display:inline-flex;align-items:center;">
                    <v-checkbox
                      :model-value="isGranted(t.tab_key)"
                      :label="t.title"
                      :disabled="isLocked(t.tab_key)"
                      density="compact"
                      hide-details
                      @update:model-value="(v) => toggle(t.tab_key, !!v)"
                    />
                  </div>
                </template>
              </v-tooltip>
              <v-chip
                v-if="overrideState(t.tab_key) === 'grant'"
                color="success"
                size="x-small"
                class="ml-2"
                closable
                @click:close="removeOverride(t.tab_key)"
              >+ добавлено</v-chip>
              <v-chip
                v-if="overrideState(t.tab_key) === 'revoke'"
                color="error"
                size="x-small"
                class="ml-2"
                closable
                @click:close="removeOverride(t.tab_key)"
              >− убрано</v-chip>
            </div>
          </div>
        </v-window-item>

        <!-- Actions (critical operations) -->
        <v-window-item value="actions">
          <div v-if="loading" class="d-flex justify-center py-4">
            <v-progress-circular indeterminate size="24" />
          </div>
          <div v-else>
            <div
              v-for="a in actions"
              :key="a.action_key"
              class="d-flex align-center py-1"
            >
              <v-tooltip
                :text="isLocked(a.action_key) ? 'Нельзя снять с себя критичное действие' : ''"
                location="top"
                :disabled="!isLocked(a.action_key)"
              >
                <template #activator="{ props: tipProps }">
                  <div v-bind="tipProps" style="display:inline-flex;align-items:center;">
                    <v-checkbox
                      :model-value="isGranted(a.action_key)"
                      :label="a.description ?? a.action_key"
                      :disabled="isLocked(a.action_key)"
                      density="compact"
                      hide-details
                      @update:model-value="(v) => toggle(a.action_key, !!v)"
                    />
                  </div>
                </template>
              </v-tooltip>
              <v-chip
                v-if="overrideState(a.action_key) === 'grant'"
                color="success"
                size="x-small"
                class="ml-2"
                closable
                @click:close="removeOverride(a.action_key)"
              >+ добавлено</v-chip>
              <v-chip
                v-if="overrideState(a.action_key) === 'revoke'"
                color="error"
                size="x-small"
                class="ml-2"
                closable
                @click:close="removeOverride(a.action_key)"
              >− убрано</v-chip>
            </div>
          </div>
        </v-window-item>
      </v-window>

      <div v-if="saving" class="text-caption text-info mt-2">Сохранение...</div>
      <div v-if="saved" class="text-caption text-success mt-2">Сохранено ✓</div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { apiFetch } from '../api'

// D-05.2 frontend self-lockout — mirror the backend SELF_LOCKOUT_PROTECTED_KEYS
const SELF_LOCKOUT_PROTECTED_KEYS = ['admin.roles', 'staff']

const props = defineProps<{
  userId: number
  currentUserId: number   // D-05.2: id of the viewer/editor
  userRole: string
  orgAccessList: { org_id: number; org_name: string; role: string }[]
}>()

const tabs = ref<{ tab_key: string; title: string }[]>([])
const actions = ref<{ action_key: string; description: string }[]>([])
const roleDefaults = ref<Record<string, Set<string>>>({})
const overrides = ref<Record<string, boolean>>({})
const selectedOrgId = ref<number | null>(props.orgAccessList[0]?.org_id ?? null)
const activeTab = ref('tabs')
const loading = ref(false)
const saving = ref(false)
const saved = ref(false)

const orgOptions = computed(() =>
  props.orgAccessList.map(o => ({ value: o.org_id, label: o.org_name }))
)

const currentOrgRole = computed(() => {
  const rec = props.orgAccessList.find(o => o.org_id === selectedOrgId.value)
  return rec?.role ?? props.userRole
})

const hasOverrides = computed(() => Object.keys(overrides.value).length > 0)

function isGranted(key: string): boolean {
  if (key in overrides.value) return overrides.value[key]
  return roleDefaults.value[currentOrgRole.value]?.has(key) ?? false
}

function overrideState(key: string): string | null {
  if (!(key in overrides.value)) return null
  const roleHas = roleDefaults.value[currentOrgRole.value]?.has(key) ?? false
  // If override matches role default — no visual override chip needed
  return overrides.value[key] === roleHas ? null : (overrides.value[key] ? 'grant' : 'revoke')
}

// D-05.2: frontend self-lockout — if editing your own card, cannot toggle protected keys
function isLocked(key: string): boolean {
  return props.userId === props.currentUserId && SELF_LOCKOUT_PROTECTED_KEYS.includes(key)
}

function roleLabel(role: string): string {
  const labels: Record<string, string> = {
    account_owner: 'Владелец аккаунта',
    superadmin: 'Суперадмин',
    admin: 'Администратор',
    org_admin: 'Админ организации',
    manager: 'Менеджер',
    employee: 'Сотрудник',
  }
  return labels[role] ?? role
}

async function loadCatalogs() {
  loading.value = true
  try {
    const [tabList, actList, roleRows] = await Promise.all([
      apiFetch<any[]>('/permissions/tabs'),
      apiFetch<any[]>('/permissions/actions'),
      apiFetch<any[]>('/permissions/roles'),
    ])
    tabs.value = tabList
    actions.value = actList
    const defaults: Record<string, Set<string>> = {}
    for (const r of roleRows) {
      defaults[r.role_name] = new Set([...(r.tabs ?? []), ...(r.actions ?? [])])
    }
    roleDefaults.value = defaults
  } catch (e) {
    console.warn('[UserPermissionsSection] loadCatalogs failed', e)
  } finally {
    loading.value = false
  }
}

async function loadForOrg() {
  if (!selectedOrgId.value) return
  loading.value = true
  try {
    const list = await apiFetch<any[]>(
      `/permissions/users/${props.userId}/overrides?org_id=${selectedOrgId.value}`
    )
    const ov: Record<string, boolean> = {}
    for (const row of list) ov[row.key] = row.granted
    overrides.value = ov
  } catch (e) {
    console.warn('[UserPermissionsSection] loadForOrg failed', e)
    overrides.value = {}
  } finally {
    loading.value = false
  }
}

function onOrgChange() {
  overrides.value = {}
  loadForOrg()
}

// Debounced write buffer
const pending: Record<string, boolean> = {}
let timer: ReturnType<typeof setTimeout> | null = null

async function toggle(key: string, granted: boolean) {
  if (isLocked(key)) return  // defensive — disabled checkbox should already prevent this
  overrides.value = { ...overrides.value, [key]: granted }
  pending[key] = granted
  if (timer) clearTimeout(timer)
  timer = setTimeout(flush, 300)
}

async function flush() {
  if (!selectedOrgId.value) return
  const updates = Object.entries(pending).map(([key, granted]) => ({ key, granted }))
  for (const k of Object.keys(pending)) delete pending[k]
  if (updates.length === 0) return
  saving.value = true
  saved.value = false
  try {
    await apiFetch(`/permissions/users/${props.userId}/overrides?org_id=${selectedOrgId.value}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    })
    saved.value = true
    setTimeout(() => { saved.value = false }, 1500)
  } catch (e: any) {
    alert(`Не удалось сохранить: ${e?.message ?? e}`)
    await loadForOrg()
  } finally {
    saving.value = false
  }
}

async function removeOverride(key: string) {
  if (!selectedOrgId.value) return
  try {
    await apiFetch(
      `/permissions/users/${props.userId}/overrides/${encodeURIComponent(key)}?org_id=${selectedOrgId.value}`,
      { method: 'DELETE' }
    )
    const { [key]: _, ...rest } = overrides.value
    overrides.value = rest
  } catch (e: any) {
    alert(`Не удалось удалить override: ${e?.message ?? e}`)
  }
}

onMounted(async () => {
  await loadCatalogs()
  if (selectedOrgId.value) await loadForOrg()
})

// Re-fetch overrides when userId changes (dialog re-used for different users)
watch(() => props.userId, async () => {
  overrides.value = {}
  selectedOrgId.value = props.orgAccessList[0]?.org_id ?? null
  if (selectedOrgId.value) await loadForOrg()
})
</script>
