<template>
  <v-container>
    <v-row>
      <v-col cols="12">
        <v-card class="pa-6">
          <div class="d-flex justify-space-between align-center mb-6">
            <div>
              <v-card-title class="text-h4 mb-2">
                <v-icon icon="mdi-plus-circle" class="mr-4" />Новый заказ
              </v-card-title>
              <v-card-subtitle class="text-h6">
                Создание нового заказа с выбором товаров
              </v-card-subtitle>
            </div>
            <div>
              <v-btn variant="outlined" to="/orders" prepend-icon="mdi-arrow-left" class="mr-2">
                К списку заказов
              </v-btn>
              <v-btn variant="outlined" to="/" prepend-icon="mdi-home">
                На дашборд
              </v-btn>
            </div>
          </div>
          
          <v-alert
            v-if="errorMessage"
            type="error"
            class="mb-6"
            @click="errorMessage = ''"
            closable
          >
            {{ errorMessage }}
          </v-alert>
          
          <v-alert
            v-if="successMessage"
            type="success"
            class="mb-6"
            @click="successMessage = ''"
            closable
          >
            {{ successMessage }}
          </v-alert>
          
          <v-form @submit.prevent="saveOrder">
            <!-- Основная информация о заказе -->
            <v-row class="mb-8">
              <v-col cols="12" md="6">
                <v-text-field
                  label="Номер заказа"
                  v-model="orderNumber"
                  variant="outlined"
                  class="mb-4"
                  required
                  :rules="[v => !!v || 'Введите номер заказа']"
                  placeholder="Например: ORD-2025-001"
                />
                
                <v-select
                  label="Контрагент"
                  :items="contractors"
                  v-model="selectedContractor"
                  variant="outlined"
                  class="mb-4"
                  required
                  :rules="[v => !!v || 'Выберите контрагента']"
                  :loading="loadingContractors"
                />
                
                <v-select
                  label="Субсидия"
                  :items="subsidies"
                  item-title="name"
                  item-value="id"
                  v-model="selectedSubsidy"
                  variant="outlined"
                  class="mb-4"
                  required
                  :rules="[v => !!v || 'Выберите субсидию']"
                  :loading="loadingSubsidies"
                >
                  <template v-slot:item="{ props, item }">
                    <v-list-item v-bind="props">
                      <v-list-item-title>{{ item.raw.name }}</v-list-item-title>
                      <v-list-item-subtitle v-if="item.raw.description">
                        {{ item.raw.description }}
                      </v-list-item-subtitle>
                    </v-list-item>
                  </template>
                </v-select>
              </v-col>
              
              <v-col cols="12" md="6">
                <v-select
                  label="Направление расходов ФЭО"
                  :items="feoCategories"
                  item-title="name"
                  item-value="id"
                  v-model="selectedFeoCategory"
                  variant="outlined"
                  class="mb-4"
                  required
                  :rules="[v => !!v || 'Выберите направление ФЭО']"
                  :loading="loadingFeoCategories"
                />
                
                <v-select
                  label="Тип расходов ФЭО"
                  :items="feoTypes"
                  v-model="selectedFeoType"
                  variant="outlined"
                  class="mb-4"
                  required
                  :rules="[v => !!v || 'Выберите тип расходов']"
                />
                
                <v-textarea
                  label="Комментарий к заказу"
                  v-model="orderComment"
                  variant="outlined"
                  rows="3"
                  class="mb-4"
                  placeholder="Дополнительная информация о заказе..."
                  auto-grow
                />
              </v-col>
            </v-row>
            
            <!-- Секция товаров -->
            <v-card variant="outlined" class="mb-8 pa-4">
              <div class="d-flex justify-space-between align-center mb-4">
                <div>
                  <h3 class="text-h6">Товары в заказе</h3>
                  <div class="text-caption text-medium-emphasis">
                    {{ orderProducts.length }} {{ pluralize(orderProducts.length, ['товар', 'товара', 'товаров']) }}
                  </div>
                </div>
                <v-btn 
                  color="primary" 
                  prepend-icon="mdi-plus"
                  @click="showProductSelector = true"
                  :loading="loadingProducts"
                >
                  Добавить товар
                </v-btn>
              </div>
              
              <!-- Таблица добавленных товаров -->
              <div v-if="orderProducts.length > 0">
                <v-table class="mb-4">
                  <thead>
                    <tr>
                      <th style="width: 100px;">Фото</th>
                      <th style="min-width: 200px;">Наименование</th>
                      <th style="width: 200px;">Описание</th>
                      <th style="width: 80px;">Категория</th>
                      <th style="width: 100px;">Количество</th>
                      <th style="width: 120px;">Цена (₽)</th>
                      <th style="width: 120px;">Сумма (₽)</th>
                      <th style="width: 80px;">Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(item, index) in orderProducts" :key="index">
                      <td>
                        <v-avatar v-if="item.product.photo_url" size="90">
                          <v-img :src="item.product.photo_url" cover />
                        </v-avatar>
                        <v-avatar v-else color="grey-lighten-2" size="90">
                          <v-icon icon="mdi-package-variant" color="grey-darken-1" />
                        </v-avatar>
                      </td>
                      <td>
                        <div class="font-weight-medium">{{ item.product.name }}</div>
                        <div class="text-caption text-medium-emphasis">
                          {{ item.unitOfMeasure }} · {{ item.unitsPerPackage }} шт./уп.
                        </div>
                      </td>
                      <td>
                        <div v-if="item.product.description" class="description-cell">
                          <div class="description-preview text-caption" :title="item.product.description">
                            {{ truncateText(item.product.description, 250) }}
                          </div>
                          <v-btn 
                            v-if="item.product.description.length > 250"
                            size="x-small" 
                            variant="text" 
                            color="primary"
                            class="mt-1"
                            @click="showFullDescription(item.product.description)"
                          >
                            Подробнее
                          </v-btn>
                        </div>
                        <span v-else class="text-caption text-medium-emphasis">—</span>
                      </td>
                      <td>
                        <v-chip v-if="item.product.category" size="small" color="info" variant="flat">
                          {{ item.product.category }}
                        </v-chip>
                        <span v-else class="text-caption text-medium-emphasis">—</span>
                      </td>
                      <td>
                        <v-text-field
                          v-model="item.quantity"
                          type="number"
                          variant="outlined"
                          density="compact"
                          min="1"
                          hide-details
                          style="max-width: 90px;"
                          @input="updateProductQuantity(index, $event)"
                        />
                      </td>
                      <td>
                        <v-text-field
                          v-model="item.price"
                          type="number"
                          variant="outlined"
                          density="compact"
                          min="0"
                          step="0.01"
                          hide-details
                          style="max-width: 120px;"
                          @input="updateProductPrice(index, $event)"
                        />
                      </td>
                      <td class="font-weight-medium">
                        {{ formatCurrency(item.quantity * item.price) }}
                      </td>
                      <td>
                        <v-btn
                          icon="mdi-delete"
                          variant="text"
                          size="small"
                          color="error"
                          @click="removeProduct(index)"
                        />
                      </td>
                    </tr>
                  </tbody>
                </v-table>
                
                <!-- Итоговая сумма -->
                <div class="d-flex justify-end">
                  <v-card variant="outlined" class="pa-4">
                    <div class="text-right">
                      <div class="text-caption text-medium-emphasis">Общая сумма заказа</div>
                      <div class="text-h5 font-weight-bold">
                        {{ formatCurrency(orderTotal) }}
                      </div>
                      <div class="text-caption">
                        {{ orderProducts.length }} {{ pluralize(orderProducts.length, ['товар', 'товара', 'товаров']) }}
                      </div>
                    </div>
                  </v-card>
                </div>
              </div>
              
              <!-- Сообщение при отсутствии товаров -->
              <div v-else class="text-center py-8 text-medium-emphasis">
                <v-icon icon="mdi-package-variant-closed" size="48" class="mb-2" />
                <div>Нет добавленных товаров</div>
                <div class="text-caption mt-1">Нажмите "Добавить товар" для начала работы</div>
              </div>
            </v-card>
            
            <!-- Модальное окно выбора товара -->
            <v-dialog v-model="showProductSelector" max-width="900" persistent>
              <v-card>
                <v-card-title class="text-h6">
                  <v-icon icon="mdi-package-variant" class="mr-2" />
                  Выбор товара
                  <v-spacer />
                  <v-btn
                    icon="mdi-close"
                    variant="text"
                    @click="showProductSelector = false"
                  />
                </v-card-title>
                <v-card-text class="pt-4">
                  <advanced-product-selector
                    ref="productSelectorRef"
                    @product-selected="onProductSelectedFromSelector"
                  />
                </v-card-text>
                <v-card-actions>
                  <v-spacer />
                  <v-btn variant="text" @click="showProductSelector = false">
                    Отмена
                  </v-btn>
                  <v-btn 
                    color="primary" 
                    @click="addProductFromSelector"
                    :disabled="!selectedProductFromSelector"
                    :loading="addingProduct"
                  >
                    Добавить в заказ
                  </v-btn>
                </v-card-actions>
              </v-card>
            </v-dialog>
            
            <!-- Модальное окно полного описания -->
            <v-dialog v-model="showDescriptionDialog" max-width="800">
              <v-card>
                <v-card-title class="text-h6">
                  <v-icon icon="mdi-text" class="mr-2" />
                  Полное описание товара
                  <v-spacer />
                  <v-btn
                    icon="mdi-close"
                    variant="text"
                    @click="showDescriptionDialog = false"
                  />
                </v-card-title>
                <v-card-text>
                  <div class="pre-formatted text-body-1 pa-4" style="white-space: pre-wrap; max-height: 400px; overflow-y: auto;">
                    {{ fullDescription }}
                  </div>
                </v-card-text>
                <v-card-actions>
                  <v-spacer />
                  <v-btn color="primary" @click="showDescriptionDialog = false">
                    Закрыть
                  </v-btn>
                </v-card-actions>
              </v-card>
            </v-dialog>
            
            <!-- Бюджетная информация -->
            <v-card variant="outlined" class="mb-8 pa-4">
              <div class="d-flex justify-space-between align-center mb-2">
                <span class="text-subtitle-2">Бюджетная информация</span>
                <v-chip 
                  :color="budgetStatus.color" 
                  size="small"
                  :prepend-icon="budgetStatus.icon"
                >
                  {{ budgetStatus.text }}
                </v-chip>
              </div>
              
              <div class="text-body-2">
                <div class="d-flex justify-space-between mb-1">
                  <span>Общая сумма заказа:</span>
                  <span class="font-weight-medium">{{ formatCurrency(orderTotal) }}</span>
                </div>
                <div class="d-flex justify-space-between mb-1">
                  <span>Лимит по направлению:</span>
                  <span class="font-weight-medium">{{ formatCurrency(2800000) }}</span>
                </div>
                <div class="d-flex justify-space-between">
                  <span>Остаток после заказа:</span>
                  <span :class="budgetRemaining >= 0 ? 'text-success' : 'text-error'">
                    {{ formatCurrency(budgetRemaining) }}
                  </span>
                </div>
              </div>
              
              <v-alert 
                v-if="budgetRemaining < 0"
                type="warning" 
                variant="tonal" 
                class="mt-4"
                icon="mdi-alert"
              >
                Внимание! Сумма заказа превышает лимит по направлению на {{ formatCurrency(Math.abs(budgetRemaining)) }}
              </v-alert>
            </v-card>
            
            <!-- Кнопки действий -->
            <div class="d-flex">
              <v-btn 
                color="primary" 
                type="submit"
                :disabled="orderProducts.length === 0 || !isFormValid || savingOrder"
                :loading="savingOrder"
                class="mr-4"
                prepend-icon="mdi-content-save"
                size="large"
              >
                Сохранить заказ
              </v-btn>
              <v-btn 
                variant="outlined" 
                to="/orders" 
                prepend-icon="mdi-close"
                :disabled="savingOrder"
                size="large"
              >
                Отмена
              </v-btn>
            </div>
          </v-form>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import AdvancedProductSelector from '../components/AdvancedProductSelector.vue'

const router = useRouter()
const errorMessage = ref('')
const successMessage = ref('')
const savingOrder = ref(false)
const addingProduct = ref(false)

// Данные заказа
const orderNumber = ref('')
const selectedContractor = ref('')
const selectedSubsidy = ref<number | null>(null)
const selectedFeoCategory = ref<number | null>(null)
const selectedFeoType = ref('')
const orderComment = ref('')
const orderProducts = ref<Array<{
  product: any
  quantity: number
  price: number
  unitsPerPackage: number
  unitOfMeasure: string
}>>([])

// Состояние загрузки
const loadingContractors = ref(false)
const loadingSubsidies = ref(false)
const loadingFeoCategories = ref(false)
const loadingProducts = ref(false)

// Справочники
const contractors = ref<string[]>([])
const subsidies = ref<any[]>([])
const feoCategories = ref<any[]>([])
const feoTypes = ref([
  'Приобретение',
  'Аренда',
  'Обслуживание',
  'Ремонт',
  'Разработка',
  'Консалтинг'
])

// Выбор товара
const showProductSelector = ref(false)
const selectedProductFromSelector = ref<any>(null)
const productSelectorRef = ref()

// Модальное окно для полного описания
const showDescriptionDialog = ref(false)
const fullDescription = ref('')

// Вспомогательные функции
const formatCurrency = (amount: number) => {
  return amount.toLocaleString() + ' ₽'
}

const pluralize = (value: number, words: string[]) => {
  const cases = [2, 0, 1, 1, 1, 2]
  return words[(value % 100 > 4 && value % 100 < 20) ? 2 : cases[Math.min(value % 10, 5)]]
}

const truncateText = (text: string, maxLength: number) => {
  if (text.length <= maxLength) return text
  return text.substring(0, maxLength) + '...'
}

// Показать полное описание
const showFullDescription = (description: string) => {
  fullDescription.value = description
  showDescriptionDialog.value = true
}

// Расчеты
const orderTotal = computed(() => {
  return orderProducts.value.reduce((total, item) => {
    return total + (item.quantity * item.price)
  }, 0)
})

const budgetRemaining = computed(() => {
  const budgetLimit = 2800000
  return budgetLimit - orderTotal.value
})

const budgetStatus = computed(() => {
  if (budgetRemaining.value < 0) {
    return {
      text: 'Превышение',
      color: 'error',
      icon: 'mdi-alert'
    }
  } else if (budgetRemaining.value < 500000) {
    return {
      text: 'Мало осталось',
      color: 'warning',
      icon: 'mdi-alert-circle'
    }
  } else {
    return {
      text: 'В пределах',
      color: 'success',
      icon: 'mdi-check-circle'
    }
  }
})

const isFormValid = computed(() => {
  return (
    selectedContractor.value &&
    selectedSubsidy.value &&
    selectedFeoCategory.value &&
    selectedFeoType.value &&
    orderNumber.value
  )
})

// Загрузка данных
const loadContractors = async () => {
  loadingContractors.value = true
  try {
    const response = await fetch('/api/contractors/')
    if (response.ok) {
      const data = await response.json()
      contractors.value = data.map((c: any) => c.name || c.full_name)
      if (contractors.value.length === 0) {
        contractors.value = [
          'ООО "ТехноПрофи"',
          'ИП Иванов И.И.',
          'АО "СтройКомплект"',
          'ЗАО "Электросила"',
          'Не определён'
        ]
      }
    }
  } catch (error) {
    console.error('Ошибка загрузки контрагентов:', error)
    contractors.value = [
      'ООО "ТехноПрофи"',
      'ИП Иванов И.И.',
      'АО "СтройКомплект"',
      'ЗАО "Электросила"',
      'Не определён'
    ]
  } finally {
    loadingContractors.value = false
  }
}

const loadSubsidies = async () => {
  loadingSubsidies.value = true
  try {
    const response = await fetch('/api/subsidies/')
    if (response.ok) {
      subsidies.value = await response.json()
    }
  } catch (error) {
    console.error('Ошибка загрузки субсидий:', error)
  } finally {
    loadingSubsidies.value = false
  }
}

const loadFeoCategories = async () => {
  loadingFeoCategories.value = true
  try {
    const response = await fetch('/api/feo-categories/')
    if (response.ok) {
      feoCategories.value = await response.json()
    }
  } catch (error) {
    console.error('Ошибка загрузки категорий ФЭО:', error)
  } finally {
    loadingFeoCategories.value = false
  }
}

// Обработчики товаров
const onProductSelectedFromSelector = (data: any) => {
  selectedProductFromSelector.value = data
}

const addProductFromSelector = () => {
  if (!selectedProductFromSelector.value) {
    errorMessage.value = 'Товар не выбран'
    return
  }
  
  addingProduct.value = true
  try {
    // Проверяем, не добавлен ли уже этот товар
    const existingIndex = orderProducts.value.findIndex(
      item => item.product.id === selectedProductFromSelector.value.product.id
    )
    
    if (existingIndex >= 0) {
      // Увеличиваем количество существующего товара
      orderProducts.value[existingIndex].quantity += selectedProductFromSelector.value.quantity
    } else {
      // Добавляем новый товар
      orderProducts.value.push({
        product: selectedProductFromSelector.value.product,
        quantity: selectedProductFromSelector.value.quantity,
        price: selectedProductFromSelector.value.price,
        unitsPerPackage: selectedProductFromSelector.value.unitsPerPackage,
        unitOfMeasure: selectedProductFromSelector.value.unitOfMeasure
      })
    }
    
    // Сбрасываем выбор и закрываем модальное окно
    selectedProductFromSelector.value = null
    showProductSelector.value = false
    
  } catch (error: any) {
    console.error('Ошибка добавления товара:', error)
    errorMessage.value = `Ошибка добавления товара: ${error.message}`
  } finally {
    addingProduct.value = false
  }
}

const updateProductQuantity = (index: number, value: any) => {
  const quantity = parseInt(value) || 1
  orderProducts.value[index].quantity = Math.max(1, quantity)
}

const updateProductPrice = (index: number, value: any) => {
  const price = parseFloat(value) || 0
  orderProducts.value[index].price = Math.max(0, price)
}

const removeProduct = (index: number) => {
  orderProducts.value.splice(index, 1)
}

// Сохранение заказа
const saveOrder = async () => {
  if (!isFormValid.value || orderProducts.length === 0) {
    errorMessage.value = 'Заполните все обязательные поля и добавьте хотя бы один товар'
    return
  }
  
  savingOrder.value = true
  errorMessage.value = ''
  
  try {
    // Подготовка данных для сохранения
    const orderData = {
      number: orderNumber.value,
      contractor: selectedContractor.value,
      subsidy_id: selectedSubsidy.value,
      feo_category_id: selectedFeoCategory.value,
      feo_type: selectedFeoType.value,
      comment: orderComment.value,
      products: orderProducts.value.map(item => ({
        product_id: item.product.id,
        quantity: item.quantity,
        price: item.price,
        units_per_package: item.unitsPerPackage,
        unit_of_measure: item.unitOfMeasure
      })),
      total: orderTotal.value
    }
    
    console.log('Сохранение заказа:', orderData)
    
    // Имитация сохранения
    await new Promise(resolve => setTimeout(resolve, 1000))
    
    successMessage.value = `Заказ ${orderNumber.value} успешно создан!`
    
    // Через 2 секунды перенаправляем на список заказов
    setTimeout(() => {
      router.push('/orders')
    }, 2000)
    
  } catch (error: any) {
    console.error('Ошибка сохранения заказа:', error)
    errorMessage.value = `Ошибка сохранения заказа: ${error.message}`
  } finally {
    savingOrder.value = false
  }
}

// Загрузка данных при монтировании
onMounted(() => {
  loadContractors()
  loadSubsidies()
  loadFeoCategories()
})
</script>

<style scoped>
.v-table {
  border-radius: 8px;
  overflow: hidden;
}
.text-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.description-cell {
  max-width: 300px;
}
.description-preview {
  display: -webkit-box;
  -webkit-line-clamp: 5;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
  max-height: 7em;
}
.pre-formatted {
  white-space: pre-wrap;
  word-break: break-word;
}
</style>