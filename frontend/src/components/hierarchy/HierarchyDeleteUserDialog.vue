<template>
  <v-dialog v-model="show" max-width="420">
    <v-card>
      <v-card-title class="pa-4">
        <v-icon icon="mdi-account-remove" color="error" class="mr-2" />
        Удалить сотрудника
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        Удалить сотрудника <strong>«{{ name }}»</strong>?
        <div class="text-caption text-medium-emphasis mt-2">
          Будет удалена учётная запись и все связи. Действие необратимо.
          Доступно только при наличии права <code>user.manage</code>.
        </div>
        <v-alert v-if="warning" type="warning" variant="tonal" density="compact" class="mt-3 text-body-2">
          {{ warning }}
        </v-alert>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn color="error" variant="flat" :loading="loading" @click="emit('confirm')">
          {{ warning ? 'Удалить безвозвратно' : 'Удалить' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  name: string
  loading: boolean
  warning: string
}>()
const emit = defineEmits<{ confirm: [] }>()
const show = defineModel<boolean>({ default: false })
</script>
