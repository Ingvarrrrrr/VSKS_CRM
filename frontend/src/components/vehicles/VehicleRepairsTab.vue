<template>
  <div class="vehicle-repairs-tab">
    <!-- Header -->
    <div class="d-flex align-center mb-4">
      <span class="text-h6">Ремонты</span>
      <v-spacer />
      <v-btn
        color="primary"
        prepend-icon="mdi-plus"
        variant="tonal"
        @click="openCreateDialog"
      >
        Добавить ремонт
      </v-btn>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="d-flex justify-center py-8">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- Empty state -->
    <v-alert
      v-else-if="repairs.length === 0"
      type="info"
      variant="tonal"
      text="Ремонты не зарегистрированы"
    />

    <!-- Timeline -->
    <v-timeline v-else side="end" density="compact" line-inset="8">
      <v-timeline-item
        v-for="repair in repairs"
        :key="repair.id"
        :dot-color="statusColor(repair.status)"
        size="small"
      >
        <template #opposite>
          <span class="text-caption text-medium-emphasis">{{ formatDate(repair.date) }}</span>
        </template>

        <v-card variant="outlined" class="repair-card">
          <v-card-title
            class="d-flex align-center flex-wrap gap-2 py-2 px-3"
            style="cursor: pointer"
            @click="toggleExpand(repair.id)"
          >
            <span class="text-body-1 font-weight-medium flex-grow-1" style="min-width: 0; white-space: normal">
              {{ repair.description_short }}
            </span>
            <div class="d-flex align-center gap-2 flex-shrink-0">
              <!-- Status inline-edit -->
              <v-select
                v-model="repair.status"
                :items="statusItems"
                item-title="label"
                item-value="value"
                density="compact"
                variant="plain"
                hide-details
                style="max-width: 130px; min-width: 100px"
                @update:model-value="patchStatus(repair)"
                @click.stop
              >
                <template #selection="{ item }">
                  <v-chip :color="statusColor(item.value)" size="x-small" label>{{ item.title }}</v-chip>
                </template>
              </v-select>
              <span v-if="repair.cost_amount" class="text-body-2 text-medium-emphasis">
                {{ formatMoney(repair.cost_amount) }} ₽
              </span>
              <v-icon size="18" :icon="expandedIds.has(repair.id) ? 'mdi-chevron-up' : 'mdi-chevron-down'" />
            </div>
          </v-card-title>

          <v-expand-transition>
            <div v-if="expandedIds.has(repair.id)">
              <v-divider />
              <v-card-text class="pt-3">
                <!-- Full description -->
                <div v-if="repair.description" class="mb-3">
                  <div class="text-caption text-medium-emphasis mb-1">Описание</div>
                  <div class="text-body-2" style="white-space: pre-wrap">{{ repair.description }}</div>
                </div>

                <!-- Details row -->
                <v-row dense class="mb-2">
                  <v-col v-if="repair.mileage_at_repair" cols="12" sm="6">
                    <div class="text-caption text-medium-emphasis">Пробег</div>
                    <div class="text-body-2">{{ repair.mileage_at_repair.toLocaleString('ru') }} км</div>
                  </v-col>
                  <v-col v-if="repair.performed_by_name" cols="12" sm="6">
                    <div class="text-caption text-medium-emphasis">Исполнитель</div>
                    <div class="text-body-2">{{ repair.performed_by_name }}</div>
                  </v-col>
                  <v-col v-if="repair.purchase_id" cols="12" sm="6">
                    <div class="text-caption text-medium-emphasis">Связанная закупка</div>
                    <router-link
                      :to="`/purchases/${repair.purchase_id}`"
                      class="text-body-2 text-primary"
                      @click.stop
                    >
                      #{{ repair.purchase_id }}
                    </router-link>
                  </v-col>
                </v-row>

                <!-- Attachments by kind -->
                <v-divider class="mb-3" />
                <div class="text-subtitle-2 mb-2">Документы ремонта</div>
                <v-row dense>
                  <v-col
                    v-for="slot in attachmentSlots"
                    :key="slot.kind"
                    cols="12"
                    sm="6"
                    md="4"
                  >
                    <v-card variant="tonal" class="pa-2">
                      <RepairAttachmentSlot
                        :repair-id="repair.id"
                        :kind="slot.kind"
                        :label="slot.label"
                        :attachments="attachmentsByKind(repair, slot.kind)"
                        @uploaded="onAttachmentUploaded(repair, $event)"
                        @deleted="onAttachmentDeleted(repair, $event)"
                      />
                    </v-card>
                  </v-col>
                </v-row>

                <!-- Actions -->
                <div class="d-flex justify-end mt-3 gap-2">
                  <v-btn
                    size="small"
                    variant="text"
                    prepend-icon="mdi-pencil"
                    @click="openEditDialog(repair)"
                  >
                    Редактировать
                  </v-btn>
                  <v-btn
                    size="small"
                    variant="text"
                    color="error"
                    prepend-icon="mdi-delete"
                    @click="confirmDelete(repair)"
                  >
                    Удалить
                  </v-btn>
                </div>
              </v-card-text>
            </div>
          </v-expand-transition>
        </v-card>
      </v-timeline-item>
    </v-timeline>

    <!-- Create / Edit dialog -->
    <v-dialog v-model="formDialog" max-width="560" persistent>
      <v-card>
        <v-card-title>{{ editingRepair ? 'Редактировать ремонт' : 'Новый ремонт' }}</v-card-title>
        <v-card-text>
          <v-form ref="formRef" @submit.prevent="submitForm">
            <v-row dense>
              <v-col cols="12" sm="6">
                <v-text-field
                  v-model="form.date"
                  label="Дата *"
                  type="date"
                  :rules="[v => !!v || 'Укажите дату']"
                  required
                />
              </v-col>
              <v-col cols="12" sm="6">
                <v-select
                  v-model="form.status"
                  :items="statusItems"
                  item-title="label"
                  item-value="value"
                  label="Статус *"
                  :rules="[v => !!v || 'Укажите статус']"
                  required
                />
              </v-col>
              <v-col cols="12">
                <v-textarea
                  v-model="form.description"
                  label="Описание *"
                  rows="3"
                  :rules="[v => !!v || 'Укажите описание']"
                  required
                />
              </v-col>
              <v-col cols="12" sm="6">
                <v-text-field
                  v-model.number="form.cost_amount"
                  label="Стоимость (₽)"
                  type="number"
                  min="0"
                  step="0.01"
                />
              </v-col>
              <v-col cols="12" sm="6">
                <v-text-field
                  v-model.number="form.mileage_at_repair"
                  label="Пробег (км)"
                  type="number"
                  min="0"
                />
              </v-col>
              <v-col cols="12">
                <v-text-field
                  v-model="form.performed_by_name"
                  label="Исполнитель"
                />
              </v-col>
              <v-col cols="12">
                <v-autocomplete
                  v-model="form.purchase_id"
                  :items="purchaseItems"
                  item-title="label"
                  item-value="id"
                  label="Связанная закупка (необязательно)"
                  clearable
                  :loading="purchasesLoading"
                  @update:search="searchPurchases"
                />
              </v-col>
            </v-row>
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="closeFormDialog">Отмена</v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            :loading="submitting"
            @click="submitForm"
          >
            {{ editingRepair ? 'Сохранить' : 'Создать' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete confirmation dialog -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title>Удалить ремонт?</v-card-title>
        <v-card-text>
          Запись от {{ pendingDeleteRepair ? formatDate(pendingDeleteRepair.date) : '' }} будет удалена.
          Все прикреплённые файлы также будут удалены.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" variant="tonal" :loading="deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import RepairAttachmentSlot from './RepairAttachmentSlot.vue'

interface RepairAttachment {
  id: number
  repair_id: number
  kind: string
  name: string
  mime: string | null
  size: number | null
  sha256: string | null
  uploaded_at: string
  uploaded_by_id: number | null
}

interface VehicleRepair {
  id: number
  vehicle_id: number
  date: string
  description: string
  cost_amount: number | null
  performed_by_name: string | null
  mileage_at_repair: number | null
  status: string
  purchase_id: number | null
  attachments: RepairAttachment[]
}

interface PurchaseItem {
  id: number
  label: string
}

const props = defineProps<{
  vehicleId: number
}>()

const { success, error: toastError } = useToast()

const repairs = ref<VehicleRepair[]>([])
const loading = ref(false)
const expandedIds = ref<Set<number>>(new Set())
const formDialog = ref(false)
const deleteDialog = ref(false)
const deleting = ref(false)
const submitting = ref(false)
const formRef = ref()
const editingRepair = ref<VehicleRepair | null>(null)
const pendingDeleteRepair = ref<VehicleRepair | null>(null)
const purchasesLoading = ref(false)
const purchaseItems = ref<PurchaseItem[]>([])

const statusItems = [
  { value: 'planned', label: 'Запланирован' },
  { value: 'in_progress', label: 'В работе' },
  { value: 'done', label: 'Выполнен' },
  { value: 'cancelled', label: 'Отменён' },
]

const attachmentSlots = [
  { kind: 'order_form', label: 'Заказ-наряд' },
  { kind: 'act', label: 'Акт' },
  { kind: 'invoice', label: 'Счёт' },
  { kind: 'photo', label: 'Фото' },
  { kind: 'other', label: 'Прочее' },
]

const form = reactive({
  date: '',
  description: '',
  cost_amount: null as number | null,
  status: 'planned',
  mileage_at_repair: null as number | null,
  performed_by_name: '',
  purchase_id: null as number | null,
})

// Computed short description for timeline header
const repairsWithShort = computed(() => {
  return repairs.value
})

async function loadRepairs() {
  loading.value = true
  try {
    const data = await apiFetch<VehicleRepair[]>(
      `/api/vehicle-repairs?vehicle_id=${props.vehicleId}`
    )
    repairs.value = data
  } catch (err: any) {
    const msg = err?.payload?.message ?? err?.message ?? 'Ошибка загрузки ремонтов'
    toastError(msg, 0)
  } finally {
    loading.value = false
  }
}

function toggleExpand(id: number) {
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id)
  } else {
    expandedIds.value.add(id)
  }
  // trigger reactivity
  expandedIds.value = new Set(expandedIds.value)
}

function statusColor(status: string): string {
  const map: Record<string, string> = {
    planned: 'blue',
    in_progress: 'orange',
    done: 'green',
    cancelled: 'grey',
  }
  return map[status] ?? 'grey'
}

function formatDate(dateStr: string): string {
  if (!dateStr) return ''
  try {
    return new Date(dateStr).toLocaleDateString('ru-RU')
  } catch {
    return dateStr
  }
}

function formatMoney(val: number | null): string {
  if (val == null) return ''
  return val.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

function attachmentsByKind(repair: VehicleRepair, kind: string): RepairAttachment[] {
  return (repair.attachments ?? []).filter(a => a.kind === kind)
}

// Extend VehicleRepair with description_short computed property
Object.defineProperty(Object.prototype, 'description_short', {
  get() {
    if (typeof this.description !== 'string') return ''
    return this.description.length > 80
      ? this.description.slice(0, 77) + '...'
      : this.description
  },
  configurable: true,
  enumerable: false,
})

function openCreateDialog() {
  editingRepair.value = null
  form.date = new Date().toISOString().slice(0, 10)
  form.description = ''
  form.cost_amount = null
  form.status = 'planned'
  form.mileage_at_repair = null
  form.performed_by_name = ''
  form.purchase_id = null
  formDialog.value = true
}

function openEditDialog(repair: VehicleRepair) {
  editingRepair.value = repair
  form.date = repair.date
  form.description = repair.description
  form.cost_amount = repair.cost_amount
  form.status = repair.status
  form.mileage_at_repair = repair.mileage_at_repair
  form.performed_by_name = repair.performed_by_name ?? ''
  form.purchase_id = repair.purchase_id
  formDialog.value = true
}

function closeFormDialog() {
  formDialog.value = false
  editingRepair.value = null
}

async function submitForm() {
  const { valid } = await formRef.value?.validate() ?? { valid: false }
  if (!valid) return

  submitting.value = true
  try {
    const payload = {
      vehicle_id: props.vehicleId,
      date: form.date,
      description: form.description,
      cost_amount: form.cost_amount ?? null,
      status: form.status,
      mileage_at_repair: form.mileage_at_repair ?? null,
      performed_by_name: form.performed_by_name || null,
      purchase_id: form.purchase_id ?? null,
    }

    if (editingRepair.value) {
      const updated = await apiFetch<VehicleRepair>(
        `/api/vehicle-repairs/${editingRepair.value.id}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        }
      )
      const idx = repairs.value.findIndex(r => r.id === editingRepair.value!.id)
      if (idx !== -1) {
        repairs.value[idx] = { ...updated, attachments: repairs.value[idx].attachments }
      }
      success('Ремонт обновлён')
    } else {
      const created = await apiFetch<VehicleRepair>('/api/vehicle-repairs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      repairs.value.unshift({ ...created, attachments: [] })
      success('Ремонт добавлен')
    }
    closeFormDialog()
  } catch (err: any) {
    const msg = err?.payload?.message ?? err?.message ?? 'Ошибка сохранения'
    toastError(msg, 0)
  } finally {
    submitting.value = false
  }
}

async function patchStatus(repair: VehicleRepair) {
  try {
    await apiFetch(`/api/vehicle-repairs/${repair.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: repair.status }),
    })
    success('Статус обновлён')
  } catch (err: any) {
    const msg = err?.payload?.message ?? err?.message ?? 'Ошибка обновления статуса'
    toastError(msg, 0)
    await loadRepairs()
  }
}

function confirmDelete(repair: VehicleRepair) {
  pendingDeleteRepair.value = repair
  deleteDialog.value = true
}

async function doDelete() {
  if (!pendingDeleteRepair.value) return
  deleting.value = true
  try {
    await apiFetch(`/api/vehicle-repairs/${pendingDeleteRepair.value.id}`, { method: 'DELETE' })
    repairs.value = repairs.value.filter(r => r.id !== pendingDeleteRepair.value!.id)
    deleteDialog.value = false
    success('Ремонт удалён')
  } catch (err: any) {
    const msg = err?.payload?.message ?? err?.message ?? 'Ошибка удаления'
    toastError(msg, 0)
  } finally {
    deleting.value = false
    pendingDeleteRepair.value = null
  }
}

function onAttachmentUploaded(repair: VehicleRepair, att: RepairAttachment) {
  if (!repair.attachments) repair.attachments = []
  repair.attachments.push(att)
}

function onAttachmentDeleted(repair: VehicleRepair, id: number) {
  repair.attachments = (repair.attachments ?? []).filter(a => a.id !== id)
}

let purchaseSearchTimeout: ReturnType<typeof setTimeout> | null = null

function searchPurchases(q: string) {
  if (purchaseSearchTimeout) clearTimeout(purchaseSearchTimeout)
  if (!q || q.length < 2) return
  purchaseSearchTimeout = setTimeout(async () => {
    purchasesLoading.value = true
    try {
      const data = await apiFetch<any[]>(`/api/purchases?search=${encodeURIComponent(q)}&limit=20`)
      purchaseItems.value = data.map(p => ({
        id: p.id,
        label: `#${p.id} — ${p.subject ?? p.title ?? ''}`,
      }))
    } catch {
      // ignore search errors
    } finally {
      purchasesLoading.value = false
    }
  }, 350)
}

onMounted(() => {
  loadRepairs()
})
</script>

<style scoped>
.vehicle-repairs-tab {
  padding: 4px 0;
}
.repair-card {
  width: 100%;
}
</style>
