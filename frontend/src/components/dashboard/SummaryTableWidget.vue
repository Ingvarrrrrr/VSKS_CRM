<template>
  <div class="chart-card table-card" style="height:100%;overflow:auto">
    <div class="chart-card-header">
      <v-icon icon="mdi-table" size="18" color="#1976D2" class="mr-2" />
      <span class="chart-card-title">Детализация субсидий — {{ selectedYear }}</span>
      <div class="ml-auto d-flex align-center" style="gap: 12px;">
        <v-btn
          variant="tonal" color="primary" size="small"
          prepend-icon="mdi-chart-pie"
          @click="$emit('open-breakdown', 'budget')"
        >
          Аналитика
        </v-btn>
      </div>
    </div>

    <div v-if="filteredSubsidies.length > 0" class="px-3 pt-2 d-flex flex-column" style="gap:10px">
      <BudgetBar
        v-for="s in filteredSubsidies"
        :key="s.id"
        :subsidy="{
          id: s.id,
          name: s.name,
          budget: s.budget,
          planned: s.planned,
          contracted: s.contracted,
          paid: s.paid,
        }"
      />
    </div>

    <v-table density="compact" class="dash-table mt-3">
      <thead>
        <tr>
          <th>Субсидия</th>
          <th class="text-right">Бюджет</th>
          <th class="text-right">Запланировано</th>
          <th class="text-right text-caption">ФЭО план</th>
          <th class="text-right">Заказано</th>
          <th class="text-right">Оплачено</th>
          <th class="text-right">Остаток</th>
          <th style="width: 160px;" class="text-center">% освоения</th>
          <th style="width: 60px;"></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="s in filteredSubsidies" :key="s.id"
          class="table-row-hover"
          @click="$emit('open-breakdown', 'budget')"
          style="cursor: pointer;"
        >
          <td>
            <div class="font-weight-medium">{{ s.name }}</div>
            <div v-if="s.description" class="text-caption text-medium-emphasis">{{ s.description }}</div>
          </td>
          <td class="text-right font-weight-medium">{{ formatCurrency(s.budget) }}</td>
          <td class="text-right text-warning">{{ formatCurrency(s.plan_schedule) }}</td>
          <td class="text-right text-blue-grey">{{ formatCurrency(s.total_feo_planned ?? 0) }}</td>
          <td class="text-right text-primary">{{ formatCurrency(s.ordered) }}</td>
          <td class="text-right text-success">{{ formatCurrency(s.paid) }}</td>
          <td class="text-right" :class="(s.remaining ?? (s.budget - s.paid)) >= 0 ? 'text-success' : 'text-error'">
            {{ formatCurrency(s.remaining ?? (s.budget - s.paid)) }}
            <!-- Phase 31-05: discrepancy chip (D-15) -->
            <v-chip
              v-if="s.budget_discrepancy !== null && s.budget_discrepancy !== undefined && Math.abs(s.budget_discrepancy) > 0.01"
              color="#fb923c"
              size="x-small"
              class="ml-1"
              prepend-icon="mdi-alert"
              :title="'Расхождение суммы ФЭО-разбивки и плановой суммы субсидии'"
            >Δ {{ Math.abs(s.budget_discrepancy).toLocaleString('ru-RU', {maximumFractionDigits:0}) }} ₽</v-chip>
          </td>
          <td>
            <v-progress-linear
              :model-value="pct(s.paid, s.budget)" height="18"
              :color="progressColor(pct(s.paid, s.budget))" rounded
              class="gradient-progress"
            >
              <template #default>
                <span class="text-caption font-weight-bold">{{ pct(s.paid, s.budget) }}%</span>
              </template>
            </v-progress-linear>
          </td>
          <td>
            <v-btn icon="mdi-magnify" size="x-small" variant="text" @click.stop="$emit('open-breakdown', 'budget')" />
          </td>
        </tr>

        <tr class="total-row">
          <td><strong>ИТОГО</strong></td>
          <td class="text-right"><strong>{{ formatCurrency(totalBudget) }}</strong></td>
          <td class="text-right text-warning"><strong>{{ formatCurrency(totalPlanSchedule) }}</strong></td>
          <td class="text-right text-blue-grey"><strong>{{ formatCurrency(totalFeoPlanned) }}</strong></td>
          <td class="text-right text-primary"><strong>{{ formatCurrency(totalOrdered) }}</strong></td>
          <td class="text-right text-success"><strong>{{ formatCurrency(totalPaid) }}</strong></td>
          <td class="text-right" :class="totalRemaining >= 0 ? 'text-success' : 'text-error'">
            <strong>{{ formatCurrency(totalRemaining) }}</strong>
          </td>
          <td>
            <v-progress-linear
              :model-value="totalUsagePct" height="18"
              :color="progressColor(totalUsagePct)" rounded
              class="gradient-progress"
            >
              <template #default>
                <span class="text-caption font-weight-bold">{{ totalUsagePct }}%</span>
              </template>
            </v-progress-linear>
          </td>
          <td></td>
        </tr>
      </tbody>
    </v-table>
  </div>
</template>

<script setup lang="ts">
import BudgetBar from '@/components/BudgetBar.vue'

defineProps<{
  selectedYear: number
  filteredSubsidies: any[]
  totalBudget: number
  totalPlanSchedule: number
  totalFeoPlanned: number
  totalOrdered: number
  totalPaid: number
  totalRemaining: number
  totalUsagePct: number
  formatCurrency: (v: number) => string
  pct: (part: number, total: number) => number
  progressColor: (p: number) => string
}>()

defineEmits<{
  (e: 'open-breakdown', metric: string): void
}>()
</script>
