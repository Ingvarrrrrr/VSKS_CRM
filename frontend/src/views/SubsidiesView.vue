<template>
  <v-container>
    <v-row>
      <v-col cols="12">
        <v-card class="pa-6">
          <v-card-title class="text-h4 mb-6">
            <v-icon icon="mdi-cash-multiple" class="mr-4" />Субсидии
          </v-card-title>
          
          <div class="d-flex justify-space-between align-center mb-6">
            <v-card-subtitle class="text-h6">
              Управление субсидиями и распределение бюджета
            </v-card-subtitle>
            <v-btn color="primary" prepend-icon="mdi-plus">
              Добавить субсидию
            </v-btn>
          </div>
          
          <v-table>
            <thead>
              <tr>
                <th>Название</th>
                <th>Год</th>
                <th>Бюджет</th>
                <th>Использовано</th>
                <th>Остаток</th>
                <th>Статус</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="subsidy in subsidies" :key="subsidy.id">
                <td>{{ subsidy.name }}</td>
                <td>{{ subsidy.year }}</td>
                <td>{{ subsidy.budget.toLocaleString() }} ₽</td>
                <td>{{ subsidy.used.toLocaleString() }} ₽</td>
                <td :class="subsidy.remaining < 0 ? 'text-error' : ''">
                  {{ subsidy.remaining.toLocaleString() }} ₽
                </td>
                <td>
                  <v-chip :color="subsidy.statusColor" size="small">
                    {{ subsidy.status }}
                  </v-chip>
                </td>
                <td>
                  <v-btn
                    icon="mdi-pencil"
                    variant="text"
                    size="small"
                    class="mr-2"
                  />
                  <v-btn
                    icon="mdi-eye"
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
          
          <v-divider class="my-8" />
          
          <v-row>
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="pa-4">
                <v-card-title class="text-h6 mb-4">
                  Категории ФЭО (Патриотика 2025)
                </v-card-title>
                <v-treeview
                  :items="feoTree"
                  item-children="children"
                  item-title="name"
                  open-all
                >
                  <template v-slot:prepend="{ item }">
                    <v-icon v-if="item.level === 1" icon="mdi-folder" color="primary" />
                    <v-icon v-if="item.level === 2" icon="mdi-folder-open" color="info" />
                    <v-icon v-if="item.level === 3" icon="mdi-file-document" color="success" />
                  </template>
                  <template v-slot:append="{ item }">
                    <span v-if="item.appendix" class="text-caption text-medium-emphasis">
                      {{ item.appendix }}
                    </span>
                  </template>
                </v-treeview>
              </v-card>
            </v-col>
            
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="pa-4">
                <v-card-title class="text-h6 mb-4">
                  Перераспределение бюджета
                </v-card-title>
                <v-form>
                  <v-select
                    label="Направление расходов"
                    :items="feoDirections"
                    variant="outlined"
                    class="mb-4"
                  />
                  
                  <v-text-field
                    label="Новая сумма, ₽"
                    variant="outlined"
                    type="number"
                    class="mb-4"
                  />
                  
                  <v-textarea
                    label="Обоснование"
                    variant="outlined"
                    rows="3"
                    class="mb-6"
                  />
                  
                  <v-btn color="primary" block>
                    Сохранить изменения
                  </v-btn>
                </v-form>
              </v-card>
            </v-col>
          </v-row>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const subsidies = ref([
  {
    id: 1,
    name: 'Патриотика 2025',
    year: 2025,
    budget: 26128070,
    used: 15840200,
    remaining: 10287870,
    status: 'Активна',
    statusColor: 'success'
  },
  {
    id: 2,
    name: 'Минпрос 2024',
    year: 2024,
    budget: 15000000,
    used: 15000000,
    remaining: 0,
    status: 'Завершена',
    statusColor: 'info'
  },
  {
    id: 3,
    name: 'ФАДМ 2025',
    year: 2025,
    budget: 8000000,
    used: 3200000,
    remaining: 4800000,
    status: 'Активна',
    statusColor: 'success'
  },
])

const feoTree = ref([
  {
    id: 1,
    name: 'Техническое оснащение деятельности штаба',
    level: 1,
    appendix: null,
    children: [
      {
        id: 5,
        name: 'Техническое оснащение деятельности штаба',
        level: 2,
        appendix: 'Прил. 2',
        children: [
          { id: 6, name: 'Компьютерная техника', level: 3, appendix: null },
          { id: 7, name: 'Офисное оборудование', level: 3, appendix: null },
          { id: 8, name: 'Программное обеспечение', level: 3, appendix: null },
        ]
      }
    ]
  },
  {
    id: 2,
    name: 'Организация мероприятий',
    level: 1,
    appendix: null,
    children: [
      {
        id: 9,
        name: 'Слёт студентов-спасателей',
        level: 2,
        appendix: 'Прил. 3',
        children: []
      }
    ]
  },
])

const feoDirections = ref([
  'Техническое оснащение деятельности штаба',
  'Организация мероприятий',
  'Поддержка работы интернет-ресурса организации',
  'Оказание услуг по транспортировке и проживанию',
])
</script>