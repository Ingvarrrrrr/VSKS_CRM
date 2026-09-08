<template>
  <v-dialog v-model="show" max-width="420" :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4">
        <v-icon icon="mdi-account-plus" color="teal" class="mr-2" />
        Добавить сотрудника в отдел
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <v-autocomplete
          v-model="selectedId"
          :items="available"
          item-title="label"
          item-value="id"
          label="Выберите сотрудника"
          no-data-text="Нет доступных сотрудников"
          prepend-inner-icon="mdi-account-search"
          clearable
        />
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-btn variant="text" color="primary" prepend-icon="mdi-account-plus" @click="emit('create-new')">
          Создать нового
        </v-btn>
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn color="teal" variant="flat" :disabled="!selectedId" :loading="loading" @click="emit('confirm')">Добавить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

defineProps<{
  available: { id: number; label: string }[]
  loading: boolean
}>()
const emit = defineEmits<{ 'create-new': []; confirm: [] }>()
const { mobile } = useDisplay()
const show = defineModel<boolean>({ default: false })
const selectedId = defineModel<number | null>('selectedId', { default: null })
</script>
