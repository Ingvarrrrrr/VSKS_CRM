<template>
  <div v-if="revision.state.context?.mode === 'revision'" class="rev-draft-bar">
    <template v-if="!revision.state.context?.draft">
      <v-icon icon="mdi-pencil-outline" size="16" class="mr-1" />
      <span class="text-caption text-medium-emphasis">Правки в этой субсидии идут через корректировку — начните с любого изменения в дереве ФЭО</span>
    </template>

    <template v-else>
      <div class="rev-draft-head">
        <v-icon icon="mdi-file-document-edit-outline" size="18" color="#7c3aed" />
        <span class="rev-draft-title">Режим корректировки №{{ revision.state.context.draft.number }}</span>
        <v-chip size="x-small" :color="statusColor" variant="flat">{{ statusLabel }}</v-chip>
        <span class="text-caption text-medium-emphasis">изменений: {{ ops.length }}</span>
        <v-spacer />
        <v-btn size="small" variant="text" :icon="expanded ? 'mdi-chevron-down' : 'mdi-chevron-up'" @click="expanded = !expanded" />
      </div>

      <div v-if="expanded" class="rev-draft-body">
        <div v-if="locked" class="rev-draft-locked text-caption">
          <v-icon icon="mdi-lock-outline" size="14" class="mr-1" />
          Корректировка на проверке — правки заблокированы до решения проверяющего
        </div>

        <div class="rev-draft-ops">
          <div
            v-for="op in ops" :key="op.id" :data-rev-op-id="op.id" class="rev-draft-op"
            :class="{ 'rev-draft-op--rejected': op.status === 'rejected', 'rev-draft-op--problem': !!submitProblems[op.id] }"
          >
            <div class="rev-draft-op-path">
              {{ op.path || opFallbackPath(op) }}
              <v-chip v-if="op.op_type === 'delete'" size="x-small" color="error" variant="tonal" class="ml-1">удалить</v-chip>
              <v-chip v-if="op.op_type === 'create'" size="x-small" color="success" variant="tonal" class="ml-1">новая</v-chip>
              <v-chip v-if="op.bundle_no" size="x-small" color="indigo" variant="tonal" class="ml-1">Связка {{ op.bundle_no }}</v-chip>
              <v-chip v-if="op.added_by_reviewer" size="x-small" color="orange" variant="tonal" class="ml-1">от проверяющего</v-chip>
            </div>
            <div class="rev-draft-op-values text-caption">{{ formatOpSummary(op) }}</div>
            <v-btn
              v-if="!locked && op.op_type === 'update' && !op.bundle_no && isIncreaseOp(op)"
              size="x-small" variant="tonal" color="indigo" class="mt-1"
              @click="openBundleDialog(op)"
            >За счёт чего…</v-btn>
            <div v-if="op.reviewer_after" class="rev-draft-op-reviewer text-caption">
              проверяющий: {{ formatValue(op.reviewer_after) }}
              <span v-if="op.review_comment"> — «{{ op.review_comment }}»</span>
            </div>
            <div v-else-if="op.review_comment" class="rev-draft-op-reviewer text-caption">«{{ op.review_comment }}»</div>
            <div v-if="submitProblems[op.id]" class="rev-draft-op-problem text-caption">{{ submitProblems[op.id] }}</div>
            <v-btn v-if="!locked" icon="mdi-close" size="x-small" variant="text" class="rev-draft-op-remove" title="Убрать эту правку" @click="removeOp(op.id)" />
          </div>
          <div v-if="!ops.length" class="text-caption text-medium-emphasis">Пока нет правок</div>
        </div>

        <div v-if="bundles.length" class="rev-draft-bundles text-caption">
          <div class="text-medium-emphasis mb-1">Связки «откуда деньги»:</div>
          <div v-for="b in bundles" :key="b.bundle_no" class="rev-draft-bundle" :class="{ 'rev-draft-bundle--bad': Math.abs(b.balance) > 0.005 }">
            Связка {{ b.bundle_no }}: добавлено {{ formatCurrency(b.added) }}, снято {{ formatCurrency(b.removed) }},
            баланс {{ formatCurrency(b.balance) }}
          </div>
        </div>

        <v-textarea
          v-if="!locked"
          v-model="comment"
          label="Комментарий к корректировке (необязательно)"
          density="compact" rows="2" auto-grow hide-details class="mt-2"
        />

        <div class="rev-draft-actions">
          <v-btn v-if="!locked" ref="submitBtn" color="primary" variant="flat" size="small" :disabled="!ops.length" :loading="submitting" @click="doSubmit">
            Отправить на проверку
          </v-btn>
          <v-btn v-else color="warning" variant="tonal" size="small" :loading="submitting" @click="doWithdraw">
            Отозвать с проверки
          </v-btn>
        </div>

        <div v-if="errorMsg" class="rev-draft-error text-caption">{{ errorMsg }}</div>
      </div>
    </template>

    <ValidationArrows :active="arrowsActive" :from-el="arrowFrom" :to-els="arrowTargets" @dismiss="arrowsActive = false" />

    <RevisionBundleDialog
      v-model="bundleDialogOpen" :op="bundleDialogOp" :ops="ops" :bundles="bundles"
      @confirm="onBundleConfirm"
    />
  </div>
</template>

<script setup lang="ts">
// Плашка корректировки — волна 3B, требование владельца п.5. Единственная
// точка submit/withdraw/removeOp — через useSubsidyRevision (Правило №6),
// сама запросов не изобретает.
import { computed, ref } from 'vue'
import { formatCurrency } from '@/composables/subsidies/format'
import { formatOpSummary } from '@/composables/subsidies/revisionFormat'
import { describeApiError } from '@/utils/apiErrorMessage'
import ValidationArrows from '@/components/ValidationArrows.vue'
import RevisionBundleDialog from './RevisionBundleDialog.vue'
import type { SubsidyRevisionApi, RevisionOp } from '@/composables/subsidies/useSubsidyRevision'
import type { RevisionOverlayApi } from '@/composables/subsidies/useRevisionOverlay'

const props = defineProps<{
  revision: SubsidyRevisionApi
  overlay?: RevisionOverlayApi | null
}>()

const expanded = ref(true)
const comment = ref('')
const submitting = ref(false)
const errorMsg = ref<string | null>(null)
const submitBtn = ref<any>(null)
const arrowsActive = ref(false)
const arrowFrom = ref<HTMLElement | null>(null)
const arrowTargets = ref<HTMLElement[]>([])
// 422 revision_problems (приёмка 02.10, п.6) — текст у КОНКРЕТНОЙ строки, не
// общий баннер; ключ — op_id.
const submitProblems = ref<Record<number, string>>({})

// «За счёт чего…» (приёмка 02.10, п.2) — RevisionBundleDialog.vue нигде не
// был смонтирован, setBundle() никто не вызывал.
const bundleDialogOpen = ref(false)
const bundleDialogOp = ref<RevisionOp | null>(null)
function openBundleDialog(op: RevisionOp) {
  bundleDialogOp.value = op
  bundleDialogOpen.value = true
}
function isIncreaseOp(op: RevisionOp): boolean {
  const before = Number(op.before?.budget ?? op.before?.planned_amount ?? op.before?.amount ?? 0)
  const after = Number(op.after?.budget ?? op.after?.planned_amount ?? op.after?.amount ?? 0)
  return after > before + 0.005
}
async function onBundleConfirm(value: number | string | null) {
  const op = bundleDialogOp.value
  if (!op) return
  try {
    if (value === null) {
      // Свободные деньги субсидии — новая связка только на эту строку.
      await props.revision.createBundle([op.id], true)
    } else if (typeof value === 'string' && value.startsWith('__sources__:')) {
      const sourceIds = value.slice('__sources__:'.length).split(',').filter(Boolean).map(Number)
      await props.revision.createBundle([op.id, ...sourceIds], false)
    } else {
      // Присоединиться к уже существующей связке.
      await props.revision.setBundle(op.id, Number(value))
    }
    props.overlay?.scheduleRefresh()
  } catch (e: any) {
    errorMsg.value = describeApiError(e, { fallback: 'Не удалось сохранить связку' })
  }
}

const ops = computed<RevisionOp[]>(() => props.revision.state.detail?.ops || [])
const bundles = computed(() => props.overlay?.preview.value?.bundles || [])
const locked = computed(() => props.revision.state.context?.draft?.status === 'submitted' || props.revision.state.context?.draft?.status === 'on_review')

const statusLabel = computed(() => {
  const s = props.revision.state.context?.draft?.status
  if (s === 'submitted' || s === 'on_review') return 'На проверке'
  if (s === 'draft') return 'Черновик'
  return s || ''
})
const statusColor = computed(() => (locked.value ? 'orange' : 'grey'))

function opFallbackPath(op: RevisionOp): string {
  return `${op.entity_type === 'feo_category' ? 'Статья' : op.entity_type === 'feo_item' ? 'Позиция' : 'Субсидия'} #${op.target_id ?? op.target_ref}`
}
function formatValue(v: any): string {
  if (v == null) return '—'
  if (typeof v === 'object') {
    const keys = Object.keys(v)
    if (!keys.length) return '—'
    return keys.map((k) => {
      const val = v[k]
      return typeof val === 'number' ? formatCurrency(val) : String(val)
    }).join(', ')
  }
  return String(v)
}

async function removeOp(opId: number) {
  try {
    await props.revision.removeOp(opId)
    if (submitProblems.value[opId]) {
      const next = { ...submitProblems.value }
      delete next[opId]
      submitProblems.value = next
    }
    props.overlay?.scheduleRefresh()
  } catch (e: any) {
    errorMsg.value = describeApiError(e, { fallback: 'Не удалось убрать правку' })
  }
}

async function doSubmit() {
  submitting.value = true
  errorMsg.value = null
  submitProblems.value = {}
  const res = await props.revision.submit(comment.value || undefined)
  submitting.value = false
  if (!res.ok) {
    arrowFrom.value = submitBtn.value?.$el || null
    if (res.problems?.length) {
      // 422 revision_problems (приёмка 02.10, п.6) — текст у строк, стрелка от
      // кнопки к каждой проблемной (не generic «ошибка» одной строкой).
      const map: Record<number, string> = {}
      for (const p of res.problems) map[Number(p.op_id)] = p.message || p.code
      submitProblems.value = map
      errorMsg.value = 'Исправьте отмеченные строки и отправьте снова'
      arrowTargets.value = Object.keys(map)
        .map((id) => document.querySelector<HTMLElement>(`[data-rev-op-id="${id}"]`))
        .filter((el): el is HTMLElement => !!el)
    } else {
      errorMsg.value = res.error
      arrowTargets.value = []
    }
    arrowsActive.value = true
  } else {
    comment.value = ''
  }
}
async function doWithdraw() {
  submitting.value = true
  errorMsg.value = null
  const res = await props.revision.withdraw()
  submitting.value = false
  if (!res.ok) errorMsg.value = res.error
}
</script>

<style scoped>
/* Приёмка 02.10, п.9: раньше position:sticky; bottom:0 держал плашку поверх
   строки ИТОГО дерева ФЭО (та идёт в DOM ПОСЛЕ плашки, но sticky-блок
   перекрывал её при прокрутке). Обычный блок после дерева, сворачивается
   кнопкой-шевроном рядом с заголовком (expanded) — этого достаточно, второй
   способ (отступ контейнера под sticky-низ) не нужен. */
.rev-draft-bar {
  background: var(--crm-surface); border: 1px solid rgba(124,58,237,0.35);
  border-radius: 10px; padding: 8px 14px; margin-top: 10px; margin-bottom: 10px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.06);
}
.rev-draft-head { display: flex; align-items: center; gap: 8px; }
.rev-draft-title { font-weight: 700; color: #6d28d9; font-size: 13px; }
.rev-draft-body { margin-top: 8px; }
.rev-draft-locked {
  background: rgba(251,146,60,0.1); border: 1px solid rgba(251,146,60,0.35);
  border-radius: 6px; padding: 4px 8px; margin-bottom: 8px; color: #b45309;
}
.rev-draft-ops { max-height: 220px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
.rev-draft-op {
  position: relative; border: 1px solid var(--crm-border); border-radius: 6px;
  padding: 4px 28px 4px 8px; font-size: 12px;
}
.rev-draft-op--rejected { opacity: 0.6; border-color: #dc2626; }
.rev-draft-op--problem { border-color: #dc2626; }
.rev-draft-op-path { font-weight: 600; }
.rev-draft-op-values { color: var(--crm-text-secondary); }
.rev-draft-op-reviewer { color: #b45309; }
.rev-draft-op-problem { color: #dc2626; font-weight: 600; margin-top: 2px; }
.rev-draft-op-remove { position: absolute; right: 2px; top: 2px; }
.rev-draft-bundles { margin-top: 8px; }
.rev-draft-bundle { padding: 2px 0; }
.rev-draft-bundle--bad { color: #dc2626; font-weight: 600; }
.rev-draft-actions { display: flex; justify-content: flex-end; margin-top: 8px; }
.rev-draft-error { color: #dc2626; margin-top: 6px; }
</style>
