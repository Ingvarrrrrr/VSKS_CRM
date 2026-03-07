<template>
  <v-container fluid class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">Закупки</h1>
        <span class="text-body-2 text-medium-emphasis">{{ orders.length }} записей</span>
      </div>
      <div class="d-flex gap-2">
        <v-btn variant="outlined" prepend-icon="mdi-file-export" color="success" @click="exportToExcel">Excel</v-btn>
        <v-btn color="primary" prepend-icon="mdi-plus" to="/create-order">Добавить</v-btn>
      </div>
    </div>

    <!-- Filters -->
    <v-card class="mb-4" variant="outlined">
      <v-card-text class="py-3">
        <div class="d-flex align-center gap-4 flex-wrap">
          <v-select
            v-model="filterSubsidyId"
            :items="subsidies"
            item-title="name"
            item-value="id"
            label="Субсидия"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:220px"
          />
          <v-select
            v-model="filterStatus"
            :items="statusItems"
            item-title="label"
            item-value="value"
            label="Статус"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:170px"
          />
          <v-text-field
            v-model="search"
            prepend-inner-icon="mdi-magnify"
            label="Поиск"
            variant="outlined"
            density="compact"
            clearable
            hide-details
            style="min-width:200px"
          />
        </div>
      </v-card-text>
    </v-card>

    <!-- Status tab chips -->
    <v-chip-group v-model="filterStatus" class="mb-4">
      <v-chip value="" variant="outlined" filter>Все</v-chip>
      <v-chip
        v-for="s in statusItems"
        :key="s.value"
        :value="s.value"
        :color="s.color"
        filter
        variant="outlined"
      >
        {{ s.label }}
      </v-chip>
    </v-chip-group>

    <!-- Bulk actions bar -->
    <div v-if="selectedOrders.length > 0" class="d-flex align-center gap-3 mb-3 pa-3 bg-blue-lighten-5 rounded-lg">
      <v-icon icon="mdi-checkbox-marked-outline" color="primary" />
      <span class="text-body-2 font-weight-medium">Выбрано: {{ selectedOrders.length }}</span>
      <v-spacer />
      <v-btn v-if="isAdmin" color="error" variant="tonal" size="small" prepend-icon="mdi-delete" @click="confirmBulkDelete">
        Удалить выбранные
      </v-btn>
      <v-btn variant="text" size="small" @click="selectedOrders = []">Снять выделение</v-btn>
    </div>

    <!-- Table -->
    <v-card variant="outlined">
      <v-data-table
        :headers="headers"
        :items="filteredOrders"
        :loading="loading"
        :search="search"
        density="compact"
        hover
        show-expand
        show-select
        v-model="selectedOrders"
        v-model:expanded="expanded"
        items-per-page="25"
        :items-per-page-options="[25, 50, 100]"
        return-object
      >
        <!-- Expand toggle column -->
        <template #item.data-table-expand="{ item, internalItem, isExpanded, toggleExpand }">
          <v-btn
            v-if="item.items && item.items.length > 0"
            :icon="isExpanded(internalItem) ? 'mdi-chevron-up' : 'mdi-chevron-down'"
            variant="text"
            size="small"
            @click="toggleExpand(internalItem)"
          />
        </template>

        <!-- Предмет договора -->
        <template #item.subject="{ item }">
          <span class="text-body-2 text-truncate" style="max-width:180px;display:inline-block">
            {{ item.subject || '—' }}
          </span>
        </template>

        <!-- Display name (first item or legacy item_name) -->
        <template #item.display_name="{ item }">
          <span class="text-body-2">{{ itemDisplayName(item) }}</span>
        </template>

        <template #item.status="{ item }">
          <v-chip :color="STATUS_COLOR[item.status] || 'grey'" size="small" variant="tonal">
            {{ STATUS_LABEL[item.status] || item.status }}
          </v-chip>
        </template>

        <template #item.effective_price="{ item }">
          {{ formatMoney(effectivePrice(item)) }}
        </template>

        <template #item.contract_date="{ item }">
          {{ item.contract_date ? formatDate(item.contract_date) : '—' }}
        </template>

        <template #item.subsidy_name="{ item }">
          <span class="text-body-2 text-truncate" style="max-width:150px;display:inline-block">
            {{ item.subsidy_name || '—' }}
          </span>
        </template>

        <template #item.actions="{ item }">
          <div class="d-flex align-center gap-1">
            <v-btn
              v-if="nextStatus(item.status)"
              size="x-small"
              :color="STATUS_COLOR[nextStatus(item.status)!]"
              variant="tonal"
              :loading="transitioning === item.id"
              @click="doTransition(item)"
            >
              → {{ STATUS_LABEL[nextStatus(item.status)!] }}
            </v-btn>
            <v-btn icon="mdi-pencil" variant="text" size="small" :to="`/orders/${item.id}/edit`" />
            <v-btn v-if="isAdmin" icon="mdi-delete" variant="text" size="small" color="error" @click="confirmDeleteOne(item)" />
          </div>
        </template>

        <!-- Expanded row: items list -->
        <template #expanded-row="{ columns, item }">
          <tr>
            <td :colspan="columns.length" class="pa-0 bg-grey-lighten-5">
              <div class="pa-3">
                <v-table density="compact" class="rounded border">
                  <thead>
                    <tr class="bg-grey-lighten-4">
                      <th>Наименование позиции</th>
                      <th>Тип</th>
                      <th class="text-right">Кол-во</th>
                      <th>Ед.</th>
                      <th class="text-right">Цена ед., ₽</th>
                      <th class="text-right">Сумма, ₽</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="itm in item.items" :key="itm.id">
                      <td>{{ itm.item_name }}</td>
                      <td>{{ itm.item_type || '—' }}</td>
                      <td class="text-right">{{ itm.quantity ?? '—' }}</td>
                      <td>{{ itm.unit || '—' }}</td>
                      <td class="text-right">{{ itm.unit_price ? Number(itm.unit_price).toLocaleString('ru-RU') : '—' }}</td>
                      <td class="text-right">{{ itm.total_price ? Number(itm.total_price).toLocaleString('ru-RU') : '—' }}</td>
                    </tr>
                    <tr v-if="!item.items?.length">
                      <td colspan="6" class="text-center text-medium-emphasis text-caption py-2">Нет позиций</td>
                    </tr>
                  </tbody>
                </v-table>
              </div>
            </td>
          </tr>
        </template>

        <template #no-data>
          <div class="text-center py-10">
            <v-icon icon="mdi-clipboard-text-outline" size="48" color="grey-lighten-1" class="mb-3" />
            <div class="text-medium-emphasis">Закупки не найдены</div>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Delete dialog -->
    <v-dialog v-model="deleteDialog.show" max-width="420">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6 d-flex align-center gap-2">
          <v-icon icon="mdi-alert-circle-outline" color="error" />
          Удалить закупки
        </v-card-title>
        <v-card-text class="px-6">
          <template v-if="deleteDialog.bulk">
            Удалить <strong>{{ selectedOrders.length }}</strong> выбранных закупок? Действие нельзя отменить.
          </template>
          <template v-else>
            Удалить закупку <strong>{{ deleteDialog.single?.subject || deleteDialog.single?.item_name || `#${deleteDialog.single?.id}` }}</strong>? Действие нельзя отменить.
          </template>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog.show = false">Отмена</v-btn>
          <v-btn color="error" :loading="deleteDialog.deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3000" location="bottom right">
      {{ snack.text }}
    </v-snackbar>

    <!-- Guard dialog -->
    <v-dialog v-model="guardDialog.show" max-width="480">
      <v-card>
        <v-card-title class="text-h6 pt-4 px-6">Не заполнены обязательные поля</v-card-title>
        <v-card-text class="px-6">
          <p class="mb-3 text-body-2 text-medium-emphasis">
            Для перехода в статус «{{ STATUS_LABEL[guardDialog.targetStatus] }}» заполните:
          </p>
          <v-list density="compact">
            <v-list-item
              v-for="f in guardDialog.missing"
              :key="f"
              prepend-icon="mdi-alert-circle-outline"
              :title="f"
            />
          </v-list>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="guardDialog.show = false">Закрыть</v-btn>
          <v-btn color="primary" :to="`/orders/${guardDialog.purchaseId}/edit`" @click="guardDialog.show = false">
            Открыть форму
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useRoute } from 'vue-router'
import { apiFetch } from '@/api'

const route = useRoute()
const userRole = localStorage.getItem('user_role') || ''
const isAdmin = userRole === 'admin'

interface PurchaseItem { id: number; item_name: string; item_type?: string; quantity?: number; unit?: string; unit_price?: number; total_price?: number }
interface Subsidy { id: number; name: string; year: number }
interface Purchase {
  id: number
  purchase_number?: number
  item_name?: string
  contractor_name?: string
  feo_category_name?: string
  subsidy_name?: string
  subsidy_id?: number
  subject?: string
  planned_total_price?: number
  total_nmck?: number
  purchase_method?: string
  contract_price?: number
  delivery_payment_amount?: number
  status: string
  contract_number?: string
  contract_date?: string
  acceptance_doc_name?: string
  acceptance_doc_date?: string
  acceptance_doc_number?: string
  acceptance_doc_amount?: number
  payment_doc_number?: string
  payment_doc_date?: string
  payment_amount?: number
  items?: PurchaseItem[]
}

const STATUS_ORDER = ['planned', 'confirmed', 'in_progress', 'contracted', 'delivered', 'paid']
const STATUS_LABEL: Record<string, string> = {
  planned: 'Планируется', confirmed: 'Подтверждено',
  in_progress: 'Ведётся работа',
  contracted: 'Договор', delivered: 'Поставлено', paid: 'Оплачено',
}
const STATUS_COLOR: Record<string, string> = {
  planned: 'orange', confirmed: 'blue',
  in_progress: 'teal',
  contracted: 'indigo', delivered: 'deep-purple', paid: 'green',
}
const statusItems = STATUS_ORDER.map(v => ({ value: v, label: STATUS_LABEL[v], color: STATUS_COLOR[v] }))

const TRANSITION_REQUIRED: Record<string, { field: keyof Purchase; label: string }[]> = {
  contracted: [
    { field: 'contract_number', label: 'Номер договора' },
    { field: 'contract_date', label: 'Дата договора' },
  ],
  delivered: [
    { field: 'acceptance_doc_name', label: 'Наименование акта' },
    { field: 'acceptance_doc_date', label: 'Дата акта' },
    { field: 'acceptance_doc_number', label: 'Номер акта' },
    { field: 'acceptance_doc_amount', label: 'Сумма акта' },
  ],
  paid: [
    { field: 'payment_doc_number', label: 'Номер платёжного поручения' },
    { field: 'payment_doc_date', label: 'Дата платёжного поручения' },
    { field: 'payment_amount', label: 'Сумма платежа' },
  ],
}

const headers = [
  { title: '', key: 'data-table-expand', width: 48, sortable: false },
  { title: '№', key: 'purchase_number', width: 60 },
  { title: 'Предмет договора', key: 'subject', minWidth: 180 },
  { title: 'Наименование', key: 'display_name', minWidth: 200 },
  { title: 'Контрагент', key: 'contractor_name', minWidth: 160 },
  { title: 'Субсидия', key: 'subsidy_name', minWidth: 150 },
  { title: 'Цена', key: 'effective_price', align: 'end' as const, minWidth: 120, sortable: false },
  { title: '№ договора', key: 'contract_number', minWidth: 120 },
  { title: 'Дата договора', key: 'contract_date', minWidth: 120 },
  { title: 'Статус', key: 'status', width: 130 },
  { title: 'Действия', key: 'actions', sortable: false, width: 200 },
]

const orders = ref<Purchase[]>([])
const subsidies = ref<Subsidy[]>([])
const loading = ref(false)
const transitioning = ref<number | null>(null)
const filterStatus = ref<string>('')
const filterSubsidyId = ref<number | null>(null)
const search = ref('')
const expanded = ref<string[]>([])
const selectedOrders = ref<Purchase[]>([])

const snack = reactive({ show: false, text: '', color: 'success' })
const guardDialog = reactive({
  show: false, purchaseId: 0, targetStatus: '', missing: [] as string[],
})
const deleteDialog = reactive({
  show: false, single: null as Purchase | null, bulk: false, deleting: false,
})

const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }

const formatMoney = (v?: number | null) =>
  v ? Number(v).toLocaleString('ru-RU') + ' ₽' : '—'

const effectivePrice = (item: Purchase): number | null => {
  switch (item.status) {
    case 'planned': case 'confirmed': case 'in_progress':
      return item.total_nmck ?? item.planned_total_price ?? null
    case 'contracted':
      return item.purchase_method === 'single'
        ? item.contract_price ?? null
        : item.delivery_payment_amount ?? null
    case 'delivered':
      return item.acceptance_doc_amount ?? null
    case 'paid':
      return item.payment_amount ?? null
    default:
      return item.total_nmck ?? item.planned_total_price ?? null
  }
}

const formatDate = (d: string) => {
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}

const itemDisplayName = (p: Purchase) => {
  if (p.items && p.items.length > 0) {
    return p.items.length === 1
      ? p.items[0].item_name
      : `${p.items[0].item_name} (+${p.items.length - 1})`
  }
  return p.item_name || '—'
}

const nextStatus = (current: string): string | null => {
  const idx = STATUS_ORDER.indexOf(current)
  return idx >= 0 && idx < STATUS_ORDER.length - 1 ? STATUS_ORDER[idx + 1] : null
}

const filteredOrders = computed(() => {
  let r = orders.value
  if (filterStatus.value) r = r.filter(o => o.status === filterStatus.value)
  if (filterSubsidyId.value) r = r.filter(o => o.subsidy_id === filterSubsidyId.value)
  return r
})

const loadOrders = async () => {
  loading.value = true
  try {
    orders.value = await apiFetch<Purchase[]>('/purchases/')
  } catch {
    showSnack('Ошибка загрузки закупок', 'error')
  } finally {
    loading.value = false
  }
}

const loadSubsidies = async () => {
  try { subsidies.value = await apiFetch<Subsidy[]>('/subsidies/') } catch {}
}

onMounted(() => {
  loadOrders()
  loadSubsidies()
  const qSub = route.query.subsidy_id
  if (qSub) filterSubsidyId.value = Number(qSub)
})

const doTransition = async (item: Purchase) => {
  const target = nextStatus(item.status)
  if (!target) return
  const required = TRANSITION_REQUIRED[target]
  if (required) {
    const missing = required.filter(r => !item[r.field]).map(r => r.label)
    if (missing.length) {
      guardDialog.purchaseId = item.id
      guardDialog.targetStatus = target
      guardDialog.missing = missing
      guardDialog.show = true
      return
    }
  }
  transitioning.value = item.id
  try {
    await apiFetch(`/purchases/${item.id}/transition?status=${target}`, { method: 'POST' })
    showSnack(`Статус изменён → ${STATUS_LABEL[target]}`)
    await loadOrders()
  } catch (e: any) {
    showSnack(e?.detail || e?.message || 'Ошибка перехода', 'error')
  } finally {
    transitioning.value = null
  }
}

const confirmDeleteOne = (item: Purchase) => {
  deleteDialog.single = item
  deleteDialog.bulk = false
  deleteDialog.show = true
}

const confirmBulkDelete = () => {
  deleteDialog.single = null
  deleteDialog.bulk = true
  deleteDialog.show = true
}

const doDelete = async () => {
  deleteDialog.deleting = true
  try {
    const targets = deleteDialog.bulk
      ? selectedOrders.value.map(o => o.id)
      : [deleteDialog.single!.id]
    await Promise.all(targets.map(id => apiFetch(`/purchases/${id}`, { method: 'DELETE' })))
    showSnack(`Удалено ${targets.length} закупок`, 'warning')
    selectedOrders.value = []
    deleteDialog.show = false
    await loadOrders()
  } catch (e: any) {
    showSnack(e?.detail || 'Ошибка удаления', 'error')
  } finally {
    deleteDialog.deleting = false
  }
}

const exportToExcel = async () => {
  try {
    const token = localStorage.getItem('access_token')
    const params = new URLSearchParams()
    if (filterSubsidyId.value) params.set('subsidy_id', String(filterSubsidyId.value))
    if (filterStatus.value) params.set('status', filterStatus.value)
    const response = await fetch(`/api/purchases/export/excel?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!response.ok) throw new Error('Ошибка экспорта')
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `zakupki_${new Date().toISOString().slice(0, 10)}.xlsx`
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
  } catch {
    showSnack('Ошибка экспорта', 'error')
  }
}
</script>
