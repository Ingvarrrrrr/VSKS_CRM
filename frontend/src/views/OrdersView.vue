<template>
  <v-container>
    <v-row>
      <v-col cols="12">
        <v-card class="pa-6">
          <v-card-title class="text-h4 mb-6">
            <v-icon icon="mdi-clipboard-list" class="mr-4" />Заказы
          </v-card-title>
          
          <div class="d-flex justify-space-between align-center mb-6">
            <v-card-subtitle class="text-h6">
              Управление заказами и контроль бюджета
            </v-card-subtitle>
            <div>
              <v-btn variant="outlined" prepend-icon="mdi-file-import">
                Импорт
              </v-btn>
            </div>
          </div>
          
          <v-tabs v-model="tab" class="mb-8">
            <v-tab value="all">Все</v-tab>
            <v-tab value="planned">Планируются</v-tab>
            <v-tab value="confirmed">Подтверждены</v-tab>
            <v-tab value="in-progress">В работе</v-tab>
            <v-tab value="completed">Завершены</v-tab>
          </v-tabs>
          
          <v-table>
            <thead>
              <tr>
                <th>№ заказа</th>
                <th>Наименование</th>
                <th>Контрагент</th>
                <th>Направление ФЭО</th>
                <th>Кол-во товаров</th>
                <th>Сумма</th>
                <th>Дата</th>
                <th>Статус</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="order in filteredOrders" :key="order.id">
                <td>{{ order.number }}</td>
                <td>{{ order.name }}</td>
                <td>{{ order.contractor }}</td>
                <td>{{ order.feoDirection }}</td>
                <td>{{ order.productCount }}</td>
                <td>{{ order.amount.toLocaleString() }} ₽</td>
                <td>{{ order.date }}</td>
                <td>
                  <v-chip :color="order.statusColor" size="small">
                    {{ order.status }}
                  </v-chip>
                </td>
                <td>
                  <v-btn
                    icon="mdi-eye"
                    variant="text"
                    size="small"
                    class="mr-2"
                    :to="`/orders/${order.id}`"
                  />
                  <v-btn
                    icon="mdi-pencil"
                    variant="text"
                    size="small"
                    class="mr-2"
                    :to="`/orders/${order.id}/edit`"
                  />
                  <v-btn
                    icon="mdi-file-document"
                    variant="text"
                    size="small"
                    class="mr-2"
                    :to="`/orders/${order.id}/documents`"
                  />
                </td>
              </tr>
            </tbody>
          </v-table>
          
          <!-- Пустая таблица -->
          <div v-if="filteredOrders.length === 0" class="text-center py-12">
            <v-icon icon="mdi-clipboard-text-outline" size="64" class="mb-4" color="grey-lighten-1" />
            <h3 class="text-h5 mb-2">Заказов пока нет</h3>
            <p class="text-body-1 text-medium-emphasis mb-6">
              Создайте первый заказ, чтобы начать работу
            </p>
            <v-btn color="primary" to="/create-order" prepend-icon="mdi-plus">
              Создать первый заказ
            </v-btn>
          </div>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const tab = ref('all')

// Демо-данные заказов
const orders = ref([
  {
    id: 1,
    number: 'ORD-2025-001',
    name: 'Оборудование для офиса',
    contractor: 'ООО "ТехноПрофи"',
    feoDirection: 'Основные средства',
    productCount: 3,
    amount: 450000,
    date: '15.02.2025',
    status: 'Подтвержден',
    statusColor: 'success'
  },
  {
    id: 2,
    number: 'ORD-2025-002',
    name: 'Канцелярские товары',
    contractor: 'ИП Иванов И.И.',
    feoDirection: 'Материальные запасы',
    productCount: 12,
    amount: 125000,
    date: '10.02.2025',
    status: 'В работе',
    statusColor: 'info'
  },
  {
    id: 3,
    number: 'ORD-2025-003',
    name: 'IT оборудование',
    contractor: 'АО "СтройКомплект"',
    feoDirection: 'Основные средства',
    productCount: 5,
    amount: 780000,
    date: '05.02.2025',
    status: 'Завершен',
    statusColor: 'primary'
  },
  {
    id: 4,
    number: 'ORD-2025-004',
    name: 'Мебель для переговорной',
    contractor: 'ЗАО "Электросила"',
    feoDirection: 'Капитальные вложения',
    productCount: 8,
    amount: 320000,
    date: '01.02.2025',
    status: 'Планируется',
    statusColor: 'warning'
  }
])

// Отфильтрованные заказы
const filteredOrders = computed(() => {
  if (tab.value === 'all') return orders.value
  
  const statusMap: Record<string, string> = {
    'planned': 'Планируется',
    'confirmed': 'Подтвержден',
    'in-progress': 'В работе',
    'completed': 'Завершен'
  }
  
  return orders.value.filter(order => order.status === statusMap[tab.value])
})
</script>