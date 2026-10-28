<template>
  <v-dialog v-model="show" max-width="460" :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4 d-flex align-center">
        <v-icon icon="mdi-folder-plus" color="primary" class="mr-2" />
        Новый отдел
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <v-text-field
          v-model="form.name"
          label="Название отдела *"
          variant="outlined"
          density="compact"
          class="mb-3"
          autofocus
          placeholder="Например: Отдел закупок, Бухгалтерия, Склад"
          @keydown.enter="emit('create')"
        />
        <v-select
          v-model="form.org_id"
          :items="orgs"
          item-title="name"
          item-value="id"
          label="Организация *"
          variant="outlined"
          density="compact"
          class="mb-3"
          :loading="loadingLists"
          :disabled="orgs.length <= 1"
          hint="К какой организации относится отдел"
          persistent-hint
        />
        <v-select
          v-model="form.subsidy_id"
          :items="subsidyOptions"
          item-title="name"
          item-value="id"
          label="Субсидия"
          variant="outlined"
          density="compact"
          clearable
          :disabled="!form.org_id"
          :loading="loadingLists"
          hint="Если отдел обслуживает конкретную субсидию. Оставьте пустым для общего отдела."
          persistent-hint
        />
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!form.name.trim() || !form.org_id" @click="emit('create')">Создать</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

defineProps<{
  form: { name: string; org_id: number | null; subsidy_id: number | null }
  orgs: { id: number; name: string }[]
  subsidyOptions: any[]
  saving?: boolean
  loadingLists?: boolean
}>()
const emit = defineEmits<{ create: [] }>()
const { mobile } = useDisplay()
const show = defineModel<boolean>('show', { default: false })
</script>
