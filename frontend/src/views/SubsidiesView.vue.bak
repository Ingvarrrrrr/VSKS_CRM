<template>
  <v-container>
    <v-row>
      <v-col cols="12">
        <v-card class="pa-6">
          <div class="d-flex justify-space-between align-center mb-6">
            <div>
              <v-card-title class="text-h4 mb-2">
                <v-icon icon="mdi-cash-multiple" class="mr-4" />Субсидии
              </v-card-title>
              <v-card-subtitle class="text-h6">
                Управление субсидиями и распределение бюджета
              </v-card-subtitle>
            </div>
            <v-btn 
              color="primary" 
              prepend-icon="mdi-plus"
              @click="showAddSubsidyDialog = true"
            >
              Добавить субсидию
            </v-btn>
          </div>
          
          <!-- Селектор выбора субсидии -->
          <v-card variant="outlined" class="mb-6 pa-4">
            <div class="d-flex align-center gap-4">
              <div class="flex-grow-1">
                <v-select
                  v-model="selectedSubsidyId"
                  :items="subsidies"
                  item-title="name"
                  item-value="id"
                  label="Выберите субсидию"
                  variant="outlined"
                  :loading="loadingSubsidies"
                  @update:model-value="loadFeoCategories"
                >
                  <template v-slot:item="{ props, item }">
                    <v-list-item v-bind="props">
                      <v-list-item-title>{{ item.raw.name }}</v-list-item-title>
                      <v-list-item-subtitle>
                        Бюджет: {{ formatCurrency(item.raw.budget) }} 
                        • Год: {{ item.raw.year }}
                      </v-list-item-subtitle>
                    </v-list-item>
                  </template>
                </v-select>
              </div>
              
              <!-- Индикатор свободных средств -->
              <div v-if="selectedSubsidy" class="text-right">
                <div class="text-caption text-medium-emphasis">Свободные средства</div>
                <div 
                  class="text-h5 font-weight-bold" 
                  :class="availableFunds >= 0 ? 'text-success' : 'text-error'"
                >
                  {{ availableFunds >= 0 ? 'Свободны' : 'Не хватает' }}
                  {{ formatCurrency(Math.abs(availableFunds)) }}
                </div>
              </div>
            </div>
          </v-card>
          
          <!-- Основная информация о выбранной субсидии -->
          <v-row v-if="selectedSubsidy">
            <v-col cols="12" md="3">
              <v-card color="primary" variant="flat" class="pa-4 h-100">
                <div class="text-h6 text-white">Общий бюджет</div>
                <div class="text-h3 text-white font-weight-bold mt-2">
                  {{ formatCurrency(selectedSubsidy.budget) }}
                </div>
                <div class="text-caption text-white mt-2">{{ selectedSubsidy.name }}</div>
              </v-card>
            </v-col>
            
            <v-col cols="12" md="3">
              <v-card color="info" variant="flat" class="pa-4 h-100">
                <div class="text-h6 text-white">Законтрактовано</div>
                <div class="text-h3 text-white font-weight-bold mt-2">
                  {{ formatCurrency(selectedSubsidy.contracted || 0) }}
                </div>
                <div class="text-caption text-white mt-2">
                  {{ calculatePercent(selectedSubsidy.contracted || 0, selectedSubsidy.budget) }}% от бюджета
                </div>
              </v-card>
            </v-col>
            
            <v-col cols="12" md="3">
              <v-card color="success" variant="flat" class="pa-4 h-100">
                <div class="text-h6 text-white">Оплачено</div>
                <div class="text-h3 text-white font-weight-bold mt-2">
                  {{ formatCurrency(selectedSubsidy.paid || 0) }}
                </div>
                <div class="text-caption text-white mt-2">
                  {{ calculatePercent(selectedSubsidy.paid || 0, selectedSubsidy.budget) }}% от бюджета
                </div>
              </v-card>
            </v-col>
            
            <v-col cols="12" md="3">
              <v-card color="warning" variant="flat" class="pa-4 h-100">
                <div class="text-h6 text-white">Остаток</div>
                <div class="text-h3 text-white font-weight-bold mt-2">
                  {{ formatCurrency(selectedSubsidy.budget - (selectedSubsidy.contracted || 0)) }}
                </div>
                <div class="text-caption text-white mt-2">
                  {{ calculatePercent(selectedSubsidy.budget - (selectedSubsidy.contracted || 0), selectedSubsidy.budget) }}% от бюджета
                </div>
              </v-card>
            </v-col>
          </v-row>
          
          <v-divider class="my-8" />
          
          <v-row>
            <!-- Категории ФЭО для выбранной субсидии -->
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="pa-4 h-100">
                <div class="d-flex justify-space-between align-center mb-4">
                  <v-card-title class="text-h6">
                    Категории ФЭО (направления расходов)
                  </v-card-title>
                  <v-btn 
                    color="primary" 
                    variant="text"
                    size="small"
                    prepend-icon="mdi-plus"
                    @click="showAddFeoCategoryDialog = true"
                  >
                    Добавить направление
                  </v-btn>
                </div>
                
                <div v-if="loadingFeoCategories" class="text-center py-8">
                  <v-progress-circular indeterminate color="primary" />
                </div>
                
                <div v-else-if="feoCategories.length === 0" class="text-center py-8 text-medium-emphasis">
                  <v-icon icon="mdi-folder-off" size="48" class="mb-2" />
                  <div>Нет категорий ФЭО</div>
                  <v-btn 
                    color="primary" 
                    variant="text"
                    size="small"
                    class="mt-2"
                    @click="showAddFeoCategoryDialog = true"
                  >
                    Добавить первую категорию
                  </v-btn>
                </div>
                
                <div v-else>
                  <v-table density="compact">
                    <thead>
                      <tr>
                        <th>Название</th>
                        <th>Уровень</th>
                        <th>Бюджет</th>
                        <th>Использовано</th>
                        <th>Действия</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="category in feoCategories" :key="category.id">
                        <td>
                          <div :style="{ marginLeft: `${(category.level - 1) * 20}px` }">
                            <v-icon v-if="category.level === 1" icon="mdi-folder" color="primary" class="mr-2" />
                            <v-icon v-else-if="category.level === 2" icon="mdi-folder-open" color="info" class="mr-2" />
                            <v-icon v-else icon="mdi-file-document" color="success" class="mr-2" />
                            {{ category.name }}
                          </div>
                        </td>
                        <td>{{ category.level }}</td>
                        <td>{{ formatCurrency(category.budget || 0) }}</td>
                        <td>{{ formatCurrency(category.used || 0) }}</td>
                        <td>
                          <v-btn
                            icon="mdi-pencil"
                            variant="text"
                            size="x-small"
                            @click="editFeoCategory(category)"
                            class="mr-2"
                          />
                          <v-btn
                            icon="mdi-cash-sync"
                            variant="text"
                            size="x-small"
                            @click="startReallocation(category)"
                          />
                        </td>
                      </tr>
                    </tbody>
                  </v-table>
                </div>
              </v-card>
            </v-col>
            
            <!-- Перераспределение бюджета -->
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="pa-4 h-100">
                <div class="d-flex justify-space-between align-center mb-4">
                  <v-card-title class="text-h6">
                    Перераспределение бюджета
                  </v-card-title>
                  <v-chip 
                    :color="budgetChangeStatus.color" 
                    size="small"
                    :prepend-icon="budgetChangeStatus.icon"
                  >
                    {{ budgetChangeStatus.text }}
                  </v-chip>
                </div>
                
                <div v-if="!selectedSubsidy" class="text-center py-8 text-medium-emphasis">
                  <v-icon icon="mdi-cash-remove" size="48" class="mb-2" />
                  <div>Выберите субсидию для работы с бюджетом</div>
                </div>
                
                <v-form v-else @submit.prevent="reallocateBudget">
                  <v-select
                    v-model="reallocation.categoryId"
                    :items="feoCategories.filter(c => c.level === 1)"
                    item-title="name"
                    item-value="id"
                    label="Направление расходов"
                    variant="outlined"
                    class="mb-4"
                    :loading="loadingFeoCategories"
                    required
                    :rules="[v => !!v || 'Выберите направление расходов']"
                    @update:model-value="onCategorySelected"
                  >
                    <template v-slot:item="{ props, item }">
                      <v-list-item v-bind="props">
                        <v-list-item-title>{{ item.raw.name }}</v-list-item-title>
                        <v-list-item-subtitle>
                          Текущий бюджет: {{ formatCurrency(item.raw.budget || 0) }}
                          • Использовано: {{ formatCurrency(item.raw.used || 0) }}
                        </v-list-item-subtitle>
                      </v-list-item>
                    </template>
                  </v-select>
                  
                  <!-- Текущая сумма направления -->
                  <v-card variant="tonal" class="mb-4 pa-3">
                    <div class="d-flex justify-space-between align-center">
                      <div class="text-caption">Текущий бюджет направления:</div>
                      <div class="text-h6 font-weight-bold">
                        {{ formatCurrency(selectedCategoryBudget) }}
                      </div>
                    </div>
                    <div v-if="selectedCategoryUsed" class="d-flex justify-space-between align-center mt-1">
                      <div class="text-caption">Из них использовано:</div>
                      <div class="text-body-1">{{ formatCurrency(selectedCategoryUsed) }}</div>
                    </div>
                  </v-card>
                  
                  <v-text-field
                    v-model.number="reallocation.newAmount"
                    label="Новая сумма, ₽"
                    variant="outlined"
                    type="number"
                    class="mb-4"
                    required
                    :rules="[v => v !== null || 'Введите сумму', v => v >= 0 || 'Сумма не может быть отрицательной']"
                    :step="1000"
                    :min="0"
                  />
                  
                  <!-- Результат перераспределения -->
                  <v-card 
                    v-if="reallocation.newAmount !== null" 
                    :color="reallocationResult.color" 
                    variant="flat"
                    class="mb-4 pa-4"
                  >
                    <div class="text-center">
                      <div class="text-h6 font-weight-bold text-white">
                        {{ reallocationResult.title }}
                      </div>
                      <div class="text-h4 font-weight-bold text-white mt-2">
                        {{ formatCurrency(Math.abs(reallocationResult.amount)) }}
                      </div>
                      <div class="text-caption text-white mt-1">
                        {{ reallocationResult.description }}
                      </div>
                    </div>
                  </v-card>
                  
                  <v-textarea
                    v-model="reallocation.justification"
                    label="Обоснование изменения бюджета"
                    variant="outlined"
                    rows="3"
                    class="mb-6"
                    required
                    :rules="[v => !!v || 'Укажите обоснование']"
                  />
                  
                  <v-btn 
                    color="primary" 
                    type="submit"
                    block
                    :loading="reallocatingBudget"
                    :disabled="!isReallocationValid"
                  >
                    Сохранить изменения
                  </v-btn>
                </v-form>
              </v-card>
            </v-col>
          </v-row>
        </v-card>
      </v-col>
    </v-row>
    
    <!-- Диалог добавления субсидии -->
    <v-dialog v-model="showAddSubsidyDialog" max-width="600">
      <v-card>
        <v-card-title class="text-h6">
          <v-icon icon="mdi-plus" class="mr-2" />
          Добавить субсидию
          <v-spacer />
          <v-btn
            icon="mdi-close"
            variant="text"
            @click="showAddSubsidyDialog = false"
          />
        </v-card-title>
        <v-card-text>
          <v-form @submit.prevent="addSubsidy">
            <v-text-field
              v-model="newSubsidy.name"
              label="Название субсидии"
              variant="outlined"
              class="mb-4"
              required
              :rules="[v => !!v || 'Введите название']"
            />
            
            <v-text-field
              v-model="newSubsidy.year"
              label="Год"
              variant="outlined"
              type="number"
              class="mb-4"
              required
              :rules="[v => !!v || 'Введите год', v => v >= 2020 || 'Год должен быть не менее 2020']"
            />
            
            <v-text-field
              v-model="newSubsidy.budget"
              label="Бюджет, ₽"
              variant="outlined"
              type="number"
              class="mb-4"
              required
              :rules="[v => !!v || 'Введите бюджет', v => v > 0 || 'Бюджет должен быть больше 0']"
              :step="1000"
            />
            
            <v-textarea
              v-model="newSubsidy.description"
              label="Описание"
              variant="outlined"
              rows="3"
              class="mb-6"
            />
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showAddSubsidyDialog = false">
            Отмена
          </v-btn>
          <v-btn 
            color="primary" 
            @click="addSubsidy"
            :loading="addingSubsidy"
            :disabled="!isNewSubsidyValid"
          >
            Добавить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    
    <!-- Диалог добавления категории ФЭО -->
    <v-dialog v-model="showAddFeoCategoryDialog" max-width="600">
      <v-card>
        <v-card-title class="text-h6">
          <v-icon icon="mdi-folder-plus" class="mr-2" />
          Добавить направление расходов
          <v-spacer />
          <v-btn
            icon="mdi-close"
            variant="text"
            @click="showAddFeoCategoryDialog = false"
          />
        </v-card-title>
        <v-card-text>
          <v-form @submit.prevent="addFeoCategory">
            <v-select
              v-model="newFeoCategory.parentId"
              :items="feoCategories.filter(c => c.level < 3)"
              item-title="name"
              item-value="id"
              label="Родительская категория (необязательно)"
              variant="outlined"
              class="mb-4"
              clearable
            >
              <template v-slot:item="{ props, item }">
                <v-list-item v-bind="props">
                  <v-list-item-title>
                    <span :style="{ marginLeft: `${(item.raw.level - 1) * 20}px` }">
                      {{ item.raw.name }}
                    </span>
                  </v-list-item-title>
                </v-list-item>
              </template>
            </v-select>
            
            <v-text-field
              v-model="newFeoCategory.name"
              label="Название направления"
              variant="outlined"
              class="mb-4"
              required
              :rules="[v => !!v || 'Введите название']"
            />
            
            <v-text-field
              v-model="newFeoCategory.code"
              label="Код (необязательно)"
              variant="outlined"
              class="mb-4"
            />
            
            <v-text-field
              v-model="newFeoCategory.budget"
              label="Бюджет, ₽"
              variant="outlined"
              type="number"
              class="mb-4"
              :step="1000"
              :min="0"
            />
            
            <v-text-field
              v-model="newFeoCategory.appendix"
              label="Приложение (необязательно)"
              variant="outlined"
              class="mb-6"
            />
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showAddFeoCategoryDialog = false">
            Отмена
          </v-btn>
          <v-btn 
            color="primary" 
            @click="addFeoCategory"
            :loading="addingFeoCategory"
            :disabled="!isNewFeoCategoryValid"
          >
            Добавить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'

interface Subsidy {
  id: number
  name: string
  year: number
  budget: number
  description?: string
  contracted?: number  // Законтрактовано (сумма всех заказов)
  paid?: number       // Оплачено (сумма всех платежей)
}

interface FeoCategory {
  id: number
  parent_id: number | null
  subsidy_id: number
  level: number
  name: string
  code: string | null
  appendix: string | null
  is_active: boolean
  budget?: number     // Выделенный бюджет на это направление
  used?: number       // Использовано средств
}

// Состояние
const loadingSubsidies = ref(false)
const loadingFeoCategories = ref(false)
const subsidies = ref<Subsidy[]>([])
const selectedSubsidyId = ref<number | null>(null)
const selectedSubsidy = computed(() => {
  return subsidies.value.find(s => s.id === selectedSubsidyId.value) || null
})
const feoCategories = ref<FeoCategory[]>([])

// Диалоги
const showAddSubsidyDialog = ref(false)
const showAddFeoCategoryDialog = ref(false)
const addingSubsidy = ref(false)
const addingFeoCategory = ref(false)

// Новая субсидия
const newSubsidy = ref({
  name: '',
  year: new Date().getFullYear(),
  budget: 0,
  description: ''
})

// Новая категория ФЭО
const newFeoCategory = ref({
  parentId: null as number | null,
  name: '',
  code: '',
  budget: 0,
  appendix: ''
})

// Перераспределение бюджета
const reallocatingBudget = ref(false)
const reallocation = ref({
  categoryId: null as number | null,
  newAmount: null as number | null,
  justification: ''
})

// Вспомогательные функции
const formatCurrency = (amount: number) => {
  return amount.toLocaleString() + ' ₽'
}

const calculatePercent = (part: number, total: number) => {
  if (!total) return 0
  return Math.round((part / total) * 100)
}

// Расчет свободных средств
const availableFunds = computed(() => {
  if (!selectedSubsidy.value) return 0
  const totalBudget = selectedSubsidy.value.budget
  const totalAllocated = feoCategories.value.reduce((sum, cat) => sum + (cat.budget || 0), 0)
  
  return totalBudget - totalAllocated
})

// Загрузка субсидий
const loadSubsidies = async () => {
  loadingSubsidies.value = true
  try {
    const response = await fetch('/api/subsidies/')
    if (response.ok) {
      const data = await response.json()
      subsidies.value = data.map((subsidy: Subsidy) => ({
        ...subsidy,
        contracted: 0,  // TODO: Загрузить реальные данные
        paid: 0         // TODO: Загрузить реальные данные
      }))
      
      // Устанавливаем первую субсидию по умолчанию
      if (subsidies.value.length > 0 && !selectedSubsidyId.value) {
        selectedSubsidyId.value = subsidies.value[0].id
        await loadFeoCategories()
      }
    }
  } catch (error) {
    console.error('Ошибка загрузки субсидий:', error)
    alert('Не удалось загрузить субсидии')
  } finally {
    loadingSubsidies.value = false
  }
}

// Загрузка категорий ФЭО
const loadFeoCategories = async () => {
  if (!selectedSubsidy.value) return
  
  loadingFeoCategories.value = true
  try {
    const response = await fetch(`/api/feo-categories/?subsidy_id=${selectedSubsidy.value.id}`)
    if (response.ok) {
      const data = await response.json()
      feoCategories.value = data.map((category: FeoCategory) => ({
        ...category,
        budget: getRandomBudget(category.level),  // TODO: Загрузить реальные данные
        used: getRandomUsed(category.level)       // TODO: Загрузить реальные данные
      }))
    }
  } catch (error) {
    console.error('Ошибка загрузки категорий ФЭО:', error)
    alert('Не удалось загрузить категории ФЭО')
  } finally {
    loadingFeoCategories.value = false
  }
}

// Вспомогательные функции для демо-данных
const getRandomBudget = (level: number) => {
  if (level === 1) return Math.floor(Math.random() * 5000000) + 1000000
  if (level === 2) return Math.floor(Math.random() * 2000000) + 500000
  return Math.floor(Math.random() * 1000000) + 100000
}

const getRandomUsed = (level: number) => {
  const budget = getRandomBudget(level)
  return Math.round(budget * (Math.random() * 0.8 + 0.1)) // 10-90% от бюджета
}

// Выбранная категория для перераспределения
const selectedCategory = computed(() => {
  if (!reallocation.value.categoryId) return null
  return feoCategories.value.find(c => c.id === reallocation.value.categoryId)
})

const selectedCategoryBudget = computed(() => {
  return selectedCategory.value?.budget || 0
})

const selectedCategoryUsed = computed(() => {
  return selectedCategory.value?.used || 0
})

// Результат перераспределения
const reallocationResult = computed(() => {
  if (reallocation.value.newAmount === null || !selectedCategory.value) {
    return {
      title: '',
      amount: 0,
      description: '',
      color: 'primary'
    }
  }
  
  const currentBudget = selectedCategory.value.budget || 0
  const change = reallocation.value.newAmount - currentBudget
  
  if (change === 0) {
    return {
      title: 'Без изменений',
      amount: 0,
      description: 'Бюджет останется прежним',
      color: 'info'
    }
  } else if (change > 0) {
    // Увеличение бюджета - проверяем, есть ли свободные средства
    if (change <= availableFunds.value) {
      return {
        title: 'Требуется дополнительно',
        amount: change,
        description: `Бюджет увеличится на ${formatCurrency(change)}`,
        color: 'warning'
      }
    } else {
      return {
        title: 'Не хватает',
        amount: change - availableFunds.value,
        description: `Недостаточно свободных средств для увеличения бюджета`,
        color: 'error'
      }
    }
  } else {
    // Уменьшение бюджета - проверяем, не меньше ли использовано
    const newBudget = currentBudget + change  // change отрицательный
    if (newBudget >= (selectedCategory.value.used || 0)) {
      return {
        title: 'Высвободится',
        amount: Math.abs(change),
        description: `Бюджет уменьшится на ${formatCurrency(Math.abs(change))}`,
        color: 'success'
      }
    } else {
      return {
        title: 'Невозможно уменьшить',
        amount: Math.abs(change),
        description: `Невозможно уменьшить бюджет меньше использованной суммы`,
        color: 'error'
      }
    }
  }
})

// Статус изменения бюджета
const budgetChangeStatus = computed(() => {
  if (availableFunds.value < 0) {
    return {
      text: 'Превышение бюджета',
      color: 'error',
      icon: 'mdi-alert'
    }
  } else if (availableFunds.value < 100000) {
    return {
      text: 'Мало свободных средств',
      color: 'warning',
      icon: 'mdi-alert-circle'
    }
  } else {
    return {
      text: 'Достаточно свободных средств',
      color: 'success',
      icon: 'mdi-check-circle'
    }
  }
})

// Валидация форм
const isNewSubsidyValid = computed(() => {
  return newSubsidy.value.name.trim() !== '' && 
         newSubsidy.value.year >= 2020 && 
         newSubsidy.value.budget > 0
})

const isNewFeoCategoryValid = computed(() => {
  return newFeoCategory.value.name.trim() !== ''
})

const isReallocationValid = computed(() => {
  return reallocation.value.categoryId !== null &&
         reallocation.value.newAmount !== null &&
         reallocation.value.newAmount >= 0 &&
         reallocation.value.justification.trim() !== ''
})

// Методы
const addSubsidy = async () => {
  addingSubsidy.value = true
  try {
    const response = await fetch('/api/subsidies/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        name: newSubsidy.value.name,
        year: parseInt(newSubsidy.value.year.toString()),
        budget: parseFloat(newSubsidy.value.budget.toString()),
        description: newSubsidy.value.description || null
      })
    })
    
    if (response.ok) {
      const newSubsidyData = await response.json()
      subsidies.value.push({
        ...newSubsidyData,
        contracted: 0,
        paid: 0
      })
      showAddSubsidyDialog.value = false
      resetNewSubsidyForm()
      
      // Выбираем новую субсидию
      selectedSubsidyId.value = newSubsidyData.id
      await loadFeoCategories()
      alert('Субсидия успешно добавлена!')
    } else {
      throw new Error('Ошибка сервера при добавлении субсидии')
    }
  } catch (error) {
    console.error('Ошибка добавления субсидии:', error)
    alert('Не удалось добавить субсидию: ' + (error as Error).message)
  } finally {
    addingSubsidy.value = false
  }
}

const addFeoCategory = async () => {
  if (!selectedSubsidy.value) {
    alert('Выберите субсидию')
    return
  }
  
  addingFeoCategory.value = true
  try {
    const response = await fetch('/api/feo-categories/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        subsidy_id: selectedSubsidy.value.id,
        parent_id: newFeoCategory.value.parentId || null,
        name: newFeoCategory.value.name,
        code: newFeoCategory.value.code || null,
        appendix: newFeoCategory.value.appendix || null,
        is_active: true
      })
    })
    
    if (response.ok) {
      const newCategory = await response.json()
      feoCategories.value.push({
        ...newCategory,
        budget: newFeoCategory.value.budget || 0,
        used: 0
      })
      showAddFeoCategoryDialog.value = false
      resetNewFeoCategoryForm()
      alert('Направление расходов успешно добавлено!')
    } else {
      throw new Error('Ошибка сервера при добавлении категории')
    }
  } catch (error) {
    console.error('Ошибка добавления категории ФЭО:', error)
    alert('Не удалось добавить направление расходов: ' + (error as Error).message)
  } finally {
    addingFeoCategory.value = false
  }
}

const reallocateBudget = async () => {
  if (!selectedSubsidy.value || !selectedCategory.value) return
  
  reallocatingBudget.value = true
  try {
    // TODO: Заменить на реальный API вызов
    console.log('Перераспределение бюджета:', {
      categoryId: reallocation.value.categoryId,
      newAmount: reallocation.value.newAmount,
      justification: reallocation.value.justification
    })
    
    // Обновляем бюджет категории локально
    const categoryIndex = feoCategories.value.findIndex(c => c.id === reallocation.value.categoryId)
    if (categoryIndex !== -1) {
      feoCategories.value[categoryIndex].budget = reallocation.value.newAmount || 0
    }
    
    alert('Бюджет успешно перераспределен!')
    resetReallocationForm()
  } catch (error) {
    console.error('Ошибка перераспределения бюджета:', error)
    alert('Не удалось перераспределить бюджет: ' + (error as Error).message)
  } finally {
    reallocatingBudget.value = false
  }
}

const startReallocation = (category: FeoCategory) => {
  reallocation.value.categoryId = category.id
  reallocation.value.newAmount = category.budget || 0
}

const editFeoCategory = (category: FeoCategory) => {
  // TODO: Реализовать редактирование категории
  console.log('Редактирование категории:', category)
  alert('Редактирование категории еще не реализовано')
}

const onCategorySelected = () => {
  if (selectedCategory.value) {
    reallocation.value.newAmount = selectedCategory.value.budget || 0
  }
}

// Сброс форм
const resetNewSubsidyForm = () => {
  newSubsidy.value = {
    name: '',
    year: new Date().getFullYear(),
    budget: 0,
    description: ''
  }
}

const resetNewFeoCategoryForm = () => {
  newFeoCategory.value = {
    parentId: null,
    name: '',
    code: '',
    budget: 0,
    appendix: ''
  }
}

const resetReallocationForm = () => {
  reallocation.value = {
    categoryId: null,
    newAmount: null,
    justification: ''
  }
}

// Загрузка при монтировании
onMounted(() => {
  loadSubsidies()
})
</script>

<style scoped>
.h-100 {
  height: 100%;
}

.gap-4 {
  gap: 16px;
}
</style>