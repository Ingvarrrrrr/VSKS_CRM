<template>
  <v-card variant="outlined">
    <v-card-title class="pa-4 d-flex align-center">
      <v-icon icon="mdi-sitemap" class="mr-2" />Дерево отделов
      <v-spacer />
      <v-btn icon="mdi-refresh" variant="text" size="small" :loading="deptLoading" @click="$emit('reload')" />
    </v-card-title>
    <v-card-text class="pa-2">
      <div v-if="deptLoading" class="d-flex justify-center py-8"><v-progress-circular indeterminate /></div>
      <div v-else-if="filteredDeptTree.length === 0" class="text-center py-8 text-medium-emphasis">
        Нет отделов. Создайте первый или загрузите из Excel.
      </div>
      <div v-else>
        <div v-for="node in filteredDeptTree" :key="node.id">
          <component :is="deptTreeNode" :node="node" :depth="0" :multi-org="multiOrg"
            @select="$emit('select', $event)" @edit="$emit('edit', $event)" @delete="$emit('delete', $event)"
            @add-member="$emit('add-member', $event)" @edit-member="$emit('edit-member', $event)" @remove-member="$emit('remove-member', $event)" />
        </div>
      </div>
      <!-- Вне отделов -->
      <div v-if="!deptLoading && unassignedUsers.length > 0" class="mt-2">
        <div class="unassigned-folder-header d-flex align-center pa-2 rounded cursor-pointer"
          @click="unassignedExpanded = !unassignedExpanded">
          <v-icon :icon="unassignedExpanded ? 'mdi-folder-open-outline' : 'mdi-folder-outline'"
            color="grey" size="18" class="mr-2" />
          <span class="text-body-2 font-weight-medium text-medium-emphasis">Вне отделов</span>
          <v-chip size="x-small" class="ml-2" color="grey" variant="tonal">{{ unassignedUsers.length }}</v-chip>
          <v-icon :icon="unassignedExpanded ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="16" class="ml-auto" color="grey" />
        </div>
        <v-expand-transition>
          <div v-if="unassignedExpanded" class="pl-6">
            <div v-for="u in unassignedUsers" :key="u.id"
              class="d-flex align-center pa-1 rounded unassigned-user-row"
              @click="$emit('edit-user', u)">
              <UserAvatar :photo-url="u.photo_url" :avatar="u.avatar" :size="26" square class="mr-2 flex-shrink-0" />
              <span class="text-body-2">{{ u.full_name || u.username }}</span>
              <span class="text-caption text-medium-emphasis ml-2">{{ u.position || '' }}</span>
              <v-spacer />
              <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary" class="dept-member-action"
                title="Редактировать сотрудника" @click.stop="$emit('edit-user', u)" />
              <v-btn v-if="isAdmin" icon="mdi-close" size="x-small" variant="text" color="error" class="dept-member-action"
                title="Удалить пользователя" @click.stop="$emit('delete-user', u)" />
            </div>
          </div>
        </v-expand-transition>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import UserAvatar from '@/components/UserAvatar.vue'
// Глобальные (не scoped) стили строк дерева отделов — используются также
// StaffDeptTreeNode.ts (рендерится через h(), поэтому не может нести scoped CSS).
import './staffDeptTree.css'

defineProps<{
  deptLoading: boolean
  filteredDeptTree: any[]
  deptTreeNode: any
  multiOrg: boolean
  unassignedUsers: any[]
  isAdmin: boolean
}>()
defineEmits<{
  (e: 'reload'): void
  (e: 'select', node: any): void
  (e: 'edit', node: any): void
  (e: 'delete', node: any): void
  (e: 'add-member', node: any): void
  (e: 'edit-member', payload: any): void
  (e: 'remove-member', payload: any): void
  (e: 'edit-user', user: any): void
  (e: 'delete-user', user: any): void
}>()
const unassignedExpanded = defineModel<boolean>('unassignedExpanded', { default: true })
</script>

<style scoped>
/* Unassigned users folder — перенесено из StaffView.vue (scoped-стили не
   пересекают границу SFC, поэтому едут вместе с разметкой). */
.unassigned-folder-header { border: 1px dashed rgba(0,0,0,0.15); background: rgba(0,0,0,0.02); transition: background 0.15s; }
.unassigned-folder-header:hover { background: rgba(0,0,0,0.05); }
.unassigned-user-row { cursor: pointer; transition: background 0.15s; border-radius: 6px; }
.unassigned-user-row:hover { background: rgba(var(--v-theme-primary), 0.06); }
</style>
