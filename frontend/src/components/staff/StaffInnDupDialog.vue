<template>
  <v-dialog v-model="show" max-width="720" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4 d-flex align-center">
        <v-icon icon="mdi-account-multiple-outline" color="warning" class="mr-2" />
        Дубликаты сотрудников по ИНН
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="show = false" />
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <v-alert type="info" variant="tonal" density="compact" class="mb-4 text-caption">
          Выберите основного сотрудника, в чей профиль будут перенесены все задачи, закупки, документы и права доступа остальных дублей. Дубликаты будут удалены.
        </v-alert>

        <div v-for="{ inn, group } in duplicateInnGroups" :key="inn" class="mb-6 pa-3 border rounded">
          <div class="text-subtitle-2 font-weight-bold mb-2 d-flex align-center">
            <v-icon icon="mdi-card-account-details-outline" size="16" class="mr-1" color="warning" />
            ИНН: {{ inn }}
            <v-chip size="x-small" color="warning" variant="tonal" class="ml-2">{{ group.length }} записи</v-chip>
            <v-spacer />
            <v-btn
              size="small"
              color="primary"
              variant="tonal"
              prepend-icon="mdi-call-merge"
              :loading="mergingInn === inn"
              @click="confirmMerge(inn, group)"
            >
              Объединить в выбранного
            </v-btn>
          </div>

          <v-table density="compact">
            <thead>
              <tr>
                <th style="width: 48px">Осн.</th>
                <th>ID</th>
                <th>ФИО</th>
                <th>Логин</th>
                <th>Роль</th>
                <th>Организация</th>
                <th style="width: 48px"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in group" :key="u.id" :class="{'bg-primary-lighten-5': getKeepId(inn, group) === u.id}">
                <td>
                  <v-radio-group
                    :model-value="getKeepId(inn, group)"
                    hide-details
                    density="compact"
                    @update:model-value="(val) => setKeepId(inn, val)"
                  >
                    <v-radio :value="u.id" color="primary" density="compact" />
                  </v-radio-group>
                </td>
                <td class="text-caption text-medium-emphasis">{{ u.id }}</td>
                <td class="text-body-2 font-weight-medium">{{ u.full_name || '—' }}</td>
                <td class="text-caption">{{ u.username }}</td>
                <td>
                  <v-chip size="x-small" :color="roleColor(u.role)" variant="tonal">
                    {{ ROLE_LABELS[u.role] || u.role }}
                  </v-chip>
                </td>
                <td class="text-caption">{{ (u as any).org_id || '—' }}</td>
                <td>
                  <v-btn
                    size="x-small"
                    variant="text"
                    color="primary"
                    icon="mdi-pencil"
                    @click="show = false; $emit('edit-user', u)"
                    title="Открыть карточку"
                  />
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
import { ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import { ROLE_LABELS, roleColor } from '@/composables/staff/staffLabels'

const props = defineProps<{
  duplicateInnGroups: { inn: string; group: any[] }[]
  mobile: boolean
}>()

const emit = defineEmits<{
  (e: 'edit-user', u: any): void
  (e: 'merged'): void
}>()

const show = defineModel<boolean>('show', { required: true })
const { success, error } = useToast()

const keepMap = ref<Record<string, number>>({})
const mergingInn = ref<string | null>(null)

function getKeepId(inn: string, group: any[]): number {
  if (keepMap.value[inn]) return keepMap.value[inn]
  return group[0]?.id
}

function setKeepId(inn: string, id: number) {
  keepMap.value[inn] = id
}

async function confirmMerge(inn: string, group: any[]) {
  const keepId = getKeepId(inn, group)
  const otherUsers = group.filter((u) => u.id !== keepId)
  const otherIds = otherUsers.map((u) => u.id)
  if (!otherIds.length) return

  const keepUser = group.find((u) => u.id === keepId)
  const keepName = keepUser?.full_name || `#${keepId}`

  if (!confirm(`Объединить ${otherIds.length} дубл. в пользователя ${keepName} (#${keepId})? Все задачи, закупки, договоры и связи будут сохранены за ним, а дублирующие записи удалены.`)) {
    return
  }

  mergingInn.value = inn
  try {
    const res = await apiFetch<any>(`/users/${keepId}/merge`, {
      method: 'POST',
      body: { merge_user_ids: otherIds },
    })
    success(`Слияние завершено: объединено ${res.merged_count} пользователей, обновлено связей: ${res.updated_relations}`)
    emit('merged')
  } catch (e: any) {
    error(`Ошибка объединения: ${e?.detail || e?.message || 'не удалось объединить сотрудников'}`)
  } finally {
    mergingInn.value = null
  }
}
</script>
