<template>
  <!-- Владелец продукта, 2026-09-02: «мне ввело в заблуждение, что "Доступ ко
       всем организациям аккаунта" находится в одной рамке вместе с ВСКС» —
       переключатель читался как настройка ВЫБРАННОЙ организации. Вынесен в
       отдельную карточку НАД списком организаций, чтобы было однозначно видно:
       это настройка уровня АККАУНТА, не привязанная к организации ниже. -->
  <v-card variant="outlined" class="mt-4" color="primary">
    <v-card-title class="d-flex align-center pa-4 pb-2">
      <v-icon size="18" class="mr-2">mdi-account-key-outline</v-icon>
      <span>Доступ ко всем организациям аккаунта</span>
    </v-card-title>
    <v-card-text class="pa-4 pt-0">
      <v-switch
        :model-value="allOrgsAccessLocal"
        color="primary"
        density="compact"
        hide-details
        class="mb-1"
        label="Включить доступ ко всем организациям аккаунта"
        @update:model-value="(v) => onAllOrgsAccessChange(!!v)"
      />
      <div class="text-caption text-medium-emphasis mb-1">
        Это настройка уровня АККАУНТА целиком, а не организации, выбранной ниже.
        Роль сотрудника не меняется — расширяется только охват данных: он увидит
        закупки/субсидии/персонал всех организаций своего аккаунта.
      </div>
      <div v-if="allOrgsAccessLocal" class="text-caption" style="color:#e65100">
        <v-icon size="13" color="warning" class="mr-1">mdi-content-copy</v-icon>
        Доступ ко всем организациям включён — галочки вкладок и критичных действий
        ниже применяются <strong>сразу ко всем организациям охвата</strong>, а не
        только к выбранной в списке. Роль в каждой организации настраивается отдельно.
      </div>
      <div v-else class="text-caption text-medium-emphasis">
        Выключено — права по вкладкам и критичным действиям ниже личные для
        выбранной организации.
      </div>
      <div v-if="allOrgsAccessSaving" class="text-caption text-info mt-2">Сохранение...</div>
      <div v-if="allOrgsAccessSaved" class="text-caption text-success mt-2">Сохранено ✓</div>
    </v-card-text>
  </v-card>

  <v-card variant="outlined" class="mt-4">
    <v-card-title class="d-flex align-center pa-4">
      <span>Доступ в организации</span>
      <v-spacer />
      <v-chip
        v-if="hasOverrides"
        color="warning"
        size="small"
        prepend-icon="mdi-account-cog"
      >Индивидуально</v-chip>
      <v-chip v-else color="primary" size="small">{{ roleLabel(selectedRole || userRole) }}</v-chip>
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
        class="mb-1"
        hide-details
        @update:model-value="onOrgChange"
      />
      <div v-if="allOrgsAccessLocal" class="text-caption mb-3" style="color:#e65100">
        <v-icon size="13" color="warning" class="mr-1">mdi-eye-check-outline</v-icon>
        Доступ ко всем организациям включён — этот список нужен только чтобы
        настроить роль/вкладки/действия для конкретной организации, видимость данных он не ограничивает.
      </div>
      <div v-else class="mb-3" />

      <v-select
        v-model="selectedRole"
        :items="roleOptionsAvailable"
        item-title="label"
        item-value="value"
        label="Роль в этой организации"
        density="compact"
        variant="outlined"
        :disabled="isRoleChangeBlocked"
        hide-details
        class="mb-3"
        @update:model-value="onRoleChange"
      />
      <div v-if="manageBlockedReason" class="text-caption mb-2" style="color:#b71c1c">
        <v-icon size="13" color="error" class="mr-1">mdi-lock-outline</v-icon>
        {{ manageBlockedReason }}
      </div>

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
                :text="isLocked(t.tab_key) ? manageBlockedReason : ''"
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
                :closable="!isManageBlocked"
                @click:close="removeOverride(t.tab_key)"
              >+ добавлено</v-chip>
              <v-chip
                v-if="overrideState(t.tab_key) === 'revoke'"
                color="error"
                size="x-small"
                class="ml-2"
                :closable="!isManageBlocked"
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
                :text="isLocked(a.action_key) ? manageBlockedReason : ''"
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
                :closable="!isManageBlocked"
                @click:close="removeOverride(a.action_key)"
              >+ добавлено</v-chip>
              <v-chip
                v-if="overrideState(a.action_key) === 'revoke'"
                color="error"
                size="x-small"
                class="ml-2"
                :closable="!isManageBlocked"
                @click:close="removeOverride(a.action_key)"
              >− убрано</v-chip>
            </div>
          </div>
        </v-window-item>
      </v-window>

      <div v-if="saving" class="text-caption text-info mt-2">Сохранение...</div>
      <div v-if="saved" class="text-caption text-success mt-2">
        Сохранено ✓<span v-if="savedOrgCount > 1"> — применено сразу в {{ savedOrgCount }} организациях</span>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { apiFetch } from '../api'

// Владелец 2026-09-02: закрытие эскалации привилегий — org_admin мог сам себе
// назначать/снимать допуски и даже роль account_owner. Бэкенд теперь жёстко
// это блокирует (см. backend/app/auth/permissions.py assert_can_manage_user_access);
// здесь то же правило зеркалим на UI, чтобы переключатели были недоступны
// заранее, а не падали с ошибкой после клика.
// Лестница ролей — 1:1 с _ROLE_PRIORITY в backend/app/auth/permissions.py.
const ROLE_RANK: Record<string, number> = {
  superadmin: 6, account_owner: 5, admin: 4, org_admin: 3, manager: 2, employee: 1,
}

const props = defineProps<{
  userId: number
  currentUserId: number   // D-05.2: id of the viewer/editor
  userRole: string
  orgAccessList: { org_id: number; org_name: string; role: string }[]
  allOrgsAccess?: boolean  // доступ ко всем организациям аккаунта (роль не меняется)
}>()

const emit = defineEmits<{
  (e: 'update:allOrgsAccess', value: boolean): void
}>()

const tabs = ref<{ tab_key: string; title: string }[]>([])
const actions = ref<{ action_key: string; description: string }[]>([])
const roleDefaults = ref<Record<string, Set<string>>>({})
const overrides = ref<Record<string, boolean>>({})
const orgRoles = ref<Record<number, string | null>>({})
// Роль ТЕКУЩЕГО (редактирующего) пользователя per-org — нужна, чтобы сравнить
// его ранг с рангом редактируемого и вперёд отключить переключатели, если
// бэкенд всё равно откажет (assert_can_manage_user_access).
const currentUserOrgRoles = ref<Record<number, string | null>>({})
const currentUserGlobalRole = localStorage.getItem('user_role') || ''
const selectedOrgId = ref<number | null>(props.orgAccessList[0]?.org_id ?? null)
const selectedRole = ref<string>('')
const activeTab = ref('tabs')
const loading = ref(false)
const saving = ref(false)
const saved = ref(false)

const roleOptions = [
  { value: 'account_owner', label: 'Владелец аккаунта' },
  { value: 'admin',         label: 'Администратор' },
  { value: 'org_admin',     label: 'Админ организации' },
  { value: 'manager',       label: 'Менеджер' },
  { value: 'employee',      label: 'Сотрудник' },
]

// Владелец 2026-09-02, п.3: роль «Владелец аккаунта» вправе выдавать только
// суперадмин или действующий владелец — не показываем опцию остальным,
// зеркалит backend-проверку в PATCH /users/{id}/role.
const roleOptionsAvailable = computed(() => {
  if (['superadmin', 'account_owner'].includes(currentUserGlobalRole)) return roleOptions
  return roleOptions.filter(o => o.value !== 'account_owner')
})

const isSelfEdit = computed(() => props.userId === props.currentUserId)

// Эффективная роль редактирующего для выбранной организации: сначала
// per-org (UOA), иначе глобальная — то же правило, что и для currentOrgRole
// (target) ниже, и что и в backend _resolve_role_for_rank.
const currentUserEffectiveRole = computed(() => {
  if (selectedOrgId.value != null && currentUserOrgRoles.value[selectedOrgId.value] != null) {
    return currentUserOrgRoles.value[selectedOrgId.value] as string
  }
  return currentUserGlobalRole
})

const isHierarchyBlocked = computed(() => {
  if (isSelfEdit.value) return false
  if (currentUserEffectiveRole.value === 'superadmin') return false
  const actorRank = ROLE_RANK[currentUserEffectiveRole.value] ?? 0
  const targetRank = ROLE_RANK[currentOrgRole.value] ?? 0
  return actorRank <= targetRank
})

// Общий гейт: свои допуски не трогает никто (кроме суперадмина), чужие —
// только если ты строго выше по лестнице ролей. Зеркалит
// assert_can_manage_user_access на бэкенде.
const isManageBlocked = computed(() => isSelfEdit.value || isHierarchyBlocked.value)

const manageBlockedReason = computed(() => {
  if (currentUserGlobalRole === 'superadmin') return ''
  if (isSelfEdit.value) {
    return 'Нельзя менять свои собственные допуски — попросите хозяина аккаунта (владельца) или суперадмина.'
  }
  if (isHierarchyBlocked.value) {
    return `Недостаточно прав: настраивать допуски пользователя с ролью «${roleLabel(currentOrgRole.value)}» может только хозяин аккаунта (владелец) или суперадмин.`
  }
  return ''
})

const isRoleChangeBlocked = computed(() => isManageBlocked.value)

async function loadCurrentUserOrgRoles() {
  try {
    const rows = await apiFetch<{ org_id: number; role: string | null }[]>(
      `/permissions/users/${props.currentUserId}/org-roles`
    )
    const map: Record<number, string | null> = {}
    for (const r of rows) map[r.org_id] = r.role
    currentUserOrgRoles.value = map
  } catch (e) {
    console.warn('[UserPermissionsSection] loadCurrentUserOrgRoles failed', e)
  }
}

// Владелец, 2026-09-01: «никакой в пизду организации и номера — у каждой
// организации есть название». Раньше при пустом org_name в переданном списке
// подставлялся `Организация #<id>`. Теперь имя резолвится по каталогу
// организаций (тот же общедоступный справочник, что и остальные орг-пикеры
// в проекте — GET /organizations/, доступен любому залогиненному), НЕЗАВИСИМО
// от того, что пришло в orgAccessList — компонент не полагается на чужой
// (возможно урезанный/устаревший) список. Если организации нет и в каталоге
// (недоступна текущему пользователю) — пункт не показываем вовсе, а не рисуем
// голый номер.
const orgCatalog = ref<{ id: number; name: string }[]>([])
async function loadOrgCatalog() {
  try {
    orgCatalog.value = await apiFetch<{ id: number; name: string }[]>('/organizations/')
  } catch (e) {
    console.warn('[UserPermissionsSection] loadOrgCatalog failed', e)
  }
}

const orgOptions = computed(() => {
  const catalog = new Map(orgCatalog.value.map(o => [o.id, o.name]))
  const options: { value: number; label: string }[] = []
  for (const o of props.orgAccessList) {
    const name = catalog.get(o.org_id) || (o.org_name && o.org_name.trim() ? o.org_name : '')
    if (!name) continue  // организация без резолвимого имени — не показываем
    options.push({ value: o.org_id, label: name })
  }
  return options
})

const allOrgsAccessLocal = ref<boolean>(!!props.allOrgsAccess)
const allOrgsAccessSaving = ref(false)
const allOrgsAccessSaved = ref(false)

watch(() => props.allOrgsAccess, (v) => { allOrgsAccessLocal.value = !!v })

async function onAllOrgsAccessChange(newVal: boolean) {
  const prev = allOrgsAccessLocal.value
  allOrgsAccessLocal.value = newVal
  allOrgsAccessSaving.value = true
  allOrgsAccessSaved.value = false
  try {
    await apiFetch(`/users/${props.userId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ all_orgs_access: newVal }),
    })
    emit('update:allOrgsAccess', newVal)
    allOrgsAccessSaved.value = true
    setTimeout(() => { allOrgsAccessSaved.value = false }, 1500)
  } catch (e: any) {
    allOrgsAccessLocal.value = prev
    alert(`Не удалось изменить доступ ко всем организациям: ${e?.payload?.detail || e?.payload?.message || e?.message || e}`)
  } finally {
    allOrgsAccessSaving.value = false
  }
}

const currentOrgRole = computed(() => {
  // Prefer the per-org role from the dedicated endpoint (fresh source of truth)
  if (selectedOrgId.value != null && orgRoles.value[selectedOrgId.value] != null) {
    return orgRoles.value[selectedOrgId.value] as string
  }
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

// Владелец 2026-09-02: раньше блокировались только SELF_LOCKOUT_PROTECTED_KEYS
// у себя. Теперь бэкенд запрещает менять СВОИ допуски целиком и допуски
// равных/старших по роли — зеркалим isManageBlocked на каждый чекбокс.
function isLocked(_key: string): boolean {
  return isManageBlocked.value
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

async function loadOrgRoles() {
  try {
    const rows = await apiFetch<{ org_id: number; role: string | null }[]>(
      `/permissions/users/${props.userId}/org-roles`
    )
    const map: Record<number, string | null> = {}
    for (const r of rows) map[r.org_id] = r.role
    orgRoles.value = map
  } catch (e) {
    console.warn('[UserPermissionsSection] loadOrgRoles failed', e)
  }
}

async function onRoleChange(newRole: string) {
  if (!selectedOrgId.value) return
  if (isManageBlocked.value) return  // defensive — select is disabled when blocked
  saving.value = true
  saved.value = false
  try {
    await apiFetch(
      `/permissions/users/${props.userId}/role?org_id=${selectedOrgId.value}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: newRole }),
      }
    )
    orgRoles.value = { ...orgRoles.value, [selectedOrgId.value]: newRole }
    saved.value = true
    setTimeout(() => { saved.value = false }, 1500)
    // Effective base changed — re-fetch overrides so chips reflect new defaults
    await loadForOrg()
  } catch (e: any) {
    alert(`Не удалось изменить роль: ${e?.message ?? e}`)
    // Revert selector
    selectedRole.value =
      (selectedOrgId.value != null ? orgRoles.value[selectedOrgId.value] : null) ??
      props.userRole
  } finally {
    saving.value = false
  }
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

const savedOrgCount = ref(0)

async function flush() {
  if (!selectedOrgId.value) return
  const updates = Object.entries(pending).map(([key, granted]) => ({ key, granted }))
  for (const k of Object.keys(pending)) delete pending[k]
  if (updates.length === 0) return
  saving.value = true
  saved.value = false
  try {
    const res = await apiFetch<{ applied_org_ids?: number[] }>(
      `/permissions/users/${props.userId}/overrides?org_id=${selectedOrgId.value}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      }
    )
    savedOrgCount.value = res?.applied_org_ids?.length ?? 1
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
  if (isManageBlocked.value) return  // defensive — chip's close button should already be hidden
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
  loadOrgCatalog()
  loadCurrentUserOrgRoles()
  await loadCatalogs()
  await loadOrgRoles()
  if (selectedOrgId.value) await loadForOrg()
})

// Re-fetch overrides when userId changes (dialog re-used for different users)
watch(() => props.userId, async () => {
  overrides.value = {}
  orgRoles.value = {}
  selectedOrgId.value = props.orgAccessList[0]?.org_id ?? null
  await loadOrgRoles()
  if (selectedOrgId.value) await loadForOrg()
})

// Владелец, 2026-09-01: баг «голый id 28 вместо названия организации» —
// StaffView грузит orgAccessList для нового сотрудника АСИНХРОННО и позже,
// чем меняется userId. Раньше selectedOrgId брался ОДИН РАЗ из userId-watcher
// (см. выше) на момент, когда orgAccessList ещё принадлежал ПРЕДЫДУЩЕМУ
// сотруднику, и больше никогда не пересчитывался — когда список наконец
// приходил, org предыдущего сотрудника (напр. 28 «ХРО ВСКС») в нём не было,
// и v-select рисовал сырое числовое значение вместо названия.
// Фикс: следим за самим orgAccessList и, если текущий выбор в нём больше не
// значится (или выбора ещё нет вовсе), переключаемся на первую доступную
// организацию нового списка (или на null, если организаций нет).
watch(
  () => props.orgAccessList,
  (list) => {
    const ids = list.map(o => o.org_id)
    const stillValid = selectedOrgId.value != null && ids.includes(selectedOrgId.value)
    if (stillValid) return
    const next = ids[0] ?? null
    if (next === selectedOrgId.value) return
    selectedOrgId.value = next
    overrides.value = {}
    if (next) loadForOrg()
  },
  { deep: true }
)

// Keep selectedRole in sync with the cached per-org role for the active org
watch(
  [orgRoles, selectedOrgId],
  () => {
    if (selectedOrgId.value == null) {
      selectedRole.value = ''
      return
    }
    selectedRole.value =
      orgRoles.value[selectedOrgId.value] ??
      (props.orgAccessList.find(o => o.org_id === selectedOrgId.value)?.role ?? props.userRole)
  },
  { immediate: true, deep: true }
)
</script>
