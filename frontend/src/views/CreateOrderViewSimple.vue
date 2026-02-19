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
              </v-col>
              
              <v-col cols="12" md="6">
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
                
                <v-textarea
                  label="Комментарий к заказу"
                  v-model="orderComment"
                  variant="outlined"
                  rows="3"
                  class="mb-4"
                  placeholder="Дополнительная информация о заказе..."
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
                <v-btn color="primary" prepend-icon="mdi-plus" @click="addEmptyProduct">
                  Добавить товар
                </v-btn>
              </div>
              
              <!-- Список товаров -->
              <div v-if="orderProducts.length > 0">
                <v-table class="mb-4">
                  <thead>
                    <tr>
                      <th>Наименование</th>
                      <th>Количество</th>
                      <th>Цена (₽)</th>
                      <th>Сумма (₽)</th>
                      <th>Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(product, index) in orderProducts" :key="index">
                      <td>
                        <v-text-field
                          v-model="product.name"
                          variant="outlined"
                          density="compact"
                          placeholder="Наименование товара"
                          :rules="[v => !!v || 'Введите наименование']"
                        />
                      </td>
                      <td style="width: 120px;">
                        <v-text-field
                          v-model="product.quantity"
                          type="number"
                          variant="outlined"
                          density="compact"
                          min="1"
                          style="max-width: 100px;"
                        />
                      </td>
                      <td style="width: 140px;">
                        <v-text-field
                          v-model="product.price"
                          type="number"
                          variant="outlined"
                          density="compact"
                          min="0"
                          step="0.01"
                          style="max-width: 120px;"
                        >
                          <template v-slot:append>
                            <span class="text-caption">₽</span>
                          </template>
                        </v-text-field>
                      </td>
                      <td class="font-weight-medium">
                        {{ formatCurrency(product.quantity * product.price) }}
                      </td>
                      <td style="width: 80px;">
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
                    </div>
                  </v-card>
                </div>
              </div>
              
              <!-- Сообщение при отсутствии товаров -->
              <div v-else class="text-center py-8 text-medium-emphasis">
                <v-icon icon="mdi-package-variant-closed" size="48" class="mb-2" />
                <div>Нет добавленных товаров</div>
                <v-btn
                  color="primary"
                  variant="text"
                  size="small"
                  class="mt-2"
                  @click="addEmptyProduct"
                >
                  Добавить первый товар
                </v-btn>
              </div>
            </v-card>
            
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
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const errorMessage = ref('')
const successMessage = ref('')
const savingOrder = ref(false)

// Данные заказа
const orderNumber = ref('')
const selectedContractor = ref('')
const selectedSubsidy = ref('')
const selectedFeoLevel1 = ref('')
const selectedFeoLevel2 = ref('')
const orderComment = ref('')
const orderProducts = ref<Array<{name: string, quantity: number, price: number}>>([])

// Справочники
const contractors = ref([
  'ООО "ТехноПрофи"',
  'ИП Иванов И.И.',
  'АО "СтройКомплект"',
  'ЗАО "Электросила"',
  'Не определён'
])

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

// Вспомогательные функции
const formatCurrency = (amount: number) => {
  return amount.toLocaleString() + ' ₽'
}

const pluralize = (value: number, words: string[]) => {
  const cases = [2, 0, 1, 1, 1, 2]
  return words[(value % 100 > 4 && value % 100 < 20) ? 2 : cases[Math.min(value % 10, 5)]]
}

// Расчеты
const orderTotal = computed(() => {
  return orderProducts.value.reduce((total, item) => {
    const quantity = Number(item.quantity) || 0
    const price = Number(item.price) || 0
    return total + (quantity * price)
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
    selectedFeoLevel1.value &&
    selectedFeoLevel2.value &&
    orderNumber.value
  )
})

// Методы работы с товарами
const addEmptyProduct = () => {
  orderProducts.value.push({
    name: '',
    quantity: 1,
    price: 0
  })
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
  
  // Проверка, что все товары имеют наименования
  const invalidProducts = orderProducts.value.filter(p => !p.name.trim())
  if (invalidProducts.length > 0) {
    errorMessage.value = 'Укажите наименование для всех товаров'
    return
  }
  
  savingOrder.value = true
  errorMessage.value = ''
  
  try {
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
</script>

<style scoped>
.v-table {
  border-radius: 8px;
  overflow: hidden;
}
</style>