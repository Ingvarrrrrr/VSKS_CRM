<template>
  <v-container>
    <v-row>
      <v-col cols="12">
        <v-card class="pa-6">
          <div class="d-flex justify-space-between align-center mb-6">
            <div>
              <v-card-title class="text-h4 mb-2">
                <v-icon icon="mdi-view-dashboard" class="mr-4" />Дашборд
              </v-card-title>
              <v-card-subtitle class="text-h6">
                Сводная информация по всем субсидиям
              </v-card-subtitle>
            </div>
            <v-btn 
              color="primary" 
              variant="outlined"
              prepend-icon="mdi-refresh"
              @click="loadData"
              :loading="loading"
            >
              Обновить
            </v-btn>
          </div>
          
          <!-- Фильтр по году -->
          <v-card variant="outlined" class="mb-6 pa-3">
            <div class="d-flex flex-column gap-4">
              <!-- Фильтр по году -->
              <div class="d-flex align-center gap-4">
                <v-chip-group v-model="selectedYear" mandatory>
                  <v-chip 
                    v-for="year in availableYears" 
                    :key="year" 
                    :value="year"
                    filter
                    variant="elevated"
                  >
                    {{ year }}
                  </v-chip>
                </v-chip-group>
                <v-spacer />
                <v-chip color="primary" variant="flat">
                  Субсидий: {{ filteredSubsidies.length }}
                </v-chip>
              </div>
              
              <!-- Выбор субсидий -->
              <div>
                <v-select
                  v-model="selectedSubsidyIds"
                  :items="allSubsidies.filter(s => s.year === selectedYear)"
                  item-title="name"
                  item-value="id"
                  label="Выберите субсидии для отображения"
                  variant="outlined"
                  multiple
                  chips
                  clearable
                  :hint="selectedSubsidyIds.length === 0 ? 'Все субсидии' : `Выбрано: ${selectedSubsidyIds.length}`"
                  persistent-hint
                  density="compact"
                >
                  <template v-slot:selection="{ item, index }">
                    <v-chip v-if="index < 2" size="small" class="mr-1">
                      <span>{{ item.title }}</span>
                    </v-chip>
                    <span v-if="index === 2" class="text-caption text-medium-emphasis">
                      +{{ selectedSubsidyIds.length - 2 }} ещё
                    </span>
                  </template>
                </v-select>
              </div>
            </div>
          </v-card>
          
          <!-- Сводная таблица -->
          <v-card variant="outlined" class="mb-8 pa-4">
            <div class="d-flex justify-space-between align-center mb-4">
              <v-card-title class="text-h6">Сводная по субсидиям</v-card-title>
              <v-btn 
                color="primary" 
                variant="text"
                @click="showAnalyticsDialog = true"
                prepend-icon="mdi-chart-pie"
              >
                Аналитика
              </v-btn>
            </div>
            
            <v-table>
              <thead>
                <tr>
                  <th>Субсидия</th>
                  <th>Общий бюджет</th>
                  <th>Законтрактовано</th>
                  <th>Оплачено</th>
                  <th>Остаток</th>
                  <th>% использования</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                <tr 
                  v-for="subsidy in filteredSubsidies" 
                  :key="subsidy.id"
                  style="cursor: pointer;"
                  @click="selectSubsidy(subsidy)"
                >
                  <td class="font-weight-medium">
                    <div>{{ subsidy.name }}</div>
                    <div class="text-caption text-medium-emphasis">{{ subsidy.description }}</div>
                  </td>
                  <td>
                    <div class="text-h6 font-weight-bold">{{ formatCurrency(subsidy.budget) }}</div>
                  </td>
                  <td>
                    <div class="text-h6 font-weight-bold text-info">{{ formatCurrency(subsidy.contracted) }}</div>
                    <div class="text-caption">{{ pct(subsidy.contracted, subsidy.budget) }}%</div>
                  </td>
                  <td>
                    <div class="text-h6 font-weight-bold text-success">{{ formatCurrency(subsidy.paid) }}</div>
                    <div class="text-caption">{{ pct(subsidy.paid, subsidy.budget) }}%</div>
                  </td>
                  <td>
                    <div 
                      class="text-h6 font-weight-bold" 
                      :class="subsidy.budget - subsidy.paid >= 0 ? 'text-success' : 'text-error'"
                    >
                      {{ formatCurrency(subsidy.budget - subsidy.paid) }}
                    </div>
                  </td>
                  <td>
                    <v-progress-linear
                      :model-value="pct(subsidy.paid, subsidy.budget)"
                      height="16"
                      :color="progressColor(pct(subsidy.paid, subsidy.budget))"
                      rounded
                    >
                      <template v-slot:default>
                        <span class="text-caption">{{ pct(subsidy.paid, subsidy.budget) }}%</span>
                      </template>
                    </v-progress-linear>
                  </td>
                  <td>
                    <v-btn icon="mdi-eye" variant="text" size="small" @click.stop="openSubsidyDetail(subsidy)" />
                    <v-btn icon="mdi-chart-bar" variant="text" size="small" @click.stop="openSubsidyChart(subsidy)" class="ml-1" />
                  </td>
                </tr>
                
                <tr class="font-weight-bold" style="background-color: rgba(0,0,0,0.03);">
                  <td>ИТОГО</td>
                  <td>{{ formatCurrency(totalBudget) }}</td>
                  <td>{{ formatCurrency(totalContracted) }}</td>
                  <td>{{ formatCurrency(totalPaid) }}</td>
                  <td :class="totalRemaining >= 0 ? 'text-success' : 'text-error'">{{ formatCurrency(totalRemaining) }}</td>
                  <td>
                    <v-progress-linear :model-value="totalUsagePct" height="16" :color="progressColor(totalUsagePct)" rounded>
                      <template v-slot:default><span class="text-caption">{{ totalUsagePct }}%</span></template>
                    </v-progress-linear>
                  </td>
                  <td></td>
                </tr>
              </tbody>
            </v-table>
          </v-card>
          
          <!-- 4 кликабельные карточки -->
          <v-row>
            <v-col v-for="card in summaryCards" :key="card.key" cols="12" md="6" lg="3">
              <v-card 
                :color="card.color" 
                variant="flat" 
                class="pa-4 dashboard-card"
                @click="openBreakdown(card.key)"
                style="cursor: pointer;"
              >
                <div class="d-flex justify-space-between align-start">
                  <div>
                    <div class="text-h6 text-white">{{ card.title }}</div>
                    <div class="text-h3 text-white font-weight-bold mt-2">{{ formatCurrency(card.value) }}</div>
                  </div>
                  <v-icon :icon="card.icon" color="white" size="40" />
                </div>
                <div class="text-caption text-white mt-2">{{ card.subtitle }}</div>
                <div class="text-caption text-white mt-1 font-italic">Нажмите для разбивки</div>
              </v-card>
            </v-col>
          </v-row>
          
          <v-divider class="my-8" />
          
          <!-- Графики -->
          <v-row>
            <!-- Визуальная разбивка бюджета -->
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="pa-4 h-100">
                <v-card-title class="text-h6 mb-4">Распределение бюджета</v-card-title>
                <div v-for="subsidy in filteredSubsidies" :key="'bar-'+subsidy.id" class="mb-3">
                  <div class="d-flex justify-space-between mb-1">
                    <span class="text-body-2 font-weight-medium">{{ subsidy.shortName }}</span>
                    <span class="text-body-2">{{ formatCurrency(subsidy.budget) }} ({{ pct(subsidy.budget, totalBudget) }}%)</span>
                  </div>
                  <v-progress-linear
                    :model-value="pct(subsidy.budget, totalBudget)"
                    height="24"
                    :color="subsidyColors[subsidy.id % subsidyColors.length]"
                    rounded
                    @click="selectSubsidy(subsidy)"
                    style="cursor: pointer;"
                  >
                    <template v-slot:default>
                      <span class="text-caption text-white font-weight-bold">{{ pct(subsidy.budget, totalBudget) }}%</span>
                    </template>
                  </v-progress-linear>
                </div>
              </v-card>
            </v-col>
            
            <!-- Последние заказы -->
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="pa-4 h-100">
                <div class="d-flex justify-space-between align-center mb-4">
                  <v-card-title class="text-h6">Последние заказы</v-card-title>
                  <v-btn color="primary" variant="text" to="/orders" prepend-icon="mdi-clipboard-list">Все заказы</v-btn>
                </div>
                <v-table density="compact">
                  <thead>
                    <tr>
                      <th>№</th>
                      <th>Наименование</th>
                      <th>Субсидия</th>
                      <th>Сумма</th>
                      <th>Статус</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="order in recentOrders" :key="order.id" style="cursor: pointer;" @click="viewOrder(order.id)">
                      <td>{{ order.number }}</td>
                      <td class="font-weight-medium">{{ order.name }}</td>
                      <td><v-chip size="x-small" color="info" variant="flat">{{ order.subsidy }}</v-chip></td>
                      <td>{{ formatCurrency(order.amount) }}</td>
                      <td><v-chip size="x-small" :color="order.statusColor">{{ order.status }}</v-chip></td>
                    </tr>
                  </tbody>
                </v-table>
              </v-card>
            </v-col>
          </v-row>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const loading = ref(false)
const selectedYear = ref(2025)
const selectedSubsidyIds = ref<number[]>([])
const selectedSubsidyId = ref<number | null>(null)

// Диалоги
const showBreakdownDialog = ref(false)
const showSubsidyDetailDialog = ref(false)
const showSubsidyChartDialog = ref(false)
const showAnalyticsDialog = ref(false)

const subsidyColors = ['primary', 'info', 'success', 'warning', 'error', 'purple', 'teal', 'deep-orange']

// ===== ДЕМО-ДАННЫЕ =====

interface Subsidy {
  id: number; name: string; shortName: string; description: string; year: number
  budget: number; contracted: number; paid: number; planned: number
}

const allSubsidies = ref<Subsidy[]>([
  {
    id: 1, name: 'Патриотика 2025', shortName: 'Патриотика', year: 2025,
    description: 'Патриотическое воспитание молодёжи',
    budget: 26_128_070, contracted: 18_450_000, paid: 12_840_200, planned: 3_200_000
  },
  {
    id: 2, name: 'ДНР Восстановление 2025', shortName: 'ДНР', year: 2025,
    description: 'Программа восстановления инфраструктуры',
    budget: 15_000_000, contracted: 11_200_000, paid: 8_600_000, planned: 2_100_000
  },
  {
    id: 3, name: 'ЗО Молодёжь 2025', shortName: 'ЗО', year: 2025,
    description: 'Запорожская область — молодёжные проекты',
    budget: 8_500_000, contracted: 5_100_000, paid: 3_200_000, planned: 1_800_000
  },
  {
    id: 4, name: 'ФАДМ Волонтёры 2025', shortName: 'ФАДМ', year: 2025,
    description: 'Волонтёрские программы и мероприятия',
    budget: 12_000_000, contracted: 9_600_000, paid: 7_100_000, planned: 1_400_000
  },
  {
    id: 5, name: 'МинПрос Образование 2025', shortName: 'МинПрос', year: 2025,
    description: 'Образовательные программы и гранты',
    budget: 19_500_000, contracted: 14_800_000, paid: 10_200_000, planned: 2_600_000
  },
])

const availableYears = computed(() => [...new Set(allSubsidies.value.map(s => s.year))].sort((a, b) => b - a))
const filteredSubsidies = computed(() => {
  let result = allSubsidies.value.filter(s => s.year === selectedYear.value)
  if (selectedSubsidyIds.value.length > 0) {
    result = result.filter(s => selectedSubsidyIds.value.includes(s.id))
  }
  return result
})

// Последние заказы (демо)
const recentOrders = computed(() => [
  { id: 1, number: 'ORD-2025-001', name: 'Оборудование для офиса', subsidy: 'Патриотика', amount: 450000, status: 'Подтвержден', statusColor: 'success' },
  { id: 2, number: 'ORD-2025-002', name: 'Канцелярские товары', subsidy: 'ДНР', amount: 125000, status: 'В работе', statusColor: 'info' },
  { id: 3, number: 'ORD-2025-003', name: 'IT оборудование', subsidy: 'ЗО', amount: 780000, status: 'Завершен', statusColor: 'primary' },
  { id: 4, number: 'ORD-2025-004', name: 'Мебель для переговорной', subsidy: 'ФАДМ', amount: 320000, status: 'Планируется', statusColor: 'warning' },
  { id: 5, number: 'ORD-2025-005', name: 'Волонтёрское оборудование', subsidy: 'ФАДМ', amount: 650000, status: 'Поставлено', statusColor: 'deep-purple' },
])

// ===== ВЫЧИСЛЯЕМЫЕ =====

const totalBudget = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.budget, 0))
const totalContracted = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.contracted, 0))
const totalPaid = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.paid, 0))
const totalRemaining = computed(() => totalBudget.value - totalPaid.value)
const totalUsagePct = computed(() => pct(totalPaid.value, totalBudget.value))

const selectedSubsidy = computed(() => filteredSubsidies.value.find(s => s.id === selectedSubsidyId.value) || null)

const summaryCards = computed(() => [
  { key: 'budget', title: 'Общий бюджет', value: totalBudget.value, color: 'primary', icon: 'mdi-chart-bar', subtitle: `${filteredSubsidies.value.length} субсидий` },
  { key: 'contracted', title: 'Законтрактовано', value: totalContracted.value, color: 'info', icon: 'mdi-file-document-check', subtitle: `${pct(totalContracted.value, totalBudget.value)}% от бюджета` },
  { key: 'paid', title: 'Оплачено', value: totalPaid.value, color: 'success', icon: 'mdi-cash-check', subtitle: `${pct(totalPaid.value, totalBudget.value)}% от бюджета` },
  { key: 'remaining', title: 'Остаток', value: totalRemaining.value, color: 'warning', icon: 'mdi-cash', subtitle: `${pct(totalRemaining.value, totalBudget.value)}% от бюджета` },
])

// ===== ФУНКЦИИ =====

function loadData() {
  loading.value = true
  setTimeout(() => {
    loading.value = false
  }, 1000)
}

function selectSubsidy(subsidy: Subsidy) {
  selectedSubsidyId.value = subsidy.id
}

function openBreakdown(key: string) {
  const fieldMap: Record<string, { title: string; icon: string; color: string }> = {
    budget: { title: 'Разбивка бюджета по субсидиям', icon: 'mdi-chart-bar', color: 'primary' },
    contracted: { title: 'Законтрактовано по субсидиям', icon: 'mdi-file-document-check', color: 'info' },
    paid: { title: 'Оплачено по субсидиям', icon: 'mdi-cash-check', color: 'success' },
    remaining: { title: 'Остаток по субсидиям', icon: 'mdi-cash', color: 'warning' },
  }
  
  const cfg = fieldMap[key]
  if (!cfg) return
  
  alert(`Разбивка: ${cfg.title}. Функция в разработке.`)
}

function openSubsidyDetail(subsidy: Subsidy) {
  alert(`Детализация субсидии: ${subsidy.name}`)
}

function openSubsidyChart(subsidy: Subsidy) {
  alert(`График субсидии: ${subsidy.name}`)
}

function viewOrder(orderId: number) {
  router.push(`/orders/${orderId}`)
}

function pct(part: number, total: number) {
  if (!total) return 0
  return Math.round((part / total) * 100)
}

function progressColor(percent: number) {
  if (percent > 90) return 'error'
  if (percent > 70) return 'warning'
  return 'primary'
}

function formatCurrency(amount: number) {
  return amount.toLocaleString('ru-RU') + ' ₽'
}

onMounted(() => {
  loadData()
})
</script>