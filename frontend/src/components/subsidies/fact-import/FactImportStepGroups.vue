<template>
  <v-alert type="info" variant="tonal" density="compact" class="mb-3">
    Каждая карточка станет одной закупкой. Строку можно перенести в другую группу или выделить в отдельную.
  </v-alert>

  <v-checkbox v-if="hasAnyExistingDecisionNeeded" v-model="onlyNeedsDecision"
              label="Нужно решение" density="compact" hide-details class="mb-2" />

  <!-- Задание 07.10.2026 (п.5): карточки, где пропущены ВСЕ строки, не
       становятся закупкой — по умолчанию скрыты, не занимают место среди
       реальных закупок; владелец разворачивает их по кнопке, если нужно
       посмотреть, что туда попало и почему. -->
  <v-btn v-if="allSkippedGroups.length && !showAllSkipped" size="small" variant="text" color="primary"
    class="mb-2" @click="showAllSkipped = true">
    Ещё {{ allSkippedGroups.length }} {{ allSkippedGroups.length === 1 ? 'группа' : 'групп' }} только из
    пропущенных строк — показать
  </v-btn>

  <!-- Сводное предупреждение «нужно решение» для групп (тот же механизм, что
       на шаге «Строки» — useRowJump.ts, ПРАВИЛО №5/№6): чипы — номера строк
       файла, попавших в такие группы; клик скроллит к карточке группы,
       раскрывает «Строки группы» и подсвечивает саму строку. -->
  <v-alert v-if="decisionNeededRows.length" type="warning" variant="tonal" density="compact" class="mb-2">
    {{ rowsInPhrase(decisionNeededRows.length) }} закупка похожа на уже существующую — нужно решить, это та же
    закупка или новая (блок «Такая закупка уже есть» на карточке группы).
    <RowWarningChips :rows="decisionNeededRows" show-isolate-button :isolated="onlyNeedsDecision"
      @update:isolated="v => onlyNeedsDecision = v" />
  </v-alert>

  <v-progress-linear v-if="factImport.previewRefreshing" indeterminate color="teal" class="mb-2" />
  <div ref="groupsWrapRef">
  <v-row dense>
    <v-col v-for="g in filteredGroups" :key="g.key" cols="12" md="6">
      <v-card variant="outlined" class="fisg-card" :data-group-key="g.key"
        :class="{ 'fisg-card--needs-decision': g.needs_existing_decision, 'row-jump-flash': g.rows.includes(rowJumpState.highlightedRow ?? -1) }">
        <v-card-text>
          <div class="d-flex justify-space-between align-start">
            <div>
              <div class="font-weight-medium">{{ g.supplier || '(без поставщика)' }}</div>
              <div class="text-caption text-medium-emphasis">
                {{ g.purchase_no ? `№ ${g.purchase_no}` : g.category_path }}
              </div>
            </div>
            <v-chip size="small" variant="tonal" class="fisg-status-chip">{{ statusLabel(g.status) }}</v-chip>
          </div>
          <div class="d-flex ga-4 mt-2 text-body-2">
            <span>Договор: <strong>{{ fmt(g.contract_amount) }}</strong></span>
            <span>Оплачено: <strong>{{ fmt(g.paid_amount) }}</strong></span>
            <!-- Задание 07.10.2026 (п.5): «Строк: N» — только АКТИВНЫЕ
                 (не пропущенные), пропущенные — отдельной припиской, иначе
                 число не совпадает с тем, что реально станет закупкой. -->
            <span>
              Строк: {{ g.active_rows.length }}
              <template v-if="g.rows.length > g.active_rows.length">
                (+{{ g.rows.length - g.active_rows.length }} пропущено)
              </template>
            </span>
          </div>
          <v-alert v-if="g.warnings?.length" type="warning" variant="tonal" density="compact" class="mt-2">
            <div v-for="(w, i) in g.warnings" :key="i">{{ w }}</div>
          </v-alert>

          <FactImportExistingMatch v-if="g.existing_matches?.length" :group="g" :subsidy-id="factImport.subsidyId" />

          <!-- Дефект приёмки «Импорт факта» (02.10.2026): до ~46 карточек на
               шаге 4 — eager-load="false" откладывает GET /contractors/ до
               фокуса конкретного поля вместо того, чтобы все карточки грузили
               первую страницу разом на mount (см. комментарий в ContractorPicker.vue). -->
          <ContractorPicker
            class="mt-2"
            label="Поставщик (из справочника)"
            :model-value="factImport.decisions.supplier_overrides[g.key] ?? null"
            :eager-load="false"
            @update:model-value="v => onSupplierOverride(g.key, v)"
          />

          <v-expansion-panels class="mt-2" variant="accordion"
            :model-value="openGroupPanels[g.key] ?? undefined"
            @update:model-value="v => openGroupPanels[g.key] = (v as number | null)">
            <v-expansion-panel title="Строки группы">
              <template #text>
                <FactImportGroupRowsList :rows="g.rows" :group-key="g.key" :highlighted-row="rowJumpState.highlightedRow" />
              </template>
            </v-expansion-panel>
          </v-expansion-panels>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useFactImport } from '@/composables/subsidies/useFactImport'
import { useRowJump } from '@/composables/subsidies/useRowJump'
import ContractorPicker from '@/components/ContractorPicker.vue'
import FactImportExistingMatch from './FactImportExistingMatch.vue'
import FactImportGroupRowsList from './FactImportGroupRowsList.vue'
import RowWarningChips from './RowWarningChips.vue'
// ПРАВИЛО №6: подпись статуса закупки и формат суммы — общие источники.
import { purchaseStatusLabel } from '@/constants/purchaseStatus'
import { formatMoney } from '@/utils/formatMoney'
import { rowsInPhrase } from '@/utils/pluralize'

const { factImport, visibleGroups, setSupplierOverride, queuePreviewRefresh } = useFactImport()

function statusLabel(s?: string | null): string {
  return purchaseStatusLabel(s) || 'План закупок'
}

// 🟢🔵 «Нужно решение» (план breezy-mixing-lovelace.md, Часть А) — группы
// с «возможно» (same_supplier, сумма другая) без явного решения владельца;
// commit отклоняется, пока такие есть (см. backend commit.py, 400).
const onlyNeedsDecision = ref(false)
// Задание 07.10.2026 (п.5): карточки, где пропущены ВСЕ строки (all_skipped),
// не станут закупкой — по умолчанию скрыты отдельно от «Нужно решение».
const showAllSkipped = ref(false)
const allSkippedGroups = computed(() => visibleGroups.value.filter(g => g.all_skipped))
const hasAnyExistingDecisionNeeded = computed(() => visibleGroups.value.some(g => g.needs_existing_decision))
const filteredGroups = computed(() => {
  let groups = visibleGroups.value
  if (!showAllSkipped.value) groups = groups.filter(g => !g.all_skipped)
  if (onlyNeedsDecision.value) groups = groups.filter(g => g.needs_existing_decision)
  return groups
})
// Строки файла внутри групп, которым нужно решение — источник для чипов
// сводного предупреждения (тот же needs_existing_decision, которым уже
// помечена карточка группы, ПРАВИЛО №6).
const decisionNeededRows = computed(() =>
  visibleGroups.value.filter(g => g.needs_existing_decision).flatMap(g => g.rows))

// Раскрытая панель «Строки группы» на карточке — по умолчанию свёрнута,
// переход по чипу (ниже) раскрывает панель нужной группы перед скроллом.
const openGroupPanels = reactive<Record<string, number | null>>({})

function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return formatMoney(v)
}

function onSupplierOverride(groupKey: string, contractorId: number | null) {
  setSupplierOverride(groupKey, contractorId)
  queuePreviewRefresh()
}

// Переход «к строке» (useRowJump.ts, ЕДИНЫЙ механизм мастера, тот же, что в
// FactImportStepRows.vue) — чип в сводном предупреждении кладёт номер строки
// файла; здесь строка живёт внутри карточки группы, поэтому «показать»
// означает: снять фильтр «Нужно решение», если он скрывает карточку,
// раскрыть её панель «Строки группы» и только потом скроллить/подсвечивать.
const { state: rowJumpState, clearPendingRow, scrollToRowEl } = useRowJump()
const groupsWrapRef = ref<HTMLElement | null>(null)
watch(() => rowJumpState.pendingRow, (row) => {
  if (row == null) return
  const group = visibleGroups.value.find(g => g.rows.includes(row))
  if (group) {
    if (onlyNeedsDecision.value && !group.needs_existing_decision) onlyNeedsDecision.value = false
    if (group.all_skipped) showAllSkipped.value = true
    openGroupPanels[group.key] = 0
  }
  // Доп. пауза сверх nextTick — раскрытие v-expansion-panel анимируется и
  // рендерит своё содержимое (v-expansion-panel-text) не в тот же тик, что
  // смена model-value, обычного nextTick тут недостаточно.
  nextTick(() => {
    setTimeout(() => {
      scrollToRowEl(groupsWrapRef.value, row)
      clearPendingRow()
    }, 120)
  })
})
</script>

<style scoped>
.fisg-card { height: 100%; }
.fisg-card--needs-decision { border-color: rgb(var(--v-theme-warning)); }
/* Задание 07.10.2026 (п.5): чип статуса не сжимается, заголовок переносится
   вместо обрезки — жалоба владельца: чип «План закупок» обрезался. */
.fisg-status-chip { flex-shrink: 0; margin-left: 8px; }
.fisg-card .d-flex.justify-space-between > div:first-child { min-width: 0; overflow-wrap: anywhere; }
</style>
