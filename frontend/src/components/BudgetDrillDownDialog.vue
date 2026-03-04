<template>
  <v-dialog v-model="dialog" max-width="1400" persistent>
    <v-card class="budget-drill-dialog">
      <v-card-title class="d-flex justify-space-between align-center pa-4 bg-primary">
        <div>
          <span class="text-h5 text-white">{{ title }}</span>
          <div class="text-caption text-white mt-1">
            {{ breadcrumbText }}
          </div>
        </div>
        <v-btn icon="mdi-close" variant="text" color="white" @click="close"></v-btn>
      </v-card-title>
      
      <v-card-text class="pa-4">
        <!-- Summary Cards -->
        <div v-if="currentLevel === 0" class="summary-cards mb-4">
          <v-card variant="outlined" class="pa-3 text-center">
            <div class="text-caption">Базовый бюджет</div>
            <div class="text-h5 text-primary">{{ formatNumber(totalBudget) }}</div>
          </v-card>
          <v-card variant="outlined" class="pa-3 text-center">
            <div class="text-caption">Σ Категорий</div>
            <div class="text-h5 text-info">{{ formatNumber(totalCategories) }}</div>
          </v-card>
          <v-card variant="outlined" class="pa-3 text-center">
            <div class="text-caption">Остаток</div>
            <div class="text-h5" :class="remaining >= 0 ? 'text-success' : 'text-error'">
              {{ formatNumber(remaining) }}
            </div>
          </v-card>
        </div>

        <!-- Transition Container -->
        <transition name="slide-fade" mode="out-in">
          
          <!-- Level 0: Субсидии (столбцы) -->
          <div v-if="currentLevel === 0" key="level0">
            <div class="text-h6 mb-4">💰 Выберите субсидию для детализации</div>
            <div class="chart-container">
              <div 
                v-for="sub in subsidies" 
                :key="sub.id"
                class="chart-bar-wrapper"
                @click="drillToSubsidy(sub)"
              >
                <div
                  class="chart-bar"
                  :style="{ height: getBarHeight(sub.budget) + 'px', backgroundColor: getBarColor(sub.id) }"
                >
                  <span class="bar-value">{{ formatNumber(sub.budget) }}</span>
                </div>
                <div class="bar-label">{{ sub.name.replace('_2026', '') }}</div>
              </div>
            </div>
          </div>

          <!-- Level 1: Направления ФЭО -->
          <div v-else-if="currentLevel === 1" key="level1">
            <v-btn variant="text" prepend-icon="mdi-arrow-left" @click="goBack" class="mb-2">
              Назад к субсидиям
            </v-btn>
            <div class="text-h6 mb-2">📁 Направления ФЭО: {{ currentSubsidy?.name }}</div>
            
            <v-card variant="outlined" class="pa-3 mb-3">
              <v-row>
                <v-col cols="4"><div class="text-caption">Базовый</div><div class="text-h6">{{ formatNumber(currentSubsidy?.budget || 0) }}</div></v-col>
                <v-col cols="4"><div class="text-caption">Σ Направлений</div><div class="text-h6 text-info">{{ formatNumber(subsidyTotal) }}</div></v-col>
                <v-col cols="4"><div class="text-caption">Остаток</div><div class="text-h6" :class="(currentSubsidy?.budget || 0) - subsidyTotal >= 0 ? 'text-success' : 'text-error'">{{ formatNumber((currentSubsidy?.budget || 0) - subsidyTotal) }}</div></v-col>
              </v-row>
            </v-card>

            <div class="direction-grid">
              <v-card 
                v-for="dir in currentDirections" 
                :key="dir.id" 
                variant="outlined" 
                class="direction-card clickable"
                @click="drillToType(dir)"
              >
                <div class="d-flex justify-space-between align-center">
                  <div class="text-subtitle-1 font-weight-bold">{{ dir.name }}</div>
                  <v-chip size="small" color="primary">Уровень 1</v-chip>
                </div>
                <v-divider class="my-2"></v-divider>
                <div class="d-flex justify-space-between">
                  <span>Бюджет:</span>
                  <strong>{{ formatNumber(dir.budget || 0) }}</strong>
                </div>
                <v-progress-linear :model-value="getProgress(dir)" color="primary" height="6" class="mt-2"></v-progress-linear>
              </v-card>
            </div>
          </div>

          <!-- Level 2: Типы расходов -->
          <div v-else-if="currentLevel === 2" key="level2">
            <v-btn variant="text" prepend-icon="mdi-arrow-left" @click="goBack" class="mb-2">
              Назад к направлениям
            </v-btn>
            <div class="text-h6 mb-2">📋 Типы расходов: {{ currentParent?.name }}</div>
            
            <div class="direction-grid">
              <v-card 
                v-for="type in currentTypes" 
                :key="type.id" 
                variant="outlined" 
                class="direction-card clickable"
                @click="drillToExpense(type)"
              >
                <div class="text-subtitle-1 font-weight-bold">{{ type.name }}</div>
                <v-divider class="my-2"></v-divider>
                <div class="d-flex justify-space-between"><span>Бюджет:</span><strong>{{ formatNumber(type.budget || 0) }}</strong></div>
                <v-progress-linear :model-value="getProgress(type)" color="info" height="6" class="mt-2"></v-progress-linear>
              </v-card>
            </div>
          </div>

          <!-- Level 3: Статьи расходов -->
          <div v-else-if="currentLevel === 3" key="level3">
            <v-btn variant="text" prepend-icon="mdi-arrow-left" @click="goBack" class="mb-2">
              Назад к типам
            </v-btn>
            <div class="text-h6 mb-2">📝 Статьи расходов: {{ currentParent?.name }}</div>
            
            <v-table>
              <thead>
                <tr>
                  <th>Наименование</th>
                  <th class="text-right">Базовый</th>
                  <th class="text-right">План.кол</th>
                  <th class="text-right">План.цена</th>
                  <th class="text-right">План.сумма</th>
                  <th class="text-right">Факт.кол</th>
                  <th class="text-right">Факт.цена</th>
                  <th class="text-right">Факт.сумма</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="exp in currentExpenses" :key="exp.id" class="clickable" @click="drillToProducts(exp)">
                  <td>{{ exp.name }}</td>
                  <td class="text-right">{{ formatNumber(exp.budget || 0) }}</td>
                  <td class="text-right">{{ exp.planned_amount || 0 }}</td>
                  <td class="text-right">{{ formatNumber(exp.planned_price || 0) }}</td>
                  <td class="text-right text-info">{{ formatNumber(exp.planned_total || 0) }}</td>
                  <td class="text-right">{{ exp.actual_amount || 0 }}</td>
                  <td class="text-right">{{ formatNumber(exp.actual_price || 0) }}</td>
                  <td class="text-right text-success">{{ formatNumber(exp.actual_total || 0) }}</td>
                </tr>
              </tbody>
            </v-table>
          </div>

          <!-- Level 4: Товары -->
          <div v-else-if="currentLevel === 4" key="level4">
            <v-btn variant="text" prepend-icon="mdi-arrow-left" @click="goBack" class="mb-2">
              Назад к статьям
            </v-btn>
            <div class="text-h6 mb-2">🎁 Товары и услуги: {{ currentParent?.name }}</div>
            
            <v-tabs v-model="productTab" class="mb-3">
              <v-tab value="planned">📋 Плановые</v-tab>
              <v-tab value="actual">✅ Фактические</v-tab>
            </v-tabs>

            <v-window v-model="productTab">
              <v-window-item value="planned">
                <v-card variant="outlined" class="pa-3 mb-3">
                  <div class="text-subtitle-1 mb-2">Добавить плановое</div>
                  <v-row dense>
                    <v-col cols="6"><v-text-field v-model="newPlanned.name" label="Наименование" variant="outlined" density="compact"></v-text-field></v-col>
                    <v-col cols="2"><v-text-field v-model.number="newPlanned.amount" label="Кол-во" type="number" variant="outlined" density="compact"></v-text-field></v-col>
                    <v-col cols="2"><v-text-field v-model.number="newPlanned.price" label="Цена" type="number" variant="outlined" density="compact"></v-text-field></v-col>
                    <v-col cols="2"><v-btn color="primary" @click="addPlanned">Добавить</v-btn></v-col>
                  </v-row>
                </v-card>
                <v-table density="compact">
                  <thead><tr><th>Наименование</th><th class="text-right">Кол-во</th><th class="text-right">Цена</th><th class="text-right">Сумма</th></tr></thead>
                  <tbody>
                    <tr v-for="p in plannedProducts" :key="p.id">
                      <td>{{ p.name }}</td>
                      <td class="text-right">{{ p.planned_amount || 0 }}</td>
                      <td class="text-right">{{ formatNumber(p.planned_price || 0) }}</td>
                      <td class="text-right text-info">{{ formatNumber(p.planned_total || 0) }}</td>
                    </tr>
                  </tbody>
                </v-table>
              </v-window-item>

              <v-window-item value="actual">
                <v-card variant="outlined" class="pa-3 mb-3">
                  <div class="text-subtitle-1 mb-2">Добавить фактическое</div>
                  <v-row dense>
                    <v-col cols="3"><v-text-field v-model.number="newActual.amount" label="Кол-во" type="number" variant="outlined" density="compact"></v-text-field></v-col>
                    <v-col cols="3"><v-text-field v-model.number="newActual.price" label="Цена" type="number" variant="outlined" density="compact"></v-text-field></v-col>
                    <v-col cols="3"><v-text-field v-model="newActual.name" label="Наименование" variant="outlined" density="compact"></v-text-field></v-col>
                    <v-col cols="3"><v-btn color="success" @click="addActual">Добавить</v-btn></v-col>
                  </v-row>
                </v-card>
                <v-table density="compact">
                  <thead><tr><th>Наименование</th><th class="text-right">Кол-во</th><th class="text-right">Цена</th><th class="text-right">Сумма</th><th>Связь</th></tr></thead>
                  <tbody>
                    <tr v-for="p in actualProducts" :key="p.id">
                      <td>{{ p.actual_name || p.name }}</td>
                      <td class="text-right">{{ p.actual_amount || 0 }}</td>
                      <td class="text-right">{{ formatNumber(p.actual_price || 0) }}</td>
                      <td class="text-right text-success">{{ formatNumber(p.actual_total || 0) }}</td>
                      <td>{{ p.plan_link_id ? '✓' : '-' }}</td>
                    </tr>
                  </tbody>
                </v-table>
              </v-window-item>
            </v-window>
          </div>
        </transition>

        <!-- Navigation Dots -->
        <div class="level-dots mt-4">
          <span 
            v-for="(label, idx) in ['Бюджет', 'Направления', 'Типы', 'Статьи', 'Товары']" 
            :key="idx"
            class="level-dot"
            :class="{ active: currentLevel === idx }"
            @click="jumpToLevel(idx)"
          >
            {{ idx + 1 }}
          </span>
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  modelValue: Boolean,
  subsidies: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:modelValue'])

const dialog = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const currentLevel = ref(0)
const currentSubsidy = ref(null)
const currentParent = ref(null)
const history = ref([])
const productTab = ref('planned')

const currentDirections = ref([])
const currentTypes = ref([])
const currentExpenses = ref([])
const currentProducts = ref([])

const newPlanned = ref({ name: '', amount: 1, price: 0 })
const newActual = ref({ name: '', amount: 1, price: 0, planLinkId: null })

const levelLabels = ['Бюджет', 'Направления', 'Типы', 'Статьи', 'Товары']

const totalBudget = computed(() => props.subsidies.reduce((s, x) => s + (x.budget || 0), 0))
const totalCategories = computed(() => {
  // Sum of all level 1 budgets
  return currentDirections.value.reduce((s, x) => s + (x.budget || 0), 0)
})
const remaining = computed(() => totalBudget.value - totalCategories.value)
const subsidyTotal = computed(() => currentDirections.value.reduce((s, x) => s + (x.budget || 0), 0))

const title = computed(() => levelLabels[currentLevel.value] || 'Детализация')
const breadcrumbText = computed(() => {
  if (currentLevel.value === 0) return 'Общий бюджет всех субсидий'
  if (currentSubsidy.value) return currentSubsidy.value.name
  return ''
})

const plannedProducts = computed(() => currentProducts.value.filter(p => (p.planned_total || 0) > 0))
const actualProducts = computed(() => currentProducts.value.filter(p => (p.actual_total || 0) > 0))

const maxBudget = computed(() => {
  if (currentLevel.value === 0) return Math.max(...props.subsidies.map(s => s.budget || 0), 1)
  if (currentDirections.value.length) return Math.max(...currentDirections.value.map(d => d.budget || 0), 1)
  if (currentTypes.value.length) return Math.max(...currentTypes.value.map(t => t.budget || 0), 1)
  return 1
})

const barColors = ['#E91E63', '#9C27B0', '#673AB7', '#3F51B5', '#2196F3', '#00BCD4', '#009688', '#4CAF50']
function getBarColor(id) { return barColors[(id - 1) % barColors.length] }
function getBarHeight(value) { return Math.max((value / maxBudget.value) * 240, 10) }
function getProgress(item) { return item.budget ? Math.min(((item.planned_total || 0) / item.budget) * 100, 100) : 0 }
function formatNumber(num) {
  if (!num) return '0'
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'М'
  if (num >= 1000) return (num / 1000).toFixed(0) + 'К'
  return num.toString()
}

async function loadDirections(subsidyId) {
  try {
    const res = await fetch(`/api/expense-directions/?subsidy_id=${subsidyId}`)
    const data = await res.json()
    currentDirections.value = data.filter(d => d.level === 1)
  } catch (e) { console.error('Error:', e) }
}

async function loadTypes(parentId) {
  try {
    const res = await fetch('/api/expense-directions/')
    const all = await res.json()
    currentTypes.value = all.filter(d => d.parent_id === parentId && d.level === 2)
  } catch (e) { console.error('Error:', e) }
}

async function loadExpenses(parentId) {
  try {
    const res = await fetch('/api/expense-directions/')
    const all = await res.json()
    currentExpenses.value = all.filter(d => d.parent_id === parentId && d.level === 3)
  } catch (e) { console.error('Error:', e) }
}

async function loadProducts(parentId) {
  try {
    const res = await fetch('/api/expense-directions/')
    const all = await res.json()
    currentProducts.value = all.filter(d => d.parent_id === parentId && (d.level === 4 || d.level === 5))
  } catch (e) { console.error('Error:', e) }
}

function drillToSubsidy(sub) {
  history.value.push({ level: 0, subsidy: null, parent: null })
  currentSubsidy.value = sub
  currentLevel.value = 1
  loadDirections(sub.id)
}

function drillToType(dir) {
  history.value.push({ level: 1, subsidy: currentSubsidy.value, parent: null })
  currentParent.value = dir
  currentLevel.value = 2
  loadTypes(dir.id)
}

function drillToExpense(type) {
  history.value.push({ level: 2, subsidy: currentSubsidy.value, parent: type })
  currentLevel.value = 3
  loadExpenses(type.id)
}

function drillToProducts(exp) {
  history.value.push({ level: 3, subsidy: currentSubsidy.value, parent: exp })
  currentLevel.value = 4
  loadProducts(exp.id)
}

function goBack() {
  if (history.value.length === 0) { close(); return }
  const prev = history.value.pop()
  currentLevel.value = prev.level
  currentSubsidy.value = prev.subsidy
  currentParent.value = prev.parent
  if (prev.level === 0) currentDirections.value = []
  else if (prev.level === 1) loadDirections(currentSubsidy.value?.id)
  else if (prev.level === 2) loadTypes(currentParent.value?.id)
}

function jumpToLevel(level) {
  if (level < currentLevel.value) {
    while (history.value.length > level) history.value.pop()
    currentLevel.value = level
    if (level === 0) { currentSubsidy.value = null; currentDirections.value = [] }
  }
}

function close() {
  dialog.value = false
  currentLevel.value = 0
  history.value = []
  currentSubsidy.value = null
  currentParent.value = null
}

async function addPlanned() {
  if (!newPlanned.value.name) return
  const total = (newPlanned.value.amount || 0) * (newPlanned.value.price || 0)
  await fetch('/api/expense-directions/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      subsidy_id: currentSubsidy.value.id,
      parent_id: currentParent.value.id,
      name: newPlanned.value.name,
      level: 5,
      budget: 0,
      planned_amount: newPlanned.value.amount,
      planned_price: newPlanned.value.price,
      planned_total: total
    })
  })
  newPlanned.value = { name: '', amount: 1, price: 0 }
  loadProducts(currentParent.value.id)
}

async function addActual() {
  const total = (newActual.value.amount || 0) * (newActual.value.price || 0)
  await fetch('/api/expense-directions/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      subsidy_id: currentSubsidy.value.id,
      parent_id: currentParent.value.id,
      name: newActual.value.name || 'Фактический товар',
      level: 5,
      budget: 0,
      actual_amount: newActual.value.amount,
      actual_price: newActual.value.price,
      actual_total: total,
      actual_name: newActual.value.name,
      plan_link_id: newActual.value.planLinkId
    })
  })
  newActual.value = { name: '', amount: 1, price: 0, planLinkId: null }
  loadProducts(currentParent.value.id)
}

watch(() => props.modelValue, (v) => {
  if (v) { currentLevel.value = 0; history.value = [] }
})
</script>

<style scoped>
.budget-drill-dialog { min-height: 600px; }
.summary-cards { display: flex; justify-content: space-around; gap: 16px; }
.direction-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.direction-card { padding: 16px; }
.chart-container { display: flex; align-items: flex-end; justify-content: space-around; height: 300px; padding: 20px; background: linear-gradient(180deg, #f5f5f5 0%, #e0e0e0 100%); border-radius: 8px; }
.chart-bar-wrapper { display: flex; flex-direction: column; align-items: center; flex: 1; max-width: 80px; margin: 0 4px; }
.chart-bar-wrapper.clickable { cursor: pointer; transition: transform 0.2s; }
.chart-bar-wrapper.clickable:hover { transform: scale(1.05); }
.chart-bar { width: 100%; min-height: 20px; border-radius: 4px 4px 0 0; display: flex; align-items: flex-start; justify-content: center; padding-top: 8px; transition: height 0.5s ease-out; }
.bar-value { font-size: 10px; font-weight: bold; color: white; text-shadow: 0 1px 2px rgba(0,0,0,0.5); }
.bar-label { margin-top: 8px; font-size: 11px; text-align: center; color: #666; max-width: 70px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.clickable { cursor: pointer; transition: background-color 0.2s; }
.clickable:hover { background-color: #f5f5f5; }
.slide-fade-enter-active, .slide-fade-leave-active { transition: all 0.3s ease-out; }
.slide-fade-enter-from { transform: translateX(30px); opacity: 0; }
.slide-fade-leave-to { transform: translateX(-30px); opacity: 0; }
.level-dots { display: flex; justify-content: center; gap: 12px; }
.level-dot { width: 32px; height: 32px; border-radius: 50%; background: #ddd; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: bold; cursor: pointer; transition: all 0.3s; }
.level-dot.active { background: #2196F3; color: white; transform: scale(1.2); }
.level-dot:hover:not(.active) { background: #bbb; }
</style>
