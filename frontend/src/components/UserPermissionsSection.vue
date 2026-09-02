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
      <!-- Владелец, 2026-09-02: бэкенд перестал молча применять галочки ко всем
           организациям — PUT /users/{id}/overrides теперь по умолчанию
           (apply_to_all=false) задевает ТОЛЬКО выбранную организацию, даже при
           включённом доступе ко всем. Старый текст ниже утверждал обратное —
           это стало ложью, переписан честно; применение ко всем — теперь
           отдельное явное действие (галочка «Применить ко всем организациям»
           рядом с сохранением). -->
      <div v-if="allOrgsAccessLocal" class="text-caption" style="color:#e65100">
        <v-icon size="13" color="warning" class="mr-1">mdi-content-copy</v-icon>
        Доступ ко всем организациям включён, но вкладки и действия ниже по
        умолчанию сохраняются <strong>только для выбранной организации</strong>,
        даже при этом включённом доступе. Чтобы применить настройки сразу ко
        всем организациям охвата — включите галочку «Применить ко всем
        организациям» рядом с сохранением. Роль в каждой организации
        настраивается отдельно.
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

      <!-- Владелец, 2026-09-02: раньше вкладки и действия рисовались двумя
           НЕСВЯЗАННЫМИ списками (27 вкладок отдельно, 28 действий отдельно) —
           сопоставить глазами, какое действие относится к какому разделу, было
           невозможно. Теперь одна таблица по функциональным областям: строка —
           область (title вкладки — с сервера, не хардкод), колонка «Только
           просмотр» — галочка вкладки, колонка «Редактирование» — галочки
           действий этой области. Область для действия определяется СТРУКТУРНО
           по префиксу action_key (см. resolveTabKeyForAction в <script>) —
           новый action_key с неизвестным префиксом не потеряется молча, а
           уйдёт в строку «Прочее» в конце таблицы. -->
      <div v-if="loading" class="d-flex justify-center py-4">
        <v-progress-circular indeterminate size="24" />
      </div>
      <div v-else style="overflow-x:auto">
        <v-table density="compact" class="permissions-table">
          <thead>
            <tr>
              <th style="min-width:200px">Область</th>
              <th style="min-width:220px">Только просмотр</th>
              <th style="min-width:260px">Редактирование</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="g in permGroups" :key="g.key">
              <td class="font-weight-medium">{{ g.title }}</td>
              <td>
                <div v-if="g.tab" class="d-flex align-center">
                  <v-tooltip
                    :text="isLocked(g.tab.tab_key) ? manageBlockedReason : ''"
                    location="top"
                    :disabled="!isLocked(g.tab.tab_key)"
                  >
                    <template #activator="{ props: tipProps }">
                      <div v-bind="tipProps" style="display:inline-flex;align-items:center;">
                        <v-checkbox
                          :model-value="isGranted(g.tab.tab_key)"
                          :disabled="isLocked(g.tab.tab_key)"
                          density="compact"
                          hide-details
                          @update:model-value="(v) => toggle(g.tab!.tab_key, !!v)"
                        />
                      </div>
                    </template>
                  </v-tooltip>
                  <v-chip
                    v-if="overrideState(g.tab.tab_key) === 'grant'"
                    color="success"
                    size="x-small"
                    class="ml-1"
                    :closable="!isManageBlocked"
                    @click:close="removeOverride(g.tab!.tab_key)"
                  >+</v-chip>
                  <v-chip
                    v-if="overrideState(g.tab.tab_key) === 'revoke'"
                    color="error"
                    size="x-small"
                    class="ml-1"
                    :closable="!isManageBlocked"
                    @click:close="removeOverride(g.tab!.tab_key)"
                  >−</v-chip>
                </div>
                <span v-else class="text-medium-emphasis">—</span>
              </td>
              <td class="py-2">
                <template v-if="g.groupActions.length">
                  <div
                    v-for="a in g.groupActions"
                    :key="a.action_key"
                    class="d-flex align-center"
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
                      class="ml-1"
                      :closable="!isManageBlocked"
                      @click:close="removeOverride(a.action_key)"
                    >+</v-chip>
                    <v-chip
                      v-if="overrideState(a.action_key) === 'revoke'"
                      color="error"
                      size="x-small"
                      class="ml-1"
                      :closable="!isManageBlocked"
                      @click:close="removeOverride(a.action_key)"
                    >−</v-chip>
                  </div>
                </template>
                <span v-else class="text-medium-emphasis">—</span>
              </td>
            </tr>
          </tbody>
        </v-table>
        <div class="text-caption text-medium-emphasis mt-1">
          Вкладок: {{ tabs.length }} · Действий: {{ actions.length }} — все учтены в таблице выше.
        </div>
      </div>

      <!-- Владелец, 2026-09-02: явное применение ко всем организациям вместо
           неявного (было: включённый «Доступ ко всем организациям» тихо
           расширял охват PUT-запроса). Бэкенд: PUT /users/{id}/overrides
           принимает apply_to_all (default false). -->
      <v-divider class="my-3" />
      <v-checkbox
        v-model="applyToAllOrgs"
        color="warning"
        density="compact"
        hide-details
        class="mb-1"
      >
        <template #label>
          <span class="text-body-2">Применить ко всем организациям</span>
        </template>
      </v-checkbox>
      <div class="text-caption text-medium-emphasis mb-2">
        По умолчанию изменения сохраняются только для организации
        «{{ selectedOrgLabel }}». Включите галочку, чтобы следующее изменение
        применилось сразу ко всем организациям охвата.
      </div>

      <div v-if="saving" class="text-caption text-info mt-2">Сохранение...</div>
      <div v-if="saved" class="text-caption text-success mt-2">
        Сохранено ✓ — применено в {{ savedOrgCount }} {{ savedOrgCount === 1 ? 'организации' : 'организациях' }}
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
const loading = ref(false)
const saving = ref(false)
const saved = ref(false)
// Владелец, 2026-09-02: явное применение изменений ко всем организациям
// охвата — по умолчанию выключено, PUT /overrides задевает только выбранную
// организацию (apply_to_all=false на бэкенде).
const applyToAllOrgs = ref(false)

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

// Владелец, 2026-09-02: подпись выбранной организации для текста рядом с
// галочкой «Применить ко всем организациям» (задача 2).
const selectedOrgLabel = computed(() =>
  orgOptions.value.find(o => o.value === selectedOrgId.value)?.label ?? ''
)

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

// ─────────────────────────────────────────────────────────────────────────
// Владелец, 2026-09-02, задача 1: «сопоставить два несвязанных списка (27
// вкладок / 28 действий) глазами невозможно». Группируем действия по вкладке
// СТРУКТУРНО по префиксу action_key (часть до первой точки), а не
// перечислением каждого из 28 ключей вручную — иначе новый action_key в
// будущем потеряется молча. Порядок разрешения:
//   1) точное совпадение префикса с tab_key,
//   2) простые singular/plural вариации (vehicle → vehicles),
//   3) явные семантические алиасы для неочевидных префиксов, где префикс не
//      совпадает с tab_key ни напрямую, ни по множественному числу
//      (subsidy→subsidies, wish→wishes, purchase_files→purchases,
//      feo_category/feo_budget→feo_categories, user→staff,
//      report_config→reports, plan_excess→plan, publication→purchases,
//      payment→payment_registry).
// Всё, что не нашло вкладку (напр. documents.view_all_in_org — намеренно
// неоднозначен, может относиться и к закупкам, и к договорам) — уходит в
// строку «Прочее» в конце таблицы, а не пропадает с экрана.
const PREFIX_ALIASES: Record<string, string> = {
  vehicle: 'vehicles',
  purchase: 'purchases',
  purchase_files: 'purchases',
  contract: 'contracts',
  subsidy: 'subsidies',
  wish: 'wishes',
  feo_category: 'feo_categories',
  feo_budget: 'feo_categories',
  user: 'staff',
  report_config: 'reports',
  plan_excess: 'plan',
  publication: 'purchases',
  payment: 'payment_registry',
}

function actionPrefix(actionKey: string): string {
  const idx = actionKey.indexOf('.')
  return idx === -1 ? actionKey : actionKey.slice(0, idx)
}

function resolveTabKeyForAction(actionKey: string, tabKeySet: Set<string>): string | null {
  const prefix = actionPrefix(actionKey)
  if (tabKeySet.has(prefix)) return prefix
  if (tabKeySet.has(prefix + 's')) return prefix + 's'
  if (prefix.endsWith('s') && tabKeySet.has(prefix.slice(0, -1))) return prefix.slice(0, -1)
  const alias = PREFIX_ALIASES[prefix]
  if (alias && tabKeySet.has(alias)) return alias
  return null
}

interface PermGroup {
  key: string
  title: string
  tab: { tab_key: string; title: string } | null
  groupActions: { action_key: string; description: string }[]
}

const OTHER_GROUP_KEY = '__other__'

// Каждая вкладка — своя строка (даже без действий, колонка «Редактирование»
// будет пустой — так задумано). Действия без совпадения уходят в «Прочее».
const permGroups = computed<PermGroup[]>(() => {
  const tabKeySet = new Set(tabs.value.map(t => t.tab_key))
  const actionsByTab = new Map<string, { action_key: string; description: string }[]>()
  const otherActions: { action_key: string; description: string }[] = []
  for (const a of actions.value) {
    const tabKey = resolveTabKeyForAction(a.action_key, tabKeySet)
    if (tabKey) {
      if (!actionsByTab.has(tabKey)) actionsByTab.set(tabKey, [])
      actionsByTab.get(tabKey)!.push(a)
    } else {
      otherActions.push(a)
    }
  }
  const groups: PermGroup[] = tabs.value.map(t => ({
    key: t.tab_key,
    title: t.title,
    tab: t,
    groupActions: actionsByTab.get(t.tab_key) ?? [],
  }))
  if (otherActions.length > 0) {
    groups.push({ key: OTHER_GROUP_KEY, title: 'Прочее', tab: null, groupActions: otherActions })
  }
  return groups
})
// ─────────────────────────────────────────────────────────────────────────

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
  // Владелец, 2026-09-02: «применить ко всем» — намеренно НЕ переживает смену
  // выбранной организации, чтобы случайно не разнести правку на чужой охват.
  applyToAllOrgs.value = false
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
    // Владелец, 2026-09-02, задача 2: apply_to_all теперь ЯВНЫЙ выбор
    // пользователя, а не побочный эффект включённого «доступа ко всем
    // организациям». По умолчанию false — бэкенд задевает только org_id.
    const applyParam = applyToAllOrgs.value ? '&apply_to_all=true' : ''
    const res = await apiFetch<{ applied_org_ids?: number[] }>(
      `/permissions/users/${props.userId}/overrides?org_id=${selectedOrgId.value}${applyParam}`,
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
  applyToAllOrgs.value = false  // не переносим «применить ко всем» на другого пользователя
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
