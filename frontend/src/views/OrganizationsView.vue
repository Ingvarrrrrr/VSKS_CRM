<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center mb-6 flex-wrap" style="gap:12px">
      <div>
        <h1 class="text-h5 font-weight-bold">Организации</h1>
        <span class="text-body-2 text-medium-emphasis">{{ orgs.length }} организаций</span>
      </div>
      <v-spacer />
      <v-text-field
        v-model="search"
        placeholder="Поиск по названию или ИНН..."
        prepend-inner-icon="mdi-magnify"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        style="max-width: 320px"
        @update:model-value="debouncedLoad"
      />
    </div>

    <v-card variant="outlined">
      <v-data-table
        v-resizable-columns="'organizations'"
        :headers="headers"
        :items="orgs"
        :loading="loading"
        :search="search"
        density="comfortable"
        item-value="id"
      >
        <template v-slot:item.is_active="{ item }">
          <v-chip :color="item.is_active ? 'success' : 'error'" size="small" variant="tonal">
            {{ item.is_active ? 'Активна' : 'Деактивирована' }}
          </v-chip>
        </template>
        <template v-slot:item.created_at="{ item }">
          <span class="text-caption">{{ formatDate(item.created_at) }}</span>
        </template>
        <template v-slot:item.actions="{ item }">
          <div class="d-flex gap-1">
            <v-btn
              icon="mdi-pencil-outline" size="x-small" variant="text" color="primary"
              title="Редактировать реквизиты"
              @click="openEditOrg(item)"
            />
            <v-btn
              :icon="item.is_active ? 'mdi-toggle-switch' : 'mdi-toggle-switch-off'"
              :color="item.is_active ? 'success' : 'grey'"
              size="x-small" variant="text"
              :title="item.is_active ? 'Деактивировать' : 'Активировать'"
              @click="toggleActive(item)"
            />
            <v-btn
              icon="mdi-delete-outline" size="x-small" variant="text" color="error"
              @click="confirmDelete(item)"
            />
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- Edit org dialog -->
    <v-dialog v-model="editOrgDialog" max-width="420">
      <v-card>
        <v-card-title class="pa-4">Реквизиты организации</v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-text-field v-model="editOrgItem.name" label="Название" variant="outlined" density="compact" class="mb-3" />
          <v-text-field
            v-model="editOrgItem.inn"
            label="ИНН"
            variant="outlined"
            density="compact"
            hint="10 цифр (юр. лицо) или 12 цифр (ИП)"
            persistent-hint
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="editOrgDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="editOrgSaving" @click="saveOrg">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete confirm -->
    <v-dialog v-model="deleteDialog.show" max-width="360">
      <v-card>
        <v-card-title class="pa-4">Удалить организацию?</v-card-title>
        <v-card-text>
          <strong>{{ deleteDialog.item?.name }}</strong><br>
          <span class="text-caption text-error">Будут удалены все данные организации: субсидии, закупки, пользователи.</span>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog.show = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="deleteDialog.deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack.show" :color="snack.color" timeout="3000">{{ snack.text }}</v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { apiFetch } from '@/api'

interface Org {
  id: number
  name: string
  inn?: string
  is_active: boolean
  created_at: string
  user_count: number
}

const orgs = ref<Org[]>([])
const loading = ref(false)
const search = ref('')

let debounceTimer: ReturnType<typeof setTimeout> | null = null
function debouncedLoad() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => loadOrgs(), 300)
}
const snack = reactive({ show: false, text: '', color: 'success' })
const showSnack = (text: string, color = 'success') => { snack.text = text; snack.color = color; snack.show = true }

const deleteDialog = reactive({ show: false, item: null as Org | null, deleting: false })

const editOrgDialog = ref(false)
const editOrgSaving = ref(false)
const editOrgItem = ref({ id: 0, name: '', inn: '' })

function openEditOrg(org: Org) {
  editOrgItem.value = { id: org.id, name: org.name, inn: org.inn || '' }
  editOrgDialog.value = true
}

async function saveOrg() {
  editOrgSaving.value = true
  try {
    await apiFetch(`/organizations/${editOrgItem.value.id}`, {
      method: 'PUT',
      body: { name: editOrgItem.value.name, inn: editOrgItem.value.inn || null }
    })
    editOrgDialog.value = false
    await loadOrgs()
    showSnack('Реквизиты сохранены')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка сохранения', 'error')
  } finally {
    editOrgSaving.value = false
  }
}

const headers = [
  { title: 'ID', key: 'id', width: 60 },
  { title: 'Название', key: 'name', minWidth: 200 },
  { title: 'ИНН', key: 'inn', width: 120 },
  { title: 'Пользователи', key: 'user_count', width: 120 },
  { title: 'Статус', key: 'is_active', width: 140 },
  { title: 'Создана', key: 'created_at', width: 160 },
  { title: '', key: 'actions', width: 80, sortable: false },
]

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('ru-RU')
}

async function loadOrgs() {
  loading.value = true
  try {
    orgs.value = await apiFetch<Org[]>('/organizations/')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка загрузки', 'error')
  } finally {
    loading.value = false
  }
}

async function toggleActive(org: Org) {
  try {
    const res = await apiFetch<{ id: number; is_active: boolean }>(`/organizations/${org.id}/toggle-active`, { method: 'PATCH' })
    const idx = orgs.value.findIndex(o => o.id === org.id)
    if (idx >= 0) orgs.value[idx].is_active = res.is_active
    showSnack(res.is_active ? 'Организация активирована' : 'Организация деактивирована')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка', 'error')
  }
}

function confirmDelete(org: Org) {
  deleteDialog.item = org
  deleteDialog.show = true
}

async function doDelete() {
  if (!deleteDialog.item) return
  deleteDialog.deleting = true
  try {
    await apiFetch(`/organizations/${deleteDialog.item.id}`, { method: 'DELETE' })
    orgs.value = orgs.value.filter(o => o.id !== deleteDialog.item!.id)
    deleteDialog.show = false
    showSnack('Организация удалена')
  } catch (e: any) {
    showSnack(e.message || 'Ошибка', 'error')
  } finally {
    deleteDialog.deleting = false
  }
}

onMounted(loadOrgs)
</script>
