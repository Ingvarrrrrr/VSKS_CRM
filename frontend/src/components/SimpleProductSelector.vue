<template>
  <div>
    <!-- Простой поиск товаров -->
    <v-autocomplete
      v-model="selectedProductId"
      :items="products"
      :loading="loading"
      :search-input.sync="search"
      item-title="name"
      item-value="id"
      label="Поиск товара"
      placeholder="Начните вводить название..."
      prepend-inner-icon="mdi-magnify"
      variant="outlined"
      clearable
      hide-no-data
      hide-selected
      class="mb-4"
      @update:model-value="onProductSelected"
    >
      <template v-slot:item="{ props, item }">
        <v-list-item v-bind="props">
          <v-list-item-title>{{ item.raw.name }}</v-list-item-title>
          <v-list-item-subtitle v-if="item.raw.category">
            {{ item.raw.category }}
          </v-list-item-subtitle>
        </v-list-item>
      </template>
    </v-autocomplete>

    <!-- Информация о выбранном товаре -->
    <v-card v-if="selectedProduct" variant="outlined" class="mt-4 pa-4">
      <div class="d-flex justify-space-between align-start">
        <div>
          <h4 class="text-h6">{{ selectedProduct.name }}</h4>
          <div class="d-flex gap-2 mt-2">
            <v-chip v-if="selectedProduct.category" size="small" color="info" variant="flat">
              {{ selectedProduct.category }}
            </v-chip>
            <v-chip v-if="selectedProduct.product_type" size="small" variant="outlined">
              {{ selectedProduct.product_type }}
            </v-chip>
          </div>
        </div>
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          @click="clearSelection"
        />
      </div>
      
      <div v-if="selectedProduct.description" class="mt-3">
        <p class="text-body-2">{{ selectedProduct.description }}</p>
      </div>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

interface Product {
  id: number
  name: string
  description?: string
  category?: string
  product_type?: string
  is_reusable?: boolean
}

const props = defineProps<{
  modelValue?: Product | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Product | null]
}>()

const loading = ref(false)
const search = ref('')
const allProducts = ref<Product[]>([])
const selectedProductId = ref<number | null>(props.modelValue?.id || null)
const selectedProduct = ref<Product | null>(props.modelValue || null)

// Загрузить все товары
const loadProducts = async () => {
  loading.value = true
  try {
    const response = await fetch('/api/products/')
    if (response.ok) {
      allProducts.value = await response.json()
    } else {
      console.error('Ошибка загрузки товаров:', response.status)
    }
  } catch (error) {
    console.error('Ошибка загрузки товаров:', error)
    // Демо-данные для тестирования
    allProducts.value = [
      {
        id: 1,
        name: 'Ноутбук Lenovo',
        description: 'Игровой ноутбук',
        category: 'Компьютерная техника',
        product_type: 'Ноутбук',
        is_reusable: true
      },
      {
        id: 2,
        name: 'Проектор Epson',
        description: 'Мультимедийный проектор',
        category: 'Офисное оборудование',
        product_type: 'Проектор',
        is_reusable: true
      }
    ]
  } finally {
    loading.value = false
  }
}

// Отфильтрованные товары для поиска
const products = computed(() => {
  if (!search.value) return allProducts.value.slice(0, 20) // Показываем первые 20
  
  const query = search.value.toLowerCase()
  return allProducts.value.filter(p =>
    p.name.toLowerCase().includes(query) ||
    (p.description && p.description.toLowerCase().includes(query)) ||
    (p.category && p.category.toLowerCase().includes(query))
  ).slice(0, 20) // Ограничиваем 20 результатами
})

// Обработчик выбора товара
const onProductSelected = (productId: number | null) => {
  if (!productId) {
    selectedProduct.value = null
    emit('update:modelValue', null)
    return
  }
  
  const product = allProducts.value.find(p => p.id === productId)
  if (product) {
    selectedProduct.value = product
    emit('update:modelValue', product)
  }
}

const clearSelection = () => {
  selectedProduct.value = null
  selectedProductId.value = null
  emit('update:modelValue', null)
}

// Загружаем товары при монтировании
onMounted(() => {
  loadProducts()
})

// Следим за изменением внешнего значения
import { watch } from 'vue'
watch(() => props.modelValue, (newValue) => {
  selectedProduct.value = newValue || null
  selectedProductId.value = newValue?.id || null
})
</script>