<template>
  <v-container fluid class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center mb-6">
      <v-icon icon="mdi-brain" size="32" color="purple" class="mr-3" />
      <div>
        <h1 class="text-h4 font-weight-bold">База знаний</h1>
        <p class="text-body-2 text-grey">Проблемы и решения</p>
      </div>
      <v-spacer />
      <v-btn color="primary" prepend-icon="mdi-plus" @click="openDialog()">
        Добавить
      </v-btn>
    </div>

    <!-- Search -->
    <v-text-field
      v-model="search"
      prepend-inner-icon="mdi-magnify"
      label="Поиск по названию, проблеме, решению, тегам..."
      variant="outlined"
      density="comfortable"
      clearable
      hide-details
      class="mb-6"
      @update:model-value="loadMemories"
    />

    <!-- Pinned Section -->
    <div v-if="pinnedMemories.length" class="mb-6">
      <h3 class="text-subtitle-1 font-weight-bold mb-3 d-flex align-center">
        <v-icon icon="mdi-pin" size="18" color="amber" class="mr-1" />
        Закреплённые
      </h3>
      <v-row>
        <v-col v-for="m in pinnedMemories" :key="m.id" cols="12" md="6" lg="4">
          <MemoryCard :memory="m" @edit="openDialog(m)" @delete="confirmDelete(m)" />
        </v-col>
      </v-row>
    </div>

    <!-- All Memories -->
    <h3 v-if="filteredMemories.length" class="text-subtitle-1 font-weight-bold mb-3">
      Все записи
    </h3>
    <v-row v-if="loading">
      <v-col cols="12" class="text-center py-12">
        <v-progress-circular indeterminate color="primary" size="48" />
      </v-col>
    </v-row>
    <v-row v-else-if="filteredMemories.length">
      <v-col v-for="m in filteredMemories" :key="m.id" cols="12" md="6" lg="4">
        <MemoryCard :memory="m" @edit="openDialog(m)" @delete="confirmDelete(m)" />
      </v-col>
    </v-row>
    <v-empty-state
      v-else
      icon="mdi-note-search-outline"
      title="Ничего не найдено"
      :text="search ? 'Попробуйте изменить запрос' : 'Добавьте первую запись'"
    />

    <!-- Dialog -->
    <v-dialog v-model="dialog" max-width="700" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center pa-4">
          <span>{{ editingId ? 'Редактировать' : 'Новая запись' }}</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="dialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <v-text-field
            v-model="form.title"
            label="Заголовок *"
            variant="outlined"
            class="mb-3"
          />
          <v-textarea
            v-model="form.problem"
            label="Проблема"
            variant="outlined"
            rows="3"
            class="mb-3"
          />
          <v-textarea
            v-model="form.solution"
            label="Решение"
            variant="outlined"
            rows="3"
            class="mb-3"
          />
          <v-text-field
            v-model="form.tags"
            label="Теги (через запятую)"
            variant="outlined"
            hint="Например: nginx, api, crm"
            persistent-hint
          />
          <v-switch
            v-model="form.is_pinned"
            label="Закрепить"
            color="amber"
            hide-details
            class="mt-3"
          />
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">Отмена</v-btn>
          <v-btn color="primary" :loading="saving" :disabled="!form.title" @click="save">
            Сохранить
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete Confirm -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title>Удалить запись?</v-card-title>
        <v-card-text>
          "{{ deletingTitle }}" будет удалена безвозвратно.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Отмена</v-btn>
          <v-btn color="error" :loading="deleting" @click="doDelete">Удалить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const API = '/api/memories'

const memories = ref([])
const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const search = ref('')
const dialog = ref(false)
const deleteDialog = ref(false)
const editingId = ref(null)
const deletingId = ref(null)
const deletingTitle = ref('')

const form = ref({
  title: '',
  problem: '',
  solution: '',
  tags: '',
  is_pinned: false
})

const pinnedMemories = computed(() => 
  memories.value.filter(m => m.is_pinned)
)

const filteredMemories = computed(() => 
  memories.value.filter(m => !m.is_pinned)
)

async function loadMemories() {
  loading.value = true
  try {
    const url = search.value ? `${API}?q=${encodeURIComponent(search.value)}` : API
    const res = await fetch(url)
    memories.value = await res.json()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function openDialog(memory = null) {
  if (memory) {
    editingId.value = memory.id
    form.value = { ...memory }
  } else {
    editingId.value = null
    form.value = { title: '', problem: '', solution: '', tags: '', is_pinned: false }
  }
  dialog.value = true
}

async function save() {
  saving.value = true
  try {
    const method = editingId.value ? 'PUT' : 'POST'
    const url = editingId.value ? `${API}/${editingId.value}` : API
    await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form.value)
    })
    dialog.value = false
    loadMemories()
  } catch (e) {
    console.error(e)
  } finally {
    saving.value = false
  }
}

function confirmDelete(memory) {
  deletingId.value = memory.id
  deletingTitle.value = memory.title
  deleteDialog.value = true
}

async function doDelete() {
  deleting.value = true
  try {
    await fetch(`${API}/${deletingId.value}`, { method: 'DELETE' })
    deleteDialog.value = false
    loadMemories()
  } catch (e) {
    console.error(e)
  } finally {
    deleting.value = false
  }
}

onMounted(loadMemories)
</script>
