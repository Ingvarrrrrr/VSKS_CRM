<template>
  <div class="kpi-toggle-row">
    <v-btn-toggle v-model="kpiPrefs.kpiTypeSplit.value" mandatory density="compact" color="primary" class="kpi-split-toggle">
      <v-btn value="total" size="small">Целиком</v-btn>
      <v-btn value="split" size="small">Товары и услуги</v-btn>
    </v-btn-toggle>
  </div>
  <v-row v-if="loading" class="kpi-row" style="margin:0">
    <v-col cols="6" sm="4" lg="3" xl="auto" style="flex:1" v-for="n in 9" :key="'skel-'+n">
      <v-skeleton-loader type="card" height="100" class="rounded-lg" />
    </v-col>
  </v-row>
  <v-row v-else class="kpi-row" style="margin:0">
    <v-col cols="6" sm="4" lg="3" xl="auto" style="flex:1" v-for="card in kpiCards" :key="card.key">
      <v-tooltip :text="card.tooltip ?? undefined" location="bottom" :disabled="!card.tooltip">
        <template #activator="{ props: tip }">
          <div v-bind="tip" class="kpi-card" :class="['kpi-' + card.key, { 'kpi-over': card.over }]" @click="$emit('kpi-click', card.key)">
            <div class="kpi-icon-box">
              <v-icon :icon="card.icon" size="26" />
            </div>
            <div class="kpi-body">
              <div class="kpi-value">{{ mobile ? formatCurrencyShort(card.amount) : formatCurrency(card.amount) }}</div>
              <div class="kpi-label">{{ card.label }}</div>
              <div class="kpi-count" v-if="card.count > 0">{{ card.count }} {{ card.countLabel }}</div>
              <div class="kpi-monthly" v-if="card.monthly !== null">
                в т.ч. ежемесячные платежи: {{ formatCurrencyShort(card.monthly!) }} /мес
              </div>
              <!-- Раздел C (план ancient-prancing-music.md, 21.09): две строки товары/
                   услуги (+ «без типа», если не ноль) при включённом переключателе —
                   card.split приходит готовым из useDashboardData.ts (единственный
                   источник расчёта), здесь только отрисовка и клик-фильтр. -->
              <div v-if="isSplit" class="kpi-split-rows" @click.stop>
                <template v-if="card.split">
                  <div
                    v-for="row in splitRows(card.split)"
                    :key="row.kind"
                    class="kpi-split-row"
                    :class="{
                      'kpi-split-row-clickable': hasStageDrill(card.key),
                      'kpi-split-row-active': hasStageDrill(card.key) && isActiveRow(card.key, row.kind),
                      'kpi-split-row-neg': row.amount < -0.5,
                    }"
                    @click="hasStageDrill(card.key) && onRowClick(card.key, row.kind)"
                  >
                    <span class="kpi-split-dot" :class="'kpi-split-dot-' + row.kind" />
                    <span class="kpi-split-text">{{ row.label }} {{ fmtSplit(Math.abs(row.amount)) }}</span>
                  </div>
                </template>
                <div v-else class="kpi-split-loading text-caption">загрузка по типам…</div>
              </div>
            </div>
          </div>
        </template>
      </v-tooltip>
    </v-col>
  </v-row>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useKpiPrefs } from '@/composables/useKpiPrefs'
import { KIND_LABELS, hasStageDrill, type ItemTypeKind } from '@/utils/itemTypeKind'

const props = defineProps<{
  loading: boolean
  mobile: boolean
  kpiCards: any[]
  formatCurrency: (v: number) => string
  formatCurrencyShort: (v: number) => string
}>()

const emit = defineEmits<{
  (e: 'kpi-click', key: string): void
  (e: 'type-row-click', payload: { stage: string; kind: ItemTypeKind; active: boolean }): void
}>()

const kpiPrefs = useKpiPrefs()
const isSplit = computed(() => kpiPrefs.kpiTypeSplit.value === 'split')

interface SplitRow { kind: ItemTypeKind; label: string; amount: number }

function splitRows(split: { goods: number; services: number; unspecified: number }): SplitRow[] {
  const rows: SplitRow[] = [
    { kind: 'goods', label: KIND_LABELS.goods, amount: split.goods },
    { kind: 'services', label: KIND_LABELS.services, amount: split.services },
  ]
  if (Math.abs(split.unspecified) > 0.5) {
    rows.push({ kind: 'unspecified', label: KIND_LABELS.unspecified, amount: split.unspecified })
  }
  return rows
}

function isActiveRow(stage: string, kind: ItemTypeKind): boolean {
  const f = kpiPrefs.activeTypeFilter.value
  return !!f && f.stage === stage && f.kind === kind
}

function onRowClick(stage: string, kind: ItemTypeKind) {
  const active = kpiPrefs.toggleTypeFilter(stage, kind)
  emit('type-row-click', { stage, kind, active })
}

function fmtSplit(v: number): string {
  return props.mobile ? props.formatCurrencyShort(v) : props.formatCurrency(v)
}
</script>

<style scoped>
.kpi-toggle-row {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}
.kpi-split-rows {
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.kpi-split-row {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  line-height: 1.3;
  padding: 1px 4px;
  border-radius: 4px;
  cursor: default;
  opacity: 0.85;
  transition: background 0.15s, opacity 0.15s;
}
.kpi-split-row-clickable {
  cursor: pointer;
}
.kpi-split-row-clickable:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.05);
}
.kpi-split-row-active {
  opacity: 1;
  background: rgba(251, 146, 60, 0.16);
  outline: 1px solid rgba(251, 146, 60, 0.5);
}
.kpi-split-row-neg {
  color: #EF4444;
}
.kpi-split-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
}
.kpi-split-dot-goods { background: #3B82F6; }
.kpi-split-dot-services { background: #A855F7; }
.kpi-split-dot-unspecified { background: #94A3B8; }
.kpi-split-loading {
  opacity: 0.6;
}
</style>
