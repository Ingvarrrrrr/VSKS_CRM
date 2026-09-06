<template>
  <!-- Диалог создания связанной задачи -->
  <v-dialog v-model="linkedTaskOpen" max-width="560" persistent :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 pt-4 px-4">
        <v-icon class="mr-1" size="20">mdi-clipboard-plus-outline</v-icon>
        Задача по закупке
      </v-card-title>
      <v-card-text>
        <v-text-field v-model="form.title" label="Заголовок задачи" variant="outlined"
          density="compact" class="mb-3" :rules="[v => !!v || 'Обязательно']" />
        <v-textarea v-model="form.description" label="Описание" variant="outlined"
          density="compact" rows="2" class="mb-3" />
        <div class="d-flex gap-3 mb-3">
          <v-select v-model="form.priority" :items="TASK_PRIORITIES"
            item-title="title" item-value="value"
            label="Приоритет" variant="outlined" density="compact" style="max-width:180px" />
          <v-text-field v-model="form.due_date" label="Срок" type="date"
            variant="outlined" density="compact" />
        </div>
        <v-autocomplete v-model="form.assignee_ids" :items="allUsers"
          item-title="text" item-value="value" label="Исполнители" variant="outlined"
          density="compact" multiple chips closable-chips />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="linkedTaskOpen = false">Отмена</v-btn>
        <v-btn color="primary" variant="tonal" :loading="saving"
          :disabled="!form.title" @click="$emit('save')">
          Создать
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Диалог привязки существующей задачи -->
  <v-dialog v-model="linkOpen" max-width="520" :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 pt-4 px-4">
        <v-icon class="mr-1" size="20">mdi-link-variant</v-icon>
        Привязать задачу к закупке
      </v-card-title>
      <v-card-text>
        <v-text-field v-model="searchText" label="Поиск по названию задачи" variant="outlined"
          density="compact" prepend-inner-icon="mdi-magnify" clearable autofocus
          @update:model-value="$emit('search', $event)" />
        <div v-if="searching" class="d-flex justify-center py-4"><v-progress-circular indeterminate size="24" /></div>
        <v-list v-else-if="results.length" density="compact" class="border rounded" style="max-height:300px;overflow-y:auto">
          <v-list-item v-for="t in results" :key="t.id" @click="$emit('link', t.id)">
            <template #prepend>
              <v-icon :color="taskStatusColor(t.status)" size="18">
                {{ t.status === 'done' ? 'mdi-check-circle' : t.status === 'in_progress' ? 'mdi-progress-clock' : 'mdi-circle-outline' }}
              </v-icon>
            </template>
            <v-list-item-title class="text-body-2">{{ t.title }}</v-list-item-title>
            <v-list-item-subtitle class="text-caption">
              {{ t.assignees?.map((a: any) => a.user_name).join(', ') || 'Без исполнителя' }}
              <span v-if="t.purchase_id" class="text-warning ml-1">(уже привязана)</span>
            </v-list-item-subtitle>
          </v-list-item>
        </v-list>
        <div v-else-if="searchText" class="text-caption text-medium-emphasis text-center py-4">
          Задачи не найдены
        </div>
        <div v-else class="text-caption text-medium-emphasis text-center py-4">
          Введите текст для поиска задач
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="linkOpen = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'
import { TASK_PRIORITIES, taskStatusColor } from '@/composables/purchase/usePurchaseTasks'

const linkedTaskOpen = defineModel<boolean>('linkedTaskOpen', { default: false })
const linkOpen = defineModel<boolean>('linkOpen', { default: false })
const searchText = defineModel<string>('searchText', { default: '' })

const props = defineProps<{
  form: { title: string; description: string; priority: string; due_date: string; assignee_ids: number[] }
  saving: boolean
  allUsers: { value: number; text: string }[]
  results: any[]
  searching: boolean
}>()

defineEmits<{
  (e: 'save'): void
  (e: 'search', q: string): void
  (e: 'link', taskId: number): void
}>()

const form = props.form
const { mobile } = useDisplay()
</script>
