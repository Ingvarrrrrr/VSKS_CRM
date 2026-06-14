<template>
  <v-dialog :model-value="modelValue" max-width="800" :fullscreen="mobile" @update:model-value="$emit('update:modelValue', $event)">
    <v-card>
      <v-card-title class="d-flex justify-space-between align-center">
        <span class="text-h6">
          <v-icon icon="mdi-plus-box" class="mr-2" />
          Добавить новый товар
        </span>
        <v-btn icon="mdi-close" variant="text" @click="$emit('update:modelValue', false)" />
      </v-card-title>
      
      <v-card-text>
        <v-alert type="info" variant="tonal" class="mb-4">
          <div class="text-caption">
            <v-icon icon="mdi-information" size="small" class="mr-1" />
            Товар будет добавлен во временный каталог и потребует утверждения администратором.
            После утверждения товар появится в общем списке.
          </div>
        </v-alert>
        
        <v-form @submit.prevent="addProduct">
          <v-row>
            <v-col cols="12">
              <v-text-field
                v-model="product.name"
                label="Название товара *"
                variant="outlined"
                :rules="[v => !!v || 'Обязательное поле']"
                required
              />
            </v-col>
            
            <v-col cols="12">
              <v-textarea
                v-model="product.description"
                label="Описание товара"
                variant="outlined"
                rows="3"
                counter
                maxlength="500"
                :rules="[v => !v || v.length <= 500 || 'Максимум 500 символов']"
              />
            </v-col>
            
            <v-col cols="12" md="6">
              <v-select
                v-model="product.category"
                :items="categories"
                label="Категория ФЭО *"
                variant="outlined"
                :rules="[v => !!v || 'Обязательное поле']"
                required
              />
            </v-col>
            
            <v-col cols="12" md="6">
              <v-text-field
                v-model="product.productType"
                label="Тип товара (например, оборудование, материалы)"
                variant="outlined"
              />
            </v-col>
            
            <v-col cols="12" md="6">
              <v-text-field
                v-model="product.photoUrl"
                label="Ссылка на фото товара"
                variant="outlined"
                placeholder="https://example.com/photo.jpg"
                prepend-icon="mdi-link"
              />
            </v-col>
            
            <v-col cols="12" md="6">
              <v-text-field
                v-model="product.unitOfMeasure"
                label="Единица измерения (шт., кг, м и т.д.)"
                variant="outlined"
                placeholder="шт."
              />
            </v-col>
            
            <v-col cols="12" md="6">
              <v-text-field
                v-model="product.unitsPerPackage"
                label="Количество в упаковке"
                variant="outlined"
                type="number"
                min="1"
              />
            </v-col>
            
            <v-col cols="12" md="6">
              <v-text-field
                v-model="product.estimatedPrice"
                label="Примерная цена за единицу, ₽"
                variant="outlined"
                type="number"
                min="0"
                step="0.01"
              />
            </v-col>
            
            <v-col cols="12">
              <v-switch
                v-model="product.isReusable"
                label="Многоразовый товар (можно использовать повторно)"
                color="primary"
              />
            </v-col>
            
            <v-col cols="12">
              <v-textarea
                v-model="product.notes"
                label="Примечания для администратора (почему нужен этот товар)"
                variant="outlined"
                rows="2"
                placeholder="Опишите, для каких задач нужен этот товар, если его нет в текущем ФЭО"
              />
            </v-col>
          </v-row>
        </v-form>
      </v-card-text>
      
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="$emit('update:modelValue', false)">
          Отмена
        </v-btn>
        <v-btn 
          color="primary" 
          @click="addProduct"
          :loading="adding"
          :disabled="!isValid"
        >
          Отправить на утверждение
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useDisplay } from 'vuetify'

const { mobile } = useDisplay()

interface Props {
  modelValue: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'product-added': [product: any]
}>()

const adding = ref(false)

const product = ref({
  name: '',
  description: '',
  category: '',
  productType: '',
  photoUrl: '',
  unitOfMeasure: 'шт.',
  unitsPerPackage: 1,
  estimatedPrice: 0,
  isReusable: false,
  notes: ''
})

const categories = [
  'Техническое оснащение',
  'Мероприятия',
  'Транспортные расходы',
  'Канцелярия',
  'Образовательные материалы',
  'Оборудование',
  'Программное обеспечение',
  'Услуги'
]

const isValid = computed(() => {
  return product.value.name.trim() !== '' && product.value.category !== ''
})

async function addProduct() {
  adding.value = true
  try {
    // Имитация API-запроса
    await new Promise(resolve => setTimeout(resolve, 1000))
    
    const newProduct = {
      id: Date.now(), // Временный ID
      ...product.value,
      is_approved_by_admin: false,
      created_at: new Date().toISOString()
    }
    
    emit('product-added', newProduct)
    emit('update:modelValue', false)
    
    // Сброс формы
    product.value = {
      name: '',
      description: '',
      category: '',
      productType: '',
      photoUrl: '',
      unitOfMeasure: 'шт.',
      unitsPerPackage: 1,
      estimatedPrice: 0,
      isReusable: false,
      notes: ''
    }
    
  } catch (error) {
    console.error('Ошибка добавления товара:', error)
  } finally {
    adding.value = false
  }
}
</script>