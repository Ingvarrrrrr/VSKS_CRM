<template>
  <!-- Диалог добавления ответственного исполнителя -->
  <v-dialog v-model="open" max-width="400" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 pt-4 px-4">Добавить в справочник</v-card-title>
      <v-card-text class="pb-0">
        <v-text-field v-model="name" label="ФИО *" variant="outlined"
          density="compact" class="mb-2" autofocus />
        <v-text-field v-model="position" label="Должность (необязательно)"
          variant="outlined" density="compact" />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="open = false">Отмена</v-btn>
        <v-btn color="teal" variant="tonal" :loading="saving"
          :disabled="!name.trim()" @click="$emit('save')">
          Сохранить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

const open = defineModel<boolean>({ default: false })
const name = defineModel<string>('name', { default: '' })
const position = defineModel<string>('position', { default: '' })

defineProps<{ saving: boolean }>()
defineEmits<{ (e: 'save'): void }>()

const { mobile } = useDisplay()
</script>
