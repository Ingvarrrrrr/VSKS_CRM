<template>
  <v-dialog v-model="visible" fullscreen persistent transition="dialog-bottom-transition">
    <v-card>
      <v-toolbar color="primary" density="comfortable">
        <v-icon icon="mdi-swap-horizontal-bold" class="ml-4 mr-2" />
        <v-toolbar-title>Перенести закупки в другую субсидию</v-toolbar-title>
        <v-spacer />
        <v-btn icon="mdi-close" :disabled="transfer.applying.value" @click="close" />
      </v-toolbar>

      <v-card-text class="pa-4">
        <v-row dense>
          <v-col cols="12" md="4">
            <v-select
              v-model="targetSubsidyId" :items="targetOptions" item-title="name" item-value="id"
              label="Целевая субсидия" variant="outlined" density="compact"
              :disabled="transfer.loadingPreview.value || transfer.applying.value || !!applyResult"
              @update:model-value="onTargetChange"
            />
          </v-col>
          <v-col cols="12" md="4">
            <v-select
              v-model="stateFilter" :items="stateFilterOptions" multiple clearable chips
              label="Фильтр по состоянию" variant="outlined" density="compact"
            />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field
              v-model="search" label="Поиск по таблице" prepend-inner-icon="mdi-magnify" clearable
              variant="outlined" density="compact"
            />
          </v-col>
        </v-row>

        <div v-if="transfer.loadingPreview.value" class="d-flex align-center ga-2 py-6 justify-center">
          <v-progress-circular indeterminate size="28" />
          <span>Сравниваем закупки субсидий…</span>
        </div>

        <v-alert v-else-if="transfer.previewError.value" type="error" variant="tonal" density="compact">
          {{ transfer.previewError.value }}
        </v-alert>

        <template v-else-if="applyResult">
          <v-alert type="success" variant="tonal" density="compact" class="mb-3">
            Готово: скопировано {{ applyResult.copied.length }}, дополнено {{ applyResult.merged.length }},
            пропущено {{ applyResult.skipped }}.
          </v-alert>
          <v-alert
            v-for="(w, i) in applyResult.warnings || []" :key="'w' + i"
            type="warning" variant="tonal" density="compact" class="mb-2"
          >{{ w }}</v-alert>
          <div v-if="applyResult.copied.length" class="mb-2">
            <div class="text-subtitle-2 mb-1">Новые закупки</div>
            <div v-for="c in applyResult.copied" :key="c.new_id" class="text-body-2">
              {{ c.source_registry_number }} → {{ c.new_registry_number }}
              <v-btn size="x-small" variant="text" color="primary" @click="openOrder(c.new_id)">Открыть</v-btn>
            </div>
          </div>
          <div v-if="applyResult.merged.length">
            <div class="text-subtitle-2 mb-1">Дополненные закупки</div>
            <div v-for="m in applyResult.merged" :key="m.target_id" class="text-body-2">
              → {{ m.target_registry_number }}
              <v-btn size="x-small" variant="text" color="primary" @click="openOrder(m.target_id)">Открыть</v-btn>
            </div>
          </div>
        </template>

        <template v-else-if="transfer.preview.value">
          <div class="text-caption text-medium-emphasis mb-2">
            «{{ transfer.preview.value.source_subsidy.name }}» → «{{ transfer.preview.value.target_subsidy.name }}»,
            показано {{ filteredRows.length }} из {{ transfer.preview.value.rows.length }}
          </div>

          <div class="transfer-table-wrap">
            <v-table density="compact" fixed-header height="55vh">
              <thead>
                <tr>
                  <th style="min-width:220px">Закупка в «{{ transfer.preview.value.source_subsidy.name }}»</th>
                  <th style="min-width:260px">Пара в «{{ transfer.preview.value.target_subsidy.name }}»</th>
                  <th style="min-width:120px">Состояние</th>
                  <th style="min-width:220px">Действие</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in filteredRows" :key="row.source.id" :class="{ 'row--undecided': isUndecided(row) }">
                  <td>
                    <div class="font-weight-medium">{{ row.source.registry_number || '—' }}</div>
                    <div class="text-caption text-medium-emphasis">
                      {{ row.source.contractor_name || row.source.employee_name || '—' }}
                    </div>
                    <div class="text-caption">{{ formatMoney(row.source.amount) }} · {{ purchaseStatusLabel(row.source.status) || '—' }}</div>
                  </td>
                  <td>
                    <v-autocomplete
                      :model-value="transfer.targetPurchaseIdOf(row.source.id)"
                      :items="candidateItems(row)"
                      item-title="label" item-value="id"
                      label="Пара" density="compact" variant="outlined" clearable hide-details
                      @update:model-value="v => transfer.setTargetPurchase(row.source.id, v)"
                    />
                  </td>
                  <td>
                    <v-chip size="small" :color="stateColor(row.state)" variant="tonal">{{ stateLabel(row.state) }}</v-chip>
                  </td>
                  <td>
                    <v-select
                      :model-value="transfer.actionOf(row.source.id)"
                      :items="actionItems(row)"
                      density="compact" variant="outlined" hide-details
                      placeholder="Не выбрано"
                      @update:model-value="v => transfer.setAction(row.source.id, v)"
                    />
                    <div v-if="isUndecided(row)" class="text-caption text-warning mt-1">
                      Нужно решение — иначе строка не переносится
                    </div>
                  </td>
                </tr>
              </tbody>
            </v-table>
          </div>

          <div class="d-flex align-center ga-4 mt-3 flex-wrap">
            <span class="text-body-2">
              Будет скопировано {{ transfer.summary.value.copy }} / дополнено {{ transfer.summary.value.merge }} /
              пропущено {{ transfer.summary.value.skip }}
            </span>
            <span v-if="transfer.pendingCount.value" class="text-body-2 text-warning">
              Без решения: {{ transfer.pendingCount.value }}
            </span>
          </div>
        </template>
      </v-card-text>

      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <template v-if="applyResult">
          <v-btn variant="flat" color="primary" @click="close">Закрыть</v-btn>
        </template>
        <template v-else>
          <v-btn variant="text" :disabled="transfer.applying.value" @click="close">Отмена</v-btn>
          <v-btn
            variant="flat" color="primary" :loading="transfer.applying.value"
            :disabled="!transfer.preview.value"
            @click="doApply"
          >
            Применить
          </v-btn>
        </template>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Перенос закупок целой субсидии в другую — вызывается из SubsidyCardsGrid.vue/
// SubsidyListTable.vue (кнопка рядом со «Скопировать для эксперимента»,
// обработчик/ref в SubsidiesView.vue по образцу SubsidySandboxDialog.vue).
// Composable usePurchaseTransfer.ts — общий с PurchaseCopyToSubsidyDialog.vue
// (карточка одной закупки), здесь только таблица сравнения на всю ширину.
import { computed, ref } from 'vue'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'
import { formatMoney } from '@/utils/formatMoney'
import { purchaseStatusLabel } from '@/constants/purchaseStatus'
import { useToast } from '@/composables/useToast'
import {
  usePurchaseTransfer,
  type PurchaseTransferApplyResult,
  type PurchaseTransferRow,
  type PurchaseTransferRowState,
} from '@/composables/purchaseTransfer/usePurchaseTransfer'
import type { SubsidyRow } from '@/composables/subsidies/types'

const toast = useToast()
const transfer = usePurchaseTransfer()

const visible = ref(false)
const sourceSubsidy = ref<SubsidyRow | null>(null)
const targetSubsidyId = ref<number | null>(null)
const targetOptions = ref<{ id: number; name: string }[]>([])
const applyResult = ref<PurchaseTransferApplyResult | null>(null)

const search = ref('')
const stateFilterOptions = [
  { title: 'совпала', value: 'same' },
  { title: 'только сумма', value: 'amount_only' },
  { title: 'нет пары', value: 'none' },
]
const stateFilter = ref<PurchaseTransferRowState[]>([])

function stateLabel(state: PurchaseTransferRowState): string {
  return state === 'same' ? 'совпала' : state === 'amount_only' ? 'только сумма' : 'нет пары'
}
function stateColor(state: PurchaseTransferRowState): string {
  return state === 'same' ? 'success' : state === 'amount_only' ? 'warning' : 'grey'
}

function isUndecided(row: PurchaseTransferRow): boolean {
  return row.state === 'amount_only' && transfer.actionOf(row.source.id) === null
}

const filteredRows = computed(() => {
  const rows = transfer.preview.value?.rows ?? []
  const q = search.value.trim().toLowerCase()
  return rows.filter(row => {
    if (stateFilter.value.length && !stateFilter.value.includes(row.state)) return false
    if (!q) return true
    const hay = [
      row.source.registry_number, row.source.contractor_name, row.source.employee_name,
      String(row.source.amount ?? ''), row.match?.registry_number, row.match?.contractor_name,
    ].filter(Boolean).join(' ').toLowerCase()
    return hay.includes(q)
  })
})

function candidateItems(_row: PurchaseTransferRow) {
  const list = transfer.preview.value?.target_purchases ?? []
  return list.map(b => ({
    id: b.id,
    label: `${b.registry_number || b.id} · ${b.contractor_name || b.employee_name || '—'} · ${formatMoney(b.amount)}`,
  }))
}

function actionItems(row: PurchaseTransferRow) {
  const hasTarget = !!transfer.targetPurchaseIdOf(row.source.id)
  return [
    { title: 'Не переносить', value: 'skip' },
    { title: 'Дополнить', value: 'merge', props: { disabled: !hasTarget } },
    { title: 'Скопировать как новую', value: 'copy' },
  ]
}

async function loadTargetOptions() {
  try {
    const all = await apiFetch<{ id: number; name: string }[]>('/subsidies/')
    targetOptions.value = all.filter(s => s.id !== sourceSubsidy.value?.id)
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось загрузить список субсидий' }), 'error')
  }
}

async function onTargetChange(id: number | null) {
  applyResult.value = null
  if (!id || !sourceSubsidy.value) return
  try {
    await transfer.loadPreview(sourceSubsidy.value.id, id)
  } catch {
    // ошибка уже в transfer.previewError
  }
}

async function doApply() {
  if (!targetSubsidyId.value) return
  try {
    const result = await transfer.apply(targetSubsidyId.value)
    applyResult.value = result
    toast.addToast(
      `Перенос завершён: скопировано ${result.copied.length}, дополнено ${result.merged.length}, пропущено ${result.skipped}`,
      'success',
    )
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось перенести закупки' }), 'error')
  }
}

function openOrder(id: number) {
  window.open(`/orders/${id}/edit`, '_blank', 'noopener')
}

async function open(s: SubsidyRow) {
  sourceSubsidy.value = s
  targetSubsidyId.value = null
  applyResult.value = null
  search.value = ''
  stateFilter.value = []
  transfer.preview.value = null
  visible.value = true
  await loadTargetOptions()
}

function close() {
  visible.value = false
}

defineExpose({ open })
</script>

<style scoped>
.transfer-table-wrap {
  overflow-x: auto;
}
.row--undecided {
  background: rgba(251, 140, 0, 0.08);
}
</style>
