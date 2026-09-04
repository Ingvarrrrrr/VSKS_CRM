<template>
  <v-dialog :model-value="visible" @update:model-value="$emit('update:visible', $event)" max-width="900" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex justify-space-between align-center">
        <div>
          <v-icon :icon="icon" class="mr-2" />
          {{ title }}
        </div>
        <v-btn icon="mdi-close" variant="text" @click="$emit('update:visible', false)" />
      </v-card-title>
      
      <v-card-text>
        <!-- Фильтр субсидий -->
        <v-row class="mb-4">
          <v-col cols="12">
            <v-select
              v-model="selectedSubsidyId"
              :items="availableSubsidies"
              item-title="name"
              item-value="id"
              label="Выберите субсидию"
              variant="outlined"
              clearable
              @update:model-value="loadBudgetTree"
              prepend-icon="mdi-filter"
            >
              <template v-slot:item="{ props, item }">
                <v-list-item v-bind="props">
                  <v-list-item-title>
                    {{ item.raw.name }} ({{ formatCurrency(item.raw.budget) }})
                  </v-list-item-title>
                  <v-list-item-subtitle>
                    Год {{ item.raw.year }}, остаток: {{ formatCurrency(item.raw.budget - (item.raw.paid || 0)) }}
                  </v-list-item-subtitle>
                </v-list-item>
              </template>
            </v-select>
          </v-col>
        </v-row>
        
        <!-- Общая сводка -->
        <v-row v-if="selectedSubsidy" class="mb-6">
          <v-col v-for="metric in summaryMetrics" :key="metric.label" cols="12" md="3">
            <v-card :color="metric.color" variant="tonal" class="pa-3 text-center">
              <div class="text-caption">{{ metric.label }}</div>
              <div class="text-h6 font-weight-bold">{{ formatCurrency(metric.value) }}</div>
              <div class="text-caption">{{ metric.percent }}%</div>
            </v-card>
          </v-col>
        </v-row>
        
        <!-- Дерево бюджета -->
        <v-card variant="outlined" class="pa-4">
          <div class="d-flex justify-space-between align-center mb-4">
            <v-card-title class="text-h6 pa-0">
              Иерархия бюджета
              <v-chip v-if="selectedSubsidy" size="small" color="primary" variant="flat" class="ml-2">
                {{ selectedSubsidy.name }}
              </v-chip>
            </v-card-title>
            <v-btn 
              variant="text" 
              size="small" 
              @click="expandAll = !expandAll"
              :prepend-icon="expandAll ? 'mdi-unfold-less-horizontal' : 'mdi-unfold-more-horizontal'"
            >
              {{ expandAll ? 'Свернуть всё' : 'Развернуть всё' }}
            </v-btn>
          </div>
          
          <!-- Строка поиска -->
          <v-text-field
            v-model="search"
            label="Поиск по названию"
            variant="outlined"
            prepend-icon="mdi-magnify"
            clearable
            class="mb-4"
            density="compact"
          />
          
          <!-- Иерархическое дерево -->
          <div v-if="treeItems.length > 0">
            <v-treeview
              :items="treeItems"
              v-model:open="openedItems"
              :search="search"
              :open-all="expandAll"
              :item-children="'children'"
              :item-key="'id'"
              class="budget-tree"
            >
              <template v-slot:prepend="{ item }">
                <v-icon :icon="getIcon(item.level)" :color="getColor(item.level)" />
              </template>
              
              <template v-slot:label="{ item }">
                <div class="tree-node d-flex justify-space-between align-center" style="width: 100%;">
                  <div class="node-name">
                    <span class="font-weight-medium">{{ item.name }}</span>
                    <v-chip v-if="item.code" size="x-small" color="grey" variant="outlined" class="ml-2">
                      {{ item.code }}
                    </v-chip>
                    <div v-if="item.description" class="text-caption text-medium-emphasis">
                      {{ item.description }}
                    </div>
                  </div>
                  
                  <div class="node-stats d-flex align-center gap-4">
                    <!-- Прогресс использования -->
                    <div class="progress-container" style="width: 150px;">
                      <v-progress-linear
                        :model-value="item.usedPercent || 0"
                        height="12"
                        :color="getProgressColor(item.usedPercent || 0)"
                        rounded
                        style="opacity: 0.8;"
                      >
                        <template v-slot:default>
                          <span class="text-caption">{{ item.usedPercent || 0 }}%</span>
                        </template>
                      </v-progress-linear>
                      <div class="text-caption text-center mt-1">
                        {{ formatCurrency(item.used || 0) }} / {{ formatCurrency(item.budget || 0) }}
                      </div>
                    </div>
                    
                    <!-- Статус -->
                    <v-chip 
                      v-if="item.status" 
                      :color="getStatusColor(item.status)" 
                      size="x-small"
                      variant="flat"
                    >
                      {{ item.status }}
                    </v-chip>
                  </div>
                </div>
              </template>
            </v-treeview>
          </div>
          
          <div v-else class="text-center py-12">
            <v-icon icon="mdi-folder-question" size="64" color="grey-lighten-1" class="mb-4" />
            <div class="text-h6 text-medium-emphasis">Нет данных для отображения</div>
            <div class="text-caption mt-2">Выберите субсидию или добавьте категории ФЭО</div>
          </div>
        </v-card>
      </v-card-text>
      
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="$emit('update:visible', false)">
          Закрыть
        </v-btn>
        <v-btn 
          color="primary" 
          v-if="selectedSubsidy" 
          to="/subsidies"
          :disabled="!selectedSubsidy"
        >
          Перейти к субсидии
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useDisplay } from 'vuetify'
import { safeDiv } from '@/utils/numberFormat'

const { mobile } = useDisplay()

interface Props {
  visible: boolean
  title: string
  icon: string
  breakdownType: 'budget' | 'contracted' | 'paid' | 'remaining'
  subsidies?: Array<{
    id: number
    name: string
    year: number
    budget: number
    description?: string
    contracted?: number
    paid?: number
    planned?: number
  }>
}

const props = withDefaults(defineProps<Props>(), {
  subsidies: () => [],
  breakdownType: 'budget'
})

const emit = defineEmits<{
  'update:visible': [value: boolean]
}>()

// Состояние
const selectedSubsidyId = ref<number | null>(null)
const selectedSubsidy = ref<any>(null)
const search = ref('')
const expandAll = ref(false)
const openedItems = ref<string[]>([])

// Загрузка дерева бюджета
async function loadBudgetTree() {
  if (!selectedSubsidyId.value) {
    selectedSubsidy.value = null
    return
  }
  
  // Находим выбранную субсидию
  const subsidy = props.subsidies.find(s => s.id === selectedSubsidyId.value)
  if (!subsidy) return
  
  selectedSubsidy.value = subsidy
  
  // TODO: Загрузить реальные категории ФЭО из API
  // Пока используем тестовые данные
  await loadMockBudgetTree(subsidy.id)
}

// Тестовые данные для демонстрации
async function loadMockBudgetTree(subsidyId: number) {
  // Это пример иерархии ФЭО с 5 уровнями
  const mockTree = [
    {
      id: 'dir1',
      name: 'Техническое оснащение',
      code: '100',
      level: 1,
      budget: 15_000_000,
      used: 8_500_000,
      usedPercent: 57,
      status: 'В работе',
      description: 'Закупка оборудования и техники',
      children: [
        {
          id: 'sub1',
          name: 'Компьютерная техника',
          code: '110',
          level: 2,
          budget: 8_000_000,
          used: 4_200_000,
          usedPercent: 53,
          status: 'Частично оплачено',
          description: 'Ноутбуки, ПК, периферия',
          children: [
            {
              id: 'art1',
              name: 'Ноутбуки для педагогов',
              code: '111',
              level: 3,
              budget: 4_500_000,
              used: 2_500_000,
              usedPercent: 56,
              status: 'В работе',
              description: 'Мобильные рабочие станции',
              children: [
                {
                  id: 'subject1',
                  name: 'Договор с ООО "ТехноСити"',
                  code: '1111',
                  level: 4,
                  budget: 3_200_000,
                  used: 1_800_000,
                  usedPercent: 56,
                  status: 'Исполняется',
                  description: 'Поставка 50 ноутбуков',
                  children: [
                    {
                      id: 'product1',
                      name: 'Ноутбук Lenovo ThinkPad X1',
                      code: '11111',
                      level: 5,
                      budget: 1_800_000,
                      used: 1_800_000,
                      usedPercent: 100,
                      status: 'Оплачено',
                      description: '30 шт. по 60 000 ₽',
                      quantity: 30,
                      unit: 'шт.',
                      unitPrice: 60000,
                      children: []
                    },
                    {
                      id: 'product2',
                      name: 'Ноутбук HP EliteBook 840',
                      code: '11112',
                      level: 5,
                      budget: 1_400_000,
                      used: 0,
                      usedPercent: 0,
                      status: 'В поставке',
                      description: '20 шт. по 70 000 ₽',
                      quantity: 20,
                      unit: 'шт.',
                      unitPrice: 70000,
                      children: []
                    }
                  ]
                }
              ]
            }
          ]
        }
      ]
    },
    {
      id: 'dir2',
      name: 'Мероприятия',
      code: '200',
      level: 1,
      budget: 10_000_000,
      used: 6_200_000,
      usedPercent: 62,
      status: 'Активно',
      description: 'Организация событий и активностей',
      children: [
        {
          id: 'sub2',
          name: 'Спортивные мероприятия',
          code: '210',
          level: 2,
          budget: 5_000_000,
          used: 3_100_000,
          usedPercent: 62,
          status: 'В работе',
          description: 'Соревнования, тренировки',
          children: []
        }
      ]
    },
    {
      id: 'dir3',
      name: 'Транспортные расходы',
      code: '300',
      level: 1,
      budget: 5_000_000,
      used: 1_800_000,
      usedPercent: 36,
      status: 'Планируется',
      description: 'Логистика и перемещения',
      children: []
    }
  ]
  
  treeItems.value = mockTree
  
  // Автоматически развернуть первые 3 уровня
  openedItems.value = ['dir1', 'sub1', 'art1', 'subject1']
}

const treeItems = ref<any[]>([])

// Доступные субсидии для выбора
const availableSubsidies = computed(() => {
  return props.subsidies.map(s => ({
    ...s,
    disabled: false
  }))
})

// Метрики сводки
const summaryMetrics = computed(() => {
  if (!selectedSubsidy.value) return []
  
  const s = selectedSubsidy.value
  const totalBudget = s.budget
  const totalUsed = treeItems.value.reduce((sum, item) => sum + (item.used || 0), 0)
  const totalAllocated = treeItems.value.reduce((sum, item) => sum + (item.budget || 0), 0)
  const remaining = totalBudget - totalAllocated
  
  return [
    { label: 'Общий бюджет', value: totalBudget, percent: 100, color: 'primary' },
    { label: 'Распределено', value: totalAllocated, percent: Math.round(safeDiv(totalAllocated, totalBudget) * 100), color: 'info' },
    { label: 'Использовано', value: totalUsed, percent: Math.round(safeDiv(totalUsed, totalAllocated) * 100), color: 'success' },
    { label: 'Не распределено', value: remaining, percent: Math.round(safeDiv(remaining, totalBudget) * 100), color: 'warning' }
  ]
})

// Иконки по уровням
function getIcon(level: number) {
  switch (level) {
    case 1: return 'mdi-folder-star'
    case 2: return 'mdi-folder-account'
    case 3: return 'mdi-folder-text'
    case 4: return 'mdi-file-document'
    case 5: return 'mdi-package-variant'
    default: return 'mdi-folder'
  }
}

// Цвета по уровням
function getColor(level: number) {
  switch (level) {
    case 1: return 'primary'
    case 2: return 'info'
    case 3: return 'success'
    case 4: return 'warning'
    case 5: return 'deep-purple'
    default: return 'grey'
  }
}

// Цвет прогресса
function getProgressColor(percent: number) {
  if (percent >= 90) return 'error'
  if (percent >= 70) return 'warning'
  if (percent >= 30) return 'info'
  return 'success'
}

// Цвет статуса
function getStatusColor(status: string) {
  switch (status.toLowerCase()) {
    case 'оплачено': return 'success'
    case 'в работе': return 'info'
    case 'активно': return 'info'
    case 'планируется': return 'warning'
    case 'исполняется': return 'primary'
    case 'в поставке': return 'deep-purple'
    case 'частично оплачено': return 'success'
    default: return 'grey'
  }
}

// Форматирование валюты
function formatCurrency(amount: number) {
  return amount.toLocaleString() + ' ₽'
}

// При изменении типа разбивки
watch(() => props.breakdownType, () => {
  if (selectedSubsidyId.value) {
    loadBudgetTree()
  }
})

// При монтировании выбрать первую субсидию, если не выбрана
onMounted(() => {
  if (props.subsidies.length > 0 && !selectedSubsidyId.value) {
    selectedSubsidyId.value = props.subsidies[0].id
    loadBudgetTree()
  }
})
</script>

<style scoped>
.budget-tree {
  max-height: 500px;
  overflow-y: auto;
}

.budget-tree .v-treeview-node {
  padding: 8px 0;
  border-bottom: 1px solid rgba(0,0,0,0.05);
}

.budget-tree .v-treeview-node:last-child {
  border-bottom: none;
}

.tree-node {
  padding: 4px 0;
}

.node-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.node-stats {
  flex-shrink: 0;
}

.progress-container {
  min-width: 150px;
}

.v-treeview-node__root {
  min-height: 48px;
}
</style>