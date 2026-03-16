<template>
  <v-container fluid class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">Запросы КП</h1>
        <span class="text-body-2 text-medium-emphasis">{{ requests.length }} записей</span>
      </div>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreateDialog">
        Создать запрос КП
      </v-btn>
    </div>

    <!-- Filters -->
    <v-card class="mb-4" variant="outlined">
      <v-card-text class="py-3">
        <div class="d-flex align-center gap-4 flex-wrap">
          <v-select
            v-model="filterStatus"
            :items="statusItems"
            item-title="label"
            item-value="value"
            label="Статус"
            variant="outlined" density="compact" clearable hide-details
            style="min-width:160px"
          />
          <v-text-field
            v-model="search"
            prepend-inner-icon="mdi-magnify"
            label="Поиск по теме"
            variant="outlined" density="compact" clearable hide-details
            style="min-width:200px"
          />
        </div>
      </v-card-text>
    </v-card>

    <!-- Table -->
    <v-card variant="outlined">
      <v-data-table
        v-resizable-columns="'commercial-requests'"
        :headers="headers"
        :items="filteredRequests"
        :loading="loading"
        item-value="id"
        :items-per-page="20"
        density="comfortable"
      >
        <template v-slot:item.status="{ item }">
          <v-chip :color="statusColor(item.status)" size="small" variant="tonal">
            {{ statusLabel(item.status) }}
          </v-chip>
        </template>
        <template v-slot:item.recipients="{ item }">
          <div class="d-flex gap-1 flex-wrap">
            <v-chip
              v-for="r in item.recipients" :key="r.id"
              :color="recipientStatusColor(r.status)"
              size="x-small" variant="tonal"
              :title="r.email || ''"
            >
              {{ r.contractor_name || r.email || '—' }}
            </v-chip>
          </div>
        </template>
        <template v-slot:item.delivery_date="{ item }">
          {{ item.delivery_date ? formatDate(item.delivery_date) : '—' }}
        </template>
        <template v-slot:item.created_at="{ item }">
          {{ item.created_at ? item.created_at.slice(0, 10) : '—' }}
        </template>
        <template v-slot:item.actions="{ item }">
          <div class="d-flex gap-1">
            <v-btn icon="mdi-eye" size="x-small" variant="text" @click="openDetailDialog(item)" title="Подробнее" />
            <v-btn
              v-if="item.status === 'prepared'"
              icon="mdi-send" size="x-small" variant="text" color="primary"
              @click="updateStatus(item.id, 'sent')" title="Отметить отправленным"
            />
            <v-btn
              v-if="item.status === 'sent'"
              icon="mdi-check-all" size="x-small" variant="text" color="success"
              @click="updateStatus(item.id, 'received')" title="Получены ответы"
            />
            <v-btn
              v-if="['prepared','sent','received'].includes(item.status)"
              icon="mdi-archive" size="x-small" variant="text" color="grey"
              @click="updateStatus(item.id, 'closed')" title="Закрыть"
            />
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Create Dialog -->
    <v-dialog v-model="createDialog.show" max-width="680" scrollable>
      <v-card>
        <v-card-title class="pa-4 d-flex align-center">
          <v-icon icon="mdi-email-plus-outline" color="primary" class="mr-2" />
          Создать запрос КП
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="createDialog.show = false" />
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-autocomplete
            v-model="createDialog.purchase_id"
            :items="purchases"
            item-title="display_name"
            item-value="id"
            label="Закупка *"
            variant="outlined" density="compact" class="mb-3"
            :loading="createDialog.loadingPurchases"
          />
          <v-text-field
            v-model="createDialog.subject"
            label="Тема письма"
            variant="outlined" density="compact" class="mb-3"
            placeholder="Запрос коммерческого предложения на ..."
          />
          <v-textarea
            v-model="createDialog.intro_text"
            label="Текст письма"
            variant="outlined" density="compact" rows="4" class="mb-3"
            placeholder="Уважаемые партнёры, просим направить коммерческое предложение..."
          />
          <v-text-field
            v-model="createDialog.delivery_date"
            label="Срок предоставления КП"
            type="date"
            variant="outlined" density="compact" class="mb-3"
          />
          <div class="mb-1 text-body-2 font-weight-medium">Получатели (контрагенты)</div>
          <v-autocomplete
            v-model="createDialog.recipient_ids"
            :items="contractors"
            item-title="name"
            item-value="id"
            label="Выбрать контрагентов"
            variant="outlined" density="compact"
            multiple chips closable-chips
            :loading="createDialog.loadingContractors"
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="createDialog.show = false">Отмена</v-btn>
          <v-btn
            color="primary" variant="flat"
            :loading="createDialog.saving"
            :disabled="!createDialog.purchase_id"
            @click="saveRequest">
            Создать
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Detail Dialog -->
    <v-dialog v-model="detailDialog.show" max-width="680" scrollable>
      <v-card v-if="detailDialog.item">
        <v-card-title class="pa-4 d-flex align-center">
          <v-icon icon="mdi-email-outline" color="primary" class="mr-2" />
          Запрос КП #{{ detailDialog.item.id }}
          <v-chip :color="statusColor(detailDialog.item.status)" size="small" variant="tonal" class="ml-3">
            {{ statusLabel(detailDialog.item.status) }}
          </v-chip>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="detailDialog.show = false" />
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <div class="mb-2"><span class="text-caption text-medium-emphasis">Тема:</span> {{ detailDialog.item.subject || '—' }}</div>
          <div class="mb-2"><span class="text-caption text-medium-emphasis">Срок КП:</span> {{ detailDialog.item.delivery_date ? formatDate(detailDialog.item.delivery_date) : '—' }}</div>
          <div v-if="detailDialog.item.intro_text" class="mb-3 text-body-2 bg-grey-lighten-4 pa-3 rounded">
            {{ detailDialog.item.intro_text }}
          </div>
          <div class="text-body-2 font-weight-medium mb-2">Получатели:</div>
          <v-table density="compact">
            <thead>
              <tr><th>Контрагент</th><th>Email</th><th>Статус</th><th>Действие</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in detailDialog.item.recipients" :key="r.id">
                <td>{{ r.contractor_name || '—' }}</td>
                <td>{{ r.email || '—' }}</td>
                <td>
                  <v-chip :color="recipientStatusColor(r.status)" size="x-small" variant="tonal">
                    {{ recipientStatusLabel(r.status) }}
                  </v-chip>
                </td>
                <td>
                  <v-select
                    :model-value="r.status"
                    :items="recipientStatusItems"
                    item-title="label"
                    item-value="value"
                    variant="plain"
                    density="compact"
                    hide-details
                    style="min-width:120px"
                    @update:model-value="updateRecipientStatus(r.id, $event)"
                  />
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="detailDialog.show = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack.show" :color="snack.color" timeout="3000">{{ snack.text }}</v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted } from 'vue'
import { apiFetch } from '@/api'

interface Recipient { id: number; contractor_id?: number; contractor_name?: string; email?: string; status: string }
interface CommercialRequest {
  id: number; purchase_id: number; subject?: string; intro_text?: string
  delivery_date?: string; status: string; created_at?: string; recipients: Recipient[]
}
interface Purchase { id: number; item_name?: string; purchase_number?: number; display_name?: string }
interface Contractor { id: number; name: string; email?: string }

const REQUEST_STATUSES: Record<string, { label: string; color: string }> = {
  prepared: { label: 'Подготовлен',  color: 'blue-grey' },
  sent:     { label: 'Отправлен',   color: 'blue' },
  received: { label: 'Ответы получены', color: 'teal' },
  closed:   { label: 'Закрыт',      color: 'grey' },
}
const RECIPIENT_STATUSES: Record<string, { label: string; color: string }> = {
  prepared: { label: 'Ожидает',     color: 'orange' },
  sent:     { label: 'Отправлено',  color: 'blue' },
  delivered:{ label: 'Доставлено',  color: 'teal' },
  read:     { label: 'Прочитано',   color: 'purple' },
  replied:  { label: 'Ответил',     color: 'green' },
  declined: { label: 'Отказал',     color: 'red' },
}

const statusLabel  = (s: string) => REQUEST_STATUSES[s]?.label || s
const statusColor  = (s: string) => REQUEST_STATUSES[s]?.color || 'grey'
const recipientStatusLabel = (s: string) => RECIPIENT_STATUSES[s]?.label || s
const recipientStatusColor = (s: string) => RECIPIENT_STATUSES[s]?.color || 'grey'

const statusItems = Object.entries(REQUEST_STATUSES).map(([v, d]) => ({ value: v, label: d.label }))
const recipientStatusItems = Object.entries(RECIPIENT_STATUSES).map(([v, d]) => ({ value: v, label: d.label }))

const headers = [
  { title: '№', key: 'id', width: 60 },
  { title: 'Тема', key: 'subject', minWidth: 200 },
  { title: 'Получатели', key: 'recipients', minWidth: 200, sortable: false },
  { title: 'Срок КП', key: 'delivery_date', width: 110 },
  { title: 'Создан', key: 'created_at', width: 110 },
  { title: 'Статус', key: 'status', width: 140 },
  { title: 'Действия', key: 'actions', width: 130, sortable: false },
]

const requests = ref<CommercialRequest[]>([])
const purchases = ref<Purchase[]>([])
const contractors = ref<Contractor[]>([])
const loading = ref(false)
const filterStatus = ref('')
const search = ref('')

const snack = reactive({ show: false, text: '', color: 'success' })
const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }

const createDialog = reactive({
  show: false,
  purchase_id: null as number | null,
  subject: '',
  intro_text: '',
  delivery_date: '',
  recipient_ids: [] as number[],
  saving: false,
  loadingPurchases: false,
  loadingContractors: false,
})

const detailDialog = reactive({ show: false, item: null as CommercialRequest | null })

const formatDate = (d: string) => {
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}

const filteredRequests = computed(() => {
  let r = requests.value
  if (filterStatus.value) r = r.filter(x => x.status === filterStatus.value)
  if (search.value) {
    const q = search.value.toLowerCase()
    r = r.filter(x => (x.subject || '').toLowerCase().includes(q))
  }
  return r
})

async function loadRequests() {
  loading.value = true
  try {
    requests.value = await apiFetch<CommercialRequest[]>('/commercial-requests/')
  } finally {
    loading.value = false
  }
}

async function openCreateDialog() {
  createDialog.purchase_id = null
  createDialog.subject = ''
  createDialog.intro_text = ''
  createDialog.delivery_date = ''
  createDialog.recipient_ids = []
  createDialog.show = true

  if (purchases.value.length === 0) {
    createDialog.loadingPurchases = true
    try {
      const data = await apiFetch<any[]>('/purchases/?limit=500')
      purchases.value = data.map(p => ({
        ...p,
        display_name: `#${p.purchase_number || p.id} ${p.item_name || p.subject || ''}`.trim(),
      }))
    } finally {
      createDialog.loadingPurchases = false
    }
  }
  if (contractors.value.length === 0) {
    createDialog.loadingContractors = true
    try {
      contractors.value = await apiFetch<Contractor[]>('/contractors/')
    } finally {
      createDialog.loadingContractors = false
    }
  }
}

async function saveRequest() {
  createDialog.saving = true
  try {
    const body: any = {
      purchase_id: createDialog.purchase_id,
      subject: createDialog.subject || null,
      intro_text: createDialog.intro_text || null,
      delivery_date: createDialog.delivery_date || null,
      recipient_ids: createDialog.recipient_ids,
    }
    const created = await apiFetch<CommercialRequest>('/commercial-requests/', { method: 'POST', body })
    requests.value = [created, ...requests.value]
    createDialog.show = false
    showSnack('Запрос КП создан')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка создания', 'error')
  } finally {
    createDialog.saving = false
  }
}

function openDetailDialog(item: CommercialRequest) {
  detailDialog.item = item
  detailDialog.show = true
}

async function updateStatus(id: number, status: string) {
  try {
    const updated = await apiFetch<CommercialRequest>(`/commercial-requests/${id}/status`, {
      method: 'PATCH',
      body: { status },
    })
    const idx = requests.value.findIndex(r => r.id === id)
    if (idx >= 0) requests.value[idx] = updated
    if (detailDialog.item?.id === id) detailDialog.item = updated
    showSnack('Статус обновлён')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка обновления', 'error')
  }
}

async function updateRecipientStatus(recipientId: number, status: string) {
  try {
    const updated = await apiFetch<CommercialRequest>(`/commercial-requests/recipients/${recipientId}/status`, {
      method: 'PATCH',
      body: { status },
    })
    const idx = requests.value.findIndex(r => r.id === updated.id)
    if (idx >= 0) requests.value[idx] = updated
    if (detailDialog.item?.id === updated.id) detailDialog.item = updated
  } catch (e: any) {
    showSnack(e.message || 'Ошибка', 'error')
  }
}

onMounted(loadRequests)
</script>
