<template>
  <v-card v-if="visible" variant="outlined" class="mb-4" style="border-color:#059669">
    <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-3 d-flex align-center justify-space-between">
      <span class="d-flex align-center gap-2">
        <v-icon icon="mdi-check-decagram" color="green-darken-2" size="20" />
        Согласование
      </span>
      <div class="d-flex align-center ga-2">
        <v-chip v-if="approvalStatus" :color="APPROVAL_STATUS_COLOR[approvalStatus]" size="small" variant="tonal">
          {{ APPROVAL_STATUS_LABEL[approvalStatus] }}
        </v-chip>
        <v-chip v-if="approvals.length" size="small" variant="outlined">
          {{ approvals.filter(a => a.status === 'approved').length }}/{{ approvals.length }}
        </v-chip>
        <v-btn v-if="!approvalStatus && canStart" color="green-darken-2" variant="tonal" size="small"
          prepend-icon="mdi-play-circle-outline" :loading="startingApproval" @click="startApprovalProcess">
          Запустить согласование
        </v-btn>
        <v-btn v-if="approvalStatus === 'rejected' && isAdmin" color="warning" variant="tonal" size="small"
          prepend-icon="mdi-refresh" @click="resetApproval">
          Перезапустить
        </v-btn>
      </div>
    </v-card-title>
    <v-card-text class="px-4 pb-3">
      <v-timeline v-if="approvals.length" density="compact" side="end">
        <v-timeline-item v-for="a in approvals" :key="a.id"
          :dot-color="approvalDotColor(a.status)"
          :icon="approvalIcon(a.status)" size="small">
          <div class="d-flex align-center justify-space-between flex-wrap ga-2">
            <div>
              <div class="font-weight-medium">{{ a.approver_full_name }}</div>
              <div class="text-caption text-medium-emphasis">{{ a.role_name }}</div>
              <div v-if="a.decided_at" class="text-caption">
                {{ new Date(a.decided_at).toLocaleString('ru-RU') }} &mdash; {{ a.decided_by_username }}
              </div>
              <div v-if="a.comment" class="text-caption mt-1" :class="a.status === 'rejected' ? 'text-error' : 'text-success'">
                <v-icon size="12" icon="mdi-comment-text" /> {{ a.comment }}
              </div>
            </div>
            <div v-if="canDecideApproval(a)" class="d-flex ga-2">
              <v-btn color="success" variant="tonal" size="small" prepend-icon="mdi-check"
                :loading="decidingApprovalId === a.id" @click="decideApproval(a.id, 'approve')">
                Согласовать
              </v-btn>
              <v-btn color="error" variant="outlined" size="small" prepend-icon="mdi-close"
                @click="rejectApprovalId = a.id; rejectComment = ''; rejectDialog = true">
                Отклонить
              </v-btn>
            </div>
            <v-chip v-else :color="approvalDotColor(a.status)" size="x-small" variant="tonal">
              {{ APPROVAL_STEP_LABEL[a.status] }}
            </v-chip>
          </div>
        </v-timeline-item>
      </v-timeline>
      <div v-else class="text-medium-emphasis text-caption">
        Согласование ещё не запущено. Нажмите «Запустить согласование» для начала процесса.
      </div>
    </v-card-text>
  </v-card>

  <!-- Reject dialog -->
  <v-dialog v-model="rejectDialog" max-width="480">
    <v-card>
      <v-card-title>Отклонение согласования</v-card-title>
      <v-card-text>
        <v-textarea v-model="rejectComment" label="Комментарий (обязательно)" rows="3" variant="outlined" />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="rejectDialog = false">Отмена</v-btn>
        <v-btn color="error" variant="flat" :disabled="!rejectComment.trim()" :loading="decidingApprovalId !== null"
          @click="decideApproval(rejectApprovalId!, 'reject', rejectComment)">
          Отклонить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { apiFetch } from '@/api'

interface Approval {
  id: number; purchase_id: number; order_num: number
  role_name: string; approver_full_name: string
  user_id: number | null; status: string
  comment: string | null; decided_at: string | null
  decided_by_user_id: number | null; decided_by_username: string | null
}

const props = defineProps<{
  purchaseId: number
  approvalStatus: string | null
  isManager: boolean
  isAdmin: boolean
  visible: boolean
}>()

const emit = defineEmits<{
  'update:approvalStatus': [status: string | null]
  'snack': [message: string, color?: string]
}>()

const APPROVAL_STATUS_COLOR: Record<string, string> = {
  in_progress: 'orange', approved: 'green', rejected: 'error',
}
const APPROVAL_STATUS_LABEL: Record<string, string> = {
  in_progress: 'На согласовании', approved: 'Согласовано', rejected: 'Отклонено',
}
const APPROVAL_STEP_LABEL: Record<string, string> = {
  pending: 'Ожидает', approved: 'Согласовано', rejected: 'Отклонено', skipped: 'Пропущено',
}

const approvals = ref<Approval[]>([])
const startingApproval = ref(false)
const decidingApprovalId = ref<number | null>(null)
const rejectDialog = ref(false)
const rejectApprovalId = ref<number | null>(null)
const rejectComment = ref('')
const currentUserId = Number(localStorage.getItem('user_id')) || null

const canStart = computed(() => props.isManager || props.isAdmin)

async function loadApprovals() {
  if (!props.purchaseId) return
  try {
    approvals.value = await apiFetch<Approval[]>(`/purchases/${props.purchaseId}/approvals`)
  } catch { approvals.value = [] }
}

async function startApprovalProcess() {
  startingApproval.value = true
  try {
    approvals.value = await apiFetch<Approval[]>(
      `/purchases/${props.purchaseId}/approvals/start`, { method: 'POST', body: {} }
    )
    emit('update:approvalStatus', 'in_progress')
    emit('snack', 'Процесс согласования запущен')
  } catch (e: any) {
    emit('snack', e?.detail || e?.message || 'Ошибка запуска согласования', 'error')
  } finally { startingApproval.value = false }
}

function canDecideApproval(a: Approval): boolean {
  if (a.status !== 'pending') return false
  if (props.approvalStatus !== 'in_progress') return false
  const prior = approvals.value.filter(x => x.order_num < a.order_num)
  if (prior.some(x => x.status !== 'approved' && x.status !== 'skipped')) return false
  if (a.user_id && a.user_id !== currentUserId && !props.isAdmin) return false
  if (!a.user_id && !props.isManager && !props.isAdmin) return false
  return true
}

async function decideApproval(approvalId: number, action: 'approve' | 'reject', comment?: string) {
  decidingApprovalId.value = approvalId
  try {
    await apiFetch(`/purchases/${props.purchaseId}/approvals/${approvalId}/decide`, {
      method: 'POST', body: { action, comment: comment || undefined }
    })
    await loadApprovals()
    try {
      const p = await apiFetch<any>(`/purchases/${props.purchaseId}`)
      emit('update:approvalStatus', p.approval_status)
    } catch {}
    emit('snack', action === 'approve' ? 'Согласовано' : 'Отклонено')
    rejectDialog.value = false
  } catch (e: any) {
    emit('snack', e?.detail || e?.message || 'Ошибка', 'error')
  } finally { decidingApprovalId.value = null }
}

async function resetApproval() {
  try {
    await apiFetch(`/purchases/${props.purchaseId}/approvals/reset`, { method: 'POST' })
    approvals.value = []
    emit('update:approvalStatus', null)
    emit('snack', 'Согласование сброшено')
  } catch (e: any) {
    emit('snack', e?.detail || 'Ошибка сброса', 'error')
  }
}

function approvalDotColor(status: string): string {
  return ({ pending: 'grey', approved: 'green', rejected: 'error', skipped: 'blue-grey' } as Record<string, string>)[status] || 'grey'
}
function approvalIcon(status: string): string {
  return ({ pending: 'mdi-clock-outline', approved: 'mdi-check', rejected: 'mdi-close', skipped: 'mdi-skip-next' } as Record<string, string>)[status] || 'mdi-help'
}

defineExpose({ loadApprovals })
</script>
