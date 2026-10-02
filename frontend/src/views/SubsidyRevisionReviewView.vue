<template>
  <div class="rrv-page">
    <v-progress-linear v-if="loading" indeterminate color="deep-purple" class="mb-3" />

    <template v-else-if="review.detail.value">
      <div class="rrv-header">
        <div class="rrv-title">
          <v-icon icon="mdi-file-document-edit-outline" size="22" color="#7c3aed" class="mr-2" />
          Корректировка №{{ review.detail.value.number }} — {{ subsidyName || `субсидия #${review.detail.value.subsidy_id}` }},
          вносит {{ authorName }}, отправлена {{ submittedAtLabel }}
        </div>
        <v-chip size="small" :color="statusColor" variant="flat">{{ statusLabel }}</v-chip>
      </div>
      <div v-if="review.detail.value.author_comment" class="rrv-author-comment">
        <v-icon icon="mdi-comment-text-outline" size="14" class="mr-1" />{{ review.detail.value.author_comment }}
      </div>

      <v-alert v-if="review.error.value" type="error" variant="tonal" density="compact" class="mb-3" closable @click:close="review.error.value = null">
        {{ review.error.value }}
      </v-alert>

      <v-alert v-if="outcomeMessage" type="success" variant="tonal" density="compact" class="mb-3" closable @click:close="outcomeMessage = null">
        {{ outcomeMessage }}
        <template #append>
          <v-btn size="small" variant="text" @click="goToSubsidy">Перейти в субсидию</v-btn>
        </template>
      </v-alert>

      <div v-if="problems.length || hasShortfall" class="rrv-problems">
        <template v-if="problems.length">
          <div class="text-caption font-weight-bold mb-1" style="color:#991b1b">Применить нельзя, пока не устранено:</div>
          <div v-for="(p, i) in problems" :key="i" class="rrv-problem">
            <a href="javascript:void(0)" @click="scrollToOp(p.op_id)">строка №{{ p.op_id }}</a> — {{ p.message || p.code }}
          </div>
        </template>
        <!-- Своё условие (не внутри problems.length — приёмка 02.10, п.3): шапка
             баланса preview.balance может сигналить нехватку денег даже когда
             problems пуст (отклонённый shortfall-блок по связке, не по строке). -->
        <div v-if="hasShortfall" class="rrv-problem">
          Не хватает свободных денег субсидии: {{ balanceMoneyLine }}
        </div>
      </div>

      <v-tabs v-model="tab" density="compact" class="mb-3">
        <v-tab value="tree">Дерево и решения</v-tab>
        <v-tab value="list">Список изменений</v-tab>
      </v-tabs>

      <v-window v-model="tab">
        <!-- Слева дерево ФЭО «было/станет» (основное представление, требование
             владельца), справа — связки и решения узкой колонкой; оба читают
             ОДНО состояние useRevisionReview.ts, клик в любой стороне
             прокручивает к той же строке в другой (см. RevisionTreeRow.vue/
             RevisionReviewPanel.vue::scrollToTreeNode). -->
        <v-window-item value="tree">
          <div class="rrv-split">
            <div class="rrv-split-tree"><RevisionTreeView :review="review" /></div>
            <div class="rrv-split-panel"><RevisionReviewPanel :review="review" /></div>
          </div>
        </v-window-item>
        <v-window-item value="list">
          <RevisionDiffTable :review="review" />
        </v-window-item>
      </v-window>

      <div v-if="isDecidable" class="rrv-actions">
        <v-btn color="error" variant="tonal" :loading="rejectingAll" @click="rejectAllOpen = true">Отклонить всё</v-btn>
        <v-spacer />
        <v-btn color="primary" variant="flat" :disabled="!canApply" :loading="review.applying.value" @click="doApply(false)">
          Применить выбранное
        </v-btn>
      </div>
    </template>

    <v-dialog v-model="rejectAllOpen" max-width="480">
      <v-card>
        <v-card-title class="text-subtitle-1">Отклонить всю корректировку</v-card-title>
        <v-card-text>
          <v-textarea v-model="rejectAllComment" label="Комментарий (обязательно)" density="compact" rows="3" auto-grow />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="rejectAllOpen = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :disabled="!rejectAllComment.trim()" :loading="rejectingAll" @click="doRejectAll">Отклонить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 409 stale (п.9): значения изменили, пока корректировка ждала. -->
    <v-dialog v-model="staleDialog.open" max-width="560">
      <v-card>
        <v-card-title class="text-subtitle-1">Пока корректировка ждала, эти значения изменили</v-card-title>
        <v-card-text>
          <div v-for="(s, i) in staleDialog.ops" :key="i" class="rrv-stale-op">
            строка №{{ s.op_id }}: {{ staleOpSummary(s) }}
          </div>
          <div class="text-caption text-medium-emphasis mt-2">
            «Применить поверх» применит ваше решение, несмотря на эти изменения.
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="staleDialog.open = false">Отмена</v-btn>
          <v-btn color="warning" variant="flat" :loading="review.applying.value" @click="doApply(true)">Применить поверх</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
// Экран ПРОВЕРЯЮЩЕГО — волна 3C (02.10.2026). Маршрут
// /subsidies/:subsidyId/revisions/:revisionId (ведут «Мои задачи» и плашка в
// SubsidiesView.vue). Собирает воедино RevisionReviewPanel.vue (дерево
// «было/станет» + решения) и RevisionDiffTable.vue (плоский список) вокруг
// ОДНОГО состояния — useRevisionReview.ts (Правило №6, сама логика решений/
// применения здесь не дублируется, только вёрстка шапки/вкладок/диалогов).
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '@/api'
import { useRevisionReview } from '@/composables/subsidies/useRevisionReview'
import { formatOpChanges, formatBundleMoneyLine } from '@/composables/subsidies/revisionFormat'
import RevisionTreeView from '@/components/subsidies/RevisionTreeView.vue'
import RevisionReviewPanel from '@/components/subsidies/RevisionReviewPanel.vue'
import RevisionDiffTable from '@/components/subsidies/RevisionDiffTable.vue'

const route = useRoute()
const router = useRouter()

const revisionId = Number(route.params.revisionId)
const review = useRevisionReview(revisionId)
const loading = ref(true)
const subsidyName = ref<string | null>(null)
const tab = ref<'tree' | 'list'>('tree')
const rejectAllOpen = ref(false)
const rejectAllComment = ref('')
const rejectingAll = ref(false)
const outcomeMessage = ref<string | null>(null)
const staleDialog = ref<{ open: boolean; ops: Array<{ op_id: number; before: any; live: any }> }>({ open: false, ops: [] })

onMounted(async () => {
  loading.value = true
  await review.init()
  const subsidyId = review.detail.value?.subsidy_id
  if (subsidyId) {
    try {
      const sub = await apiFetch<{ name?: string }>(`/subsidies/${subsidyId}`)
      subsidyName.value = sub?.name || null
    } catch { /* название субсидии — не критично для работы экрана */ }
  }
  loading.value = false
})

const authorName = computed(() => review.detail.value?.author_name || 'автор')
const submittedAtLabel = computed(() => {
  const raw = review.detail.value?.submitted_at
  if (!raw) return '—'
  try { return new Date(raw).toLocaleString('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }) } catch { return raw }
})
const statusLabel = computed(() => {
  const s = review.detail.value?.status
  if (s === 'submitted') return 'на проверке'
  if (s === 'partially_decided') return 'часть решена'
  if (s === 'closed') return 'закрыта'
  return s || ''
})
const statusColor = computed(() => (review.detail.value?.status === 'closed' ? 'success' : 'orange'))
const isDecidable = computed(() => ['submitted', 'partially_decided'].includes(review.detail.value?.status || ''))

const problems = computed(() => review.overlay.preview.value?.problems || [])
const balanceShortfall = computed(() => review.overlay.preview.value?.balance?.shortfall || 0)
// Своё условие нехватки денег (приёмка 02.10, п.3) — НЕ завязано на problems:
// явный shortfall>0 ИЛИ can_apply===false (бэкенд может отказать по балансу,
// не положив ничего в problems, см. subsidy_revision_floor.py::compute_balance).
const hasShortfall = computed(() => balanceShortfall.value > 0.5 || review.overlay.preview.value?.balance?.can_apply === false)
// «Прибавлено»/«снято» — сумма по связкам (preview.bundles, тот же расчёт,
// что и в шапке связки RevisionReviewPanel.vue, Правило №6); без связок (вся
// нехватка вне связок) — прибавленное берём из дельты итогового «Запланировано».
const balanceAdded = computed(() => {
  const bundles = review.overlay.preview.value?.bundles || []
  if (bundles.length) return bundles.reduce((s, b) => s + (b.added || 0), 0)
  const before = review.overlay.preview.value?.before?.totals?.planned || 0
  const after = review.overlay.preview.value?.after?.totals?.planned || 0
  return Math.max(0, after - before)
})
const balanceRemoved = computed(() => (review.overlay.preview.value?.bundles || []).reduce((s, b) => s + (b.removed || 0), 0))
// Общий баннер нехватки — тот же язык «прибавлено/снято/из свободных денег
// субсидии → не хватает X» что и у шапки связки (RevisionReviewPanel.vue::
// bundleMoneyLine, Правило №6, formatBundleMoneyLine — общий форматер).
const balanceMoneyLine = computed(() => formatBundleMoneyLine(balanceAdded.value, balanceRemoved.value, balanceShortfall.value))
const canApply = computed(() => !!review.overlay.preview.value?.can_apply && review.pendingOps.value.length > 0)

function scrollToOp(opId: number | string) {
  document.querySelector<HTMLElement>(`[data-rev-op-id="${opId}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
// Было «формировали список ключей сырым JSON» (приёмка 02.10, п.8, тот же
// паттерн, что у RevisionDraftBar.vue/RevisionDiffTable.vue) — теперь ОДНА
// функция (formatOpChanges, revisionFormat.ts, Правило №6) на русских подписях,
// только РЕАЛЬНО различающиеся поля, без null-мусора.
function staleOpSummary(s: { before: any; live: any }): string {
  const changes = formatOpChanges({ op_type: 'update', before: s.before, after: s.live })
  if (!changes.length) return 'значения совпадают'
  return changes.map((c) => `${c.label}: было в черновике ${c.before}, сейчас в системе ${c.after}`).join('; ')
}
function goToSubsidy() {
  const id = review.detail.value?.subsidy_id
  router.push(id ? `/subsidies?sid=${id}` : '/subsidies')
}

async function doApply(force: boolean) {
  const res = await review.apply(force)
  if (res.ok) {
    staleDialog.value.open = false
    const applied = res.details?.applied?.length || 0
    const rejected = (res.details?.rejected?.length || 0) + (res.details?.auto_rejected?.length || 0)
    outcomeMessage.value = `Применено ${applied} строк, отклонено ${rejected}`
    return
  }
  if (res.code === 'stale') {
    staleDialog.value = { open: true, ops: res.details?.ops || [] }
  }
  // below_committed/balance/apply_error — problems уже видны через preview;
  // текст ошибки (review.error) показан баннером выше.
}

async function doRejectAll() {
  rejectingAll.value = true
  const res = await review.rejectAll(rejectAllComment.value)
  rejectingAll.value = false
  rejectAllOpen.value = false
  if (res.ok) {
    const rejected = (res.details?.rejected?.length || 0) + (res.details?.auto_rejected?.length || 0)
    outcomeMessage.value = `Применено 0 строк, отклонено ${rejected}`
  }
}
</script>

<style scoped>
.rrv-page { padding: 16px; max-width: 1200px; margin: 0 auto; }
.rrv-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 6px; }
.rrv-title { font-size: 16px; font-weight: 700; }
.rrv-author-comment { font-size: 13px; color: var(--crm-text-secondary); margin-bottom: 12px; }
.rrv-problems {
  background: rgba(220,38,38,0.06); border: 1px solid rgba(220,38,38,0.3);
  border-radius: 8px; padding: 8px 12px; margin-bottom: 12px; font-size: 12px;
}
.rrv-problem { padding: 2px 0; }
.rrv-actions { display: flex; align-items: center; gap: 8px; margin-top: 16px; position: sticky; bottom: 0; background: var(--crm-surface); padding: 10px 0; }
.rrv-stale-op { font-size: 13px; padding: 2px 0; }
.rrv-split { display: flex; gap: 14px; align-items: flex-start; }
.rrv-split-tree { flex: 2; min-width: 0; }
.rrv-split-panel { flex: 1; min-width: 300px; max-width: 460px; }
@media (max-width: 900px) {
  .rrv-split { flex-direction: column; }
  .rrv-split-panel { max-width: 100%; }
}
</style>
