<template>
  <div class="d-flex align-center justify-space-between mb-4">
    <div>
      <h1 class="text-h5 font-weight-bold">Реестр договоров</h1>
      <span class="text-body-2 text-medium-emphasis">
        {{ filteredCount }} из {{ totalCount }} записей
      </span>
    </div>
    <div class="d-flex gap-2">
      <v-btn v-if="isAdmin" variant="outlined" prepend-icon="mdi-database-import" @click="emit('open-migrate')">
        Мигрировать из закупок
      </v-btn>
      <v-btn variant="outlined" prepend-icon="mdi-file-upload-outline" color="info"
        @click="emit('open-import')"
        @dragover.prevent.stop
        @dragenter.prevent.stop
        @drop.prevent.stop="onButtonDrop"
        class="import-drop-btn"
        :class="{ 'import-drop-btn--hover': btnDragOver }"
        @dragenter="btnDragOver = true" @dragleave="btnDragOver = false"
      >
        Импорт из файла
      </v-btn>
      <v-btn variant="outlined" prepend-icon="mdi-content-duplicate" color="warning" @click="emit('check-duplicates')" :loading="dupLoading">
        Проверить дубли
      </v-btn>
      <v-btn
        v-if="isAdmin"
        variant="outlined"
        prepend-icon="mdi-database-refresh"
        color="purple"
        @click="emit('open-enrich')"
      >
        Обогатить из закупок
      </v-btn>
      <v-btn variant="outlined" prepend-icon="mdi-file-excel-outline" color="success" @click="emit('open-export')">
        Скачать реестр
      </v-btn>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="emit('add')">Добавить</v-btn>
      <v-btn variant="tonal" prepend-icon="mdi-view-column" size="small" @click="emit('open-columns')">Колонки</v-btn>
      <v-btn-toggle v-if="!mobile" v-model="viewMode" mandatory density="compact" variant="outlined" divided class="ml-1">
        <v-btn value="table" size="small" icon="mdi-table" />
        <v-btn value="cards" size="small" icon="mdi-view-grid" />
      </v-btn-toggle>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const viewMode = defineModel<'table' | 'cards'>('viewMode', { required: true })

defineProps<{
  filteredCount: number
  totalCount: number
  isAdmin: boolean
  dupLoading: boolean
  mobile: boolean
}>()

const emit = defineEmits<{
  'open-migrate': []
  'open-import': []
  'check-duplicates': []
  'open-enrich': []
  'open-export': []
  add: []
  'open-columns': []
  'file-dropped': [file: File]
}>()

// Drag-and-drop файла договора прямо на кнопку «Импорт из файла» —
// дословный перенос из ContractsView.vue (onButtonDrop).
const btnDragOver = ref(false)
function onButtonDrop(e: DragEvent) {
  btnDragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) emit('file-dropped', file)
}
</script>

<style scoped>
.import-drop-btn--hover {
  outline: 2px dashed rgb(var(--v-theme-info));
  outline-offset: 2px;
  background: rgba(var(--v-theme-info), 0.08) !important;
}
</style>
