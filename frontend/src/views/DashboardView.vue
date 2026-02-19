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
            
            <div>
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
          </div>
          
          <!-- Сводная таблица по всем субсидиям -->
          <v-card variant="outlined" class="mb-8 pa-4">
            <div class="d-flex justify-space-between align-center mb-4">
              <v-card-title class="text-h6">
                Сводная по субсидиям
              </v-card-title>
              <v-btn 
                color="primary" 
                variant="text"
                @click="showSubsidyAnalytics"
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
                <tr v-for="subsidy in subsidies" :key="subsidy.id">
                  <td class="font-weight-medium">
                    <div>{{ subsidy.name }}</div>
                    <div class="text-caption text-medium-emphasis">{{ subsidy.description || 'Без описания' }}</div>
                  </td>
                  <td>
                    <div class="text-h6 font-weight-bold">{{ formatCurrency(subsidy.budget || 0) }}</div>
                    <div class="text-caption">Бюджет</div>
                  </td>
                  <td>
                    <div class="text-h6 font-weight-bold text-info">{{ formatCurrency(subsidy.contracted || 0) }}</div>
                    <div class="text-caption">{{ calculatePercent(subsidy.contracted, subsidy.budget) }}% от бюджета</div>
                  </td>
                  <td>
                    <div class="text-h6 font-weight-bold text-success">{{ formatCurrency(subsidy.paid || 0) }}</div>
                    <div class="text-caption">{{ calculatePercent(subsidy.paid, subsidy.budget) }}% от бюджета</div>
                  </td>
                  <td>
                    <div 
                      class="text-h6 font-weight-bold" 
                      :class="getRemainingColor(subsidy.budget - (subsidy.paid || 0))"
                    >
                      {{ formatCurrency((subsidy.budget || 0) - (subsidy.paid || 0)) }}
                    </div>
                    <div class="text-caption">Остаток</div>
                  </td>
                  <td>
                    <v-progress-linear
                      :model-value="calculatePercent(subsidy.paid, subsidy.budget)"
                      height="16"
                      :color="getProgressColor(calculatePercent(subsidy.paid, subsidy.budget))"
                      rounded
                    >
                      <template v-slot:default>
                        <span class="text-caption">{{ calculatePercent(subsidy.paid, subsidy.budget) }}%</span>
                      </template>
                    </v-progress-linear>
                  </td>
                  <td>
                    <v-btn
                      icon="mdi-eye"
                      variant="text"
                      size="small"
                      @click="viewSubsidyDetails(subsidy)"
                      title="Просмотреть детали"
                    />
                    <v-btn
                      icon="mdi-chart-bar"
                      variant="text"
                      size="small"
                      @click="viewSubsidyAnalytics(subsidy)"
                      title="Аналитика"
                      class="ml-1"
                    />
                  </td>
                </tr>
                
                <!-- Итоговая строка -->
                <tr class="font-weight-bold" style="background-color: rgba(0, 0, 0, 0.02);">
                  <td>ИТОГО</td>
                  <td>{{ formatCurrency(totalBudget) }}</td>
                  <td>{{ formatCurrency(totalContracted) }}</td>
                  <td>{{ formatCurrency(totalPaid) }}</td>
                  <td :class="totalRemaining >= 0 ? 'text-success' : 'text-error'">
                    {{ formatCurrency(totalRemaining) }}
                  </td>
                  <td>
                    <v-progress-linear
                      :model-value="totalUsagePercent"
                      height="16"
                      :color="getProgressColor(totalUsagePercent)"
                      rounded
                    >
                      <template v-slot:default>
                        <span class="text-caption">{{ totalUsagePercent }}%</span>
                      </template>
                    </v-progress-linear>
                  </td>
                  <td></td>
                </tr>
              </tbody>
            </v-table>
          </v-card>
          
          <v-row>
            <!-- Карточка Общий бюджет -->
            <v-col cols="12" md="6" lg="3">
              <v-card 
                color="primary" 
                variant="flat" 
                class="pa-4 dashboard-card"
                @click="showBudgetBreakdown"
                style="cursor: pointer;"
              >
                <div class="d-flex justify-space-between align-start">
                  <div>
                    <div class="text-h6 text-white">Общий бюджет</div>
                    <div class="text-h3 text-white font-weight-bold mt-2">
                      {{ formatCurrency(totalBudget) }}
                    </div>
                  </div>
                  <v-icon icon="mdi-chart-bar" color="white" size="40" />
                </div>
                <div class="text-caption text-white mt-2">
                  По всем субсидиям
                </div>
                <div class="text-caption text-white mt-1">
                  Нажмите для разбивки по субсидиям
                </div>
              </v-card>
            </v-col>
            
            <!-- Карточка Законтрактовано -->
            <v-col cols="12" md="6" lg="3">
              <v-card 
                color="info" 
                variant="flat" 
                class="pa-4 dashboard-card"
                @click="showContractedBreakdown"
                style="cursor: pointer;"
              >
                <div class="d-flex justify-space-between align-start">
                  <div>
                    <div class="text-h6 text-white">Законтрактовано</div>
                    <div class="text-h3 text-white font-weight-bold mt-2">
                      {{ formatCurrency(totalContracted) }}
                    </div>
                  </div>
                  <v-icon icon="mdi-file-document-check" color="white" size="40" />
                </div>
                <div class="text-caption text-white mt-2">
                  {{ calculatePercent(totalContracted, totalBudget) }}% от бюджета
                </div>
                <div class="text-caption text-white mt-1">
                  Нажмите для деталей
                </div>
              </v-card>
            </v-col>
            
            <!-- Карточка Оплачено -->
            <v-col cols="12" md="6" lg="3">
              <v-card 
                color="success" 
                variant="flat" 
                class="pa-4 dashboard-card"
                @click="showPaidBreakdown"
                style="cursor: pointer;"
              >
                <div class="d-flex justify-space-between align-start">
                  <div>
                    <div class="text-h6 text-white">Оплачено</div>
                    <div class="text-h3 text-white font-weight-bold mt-2">
                      {{ formatCurrency(totalPaid) }}
                    </div>
                  </div>
                  <v-icon icon="mdi-cash-check" color="white" size="40" />
                </div>
                <div class="text-caption text-white mt-2">
                  {{ calculatePercent(totalPaid, totalBudget) }}% от бюджета
                </div>
                <div class="text-caption text-white mt-1">
                  Нажмите для деталей
                </div>
              </v-card>
            </v-col>
            
            <!-- Карточка Остаток -->
            <v-col cols="12" md="6" lg="3">
              <v-card 
                color="warning" 
                variant="flat" 
                class="pa-4 dashboard-card"
                @click="showRemainingBreakdown"
                style="cursor: pointer;"
              >
                <div class="d-flex justify-space-between align-start">
                  <div>
                    <div class="text-h6 text-white">Остаток</div>
                    <div class="text-h3 text-white font-weight-bold mt-2">
                      {{ formatCurrency(totalRemaining) }}
                    </div>
                  </div>
                  <v-icon icon="mdi-cash" color="white" size="40" />
                </div>
                <div class="text-caption text-white mt-2">
                  {{ calculatePercent(totalRemaining, totalBudget) }}% от бюджета
                </div>
                <div class="text-caption text-white mt-1">
                  Нажмите для деталей
                </div>
              </v-card>
            </v-col>
          </v-row>
          
          <v-divider class="my-8" />
          
          <!-- Диаграмма распределения бюджета -->
          <v-row>
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="pa-4 h-100">
                <v-card-title class="text-h6 mb-4">
                  Распределение бюджета по субсидиям
                </v-card-title>
                <div class="text-center py-8" v-if="!hasBudgetData">
                  <v-icon icon="mdi-chart-pie" size="64" class="mb-4 text-medium-emphasis" />
                  <div class="text-body-1 text-medium-emphasis">Нет данных для отображения</div>
                </div>
                <div v-else class="text-center">
                  <!-- Здесь можно добавить диаграмму -->
                  <div class="d-flex flex-wrap justify-center gap-4">
                    <div v-for="subsidy in subsidies" :key="subsidy.id" class="text-center">
                      <div class="text-caption">{{ subsidy.shortName || subsidy.name }}</div>
                      <div class="text-h6 font-weight-bold">{{ formatCurrency(subsidy.budget || 0) }}</div>
                      <div class="text-caption">{{ calculatePercent(subsidy.budget, totalBudget) }}%</div>
                    </div>
                  </div>
                </div>
              </v-card>
            </v-col>
            
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="pa-4 h-100">
                <div class="d-flex justify-space-between align-center mb-4">
                  <v-card-title class="text-h6">
                    Последние заказы
                  </v-card-title>
                  <v-btn 
                    color="primary" 
                    variant="text"
                    to="/orders"
                    prepend-icon="mdi-clipboard-list"
                  >
                    Все заказы
                  </v-btn>
                </div>
                
                <v-table>
                  <thead>
                    <tr>
                      <th>№</th>
                      <th>Наименование</th>
                      <th>Субсидия</th>
                      <th>Сумма</th>
                      <th>Статус</th>
                      <th>Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="order in recentOrders" :key="order.id">
                      <td>{{ order.number }}</td>
                      <td class="font-weight-medium">{{ order.name }}</td>
                      <td>
                        <v-chip size="small" color="info" variant="flat">
                          {{ order.subsidy }}
                        </v-chip>
                      </td>
                      <td>{{ formatCurrency(order.amount) }}</td>
                      <td>
                        <v-chip size="small" :color="order.statusColor">
                          {{ order.status }}
                        </v-chip>
                      </td>
                      <td>
                        <v-btn
                          icon="mdi-eye"
                          variant="text"
                          size="small"
                          @click="viewOrder(order.id)"
                          title="Просмотреть заказ"
                        />
                      </td>
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

interface Subsidy {
  id: number
  name: string
  description?: string
  budget?: number
  contracted?: number
  paid?: number
  shortName?: string
}

const subsidies = ref<Subsidy[]>([])
const recentOrders = ref([
  { 
    id: 1, 
    number: 'ORD-2025-001', 
    name: 'Ноутбуки Lenovo', 
    subsidy: 'Патриотика 2025',
    amount: 850000, 
    status: 'Оплачен', 
    statusColor: 'success',
    date: '15.02.2025'
  },
  { 
    id: 2, 
    number: 'ORD-2025-002', 
    name: 'Оборудование для мероприятий', 
    subsidy: 'ДНР_2026',
    amount: 1200000, 
    status: 'В работе', 
    statusColor: 'info',
    date: '14.02.2025'
  },
  { 
    id: 3, 
    number: 'ORD-2025-003', 
    name: 'Хостинг сайта', 
    subsidy: 'Патриотика 2025',
    amount: 24000, 
    status: 'Планируется', 
    statusColor: 'warning',
    date: '13.02.2025'
  },
  { 
    id: 4, 
    number: 'ORD-2025-004', 
    name: 'Транспортные услуги', 
    subsidy: 'ЗО_2026',
    amount: 185000, 
    status: 'Подписан', 
    statusColor: 'primary',
    date: '12.02.2025'
  },
])

// Форматирование валюты
const formatCurrency = (amount: number) => {
  return amount.toLocaleString() + ' ₽'
}

// Расчет процента
const calculatePercent = (part: number, total: number) => {
  if (!total) return 0
  return Math.round((part / total) * 100)
}

// Цвет для остатка
const getRemainingColor = (remaining: number) => {
  if (remaining < 0) return 'text-error'
  if (remaining < 100000) return 'text-warning'
  return 'text-success'
}

// Цвет прогресс-бара
const getProgressColor = (percent: number) => {
  if (percent > 90) return 'error'
  if (percent > 70) return 'warning'
  return 'primary'
}

// Загрузка данных
const loadData = async () => {
  loading.value = true
  try {
    // Загружаем субсидии с API
    const response = await fetch('/api/subsidies/')
    if (response.ok) {
      subsidies.value = await response.json()
      
      // TODO: Загрузить реальные данные по контрактам и платежам
      // Пока используем демо-данные
      subsidies.value = subsidies.value.map(subsidy => ({
        ...subsidy,
        budget: subsidy.budget || getRandomBudget(),
        contracted: subsidy.contracted || Math.round((subsidy.budget || 0) * 0.4),
        paid: subsidy.paid || Math.round((subsidy.budget || 0) * 0.25),
        shortName: extractShortName(subsidy.name)
      }))
    }
  } catch (error) {
    console.error('Ошибка загрузки данных:', error)
  } finally {
    loading.value = false
  }
}

// Вспомогательные функции
const getRandomBudget = () => {
  const budgets = [2000000, 2500000, 3000000, 3500000, 4000000]
  return budgets[Math.floor(Math.random() * budgets.length)]
}

const extractShortName = (name: string) => {
  if (name.includes('Патриотика')) return 'Патриотика'
  if (name.includes('ДНР')) return 'ДНР'
  if (name.includes('ЗО')) return 'ЗО'
  if (name.includes('КОС')) return 'КОС'
  if (name.includes('ЛНР')) return 'ЛНР'
  if (name.includes('МинОбр')) return 'МинОбр'
  if (name.includes('МинПрос')) return 'МинПрос'
  if (name.includes('ФАДМ')) return 'ФАДМ'
  if (name.includes('МинТруд')) return 'МинТруд'
  return name
}

// Итоговые значения
const totalBudget = computed(() => {
  return subsidies.value.reduce((total, subsidy) => total + (subsidy.budget || 0), 0)
})

const totalContracted = computed(() => {
  return subsidies.value.reduce((total, subsidy) => total + (subsidy.contracted || 0), 0)
})

const totalPaid = computed(() => {
  return subsidies.value.reduce((total, subsidy) => total + (subsidy.paid || 0), 0)
})

const totalRemaining = computed(() => {
  return totalBudget.value - totalPaid.value
})

const totalUsagePercent = computed(() => {
  return calculatePercent(totalPaid.value, totalBudget.value)
})

const hasBudgetData = computed(() => {
  return totalBudget.value > 0
})

// Обработчики кликов
const showBudgetBreakdown = () => {
  alert('Разбивка общего бюджета по субсидиям')
  // Здесь можно открыть модальное окно или перейти на страницу с деталями
}

const showContractedBreakdown = () => {
  alert('Детали по законтрактованным суммам')
}

const showPaidBreakdown = () => {
  alert('Детали по оплаченным суммам')
}

const showRemainingBreakdown = () => {
  alert('Детали по остаткам бюджетов')
}

const showSubsidyAnalytics = () => {
  alert('Аналитика по всем субсидиям')
}

const viewSubsidyDetails = (subsidy: Subsidy) => {
  alert(`Детали субсидии: ${subsidy.name}\nБюджет: ${formatCurrency(subsidy.budget || 0)}`)
}

const viewSubsidyAnalytics = (subsidy: Subsidy) => {
  alert(`Аналитика субсидии: ${subsidy.name}`)
}

const viewOrder = (orderId: number) => {
  router.push(`/orders/${orderId}`)
}

// Загрузка данных при монтировании
onMounted(() => {
  loadData()
})
</script>

<style scoped>
.dashboard-card:hover {
  transform: translateY(-2px);
  transition: transform 0.2s ease;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}
.h-100 {
  height: 100%;
}
</style>