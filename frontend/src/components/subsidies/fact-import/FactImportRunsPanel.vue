<template>
  <v-dialog v-model="factImport.runsPanelShow" max-width="900">
    <v-card>
      <v-card-title class="text-h6">Журнал импорта факта</v-card-title>
      <v-card-text>
        <v-progress-linear v-if="factImport.runsLoading" indeterminate color="teal" class="mb-2" />
        <v-table density="compact">
          <thead>
            <tr><th>Дата</th><th>Файл</th><th>Лист</th><th>Кто</th><th>Статус</th><th>Закупок</th><th>Платежей</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="r in factImport.runs" :key="r.id">
              <td>{{ formatDate(r.created_at) }}</td>
              <td>{{ r.filename }}</td>
              <td>{{ r.sheet }}</td>
              <td>{{ r.user_name }}</td>
              <td>
                <v-chip size="x-small" :color="r.status === 'committed' ? 'success' : 'grey'" variant="tonal">
                  {{ r.status === 'committed' ? 'применён' : 'откачен' }}
                </v-chip>
              </td>
              <td>{{ r.purchases_created }}</td>
              <td>{{ r.payments_created }}</td>
              <td>
                <v-btn v-if="r.status === 'committed'" size="x-small" variant="outlined" color="error"
                  @click="startRollback(r)">Откатить</v-btn>
              </td>
            </tr>
            <tr v-if="!factImport.runs.length && !factImport.runsLoading">
              <td colspan="8" class="text-center text-medium-emphasis py-4">Прогонов импорта факта ещё не было</td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="factImport.runsPanelShow = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Подтверждение откат — встроенное (не confirm()), с блокерами/объёмом удаления. -->
  <v-dialog v-model="rollbackDialog" max-width="520">
    <v-card>
      <v-card-title class="text-h6">Откатить импорт №{{ rollbackTarget?.id }}?</v-card-title>
      <v-card-text>
        <v-progress-linear v-if="rollbackChecking" indeterminate color="teal" class="mb-2" />
        <template v-if="rollbackCheck">
          <v-alert v-if="!rollbackCheck.can_rollback" type="error" variant="tonal" density="compact">
            Откат невозможен:
            <ul><li v-for="(b, i) in rollbackCheck.blockers" :key="i">{{ b }}</li></ul>
          </v-alert>
          <template v-else>
            <v-alert v-if="rollbackCheck.blockers.length" type="warning" variant="tonal" density="compact" class="mb-2">
              <div v-for="(b, i) in rollbackCheck.blockers" :key="i">{{ b }}</div>
            </v-alert>
            <div class="text-body-2">Будет удалено:</div>
            <ul class="text-body-2">
              <li>закупок: {{ rollbackCheck.will_delete.purchases }}</li>
              <li>платежей: {{ rollbackCheck.will_delete.payments }}</li>
              <li>контрагентов: {{ rollbackCheck.will_delete.contractors }}</li>
              <li>договоров: {{ rollbackCheck.will_delete.contracts }}</li>
              <li>плановых позиций: {{ rollbackCheck.will_delete.planned_items }}</li>
            </ul>
          </template>
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="rollbackDialog = false">Отмена</v-btn>
        <v-btn v-if="rollbackCheck?.can_rollback" color="error" variant="flat" :loading="rollbackRunning"
          @click="confirmRollback">Откатить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// FactImportRunsPanel.vue — журнал прогонов импорта факта + откат (план
// breezy-mixing-lovelace.md). Подтверждение отката — встроенный диалог
// (ПРАВИЛО проекта: никаких confirm()), сперва dry_run=true показывает
// blockers/will_delete, затем настоящий rollback.
import { ref } from 'vue'
import { useFactImport, type FactImportRunListItem, type FactImportRollbackCheck } from '@/composables/subsidies/useFactImport'

const { factImport, checkRollback, doRollback } = useFactImport()

function formatDate(iso: string): string {
  try { return new Date(iso).toLocaleString('ru-RU') } catch { return iso }
}

const rollbackDialog = ref(false)
const rollbackTarget = ref<FactImportRunListItem | null>(null)
const rollbackCheck = ref<FactImportRollbackCheck | null>(null)
const rollbackChecking = ref(false)
const rollbackRunning = ref(false)

async function startRollback(run: FactImportRunListItem) {
  rollbackTarget.value = run
  rollbackCheck.value = null
  rollbackDialog.value = true
  rollbackChecking.value = true
  rollbackCheck.value = await checkRollback(run.id)
  rollbackChecking.value = false
}

async function confirmRollback() {
  if (!rollbackTarget.value) return
  rollbackRunning.value = true
  const ok = await doRollback(rollbackTarget.value.id)
  rollbackRunning.value = false
  if (ok) rollbackDialog.value = false
}
</script>
