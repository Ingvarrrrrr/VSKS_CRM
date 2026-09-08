<template>
  <Teleport to="body">
    <v-dialog v-model="show" max-width="420" :z-index="9999" :fullscreen="mobile">
      <v-card>
        <v-card-title class="pa-4 text-body-1">
          <v-icon icon="mdi-content-copy" class="mr-2" />Копировать «{{ userName }}» в отдел
        </v-card-title>
        <v-card-text class="pa-4 pt-0">
          <v-select
            v-model="targetDeptId"
            :items="deptOptions"
            item-title="title"
            item-value="value"
            label="Целевой отдел"
            variant="outlined"
            density="compact"
          />
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" @click="show = false">Отмена</v-btn>
          <v-btn color="teal" variant="flat" :disabled="!targetDeptId" @click="emit('confirm')">Добавить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </Teleport>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

defineProps<{
  userName: string
  deptOptions: { title: string; value: number }[]
}>()
const emit = defineEmits<{ confirm: [] }>()
const { mobile } = useDisplay()
const show = defineModel<boolean>({ default: false })
const targetDeptId = defineModel<number | null>('targetDeptId', { default: null })
</script>
