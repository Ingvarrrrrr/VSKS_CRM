<template>
  <v-alert type="warning" variant="tonal" density="compact" class="mb-3" icon="mdi-alert-circle-outline">
    Ничего ещё не записано. Проверьте итоги — после нажатия «Загрузить» будут созданы закупки и платежи.
    Уведомления и согласования при этом не запускаются.
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
  <v-alert v-if="totals && totals.skipped > 0" type="info" variant="tonal" density="compact" class="mt-3">
    Пропущено строк: {{ totals.skipped }}
  </v-alert>
  <p class="text-caption text-medium-emphasis mt-3">
    Оплата из таблицы попадёт как отметка человека. Подтверждённой станет после загрузки выписки
    банка/казначейства и сопоставления.
  </p>
</template>

<script setup lang="ts">
import { useFactImport } from '@/composables/subsidies/useFactImport'
const { totals } = useFactImport()
function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(v)
}
</script>
