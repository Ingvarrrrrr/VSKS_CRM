<template>
  <v-card v-if="selectedDept" variant="outlined">
    <v-card-title class="pa-4 d-flex align-center">
      <v-icon icon="mdi-account-group" class="mr-2" />{{ selectedDept.name }}
      <v-spacer />
      <v-chip v-if="selectedDept.head_user_name" size="small" color="teal" variant="tonal" prepend-icon="mdi-crown">
        {{ selectedDept.head_user_name }}
      </v-chip>
    </v-card-title>

    <!-- Members -->
    <v-card-text class="pa-4 pt-0">
      <div class="d-flex align-center mb-2">
        <span class="text-subtitle-2 font-weight-medium">Сотрудники</span>
        <v-chip size="x-small" class="ml-2" variant="tonal">{{ deptMembers.length }}</v-chip>
        <v-spacer />
        <v-btn size="x-small" variant="tonal" color="primary" prepend-icon="mdi-account-plus" @click="$emit('add-member', selectedDept)">Добавить</v-btn>
      </div>
      <v-alert v-if="deptMembers.length === 0" type="info" variant="tonal" density="compact" class="mb-2">
        Нажмите <strong>+</strong> на отделе в дереве слева или кнопку «Добавить» выше.
      </v-alert>
      <v-list density="compact" v-if="deptMembers.length">
        <v-list-item v-for="m in deptMembers" :key="m.id" :subtitle="m.position || m.user_role">
          <template v-slot:prepend>
            <UserAvatar :photo-url="getMemberPhotoUrl(m.user_id)" :avatar="getMemberAvatar(m.user_id)" :size="28" square />
          </template>
          <v-list-item-title>{{ m.user_name }}</v-list-item-title>
          <template v-slot:append>
            <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" class="mr-1" @click="$emit('edit-user-by-id', m.user_id)" title="Редактировать сотрудника" />
            <v-btn icon="mdi-close" size="x-small" variant="text" color="error" @click="$emit('remove-member', m.user_id)" />
          </template>
        </v-list-item>
      </v-list>
      <div v-else class="text-caption text-medium-emphasis pa-2">Нет сотрудников</div>

      <v-divider class="my-3" />

      <!-- Delegates -->
      <div class="d-flex align-center mb-2">
        <span class="text-subtitle-2 font-weight-medium">Права на задачи</span>
        <v-spacer />
        <v-btn size="x-small" variant="tonal" color="orange" prepend-icon="mdi-shield-account" @click="$emit('open-delegate-dialog')">Добавить</v-btn>
      </div>
      <div class="text-caption text-medium-emphasis mb-2">
        Начальник отдела автоматически может редактировать задачи своих сотрудников. Ниже — дополнительные права:
      </div>
      <v-list density="compact" v-if="delegates.length">
        <v-list-item v-for="d in delegates" :key="d.id">
          <v-list-item-title class="text-body-2">
            <strong>{{ d.delegate_user_name }}</strong> может редактировать задачи <strong>{{ d.target_user_name }}</strong>
          </v-list-item-title>
          <template v-slot:append>
            <v-btn icon="mdi-close" size="x-small" variant="text" color="error" @click="$emit('remove-delegate', d.id)" />
          </template>
        </v-list-item>
      </v-list>
      <div v-else class="text-caption text-medium-emphasis pa-2">Нет дополнительных делегирований</div>
    </v-card-text>
  </v-card>

  <v-card v-else variant="outlined" style="min-height:200px">
    <v-card-text class="d-flex flex-column align-center justify-center pa-6" style="min-height:200px">
      <v-icon icon="mdi-cursor-default-click" size="48" color="grey-lighten-1" />
      <div class="text-body-1 text-medium-emphasis mt-3 mb-4">Выберите отдел в дереве слева</div>
      <v-alert type="info" variant="tonal" density="compact" class="text-left" style="max-width:360px">
        <div class="text-body-2 font-weight-medium mb-1">Порядок настройки:</div>
        <ol class="text-body-2 pl-4" style="line-height:1.8">
          <li>Создайте отдел (кнопка "Добавить отдел")</li>
          <li>Нажмите <strong>+</strong> на отделе, чтобы добавить сотрудников</li>
          <li>Карандашом измените должность сотрудника</li>
          <li>Отредактируйте отдел и назначьте начальника</li>
        </ol>
      </v-alert>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import UserAvatar from '@/components/UserAvatar.vue'

defineProps<{
  selectedDept: any
  deptMembers: any[]
  delegates: any[]
  getMemberAvatar: (userId: number) => string | undefined
  getMemberPhotoUrl: (userId: number) => string | null | undefined
}>()
defineEmits<{
  (e: 'add-member', dept: any): void
  (e: 'edit-user-by-id', userId: number): void
  (e: 'remove-member', userId: number): void
  (e: 'open-delegate-dialog'): void
  (e: 'remove-delegate', id: number): void
}>()
</script>
