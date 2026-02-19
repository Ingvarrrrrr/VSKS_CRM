<template>
  <v-container>
    <v-row>
      <v-col cols="12">
        <v-card class="pa-6">
          <v-card-title class="text-h4 mb-6">
            <v-icon icon="mdi-account-group" class="mr-4" />Контрагенты
          </v-card-title>
          
          <div class="d-flex justify-space-between align-center mb-6">
            <v-card-subtitle class="text-h6">
              Управление поставщиками и подрядчиками
            </v-card-subtitle>
            <div>
              <v-btn color="primary" prepend-icon="mdi-plus" class="mr-4">
                Добавить контрагента
              </v-btn>
              <v-btn variant="outlined" prepend-icon="mdi-file-import">
                Импорт из файла
              </v-btn>
            </div>
          </div>
          
          <v-table>
            <thead>
              <tr>
                <th>Наименование</th>
                <th>ИНН</th>
                <th>КПП</th>
                <th>Адрес</th>
                <th>Контакты</th>
                <th>Договоров</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="contractor in contractors" :key="contractor.id">
                <td>{{ contractor.name }}</td>
                <td>{{ contractor.inn }}</td>
                <td>{{ contractor.kpp }}</td>
                <td>{{ contractor.address }}</td>
                <td>
                  <div>{{ contractor.phone }}</div>
                  <div class="text-caption">{{ contractor.email }}</div>
                </td>
                <td>{{ contractor.contractsCount }}</td>
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
                    icon="mdi-file-document"
                    variant="text"
                    size="small"
                    class="mr-2"
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
                  Добавить контрагента
                </v-card-title>
                <v-form>
                  <v-text-field
                    label="Наименование организации"
                    variant="outlined"
                    class="mb-4"
                  />
                  
                  <v-row>
                    <v-col cols="6">
                      <v-text-field
                        label="ИНН"
                        variant="outlined"
                        class="mb-4"
                      />
                    </v-col>
                    <v-col cols="6">
                      <v-text-field
                        label="КПП"
                        variant="outlined"
                        class="mb-4"
                      />
                    </v-col>
                  </v-row>
                  
                  <v-textarea
                    label="Адрес"
                    variant="outlined"
                    rows="2"
                    class="mb-4"
                  />
                  
                  <v-text-field
                    label="Телефон"
                    variant="outlined"
                    class="mb-4"
                  />
                  
                  <v-text-field
                    label="Email"
                    variant="outlined"
                    class="mb-6"
                  />
                  
                  <v-btn color="primary" block>
                    Сохранить
                  </v-btn>
                </v-form>
              </v-card>
            </v-col>
            
            <v-col cols="12" md="6">
              <v-card variant="outlined" class="pa-4">
                <v-card-title class="text-h6 mb-4">
                  Импорт из файла
                </v-card-title>
                <v-file-input
                  label="Выберите файл"
                  variant="outlined"
                  accept=".xlsx,.xls,.csv"
                  class="mb-4"
                />
                
                <v-alert type="info" variant="tonal" class="mb-6">
                  Поддерживаемые форматы: Excel (.xlsx, .xls), CSV.
                  Файл должен содержать столбцы: Наименование, ИНН, КПП, Адрес.
                </v-alert>
                
                <v-btn color="primary" block>
                  Загрузить и обработать
                </v-btn>
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

const contractors = ref([
  {
    id: 1,
    name: 'ООО "Техноторг"',
    inn: '7712345678',
    kpp: '771201001',
    address: 'г. Москва, ул. Ленина, д. 1',
    phone: '+7 (495) 123-45-67',
    email: 'info@tehnotorg.ru',
    contractsCount: 12
  },
  {
    id: 2,
    name: 'ИП Сидоров Петр Иванович',
    inn: '7723456789',
    kpp: '-',
    address: 'г. Москва, пр-т Мира, д. 25',
    phone: '+7 (916) 234-56-78',
    email: 'sidorov@mail.ru',
    contractsCount: 8
  },
  {
    id: 3,
    name: 'ООО "Веб-сервис"',
    inn: '7734567890',
    kpp: '773401001',
    address: 'г. Москва, ул. Тверская, д. 15',
    phone: '+7 (495) 345-67-89',
    email: 'support@webservice.ru',
    contractsCount: 5
  },
  {
    id: 4,
    name: 'ООО "Трансавто"',
    inn: '7745678901',
    kpp: '774501001',
    address: 'г. Москва, ш. Энтузиастов, д. 45',
    phone: '+7 (495) 456-78-90',
    email: 'transport@transauto.ru',
    contractsCount: 7
  },
])
</script>