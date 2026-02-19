<template>
  <v-container>
    <v-row>
      <v-col cols="12">
        <v-card class="pa-6">
          <v-card-title class="text-h4 mb-6">
            <v-icon icon="mdi-folder-tree" class="mr-4" />Категории ФЭО
          </v-card-title>
          
          <div class="d-flex justify-space-between align-center mb-6">
            <v-card-subtitle class="text-h6">
              Управление категориями федеральных целевых программ
            </v-card-subtitle>
            <div>
              <v-btn color="primary" prepend-icon="mdi-plus" class="mr-4">
                Добавить категорию
              </v-btn>
              <v-btn variant="outlined" prepend-icon="mdi-file-import">
                Импорт
              </v-btn>
            </div>
          </div>
          
          <v-table>
            <thead>
              <tr>
                <th>Код</th>
                <th>Наименование</th>
                <th>Уровень</th>
                <th>Описание</th>
                <th>Бюджет</th>
                <th>Товаров</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="category in categories" :key="category.id">
                <td>
                  <v-chip size="small" color="primary" variant="flat">
                    {{ category.code }}
                  </v-chip>
                </td>
                <td class="font-weight-medium">{{ category.name }}</td>
                <td>
                  <v-chip size="small" :color="getLevelColor(category.level)" variant="flat">
                    Уровень {{ category.level }}
                  </v-chip>
                </td>
                <td>{{ category.description }}</td>
                <td class="font-weight-medium">{{ category.budget?.toLocaleString() }} ₽</td>
                <td>{{ category.productsCount }}</td>
                <td>
                  <v-btn
                    icon="mdi-eye"
                    variant="text"
                    size="small"
                    class="mr-2"
                  />
                  <v-btn
                    icon="mdi-pencil"
                    variant="text"
                    size="small"
                    class="mr-2"
                  />
                  <v-btn
                    icon="mdi-delete"
                    variant="text"
                    size="small"
                    color="error"
                  />
                </td>
              </tr>
            </tbody>
          </v-table>
          
          <!-- Пустая таблица -->
          <div v-if="categories.length === 0" class="text-center py-12">
            <v-icon icon="mdi-folder-outline" size="64" class="mb-4" color="grey-lighten-1" />
            <h3 class="text-h5 mb-2">Категории ФЭО не настроены</h3>
            <p class="text-body-1 text-medium-emphasis mb-6">
              Настройте категории федеральных целевых программ для работы с заказами
            </p>
            <v-btn color="primary" prepend-icon="mdi-plus">
              Добавить первую категорию
            </v-btn>
          </div>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'

// Демо-данные категорий ФЭО
const categories = ref([
  {
    id: 1,
    code: 'ФЭО-001',
    name: 'Основные средства',
    level: 1,
    description: 'Приобретение основных средств',
    budget: 5000000,
    productsCount: 45
  },
  {
    id: 2,
    code: 'ФЭО-002',
    name: 'Материальные запасы',
    level: 1,
    description: 'Закупка материальных запасов',
    budget: 3000000,
    productsCount: 120
  },
  {
    id: 3,
    code: 'ФЭО-003',
    name: 'Услуги',
    level: 1,
    description: 'Оплата услуг подрядчиков',
    budget: 2000000,
    productsCount: 25
  },
  {
    id: 4,
    code: 'ФЭО-004',
    name: 'Капитальные вложения',
    level: 1,
    description: 'Капитальные инвестиции',
    budget: 10000000,
    productsCount: 15
  },
  {
    id: 5,
    code: 'ФЭО-001-01',
    name: 'Офисная техника',
    level: 2,
    description: 'Компьютеры, принтеры, оргтехника',
    budget: 1500000,
    productsCount: 30
  },
  {
    id: 6,
    code: 'ФЭО-001-02',
    name: 'Мебель',
    level: 2,
    description: 'Офисная мебель и оборудование',
    budget: 1000000,
    productsCount: 15
  }
])

// Функция для получения цвета по уровню
const getLevelColor = (level: number) => {
  const colors = ['primary', 'secondary', 'success', 'warning', 'error']
  return colors[level - 1] || 'grey'
}
</script>