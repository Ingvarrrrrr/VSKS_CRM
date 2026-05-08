<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">Поставщики</h1>
        <span class="text-body-2 text-medium-emphasis">{{ suppliers.length }} записей</span>
      </div>
      <v-spacer />
      <div class="d-flex gap-2">
        <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" @click="showColumnPicker = true">Колонки</v-btn>
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreate">Добавить поставщика</v-btn>
      </div>
    </div>

    <!-- Search -->
    <v-text-field
      v-model="search" prepend-inner-icon="mdi-magnify" label="Поиск по имени или ИНН"
      variant="outlined" density="compact" clearable hide-details class="mb-4" style="max-width:400px"
    />

    <!-- Table -->
    <v-card variant="outlined">
      <v-data-table
        :headers="visibleHeaders"
        :items="filteredSuppliers"
        :loading="loading"
        density="comfortable"
        item-value="id"
      >
        <template v-slot:item.products="{ item }">
          <v-chip v-for="p in item.products.slice(0, 3)" :key="p.id" size="x-small" variant="tonal" class="mr-1">
            {{ p.product_id }}
          </v-chip>
          <span v-if="item.products.length > 3" class="text-caption text-medium-emphasis">
            +{{ item.products.length - 3 }}
          </span>
          <span v-if="item.products.length === 0" class="text-caption text-medium-emphasis">—</span>
        </template>
        <template v-slot:item.actions="{ item }">
          <div class="d-flex gap-1">
            <v-btn icon="mdi-pencil" size="x-small" variant="text" @click="openEdit(item)" />
            <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error" @click="confirmDelete(item)" />
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Create/Edit dialog -->
    <v-dialog v-model="formDialog.show" max-width="560" scrollable>
      <v-card>
        <v-card-title class="pa-4 d-flex align-center">
          {{ formDialog.isEdit ? 'Редактировать поставщика' : 'Добавить поставщика' }}
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="formDialog.show = false" />
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-row>
            <v-col cols="12">
              <v-text-field v-model="formDialog.name" label="Наименование *" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="formDialog.inn" label="ИНН" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="formDialog.kpp" label="КПП" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="formDialog.contact" label="Контактное лицо" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="formDialog.phone" label="Телефон" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12">
              <v-text-field v-model="formDialog.email" label="Email" variant="outlined" density="compact" />
            </v-col>
            <v-col cols="12">
              <v-textarea v-model="formDialog.notes" label="Примечания" variant="outlined" density="compact" rows="3" />
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="formDialog.show = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="formDialog.saving" :disabled="!formDialog.name" @click="saveSupplier">
            {{ formDialog.isEdit ? 'Сохранить' : 'Создать' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete confirm -->
    <v-dialog v-model="deleteDialog.show" max-width="340">
      <v-card>
        <v-card-title class="pa-4">Удалить поставщика?</v-card-title>
        <v-card-text>{{ deleteDialog.item?.name }}</v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog.show = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="deleteDialog.deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack.show" :color="snack.color" timeout="3000">{{ snack.text }}</v-snackbar>

    <ColumnConfigDialog
      v-model="showColumnPicker"
      :all-columns="allColumns"
      :state="colState"
      :show-width="true"
      :toggle-visible="toggleVisible"
      :set-position="setPosition"
      :set-width="setWidth"
      :reset="resetColumns"
    />
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted } from 'vue'
import { apiFetch } from '@/api'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'
import ColumnConfigDialog from '@/components/ColumnConfigDialog.vue'

interface SupplierProduct { id: number; product_id?: number; price_notes?: string; source?: string }
interface Supplier { id: number; name: string; inn?: string; kpp?: string; contact?: string; phone?: string; email?: string; notes?: string; products: SupplierProduct[] }

const suppliers = ref<Supplier[]>([])
const loading = ref(false)
const search = ref('')

const snack = reactive({ show: false, text: '', color: 'success' })
const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }

const allColumns: ColumnDef[] = [
  { title: 'Наименование', key: 'name' },
  { title: 'ИНН', key: 'inn', width: 120 },
  { title: 'КПП', key: 'kpp', width: 120 },
  { title: 'Контакт', key: 'contact' },
  { title: 'Email', key: 'email' },
  { title: 'Телефон', key: 'phone' },
  { title: 'Товары', key: 'products', width: 120, sortable: false },
  { title: '', key: 'actions', width: 80, sortable: false },
]

const { state: colState, visibleHeaders, toggleVisible, setPosition, setWidth, reset: resetColumns } = useColumnConfig('suppliers', allColumns)
const showColumnPicker = ref(false)

const filteredSuppliers = computed(() => {
  if (!search.value) return suppliers.value
  const q = search.value.toLowerCase()
  return suppliers.value.filter(s =>
    s.name.toLowerCase().includes(q) || (s.inn || '').includes(q)
  )
})

const formDialog = reactive({
  show: false, isEdit: false, id: null as number | null,
  name: '', inn: '', kpp: '', contact: '', phone: '', email: '', notes: '', saving: false,
})

const deleteDialog = reactive({ show: false, item: null as Supplier | null, deleting: false })

function openCreate() {
  Object.assign(formDialog, { show: true, isEdit: false, id: null, name: '', inn: '', kpp: '', contact: '', phone: '', email: '', notes: '' })
}
function openEdit(s: Supplier) {
  Object.assign(formDialog, { show: true, isEdit: true, id: s.id, name: s.name, inn: s.inn || '', kpp: s.kpp || '', contact: s.contact || '', phone: s.phone || '', email: s.email || '', notes: s.notes || '' })
}
function confirmDelete(s: Supplier) { deleteDialog.item = s; deleteDialog.show = true }

async function loadSuppliers() {
  loading.value = true
  try {
    suppliers.value = await apiFetch<Supplier[]>('/suppliers/')
  } finally {
    loading.value = false
  }
}

async function saveSupplier() {
  formDialog.saving = true
  try {
    const body = {
      name: formDialog.name, inn: formDialog.inn || null, kpp: formDialog.kpp || null,
      contact: formDialog.contact || null, phone: formDialog.phone || null,
      email: formDialog.email || null, notes: formDialog.notes || null,
    }
    if (formDialog.isEdit) {
      const updated = await apiFetch<Supplier>(`/suppliers/${formDialog.id}`, { method: 'PUT', body })
      const idx = suppliers.value.findIndex(s => s.id === formDialog.id)
      if (idx >= 0) suppliers.value[idx] = updated
    } else {
      const created = await apiFetch<Supplier>('/suppliers/', { method: 'POST', body })
      suppliers.value = [created, ...suppliers.value]
    }
    formDialog.show = false
    showSnack('Поставщик сохранён')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка', 'error')
  } finally {
    formDialog.saving = false
  }
}

async function doDelete() {
  if (!deleteDialog.item) return
  deleteDialog.deleting = true
  try {
    await apiFetch(`/suppliers/${deleteDialog.item.id}`, { method: 'DELETE' })
    suppliers.value = suppliers.value.filter(s => s.id !== deleteDialog.item!.id)
    deleteDialog.show = false
    showSnack('Поставщик удалён')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка', 'error')
  } finally {
    deleteDialog.deleting = false
  }
}

onMounted(loadSuppliers)
</script>
