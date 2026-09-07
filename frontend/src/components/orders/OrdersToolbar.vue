<template>
  <div class="d-flex align-center justify-space-between mb-6">
    <div>
      <h1 class="text-h5 font-weight-bold">Закупки</h1>
      <span class="text-body-2 text-medium-emphasis">{{ ordersCount }} записей</span>
    </div>
    <div class="d-flex gap-2">
      <v-btn variant="outlined" size="small" prepend-icon="mdi-download" @click="emit('download-template')">Шаблон</v-btn>
      <v-btn variant="outlined" prepend-icon="mdi-file-import" color="blue" @click="emit('open-import')">Импорт</v-btn>
      <v-btn variant="outlined" prepend-icon="mdi-folder-upload" color="teal" @click="emit('open-scans')">Сканы</v-btn>
      <v-btn variant="outlined" prepend-icon="mdi-bank-transfer" color="indigo" @click="emit('open-payment-match')">Разнести платежи</v-btn>
      <v-btn variant="outlined" prepend-icon="mdi-file-export" color="success" @click="emit('open-export')">Excel</v-btn>
      <v-btn v-if="canAddWish" color="primary" prepend-icon="mdi-plus" to="/wishes?create=1">Добавить</v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  ordersCount: number
  canAddWish: boolean
}>()

const emit = defineEmits<{
  'download-template': []
  'open-import': []
  'open-scans': []
  'open-payment-match': []
  'open-export': []
}>()
</script>
