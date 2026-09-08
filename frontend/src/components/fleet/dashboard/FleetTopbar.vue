<template>
  <div class="fleet-topbar">
    <div class="fleet-crumbs">
      Автопарк <span class="fleet-crumbs__sep">/</span>
      <b>Все ТС</b>
    </div>
    <div class="fleet-search">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>
      </svg>
      <input
        :value="searchQuery"
        @input="$emit('update:searchQuery', ($event.target as HTMLInputElement).value)"
        placeholder="Поиск по госномеру, VIN, марке, ответственному…"
        class="fleet-search__input"
      />
    </div>
    <div class="fleet-topbar__actions">

      <button class="fleet-btn" @click="$emit('export')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>
        </svg>
        Экспорт
      </button>
      <button class="fleet-btn" @click="$emit('trip-picker')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
        </svg>
        Путевой лист
      </button>
      <button class="fleet-btn" @click="router.push('/m/driver')" title="Мобильный кабинет водителя">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12" y2="18"/>
        </svg>
        Кабинет водителя
      </button>
      <button class="fleet-btn fleet-btn--primary" @click="router.push('/property/vehicles/new')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 5v14M5 12h14"/>
        </svg>
        Добавить ТС
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

defineProps<{ searchQuery: string }>()
defineEmits<{
  (e: 'update:searchQuery', value: string): void
  (e: 'export'): void
  (e: 'trip-picker'): void
}>()

const router = useRouter()
</script>

<style scoped></style>
