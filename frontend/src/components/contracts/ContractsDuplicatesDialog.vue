<template>
  <v-dialog v-model="dupDialog" max-width="700" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="pa-4">
        <v-icon icon="mdi-content-duplicate" color="warning" class="mr-2" />
        Найденные дубли ({{ duplicateGroups.length }} групп)
      </v-card-title>
      <v-card-text v-if="!duplicateGroups.length" class="text-center py-8 text-medium-emphasis">
        Дубликатов не найдено
      </v-card-text>
      <v-card-text v-else class="pa-4 pt-0">
        <div v-for="(group, gi) in duplicateGroups" :key="gi" class="mb-4 pa-3 rounded-lg" style="background:rgba(255,152,0,0.08);border-left:3px solid #ff9800">
          <div class="text-body-2 font-weight-bold mb-2">{{ group[0].number }} — {{ group[0].contractor_name || '?' }}</div>
          <v-table density="compact">
            <thead><tr><th>ID</th><th>Дата</th><th>Сумма</th><th>Закупок</th><th></th></tr></thead>
            <tbody>
              <tr v-for="c in group" :key="c.id">
                <td>{{ c.id }}</td>
                <td>{{ c.date || '—' }}</td>
                <td>{{ c.max_amount ? Number(c.max_amount).toLocaleString('ru-RU') + ' ₽' : '—' }}</td>
                <td>{{ c._purchaseCount ?? '?' }}</td>
                <td>
                  <v-btn v-if="group.length > 1" size="x-small" variant="tonal" color="error"
                    @click="onMerge(c.id, group.find((x: any) => x.id !== c.id)!.id)">
                    Объединить в #{{ group.find((x: any) => x.id !== c.id)?.id }}
                  </v-btn>
                </td>
              </tr>
            </tbody>
          </v-table>
        </div>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="dupDialog = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
const dupDialog = defineModel<boolean>({ required: true })

defineProps<{
  duplicateGroups: any[][]
  mobile: boolean
  onMerge: (sourceId: number, targetId: number) => void
}>()
</script>
