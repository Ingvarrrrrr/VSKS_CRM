<template>
  <div>
    <!-- Заголовок таблицы -->
    <div class="d-flex justify-space-between align-center mb-4">
      <div>
        <h3 class="text-h6">Товары в заказе</h3>
        <div class="text-caption text-medium-emphasis">
          {{ selectedProducts.length }} {{ pluralize(selectedProducts.length, ['товар', 'товара', 'товаров']) }}
        </div>
      </div>
      <v-btn
        color="primary"
        prepend-icon="mdi-plus"
        @click="$emit('add-product')"
      >
        Добавить товар
      </v-btn>
    </div>

    <!-- Таблица товаров -->
    <v-table density="compact" class="border rounded">
      <thead>
        <tr>
          <th class="text-left" style="width: 80px;">Фото</th>
          <th class="text-left">Категория</th>
          <th class="text-left">Вид</th>
          <th class="text-left">Наименование</th>
          <th class="text-left">Тип использования</th>
          <th class="text-left">Описание</th>
          <th class="text-left" style="width: 100px;">Количество</th>
          <th class="text-left" style="width: 120px;">Цена</th>
          <th class="text-left" style="width: 120px;">Сумма</th>
          <th class="text-left" style="width: 80px;">Действия</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(item, index) in selectedProducts" :key="item.product.id">
          <!-- Фото -->
          <td>
            <v-avatar v-if="item.product.photo_url" size="40">
              <v-img :src="item.product.photo_url" cover />
            </v-avatar>
            <v-avatar v-else color="grey-lighten-2" size="40">
              <v-icon icon="mdi-package-variant" color="grey-darken-1" />
            </v-avatar>
          </td>
          
          <!-- Категория -->
          <td>
            <v-chip v-if="item.product.category" size="x-small" color="info" variant="flat" density="compact">
              {{ item.product.category }}
            </v-chip>
            <span v-else class="text-caption text-medium-emphasis">—</span>
          </td>
          
          <!-- Вид -->
          <td>
            <span v-if="item.product.product_type">{{ item.product.product_type }}</span>
            <span v-else class="text-caption text-medium-emphasis">—</span>
          </td>
          
          <!-- Наименование -->
          <td>
            <div class="font-weight-medium">{{ item.product.name }}</div>
            <div v-if="item.product.clarification_link" class="mt-1">
              <v-btn
                :href="item.product.clarification_link"
                target="_blank"
                icon="mdi-link"
                variant="text"
                size="x-small"
                density="compact"
              />
            </div>
          </td>
          
          <!-- Тип использования -->
          <td>
            <v-chip
              v-if="item.product.is_reusable !== null"
              size="x-small"
              :color="item.product.is_reusable ? 'success' : 'warning'"
              variant="flat"
              density="compact"
            >
              {{ item.product.is_reusable ? 'Многоразовое' : 'Одноразовое' }}
            </v-chip>
            <span v-else class="text-caption text-medium-emphasis">—</span>
          </td>
          
          <!-- Описание -->
          <td>
            <div v-if="item.product.description" class="text-body-2 text-truncate" style="max-width: 200px;">
              {{ truncateText(item.product.description, 60) }}
            </div>
            <span v-else class="text-caption text-medium-emphasis">—</span>
          </td>
          
          <!-- Количество -->
          <td>
            <v-text-field
              v-model="item.quantity"
              type="number"
              variant="outlined"
              density="compact"
              hide-details
              min="1"
              style="max-width: 80px;"
              @input="updateProductQuantity(index, $event)"
            />
          </td>
          
          <!-- Цена -->
          <td>
            <v-text-field
              v-model="item.price"
              type="number"
              variant="outlined"
              density="compact"
              hide-details
              min="0"
              step="0.01"
              style="max-width: 100px;"
              @input="updateProductPrice(index, $event)"
            >
              <template v-slot:append>
                <span class="text-caption">₽</span>
              </template>
            </v-text-field>
          </td>
          
          <!-- Сумма -->
          <td class="font-weight-medium">
            {{ calculateProductTotal(item)?.toLocaleString() }} ₽
          </td>
          
          <!-- Действия -->
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
        
        <!-- Пустая таблица -->
        <tr v-if="selectedProducts.length === 0">
          <td colspan="10" class="text-center py-8 text-medium-emphasis">
            <v-icon icon="mdi-package-variant-closed" size="48" class="mb-2" />
            <div>Нет добавленных товаров</div>
            <v-btn
              color="primary"
              variant="text"
              size="small"
              class="mt-2"
              @click="$emit('add-product')"
            >
              Добавить первый товар
            </v-btn>
          </td>
        </tr>
      </tbody>
    </v-table>

    <!-- Итоговая сумма -->
    <div v-if="selectedProducts.length > 0" class="d-flex justify-end mt-4">
      <v-card variant="outlined" class="pa-4">
        <div class="d-flex align-center gap-4">
          <div class="text-right">
            <div class="text-caption text-medium-emphasis">Общая сумма</div>
            <div class="text-h5 font-weight-bold">
              {{ calculateTotal()?.toLocaleString() }} ₽
            </div>
          </div>
          <v-divider vertical />
          <div class="text-right">
            <div class="text-caption text-medium-emphasis">Количество товаров</div>
            <div class="text-h6">
              {{ selectedProducts.length }}
            </div>
          </div>
        </div>
      </v-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

interface Product {
  id: number
  name: string
  description?: string
  category?: string
  product_type?: string
  is_reusable?: boolean
  photo_url?: string
  photo_link?: string
  clarification_link?: string
  feo_category_id?: number
}

interface OrderProduct {
  product: Product
  quantity: number
  price: number
}

const props = defineProps<{
  modelValue: OrderProduct[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: OrderProduct[]]
  'add-product': []
}>()

const selectedProducts = ref<OrderProduct[]>(props.modelValue || [])

// Функция для обрезки текста
const truncateText = (text: string, maxLength: number) => {
  if (text.length <= maxLength) return text
  return text.substring(0, maxLength) + '...'
}

// Функция для склонения слов
const pluralize = (value: number, words: string[]) => {
  const cases = [2, 0, 1, 1, 1, 2]
  return words[(value % 100 > 4 && value % 100 < 20) ? 2 : cases[Math.min(value % 10, 5)]]
}

// Рассчитать сумму для одного товара
const calculateProductTotal = (item: OrderProduct) => {
  return item.quantity * item.price
}

// Обновить количество товара
const updateProductQuantity = (index: number, value: any) => {
  const quantity = parseInt(value) || 1
  selectedProducts.value[index].quantity = Math.max(1, quantity)
  emit('update:modelValue', selectedProducts.value)
}

// Обновить цену товара
const updateProductPrice = (index: number, value: any) => {
  const price = parseFloat(value) || 0
  selectedProducts.value[index].price = Math.max(0, price)
  emit('update:modelValue', selectedProducts.value)
}

// Удалить товар
const removeProduct = (index: number) => {
  selectedProducts.value.splice(index, 1)
  emit('update:modelValue', selectedProducts.value)
}

// Рассчитать общую сумму
const calculateTotal = () => {
  return selectedProducts.value.reduce((total, item) => {
    return total + (item.quantity * item.price)
  }, 0)
}

// Следим за изменением внешнего значения
watch(() => props.modelValue, (newValue) => {
  selectedProducts.value = newValue || []
})
</script>

<style scoped>
.border {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.gap-4 {
  gap: 16px;
}
.text-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>