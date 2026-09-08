<template>
  <v-data-table
      v-resizable-columns="'staff'"
      :headers="visibleHeaders"
      :items="filteredUsers"
      :loading="usersLoading"
      density="comfortable"
      show-expand
      expand-on-click
      item-value="id"
      v-model:expanded="expandedUsers"
      @update:expanded="$emit('user-expanded', $event)"
      v-model:selected="selectedUsers"
      :show-select="isAdmin"
    >
      <template v-slot:item.avatar="{ item }">
        <UserAvatar :photo-url="item.photo_url" :avatar="item.avatar" :size="32" square />
      </template>
      <template v-slot:item.role="{ item }">
        <v-chip :color="roleColor(item.role)" size="small" variant="tonal">
          {{ ROLE_LABELS[item.role] || item.role }}
        </v-chip>
      </template>
      <template v-slot:item.position="{ item }">
        <span class="text-body-2">{{ item.position || '---' }}</span>
      </template>
      <template v-slot:item.has_signature="{ item }">
        <v-icon v-if="item.has_signature" icon="mdi-draw" size="18" color="success" title="Подпись создана" />
        <v-icon v-else icon="mdi-draw-pen" size="18" color="grey-lighten-1" title="Подпись не создана" />
      </template>
      <template v-slot:item.actions="{ item }">
        <div class="d-flex gap-1" v-if="isAdmin">
          <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary"
            @click.stop="$emit('edit-user', item)" title="Редактировать" />
          <v-btn icon="mdi-account-supervisor" size="x-small" variant="text" color="teal"
            @click.stop="$emit('open-hierarchy', item)" title="Настроить подчиненных" />
          <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error"
            @click.stop="$emit('delete-user', item)" :disabled="item.username === 'admin'" />
        </div>
      </template>
      <template v-slot:expanded-row="{ item, columns }">
        <tr>
          <td :colspan="columns.length + 1" class="pa-0">
            <div class="px-4 py-3 bg-grey-lighten-5">
              <div v-if="taskAuthorityLoading[item.id]" class="d-flex align-center ga-2 py-1">
                <v-progress-circular size="16" indeterminate />
                <span class="text-caption text-medium-emphasis">Загрузка...</span>
              </div>
              <div v-else class="d-flex ga-4 flex-wrap align-start">
                <div>
                  <div class="text-caption font-weight-medium text-medium-emphasis mb-1 d-flex align-center">
                    <v-icon size="14" class="mr-1" color="teal">mdi-arrow-right-circle</v-icon>
                    Может ставить задачи:
                  </div>
                  <div v-if="!taskAuthority[item.id]?.can_assign_to?.length" class="text-caption text-medium-emphasis">—</div>
                  <v-chip
                    v-for="u in taskAuthority[item.id]?.can_assign_to" :key="u.id"
                    size="x-small" color="teal" variant="tonal" class="mr-1 mb-1">
                    {{ u.full_name || u.username }}
                  </v-chip>
                </div>
                <div>
                  <div class="text-caption font-weight-medium text-medium-emphasis mb-1 d-flex align-center">
                    <v-icon size="14" class="mr-1" color="indigo">mdi-arrow-left-circle</v-icon>
                    Кто ставит ему задачи:
                  </div>
                  <div v-if="!taskAuthority[item.id]?.can_receive_from?.length" class="text-caption text-medium-emphasis">—</div>
                  <v-chip
                    v-for="u in taskAuthority[item.id]?.can_receive_from" :key="u.id"
                    size="x-small" color="indigo" variant="tonal" class="mr-1 mb-1">
                    {{ u.full_name || u.username }}
                  </v-chip>
                </div>
                <v-btn size="x-small" variant="text" color="primary" prepend-icon="mdi-sitemap"
                  @click.stop="$emit('goto-hierarchy-tab')">
                  Настроить в Иерархии
                </v-btn>
              </div>
            </div>
          </td>
        </tr>
      </template>
    </v-data-table>
</template>

<script setup lang="ts">
import UserAvatar from '@/components/UserAvatar.vue'
import { ROLE_LABELS, roleColor } from '@/composables/staff/staffLabels'

defineProps<{
  visibleHeaders: any[]
  filteredUsers: any[]
  usersLoading: boolean
  isAdmin: boolean
  taskAuthority: Record<number, { can_assign_to: any[]; can_receive_from: any[] }>
  taskAuthorityLoading: Record<number, boolean>
}>()
defineEmits<{
  (e: 'user-expanded', expanded: number[]): void
  (e: 'edit-user', item: any): void
  (e: 'open-hierarchy', item: any): void
  (e: 'delete-user', item: any): void
  (e: 'goto-hierarchy-tab'): void
}>()
const expandedUsers = defineModel<number[]>('expandedUsers', { required: true })
const selectedUsers = defineModel<any[]>('selectedUsers', { required: true })
</script>
