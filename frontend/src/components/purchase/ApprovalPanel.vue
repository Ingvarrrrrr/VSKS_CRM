<template>
  <v-card v-if="visible" variant="outlined" class="mb-4" style="border-color:#059669">
    <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-3 d-flex align-center justify-space-between">
      <span class="d-flex align-center gap-2">
        <v-icon icon="mdi-check-decagram" color="green-darken-2" size="20" />
        {{ panelTitle }}
      </span>
      <div class="d-flex align-center ga-2">
        <v-chip v-if="approvalStatus" :color="APPROVAL_STATUS_COLOR[approvalStatus]" size="small" variant="tonal">
          {{ APPROVAL_STATUS_LABEL[approvalStatus] }}
        </v-chip>
        <v-chip v-if="approvals.length" size="small" variant="outlined">
          {{ approvals.filter(a => a.status === 'approved').length }}/{{ approvals.length }}
        </v-chip>
        <v-chip v-if="approvalStatus === 'in_progress' && props.approvalMode === 'parallel'"
          size="small" variant="tonal" color="blue" prepend-icon="mdi-account-group">
          параллельно
        </v-chip>
        <!-- Рамочная голова: денежный «Запустить согласование» (SubsidyApprover,
             требует статус work_in_progress) сюда не подходит — необходимость
             договора согласуют вручную добавленные/построенные цепочкой люди. -->
        <v-btn v-if="!approvalStatus && canStart && !props.isFrameworkHead" color="green-darken-2" variant="tonal" size="small"
          prepend-icon="mdi-play-circle-outline" :loading="startingApproval" @click="startDialog = true">
          Запустить согласование
        </v-btn>
        <v-btn v-if="props.isFrameworkHead" color="teal-darken-1" variant="tonal" size="small"
          prepend-icon="mdi-source-branch" :loading="fhCascadeLoading" @click="runFrameworkCascade">
          Построить цепочку
        </v-btn>
        <v-btn v-if="approvalStatus === 'rejected' && isAdmin" color="warning" variant="tonal" size="small"
          prepend-icon="mdi-refresh" @click="resetApproval">
          Перезапустить
        </v-btn>
        <v-btn color="primary" variant="tonal" size="small"
          prepend-icon="mdi-account-plus-outline" @click="openAddApproverDialog">
          Добавить
        </v-btn>
      </div>
    </v-card-title>

    <!-- Рамочная голова, согласование ещё не начато: выбор режима ДО того как
         добавлен первый согласующий (первый add/cascade фиксирует режим). -->
    <v-card-text v-if="props.isFrameworkHead && !approvalStatus" class="px-4 pt-0 pb-2">
      <div class="text-caption text-medium-emphasis mb-1">
        Порядок согласования (учитывается при добавлении первого согласующего)
      </div>
      <v-btn-toggle v-model="fhMode" mandatory density="compact" color="teal" size="small">
        <v-btn value="sequential" size="small">Последовательно</v-btn>
        <v-btn value="parallel" size="small">Параллельно</v-btn>
      </v-btn-toggle>
    </v-card-text>

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
      <div v-else-if="props.isFrameworkHead" class="text-medium-emphasis text-caption">
        Согласующие ещё не выбраны. Добавьте их по одному кнопкой «Добавить» или нажмите «Построить цепочку».
      </div>
      <div v-else class="text-medium-emphasis text-caption">
        Согласование ещё не запущено. Нажмите «Запустить согласование» для начала процесса.
      </div>
    </v-card-text>
  </v-card>

  <!-- ── Reject dialog ── -->
  <v-dialog v-model="rejectDialog" max-width="480" :fullscreen="mobile">
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
  <v-dialog v-model="approveDialog" max-width="440" :fullscreen="mobile">
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

  <!-- ── Start approval dialog ── -->
  <v-dialog v-model="startDialog" max-width="480" :fullscreen="mobile">
    <v-card>
      <v-card-title class="pt-4 px-5">Запуск согласования</v-card-title>
      <v-card-text class="px-5">
        <!-- Sign type -->
        <div class="text-body-2 font-weight-medium mb-2">Тип подписания</div>
        <v-btn-toggle v-model="startSignType" mandatory color="primary" class="mb-4" density="compact">
          <v-btn value="electronic" prepend-icon="mdi-draw" size="small">Электронное</v-btn>
          <v-btn value="paper" prepend-icon="mdi-printer" size="small">Бумажное</v-btn>
        </v-btn-toggle>

        <!-- Approval mode (only for electronic) -->
        <template v-if="startSignType === 'electronic'">
          <div class="text-body-2 font-weight-medium mb-2">Порядок согласования</div>
          <v-card
            :variant="startMode === 'sequential' ? 'tonal' : 'outlined'"
            :color="startMode === 'sequential' ? 'teal' : undefined"
            class="mb-2 cursor-pointer"
            @click="startMode = 'sequential'"
          >
            <v-card-text class="d-flex align-start ga-3 pa-3">
              <v-icon icon="mdi-format-list-numbered" size="24"
                :color="startMode === 'sequential' ? 'teal' : 'grey'" />
              <div>
                <div class="font-weight-medium">Последовательно</div>
                <div class="text-caption text-medium-emphasis">
                  Каждый согласующий подписывает по очереди, в порядке листа
                </div>
              </div>
            </v-card-text>
          </v-card>
          <v-card
            :variant="startMode === 'parallel' ? 'tonal' : 'outlined'"
            :color="startMode === 'parallel' ? 'teal' : undefined"
            class="cursor-pointer"
            @click="startMode = 'parallel'"
          >
            <v-card-text class="d-flex align-start ga-3 pa-3">
              <v-icon icon="mdi-account-group" size="24"
                :color="startMode === 'parallel' ? 'teal' : 'grey'" />
              <div>
                <div class="font-weight-medium">Параллельно (всем сразу)</div>
                <div class="text-caption text-medium-emphasis">
                  Все согласующие могут подписать одновременно, порядок не важен
                </div>
              </div>
            </v-card-text>
          </v-card>
        </template>
      </v-card-text>
      <v-card-text class="px-5 pt-0 pb-2">
        <v-text-field v-model="approvalDeadline" label="Срок согласования (необязательно)"
          type="date" variant="outlined" density="compact" hide-details clearable
          hint="Если указан — напоминание при просрочке" />
      </v-card-text>
      <v-card-actions class="px-5 pb-4">
        <v-spacer />
        <v-btn @click="startDialog = false">Отмена</v-btn>
        <v-btn color="green-darken-2" variant="flat" :loading="startingApproval"
          prepend-icon="mdi-play-circle-outline" @click="startApprovalProcess">
          Запустить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Signature pad -->
  <SignaturePad ref="sigPadRef" @saved="onSignatureSaved" />

  <!-- ── Add Approver Dialog ── -->
  <v-dialog v-model="addApproverDialog" max-width="480" :fullscreen="mobile">
    <v-card>
      <v-card-title class="pt-4 px-5 d-flex align-center">
        <v-icon icon="mdi-account-plus-outline" color="primary" class="mr-2" />
        Добавить согласующего
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="addApproverDialog = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="px-5 pt-4">
        <v-autocomplete
          v-model="addApproverForm.selectedUser"
          :items="usersList"
          item-title="full_name"
          item-value="id"
          label="Сотрудник *"
          variant="outlined"
          density="compact"
          return-object
          clearable
          class="mb-3"
        />
        <v-text-field
          v-model="addApproverForm.role_name"
          label="Должность / роль *"
          variant="outlined"
          density="compact"
          hide-details
          class="mb-3"
        />
      </v-card-text>
      <v-card-actions class="px-5 pb-4">
        <v-spacer />
        <v-btn @click="addApproverDialog = false">Отмена</v-btn>
        <v-btn color="primary" variant="flat"
          :disabled="!addApproverForm.selectedUser || !addApproverForm.role_name.trim()"
          :loading="addingApprover"
          @click="submitAddApprover">
          Добавить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { refreshMyPendingApprovals } from '@/composables/useApprovalsBadge'
import SignaturePad from '@/components/SignaturePad.vue'

const { mobile } = useDisplay()

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
  approvalMode: string | null
  isManager: boolean
  isAdmin: boolean
  visible: boolean
  subsidyId?: number | null
  // Владелец (2026-09-03): рамочная ГОЛОВА договора согласуется как заявка —
  // вручную добавленными согласующими необходимости, а не денежным
  // SubsidyApprover-потоком (см. CreateOrderView.vue::isFrameworkHeadPurchase,
  // источник — Purchase.is_framework_head с бэкенда).
  isFrameworkHead?: boolean
}>()

const emit = defineEmits<{
  'update:approvalStatus': [status: string | null]
  'update:approvalMode': [mode: string | null]
  'snack': [message: string, color?: string]
}>()

// Панель у рамочной головы — про необходимость самого договора, не про сумму
// (владелец: «Смысл согласования у рамочной головы — нужен ли вообще этот
// договор... а не согласование суммы»).
const panelTitle = computed(() => props.isFrameworkHead ? 'Согласование необходимости договора' : 'Согласование')

// Режим (последовательно/параллельно), выбираемый ДО первого согласующего —
// фиксируется на сервере первым же add/cascade (см. add_approver,
// cascade_purchase_approvers). После этого момента approvalStatus уже не
// null, и переключатель в шаблоне скрывается сам.
const fhMode = ref<'sequential' | 'parallel'>('sequential')
const fhCascadeLoading = ref(false)

async function runFrameworkCascade() {
  fhCascadeLoading.value = true
  try {
    const res = await apiFetch<{ approval_mode: string; approval_status: string | null; approvers: Approval[]; warning?: string | null }>(
      `/purchases/${props.purchaseId}/approvers/cascade`,
      { method: 'POST', body: { mode: fhMode.value } },
    )
    approvals.value = res.approvers
    emit('update:approvalStatus', res.approval_status)
    emit('update:approvalMode', res.approval_mode)
    if (res.warning) {
      emit('snack', `Цепочка построена. Внимание: ${res.warning}`, 'warning')
    } else if (res.approvers.length) {
      emit('snack', 'Цепочка построена')
    } else {
      emit('snack', 'Не удалось построить цепочку — у организации не задан руководитель', 'warning')
    }
  } catch (e: any) {
    emit('snack', e?.detail || e?.message || 'Не удалось построить цепочку', 'error')
  } finally {
    fhCascadeLoading.value = false
  }
}

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

// Add approver dialog
const addApproverDialog = ref(false)
const addingApprover = ref(false)
const addApproverForm = ref<{ selectedUser: { id: number; full_name: string } | null; role_name: string }>({
  selectedUser: null,
  role_name: '',
})
const usersList = ref<Array<{ id: number; full_name: string }>>([])

async function loadUsers() {
  try {
    // Согласующим по закупке с субсидией может быть только сотрудник орг(а)
    // субсидии или человек с персональным доступом к ней.
    const qs = props.subsidyId ? `?subsidy_id=${props.subsidyId}` : ''
    const data = await apiFetch<any[]>(`/users/${qs}`)
    usersList.value = data
      .filter((u: any) => u.full_name)
      .map((u: any) => ({ id: u.id, full_name: u.full_name }))
  } catch { usersList.value = [] }
}

async function openAddApproverDialog() {
  addApproverForm.value = { selectedUser: null, role_name: '' }
  addApproverDialog.value = true
  await loadUsers()
}

async function submitAddApprover() {
  const user = addApproverForm.value.selectedUser
  if (!user || !addApproverForm.value.role_name.trim()) return
  addingApprover.value = true
  try {
    const res = await apiFetch<any>(`/purchases/${props.purchaseId}/approvals/add`, {
      method: 'POST',
      body: {
        user_id: user.id,
        full_name: user.full_name,
        role_name: addApproverForm.value.role_name.trim(),
        // Учитывается бэкендом только на самом ПЕРВОМ согласующем рамочной
        // головы — им она уходит на согласование (см. add_approver docstring).
        ...(props.isFrameworkHead ? { mode: fhMode.value } : {}),
      },
    })
    await loadApprovals()
    addApproverDialog.value = false
    emit('snack', `${user.full_name} добавлен как согласующий`, 'success')
    // Рамочная голова: первый добавленный согласующий сразу включает
    // согласование необходимости на сервере (purchase.approval_status —
    // см. add_approver) — синхронизируем родителя, иначе кнопки
    // «Согласовать/Отклонить» не появятся до перезагрузки страницы.
    if (props.isFrameworkHead) {
      if (res?.purchase_approval_status) emit('update:approvalStatus', res.purchase_approval_status)
      if (res?.purchase_approval_mode) emit('update:approvalMode', res.purchase_approval_mode)
    }
  } catch (e: any) {
    emit('snack', e?.detail || e?.message || 'Ошибка добавления', 'error')
  } finally {
    addingApprover.value = false
  }
}

// Start dialog
const startDialog = ref(false)
const startMode = ref<'sequential' | 'parallel'>('sequential')
const startSignType = ref<'electronic' | 'paper'>('electronic')
const approvalDeadline = ref<string>('')

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
      `/purchases/${props.purchaseId}/approvals/start`, {
        method: 'POST',
        body: {
          approval_mode: startSignType.value === 'electronic' ? startMode.value : 'sequential',
          approval_sign_type: startSignType.value,
          approval_deadline: approvalDeadline.value || undefined,
        },
      }
    )
    emit('update:approvalStatus', 'in_progress')
    const modeLabel = startMode.value === 'parallel' ? 'параллельно' : 'последовательно'
    const typeLabel = startSignType.value === 'electronic' ? 'электронно' : 'бумажно'
    emit('snack', `Согласование запущено (${typeLabel}, ${modeLabel})`)
    startDialog.value = false
  } catch (e: any) {
    emit('snack', e?.detail || e?.message || 'Ошибка запуска согласования', 'error')
  } finally { startingApproval.value = false }
}

function canDecideApproval(a: Approval): boolean {
  if (a.status !== 'pending') return false
  if (props.approvalStatus !== 'in_progress') return false
  // In sequential mode, check that all prior approvers are done
  if (props.approvalMode !== 'parallel') {
    const prior = approvals.value.filter(x => x.order_num < a.order_num)
    if (prior.some(x => x.status !== 'approved' && x.status !== 'skipped')) return false
  }
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
    refreshMyPendingApprovals()  // бейдж «мои согласования» в сайдбаре
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
