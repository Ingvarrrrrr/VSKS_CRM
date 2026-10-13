<template>
  <!-- «Где взять деньги» (план .planning/quick/2026-10-05-funding-sources/PLAN.md,
       п.3) — смонтирован ОДИН РАЗ глобально в App.vue (как ApiErrorDialog/
       ToastContainer), открывается через useFundingSources().openFundingSources()
       из любого места: дерево ФЭО, панель подтверждений оплаты, форма закупки
       при 409 «ТЗ/договор над плановой позицией», карточка «Можно
       перераспределить». Данные/формулы — только с бэкенда (Правило №6). -->
  <v-dialog :model-value="f.show.value" max-width="720" :fullscreen="mobile" scrollable
    @update:model-value="(v: boolean) => { if (!v) f.closeFundingSources() }">
    <v-card>
      <v-card-title class="d-flex align-center text-subtitle-1 font-weight-bold px-4 pt-4">
        <v-icon icon="mdi-cash-sync" color="deep-purple" class="mr-2" />
        <span v-if="f.data.value && isClosed && f.data.value.target.kind === 'subsidy'">
          Превышение плана субсидии закрыто
        </span>
        <span v-else-if="f.data.value && isClosed">
          Превышение по «{{ f.data.value.target.name }}» закрыто
        </span>
        <span v-else-if="f.data.value && f.data.value.target.kind === 'subsidy'">
          Превышение плана субсидии {{ formatCurrency(f.data.value.need_amount) }} — где взять деньги
        </span>
        <span v-else-if="f.data.value">
          Превышение {{ formatCurrency(f.data.value.need_amount) }} по «{{ f.data.value.target.name }}» — где взять деньги
        </span>
        <span v-else>Где взять деньги</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="f.closeFundingSources()" />
      </v-card-title>
      <div v-if="f.data.value" class="px-4 text-caption text-medium-emphasis">
        <span v-if="f.data.value.scope.kind === 'branch'">ищем в направлении «{{ f.data.value.scope.name }}»</span>
        <span v-else>ищем по всей субсидии — у направлений нет своих лимитов</span>
      </div>
      <v-card-text class="px-4 pb-4" style="max-height:72vh">
        <div v-if="f.loading.value" class="d-flex align-center justify-center py-8">
          <v-progress-circular indeterminate color="deep-purple" class="mr-2" />
          <span class="text-body-2 text-medium-emphasis">Загрузка источников…</span>
        </div>
        <v-alert v-else-if="f.error.value" type="error" variant="tonal" density="compact" closable @click:close="f.closeFundingSources()">
          {{ f.error.value }}
        </v-alert>
        <template v-else-if="f.data.value">
          <!-- Превышение уже закрыто (после reduce need_amount ушёл в 0, либо
               владелец открыл окно по позиции, которая уже в норме) — список
               источников и кнопки «Уменьшить»/«Перенести» прячем, иначе легко
               снять с кого-то ещё лишнее (жалоба 13.10.2026, п.1). -->
          <v-alert v-if="isClosed" type="success" variant="tonal" density="comfortable">
            Превышение закрыто — больше ничего уменьшать не нужно.
          </v-alert>
          <div v-else-if="!f.data.value.groups.length" class="text-body-2 text-medium-emphasis py-6 text-center">
            Свободных незаконтрактованных остатков нет — превышение можно только согласовать или снизить сумму договора.
          </div>
          <template v-else>
            <div v-for="group in f.data.value.groups" :key="group.need_level" class="funding-sources-group mb-4">
              <v-chip
                size="small" variant="tonal" class="mb-2"
                :color="group.need_level === 'nice_to_have' ? 'deep-orange' : 'blue-grey'"
              >{{ group.label }}</v-chip>
              <v-card v-for="item in group.items" :key="item.planned_item_id" variant="outlined" class="pa-3 mb-2">
                <div class="d-flex align-center flex-wrap ga-2">
                  <div class="flex-grow-1" style="min-width:200px">
                    <div class="font-weight-medium">{{ item.name }}</div>
                    <div class="text-caption text-medium-emphasis funding-source-path" :title="item.category_path">{{ item.category_path }}</div>
                    <div class="text-caption text-medium-emphasis">не законтрактовано: {{ formatCurrency(item.residual) }}</div>
                  </div>
                  <v-text-field
                    :model-value="rowDraft(item)"
                    @update:model-value="(v: string) => onRowInput(item, v)"
                    @blur="onRowBlur(item)"
                    density="compact" variant="outlined" hide-details inputmode="decimal"
                    suffix="₽" style="max-width:160px"
                  />
                  <v-btn
                    size="small" color="deep-purple" variant="flat"
                    :loading="f.actingId.value === item.planned_item_id"
                    :disabled="!(f.rowAmounts[item.planned_item_id] > 0)"
                    @click="onReduce(item)"
                  >
                    <span v-if="f.data.value!.target.kind === 'planned_item'">
                      Перенести {{ formatCurrency(f.rowAmounts[item.planned_item_id] || 0) }} в «{{ f.data.value!.target.name }}»
                    </span>
                    <span v-else>Уменьшить на {{ formatCurrency(f.rowAmounts[item.planned_item_id] || 0) }}</span>
                  </v-btn>
                </div>
              </v-card>
            </div>
            <div class="mt-3">
              <div class="text-caption text-medium-emphasis mb-1">
                закрывает {{ formatCurrency(f.data.value.covered_amount) }} из {{ formatCurrency(f.data.value.need_amount) }} ₽
              </div>
              <v-progress-linear :model-value="f.progressPct.value" height="8" rounded color="deep-purple" bg-color="grey-lighten-3" />
            </div>
          </template>
        </template>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useDisplay } from 'vuetify'
import { useFundingSources, type FundingSourceItem } from '@/composables/subsidies/useFundingSources'
import { formatCurrency, roundMoney } from '@/composables/subsidies/format'
import { formatMoneyInput, parseNumber } from '@/utils/numberFormat'

const { mobile } = useDisplay()
const f = useFundingSources()

// Превышение закрыто (бэкенд отдал need_amount ~0) — единственная проверка,
// остальной шаблон на неё ориентируется (владелец, 13.10.2026).
const isClosed = computed(() => !!f.data.value && f.data.value.need_amount <= 0.005)

function clamp(v: number, max: number): number {
  if (v < 0) return 0
  if (v > max) return max
  return v
}

// Черновики денежного поля по planned_item_id — пока строка в фокусе,
// показываем буквально то, что набрал человек (та же причина, что у
// moneyFieldDisplay/moneyFieldOnInput/moneyFieldOnBlur в numberFormat.ts:
// переформатирование на каждый символ двигает курсор); на blur нормализуем
// в «257 971,82». Единственный денежный форматтер этого поля — formatMoneyInput/
// parseNumber, второй не заводим (Правило №6).
const drafts = reactive<Record<number, string | undefined>>({})

function rowDraft(item: FundingSourceItem): string {
  const d = drafts[item.planned_item_id]
  return d != null ? d : formatMoneyInput(f.rowAmounts[item.planned_item_id])
}

function onRowInput(item: FundingSourceItem, raw: string) {
  drafts[item.planned_item_id] = raw
  const n = parseNumber(raw)
  f.setRowAmount(item.planned_item_id, roundMoney(clamp(n ?? 0, item.residual)))
}

function onRowBlur(item: FundingSourceItem) {
  drafts[item.planned_item_id] = formatMoneyInput(f.rowAmounts[item.planned_item_id])
}

// После успешного переноса load() пересчитывает rowAmounts под новый
// актуальный остаток — черновик строки нужно сбросить, иначе поле продолжит
// показывать то, что было набрано ДО переноса (жалоба 13.10.2026, п.1).
async function onReduce(item: FundingSourceItem) {
  const id = item.planned_item_id
  await f.reduceFrom(item)
  delete drafts[id]
}
</script>

<style scoped>
.funding-source-path {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
