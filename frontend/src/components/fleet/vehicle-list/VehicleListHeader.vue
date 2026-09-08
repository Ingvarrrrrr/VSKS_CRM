<template>
  <div>
    <!-- Trip picker banner -->
    <v-alert
      v-if="showTripBanner"
      type="info"
      variant="tonal"
      class="mb-3"
      closable
      @click:close="emit('update:showTripBanner', false)"
    >
      <strong>Выберите ТС для путевого листа.</strong>
      Кликните на машину — откроется её карточка, вкладка «Путёвки», там кнопка «+ Добавить путёвку».
    </v-alert>

    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold">Автотранспорт</h1>
        <span class="text-body-2 text-medium-emphasis">{{ total }} записей</span>
      </div>
      <div class="d-flex gap-2 align-center">
        <v-btn-toggle
          v-if="!mobile"
          :model-value="viewMode"
          mandatory
          density="compact"
          variant="outlined"
          divided
          @update:model-value="emit('update:viewMode', $event)"
        >
          <v-btn value="table" size="small" icon="mdi-table" />
          <v-btn value="cards" size="small" icon="mdi-view-grid" />
        </v-btn-toggle>
        <v-btn variant="outlined" size="small" prepend-icon="mdi-view-dashboard"
          @click="router.push('/property/vehicles/dashboard')">Дашборд</v-btn>
        <!-- Раньше шаблон можно было скачать только из первого шага диалога импорта —
             владелец жаловался, что не может найти, откуда скачать пустой шаблон
             для заполнения. Кнопка вынесена в шапку реестра, диалог импорта её тоже
             сохраняет (уместна на своём первом шаге). Desktop — обычная кнопка,
             мобильный — пункт меню «Ещё», иначе кнопки не помещаются в один ряд. -->
        <v-btn
          v-if="!mobile && canImport"
          variant="outlined" prepend-icon="mdi-file-download-outline" color="primary"
          :loading="loadingTemplate"
          @click="emit('download-template')">
          Шаблон Excel
        </v-btn>
        <v-btn
          v-if="!mobile && canImport"
          variant="outlined" prepend-icon="mdi-file-excel" color="green"
          @click="emit('open-import')">
          Импорт Excel
        </v-btn>
        <v-menu v-if="mobile && canImport">
          <template #activator="{ props: menuProps }">
            <v-btn v-bind="menuProps" variant="outlined" size="small" icon="mdi-dots-vertical" />
          </template>
          <v-list density="compact">
            <v-list-item :disabled="loadingTemplate" @click="emit('download-template')">
              <template #prepend><v-icon icon="mdi-file-download-outline" /></template>
              <v-list-item-title>Шаблон Excel</v-list-item-title>
            </v-list-item>
            <v-list-item @click="emit('open-import')">
              <template #prepend><v-icon icon="mdi-file-excel" color="green" /></template>
              <v-list-item-title>Импорт Excel</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-menu>
        <v-btn color="primary" prepend-icon="mdi-plus" @click="emit('create')">Добавить ТС</v-btn>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

defineProps<{
  total: number
  mobile: boolean
  viewMode: 'table' | 'cards'
  loadingTemplate: boolean
  canImport: boolean
  showTripBanner: boolean
}>()

const emit = defineEmits<{
  (e: 'update:viewMode', value: 'table' | 'cards'): void
  (e: 'update:showTripBanner', value: boolean): void
  (e: 'download-template'): void
  (e: 'open-import'): void
  (e: 'create'): void
}>()

const router = useRouter()
</script>

<style scoped></style>
