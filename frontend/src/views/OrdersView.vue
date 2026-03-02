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
              <!-- STATUS_MENU_START -->
<v-menu>
                    <template v-slot:activator="{ props }">
                      <v-btn icon="mdi-swap-horizontal" variant="text" size="small" v-bind="props" class="mr-2" />
                    </template>
                    <v-list density="compact">
                      <v-list-item @click="changeStatus(order.id, 'plan')"><v-list-item-title>📋 Планируется</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'contract')"><v-list-item-title>📝 Контракт</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'delivery')"><v-list-item-title>🚚 Поставка</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'paid')"><v-list-item-title>✅ Оплачено</v-list-item-title></v-list-item>
                    </v-list>
                  </v-menu>
<!-- STATUS_MENU_END -->
<v-btn variant="outlined" prepend-icon="mdi-file-import" class="mr-2">
                Импорт
              </v-btn>
              <!-- STATUS_MENU_START -->
<v-menu>
                    <template v-slot:activator="{ props }">
                      <v-btn icon="mdi-swap-horizontal" variant="text" size="small" v-bind="props" class="mr-2" />
                    </template>
                    <v-list density="compact">
                      <v-list-item @click="changeStatus(order.id, 'plan')"><v-list-item-title>📋 Планируется</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'contract')"><v-list-item-title>📝 Контракт</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'delivery')"><v-list-item-title>🚚 Поставка</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'paid')"><v-list-item-title>✅ Оплачено</v-list-item-title></v-list-item>
                    </v-list>
                  </v-menu>
<!-- STATUS_MENU_END -->
<v-btn variant="outlined" prepend-icon="mdi-file-export" color="success" @click="exportToExcel">
                Экспорт в Excel
              </v-btn>
            </div>
          </div>
          
          <v-tabs v-model="tab" class="mb-4">
            <v-tab value="all">Все</v-tab>
            <v-tab value="planned">Планируются</v-tab>
            <v-tab value="confirmed">Подтверждены</v-tab>
            <v-tab value="in-progress">В работе</v-tab>
            <v-tab value="delivered">Поставлено (не оплачено)</v-tab>
            <v-tab value="signed">Подписан</v-tab>
            <v-tab value="completed">Завершены</v-tab>
            <v-tab value="payments">Ежемесячные платежи</v-tab>
          </v-tabs>
          
          <!-- Вкладки по субсидиям -->
          <v-tabs v-model="subsidyTab" class="mb-8">
            <v-tab value="all">Все субсидии</v-tab>
            <v-tab v-for="subsidy in subsidies" :key="subsidy.id" :value="subsidy.id.toString()">
              {{ subsidy.shortName }}
            </v-tab>
          </v-tabs>
          
          <template v-if="tab !== 'payments'">
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
                  <!-- STATUS_MENU_START -->
<v-menu>
                    <template v-slot:activator="{ props }">
                      <v-btn icon="mdi-swap-horizontal" variant="text" size="small" v-bind="props" class="mr-2" />
                    </template>
                    <v-list density="compact">
                      <v-list-item @click="changeStatus(order.id, 'plan')"><v-list-item-title>📋 Планируется</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'contract')"><v-list-item-title>📝 Контракт</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'delivery')"><v-list-item-title>🚚 Поставка</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'paid')"><v-list-item-title>✅ Оплачено</v-list-item-title></v-list-item>
                    </v-list>
                  </v-menu>
<!-- STATUS_MENU_END -->
<v-btn
                    icon="mdi-eye"
                    variant="text"
                    size="small"
                    class="mr-2"
                    :to="`/orders/${order.id}`"
                  />
                  <!-- STATUS_MENU_START -->
<v-menu>
                    <template v-slot:activator="{ props }">
                      <v-btn icon="mdi-swap-horizontal" variant="text" size="small" v-bind="props" class="mr-2" />
                    </template>
                    <v-list density="compact">
                      <v-list-item @click="changeStatus(order.id, 'plan')"><v-list-item-title>📋 Планируется</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'contract')"><v-list-item-title>📝 Контракт</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'delivery')"><v-list-item-title>🚚 Поставка</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'paid')"><v-list-item-title>✅ Оплачено</v-list-item-title></v-list-item>
                    </v-list>
                  </v-menu>
<!-- STATUS_MENU_END -->
<v-btn
                    icon="mdi-pencil"
                    variant="text"
                    size="small"
                    class="mr-2"
                    :to="`/orders/${order.id}/edit`"
                  />
                  <!-- STATUS_MENU_START -->
<v-menu>
                    <template v-slot:activator="{ props }">
                      <v-btn icon="mdi-swap-horizontal" variant="text" size="small" v-bind="props" class="mr-2" />
                    </template>
                    <v-list density="compact">
                      <v-list-item @click="changeStatus(order.id, 'plan')"><v-list-item-title>📋 Планируется</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'contract')"><v-list-item-title>📝 Контракт</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'delivery')"><v-list-item-title>🚚 Поставка</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'paid')"><v-list-item-title>✅ Оплачено</v-list-item-title></v-list-item>
                    </v-list>
                  </v-menu>
<!-- STATUS_MENU_END -->
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
            <!-- STATUS_MENU_START -->
<v-menu>
                    <template v-slot:activator="{ props }">
                      <v-btn icon="mdi-swap-horizontal" variant="text" size="small" v-bind="props" class="mr-2" />
                    </template>
                    <v-list density="compact">
                      <v-list-item @click="changeStatus(order.id, 'plan')"><v-list-item-title>📋 Планируется</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'contract')"><v-list-item-title>📝 Контракт</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'delivery')"><v-list-item-title>🚚 Поставка</v-list-item-title></v-list-item>
                      <v-list-item @click="changeStatus(order.id, 'paid')"><v-list-item-title>✅ Оплачено</v-list-item-title></v-list-item>
                    </v-list>
                  </v-menu>
<!-- STATUS_MENU_END -->
<v-btn color="primary" to="/create-order" prepend-icon="mdi-plus">
              Создать первый заказ
            </v-btn>
          </div>
          </template>
          <template v-else>
            <v-table>
              <thead>
                <tr>
                  <th>№ заказа</th>
                  <th>Контрагент</th>
                  <th>Сумма</th>
                  <th>Срок оплаты</th>
                  <th>Статус</th>
                  <th>Субсидия</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="payment in payments" :key="payment.id">
                  <td>{{ payment.orderNumber }}</td>
                  <td>{{ payment.contractor }}</td>
                  <td>{{ payment.amount.toLocaleString() }} ₽</td>
                  <td>{{ payment.dueDate }}</td>
                  <td><v-chip :color="payment.statusColor" size="small">{{ payment.status }}</v-chip></td>
                  <td>{{ payment.subsidy }}</td>
                </tr>
              </tbody>
            </v-table>
          </template>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const tab = ref('all')
const subsidyTab = ref('all')

// Демо-данные субсидий (взять из API)
const subsidies = ref([
  { id: 1, name: 'Патриотика 2025', shortName: 'Патриотика' },
  { id: 2, name: 'ДНР Восстановление 2025', shortName: 'ДНР' },
  { id: 3, name: 'ЗО Молодёжь 2025', shortName: 'ЗО' },
  { id: 4, name: 'ФАДМ Волонтёры 2025', shortName: 'ФАДМ' },
  { id: 5, name: 'МинПрос Образование 2025', shortName: 'МинПрос' },
])

// Демо-данные ежемесячных платежей
const payments = ref([
  {
    id: 1,
    orderNumber: 'ORD-2025-001',
    contractor: 'ООО "ТехноПрофи"',
    amount: 150000,
    dueDate: '05.03.2025',
    status: 'Ожидает оплаты',
    statusColor: 'warning',
    subsidy: 'Патриотика 2025'
  },
  {
    id: 2,
    orderNumber: 'ORD-2025-002',
    contractor: 'ИП Иванов И.И.',
    amount: 62500,
    dueDate: '10.03.2025',
    status: 'Оплачен',
    statusColor: 'success',
    subsidy: 'ДНР Восстановление 2025'
  },
  {
    id: 3,
    orderNumber: 'ORD-2025-003',
    contractor: 'АО "СтройКомплект"',
    amount: 390000,
    dueDate: '15.03.2025',
    status: 'Просрочен',
    statusColor: 'error',
    subsidy: 'ЗО Молодёжь 2025'
  },
  {
    id: 4,
    orderNumber: 'ORD-2025-005',
    contractor: 'ООО "Социальные технологии"',
    amount: 325000,
    dueDate: '25.03.2025',
    status: 'Ожидает оплаты',
    statusColor: 'warning',
    subsidy: 'ФАДМ Волонтёры 2025'
  },
])

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
    statusColor: 'success',
    subsidyId: 1 // Патриотика
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
    statusColor: 'info',
    subsidyId: 2 // ДНР
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
    statusColor: 'primary',
    subsidyId: 3 // ЗО
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
    statusColor: 'warning',
    subsidyId: 1 // Патриотика
  },
  {
    id: 5,
    number: 'ORD-2025-005',
    name: 'Волонтёрское оборудование',
    contractor: 'ООО "Социальные технологии"',
    feoDirection: 'Материальные запасы',
    productCount: 20,
    amount: 650000,
    date: '20.02.2025',
    status: 'Поставлено (не оплачено)',
    statusColor: 'deep-purple',
    subsidyId: 4 // ФАДМ
  },
  {
    id: 6,
    number: 'ORD-2025-006',
    name: 'Учебные материалы',
    contractor: 'Издательство "Просвещение"',
    feoDirection: 'Образовательные расходы',
    productCount: 150,
    amount: 1200000,
    date: '18.02.2025',
    status: 'Подписан',
    statusColor: 'info',
    subsidyId: 5 // МинПрос
  }
])

// Отфильтрованные заказы
const filteredOrders = computed(() => {

// Смена статуса закупки
const changeStatus = async (id, newStatus) => {
  try {
    await fetch(`/api/purchases/${id}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus })
    })
    loadOrders()
  } catch (e) {
    console.error(e)
  }
}

  let result = orders.value
  
  // Фильтр по статусу
  if (tab.value !== 'all') {
    const statusMap: Record<string, string> = {
      'planned': 'Планируется',
      'confirmed': 'Подтвержден',
      'in-progress': 'В работе',
      'completed': 'Завершен',
      'delivered': 'Поставлено (не оплачено)',
      'signed': 'Подписан'
    }
    const targetStatus = statusMap[tab.value]
    if (targetStatus) {
      result = result.filter(order => order.status === targetStatus)
    }
  }
  
  // Фильтр по субсидии
  if (subsidyTab.value !== 'all') {
    const subsidyId = parseInt(subsidyTab.value)
    result = result.filter(order => order.subsidyId === subsidyId)
  }
  
  return result
})

// Экспорт в Excel
const exportToExcel = async () => {
  try {
    const token = localStorage.getItem('token')
    const response = await fetch('http://localhost:8000/api/purchases/export/excel', {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })
    
    if (!response.ok) throw new Error('Ошибка экспорта')
    
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `заказы_${new Date().toISOString().slice(0,10)}.xlsx`
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
  } catch (e) {
    alert('Ошибка экспорта: ' + e)
  }
}
</script>