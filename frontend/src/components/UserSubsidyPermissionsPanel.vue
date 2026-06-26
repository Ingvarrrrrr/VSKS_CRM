<template>
  <div class="pa-2">
    <v-tabs v-model="activeTab" density="compact" class="mb-2">
      <v-tab value="tabs">Листы ({{ props.tabs.length }})</v-tab>
      <v-tab value="actions">Критичные действия ({{ props.actions.length }})</v-tab>
    </v-tabs>

    <v-window v-model="activeTab">
      <!-- Tabs (page visibility) -->
      <v-window-item value="tabs">
        <div v-if="loading" class="d-flex justify-center py-4">
          <v-progress-circular indeterminate size="24" />
        </div>
        <div v-else>
          <div
            v-for="t in props.tabs"
            :key="t.tab_key"
            class="d-flex align-center py-1"
          >
            <v-checkbox
              :model-value="isGranted(t.tab_key)"
              :label="t.title"
              density="compact"
              hide-details
              @update:model-value="(v) => toggle(t.tab_key, !!v)"
            />
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
            v-for="a in props.actions"
            :key="a.action_key"
            class="d-flex align-center py-1"
          >
            <v-checkbox
              :model-value="isGranted(a.action_key)"
              :label="a.description ?? a.action_key"
              density="compact"
              hide-details
              @update:model-value="(v) => toggle(a.action_key, !!v)"
            />
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { apiFetch } from '../api'

const props = defineProps<{
  userId: number
  subsidyId: number
  role: string
  tabs: { tab_key: string; title: string }[]
  actions: { action_key: string; description: string }[]
  roleDefaults: Record<string, Set<string>>
}>()

const overrides = ref<Record<string, boolean>>({})
const activeTab = ref('tabs')
const loading = ref(false)
const saving = ref(false)
const saved = ref(false)

function isGranted(key: string): boolean {
  if (key in overrides.value) return overrides.value[key]
  return props.roleDefaults[props.role]?.has(key) ?? false
}

function overrideState(key: string): string | null {
  if (!(key in overrides.value)) return null
  const roleHas = props.roleDefaults[props.role]?.has(key) ?? false
  return overrides.value[key] === roleHas ? null : (overrides.value[key] ? 'grant' : 'revoke')
}

async function loadOverrides() {
  loading.value = true
  try {
    const list = await apiFetch<{ key: string; granted: boolean }[]>(
      `/permissions/users/${props.userId}/subsidy-access/${props.subsidyId}/overrides`
    )
    const ov: Record<string, boolean> = {}
    for (const row of list) ov[row.key] = row.granted
    overrides.value = ov
  } catch (e) {
    console.warn('[UserSubsidyPermissionsPanel] loadOverrides failed', e)
    overrides.value = {}
  } finally {
    loading.value = false
  }
}

// Debounced write buffer
const pending: Record<string, boolean> = {}
let timer: ReturnType<typeof setTimeout> | null = null

function toggle(key: string, granted: boolean) {
  overrides.value = { ...overrides.value, [key]: granted }
  pending[key] = granted
  if (timer) clearTimeout(timer)
  timer = setTimeout(flush, 300)
}

async function flush() {
  const updates = Object.entries(pending).map(([key, granted]) => ({ key, granted }))
  for (const k of Object.keys(pending)) delete pending[k]
  if (updates.length === 0) return
  saving.value = true
  saved.value = false
  try {
    await apiFetch(
      `/permissions/users/${props.userId}/subsidy-access/${props.subsidyId}/overrides`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      }
    )
    saved.value = true
    setTimeout(() => { saved.value = false }, 1500)
  } catch (e: any) {
    alert(`Не удалось сохранить: ${e?.message ?? e}`)
    await loadOverrides()
  } finally {
    saving.value = false
  }
}

async function removeOverride(key: string) {
  try {
    await apiFetch(
      `/permissions/users/${props.userId}/subsidy-access/${props.subsidyId}/overrides/${encodeURIComponent(key)}`,
      { method: 'DELETE' }
    )
    const { [key]: _, ...rest } = overrides.value
    overrides.value = rest
  } catch (e: any) {
    alert(`Не удалось удалить override: ${e?.message ?? e}`)
  }
}

onMounted(() => {
  loadOverrides()
})

watch(
  () => [props.userId, props.subsidyId] as const,
  () => {
    overrides.value = {}
    loadOverrides()
  }
)
</script>
