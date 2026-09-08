<template>
  <!-- ── Members (co-editors) Dialog ── -->
  <v-dialog v-model="visible" max-width="520" scrollable :fullscreen="mobile">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-account-group" color="deep-purple" class="mr-2" />
        Участники: {{ membersSubsidy?.name }}
        <v-chip class="ml-2" size="x-small" variant="tonal">{{ membersList.length }}</v-chip>
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="visible = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-4">
        <v-autocomplete
          v-if="canManageMembers"
          v-model="memberToAdd"
          :items="memberUsersList"
          item-title="full_name"
          item-value="id"
          label="Добавить участника"
          variant="outlined"
          density="compact"
          clearable
          hide-details
          :loading="addingMember"
          class="mb-3"
          @update:model-value="(val) => { if (val) addSubsidyMember(val) }"
        />
        <div v-else class="text-caption text-medium-emphasis mb-3">
          Добавлять/удалять участников может автор субсидии или сотрудник с правом «Редактирование субсидий».
        </div>
        <div v-if="loadingMembers" class="d-flex justify-center py-4">
          <v-progress-circular indeterminate color="primary" size="28" />
        </div>
        <div v-else-if="!membersList.length" class="text-caption text-medium-emphasis">Пока нет участников.</div>
        <div v-else class="d-flex flex-wrap" style="gap:8px">
          <v-chip
            v-for="m in membersList"
            :key="m.user_id"
            :closable="canManageMembers"
            @click:close="removeSubsidyMember(m.user_id)"
          >
            {{ m.full_name || m.username || '—' }}
          </v-chip>
        </div>
      </v-card-text>
      <v-divider />
      <v-card-actions class="px-4 py-3">
        <v-spacer />
        <v-btn variant="text" @click="visible = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import type { SubsidyMember, SubsidyRow } from '@/composables/subsidies/types'

const visible = defineModel<boolean>({ default: false })

const { mobile } = useDisplay()
const toast = useToast()
function showSnack(text: string, color: ToastType = 'success', opts?: { actionText?: string; onAction?: () => void; duration?: number }) {
  toast.addToast(text, color, opts)
}
const authStore = useAuthStore()
const currentUserId = Number(localStorage.getItem('user_id') || '0')

const membersSubsidy = ref<SubsidyRow | null>(null)
const membersList = ref<SubsidyMember[]>([])
const loadingMembers = ref(false)
const addingMember = ref(false)
const memberToAdd = ref<number | null>(null)
const memberUsersList = ref<Array<{ id: number; full_name: string }>>([])

// Тот же гейт, что на бэкенде (_can_manage_subsidy_members): автор субсидии
// или обладатель subsidy.edit. hasAction() читает /users/me permissions.
const canManageMembers = computed(() => {
  const s = membersSubsidy.value
  if (!s) return false
  if (authStore.hasAction('subsidy.edit')) return true
  return s.created_by != null && s.created_by === currentUserId
})

let _memberUsersSubsidyId: number | null = null
async function loadMemberUsers(sid: number) {
  if (memberUsersList.value.length && _memberUsersSubsidyId === sid) return
  try {
    memberUsersList.value = await apiFetch<any[]>(`/users/?subsidy_id=${sid}`)
    _memberUsersSubsidyId = sid
  } catch { memberUsersList.value = [] }
}

async function open(s: SubsidyRow) {
  membersSubsidy.value = s
  visible.value = true
  loadingMembers.value = true
  try {
    membersList.value = await apiFetch<SubsidyMember[]>(`/subsidies/${s.id}/members`)
  } catch (e: any) {
    showSnack(e.detail || 'Ошибка загрузки участников', 'error')
  } finally {
    loadingMembers.value = false
  }
  loadMemberUsers(s.id)
}

async function addSubsidyMember(userId: number | null) {
  if (!userId || !membersSubsidy.value) { memberToAdd.value = null; return }
  if (membersList.value.some((m: SubsidyMember) => m.user_id === userId)) { memberToAdd.value = null; return }
  addingMember.value = true
  try {
    const created = await apiFetch<SubsidyMember>(`/subsidies/${membersSubsidy.value.id}/members`, {
      method: 'POST', body: JSON.stringify({ user_id: userId }),
    })
    membersList.value.push(created)
    showSnack('Участник добавлен')
  } catch (e: any) {
    showSnack(e.detail || 'Ошибка добавления участника', 'error')
  } finally {
    addingMember.value = false
    memberToAdd.value = null
  }
}

async function removeSubsidyMember(userId: number) {
  if (!membersSubsidy.value) return
  try {
    await apiFetch(`/subsidies/${membersSubsidy.value.id}/members/${userId}`, { method: 'DELETE' })
    membersList.value = membersList.value.filter((m: SubsidyMember) => m.user_id !== userId)
    showSnack('Участник удалён', 'warning')
  } catch (e: any) {
    showSnack(e.detail || 'Ошибка удаления участника', 'error')
  }
}

defineExpose({ open })
</script>

<style scoped>
/* .dialog-card/.dialog-title — было в <style scoped> SubsidiesView.vue, пока
   диалог был её частью; вынесено вместе с диалогом (волна 5c) — иначе scoped CSS
   другого файла эти классы не достаёт (проверено на ContractorEditDialog.vue —
   тот же паттерн: каждый диалог держит эти два правила у себя). */
.dialog-card {}
.dialog-title {
  display: flex; align-items: center;
  font-size: 16px !important; font-weight: 600 !important;
  padding: 16px 20px !important;
}
</style>
