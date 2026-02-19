<template>
  <div>
    <!-- Поиск товара с автодополнением -->
    <v-autocomplete
      v-model="selectedProductId"
      :items="filteredProducts"
      :loading="loading"
      :search-input.sync="searchQuery"
      item-title="name"
      item-value="id"
      label="Поиск товара"
      placeholder="Начните вводить название товара..."
      prepend-inner-icon="mdi-magnify"
      variant="outlined"
      clearable
      hide-no-data
      hide-selected
      class="mb-4"
      auto-select-first
      @update:search="onSearch"
      @update:model-value="onProductSelected"
    >
      <template v-slot:item="{ props, item }">
        <v-list-item v-bind="props">
          <template v-slot:prepend>
            <v-avatar v-if="item.raw.photo_url" size="60" class="mr-2">
              <v-img :src="item.raw.photo_url" cover />
            </v-avatar>
            <v-avatar v-else color="grey-lighten-2" size="60" class="mr-2">
              <v-icon icon="mdi-package-variant" color="grey-darken-1" />
            </v-avatar>
          </template>
          
          <v-list-item-title class="font-weight-medium">
            {{ item.raw.name }}
          </v-list-item-title>
          <v-list-item-subtitle class="mt-1">
            <div class="d-flex flex-wrap gap-1">
              <v-chip v-if="item.raw.category" size="x-small" color="info" variant="flat">
                {{ item.raw.category }}
              </v-chip>
              <v-chip v-if="item.raw.product_type" size="x-small" variant="outlined">
                {{ item.raw.product_type }}
              </v-chip>
              <v-chip 
                v-if="item.raw.is_reusable !== null"
                size="x-small"
                :color="item.raw.is_reusable ? 'success' : 'warning'"
                variant="flat"
              >
                {{ item.raw.is_reusable ? 'Многоразовое' : 'Одноразовое' }}
              </v-chip>
            </div>
            <div v-if="item.raw.description" class="mt-1 text-caption text-truncate" style="max-width: 400px;">
              {{ truncateText(item.raw.description, 80) }}
            </div>
          </v-list-item-subtitle>
        </v-list-item>
      </template>
      
      <template v-slot:append-item>
        <v-list-item v-if="hasMoreProducts && !loading">
          <v-list-item-title class="text-center text-caption text-medium-emphasis">
            Показано {{ filteredProducts.length }} из {{ allProducts.length }} товаров
          </v-list-item-title>
        </v-list-item>
      </template>
    </v-autocomplete>

    <!-- Детали выбранного товара -->
    <v-card v-if="selectedProduct" variant="outlined" class="mt-4 pa-4">
      <div class="d-flex justify-space-between align-start">
        <div class="d-flex gap-4">
          <!-- Фото товара -->
          <v-avatar v-if="selectedProduct.photo_url" size="150" rounded="lg">
            <v-img :src="selectedProduct.photo_url" cover />
          </v-avatar>
          <v-avatar v-else color="grey-lighten-2" size="150" rounded="lg">
            <v-icon icon="mdi-package-variant" size="60" color="grey-darken-1" />
          </v-avatar>
          
          <!-- Основная информация -->
          <div>
            <h4 class="text-h6 mb-2">{{ selectedProduct.name }}</h4>
            <div class="d-flex flex-wrap gap-2 mb-3">
              <v-chip v-if="selectedProduct.category" size="small" color="info" variant="flat">
                {{ selectedProduct.category }}
              </v-chip>
              <v-chip v-if="selectedProduct.product_type" size="small" variant="outlined">
                {{ selectedProduct.product_type }}
              </v-chip>
              <v-chip 
                v-if="selectedProduct.is_reusable !== null"
                size="small"
                :color="selectedProduct.is_reusable ? 'success' : 'warning'"
                variant="flat"
              >
                {{ selectedProduct.is_reusable ? 'Многоразовое' : 'Одноразовое' }}
              </v-chip>
            </div>
            
            <!-- Дополнительная информация -->
            <div class="text-body-2">
              <div v-if="selectedProduct.clarification_link && selectedProduct.clarification_link !== '#REF!'">
                <v-icon icon="mdi-link" size="small" class="mr-1" />
                <a :href="selectedProduct.clarification_link" target="_blank" class="text-info">
                  Ссылка на документацию
                </a>
              </div>
            </div>
          </div>
        </div>
        
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          @click="clearSelection"
        />
      </div>
      
      <!-- Описание товара -->
      <div v-if="selectedProduct.description" class="mt-4">
        <v-expansion-panels variant="accordion">
          <v-expansion-panel>
            <v-expansion-panel-title class="text-subtitle-2">
              <v-icon icon="mdi-text" class="mr-2" />Описание товара
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <div class="text-body-2 pre-formatted">
                {{ selectedProduct.description }}
              </div>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </div>
      
      <!-- Поля для ввода количества и цены -->
      <v-row class="mt-4">
        <v-col cols="12" md="3">
          <v-text-field
            v-model="quantity"
            label="Количество"
            type="number"
            variant="outlined"
            density="compact"
            min="1"
            hide-details
          >
            <template v-slot:append>
              <span class="text-caption">шт.</span>
            </template>
          </v-text-field>
        </v-col>
        
        <v-col cols="12" md="3">
          <v-text-field
            v-model="price"
            label="Цена за единицу"
            type="number"
            variant="outlined"
            density="compact"
            min="0"
            step="0.01"
            hide-details
          >
            <template v-slot:append>
              <span class="text-caption">₽</span>
            </template>
          </v-text-field>
        </v-col>
        
        <v-col cols="12" md="3">
          <v-text-field
            v-model="unitsPerPackage"
            label="Штук в упаковке"
            type="number"
            variant="outlined"
            density="compact"
            min="1"
            hide-details
          >
            <template v-slot:append>
              <span class="text-caption">шт./уп.</span>
            </template>
          </v-text-field>
        </v-col>
        
        <v-col cols="12" md="3">
          <v-text-field
            v-model="unitOfMeasure"
            label="Единица измерения"
            variant="outlined"
            density="compact"
            hide-details
            placeholder="шт., кг, м и т.д."
          />
        </v-col>
      </v-row>
      
      <!-- Итоговая сумма -->
      <div class="d-flex justify-end mt-4">
        <v-card variant="tonal" class="pa-3">
          <div class="text-right">
            <div class="text-caption text-medium-emphasis">Итого за товар</div>
            <div class="text-h6 font-weight-bold">
              {{ formatCurrency(productTotal) }}
            </div>
            <div class="text-caption">
              {{ quantity }} × {{ formatCurrency(price) }}
            </div>
          </div>
        </v-card>
      </div>
    </v-card>
    
    <!-- Быстрый поиск по категориям -->
    <div v-if="showQuickFilters" class="mt-4">
      <div class="text-caption text-medium-emphasis mb-2">Быстрый поиск:</div>
      <div class="d-flex flex-wrap gap-1">
        <v-chip
          v-for="category in uniqueCategories"
          :key="category"
          size="small"
          :color="activeCategory === category ? 'primary' : 'default'"
          variant="flat"
          @click="filterByCategory(category)"
        >
          {{ category }}
        </v-chip>
        <v-chip
          v-if="activeCategory"
          size="small"
          color="error"
          variant="flat"
          @click="clearCategoryFilter"
          prepend-icon="mdi-close"
        >
          Сбросить фильтр
        </v-chip>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'

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

const props = defineProps<{
  modelValue?: Product | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Product | null]
  'product-selected': [value: { product: Product, quantity: number, price: number, unitsPerPackage: number, unitOfMeasure: string }]
}>()

const loading = ref(false)
const searchQuery = ref('')
const allProducts = ref<Product[]>([])
const selectedProductId = ref<number | null>(props.modelValue?.id || null)
const selectedProduct = ref<Product | null>(props.modelValue || null)
const quantity = ref(1)
const price = ref(0)
const unitsPerPackage = ref(1)
const unitOfMeasure = ref('шт.')
const activeCategory = ref<string | null>(null)
const showQuickFilters = ref(true)

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
  } finally {
    loading.value = false
  }
}

// Фильтрованные товары
const filteredProducts = computed(() => {
  let products = allProducts.value
  
  // Фильтр по поисковому запросу
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    products = products.filter(product => 
      product.name.toLowerCase().includes(query) ||
      (product.description && product.description.toLowerCase().includes(query)) ||
      (product.category && product.category.toLowerCase().includes(query)) ||
      (product.product_type && product.product_type.toLowerCase().includes(query))
    )
  }
  
  // Фильтр по категории
  if (activeCategory.value) {
    products = products.filter(product => product.category === activeCategory.value)
  }
  
  return products.slice(0, 50) // Ограничиваем количество для производительности
})

// Уникальные категории для быстрого поиска
const uniqueCategories = computed(() => {
  const categories = new Set<string>()
  allProducts.value.forEach(product => {
    if (product.category) {
      categories.add(product.category)
    }
  })
  return Array.from(categories).slice(0, 10) // Показываем только первые 10 категорий
})

const hasMoreProducts = computed(() => {
  return filteredProducts.value.length < allProducts.value.length
})

// Общая сумма за товар
const productTotal = computed(() => {
  return quantity.value * price.value
})

// Форматирование валюты
const formatCurrency = (amount: number) => {
  return amount.toLocaleString() + ' ₽'
}

// Обрезка текста
const truncateText = (text: string, maxLength: number) => {
  if (text.length <= maxLength) return text
  return text.substring(0, maxLength) + '...'
}

// Обработчик поиска
const onSearch = (value: string) => {
  searchQuery.value = value
}

// Обработчик выбора товара
const onProductSelected = (productId: number | null) => {
  if (!productId) {
    selectedProduct.value = null
    return
  }
  
  const product = allProducts.value.find(p => p.id === productId)
  if (product) {
    selectedProduct.value = product
    // Можно установить стандартную цену на основе категории или другого критерия
    price.value = getDefaultPrice(product)
    unitsPerPackage.value = getDefaultUnitsPerPackage(product)
    unitOfMeasure.value = getDefaultUnitOfMeasure(product)
    
    // Эмитируем событие
    emit('update:modelValue', product)
    emitProductSelected()
  }
}

// Очистить выбор
const clearSelection = () => {
  selectedProduct.value = null
  selectedProductId.value = null
  emit('update:modelValue', null)
}

// Фильтр по категории
const filterByCategory = (category: string) => {
  activeCategory.value = category
  searchQuery.value = ''
}

// Очистить фильтр категории
const clearCategoryFilter = () => {
  activeCategory.value = null
}

// Эмитировать событие выбора товара
const emitProductSelected = () => {
  if (selectedProduct.value) {
    emit('product-selected', {
      product: selectedProduct.value,
      quantity: quantity.value,
      price: price.value,
      unitsPerPackage: unitsPerPackage.value,
      unitOfMeasure: unitOfMeasure.value
    })
  }
}

// Вспомогательные функции для установки значений по умолчанию
const getDefaultPrice = (product: Product): number => {
  // Здесь можно реализовать логику определения цены
  // Например, на основе категории или типа товара
  if (product.category?.includes('электро')) return 15000
  if (product.category?.includes('строитель')) return 8000
  if (product.category?.includes('канцеляр')) return 500
  return 1000
}

const getDefaultUnitsPerPackage = (product: Product): number => {
  if (product.is_reusable) return 1
  if (product.category?.includes('канцеляр')) return 10
  if (product.category?.includes('расход')) return 5
  return 1
}

const getDefaultUnitOfMeasure = (product: Product): string => {
  if (product.category?.includes('жидкость')) return 'л'
  if (product.category?.includes('сыпучий')) return 'кг'
  if (product.category?.includes('ткань')) return 'м'
  return 'шт.'
}

// Следим за изменениями количества и цены
watch(quantity, () => {
  emitProductSelected()
})

watch(price, () => {
  emitProductSelected()
})

watch(unitsPerPackage, () => {
  emitProductSelected()
})

watch(unitOfMeasure, () => {
  emitProductSelected()
})

// Загрузка данных при монтировании
onMounted(() => {
  loadProducts()
})
</script>

<style scoped>
.pre-formatted {
  white-space: pre-wrap;
  word-break: break-word;
}
.gap-1 {
  gap: 4px;
}
.gap-2 {
  gap: 8px;
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