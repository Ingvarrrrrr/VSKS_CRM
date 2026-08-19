<template>
  <div class="expcodes-page">
    <!-- ── Header ── -->
    <div class="page-header">
      <div class="page-header-left">
        <v-icon icon="mdi-format-list-numbered" size="32" color="#3B82F6" class="mr-3" />
        <div>
          <div class="page-title">Коды расходов</div>
          <div class="page-subtitle">Справочник кодов направления расходования целевых средств (КРЦС)</div>
        </div>
      </div>
      <div class="page-header-right">
        <v-text-field
          v-model="search"
          prepend-inner-icon="mdi-magnify"
          placeholder="Поиск по коду или наименованию..."
          variant="outlined"
          density="compact"
          hide-details
          clearable
          style="max-width:280px"
          class="mr-3"
        />
        <v-checkbox
          v-model="showInactive"
          label="Показать неактивные"
          density="compact"
          hide-details
          class="mr-3"
          @update:model-value="load"
        />
        <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="openAddDialog">
          Добавить
        </v-btn>
      </div>
    </div>

    <div v-if="loading" class="d-flex justify-center py-16">
      <v-progress-circular indeterminate color="primary" size="52" />
    </div>

    <template v-else>
      <div v-if="filtered.length === 0" class="empty-state">
        <v-icon icon="mdi-format-list-numbered" size="64" color="grey-lighten-2" />
        <div class="text-h6 text-medium-emphasis mt-3">Коды не найдены</div>
      </div>

      <div v-else class="ec-table-wrap">
        <table class="ec-table">
          <thead>
            <tr>
              <th class="ec-th ec-th-code">Код</th>
              <th class="ec-th">Наименование</th>
              <th class="ec-th ec-th-kind">Тип</th>
              <th class="ec-th ec-th-flag">Закупки</th>
              <th class="ec-th ec-th-flag">Активен</th>
              <th class="ec-th ec-th-actions"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in filtered" :key="c.code" class="ec-tr" :class="{ 'ec-tr--group': !c.parent_code }">
              <td class="ec-td ec-td-code">
                <span :class="{ 'font-weight-bold': !c.parent_code }">{{ c.code }}</span>
              </td>
              <td class="ec-td">{{ c.name }}</td>
              <td class="ec-td">
                <v-chip v-if="c.kind" size="x-small" variant="tonal" :color="kindColor(c.kind)">{{ kindLabel(c.kind) }}</v-chip>
                <span v-else class="ec-empty-hint">—</span>
              </td>
              <td class="ec-td ec-td-flag">
                <v-icon v-if="c.is_procurement" icon="mdi-check" color="success" size="18" />
              </td>
              <td class="ec-td ec-td-flag">
                <v-icon v-if="c.is_active" icon="mdi-check" color="success" size="18" />
                <v-icon v-else icon="mdi-close" color="grey" size="18" />
              </td>
              <td class="ec-td ec-td-actions">
                <v-btn icon="mdi-pencil-outline" variant="text" size="small" color="secondary"
                  title="Редактировать" @click="openEditDialog(c)" />
                <v-btn v-if="c.is_active" icon="mdi-delete-outline" variant="text" size="small" color="error"
                  title="Деактивировать" @click="openDeleteDialog(c)" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- ── Диалог добавления ── -->
    <v-dialog v-model="addDialog" max-width="560" :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-5 pb-2">Добавить код расходов</v-card-title>
        <v-card-text class="pa-5 pt-2">
          <v-form ref="addFormRef">
            <v-row dense>
              <v-col cols="6">
                <v-text-field v-model="addForm.code" label="Код *" variant="outlined" density="compact"
                  hint="Напр. 0200 или 0200032" persistent-hint
                  :rules="[r => !!r || 'Обязательное поле']" />
              </v-col>
              <v-col cols="6">
                <v-text-field v-model="addForm.parent_code" label="Укрупнённый код" variant="outlined" density="compact"
                  hint="Оставьте пустым для укрупнённого кода" persistent-hint />
              </v-col>
              <v-col cols="12">
                <v-text-field v-model="addForm.name" label="Наименование *" variant="outlined" density="compact"
                  :rules="[r => !!r || 'Обязательное поле']" />
              </v-col>
              <v-col cols="6">
                <v-select v-model="addForm.kind" :items="KIND_OPTIONS" item-title="label" item-value="value"
                  label="Тип" variant="outlined" density="compact" clearable />
              </v-col>
              <v-col cols="6" class="d-flex align-center">
                <v-checkbox v-model="addForm.is_procurement" label="Относится к закупкам" density="compact" hide-details />
              </v-col>
            </v-row>
          </v-form>
          <v-alert v-if="dialogError" type="error" class="mt-3" density="compact">{{ dialogError }}</v-alert>
        </v-card-text>
        <v-card-actions class="pa-5 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="addDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="dialogLoading" @click="submitAdd">Добавить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Диалог редактирования ── -->
    <v-dialog v-model="editDialog" max-width="560" :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-5 pb-2">Редактировать код {{ editTarget?.code }}</v-card-title>
        <v-card-text class="pa-5 pt-2">
          <v-form ref="editFormRef">
            <v-row dense>
              <v-col cols="6">
                <v-text-field v-model="editForm.parent_code" label="Укрупнённый код" variant="outlined" density="compact" />
              </v-col>
              <v-col cols="12">
                <v-text-field v-model="editForm.name" label="Наименование *" variant="outlined" density="compact"
                  :rules="[r => !!r || 'Обязательное поле']" />
              </v-col>
              <v-col cols="6">
                <v-select v-model="editForm.kind" :items="KIND_OPTIONS" item-title="label" item-value="value"
                  label="Тип" variant="outlined" density="compact" clearable />
              </v-col>
              <v-col cols="6" class="d-flex align-center">
                <v-checkbox v-model="editForm.is_procurement" label="Относится к закупкам" density="compact" hide-details />
              </v-col>
              <v-col cols="12">
                <v-checkbox v-model="editForm.is_active" label="Активен" density="compact" hide-details />
              </v-col>
            </v-row>
          </v-form>
          <v-alert v-if="dialogError" type="error" class="mt-3" density="compact">{{ dialogError }}</v-alert>
        </v-card-text>
        <v-card-actions class="pa-5 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="editDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="dialogLoading" @click="submitEdit">Сохранить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Диалог удаления ── -->
    <v-dialog v-model="deleteDialog" max-width="440">
      <v-card>
        <v-card-title class="pa-5 pb-2 text-error">Деактивировать код?</v-card-title>
        <v-card-text class="pa-5 pt-2">
          <div class="mb-2">«{{ deleteTarget?.code }} — {{ deleteTarget?.name }}»</div>
          <v-alert v-if="dialogError" type="error" density="compact">{{ dialogError }}</v-alert>
        </v-card-text>
        <v-card-actions class="pa-5 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" variant="flat" :loading="dialogLoading" @click="submitDelete">Деактивировать</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'

const { mobile } = useDisplay()
const toast = useToast()

interface ExpenseCode {
  code: string
  parent_code: string | null
  name: string
  kind: string | null
  is_procurement: boolean
  is_active: boolean
}

const KIND_OPTIONS = [
  { value: 'товар', label: 'Товар' },
  { value: 'услуга', label: 'Услуга' },
  { value: 'работа', label: 'Работа' },
  { value: 'персонал', label: 'Персонал' },
  { value: 'налог', label: 'Налог' },
  { value: 'аванс', label: 'Аванс' },
  { value: 'командировка', label: 'Командировка' },
  { value: 'накладные', label: 'Накладные' },
  { value: 'прочее', label: 'Прочее' },
]
const KIND_COLORS: Record<string, string> = {
  товар: 'blue', услуга: 'teal', работа: 'indigo', персонал: 'purple',
  налог: 'red', аванс: 'orange', командировка: 'amber', накладные: 'brown', прочее: 'grey',
}
const kindLabel = (v: string) => KIND_OPTIONS.find(k => k.value === v)?.label ?? v
const kindColor = (v: string) => KIND_COLORS[v] ?? 'grey'

const codes = ref<ExpenseCode[]>([])
const loading = ref(false)
const search = ref('')
const showInactive = ref(false)

const dialogError = ref('')
const dialogLoading = ref(false)

const addDialog = ref(false)
const addFormRef = ref()
const addForm = reactive({ code: '', parent_code: '', name: '', kind: null as string | null, is_procurement: false })

const editDialog = ref(false)
const editFormRef = ref()
const editTarget = ref<ExpenseCode | null>(null)
const editForm = reactive({ parent_code: '', name: '', kind: null as string | null, is_procurement: false, is_active: true })

const deleteDialog = ref(false)
const deleteTarget = ref<ExpenseCode | null>(null)

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return codes.value
  return codes.value.filter(c =>
    c.code.toLowerCase().includes(q) || c.name.toLowerCase().includes(q)
  )
})

const load = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (showInactive.value) params.set('include_inactive', 'true')
    codes.value = await apiFetch<ExpenseCode[]>(`/expense-codes?${params.toString()}`)
  } finally {
    loading.value = false
  }
}

const showSnack = (text: string, color: ToastType = 'success') => { toast.addToast(text, color) }

const openAddDialog = () => {
  addForm.code = ''; addForm.parent_code = ''; addForm.name = ''
  addForm.kind = null; addForm.is_procurement = false
  dialogError.value = ''; addDialog.value = true
}

const submitAdd = async () => {
  const { valid } = await addFormRef.value.validate()
  if (!valid) return
  dialogLoading.value = true; dialogError.value = ''
  try {
    await apiFetch('/expense-codes', {
      method: 'POST',
      body: JSON.stringify({
        code: addForm.code.trim(), parent_code: addForm.parent_code.trim() || null,
        name: addForm.name.trim(), kind: addForm.kind, is_procurement: addForm.is_procurement,
      }),
    })
    addDialog.value = false; showSnack('Код добавлен')
    await load()
  } catch (e: any) { dialogError.value = e.detail || 'Ошибка' }
  finally { dialogLoading.value = false }
}

const openEditDialog = (c: ExpenseCode) => {
  editTarget.value = c
  editForm.parent_code = c.parent_code ?? ''
  editForm.name = c.name
  editForm.kind = c.kind
  editForm.is_procurement = c.is_procurement
  editForm.is_active = c.is_active
  dialogError.value = ''; editDialog.value = true
}

const submitEdit = async () => {
  const { valid } = await editFormRef.value.validate()
  if (!valid || !editTarget.value) return
  dialogLoading.value = true; dialogError.value = ''
  try {
    await apiFetch(`/expense-codes/${encodeURIComponent(editTarget.value.code)}`, {
      method: 'PUT',
      body: JSON.stringify({
        parent_code: editForm.parent_code.trim() || null, name: editForm.name.trim(),
        kind: editForm.kind, is_procurement: editForm.is_procurement, is_active: editForm.is_active,
      }),
    })
    editDialog.value = false; showSnack('Сохранено')
    await load()
  } catch (e: any) { dialogError.value = e.detail || 'Ошибка' }
  finally { dialogLoading.value = false }
}

const openDeleteDialog = (c: ExpenseCode) => {
  deleteTarget.value = c; dialogError.value = ''; deleteDialog.value = true
}

const submitDelete = async () => {
  if (!deleteTarget.value) return
  dialogLoading.value = true; dialogError.value = ''
  try {
    await apiFetch(`/expense-codes/${encodeURIComponent(deleteTarget.value.code)}`, { method: 'DELETE' })
    deleteDialog.value = false; showSnack('Деактивирован')
    await load()
  } catch (e: any) { dialogError.value = e.detail || 'Ошибка деактивации' }
  finally { dialogLoading.value = false }
}

load()
</script>

<style scoped>
.expcodes-page { padding: 20px 24px; max-width: 1200px; }

.page-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 24px; flex-wrap: wrap; gap: 12px;
}
.page-header-left  { display: flex; align-items: center; }
.page-header-right { display: flex; align-items: center; flex-wrap: wrap; }
.page-title    { font-size: 26px; font-weight: 700; color: var(--crm-text); line-height: 1.2; }
.page-subtitle { font-size: 13px; color: var(--crm-text-muted); margin-top: 2px; }

.empty-state {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 64px 0; color: var(--crm-text-faint);
}

.ec-table-wrap {
  background: var(--crm-surface); border-radius: 12px;
  border: 1px solid var(--crm-border);
  box-shadow: 0 1px 4px var(--crm-shadow);
  overflow: hidden;
}
.ec-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
.ec-th {
  padding: 10px 12px; text-align: left; font-weight: 600;
  font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--crm-text-muted); border-bottom: 2px solid var(--crm-border);
  background: var(--crm-table-header);
}
.ec-th-code { width: 110px; }
.ec-th-kind { width: 140px; }
.ec-th-flag { width: 80px; text-align: center; }
.ec-th-actions { width: 90px; }
.ec-td { padding: 7px 12px; border-bottom: 1px solid var(--crm-border); vertical-align: middle; }
.ec-td-code { font-variant-numeric: tabular-nums; }
.ec-td-flag { text-align: center; }
.ec-td-actions { white-space: nowrap; }
.ec-tr:hover { background: var(--crm-surface-alt); }
.ec-tr--group { background: var(--crm-surface-alt); }
.ec-empty-hint { color: var(--crm-text-faint); }
</style>
