<template>
  <v-dialog v-model="show" max-width="640" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4 d-flex align-center">
        <v-icon icon="mdi-account-multiple-outline" color="warning" class="mr-2" />
        Дубликаты пользователей по ИНН
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="show = false" />
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <v-alert type="info" variant="tonal" density="compact" class="mb-4 text-caption">
          Показаны пользователи с одинаковым ИНН. Объединение (merge) будет доступно после реализации backend-эндпоинта
          <code>PATCH /api/users/{'{id}'}/merge</code> — это отдельная задача.
          Пока вы можете открыть карточку каждого и разобраться вручную.
        </v-alert>
        <div v-for="{ inn, group } in duplicateInnGroups" :key="inn" class="mb-5">
          <div class="text-subtitle-2 font-weight-bold mb-2 d-flex align-center">
            <v-icon icon="mdi-card-account-details-outline" size="16" class="mr-1" color="warning" />
            ИНН: {{ inn }}
            <v-chip size="x-small" color="warning" variant="tonal" class="ml-2">{{ group.length }} записи</v-chip>
          </div>
          <v-table density="compact">
            <thead>
              <tr>
                <th>ID</th>
                <th>ФИО</th>
                <th>Логин</th>
                <th>Роль</th>
                <th>Организация</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in group" :key="u.id">
                <td class="text-caption text-medium-emphasis">{{ u.id }}</td>
                <td class="text-body-2">{{ u.full_name || '—' }}</td>
                <td class="text-caption">{{ u.username }}</td>
                <td><v-chip size="x-small" :color="roleColor(u.role)" variant="tonal">{{ ROLE_LABELS[u.role] || u.role }}</v-chip></td>
                <td class="text-caption">{{ (u as any).org_id || '—' }}</td>
                <td>
                  <v-btn size="x-small" variant="text" color="primary" icon="mdi-pencil"
                    @click="show = false; $emit('edit-user', u)" title="Открыть карточку" />
                </td>
              </tr>
            </tbody>
          </v-table>
        </div>
        <div v-if="duplicateInnGroups.length === 0" class="text-center py-6 text-medium-emphasis">
          Дубликатов не найдено
        </div>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="flat" color="primary" @click="show = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ROLE_LABELS, roleColor } from '@/composables/staff/staffLabels'

defineProps<{
  duplicateInnGroups: { inn: string; group: any[] }[]
  mobile: boolean
}>()
defineEmits<{ (e: 'edit-user', u: any): void }>()
const show = defineModel<boolean>('show', { required: true })
</script>
