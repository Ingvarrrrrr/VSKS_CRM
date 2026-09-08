<template>
  <v-dialog v-model="show" max-width="420" :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4">
        <v-icon icon="mdi-account-group" color="teal" class="mr-2" />
        Новый отдел
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <v-text-field
          v-model="form.name"
          label="Название отдела"
          prepend-inner-icon="mdi-account-group-outline"
          autofocus
          class="mb-3"
          @keydown.enter="emit('create')"
        />
        <v-select
          v-if="orgs.length > 1"
          v-model="form.orgId"
          :items="orgs"
          item-title="name"
          item-value="id"
          label="Организация"
          variant="outlined"
          density="compact"
          prepend-inner-icon="mdi-domain"
          hint="К какой организации относится отдел"
          persistent-hint
        />
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn color="teal" variant="flat" :disabled="!form.name.trim()" @click="emit('create')">Создать</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

defineProps<{
  form: { name: string; orgId: number | null }
  orgs: { id: number; name: string }[]
}>()
const emit = defineEmits<{ create: [] }>()
const { mobile } = useDisplay()
const show = defineModel<boolean>({ default: false })
</script>
