<template>
  <div>
    <!-- Строка поиска с автодополнением -->
    <v-autocomplete
      v-model="selectedProductId"
      :items="searchResults"
      :loading="searchLoading"
      :search-input.sync="searchQuery"
      item-title="name"
      item-value="id"
      label="Поиск товара"
      placeholder="Начните вводить название, категорию или тип..."
      prepend-inner-icon="mdi-magnify"
      variant="outlined"
      clearable
      hide-no-data
      hide-selected
      class="mb-4"
      @update:search-input="onSearchInput"
      @update:model-value="onProductIdSelected"
    >
      <template v-slot:item="{ props, item }">
        <v-list-item v-bind="props" class="py-2">
          <template v-slot:prepend>
            <v-avatar v-if="productPhotoSrc(item.raw)" size="48" class="mr-3">
              <v-img :src="productPhotoSrc(item.raw)" cover />
            </v-avatar>
            <v-avatar v-else color="grey-lighten-2" size="48" class="mr-3">
              <v-icon icon="mdi-package-variant" color="grey-darken-1" />
            </v-avatar>
          </template>
          
          <v-list-item-title class="font-weight-medium">
            {{ item.raw.name }}
          </v-list-item-title>
          
          <v-list-item-subtitle class="d-flex flex-column mt-1">
            <div class="d-flex align-center gap-1 mb-1">
              <v-chip v-if="item.raw.category" size="x-small" color="info" variant="flat" density="compact">
                {{ item.raw.category }}
              </v-chip>
              <v-chip v-if="item.raw.product_type" size="x-small" variant="outlined" density="compact">
                {{ item.raw.product_type }}
              </v-chip>
              <v-chip 
                v-if="item.raw.is_reusable !== null"
                size="x-small"
                :color="item.raw.is_reusable ? 'success' : 'warning'"
                variant="flat"
                density="compact"
              >
                {{ item.raw.is_reusable ? 'Многоразовое' : 'Одноразовое' }}
              </v-chip>
            </div>
            
            <div v-if="item.raw.description" class="text-caption text-truncate" style="max-width: 400px;">
              {{ truncateText(item.raw.description, 80) }}
            </div>
          </v-list-item-subtitle>
          
          <template v-slot:append>
            <v-btn
              icon="mdi-plus"
              variant="text"
              size="small"
              color="primary"
              @click.stop="selectProduct(item.raw)"
            />
          </template>
        </v-list-item>
      </template>
      
      <template v-slot:append-item v-if="searchQuery && searchResults.length === 0 && !searchLoading">
        <v-list-item class="text-center text-medium-emphasis py-4">
          <v-icon icon="mdi-magnify-close" class="mr-2" />
          Товары не найдены
        </v-list-item>
      </template>
    </v-autocomplete>

    <!-- Быстрые фильтры -->
    <div v-if="allProducts.length > 0" class="mb-6">
      <div class="d-flex justify-space-between align-center mb-3">
        <span class="text-subtitle-2 font-weight-medium">Быстрый поиск</span>
        <span class="text-caption text-medium-emphasis">{{ allProducts.length }} товаров</span>
      </div>
      
      <!-- Категории -->
      <div class="mb-4">
        <div class="text-caption text-medium-emphasis mb-2">Категории</div>
        <div class="d-flex flex-wrap gap-2">
          <v-chip
            v-for="category in categories"
            :key="category"
            :color="selectedCategory === category ? 'primary' : 'default'"
            variant="outlined"
            size="small"
            @click="toggleCategory(category)"
          >
            {{ category }}
            <v-badge
              v-if="categoryCounts[category]"
              :content="categoryCounts[category]"
              inline
              class="ml-1"
            />
          </v-chip>
        </div>
      </div>
      
      <!-- Типы использования -->
      <div class="mb-4">
        <div class="text-caption text-medium-emphasis mb-2">Тип использования</div>
        <div class="d-flex flex-wrap gap-2">
          <v-chip
            v-for="type in usageTypes"
            :key="type.value"
            :color="selectedUsageType === type.value ? type.color : 'default'"
            variant="outlined"
            size="small"
            @click="toggleUsageType(type.value)"
          >
            {{ type.label }}
            <v-badge
              v-if="usageTypeCounts[type.value]"
              :content="usageTypeCounts[type.value]"
              inline
              class="ml-1"
            />
          </v-chip>
        </div>
      </div>
    </div>

    <!-- Список товаров с фильтрами -->
    <div v-if="filteredProducts.length > 0" class="mb-6">
      <div class="d-flex justify-space-between align-center mb-3">
        <span class="text-subtitle-2 font-weight-medium">
          {{ selectedCategory ? `Категория: ${selectedCategory}` : 'Все товары' }}
          {{ selectedUsageType !== null ? ` • ${selectedUsageType ? 'Многоразовые' : 'Одноразовые'}` : '' }}
        </span>
        <span class="text-caption text-medium-emphasis">{{ filteredProducts.length }} из {{ allProducts.length }}</span>
      </div>
      
      <v-list density="compact" class="border rounded">
        <v-list-item
          v-for="product in filteredProducts"
          :key="product.id"
          @click="selectProduct(product)"
          :class="{ 'bg-primary-lighten-5': selectedProduct?.id === product.id }"
          class="py-3"
        >
          <template v-slot:prepend>
            <v-avatar v-if="productPhotoSrc(product)" size="56" class="mr-4">
              <v-img :src="productPhotoSrc(product)" cover />
            </v-avatar>
            <v-avatar v-else color="grey-lighten-2" size="56" class="mr-4">
              <v-icon icon="mdi-package-variant" size="28" color="grey-darken-1" />
            </v-avatar>
          </template>
          
          <div class="flex-grow-1">
            <div class="d-flex justify-space-between align-start mb-1">
              <div>
                <h5 class="text-subtitle-1 font-weight-medium mb-1">{{ product.name }}</h5>
                <div class="d-flex align-center gap-2 mb-2">
                  <v-chip v-if="product.category" size="x-small" color="info" variant="flat" density="compact">
                    {{ product.category }}
                  </v-chip>
                  <v-chip v-if="product.product_type" size="x-small" variant="outlined" density="compact">
                    {{ product.product_type }}
                  </v-chip>
                  <v-chip 
                    v-if="product.is_reusable !== null"
                    size="x-small"
                    :color="product.is_reusable ? 'success' : 'warning'"
                    variant="flat"
                    density="compact"
                  >
                    {{ product.is_reusable ? 'Многоразовое' : 'Одноразовое' }}
                  </v-chip>
                </div>
              </div>
              <v-btn
                icon="mdi-plus"
                variant="text"
                size="small"
                color="primary"
                @click.stop="selectProduct(product)"
              />
            </div>
            
            <div v-if="product.description" class="text-body-2 text-medium-emphasis">
              {{ truncateText(product.description, 120) }}
            </div>
            
            <div v-if="product.clarification_link" class="mt-2">
              <v-btn
                :href="product.clarification_link"
                target="_blank"
                prepend-icon="mdi-link"
                variant="text"
                size="x-small"
                density="compact"
              >
                Уточняющая ссылка
              </v-btn>
            </div>
          </div>
        </v-list-item>
      </v-list>
    </div>

    <!-- Информация о выбранном товаре -->
    <v-card v-if="selectedProduct" variant="outlined" class="mt-6 pa-4">
      <div class="d-flex align-start">
        <v-avatar v-if="productPhotoSrc(selectedProduct)" size="80" class="mr-4">
          <v-img :src="productPhotoSrc(selectedProduct)" cover />
        </v-avatar>
        <v-avatar v-else color="primary-lighten-1" size="80" class="mr-4">
          <v-icon icon="mdi-package-variant" size="40" color="white" />
        </v-avatar>
        
        <div class="flex-grow-1">
          <div class="d-flex justify-space-between align-start mb-3">
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
            </div>
            <v-btn
              icon="mdi-close"
              variant="text"
              size="small"
              @click="clearSelection"
            />
          </div>
          
          <div v-if="selectedProduct.description" class="mb-4">
            <div class="text-caption text-medium-emphasis mb-1">Описание</div>
            <p class="text-body-2">{{ selectedProduct.description }}</p>
          </div>
          
          <div v-if="selectedProduct.clarification_link" class="mb-2">
            <v-btn
              :href="selectedProduct.clarification_link"
              target="_blank"
              prepend-icon="mdi-link"
              variant="outlined"
              size="small"
            >
              Уточняющая ссылка
            </v-btn>
          </div>
        </div>
      </div>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { debounce } from 'lodash-es'

interface Product {
  id: number
  name: string
  description?: string
  category?: string
  product_type?: string
  is_reusable?: boolean
  photo_url?: string
  photo_link?: string
  has_photo?: boolean
  clarification_link?: string
  feo_category_id?: number
}

// Phase 17.1-08: prefer DB bytea endpoint when a cached copy exists.
function productPhotoSrc(p: Pick<Product, 'id' | 'has_photo' | 'photo_url' | 'photo_link'> | null | undefined): string | undefined {
  if (!p) return undefined
  if (p.has_photo) return `/api/products/${p.id}/photo`
  return p.photo_url || p.photo_link || undefined
}

const props = defineProps<{
  modelValue?: Product | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Product | null]
}>()

const searchLoading = ref(false)
const searchQuery = ref('')
const allProducts = ref<Product[]>([])
const selectedProductId = ref<number | null>(props.modelValue?.id || null)
const selectedProduct = ref<Product | null>(props.modelValue || null)
const selectedCategory = ref<string | null>(null)
const selectedUsageType = ref<boolean | null>(null)

// Типы использования
const usageTypes = [
  { value: true, label: 'Многоразовые', color: 'success' },
  { value: false, label: 'Одноразовые', color: 'warning' }
]

// Загрузить все товары
const loadProducts = async () => {
  searchLoading.value = true
  try {
    const response = await fetch('/api/products/')
    if (response.ok) {
      allProducts.value = await response.json()
    }
  } catch (error) {
    console.error('Ошибка загрузки товаров:', error)
    // Демо-данные для тестирования
    allProducts.value = [
      {
        id: 1,
        name: 'Ноутбук Lenovo',
        description: 'Игровой ноутбук с процессором Intel Core i7, 16GB RAM, SSD 512GB',
        category: 'Компьютерная техника',
        product_type: 'Ноутбук',
        is_reusable: true,
        photo_url: 'https://example.com/laptop.jpg',
        clarification_link: 'https://example.com/specs'
      },
      {
        id: 2,
        name: 'Проектор Epson',
        description: 'Мультимедийный проектор Full HD, 3500 люмен',
        category: 'Офисное оборудование',
        product_type: 'Проектор',
        is_reusable: true,
        photo_url: 'https://example.com/projector.jpg'
      },
      {
        id: 3,
        name: 'Канцелярские наборы',
        description: 'Наборы для офиса: ручки, карандаши, блокноты',
        category: 'Канцелярия',
        product_type: 'Расходные материалы',
        is_reusable: false,
        photo_url: 'https://example.com/stationery.jpg'
      },
      {
        id: 4,
        name: 'Стулья офисные',
        description: 'Эргономичные офисные стулья с регулировкой высоты',
        category: 'Мебель',
        product_type: 'Стул',
        is_reusable: true,
        photo_url: 'https://example.com/chair.jpg'
      }
    ]
  } finally {
    searchLoading.value = false
  }
}

// Категории товаров
const categories = computed(() => {
  const cats = new Set<string>()
  allProducts.value.forEach(p => {
    if (p.category) cats.add(p.category)
  })
  return Array.from(cats).sort()
})

// Количество товаров по категориям
const categoryCounts = computed(() => {
  const counts: Record<string, number> = {}
  allProducts.value.forEach(p => {
    if (p.category) {
      counts[p.category] = (counts[p.category] || 0) + 1
    }
  })
  return counts
})

// Количество товаров по типу использования
const usageTypeCounts = computed(() => {
  const counts: Record<string, number> = {
    'true': 0,
    'false': 0
  }
  allProducts.value.forEach(p => {
    if (p.is_reusable === true) counts['true']++
    if (p.is_reusable === false) counts['false']++
  })
  return counts
})

// Результаты поиска
const searchResults = computed(() => {
  if (!searchQuery.value || searchQuery.value.length < 2) return []
  
  const query = searchQuery.value.toLowerCase()
  return allProducts.value.filter(p =>
    p.name.toLowerCase().includes(query) ||
    (p.description && p.description.toLowerCase().includes(query)) ||
    (p.category && p.category.toLowerCase().includes(query)) ||
    (p.product_type && p.product_type.toLowerCase().includes(query))
  )
})

// Отфильтрованные товары (с учетом категории и типа использования)
const filteredProducts = computed(() => {
  let result = allProducts.value
  
  if (selectedCategory.value) {
    result = result.filter(p => p.category === selectedCategory.value)
  }
  
  if (selectedUsageType.value !== null) {
    result = result.filter(p => p.is_reusable === selectedUsageType.value)
  }
  
  return result
})

// Функция для обрезки текста
const truncateText = (text: string, maxLength: number) => {
  if (text.length <= maxLength) return text
  return text.substring(0, maxLength) + '...'
}

// Debounced поиск
const debouncedSearch = debounce((query: string) => {
  if (query && query.length > 2) {
    // Здесь можно добавить запрос к API для поиска
    console.log('Searching for:', query)
  }
}, 300)

// Обработчики
const onSearchInput = (value: string | null) => {
  if (value) {
    debouncedSearch(value)
  }
}

const onProductIdSelected = (productId: number | null) => {
  if (!productId) {
    selectedProduct.value = null
    emit('update:modelValue', null)
    return
  }
  
  const product = allProducts.value.find(p => p.id === productId)
  if (product) {
    selectProduct(product)
  }
}

const toggleCategory = (category: string) => {
  selectedCategory.value = selectedCategory.value === category ? null : category
}

const toggleUsageType = (type: boolean) => {
  selectedUsageType.value = selectedUsageType.value === type ? null : type
}

const selectProduct = (product: Product) => {
  selectedProduct.value = product
  selectedProductId.value = product.id
  emit('update:modelValue', product)
  
  // Автоматически выбираем категорию товара
  if (product.category) {
    selectedCategory.value = product.category
  }
  
  // Автоматически выбираем тип использования
  if (product.is_reusable !== null) {
    selectedUsageType.value = product.is_reusable
  }
}

const clearSelection = () => {
  selectedProduct.value = null
  selectedProductId.value = null
  selectedCategory.value = null
  selectedUsageType.value = null
  emit('update:modelValue', null)
}

// Загружаем товары при монтировании
onMounted(() => {
  loadProducts()
})

// Следим за изменением внешнего значения
watch(() => props.modelValue, (newValue) => {
  selectedProduct.value = newValue || null
  selectedProductId.value = newValue?.id || null
})
</script>

<style scoped>
.border {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.gap-1 {
  gap: 4px;
}
.gap-2 {
  gap: 8px;
}
.bg-primary-lighten-5 {
  background-color: rgba(var(--v-theme-primary), 0.05);
}
</style>