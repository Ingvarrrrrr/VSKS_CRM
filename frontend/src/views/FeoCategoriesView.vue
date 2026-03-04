<template>
  <v-container>
    <v-row>
      <v-col cols="12">
        <v-card class="pa-6">
          <v-card-title class="text-h4 mb-6">
            <v-icon icon="mdi-folder-tree" class="mr-4" />Категории ФЭО
          </v-card-title>

          <div class="d-flex justify-space-between align-center mb-6">
            <v-card-subtitle class="text-h6">
              Управление категориями федеральных целевых программ
            </v-card-subtitle>
            <div>
              <v-btn color="primary" prepend-icon="mdi-plus" class="mr-4" @click="openAddDialog">
                Добавить категорию
              </v-btn>
              <v-btn variant="outlined" prepend-icon="mdi-file-import">
                Импорт
              </v-btn>
            </div>
          </div>

          <!-- Фильтры -->
          <v-row class="mb-4">
            <v-col cols="12" md="4">
              <v-select
                v-model="filterSubsidyId"
                :items="subsidies"
                item-title="name"
                item-value="id"
                label="Субсидия"
                variant="outlined"
                density="compact"
                clearable
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-select
                v-model="filterLevel"
                :items="[{value:1,title:'Уровень 1'},{value:2,title:'Уровень 2'},{value:3,title:'Уровень 3'}]"
                item-title="title"
                item-value="value"
                label="Уровень"
                variant="outlined"
                density="compact"
                clearable
              />
            </v-col>
          </v-row>

          <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />
          <v-alert v-if="error" type="error" class="mb-4">{{ error }}</v-alert>

          <v-table>
            <thead>
              <tr>
                <th>Код</th>
                <th>Наименование</th>
                <th>Уровень</th>
                <th>Приложение</th>
                <th>Субсидия</th>
                <th>Активна</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!loading && filteredCategories.length === 0">
                <td colspan="7" class="text-center py-8 text-medium-emphasis">Категории ФЭО не найдены</td>
              </tr>
              <tr v-for="category in filteredCategories" :key="category.id">
                <td>
                  <v-chip size="small" color="primary" variant="flat">
                    {{ category.code || '—' }}
                  </v-chip>
                </td>
                <td class="font-weight-medium">{{ category.name }}</td>
                <td>
                  <v-chip size="small" :color="getLevelColor(category.level)" variant="flat">
                    Уровень {{ category.level }}
                  </v-chip>
                </td>
                <td>{{ category.appendix || '—' }}</td>
                <td>{{ subsidyName(category.subsidy_id) }}</td>
                <td>
                  <v-chip size="small" :color="category.is_active ? 'success' : 'grey'" variant="flat">
                    {{ category.is_active ? 'Да' : 'Нет' }}
                  </v-chip>
                </td>
                <td>
                  <v-btn
                    icon="mdi-plus-circle-outline"
                    variant="text"
                    size="small"
                    color="primary"
                    class="mr-1"
                    title="Добавить дочернюю"
                    @click="openAddDialog(category.id)"
                  />
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card>
      </v-col>
    </v-row>

    <!-- Диалог добавления категории -->
    <v-dialog v-model="addDialog" max-width="600">
      <v-card>
        <v-card-title class="text-h6 pa-6 pb-2">
          {{ newCat.parent_id ? 'Добавить дочернюю категорию' : 'Добавить категорию' }}
        </v-card-title>
        <v-card-text class="pa-6 pt-2">
          <v-form ref="addFormRef" @submit.prevent="submitAdd">
            <v-row>
              <v-col cols="12">
                <v-text-field
                  v-model="newCat.name"
                  label="Наименование *"
                  variant="outlined"
                  density="compact"
                  :rules="[r => !!r || 'Обязательное поле']"
                />
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="newCat.code"
                  label="Код"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
              <v-col cols="12" md="6">
                <v-text-field
                  v-model="newCat.appendix"
                  label="Приложение"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
              <v-col cols="12" md="8">
                <v-select
                  v-model="newCat.subsidy_id"
                  :items="subsidies"
                  item-title="name"
                  item-value="id"
                  label="Субсидия *"
                  variant="outlined"
                  density="compact"
                  :rules="[r => !!r || 'Выберите субсидию']"
                />
              </v-col>
              <v-col cols="12" md="4">
                <v-select
                  v-model="newCat.parent_id"
                  :items="parentOptions"
                  item-title="label"
                  item-value="id"
                  label="Родительская категория"
                  variant="outlined"
                  density="compact"
                  clearable
                />
              </v-col>
              <v-col cols="12" md="4">
                <v-checkbox v-model="newCat.is_active" label="Активна" density="compact" />
              </v-col>
            </v-row>
          </v-form>
          <v-alert v-if="addError" type="error" class="mt-3" density="compact">{{ addError }}</v-alert>
        </v-card-text>
        <v-card-actions class="pa-6 pt-0">
          <v-spacer />
          <v-btn variant="outlined" @click="addDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="addLoading" @click="submitAdd">
            Добавить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3000" location="bottom right">
      {{ snack.text }}
    </v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { apiFetch } from '@/api'

interface FeoCategory {
  id: number
  code?: string
  name: string
  level: number
  appendix?: string
  subsidy_id: number
  parent_id?: number | null
  is_active: boolean
}

interface Subsidy { id: number; name: string }

const categories = ref<FeoCategory[]>([])
const subsidies = ref<Subsidy[]>([])
const loading = ref(false)
const error = ref('')
const filterSubsidyId = ref<number | null>(null)
const filterLevel = ref<number | null>(null)

const addDialog = ref(false)
const addLoading = ref(false)
const addError = ref('')
const addFormRef = ref()
const snack = reactive({ show: false, text: '', color: 'success' })

const newCat = reactive({
  name: '',
  code: '',
  appendix: '',
  subsidy_id: null as number | null,
  parent_id: null as number | null,
  is_active: true,
})

const filteredCategories = computed(() => {
  let list = categories.value
  if (filterSubsidyId.value) list = list.filter(c => c.subsidy_id === filterSubsidyId.value)
  if (filterLevel.value) list = list.filter(c => c.level === filterLevel.value)
  return list
})

const parentOptions = computed(() => {
  return categories.value
    .filter(c => c.level < 3)
    .map(c => ({ id: c.id, label: `[${c.level}] ${c.name}` }))
})

const subsidyName = (id: number) => subsidies.value.find(s => s.id === id)?.name ?? String(id)

const loadData = async () => {
  loading.value = true
  error.value = ''
  try {
    const [cats, subs] = await Promise.all([
      apiFetch<FeoCategory[]>('/feo-categories/'),
      apiFetch<Subsidy[]>('/subsidies/'),
    ])
    categories.value = cats
    subsidies.value = subs
  } catch (e: any) {
    error.value = e.detail || e.message
  } finally {
    loading.value = false
  }
}

onMounted(loadData)

const getLevelColor = (level: number) => {
  const colors = ['primary', 'secondary', 'success', 'warning', 'error']
  return colors[level - 1] || 'grey'
}

const openAddDialog = (parentId?: number) => {
  newCat.name = ''
  newCat.code = ''
  newCat.appendix = ''
  newCat.subsidy_id = null
  newCat.parent_id = parentId ?? null
  newCat.is_active = true
  addError.value = ''
  addDialog.value = true
}

const submitAdd = async () => {
  const { valid } = await addFormRef.value.validate()
  if (!valid) return
  addLoading.value = true
  addError.value = ''
  try {
    await apiFetch('/feo-categories/', {
      method: 'POST',
      body: JSON.stringify({
        name: newCat.name,
        code: newCat.code || null,
        appendix: newCat.appendix || null,
        subsidy_id: newCat.subsidy_id,
        parent_id: newCat.parent_id ?? null,
        is_active: newCat.is_active,
      }),
    })
    addDialog.value = false
    snack.text = 'Категория добавлена'
    snack.color = 'success'
    snack.show = true
    await loadData()
  } catch (e: any) {
    addError.value = e.detail || e.message || 'Ошибка создания категории'
  } finally {
    addLoading.value = false
  }
}
</script>
