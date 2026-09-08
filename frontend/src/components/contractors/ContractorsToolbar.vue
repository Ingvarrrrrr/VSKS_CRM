<template>
  <div class="page-header">
    <div class="page-header-left">
      <v-icon icon="mdi-account-group" size="32" color="#3B82F6" class="mr-3" />
      <div>
        <div class="page-title">Контрагенты</div>
        <div class="page-subtitle">Список поставщиков и исполнителей</div>
      </div>
    </div>
    <div class="page-header-right">
      <v-btn
        variant="tonal"
        color="secondary"
        prepend-icon="mdi-download"
        class="mr-2"
        @click="$emit('download-template')"
      >
        Шаблон
      </v-btn>
      <v-btn
        variant="tonal"
        color="success"
        prepend-icon="mdi-file-import-outline"
        class="mr-2"
        @click="$emit('open-import')"
      >
        Импорт из файла
      </v-btn>
      <v-btn v-if="isOwnerPlus" variant="tonal" color="blue" prepend-icon="mdi-database-refresh"
        class="mr-2" :loading="enrichAllLoading" @click="$emit('enrich-all')">
        Обновить из ЕГРЮЛ
      </v-btn>
      <v-btn variant="outlined" color="warning" prepend-icon="mdi-content-duplicate"
             class="mr-2" @click="$emit('open-duplicates')">
        Найти дубли по ИНН
      </v-btn>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="$emit('add')">
        Добавить контрагента
      </v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  isOwnerPlus: boolean
  enrichAllLoading: boolean
}>()
defineEmits<{
  (e: 'download-template'): void
  (e: 'open-import'): void
  (e: 'enrich-all'): void
  (e: 'open-duplicates'): void
  (e: 'add'): void
}>()
</script>
