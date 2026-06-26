<template>
  <v-card variant="outlined" class="mt-4">
    <v-card-title class="pa-4">
      <span>Доступ к субсидиям</span>
    </v-card-title>

    <v-card-text class="pa-4 pt-0">
      <!-- Add new grant row -->
      <div class="d-flex align-center gap-2 mb-3">
        <v-autocomplete
          v-model="newSubsidyId"
          :items="availableSubsidies"
          item-title="title"
          item-value="value"
          label="Добавить субсидию"
          density="compact"
          variant="outlined"
          hide-details
          clearable
          class="flex-grow-1"
        />
        <v-select
          v-model="newRole"
          :items="roleOptions"
          item-title="label"
          item-value="value"
          label="Роль"
          density="compact"
          variant="outlined"
          hide-details
          style="max-width: 160px"
        />
        <v-btn
          color="primary"
          density="compact"
          variant="tonal"
          :disabled="!newSubsidyId || saving"
          @click="addGrant"
        >Добавить</v-btn>
      </div>

      <!-- Current grants list -->
      <div v-if="grants.length === 0" class="text-caption text-medium-emphasis py-2">
        Субсидии не назначены
      </div>

      <!-- Each grant wrapped in a div to contain its optional permissions panel -->
      <div
        v-for="grant in grants"
        :key="grant.subsidy_id"
      >
        <!-- Grant row -->
        <div class="d-flex align-center py-1 gap-2">
          <span class="flex-grow-1 text-subtitle-1 font-weight-bold text-primary">{{ grant.subsidy_name }}</span>
          <v-select
            :model-value="grant.role"
            :items="roleOptions"
            item-title="label"
            item-value="value"
            density="compact"
            variant="outlined"
            hide-details
            style="max-width: 160px"
            @update:model-value="(v: any) => changeRole(grant, v)"
          />
          <v-tooltip text="Настройки доступа" location="top">
            <template #activator="{ props: tipProps }">
              <v-btn
                v-bind="tipProps"
                :icon="expanded.has(grant.subsidy_id) ? 'mdi-chevron-up' : 'mdi-chevron-down'"
                density="compact"
                variant="text"
                @click="toggleExpand(grant.subsidy_id)"
              />
            </template>
          </v-tooltip>
          <v-btn
            icon="mdi-delete-outline"
            color="error"
            density="compact"
            variant="text"
            @click="removeGrant(grant.subsidy_id)"
          />
        </div>

        <!-- Expandable permissions panel -->
        <UserSubsidyPermissionsPanel
          v-if="expanded.has(grant.subsidy_id)"
          :user-id="userId"
          :subsidy-id="grant.subsidy_id"
          :role="grant.role"
          :tabs="tabs"
          :actions="actions"
          :role-defaults="roleDefaults"
        />
      </div>

      <div v-if="saving" class="text-caption text-info mt-2">Сохранение...</div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { apiFetch } from '../api'
import UserSubsidyPermissionsPanel from './UserSubsidyPermissionsPanel.vue'

const props = defineProps<{
  userId: number
  userRole: string
}>()

interface SubsidyItem {
  id: number
  name: string
}

interface Grant {
  subsidy_id: number
  subsidy_name: string
  role: string
}

const subsidies = ref<SubsidyItem[]>([])
const grants = ref<Grant[]>([])
const newSubsidyId = ref<number | null>(null)
const newRole = ref<string>('employee')
const saving = ref(false)

// Catalog data loaded once for all child panels
const tabs = ref<{ tab_key: string; title: string }[]>([])
const actions = ref<{ action_key: string; description: string }[]>([])
const roleDefaults = ref<Record<string, Set<string>>>({})

// Expand state per subsidy_id
const expanded = ref<Set<number>>(new Set())

function toggleExpand(subsidyId: number) {
  const next = new Set(expanded.value)
  if (next.has(subsidyId)) {
    next.delete(subsidyId)
  } else {
    next.add(subsidyId)
  }
  expanded.value = next
}

const roleOptions = [
  { value: 'org_admin', label: 'Админ организации' },
  { value: 'manager',   label: 'Менеджер' },
  { value: 'employee',  label: 'Сотрудник' },
]

const availableSubsidies = computed(() => {
  const grantedIds = new Set(grants.value.map((g: Grant) => g.subsidy_id))
  return subsidies.value
    .filter((s: SubsidyItem) => !grantedIds.has(s.id))
    .map((s: SubsidyItem) => ({ title: s.name, value: s.id }))
})

async function loadSubsidies() {
  try {
    const data = await apiFetch<any[]>('/subsidies/')
    subsidies.value = data.map((s: any) => ({ id: s.id, name: s.name }))
  } catch (e) {
    console.warn('[UserSubsidyAccessSection] loadSubsidies failed', e)
  }
}

async function loadGrants() {
  try {
    const data = await apiFetch<any[]>(`/permissions/users/${props.userId}/subsidy-access`)
    grants.value = data
    // Раскрываем панель доступа для каждой субсидии сразу — как на референсе (орг-панель видна без клика).
    expanded.value = new Set(data.map((g: any) => g.subsidy_id))
  } catch (e) {
    console.warn('[UserSubsidyAccessSection] loadGrants failed', e)
    grants.value = []
  }
}

async function loadCatalogs() {
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
    console.warn('[UserSubsidyAccessSection] loadCatalogs failed', e)
  }
}

async function addGrant() {
  if (!newSubsidyId.value) return
  saving.value = true
  try {
    await apiFetch(`/permissions/users/${props.userId}/subsidy-access`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subsidy_id: newSubsidyId.value, role: newRole.value }),
    })
    newSubsidyId.value = null
    await loadGrants()
  } catch (e) {
    console.warn('[UserSubsidyAccessSection] addGrant failed', e)
  } finally {
    saving.value = false
  }
}

async function changeRole(grant: Grant, newRoleValue: any) {
  saving.value = true
  try {
    await apiFetch(`/permissions/users/${props.userId}/subsidy-access`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subsidy_id: grant.subsidy_id, role: newRoleValue }),
    })
    await loadGrants()
  } catch (e) {
    console.warn('[UserSubsidyAccessSection] changeRole failed', e)
  } finally {
    saving.value = false
  }
}

async function removeGrant(subsidyId: number) {
  // Collapse panel if expanded before removing
  if (expanded.value.has(subsidyId)) {
    const next = new Set(expanded.value)
    next.delete(subsidyId)
    expanded.value = next
  }
  try {
    await apiFetch(`/permissions/users/${props.userId}/subsidy-access/${subsidyId}`, {
      method: 'DELETE',
    })
    await loadGrants()
  } catch (e) {
    console.warn('[UserSubsidyAccessSection] removeGrant failed', e)
  }
}

onMounted(async () => {
  await Promise.all([loadSubsidies(), loadGrants(), loadCatalogs()])
})

watch(() => props.userId, async () => {
  grants.value = []
  expanded.value = new Set()
  await Promise.all([loadSubsidies(), loadGrants()])
})
</script>
