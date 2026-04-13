<template>
  <v-container fluid class="pa-4">
    <!-- Header -->
    <div class="d-flex align-center mb-4 flex-wrap" style="gap:12px">
      <div>
        <h1 class="text-h5 font-weight-bold">Заявки</h1>
        <span class="text-body-2 text-medium-emphasis">
          {{ isManagerOrAdmin ? activeTab === 'my' ? 'Мои заявки' : 'Заявки сотрудников' : 'Мои заявки' }}
        </span>
      </div>
      <v-spacer />
      <v-btn variant="tonal" color="primary" size="small" prepend-icon="mdi-refresh" :loading="loading" @click="loadWishes">
        Обновить
      </v-btn>
    </div>

    <!-- Tabs (manager/admin only) -->
    <v-tabs v-if="isManagerOrAdmin" v-model="activeTab" class="mb-4">
      <v-tab value="my">Мои заявки</v-tab>
      <v-tab value="all">Заявки сотрудников</v-tab>
    </v-tabs>

    <!-- ── MY WISHES TAB ── -->
    <div v-if="!isManagerOrAdmin || activeTab === 'my'">
      <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-2" />

      <div v-if="!loading && myWishes.length === 0" class="text-center py-12">
        <v-icon icon="mdi-hand-heart-outline" size="64" color="grey-lighten-1" class="mb-3" />
        <div class="text-h6 text-medium-emphasis">Нет заявок</div>
        <div class="text-body-2 text-medium-emphasis mt-1">Создайте первую заявку с помощью кнопки +</div>
      </div>

      <v-row v-else dense>
        <v-col v-for="wish in myWishes" :key="wish.id" cols="12" md="6" lg="4">
          <v-card variant="outlined" class="pa-3 h-100">
            <div class="d-flex align-start justify-space-between mb-2">
              <div class="flex-grow-1 mr-2">
                <div class="text-subtitle-1 font-weight-medium">{{ wish.title }}</div>
                <div v-if="wish.description" class="text-body-2 text-medium-emphasis mt-1" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">
                  {{ wish.description }}
                </div>
              </div>
              <div class="d-flex flex-column align-end ga-1">
                <v-chip :color="statusColor[wish.status]" size="small" variant="tonal">
                  {{ statusLabel[wish.status] }}
                </v-chip>
                <v-btn
                  v-if="wish.status === 'draft'"
                  icon="mdi-delete-outline"
                  size="x-small"
                  variant="text"
                  color="error"
                  :loading="deletingId === wish.id"
                  @click="deleteWish(wish)"
                />
              </div>
            </div>

            <!-- Metadata -->
            <div class="d-flex flex-wrap ga-2 text-caption text-medium-emphasis mb-2">
              <span v-if="wish.quantity">Кол-во: <b>{{ wish.quantity }} {{ wish.unit || '' }}</b></span>
              <span v-if="wish.estimated_price">Цена: <b>{{ formatPrice(wish.estimated_price) }}</b></span>
            </div>

            <!-- Rejection reason -->
            <div v-if="wish.status === 'rejected' && wish.rejection_reason" class="text-caption text-error mt-1 mb-2">
              <v-icon icon="mdi-close-circle" size="14" class="mr-1" />
              Причина отказа: {{ wish.rejection_reason }}
            </div>

            <!-- Link to purchase for converted wishes -->
            <div v-if="wish.status === 'converted' && wish.purchase_id" class="mb-2">
              <v-btn
                size="small"
                variant="tonal"
                color="purple"
                prepend-icon="mdi-cart-arrow-right"
                :href="`/orders/${wish.purchase_id}/edit`"
                @click.prevent="$router.push(`/orders/${wish.purchase_id}/edit`)"
              >
                Перейти к закупке
              </v-btn>
            </div>

            <!-- Actions for draft wishes -->
            <div v-if="wish.status === 'draft'" class="d-flex ga-2 mt-2">
              <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-pencil" @click="openEditDialog(wish)">
                Изменить
              </v-btn>
              <v-btn
                size="small"
                variant="flat"
                color="success"
                prepend-icon="mdi-send"
                :loading="submittingId === wish.id"
                @click="submitWish(wish)"
              >
                Отправить
              </v-btn>
            </div>
          </v-card>
        </v-col>
      </v-row>

      <!-- FAB to create new wish -->
      <v-btn
        icon="mdi-plus"
        color="primary"
        size="large"
        style="position:fixed;bottom:32px;right:32px;z-index:100"
        elevation="4"
        @click="openCreateDialog"
      />
    </div>

    <!-- ── ALL WISHES TAB (manager/admin) ── -->
    <div v-if="isManagerOrAdmin && activeTab === 'all'">
      <!-- Status filter chips -->
      <div class="d-flex flex-wrap ga-2 mb-4">
        <v-chip
          v-for="f in allFilters"
          :key="f.value"
          :color="allFilter === f.value ? 'primary' : undefined"
          :variant="allFilter === f.value ? 'flat' : 'outlined'"
          size="small"
          @click="allFilter = f.value; loadAllWishes()"
        >
          {{ f.label }}
        </v-chip>
      </div>

      <v-progress-linear v-if="loadingAll" indeterminate color="primary" class="mb-2" />

      <div v-if="!loadingAll && allWishes.length === 0" class="text-center py-12">
        <v-icon icon="mdi-hand-heart-outline" size="64" color="grey-lighten-1" class="mb-3" />
        <div class="text-h6 text-medium-emphasis">Нет заявок</div>
      </div>

      <v-row v-else dense>
        <v-col v-for="wish in allWishes" :key="wish.id" cols="12" md="6" lg="4">
          <v-card variant="outlined" class="pa-3 h-100">
            <div class="d-flex align-start justify-space-between mb-2">
              <div class="flex-grow-1 mr-2">
                <div class="text-subtitle-1 font-weight-medium">{{ wish.title }}</div>
                <div class="text-caption text-medium-emphasis mt-0.5">
                  <v-icon icon="mdi-account" size="12" class="mr-1" />{{ wish.creator_name || 'Неизвестно' }}
                </div>
                <div v-if="wish.description" class="text-body-2 text-medium-emphasis mt-1" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">
                  {{ wish.description }}
                </div>
              </div>
              <v-chip :color="statusColor[wish.status]" size="small" variant="tonal">
                {{ statusLabel[wish.status] }}
              </v-chip>
            </div>

            <!-- Metadata -->
            <div class="d-flex flex-wrap ga-2 text-caption text-medium-emphasis mb-2">
              <span v-if="wish.quantity">Кол-во: <b>{{ wish.quantity }} {{ wish.unit || '' }}</b></span>
              <span v-if="wish.estimated_price">Цена: <b>{{ formatPrice(wish.estimated_price) }}</b></span>
            </div>

            <!-- Justification -->
            <div v-if="wish.justification" class="text-caption text-medium-emphasis mb-2">
              <b>Обоснование:</b> {{ wish.justification }}
            </div>

            <!-- Rejection reason -->
            <div v-if="wish.status === 'rejected' && wish.rejection_reason" class="text-caption text-error mt-1 mb-2">
              <v-icon icon="mdi-close-circle" size="14" class="mr-1" />
              Причина отказа: {{ wish.rejection_reason }}
            </div>

            <!-- Actions for submitted wishes -->
            <div v-if="wish.status === 'submitted'" class="d-flex ga-2 mt-2 flex-wrap">
              <v-btn
                size="small"
                variant="flat"
                color="success"
                prepend-icon="mdi-check"
                :loading="approvingId === wish.id"
                @click="approveWish(wish)"
              >
                Одобрить
              </v-btn>
              <v-btn
                size="small"
                variant="tonal"
                color="error"
                prepend-icon="mdi-close"
                @click="openRejectDialog(wish)"
              >
                Отклонить
              </v-btn>
            </div>

            <!-- Convert to purchase (admin+) -->
            <div v-if="wish.status === 'approved' && isAdmin" class="mt-2">
              <v-btn
                size="small"
                variant="flat"
                color="primary"
                prepend-icon="mdi-cart-plus"
                @click="openConvertDialog(wish)"
              >
                Создать закупку
              </v-btn>
            </div>
          </v-card>
        </v-col>
      </v-row>
    </div>

    <!-- ── CREATE/EDIT DIALOG ── -->
    <v-dialog v-model="wishDialog" max-width="600" scrollable>
      <v-card>
        <v-card-title class="pa-4 pb-2">
          {{ editingWish ? 'Редактировать заявку' : 'Новая заявка' }}
        </v-card-title>
        <v-card-text class="pa-4">
          <v-form ref="wishFormRef" @submit.prevent="saveWish">
            <v-text-field
              v-model="wishForm.title"
              label="Наименование *"
              :rules="[v => !!v || 'Обязательное поле']"
              variant="outlined"
              density="compact"
              class="mb-3"
            />
            <v-textarea
              v-model="wishForm.description"
              label="Описание"
              variant="outlined"
              density="compact"
              rows="3"
              class="mb-3"
            />
            <v-row dense class="mb-3">
              <v-col cols="6">
                <v-text-field
                  v-model.number="wishForm.quantity"
                  label="Количество"
                  type="number"
                  variant="outlined"
                  density="compact"
                  min="0"
                />
              </v-col>
              <v-col cols="6">
                <v-text-field
                  v-model="wishForm.unit"
                  label="Единица измерения"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
            </v-row>
            <v-text-field
              v-model.number="wishForm.estimated_price"
              label="Примерная стоимость (₽)"
              type="number"
              variant="outlined"
              density="compact"
              class="mb-3"
              min="0"
            />
            <v-textarea
              v-model="wishForm.justification"
              label="Обоснование"
              variant="outlined"
              density="compact"
              rows="3"
            />
          </v-form>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="wishDialog = false">Отмена</v-btn>
          <v-btn variant="flat" color="primary" :loading="savingWish" @click="saveWish">
            {{ editingWish ? 'Сохранить' : 'Создать' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── REJECT DIALOG ── -->
    <v-dialog v-model="rejectDialog" max-width="480">
      <v-card>
        <v-card-title class="pa-4 pb-2">Отклонить заявку</v-card-title>
        <v-card-text class="pa-4">
          <v-textarea
            v-model="rejectionReason"
            label="Причина отклонения *"
            variant="outlined"
            density="compact"
            rows="4"
            :rules="[v => !!v || 'Укажите причину']"
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="rejectDialog = false">Отмена</v-btn>
          <v-btn variant="flat" color="error" :loading="rejectingWish" :disabled="!rejectionReason.trim()" @click="rejectWish">
            Отклонить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── CONVERT DIALOG ── -->
    <v-dialog v-model="convertDialog" max-width="540">
      <v-card>
        <v-card-title class="pa-4 pb-2">Создать закупку из заявки</v-card-title>
        <v-card-text class="pa-4">
          <div class="mb-4 pa-3 bg-grey-lighten-4 rounded">
            <div class="text-subtitle-2 font-weight-bold mb-1">Исходная заявка</div>
            <div class="text-body-2">{{ convertingWish?.title }}</div>
            <div class="text-caption text-medium-emphasis mt-1">
              <span v-if="convertingWish?.quantity">Кол-во: {{ convertingWish.quantity }} {{ convertingWish.unit || '' }}</span>
              <span v-if="convertingWish?.estimated_price" class="ml-2">Цена: {{ formatPrice(convertingWish.estimated_price) }}</span>
            </div>
          </div>
          <v-row dense class="mb-3">
            <v-col cols="6">
              <v-text-field
                v-model.number="convertForm.approved_quantity"
                label="Утверждённое количество"
                type="number"
                variant="outlined"
                density="compact"
                min="0"
              />
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model.number="convertForm.approved_price"
                label="Утверждённая цена (₽)"
                type="number"
                variant="outlined"
                density="compact"
                min="0"
              />
            </v-col>
          </v-row>
          <v-select
            v-model="convertForm.subsidy_id"
            :items="subsidies"
            item-title="name"
            item-value="id"
            label="Субсидия (опционально)"
            variant="outlined"
            density="compact"
            clearable
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="convertDialog = false">Отмена</v-btn>
          <v-btn variant="flat" color="primary" :loading="convertingWishLoading" @click="convertWish">
            Создать закупку
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snackbar" :color="snackbarColor" timeout="3000" location="bottom right">
      {{ snackbarText }}
    </v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '@/api'

const router = useRouter()

interface Wish {
  id: number
  org_id: number
  title: string
  description?: string
  quantity?: number
  unit?: string
  estimated_price?: number
  justification?: string
  status: 'draft' | 'submitted' | 'approved' | 'rejected' | 'converted'
  rejection_reason?: string
  created_by: number
  creator_name?: string
  approved_by?: number
  approver_name?: string
  purchase_id?: number
  created_at: string
  updated_at: string
}

interface Subsidy {
  id: number
  name: string
}

// Role detection
const userRole = localStorage.getItem('user_role') || ''
const userId = Number(localStorage.getItem('user_id') || 0)

const ADMIN_ROLES = ['superadmin', 'account_owner', 'org_admin', 'admin']
const MANAGER_ROLES = ['superadmin', 'account_owner', 'org_admin', 'admin', 'manager']

const isAdmin = computed(() => ADMIN_ROLES.includes(userRole))
const isManagerOrAdmin = computed(() => MANAGER_ROLES.includes(userRole))

// Status display
const statusColor: Record<string, string> = {
  draft: 'grey',
  submitted: 'blue',
  approved: 'green',
  rejected: 'red',
  converted: 'purple',
}
const statusLabel: Record<string, string> = {
  draft: 'Черновик',
  submitted: 'Отправлена',
  approved: 'Одобрена',
  rejected: 'Отклонена',
  converted: 'Конвертирована',
}

// Tabs
const activeTab = ref('my')

// My wishes
const myWishes = ref<Wish[]>([])
const loading = ref(false)

// All wishes (manager/admin)
const allWishes = ref<Wish[]>([])
const loadingAll = ref(false)
const allFilter = ref('submitted')
const allFilters = [
  { value: 'all', label: 'Все' },
  { value: 'submitted', label: 'Отправленные' },
  { value: 'approved', label: 'Одобренные' },
  { value: 'rejected', label: 'Отклонённые' },
  { value: 'converted', label: 'Конвертированные' },
]

// Create/edit dialog
const wishDialog = ref(false)
const editingWish = ref<Wish | null>(null)
const wishFormRef = ref<any>(null)
const savingWish = ref(false)
const wishForm = ref({
  title: '',
  description: '',
  quantity: null as number | null,
  unit: '',
  estimated_price: null as number | null,
  justification: '',
})

// Submit
const submittingId = ref<number | null>(null)

// Delete
const deletingId = ref<number | null>(null)

// Reject dialog
const rejectDialog = ref(false)
const rejectingWish = ref(false)
const rejectionReason = ref('')
const rejectingWishItem = ref<Wish | null>(null)

// Convert dialog
const convertDialog = ref(false)
const convertingWishLoading = ref(false)
const convertingWish = ref<Wish | null>(null)
const convertForm = ref({
  approved_quantity: null as number | null,
  approved_price: null as number | null,
  subsidy_id: null as number | null,
})
const subsidies = ref<Subsidy[]>([])

// Approve
const approvingId = ref<number | null>(null)

// Snackbar
const snackbar = ref(false)
const snackbarText = ref('')
const snackbarColor = ref('success')

function showSnack(text: string, color = 'success') {
  snackbarText.value = text
  snackbarColor.value = color
  snackbar.value = true
}

function formatPrice(price: number) {
  return price.toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 })
}

async function loadWishes() {
  loading.value = true
  try {
    myWishes.value = await apiFetch<Wish[]>('/wishes?mine_only=true')
  } catch (e) {
    showSnack('Ошибка загрузки заявок', 'error')
  } finally {
    loading.value = false
  }
}

async function loadAllWishes() {
  loadingAll.value = true
  try {
    const params = allFilter.value === 'all' ? '' : `?status=${allFilter.value}`
    allWishes.value = await apiFetch<Wish[]>(`/wishes${params}`)
  } catch (e) {
    showSnack('Ошибка загрузки заявок', 'error')
  } finally {
    loadingAll.value = false
  }
}

async function loadSubsidies() {
  try {
    subsidies.value = await apiFetch<Subsidy[]>('/subsidies/')
  } catch {}
}

function openCreateDialog() {
  editingWish.value = null
  wishForm.value = { title: '', description: '', quantity: null, unit: '', estimated_price: null, justification: '' }
  wishDialog.value = true
}

function openEditDialog(wish: Wish) {
  editingWish.value = wish
  wishForm.value = {
    title: wish.title,
    description: wish.description || '',
    quantity: wish.quantity ?? null,
    unit: wish.unit || '',
    estimated_price: wish.estimated_price ?? null,
    justification: wish.justification || '',
  }
  wishDialog.value = true
}

async function saveWish() {
  const { valid } = await wishFormRef.value?.validate()
  if (!valid) return
  savingWish.value = true
  try {
    const body = {
      title: wishForm.value.title,
      description: wishForm.value.description || undefined,
      quantity: wishForm.value.quantity ?? undefined,
      unit: wishForm.value.unit || undefined,
      estimated_price: wishForm.value.estimated_price ?? undefined,
      justification: wishForm.value.justification || undefined,
    }
    if (editingWish.value) {
      await apiFetch(`/wishes/${editingWish.value.id}`, { method: 'PUT', body: JSON.stringify(body) })
      showSnack('Заявка обновлена')
    } else {
      await apiFetch('/wishes', { method: 'POST', body: JSON.stringify(body) })
      showSnack('Заявка создана')
    }
    wishDialog.value = false
    await loadWishes()
  } catch (e) {
    showSnack('Ошибка при сохранении', 'error')
  } finally {
    savingWish.value = false
  }
}

async function submitWish(wish: Wish) {
  submittingId.value = wish.id
  try {
    await apiFetch(`/wishes/${wish.id}/submit`, { method: 'POST' })
    showSnack('Заявка отправлена')
    await loadWishes()
  } catch (e) {
    showSnack('Ошибка при отправке', 'error')
  } finally {
    submittingId.value = null
  }
}

async function deleteWish(wish: Wish) {
  deletingId.value = wish.id
  try {
    await apiFetch(`/wishes/${wish.id}`, { method: 'DELETE' })
    showSnack('Заявка удалена')
    await loadWishes()
  } catch (e) {
    showSnack('Ошибка при удалении', 'error')
  } finally {
    deletingId.value = null
  }
}

async function approveWish(wish: Wish) {
  approvingId.value = wish.id
  try {
    await apiFetch(`/wishes/${wish.id}/approve`, { method: 'POST' })
    showSnack('Заявка одобрена')
    await loadAllWishes()
  } catch (e) {
    showSnack('Ошибка при одобрении', 'error')
  } finally {
    approvingId.value = null
  }
}

function openRejectDialog(wish: Wish) {
  rejectingWishItem.value = wish
  rejectionReason.value = ''
  rejectDialog.value = true
}

async function rejectWish() {
  if (!rejectionReason.value.trim() || !rejectingWishItem.value) return
  rejectingWish.value = true
  try {
    await apiFetch(`/wishes/${rejectingWishItem.value.id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ rejection_reason: rejectionReason.value }),
    })
    showSnack('Заявка отклонена')
    rejectDialog.value = false
    await loadAllWishes()
  } catch (e) {
    showSnack('Ошибка при отклонении', 'error')
  } finally {
    rejectingWish.value = false
  }
}

function openConvertDialog(wish: Wish) {
  convertingWish.value = wish
  convertForm.value = {
    approved_quantity: wish.quantity ?? null,
    approved_price: wish.estimated_price ?? null,
    subsidy_id: null,
  }
  convertDialog.value = true
  loadSubsidies()
}

async function convertWish() {
  if (!convertingWish.value) return
  convertingWishLoading.value = true
  try {
    const body: any = {}
    if (convertForm.value.approved_quantity != null) body.approved_quantity = convertForm.value.approved_quantity
    if (convertForm.value.approved_price != null) body.approved_price = convertForm.value.approved_price
    if (convertForm.value.subsidy_id != null) body.subsidy_id = convertForm.value.subsidy_id
    const result = await apiFetch<{ wish_id: number; purchase_id: number; status: string }>(
      `/wishes/${convertingWish.value.id}/convert`,
      { method: 'POST', body: JSON.stringify(body) }
    )
    showSnack('Закупка создана')
    convertDialog.value = false
    await loadAllWishes()
    router.push(`/orders/${result.purchase_id}/edit`)
  } catch (e) {
    showSnack('Ошибка при создании закупки', 'error')
  } finally {
    convertingWishLoading.value = false
  }
}

onMounted(async () => {
  await loadWishes()
  if (isManagerOrAdmin.value) {
    await loadAllWishes()
  }
})
</script>
