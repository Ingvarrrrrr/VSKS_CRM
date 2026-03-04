<template>
  <v-container>
    <v-row>
      <v-col cols="12">
        <v-card class="pa-6">
          <v-card-title class="text-h4 mb-6">
            <v-icon icon="mdi-account-group" class="mr-4" />Контрагенты
          </v-card-title>
          <div class="d-flex justify-space-between align-center mb-6">
            <v-text-field
              v-model="search"
              prepend-inner-icon="mdi-magnify"
              label="Поиск по названию или ИНН"
              variant="outlined"
              density="compact"
              hide-details
              style="max-width: 350px"
            />
            <v-btn color="primary" prepend-icon="mdi-plus" @click="openAdd">
              Добавить контрагента
            </v-btn>
          </div>
          <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />
          <v-alert v-if="error" type="error" class="mb-4">{{ error }}</v-alert>
          <v-table>
            <thead>
              <tr>
                <th>Наименование</th>
                <th>ИНН</th>
                <th>КПП</th>
                <th>Адрес</th>
                <th>Телефон / Email</th>
                <th>Контактное лицо</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!loading && filtered.length === 0">
                <td colspan="7" class="text-center py-8 text-medium-emphasis">Контрагенты не найдены</td>
              </tr>
              <tr v-for="c in filtered" :key="c.id">
                <td>{{ c.name }}</td>
                <td>{{ c.inn || '—' }}</td>
                <td>{{ c.kpp || '—' }}</td>
                <td>{{ c.address || '—' }}</td>
                <td>
                  <div>{{ c.phone || '—' }}</div>
                  <div class="text-caption text-medium-emphasis">{{ c.email || '' }}</div>
                </td>
                <td>{{ c.contact_person || '—' }}</td>
                <td>
                  <v-btn icon="mdi-pencil" variant="text" size="small" class="mr-1" @click="openEdit(c)" />
                  <v-btn icon="mdi-delete" variant="text" size="small" color="error" @click="confirmDelete(c)" />
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card>
      </v-col>
    </v-row>

    <v-dialog v-model="dialog" max-width="600" persistent>
      <v-card>
        <v-card-title class="pa-4">{{ editId ? 'Редактировать контрагента' : 'Добавить контрагента' }}</v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <v-form ref="formRef">
            <v-text-field
              v-model="form.name"
              label="Наименование организации *"
              variant="outlined"
              :rules="[v => !!v || 'Обязательное поле']"
              class="mb-3"
            />
            <v-row>
              <v-col cols="6"><v-text-field v-model="form.inn" label="ИНН" variant="outlined" /></v-col>
              <v-col cols="6"><v-text-field v-model="form.kpp" label="КПП" variant="outlined" /></v-col>
            </v-row>
            <v-textarea v-model="form.address" label="Адрес" variant="outlined" rows="2" class="mb-3" />
            <v-text-field v-model="form.contact_person" label="Контактное лицо" variant="outlined" class="mb-3" />
            <v-row>
              <v-col cols="6"><v-text-field v-model="form.phone" label="Телефон" variant="outlined" /></v-col>
              <v-col cols="6"><v-text-field v-model="form.email" label="Email" variant="outlined" /></v-col>
            </v-row>
          </v-form>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="saving" @click="save">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title class="pa-4">Удалить контрагента?</v-card-title>
        <v-card-text>{{ deleteTarget?.name }}</v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" :loading="saving" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack" :color="snackColor" timeout="3000">{{ snackMsg }}</v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiFetch } from '@/api'

interface Contractor {
  id: number
  name: string
  inn?: string
  kpp?: string
  address?: string
  contact_person?: string
  phone?: string
  email?: string
}

const contractors = ref<Contractor[]>([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const dialog = ref(false)
const deleteDialog = ref(false)
const saving = ref(false)
const editId = ref<number | null>(null)
const deleteTarget = ref<Contractor | null>(null)
const formRef = ref()
const snack = ref(false)
const snackMsg = ref('')
const snackColor = ref('success')

const emptyForm = () => ({ name: '', inn: '', kpp: '', address: '', contact_person: '', phone: '', email: '' })
const form = ref(emptyForm())

const filtered = computed(() => {
  const q = search.value.toLowerCase()
  if (!q) return contractors.value
  return contractors.value.filter(c =>
    c.name.toLowerCase().includes(q) || (c.inn || '').includes(q)
  )
})

const loadContractors = async () => {
  loading.value = true
  error.value = ''
  try {
    contractors.value = await apiFetch<Contractor[]>('/contractors/')
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

const openAdd = () => {
  editId.value = null
  form.value = emptyForm()
  dialog.value = true
}

const openEdit = (c: Contractor) => {
  editId.value = c.id
  form.value = {
    name: c.name,
    inn: c.inn || '',
    kpp: c.kpp || '',
    address: c.address || '',
    contact_person: c.contact_person || '',
    phone: c.phone || '',
    email: c.email || ''
  }
  dialog.value = true
}

const save = async () => {
  const { valid } = await formRef.value.validate()
  if (!valid) return
  saving.value = true
  try {
    if (editId.value) {
      const updated = await apiFetch<Contractor>('/contractors/' + editId.value, { method: 'PUT', body: form.value })
      const idx = contractors.value.findIndex(c => c.id === editId.value)
      if (idx >= 0) contractors.value[idx] = updated
    } else {
      const created = await apiFetch<Contractor>('/contractors/', { method: 'POST', body: form.value })
      contractors.value.push(created)
    }
    dialog.value = false
    showSnack(editId.value ? 'Контрагент обновлён' : 'Контрагент добавлен', 'success')
  } catch (e: any) {
    showSnack(e.message, 'error')
  } finally {
    saving.value = false
  }
}

const confirmDelete = (c: Contractor) => {
  deleteTarget.value = c
  deleteDialog.value = true
}

const doDelete = async () => {
  if (!deleteTarget.value) return
  saving.value = true
  try {
    await apiFetch('/contractors/' + deleteTarget.value.id, { method: 'DELETE' })
    contractors.value = contractors.value.filter(c => c.id !== deleteTarget.value!.id)
    deleteDialog.value = false
    showSnack('Контрагент удалён', 'success')
  } catch (e: any) {
    showSnack(e.message, 'error')
  } finally {
    saving.value = false
  }
}

const showSnack = (msg: string, color: string) => {
  snackMsg.value = msg
  snackColor.value = color
  snack.value = true
}

onMounted(loadContractors)
</script>
