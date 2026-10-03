<template>
  <v-alert type="info" variant="tonal" density="compact" class="mb-3">
    Каждая карточка станет одной закупкой. Строку можно перенести в другую группу или выделить в отдельную.
  </v-alert>

  <v-checkbox v-if="hasAnyExistingDecisionNeeded" v-model="onlyNeedsDecision"
              label="Нужно решение" density="compact" hide-details class="mb-2" />

  <v-progress-linear v-if="factImport.previewRefreshing" indeterminate color="teal" class="mb-2" />
  <v-row dense>
    <v-col v-for="g in filteredGroups" :key="g.key" cols="12" md="6">
      <v-card variant="outlined" class="fisg-card" :class="{ 'fisg-card--needs-decision': g.needs_existing_decision }">
        <v-card-text>
          <div class="d-flex justify-space-between align-start">
            <div>
              <div class="font-weight-medium">{{ g.supplier || '(без поставщика)' }}</div>
              <div class="text-caption text-medium-emphasis">
                {{ g.purchase_no ? `№ ${g.purchase_no}` : g.category_path }}
              </div>
            </div>
            <v-chip size="small" variant="tonal">{{ g.status }}</v-chip>
          </div>
          <div class="d-flex ga-4 mt-2 text-body-2">
            <span>Договор: <strong>{{ fmt(g.contract_amount) }}</strong></span>
            <span>Оплачено: <strong>{{ fmt(g.paid_amount) }}</strong></span>
            <span>Строк: {{ g.rows.length }}</span>
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

          <v-expansion-panels class="mt-2" variant="accordion">
            <v-expansion-panel title="Строки группы">
              <template #text>
                <div v-for="rn in g.rows" :key="rn" class="d-flex align-center ga-2 mb-1">
                  <span class="text-caption">Стр. {{ rn }}</span>
                  <v-select
                    density="compact" variant="outlined" hide-details style="max-width:220px"
                    :items="otherGroupOptions(g.key)"
                    label="Перенести в…"
                    @update:model-value="v => v && moveRow(rn, v)"
                  />
                </div>
              </template>
            </v-expansion-panel>
          </v-expansion-panels>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useFactImport } from '@/composables/subsidies/useFactImport'
import ContractorPicker from '@/components/ContractorPicker.vue'
import FactImportExistingMatch from './FactImportExistingMatch.vue'

const { factImport, visibleGroups, setSupplierOverride, moveRowToGroup, queuePreviewRefresh } = useFactImport()

// 🟢🔵 «Нужно решение» (план breezy-mixing-lovelace.md, Часть А) — группы
// с «возможно» (same_supplier, сумма другая) без явного решения владельца;
// commit отклоняется, пока такие есть (см. backend commit.py, 400).
const onlyNeedsDecision = ref(false)
const hasAnyExistingDecisionNeeded = computed(() => visibleGroups.value.some(g => g.needs_existing_decision))
const filteredGroups = computed(() =>
  onlyNeedsDecision.value ? visibleGroups.value.filter(g => g.needs_existing_decision) : visibleGroups.value,
)

function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(v)
}

function otherGroupOptions(exceptKey: string) {
  const items = visibleGroups.value
    .filter(g => g.key !== exceptKey)
    .map(g => ({ title: g.supplier || g.category_path || g.key, value: g.key }))
  items.push({ title: '— выделить в отдельную закупку —', value: 'new' })
  return items
}

// 🔵 правка 3: тот же debounce, что и в StepRows.vue (queuePreviewRefresh) —
// перенос нескольких строк подряд не шлёт файл на каждый клик.
function moveRow(row: number, targetKey: string) {
  moveRowToGroup(row, targetKey)
  queuePreviewRefresh()
}

function onSupplierOverride(groupKey: string, contractorId: number | null) {
  setSupplierOverride(groupKey, contractorId)
  queuePreviewRefresh()
}
</script>

<style scoped>
.fisg-card { height: 100%; }
.fisg-card--needs-decision { border-color: rgb(var(--v-theme-warning)); }
</style>
