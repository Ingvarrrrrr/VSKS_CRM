<template>
  <!-- ЕГРЮЛ diff dialog -->
  <v-dialog v-model="open" max-width="640" persistent :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4">
        <v-icon icon="mdi-database-sync-outline" color="primary" class="mr-2" />
        Данные из ЕГРЮЛ отличаются
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <p class="text-body-2 text-medium-emphasis mb-3">
          По каждому полю выберите — обновить значение или оставить текущее.
        </p>
        <v-table density="compact">
          <thead>
            <tr><th>Поле</th><th>Сейчас</th><th>Из ЕГРЮЛ</th><th style="width:90px">Обновить</th></tr>
          </thead>
          <tbody>
            <tr v-for="d in items" :key="d.key">
              <td class="text-caption font-weight-medium">{{ d.label }}</td>
              <td class="text-caption text-medium-emphasis" style="max-width:200px;word-break:break-word">{{ d.old }}</td>
              <td class="text-caption" style="color:#4caf50;max-width:200px;word-break:break-word">{{ d.new }}</td>
              <td>
                <v-checkbox
                  :model-value="pending[d.key] !== undefined"
                  density="compact" hide-details
                  @update:model-value="(v) => v ? (pending[d.key] = d.new) : (delete pending[d.key])"
                />
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="open = false">Отмена</v-btn>
        <v-btn color="primary" variant="flat" @click="$emit('apply')" :disabled="Object.keys(pending).length === 0">
          Применить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'

const open = defineModel<boolean>({ default: false })

defineProps<{
  items: { key: string; label: string; old: string; new: string }[]
  pending: Record<string, string>
}>()

defineEmits<{ (e: 'apply'): void }>()

const { mobile } = useDisplay()
</script>
