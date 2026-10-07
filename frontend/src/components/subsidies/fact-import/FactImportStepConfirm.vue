<template>
  <v-alert type="warning" variant="tonal" density="compact" class="mb-3" icon="mdi-alert-circle-outline">
    Ничего ещё не записано. Проверьте итоги — после нажатия «Загрузить» будут созданы закупки и платежи.
    Уведомления и согласования при этом не запускаются.
  </v-alert>
  <!-- Доп. задача (владелец, 07.10.2026): «при импорте об этом должно идти
       уведомление» — предупреждение у строки уже есть (см. backend preview.py::
       paid_not_delivered_predicate), но на шаге итогов (эти плитки) его не
       видно, пока не прокрутишь все строки. Та же плашка, что и на дашборде
       (v-alert type="error"), над плитками — НАД, не вперемешку с ними,
       владелец должен увидеть её первой. -->
  <v-alert
    v-if="totals && totals.paid_not_delivered.count > 0"
    type="error"
    variant="tonal"
    density="compact"
    class="mb-3"
    icon="mdi-alert-decagram"
  >
    <div>
      Оплачено, но не поставлено: {{ totals.paid_not_delivered.count }}
      {{ rowsWord(totals.paid_not_delivered.count) }} на {{ fmt(totals.paid_not_delivered.amount) }} —
      статус в файле ниже «Поставлено», а оплата заполнена. После загрузки на дашборде будет
      «Оплачено больше, чем поставлено». Проверьте статус в файле или выберите его в строке.
    </div>
    <v-expansion-panels class="mt-2" variant="accordion">
      <v-expansion-panel>
        <v-expansion-panel-title class="text-caption">
          Показать строки ({{ totals.paid_not_delivered.count }})
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <ul class="mb-0 pl-4">
            <li v-for="r in totals.paid_not_delivered.rows" :key="r.row">
              Строка {{ r.row }}{{ r.name ? `, «${r.name}»` : '' }} — статус «{{ r.status_label }}», оплата {{ fmt(r.paid) }}
            </li>
          </ul>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>
  </v-alert>

  <v-row dense v-if="totals">
    <v-col cols="12" sm="6" md="3">
      <v-card variant="outlined"><v-card-text>
        <div class="text-caption text-medium-emphasis">Строк</div>
        <div class="text-h6">{{ totals.rows }}</div>
      </v-card-text></v-card>
    </v-col>
    <v-col cols="12" sm="6" md="3">
      <v-card variant="outlined"><v-card-text>
        <div class="text-caption text-medium-emphasis">Закупок</div>
        <div class="text-h6">{{ totals.purchases }}</div>
      </v-card-text></v-card>
    </v-col>
    <v-col cols="12" sm="6" md="3">
      <v-card variant="outlined"><v-card-text>
        <div class="text-caption text-medium-emphasis">Договоров на сумму</div>
        <div class="text-h6">{{ fmt(totals.contract_amount) }}</div>
      </v-card-text></v-card>
    </v-col>
    <v-col cols="12" sm="6" md="3">
      <v-card variant="outlined"><v-card-text>
        <div class="text-caption text-medium-emphasis">Оплачено (по отметке)</div>
        <div class="text-h6">{{ fmt(totals.paid_amount) }}</div>
      </v-card-text></v-card>
    </v-col>
  </v-row>
  <!-- Задание 07.10.2026 (п.4/п.6, чек-лист владельца): «из чего сложились
       итоги» — по статусам, Σ == плиткам выше (totals.breakdown считается
       бэкендом В ОДНОМ цикле с totals, ПРАВИЛО №6 — здесь только показ).
       Старая плашка «Пропущено строк: N» заменена разделом «Пропущено»
       ниже, с раскрытием по причине и номерами строк. -->
  <FactImportBreakdownTable v-if="totals" :totals="totals" @go-to-row="goToRow" />

  <!-- 🟢 Задача B («Оплачено, но уже в закупке», 07.10.2026) — закупки,
       которые НЕ создаются заново, а обновляются по статусу/оплате из
       файла. Подписи статусов — statusLabel(), тот же словарь из
       preview.statuses, второго справочника на фронте не заводим. -->
  <v-alert v-if="existingUpdates.length" type="info" variant="tonal" density="compact" class="mt-3">
    <div>Обновятся существующие закупки: {{ existingUpdates.length }}</div>
    <ul class="mt-1 mb-0 pl-4">
      <li v-for="u in existingUpdates" :key="u.purchase_id">
        {{ u.registry_number || `#${u.purchase_id}` }}:
        «{{ statusLabel(u.status_from) }}» → «{{ statusLabel(u.status_to) }}»<template v-if="u.paid_add > 0">, оплата +{{ fmt(u.paid_add) }}</template>
      </li>
    </ul>
  </v-alert>

  <p class="text-caption text-medium-emphasis mt-3">
    Оплата из таблицы попадёт как отметка человека. Подтверждённой станет после загрузки выписки
    банка/казначейства и сопоставления.
  </p>
</template>

<script setup lang="ts">
import { nextTick } from 'vue'
import { useFactImport } from '@/composables/subsidies/useFactImport'
import { useRowJump } from '@/composables/subsidies/useRowJump'
import FactImportBreakdownTable from './FactImportBreakdownTable.vue'
// ПРАВИЛО №6: формат суммы — общий хелпер, не своя копия Intl.NumberFormat.
import { formatMoney } from '@/utils/formatMoney'
const { factImport, totals, existingUpdates, statusLabel } = useFactImport()
const { jumpToRow } = useRowJump()
function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return formatMoney(v)
}

// Задание 07.10.2026 (п.10): клик по номеру строки в разбивке «Пропущено» —
// назад на шаг 3 (строки) и переход к строке (useRowJump, ЕДИНЫЙ механизм
// мастера). nextTick — шаг 3 должен успеть смонтироваться и повесить свой
// watch(pendingRow) ПЕРЕД тем, как jumpToRow положит туда номер строки.
function goToRow(row: number) {
  factImport.step = 3
  nextTick(() => jumpToRow(row))
}
// Склонение «строка/строки/строк» для плашки paid_not_delivered выше.
function rowsWord(n: number): string {
  const mod100 = Math.abs(n) % 100
  const mod10 = mod100 % 10
  if (mod100 >= 11 && mod100 <= 14) return 'строк'
  if (mod10 === 1) return 'строка'
  if (mod10 >= 2 && mod10 <= 4) return 'строки'
  return 'строк'
}
</script>
