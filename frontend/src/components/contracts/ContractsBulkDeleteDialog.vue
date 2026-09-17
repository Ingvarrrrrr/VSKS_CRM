<template>
  <v-dialog :model-value="dialog.show" max-width="520" @update:model-value="v => !v && !dialog.deleting && emit('close')">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
        Удалить {{ selected.length }} {{ pluralDocs(selected.length) }}?
      </v-card-title>
      <v-card-text class="px-4">
        <div class="text-body-2 mb-2">
          Договоры: {{ selected.map(c => c.number || ('#' + c.id)).join(', ') }}
        </div>
        <div class="text-caption text-medium-emphasis mb-2">Закупки, привязанные к договорам, сохранятся.</div>

        <v-progress-linear v-if="dialog.deleting" :model-value="dialog.total ? (dialog.progress / dialog.total) * 100 : 0" height="6" class="mb-2" />

        <v-alert v-if="!dialog.deleting && dialog.failures.length" type="warning" variant="tonal" density="compact" class="mt-2">
          <div class="font-weight-medium mb-1">Не удалось удалить {{ dialog.failures.length }}:</div>
          <ul class="ml-4">
            <li v-for="f in dialog.failures" :key="f.id">№{{ f.number }}: {{ f.reason }}</li>
          </ul>
        </v-alert>
      </v-card-text>
      <v-card-actions class="px-4 pb-3">
        <v-spacer />
        <v-btn variant="text" :disabled="dialog.deleting" @click="emit('close')">
          {{ dialog.failures.length ? 'Закрыть' : 'Отмена' }}
        </v-btn>
        <v-btn v-if="!dialog.failures.length || dialog.deleting" color="error" variant="tonal" :loading="dialog.deleting" @click="emit('confirm')">
          Удалить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { Contract } from '@/composables/contracts/contractsTypes'
import type { BulkDeleteFailure } from '@/composables/contracts/useContractsSelection'

defineProps<{
  dialog: { show: boolean; deleting: boolean; progress: number; total: number; failures: BulkDeleteFailure[] }
  selected: Contract[]
}>()

const emit = defineEmits<{
  confirm: []
  close: []
}>()

function pluralDocs(n: number): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return 'договор'
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return 'договора'
  return 'договоров'
}
</script>
