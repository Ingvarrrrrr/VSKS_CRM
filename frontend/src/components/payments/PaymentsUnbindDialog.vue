<template>
  <v-dialog v-model="dialogOpen" max-width="420">
    <v-card>
      <v-card-title>Откатить подтверждение?</v-card-title>
      <v-card-text>
        Платёжные записи, созданные при подтверждении, будут удалены. Статусы закупок пересчитаются автоматически.
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="dialogOpen = false">Отмена</v-btn>
        <v-btn color="warning" variant="elevated" :loading="loading" @click="emit('confirm')">Откатить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
const dialogOpen = defineModel<boolean>({ required: true })

defineProps<{
  loading: boolean
}>()

const emit = defineEmits<{
  confirm: []
}>()
</script>
