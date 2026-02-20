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
                  :class="{ 'selected-row': selectedSubsidyId === subsidy.id }"
                  @click="selectSubsidy(subsidy)"
                  style="cursor: pointer;"
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
                    @click="openSubsidyDetail(subsidy)"
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
                    <tr v-for="order in recentOrders" :key="order.id" @click="viewOrder(order.id)" style="cursor: pointer;">
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
          
          <v-divider class="my-8" />
          
          <!-- Детальная разбивка выбранной субсидии -->
          <v-row v-if="selectedSubsidy">
            <v-col cols="12">
              <v-card variant="outlined" class="pa-4">
                <div class="d-flex justify-space-between align-center mb-4">
                  <v-card-title class="text-h6">
                    <v-icon icon="mdi-magnify" class="mr-2" />
                    Детализация: {{ selectedSubsidy.name }}
                  </v-card-title>
                  <v-btn icon="mdi-close" variant="text" @click="selectedSubsidyId = null" />
                </div>
                
                <!-- Мини-карточки субсидии -->
                <v-row class="mb-4">
                  <v-col cols="3">
                    <v-card color="primary" variant="tonal" class="pa-3 text-center">
                      <div class="text-caption">Бюджет</div>
                      <div class="text-h5 font-weight-bold">{{ formatCurrency(selectedSubsidy.budget) }}</div>
                    </v-card>
                  </v-col>
                  <v-col cols="3">
                    <v-card color="info" variant="tonal" class="pa-3 text-center">
                      <div class="text-caption">Законтрактовано</div>
                      <div class="text-h5 font-weight-bold">{{ formatCurrency(selectedSubsidy.contracted) }}</div>
                    </v-card>
                  </v-col>
                  <v-col cols="3">
                    <v-card color="success" variant="tonal" class="pa-3 text-center">
                      <div class="text-caption">Оплачено</div>
                      <div class="text-h5 font-weight-bold">{{ formatCurrency(selectedSubsidy.paid) }}</div>
                    </v-card>
                  </v-col>
                  <v-col cols="3">
                    <v-card color="warning" variant="tonal" class="pa-3 text-center">
                      <div class="text-caption">Остаток</div>
                      <div class="text-h5 font-weight-bold">{{ formatCurrency(selectedSubsidy.budget - selectedSubsidy.paid) }}</div>
                    </v-card>
                  </v-col>
                </v-row>
                
                <!-- Категории ФЭО субсидии -->
                <v-card-title class="text-subtitle-1 mb-2">Направления расходов (ФЭО)</v-card-title>
                <v-table density="compact">
                  <thead>
                    <tr>
                      <th>Направление</th>
                      <th>Выделено</th>
                      <th>Использовано</th>
                      <th>Остаток</th>
                      <th>Прогресс</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="cat in selectedSubsidyCategories" :key="cat.id">
                      <td>
                        <div :style="{ marginLeft: (cat.level - 1) * 20 + 'px' }">
                          <v-icon 
                            :icon="cat.level === 1 ? 'mdi-folder' : cat.level === 2 ? 'mdi-folder-open' : 'mdi-file-document'" 
                            :color="cat.level === 1 ? 'primary' : cat.level === 2 ? 'info' : 'success'"
                            size="small"
                            class="mr-1"
                          />
                          {{ cat.name }}
                        </div>
                      </td>
                      <td>{{ formatCurrency(cat.allocated) }}</td>
                      <td>{{ formatCurrency(cat.used) }}</td>
                      <td :class="cat.allocated - cat.used >= 0 ? 'text-success' : 'text-error'">
                        {{ formatCurrency(cat.allocated - cat.used) }}
                      </td>
                      <td style="width: 150px;">
                        <v-progress-linear
                          :model-value="pct(cat.used, cat.allocated)"
                          height="14"
                          :color="progressColor(pct(cat.used, cat.allocated))"
                          rounded
                        >
                          <template v-slot:default>
                            <span class="text-caption">{{ pct(cat.used, cat.allocated) }}%</span>
                          </template>
                        </v-progress-linear>
                      </td>
                    </tr>
                  </tbody>
                </v-table>
                
                <!-- Заказы субсидии -->
                <v-card-title class="text-subtitle-1 mt-6 mb-2">Заказы по субсидии</v-card-title>
                <v-table density="compact">
                  <thead>
                    <tr>
                      <th>№</th>
                      <th>Контрагент</th>
                      <th>Предмет</th>
                      <th>Сумма</th>
                      <th>Статус</th>
                      <th>Дата</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="order in selectedSubsidyOrders" :key="order.id">
                      <td>{{ order.number }}</td>
                      <td>{{ order.contractor }}</td>
                      <td>{{ order.subject }}</td>
                      <td>{{ formatCurrency(order.amount) }}</td>
                      <td><v-chip size="x-small" :color="order.statusColor">{{ order.status }}</v-chip></td>
                      <td>{{ order.date }}</td>
                    </tr>
                  </tbody>
                </v-table>
              </v-card>
            </v-col>
          </v-row>
        </v-card>
      </v-col>
    </v-row>
    
    <!-- Диалог: разбивка по карточкам (бюджет/контракты/оплата/остаток) -->
    <v-dialog v-model="showBreakdownDialog" max-width="800">
      <v-card>
        <v-card-title class="d-flex justify-space-between align-center">
          <span class="text-h6">
            <v-icon :icon="breakdownData.icon" class="mr-2" />
            {{ breakdownData.title }}
          </span>
          <v-btn icon="mdi-close" variant="text" @click="showBreakdownDialog = false" />
        </v-card-title>
        <v-card-text>
          <v-table>
            <thead>
              <tr>
                <th>Субсидия</th>
                <th>Сумма</th>
                <th>Доля</th>
                <th>Прогресс</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in breakdownData.items" :key="item.name">
                <td class="font-weight-medium">{{ item.name }}</td>
                <td class="text-h6 font-weight-bold">{{ formatCurrency(item.value) }}</td>
                <td>{{ item.percent }}%</td>
                <td style="width: 200px;">
                  <v-progress-linear
                    :model-value="item.percent"
                    height="20"
                    :color="item.color"
                    rounded
                  >
                    <template v-slot:default>
                      <span class="text-caption text-white font-weight-bold">{{ item.percent }}%</span>
                    </template>
                  </v-progress-linear>
                </td>
              </tr>
            </tbody>
          </v-table>
          
          <v-divider class="my-4" />
          
          <div class="text-center">
            <div class="text-h4 font-weight-bold" :class="'text-' + breakdownData.color">
              {{ formatCurrency(breakdownData.total) }}
            </div>
            <div class="text-caption text-medium-emphasis">Итого</div>
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>
    
    <!-- Диалог: детали субсидии -->
    <v-dialog v-model="showSubsidyDetailDialog" max-width="900">
      <v-card v-if="detailSubsidy">
        <v-card-title class="d-flex justify-space-between align-center">
          <span class="text-h6">
            <v-icon icon="mdi-file-document" class="mr-2" />
            {{ detailSubsidy.name }}
          </span>
          <v-btn icon="mdi-close" variant="text" @click="showSubsidyDetailDialog = false" />
        </v-card-title>
        <v-card-text>
          <v-row class="mb-4">
            <v-col cols="3" v-for="metric in detailMetrics" :key="metric.label">
              <v-card :color="metric.color" variant="tonal" class="pa-3 text-center">
                <div class="text-caption">{{ metric.label }}</div>
                <div class="text-h5 font-weight-bold">{{ formatCurrency(metric.value) }}</div>
                <div class="text-caption">{{ metric.percent }}% от бюджета</div>
              </v-card>
            </v-col>
          </v-row>
          
          <!-- Горизонтальный stacked bar -->
          <v-card variant="outlined" class="pa-3 mb-4">
            <div class="text-subtitle-2 mb-2">Использование бюджета</div>
            <div class="stacked-bar">
              <div 
                class="stacked-segment paid" 
                :style="{ width: pct(detailSubsidy.paid, detailSubsidy.budget) + '%' }"
                :title="'Оплачено: ' + formatCurrency(detailSubsidy.paid)"
              ></div>
              <div 
                class="stacked-segment contracted" 
                :style="{ width: pct(detailSubsidy.contracted - detailSubsidy.paid, detailSubsidy.budget) + '%' }"
                :title="'В контрактах (не оплачено): ' + formatCurrency(detailSubsidy.contracted - detailSubsidy.paid)"
              ></div>
              <div 
                class="stacked-segment planned" 
                :style="{ width: pct(detailSubsidy.planned, detailSubsidy.budget) + '%' }"
                :title="'Планируется: ' + formatCurrency(detailSubsidy.planned)"
              ></div>
            </div>
            <div class="d-flex justify-space-between mt-2">
              <div class="d-flex align-center gap-4">
                <span class="legend-dot paid"></span><span class="text-caption">Оплачено</span>
                <span class="legend-dot contracted"></span><span class="text-caption">В контрактах</span>
                <span class="legend-dot planned"></span><span class="text-caption">Планируется</span>
                <span class="legend-dot free"></span><span class="text-caption">Свободно</span>
              </div>
            </div>
          </v-card>
          
          <!-- Контрагенты по субсидии -->
          <v-card-title class="text-subtitle-1 mb-2">Контрагенты</v-card-title>
          <v-table density="compact">
            <thead>
              <tr>
                <th>Контрагент</th>
                <th>Договоров</th>
                <th>Сумма</th>
                <th>Оплачено</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in detailContractors" :key="c.name">
                <td class="font-weight-medium">{{ c.name }}</td>
                <td>{{ c.contracts }}</td>
                <td>{{ formatCurrency(c.amount) }}</td>
                <td>{{ formatCurrency(c.paid) }}</td>
                <td><v-chip size="x-small" :color="c.statusColor">{{ c.status }}</v-chip></td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
      </v-card>
    </v-dialog>
    
    <!-- Диалог: график субсидии -->
    <v-dialog v-model="showSubsidyChartDialog" max-width="700">
      <v-card v-if="chartSubsidy">
        <v-card-title class="d-flex justify-space-between align-center">
          <span class="text-h6">
            <v-icon icon="mdi-chart-bar" class="mr-2" />
            {{ chartSubsidy.name }} — помесячный расход
          </span>
          <v-btn icon="mdi-close" variant="text" @click="showSubsidyChartDialog = false" />
        </v-card-title>
        <v-card-text>
          <div v-for="(month, idx) in chartMonths" :key="idx" class="mb-2">
            <div class="d-flex justify-space-between mb-1">
              <span class="text-body-2">{{ month.label }}</span>
              <span class="text-body-2 font-weight-medium">{{ formatCurrency(month.value) }}</span>
            </div>
            <v-progress-linear
              :model-value="pct(month.value, chartMaxMonth)"
              height="20"
              :color="month.value > 0 ? subsidyColors[idx % subsidyColors.length] : 'grey'"
              rounded
            />
          </div>
          
          <v-divider class="my-4" />
          <div class="d-flex justify-space-between">
            <div>
              <span class="text-caption text-medium-emphasis">Итого расход за период:</span>
              <span class="text-h6 font-weight-bold ml-2">{{ formatCurrency(chartTotalSpent) }}</span>
            </div>
            <div>
              <span class="text-caption text-medium-emphasis">Среднемесячный:</span>
              <span class="text-h6 font-weight-bold ml-2">{{ formatCurrency(chartAvgMonth) }}</span>
            </div>
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>
    
    <!-- Диалог: общая аналитика -->
    <v-dialog v-model="showAnalyticsDialog" max-width="900">
      <v-card>
        <v-card-title class="d-flex justify-space-between align-center">
          <span class="text-h6"><v-icon icon="mdi-chart-pie" class="mr-2" />Аналитика по субсидиям</span>
          <v-btn icon="mdi-close" variant="text" @click="showAnalyticsDialog = false" />
        </v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="6">
              <v-card-title class="text-subtitle-1 mb-2">Бюджет vs Оплачено</v-card-title>
              <div v-for="subsidy in filteredSubsidies" :key="'an-'+subsidy.id" class="mb-3">
                <div class="text-body-2 font-weight-medium mb-1">{{ subsidy.shortName }}</div>
                <div class="double-bar">
                  <div class="bar-budget" :style="{ width: pct(subsidy.budget, maxBudget) + '%' }">
                    <span class="text-caption text-white px-1">{{ formatCurrencyShort(subsidy.budget) }}</span>
                  </div>
                  <div class="bar-paid" :style="{ width: pct(subsidy.paid, maxBudget) + '%' }">
                    <span class="text-caption text-white px-1">{{ formatCurrencyShort(subsidy.paid) }}</span>
                  </div>
                </div>
              </div>
              <div class="d-flex gap-4 mt-2">
                <span class="legend-dot budget"></span><span class="text-caption">Бюджет</span>
                <span class="legend-dot paid-legend"></span><span class="text-caption">Оплачено</span>
              </div>
            </v-col>
            
            <v-col cols="12" md="6">
              <v-card-title class="text-subtitle-1 mb-2">Топ контрагентов</v-card-title>
              <v-table density="compact">
                <thead>
                  <tr>
                    <th>Контрагент</th>
                    <th>Сумма договоров</th>
                    <th>Субсидий</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="c in topContractors" :key="c.name">
                    <td class="font-weight-medium">{{ c.name }}</td>
                    <td>{{ formatCurrency(c.total) }}</td>
                    <td>{{ c.subsidyCount }}</td>
                  </tr>
                </tbody>
              </v-table>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const loading = ref(false)
const selectedYear = ref(2025)
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
    description: 'Федеральное агентство по делам молодёжи',
    budget: 12_000_000, contracted: 9_600_000, paid: 7_100_000, planned: 1_400_000
  },
  {
    id: 5, name: 'МинПрос Образование 2025', shortName: 'МинПрос', year: 2025,
    description: 'Образовательные программы и гранты',
    budget: 19_500_000, contracted: 14_800_000, paid: 10_200_000, planned: 2_600_000
  },
  // 2024
  {
    id: 6, name: 'Патриотика 2024', shortName: 'Патриотика', year: 2024,
    description: 'Патриотическое воспитание (завершена)',
    budget: 22_000_000, contracted: 22_000_000, paid: 22_000_000, planned: 0
  },
  {
    id: 7, name: 'МинПрос 2024', shortName: 'МинПрос', year: 2024,
    description: 'Образовательные программы (завершена)',
    budget: 15_000_000, contracted: 15_000_000, paid: 15_000_000, planned: 0
  },
  {
    id: 8, name: 'ФАДМ 2024', shortName: 'ФАДМ', year: 2024,
    description: 'Волонтёрские программы (завершена)',
    budget: 9_000_000, contracted: 9_000_000, paid: 8_800_000, planned: 0
  },
  {
    id: 9, name: 'КОС Спорт 2024', shortName: 'КОС', year: 2024,
    description: 'Комитет общественных связей — спортивные программы',
    budget: 6_500_000, contracted: 6_500_000, paid: 6_200_000, planned: 0
  },
])

const availableYears = computed(() => [...new Set(allSubsidies.value.map(s => s.year))].sort((a, b) => b - a))
const filteredSubsidies = computed(() => allSubsidies.value.filter(s => s.year === selectedYear.value))

// Категории ФЭО для каждой субсидии
const feoBySubsidy: Record<number, Array<{ id: number; name: string; level: number; allocated: number; used: number }>> = {
  1: [
    { id: 1, name: 'Техническое оснащение штаба', level: 1, allocated: 8_500_000, used: 5_200_000 },
    { id: 2, name: 'Компьютерная техника', level: 2, allocated: 4_000_000, used: 3_100_000 },
    { id: 3, name: 'Оргтехника и мебель', level: 2, allocated: 2_500_000, used: 1_400_000 },
    { id: 4, name: 'ПО и лицензии', level: 2, allocated: 2_000_000, used: 700_000 },
    { id: 5, name: 'Организация мероприятий', level: 1, allocated: 10_000_000, used: 4_800_000 },
    { id: 6, name: 'Слёт студентов-спасателей', level: 2, allocated: 4_000_000, used: 2_300_000 },
    { id: 7, name: 'Форум «Патриот»', level: 2, allocated: 3_500_000, used: 1_600_000 },
    { id: 8, name: 'Региональные сборы', level: 2, allocated: 2_500_000, used: 900_000 },
    { id: 9, name: 'Интернет-ресурс и PR', level: 1, allocated: 3_500_000, used: 1_200_000 },
    { id: 10, name: 'Хостинг и домены', level: 2, allocated: 500_000, used: 180_000 },
    { id: 11, name: 'Контент и SMM', level: 2, allocated: 2_000_000, used: 700_000 },
    { id: 12, name: 'Дизайн и полиграфия', level: 2, allocated: 1_000_000, used: 320_000 },
    { id: 13, name: 'Транспорт и проживание', level: 1, allocated: 4_128_070, used: 1_640_200 },
    { id: 14, name: 'Авиабилеты и ж/д', level: 2, allocated: 2_128_070, used: 940_200 },
    { id: 15, name: 'Гостиницы', level: 2, allocated: 2_000_000, used: 700_000 },
  ],
  2: [
    { id: 20, name: 'Строительные материалы', level: 1, allocated: 6_000_000, used: 4_100_000 },
    { id: 21, name: 'Цемент и бетон', level: 2, allocated: 3_000_000, used: 2_400_000 },
    { id: 22, name: 'Металлоконструкции', level: 2, allocated: 3_000_000, used: 1_700_000 },
    { id: 23, name: 'Оборудование', level: 1, allocated: 5_000_000, used: 2_800_000 },
    { id: 24, name: 'Генераторы', level: 2, allocated: 2_500_000, used: 1_500_000 },
    { id: 25, name: 'Инструменты', level: 2, allocated: 2_500_000, used: 1_300_000 },
    { id: 26, name: 'Логистика', level: 1, allocated: 4_000_000, used: 1_700_000 },
    { id: 27, name: 'Автотранспорт', level: 2, allocated: 2_500_000, used: 1_100_000 },
    { id: 28, name: 'Складские услуги', level: 2, allocated: 1_500_000, used: 600_000 },
  ],
  3: [
    { id: 30, name: 'Молодёжные лагеря', level: 1, allocated: 4_000_000, used: 1_800_000 },
    { id: 31, name: 'Аренда площадок', level: 2, allocated: 2_000_000, used: 1_100_000 },
    { id: 32, name: 'Питание', level: 2, allocated: 2_000_000, used: 700_000 },
    { id: 33, name: 'Образовательные проекты', level: 1, allocated: 3_000_000, used: 900_000 },
    { id: 34, name: 'Учебные материалы', level: 2, allocated: 1_500_000, used: 500_000 },
    { id: 35, name: 'Преподаватели', level: 2, allocated: 1_500_000, used: 400_000 },
    { id: 36, name: 'Спортивные мероприятия', level: 1, allocated: 1_500_000, used: 500_000 },
  ],
  4: [
    { id: 40, name: 'Волонтёрские штабы', level: 1, allocated: 5_000_000, used: 3_200_000 },
    { id: 41, name: 'Оборудование штабов', level: 2, allocated: 2_500_000, used: 1_800_000 },
    { id: 42, name: 'Расходные материалы', level: 2, allocated: 2_500_000, used: 1_400_000 },
    { id: 43, name: 'Обучение волонтёров', level: 1, allocated: 4_000_000, used: 2_500_000 },
    { id: 44, name: 'Тренинги', level: 2, allocated: 2_000_000, used: 1_300_000 },
    { id: 45, name: 'Сертификация', level: 2, allocated: 2_000_000, used: 1_200_000 },
    { id: 46, name: 'Медиа и продвижение', level: 1, allocated: 3_000_000, used: 1_400_000 },
    { id: 47, name: 'Видеопроизводство', level: 2, allocated: 1_500_000, used: 800_000 },
    { id: 48, name: 'Соцсети и реклама', level: 2, allocated: 1_500_000, used: 600_000 },
  ],
  5: [
    { id: 50, name: 'Гранты школам', level: 1, allocated: 8_000_000, used: 5_100_000 },
    { id: 51, name: 'Оснащение классов', level: 2, allocated: 4_000_000, used: 2_800_000 },
    { id: 52, name: 'Учебные пособия', level: 2, allocated: 4_000_000, used: 2_300_000 },
    { id: 53, name: 'Повышение квалификации', level: 1, allocated: 6_000_000, used: 3_200_000 },
    { id: 54, name: 'Курсы для учителей', level: 2, allocated: 3_000_000, used: 1_800_000 },
    { id: 55, name: 'Методические материалы', level: 2, allocated: 3_000_000, used: 1_400_000 },
    { id: 56, name: 'Олимпиады и конкурсы', level: 1, allocated: 5_500_000, used: 1_900_000 },
    { id: 57, name: 'Призовой фонд', level: 2, allocated: 2_500_000, used: 900_000 },
    { id: 58, name: 'Организация мероприятий', level: 2, allocated: 3_000_000, used: 1_000_000 },
  ],
}

// Заказы по субсидиям
const ordersBySubsidy: Record<number, Array<{ id: number; number: string; contractor: string; subject: string; amount: number; status: string; statusColor: string; date: string }>> = {
  1: [
    { id: 1, number: 'Д-2025-001', contractor: 'ООО «ТехноСервис»', subject: 'Ноутбуки Lenovo ThinkPad', amount: 3_100_000, status: 'Оплачен', statusColor: 'success', date: '15.01.2025' },
    { id: 2, number: 'Д-2025-007', contractor: 'ИП Козлов А.В.', subject: 'Организация форума «Патриот»', amount: 1_600_000, status: 'В работе', statusColor: 'info', date: '01.02.2025' },
    { id: 3, number: 'Д-2025-012', contractor: 'ООО «Вебмастер»', subject: 'Редизайн сайта + SEO', amount: 700_000, status: 'Подписан', statusColor: 'primary', date: '10.02.2025' },
    { id: 4, number: 'Д-2025-015', contractor: 'АО «Аэрофлот»', subject: 'Авиабилеты делегации', amount: 940_200, status: 'Оплачен', statusColor: 'success', date: '12.02.2025' },
    { id: 5, number: 'Д-2025-018', contractor: 'ООО «Принт-Хаус»', subject: 'Полиграфия для слёта', amount: 320_000, status: 'Планируется', statusColor: 'warning', date: '18.02.2025' },
  ],
  2: [
    { id: 10, number: 'Д-2025-002', contractor: 'ООО «СтройМонтаж»', subject: 'Цемент М500, 200 тонн', amount: 2_400_000, status: 'Оплачен', statusColor: 'success', date: '20.01.2025' },
    { id: 11, number: 'Д-2025-005', contractor: 'ЗАО «МеталлПром»', subject: 'Металлоконструкции', amount: 1_700_000, status: 'В работе', statusColor: 'info', date: '28.01.2025' },
    { id: 12, number: 'Д-2025-009', contractor: 'ООО «ЭнергоРесурс»', subject: 'Дизельные генераторы 4 шт.', amount: 1_500_000, status: 'Оплачен', statusColor: 'success', date: '05.02.2025' },
    { id: 13, number: 'Д-2025-014', contractor: 'ИП Сидоров', subject: 'Автотранспорт (аренда)', amount: 1_100_000, status: 'В работе', statusColor: 'info', date: '11.02.2025' },
  ],
  3: [
    { id: 20, number: 'Д-2025-003', contractor: 'ООО «Лагерь-Сервис»', subject: 'Аренда базы отдыха', amount: 1_100_000, status: 'Оплачен', statusColor: 'success', date: '22.01.2025' },
    { id: 21, number: 'Д-2025-008', contractor: 'ООО «КейтерингПро»', subject: 'Питание (200 чел, 7 дней)', amount: 700_000, status: 'Подписан', statusColor: 'primary', date: '03.02.2025' },
    { id: 22, number: 'Д-2025-016', contractor: 'ИП Петрова Е.Н.', subject: 'Учебные материалы (печать)', amount: 500_000, status: 'Планируется', statusColor: 'warning', date: '15.02.2025' },
  ],
  4: [
    { id: 30, number: 'Д-2025-004', contractor: 'ООО «ОфисМаркет»', subject: 'Мебель и оборудование для штабов', amount: 1_800_000, status: 'Оплачен', statusColor: 'success', date: '25.01.2025' },
    { id: 31, number: 'Д-2025-010', contractor: 'ООО «ПроТренинг»', subject: 'Курсы первой помощи', amount: 1_300_000, status: 'В работе', statusColor: 'info', date: '06.02.2025' },
    { id: 32, number: 'Д-2025-013', contractor: 'ООО «Видеолаб»', subject: 'Съёмка документального фильма', amount: 800_000, status: 'Подписан', statusColor: 'primary', date: '09.02.2025' },
    { id: 33, number: 'Д-2025-017', contractor: 'ООО «Сертификат.ру»', subject: 'Сертификация волонтёров', amount: 1_200_000, status: 'Оплачен', statusColor: 'success', date: '16.02.2025' },
  ],
  5: [
    { id: 40, number: 'Д-2025-006', contractor: 'ООО «УчТехСнаб»', subject: 'Интерактивные доски 15 шт.', amount: 2_800_000, status: 'Оплачен', statusColor: 'success', date: '30.01.2025' },
    { id: 41, number: 'Д-2025-011', contractor: 'Издательство «Просвещение»', subject: 'Учебные пособия (тираж 5000)', amount: 2_300_000, status: 'В работе', statusColor: 'info', date: '07.02.2025' },
    { id: 42, number: 'Д-2025-019', contractor: 'НОУ «Педагог+»', subject: 'Курсы повышения квалификации', amount: 1_800_000, status: 'Подписан', statusColor: 'primary', date: '19.02.2025' },
    { id: 43, number: 'Д-2025-020', contractor: 'ООО «ЭвентПро»', subject: 'Организация олимпиады', amount: 1_000_000, status: 'Планируется', statusColor: 'warning', date: '20.02.2025' },
    { id: 44, number: 'Д-2025-021', contractor: 'АНО «Талант»', subject: 'Призовой фонд конкурсов', amount: 900_000, status: 'Планируется', statusColor: 'warning', date: '20.02.2025' },
  ],
}

// Контрагенты для деталей
const contractorsBySubsidy: Record<number, Array<{ name: string; contracts: number; amount: number; paid: number; status: string; statusColor: string }>> = {
  1: [
    { name: 'ООО «ТехноСервис»', contracts: 2, amount: 3_600_000, paid: 3_100_000, status: 'Частично оплачен', statusColor: 'info' },
    { name: 'ИП Козлов А.В.', contracts: 1, amount: 1_600_000, paid: 0, status: 'В работе', statusColor: 'warning' },
    { name: 'ООО «Вебмастер»', contracts: 1, amount: 700_000, paid: 0, status: 'Подписан', statusColor: 'primary' },
    { name: 'АО «Аэрофлот»', contracts: 3, amount: 2_100_000, paid: 1_940_200, status: 'Частично оплачен', statusColor: 'info' },
    { name: 'ООО «Принт-Хаус»', contracts: 1, amount: 320_000, paid: 0, status: 'Планируется', statusColor: 'warning' },
  ],
  2: [
    { name: 'ООО «СтройМонтаж»', contracts: 2, amount: 3_400_000, paid: 2_400_000, status: 'Частично оплачен', statusColor: 'info' },
    { name: 'ЗАО «МеталлПром»', contracts: 1, amount: 1_700_000, paid: 0, status: 'В работе', statusColor: 'warning' },
    { name: 'ООО «ЭнергоРесурс»', contracts: 1, amount: 1_500_000, paid: 1_500_000, status: 'Оплачен', statusColor: 'success' },
    { name: 'ИП Сидоров', contracts: 1, amount: 1_100_000, paid: 500_000, status: 'Частично оплачен', statusColor: 'info' },
  ],
  3: [
    { name: 'ООО «Лагерь-Сервис»', contracts: 1, amount: 1_100_000, paid: 1_100_000, status: 'Оплачен', statusColor: 'success' },
    { name: 'ООО «КейтерингПро»', contracts: 1, amount: 700_000, paid: 0, status: 'Подписан', statusColor: 'primary' },
    { name: 'ИП Петрова Е.Н.', contracts: 1, amount: 500_000, paid: 0, status: 'Планируется', statusColor: 'warning' },
  ],
  4: [
    { name: 'ООО «ОфисМаркет»', contracts: 1, amount: 1_800_000, paid: 1_800_000, status: 'Оплачен', statusColor: 'success' },
    { name: 'ООО «ПроТренинг»', contracts: 2, amount: 2_100_000, paid: 1_300_000, status: 'Частично оплачен', statusColor: 'info' },
    { name: 'ООО «Видеолаб»', contracts: 1, amount: 800_000, paid: 0, status: 'Подписан', statusColor: 'primary' },
    { name: 'ООО «Сертификат.ру»', contracts: 1, amount: 1_200_000, paid: 1_200_000, status: 'Оплачен', statusColor: 'success' },
  ],
  5: [
    { name: 'ООО «УчТехСнаб»', contracts: 1, amount: 2_800_000, paid: 2_800_000, status: 'Оплачен', statusColor: 'success' },
    { name: 'Издательство «Просвещение»', contracts: 2, amount: 3_500_000, paid: 2_300_000, status: 'Частично оплачен', statusColor: 'info' },
    { name: 'НОУ «Педагог+»', contracts: 1, amount: 1_800_000, paid: 0, status: 'Подписан', statusColor: 'primary' },
    { name: 'ООО «ЭвентПро»', contracts: 1, amount: 1_000_000, paid: 0, status: 'Планируется', statusColor: 'warning' },
    { name: 'АНО «Талант»', contracts: 1, amount: 900_000, paid: 0, status: 'Планируется', statusColor: 'warning' },
  ],
}

// Последние заказы (сборная)
const recentOrders = computed(() => {
  const all: Array<{ id: number; number: string; name: string; subsidy: string; amount: number; status: string; statusColor: string }> = []
  for (const s of filteredSubsidies.value) {
    const orders = ordersBySubsidy[s.id] || []
    for (const o of orders) {
      all.push({ id: o.id, number: o.number, name: o.subject, subsidy: s.shortName, amount: o.amount, status: o.status, statusColor: o.statusColor })
    }
  }
  return all.slice(-6)
})

// ===== ВЫЧИСЛЯЕМЫЕ =====

const totalBudget = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.budget, 0))
const totalContracted = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.contracted, 0))
const totalPaid = computed(() => filteredSubsidies.value.reduce((s, x) => s + x.paid, 0))
const totalRemaining = computed(() => totalBudget.value - totalPaid.value)
const totalUsagePct = computed(() => pct(totalPaid.value, totalBudget.value))
const maxBudget = computed(() => Math.max(...filteredSubsidies.value.map(s => s.budget), 1))

const selectedSubsidy = computed(() => filteredSubsidies.value.find(s => s.id === selectedSubsidyId.value) || null)
const selectedSubsidyCategories = computed(() => selectedSubsidy.value ? (feoBySubsidy[selectedSubsidy.value.id] || []) : [])
const selectedSubsidyOrders = computed(() => selectedSubsidy.value ? (ordersBySubsidy[selectedSubsidy.value.id] || []) : [])

const summaryCards = computed(() => [
  { key: 'budget', title: 'Общий бюджет', value: totalBudget.value, color: 'primary', icon: 'mdi-chart-bar', subtitle: `${filteredSubsidies.value.length} субсидий` },
  { key: 'contracted', title: 'Законтрактовано', value: totalContracted.value, color: 'info', icon: 'mdi-file-document-check', subtitle: `${pct(totalContracted.value, totalBudget.value)}% от бюджета` },
  { key: 'paid', title: 'Оплачено', value: totalPaid.value, color: 'success', icon: 'mdi-cash-check', subtitle: `${pct(totalPaid.value, totalBudget.value)}% от бюджета` },
  { key: 'remaining', title: 'Остаток', value: totalRemaining.value, color: 'warning', icon: 'mdi-cash', subtitle: `${pct(totalRemaining.value, totalBudget.value)}% от бюджета` },
])

// Топ контрагентов (для аналитики)
const topContractors = computed(() => {
  const map: Record<string, { total: number; subsidies: Set<number> }> = {}
  for (const s of filteredSubsidies.value) {
    for (const c of (contractorsBySubsidy[s.id] || [])) {
      if (!map[c.name]) map[c.name] = { total: 0, subsidies: new Set() }
      map[c.name].total += c.amount
      map[c.name].subsidies.add(s.id)
    }
  }
  return Object.entries(map)
    .map(([name, d]) => ({ name, total: d.total, subsidyCount: d.subsidies.size }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 8)
})

// ===== BREAKDOWN DIALOG =====

const breakdownData = ref<{ title: string; icon: string; color: string; total: number; items: Array<{ name: string; value: number; percent: number; color: string }> }>({
  title: '', icon: '', color: 'primary', total: 0, items: []
})

function openBreakdown(key: string) {
  const fieldMap: Record<string, { title: string; icon: string; color: string; field: keyof Subsidy }> = {
    budget: { title: 'Разбивка бюджета по субсидиям', icon: 'mdi-chart-bar', color: 'primary', field: 'budget' },
    contracted: { title: 'Законтрактовано по субсидиям', icon: 'mdi-file-document-check', color: 'info', field: 'contracted' },
    paid: { title: 'Оплачено по субсидиям', icon: 'mdi-cash-check', color: 'success', field: 'paid' },
    remaining: { title: 'Остаток по субсидиям', icon: 'mdi-cash', color: 'warning', field: 'budget' },
  }
  const cfg = fieldMap[key]
  if (!cfg) return
  
  const total = key === 'remaining' ? totalRemaining.value :
    filteredSubsidies.value.reduce((s, x) => s + (x[cfg.field] as number), 0)
  
  breakdownData.value = {
    title: cfg.title,
    icon: cfg.icon,
    color: cfg.color,
    total,
    items: filteredSubsidies.value.map((s, i) => {
      const val = key === 'remaining' ? s.budget - s.paid : (s[cfg.field] as number)
      return {
        name: s.shortName,
        value: val,
        percent: pct(val, total),
        color: subsidyColors[i % subsidyColors.length],
      }
    })
  }
  showBreakdownDialog.value = true
}

// ===== SUBSIDY DETAIL DIALOG =====

const detailSubsidy = ref<Subsidy | null>(null)
const detailContractors = computed(() => detailSubsidy.value ? (contractorsBySubsidy[detailSubsidy.value.id] || []) : [])
const detailMetrics = computed(() => {
  if (!detailSubsidy.value) return []
  const s = detailSubsidy.value
  return [
    { label: 'Бюджет', value: s.budget, percent: 100, color: 'primary' },
    { label: 'Законтрактовано', value: s.contracted, percent: pct(s.contracted, s.budget), color: 'info' },
    { label: 'Оплачено', value: s.paid, percent: pct(s.paid, s.budget), color: 'success' },
    { label: 'Остаток', value: s.budget - s.paid, percent: pct(s.budget - s.paid, s.budget), color: 'warning' },
  ]
})

function openSubsidyDetail(subsidy: Subsidy) {
  detailSubsidy.value = subsidy
  showSubsidyDetailDialog.value = true
}

// ===== SUBSIDY CHART DIALOG =====

const chartSubsidy = ref<Subsidy | null>(null)
const chartMonths = computed(() => {
  if (!chartSubsidy.value) return []
  // Генерируем помесячные данные на основе paid
  const months = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
  const totalPaid = chartSubsidy.value.paid
  // Распределяем неравномерно для реалистичности
  const weights = [0.05, 0.12, 0.08, 0.15, 0.10, 0.18, 0.07, 0.03, 0.06, 0.09, 0.04, 0.03]
  return months.map((label, i) => ({
    label,
    value: Math.round(totalPaid * weights[i])
  }))
})
const chartMaxMonth = computed(() => Math.max(...chartMonths.value.map(m => m.value), 1))
const chartTotalSpent = computed(() => chartMonths.value.reduce((s, m) => s + m.value, 0))
const chartAvgMonth = computed(() => Math.round(chartTotalSpent.value / Math.max(chartMonths.value.filter(m => m.value > 0).length, 1)))

function openSubsidyChart(subsidy: Subsidy) {
  chartSubsidy.value = subsidy
  showSubsidyChartDialog.value = true
}

// ===== УТИЛИТЫ =====

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

function formatCurrencyShort(amount: number) {
  if (amount >= 1_000_000) return (amount / 1_000_000).toFixed(1) + ' млн'
  if (amount >= 1_000) return (amount / 1_000).toFixed(0) + ' тыс'
  return amount.toString()
}

function selectSubsidy(subsidy: Subsidy) {
  selectedSubsidyId.value = selectedSubsidyId.value === subsidy.id ? null : subsidy.id
}

function viewOrder(orderId: number) {
  router.push(`/orders/${orderId}`)
}

function loadData() {
  loading.value = true
  setTimeout(() => { loading.value = false }, 500)
}

onMounted(() => { loadData() })
</script>

<style scoped>
.dashboard-card:hover {
  transform: translateY(-2px);
  transition: transform 0.2s ease;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}
.h-100 { height: 100%; }
.gap-4 { gap: 16px; }
.selected-row { background-color: rgba(33, 150, 243, 0.08) !important; }

.stacked-bar {
  display: flex;
  height: 32px;
  border-radius: 8px;
  overflow: hidden;
  background: #e0e0e0;
}
.stacked-segment {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 2px;
  transition: width 0.3s ease;
}
.stacked-segment.paid { background: #4caf50; }
.stacked-segment.contracted { background: #2196f3; }
.stacked-segment.planned { background: #ff9800; }

.legend-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  margin-right: 4px;
}
.legend-dot.paid { background: #4caf50; }
.legend-dot.contracted { background: #2196f3; }
.legend-dot.planned { background: #ff9800; }
.legend-dot.free { background: #e0e0e0; }
.legend-dot.budget { background: #1976d2; }
.legend-dot.paid-legend { background: #4caf50; }

.double-bar {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.bar-budget {
  height: 16px;
  background: #1976d2;
  border-radius: 4px;
  display: flex;
  align-items: center;
  min-width: 40px;
  transition: width 0.3s ease;
}
.bar-paid {
  height: 16px;
  background: #4caf50;
  border-radius: 4px;
  display: flex;
  align-items: center;
  min-width: 40px;
  transition: width 0.3s ease;
}
</style>
