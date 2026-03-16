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
              <div class="font-weight-medium d-flex align-center ga-1">
                {{ a.approver_full_name }}
                <v-icon v-if="a.has_signature" icon="mdi-draw" size="14" color="blue-darken-2"
                  title="Подписано электронно" />
              </div>
              <div class="text-caption text-medium-emphasis">{{ a.role_name }}</div>
              <div v-if="a.decided_at" class="text-caption">
                {{ new Date(a.decided_at).toLocaleString('ru-RU') }} &mdash; {{ a.decided_by_username }}
                <v-chip v-if="a.has_signature" size="x-small" color="blue" variant="tonal" class="ml-1">
                  эл. подпись
                </v-chip>
              </div>
              <div v-if="a.comment" class="text-caption mt-1"
                :class="a.status === 'rejected' ? 'text-error' : 'text-success'">
                <v-icon size="12" icon="mdi-comment-text" /> {{ a.comment }}
              </div>
            </div>
            <div v-if="canDecideApproval(a)" class="d-flex ga-2">
              <v-btn color="success" variant="tonal" size="small" prepend-icon="mdi-check"
                @click="openApproveDialog(a)">
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

  <!-- ── Reject dialog ── -->
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

  <!-- ── Approve dialog: электронно или бумажно ── -->
  <v-dialog v-model="approveDialog" max-width="440">
    <v-card>
      <v-card-title class="pt-4 px-5">Подписать согласование</v-card-title>
      <v-card-text class="px-5">
        <div class="text-body-2 mb-4">Выберите способ подписания:</div>

        <!-- Электронная подпись -->
        <v-card
          :class="['sign-option', signMode === 'electronic' ? 'sign-option--active' : '']"
          :variant="signMode === 'electronic' ? 'tonal' : 'outlined'"
          :color="signMode === 'electronic' ? 'primary' : undefined"
          class="mb-3 cursor-pointer"
          @click="signMode = 'electronic'"
        >
          <v-card-text class="d-flex align-start ga-3 pa-3">
            <v-icon icon="mdi-draw" size="28" :color="signMode === 'electronic' ? 'primary' : 'grey'" class="mt-1" />
            <div class="flex-grow-1">
              <div class="font-weight-medium">Электронная подпись</div>
              <div class="text-caption text-medium-emphasis">
                Ваша подпись фиксируется в системе и появится в документе
              </div>
              <!-- Signature preview -->
              <div v-if="userSignature" class="mt-2 sig-preview-sm">
                <img :src="userSignature" alt="подпись" class="sig-img-sm" />
              </div>
              <div v-else class="mt-2">
                <v-chip size="x-small" color="warning" variant="tonal">
                  Подпись не создана
                </v-chip>
                <v-btn size="x-small" variant="text" color="primary" class="ml-1"
                  @click.stop="openSignaturePad">
                  Создать
                </v-btn>
              </div>
            </div>
          </v-card-text>
        </v-card>

        <!-- Бумажная подпись -->
        <v-card
          :class="['sign-option', signMode === 'paper' ? 'sign-option--active' : '']"
          :variant="signMode === 'paper' ? 'tonal' : 'outlined'"
          :color="signMode === 'paper' ? 'grey' : undefined"
          class="cursor-pointer"
          @click="signMode = 'paper'"
        >
          <v-card-text class="d-flex align-start ga-3 pa-3">
            <v-icon icon="mdi-printer" size="28" :color="signMode === 'paper' ? 'grey-darken-2' : 'grey'" class="mt-1" />
            <div>
              <div class="font-weight-medium">Бумажная подпись</div>
              <div class="text-caption text-medium-emphasis">
                Согласование зафиксируется, лист нужно будет распечатать и подписать вручную
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-card-text>

      <v-card-actions class="px-5 pb-4">
        <v-spacer />
        <v-btn @click="approveDialog = false">Отмена</v-btn>
        <v-btn color="success" variant="flat"
          :disabled="signMode === 'electronic' && !userSignature"
          :loading="decidingApprovalId !== null"
          @click="confirmApprove">
          Подтвердить согласование
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Signature pad -->
  <SignaturePad ref="sigPadRef" @saved="onSignatureSaved" />
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiFetch } from '@/api'
import SignaturePad from '@/components/SignaturePad.vue'

interface Approval {
  id: number; purchase_id: number; order_num: number
  role_name: string; approver_full_name: string
  user_id: number | null; status: string
  comment: string | null; decided_at: string | null
  decided_by_user_id: number | null; decided_by_username: string | null
  has_signature: boolean; signature_algorithm: string | null
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

// Approve dialog
const approveDialog = ref(false)
const approveTargetId = ref<number | null>(null)
const signMode = ref<'electronic' | 'paper'>('electronic')
const userSignature = ref<string | null>(null)
const sigPadRef = ref<InstanceType<typeof SignaturePad> | null>(null)

const canStart = computed(() => props.isManager || props.isAdmin)

async function loadApprovals() {
  if (!props.purchaseId) return
  try {
    approvals.value = await apiFetch<Approval[]>(`/purchases/${props.purchaseId}/approvals`)
  } catch { approvals.value = [] }
}

async function loadUserSignature() {
  try {
    const data = await apiFetch<{ signature: string | null }>('/users/me/signature')
    userSignature.value = data.signature || null
  } catch { userSignature.value = null }
}

onMounted(() => { loadUserSignature() })

function openApproveDialog(a: Approval) {
  approveTargetId.value = a.id
  signMode.value = userSignature.value ? 'electronic' : 'paper'
  approveDialog.value = true
}

async function confirmApprove() {
  if (!approveTargetId.value) return
  await decideApproval(
    approveTargetId.value,
    'approve',
    undefined,
    signMode.value === 'electronic'
  )
  approveDialog.value = false
}

function openSignaturePad() {
  sigPadRef.value?.open()
}

function onSignatureSaved(hasSignature: boolean) {
  if (hasSignature) loadUserSignature()
  else userSignature.value = null
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

async function decideApproval(
  approvalId: number,
  action: 'approve' | 'reject',
  comment?: string,
  signElectronically = false
) {
  decidingApprovalId.value = approvalId
  try {
    await apiFetch(`/purchases/${props.purchaseId}/approvals/${approvalId}/decide`, {
      method: 'POST',
      body: { action, comment: comment || undefined, sign_electronically: signElectronically }
    })
    await loadApprovals()
    try {
      const p = await apiFetch<any>(`/purchases/${props.purchaseId}`)
      emit('update:approvalStatus', p.approval_status)
    } catch {}
    const msg = action === 'approve'
      ? (signElectronically ? 'Согласовано с электронной подписью' : 'Согласовано')
      : 'Отклонено'
    emit('snack', msg, action === 'approve' ? 'success' : 'error')
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

<style scoped>
.cursor-pointer { cursor: pointer; }
.sign-option { transition: all 0.15s ease; }
.sign-option--active { border-width: 2px !important; }
.sig-preview-sm {
  border: 1px solid rgba(0,0,0,0.1);
  border-radius: 6px;
  padding: 4px 8px;
  background: #fff;
  display: inline-block;
  max-width: 200px;
}
.sig-img-sm {
  max-height: 48px;
  max-width: 180px;
  display: block;
}
</style>
