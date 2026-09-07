<template>
  <!-- Связанные задачи -->
  <v-card variant="outlined" class="mb-4">
    <v-card-title class="text-subtitle-1 d-flex align-center gap-2">
      <v-icon size="20">mdi-clipboard-check-outline</v-icon>
      Связанные задачи
      <v-chip size="x-small" variant="tonal" color="primary">{{ linkedTasks.length }}</v-chip>
      <v-spacer />
      <v-btn size="small" variant="tonal" color="secondary" prepend-icon="mdi-link-variant"
        :to="`/my-tasks?link_purchase=${purchaseId}`" class="mr-2">
        Привязать
      </v-btn>
      <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-plus"
        @click="openCreateLinkedTask">
        Создать
      </v-btn>
    </v-card-title>
    <v-card-text v-if="linkedTasks.length" class="pt-0">
      <v-list density="compact" class="pa-0">
        <v-list-item v-for="lt in linkedTasks" :key="lt.id" class="px-2"
          @click="$router.push(`/my-tasks?task=${lt.id}`)">
          <template #prepend>
            <v-icon :color="taskStatusColor(lt.status)" size="18">
              {{ lt.status === 'done' ? 'mdi-check-circle' : lt.status === 'in_progress' ? 'mdi-progress-clock' : 'mdi-circle-outline' }}
            </v-icon>
          </template>
          <v-list-item-title class="text-body-2">{{ lt.title }}</v-list-item-title>
          <v-list-item-subtitle class="text-caption">
            <v-chip size="x-small" variant="flat" :color="taskPriorityColor(lt.priority)" class="mr-1">
              {{ lt.priority }}
            </v-chip>
            <span v-if="lt.assignees?.length">
              {{ lt.assignees.map((a: any) => a.user_name || `#${a.user_id}`).join(', ') }}
            </span>
            <span v-if="lt.due_date" class="ml-2">
              · до {{ new Date(lt.due_date).toLocaleDateString('ru') }}
            </span>
          </v-list-item-subtitle>
          <template #append>
            <v-chip size="x-small" variant="tonal" :color="taskStatusColor(lt.status)" class="mr-1">
              {{ TASK_STATUS_LABEL[lt.status] || lt.status }}
            </v-chip>
            <v-btn icon="mdi-link-variant-off" size="x-small" variant="text" color="grey"
              title="Отвязать задачу" @click.stop="unlinkTask(lt.id)" />
          </template>
        </v-list-item>
      </v-list>
    </v-card-text>
    <v-card-text v-else class="text-caption text-medium-emphasis pt-0">
      Нет связанных задач. Нажмите «Создать задачу» чтобы делегировать работу по этой закупке.
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
// Карточка «Связанные задачи». Вынесено из CreateOrderView.vue (рефакторинг
// без изменения поведения, часть 3). Данные/функции — из
// composables/purchase/usePurchaseTasks.ts, вызываемого в родителе (там же
// нужен LinkedTaskDialogs) — приходят пропами.
defineProps<{
  purchaseId: number | null
  linkedTasks: any[]
  openCreateLinkedTask: () => void
  taskStatusColor: (status: string) => string
  taskPriorityColor: (priority: string) => string
  TASK_STATUS_LABEL: Record<string, string>
  unlinkTask: (id: number) => void
}>()
</script>
