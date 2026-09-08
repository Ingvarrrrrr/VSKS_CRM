<template>
  <v-dialog :model-value="modelValue" max-width="500" scrollable :fullscreen="mobile" @update:model-value="$emit('update:modelValue', $event)">
    <v-card>
      <v-card-title class="d-flex align-center">
        <v-icon icon="mdi-chat-plus" class="me-2" />
        Новый чат
      </v-card-title>
      <v-card-text>
        <!-- Staff search -->
        <v-text-field
          :model-value="staffSearch"
          placeholder="Поиск сотрудника..."
          prepend-inner-icon="mdi-magnify"
          variant="outlined"
          density="compact"
          class="mb-3"
          clearable
          @update:model-value="$emit('update:staffSearch', $event ?? '')"
        />

        <!-- Staff list -->
        <v-list lines="two" max-height="300" class="overflow-y-auto border rounded">
          <v-list-item
            v-for="person in filteredStaff"
            :key="person.id"
            :class="{ 'bg-primary-lighten-5': selectedStaffIds.includes(person.id) }"
            rounded
            @click="$emit('toggle-staff', person.id)"
          >
            <template #prepend>
              <v-avatar color="secondary" size="36">
                <span class="text-body-2 text-white">{{ person.full_name.charAt(0) }}</span>
              </v-avatar>
            </template>
            <v-list-item-title>{{ person.full_name }}</v-list-item-title>
            <v-list-item-subtitle>{{ person.username }}</v-list-item-subtitle>
            <template #append>
              <v-checkbox-btn :model-value="selectedStaffIds.includes(person.id)" readonly />
            </template>
          </v-list-item>
          <v-empty-state
            v-if="filteredStaff.length === 0"
            icon="mdi-account-search"
            text="Сотрудники не найдены"
            class="py-4"
          />
        </v-list>

        <!-- Group name (shown when 2+ selected) -->
        <v-text-field
          v-if="selectedStaffIds.length >= 2"
          :model-value="newGroupName"
          label="Название группы"
          variant="outlined"
          density="compact"
          class="mt-3"
          prepend-inner-icon="mdi-account-group"
          @update:model-value="$emit('update:newGroupName', $event ?? '')"
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="$emit('cancel')">Отмена</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :disabled="selectedStaffIds.length === 0 || (selectedStaffIds.length >= 2 && !newGroupName.trim())"
          :loading="creatingChat"
          @click="$emit('create')"
        >
          {{ selectedStaffIds.length === 1 ? 'Написать' : 'Создать группу' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { StaffMember } from '@/composables/chat/chatTypes'

defineProps<{
  modelValue: boolean
  mobile: boolean
  staffSearch: string
  filteredStaff: StaffMember[]
  selectedStaffIds: number[]
  newGroupName: string
  creatingChat: boolean
}>()

defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'update:staffSearch', value: string): void
  (e: 'update:newGroupName', value: string): void
  (e: 'toggle-staff', id: number): void
  (e: 'cancel'): void
  (e: 'create'): void
}>()
</script>
