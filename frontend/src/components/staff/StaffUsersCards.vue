<template>
  <div v-if="filteredUsers.length === 0" class="text-center py-12 text-medium-emphasis">
    <v-icon icon="mdi-account-group-outline" size="48" color="grey-lighten-2" class="mb-3 d-block" />
    Нет сотрудников
  </div>
  <v-row v-else dense>
    <v-col
      v-for="u in pagedCards"
      :key="u.id"
      cols="12"
      sm="6"
      lg="4"
    >
      <v-card
        variant="outlined"
        class="pa-0 h-100"
        hover
        @click="$emit('edit-user', u)"
      >
        <v-card-text class="pa-3">
          <div class="d-flex align-center mb-2">
            <v-checkbox-btn
              v-if="isAdmin"
              :model-value="selectedUsers.some((s: any) => (s as any).id === u.id || s === u.id)"
              density="compact"
              class="mr-1 flex-shrink-0"
              @click.stop
              @update:model-value="$emit('toggle-selection', u)"
            />
            <v-avatar size="38" class="mr-3 flex-shrink-0" color="primary" variant="tonal">
              <UserAvatar
                v-if="u.photo_url || u.avatar"
                :photo-url="u.photo_url"
                :avatar="u.avatar"
                :size="38"
                square
              />
              <span v-else class="text-body-2 font-weight-bold">
                {{ (u.full_name || u.username || '?').charAt(0).toUpperCase() }}
              </span>
            </v-avatar>
            <div class="flex-grow-1 min-width-0">
              <div class="text-body-1 font-weight-bold text-truncate">
                {{ u.full_name || u.username }}
              </div>
              <div class="text-caption text-medium-emphasis text-truncate">
                {{ u.position || '—' }}
              </div>
            </div>
            <v-chip :color="roleColor(u.role)" size="x-small" variant="tonal" class="ml-2 flex-shrink-0">
              {{ ROLE_LABELS[u.role] || u.role }}
            </v-chip>
          </div>
          <div v-if="u.email" class="d-flex align-center text-body-2 text-truncate mb-1">
            <v-icon icon="mdi-email-outline" size="14" class="mr-1 flex-shrink-0" color="grey" />
            {{ u.email }}
          </div>
          <div v-if="u.department" class="d-flex align-center text-caption text-medium-emphasis text-truncate">
            <v-icon icon="mdi-sitemap-outline" size="14" class="mr-1 flex-shrink-0" color="grey" />
            {{ u.department }}
          </div>
        </v-card-text>
        <v-card-actions class="pa-2 pt-0" @click.stop>
          <v-spacer />
          <template v-if="isAdmin">
            <v-btn icon="mdi-pencil" size="x-small" variant="text" color="primary"
              @click.stop="$emit('edit-user', u)" title="Редактировать" />
            <v-btn icon="mdi-account-supervisor" size="x-small" variant="text" color="teal"
              @click.stop="$emit('open-hierarchy', u)" title="Настроить подчиненных" />
            <v-btn icon="mdi-delete-outline" size="x-small" variant="text" color="error"
              @click.stop="$emit('delete-user', u)" :disabled="u.username === 'admin'" />
          </template>
        </v-card-actions>
      </v-card>
    </v-col>
  </v-row>
  <v-pagination
    v-if="cardsTotalPages > 1"
    v-model="cardsPage"
    :length="cardsTotalPages"
    density="compact"
    :total-visible="7"
    class="d-flex justify-center mt-4"
  />
</template>

<script setup lang="ts">
import UserAvatar from '@/components/UserAvatar.vue'
import { ROLE_LABELS, roleColor } from '@/composables/staff/staffLabels'

defineProps<{
  filteredUsers: any[]
  pagedCards: any[]
  isAdmin: boolean
  selectedUsers: any[]
  cardsTotalPages: number
}>()
defineEmits<{
  (e: 'edit-user', u: any): void
  (e: 'toggle-selection', u: any): void
  (e: 'open-hierarchy', u: any): void
  (e: 'delete-user', u: any): void
}>()
const cardsPage = defineModel<number>('cardsPage', { required: true })
</script>
