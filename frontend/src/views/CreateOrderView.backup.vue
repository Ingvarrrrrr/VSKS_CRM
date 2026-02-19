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
          
          <!-- Сообщения об ошибках -->
          <v-alert
            v-if="errorMessage"
            type="error"
            class="mb-6"
            @click="errorMessage = ''"
            closable
          >
            {{ errorMessage }}
          </v-alert>
          
          <!-- Отладочная информация (можно убрать в продакшене) -->
          <v-alert
            v-if="debugMode"
            type="info"
            class="mb-6"
            variant="tonal"
          >
            <strong>Отладка:</strong><br>
            Товаров загружено: {{ allProductsCount }}<br>
            Выбрано товаров: {{ orderProducts.length }}<br>
            Компонент загружен: {{ componentLoaded ? '✅' : '❌' }}
          </v-alert>
          
          <v-form @submit.prevent="saveOrder">
            <v-row>
              <v-col cols="12">
                <!-- Таблица товаров -->
                <order-products-table
                  v-model="orderProducts"
                  @add-product="showProductSelector = true"
                  class="mb-8"
                  v-if="componentLoaded"
                />
                
                <!-- Сообщение, если таблица не загрузилась -->
                <v-alert
                  v-else
                  type="warning"
                  class="mb-8"
                  icon="mdi-alert"
                >
                  Компонент таблицы товаров не загружен. Попробуйте обновить страницу (F5).
                </v-alert>
                
                <!-- Выбор товара (модальное окно) -->
                <v-dialog v-model="showProductSelector" max-width="800" persistent>
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
                    <v-card-text>
                      <simple-product-selector
                        v-model="selectedProduct"
                        ref="productSelectorRef"
                        @update:model-value="onProductSelected"
                      />
                    </v-card-text>
                    <v-card-actions>
                      <v-spacer />
                      <v-btn variant="text" @click="showProductSelector = false">
                        Отмена
                      </v-btn>
                      <v-btn 
                        color="primary" 
                        :disabled="!selectedProduct"
                        @click="addProductToOrder"
                        :loading="addingProduct"
                      >
                        Добавить в заказ
                      </v-btn>
                    </v-card-actions>
                  </v-card>
                </v-dialog>
              </v-col>
            </v-row>
            
            <v-row>
              <v-col cols="12" md="6">
                <v-select
                  label="Контрагент"
                  :items="contractors"
                  v-model="selectedContractor"
                  variant="outlined"
                  class="mb-4"
                  required
                  :rules="[v => !!v || 'Выберите контрагента']"
                />
                
                <v-select
                  label="Субсидия"
                  :items="subsidies"
                  v-model="selectedSubsidy"
                  variant="outlined"
                  class="mb-4"
                  required
                  :rules="[v => !!v || 'Выберите субсидию']"
                />
                
                <v-select
                  label="Направление расходов ФЭО"
                  :items="feoLevel1"
                  v-model="selectedFeoLevel1"
                  variant="outlined"
                  class="mb-4"
                  required
                  :rules="[v => !!v || 'Выберите направление ФЭО']"
                />
                
                <v-select
                  label="Тип расходов ФЭО"
                  :items="feoLevel2"
                  v-model="selectedFeoLevel2"
                  variant="outlined"
                  class="mb-4"
                  required
                  :rules="[v => !!v || 'Выберите тип расходов']"
                />
              </v-col>
              
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
                
                <v-textarea
                  label="Комментарий к заказу"
                  v-model="orderComment"
                  variant="outlined"
                  rows="3"
                  class="mb-4"
                  placeholder="Дополнительная информация о заказе..."
                />
                
                <!-- Информация о бюджете -->
                <v-card variant="outlined" class="pa-4 mb-6">
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
                </v-card>
                
                <v-alert 
                  v-if="budgetRemaining < 0"
                  type="warning" 
                  variant="tonal" 
                  class="mb-6"
                  icon="mdi-alert"
                >
                  Внимание! Сумма заказа превышает лимит по направлению на {{ formatCurrency(Math.abs(budgetRemaining)) }}
                </v-alert>
                
                <div class="d-flex">
                  <v-btn 
                    color="primary" 
                    type="submit"
                    :disabled="orderProducts.length === 0 || !isFormValid || savingOrder"
                    :loading="savingOrder"
                    class="mr-4"
                    prepend-icon="mdi-content-save"
                  >
                    Сохранить заказ
                  </v-btn>
                  <v-btn 
                    variant="outlined" 
                    to="/orders" 
                    prepend-icon="mdi-close"
                    :disabled="savingOrder"
                  >
                    Отмена
                  </v-btn>
                  <v-spacer />
                  <v-btn
                    variant="text"
                    @click="debugMode = !debugMode"
                    icon="mdi-bug"
                    size="small"
                    title="Режим отладки"
                  />
                </div>
              </v-col>
            </v-row>
          </v-form>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import SimpleProductSelector from '../components/SimpleProductSelector.vue'
import OrderProductsTable from '../components/OrderProductsTable.vue'

const router = useRouter()

// Состояние компонента
const componentLoaded = ref(false)
const debugMode = ref(false)
const errorMessage = ref('')

// Данные заказа
const orderProducts = ref<any[]>([])
const selectedProduct = ref<any>(null)
const showProductSelector = ref(false)
const addingProduct = ref(false)
const savingOrder = ref(false)
const selectedContractor = ref('')
const selectedSubsidy = ref('')
const selectedFeoLevel1 = ref('')
const selectedFeoLevel2 = ref('')
const orderNumber = ref('')
const orderComment = ref('')

// Контрагенты
const contractors = ref([
  'ООО "ТехноПрофи"',
  'ИП Иванов И.И.',
  'АО "СтройКомплект"',
  'ЗАО "Электросила"',
  'Не определён'
])

// Субсидии
const subsidies = ref([
  'Патриотика 2025',
  'ДНР_2026',
  'ЗО_2026',
  'КОС_2026',
  'ЛНР_2026',
  'МинОбр_2026',
  'МинПрос_2026',
  'ФАДМ_2026',
  'МинТруд_2026'
])

// Направления ФЭО
const feoLevel1 = ref([
  'Основные средства',
  'Материальные запасы',
  'Услуги',
  'Капитальные вложения'
])

const feoLevel2 = ref([
  'Приобретение',
  'Аренда',
  'Обслуживание',
  'Ремонт'
])

// Отладочная информация
const allProductsCount = ref(0)

// Форматирование валюты
const formatCurrency = (amount: number) => {
  return amount.toLocaleString() + ' ₽'
}

// Общая сумма заказа
const orderTotal = computed(() => {
  try {
    return orderProducts.value.reduce((total, item) => {
      const quantity = Number(item.quantity) || 0
      const price = Number(item.price) || 0
      return total + (quantity * price)
    }, 0)
  } catch (error) {
    console.error('Ошибка расчета суммы:', error)
    return 0
  }
})

// Остаток бюджета
const budgetRemaining = computed(() => {
  const budgetLimit = 2800000
  return budgetLimit - orderTotal.value
})

// Статус бюджета
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

// Валидация формы
const isFormValid = computed(() => {
  return (
    selectedContractor.value &&
    selectedSubsidy.value &&
    selectedFeoLevel1.value &&
    selectedFeoLevel2.value &&
    orderNumber.value
  )
})

// Обработчик выбора товара
const onProductSelected = (product: any) => {
  console.log('Товар выбран:', product)
  // Можно автоматически добавлять товар при выборе
  // или оставить для ручного добавления по кнопке
}

// Добавить товар в заказ
const addProductToOrder = async () => {
  if (!selectedProduct.value) {
    errorMessage.value = 'Товар не выбран'
    return
  }
  
  addingProduct.value = true
  try {
    // Проверяем, не добавлен ли уже этот товар
    const existingIndex = orderProducts.value.findIndex(
      item => item.product.id === selectedProduct.value.id
    )
    
    if (existingIndex >= 0) {
      // Увеличиваем количество существующего товара
      orderProducts.value[existingIndex].quantity += 1
    } else {
      // Добавляем новый товар
      orderProducts.value.push({
        product: selectedProduct.value,
        quantity: 1,
        price: 0
      })
    }
    
    // Сбрасываем выбор и закрываем модальное окно
    selectedProduct.value = null
    showProductSelector.value = false
    
  } catch (error: any) {
    console.error('Ошибка добавления товара:', error)
    errorMessage.value = `Ошибка добавления товара: ${error.message}`
  } finally {
    addingProduct.value = false
  }
}

// Сохранить заказ
const saveOrder = async () => {
  if (!isFormValid.value || orderProducts.value.length === 0) {
    errorMessage.value = 'Заполните все обязательные поля и добавьте хотя бы один товар'
    return
  }
  
  savingOrder.value = true
  errorMessage.value = ''
  
  try {
    // Здесь будет логика сохранения заказа
    console.log('Сохранение заказа:', {
      number: orderNumber.value,
      contractor: selectedContractor.value,
      subsidy: selectedSubsidy.value,
      feoLevel1: selectedFeoLevel1.value,
      feoLevel2: selectedFeoLevel2.value,
      comment: orderComment.value,
      products: orderProducts.value,
      total: orderTotal.value
    })
    
    // Имитация сохранения
    await new Promise(resolve => setTimeout(resolve, 1000))
    
    // Показываем уведомление
    alert(`Заказ ${orderNumber.value} успешно создан!`)
    
    // Перенаправляем на список заказов
    router.push('/orders')
    
  } catch (error: any) {
    console.error('Ошибка сохранения заказа:', error)
    errorMessage.value = `Ошибка сохранения заказа: ${error.message}`
  } finally {
    savingOrder.value = false
  }
}

// Инициализация компонента
onMounted(() => {
  console.log('CreateOrderView mounted')
  componentLoaded.value = true
  
  // Загрузка данных о товарах для отладки
  fetch('/api/products/')
    .then(response => response.json())
    .then(products => {
      allProductsCount.value = products.length
      console.log(`Загружено товаров: ${products.length}`)
    })
    .catch(error => {
      console.error('Ошибка загрузки товаров:', error)
    })
})

// Очистка при размонтировании
onUnmounted(() => {
  console.log('CreateOrderView unmounted')
})
</script>

<style scoped>
.border {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>