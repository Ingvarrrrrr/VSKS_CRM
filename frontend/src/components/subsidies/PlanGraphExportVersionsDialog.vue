<template>
  <!-- Export versions dialog -->
  <v-dialog v-model="v.showExportVersionsDialog.value" max-width="760" scrollable>
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-file-excel-outline" size="20" color="success" class="mr-2" />
        Выгрузить редакции ФЭО
        <v-spacer />
        <v-btn icon="mdi-close" size="x-small" variant="text" @click="v.showExportVersionsDialog.value = false" />
      </v-card-title>
      <v-divider />
      <v-card-text style="min-height:160px">
        <v-progress-linear v-if="v.exportVersionsLoading.value" indeterminate color="primary" class="mb-3" />
        <div class="text-caption text-medium-emphasis mb-3">Выберите одну или несколько редакций. Несколько редакций выгрузятся в один документ — колонки рядом.</div>
        <v-checkbox v-model="v.exportIncludeCurrent.value" density="compact" hide-details label="Текущая (живая) ФЭО" class="mb-2" />
        <v-table density="compact">
          <thead>
            <tr>
              <th></th>
              <th>Дата редакции</th>
              <th>Примечание</th>
              <th class="text-right">План, ₽</th>
              <th class="text-right">Факт, ₽</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="ver in v.exportVersionsList.value" :key="ver.id">
              <td>
                <v-checkbox
                  :model-value="v.exportSelectedIds.value.includes(ver.id)"
                  @update:model-value="v.toggleExportId(ver.id)"
                  density="compact"
                  hide-details
                />
              </td>
              <td style="font-size:12px">{{ v.formatEditionDate(ver.effective_date || ver.created_at) }}</td>
              <td style="font-size:12px">{{ ver.note || '—' }}</td>
              <td class="text-right" style="font-size:12px">{{ Number(ver.total_planned || 0).toLocaleString('ru-RU') }}</td>
              <td class="text-right" style="font-size:12px">{{ Number(ver.total_used || 0).toLocaleString('ru-RU') }}</td>
            </tr>
            <tr v-if="!v.exportVersionsLoading.value && v.exportVersionsList.value.length === 0">
              <td colspan="5" class="text-center text-medium-emphasis py-4">Сохранённых редакций нет</td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
      <v-divider />
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="v.showExportVersionsDialog.value = false">Отмена</v-btn>
        <v-btn
          color="success"
          variant="flat"
          prepend-icon="mdi-file-excel-outline"
          :loading="v.exportRunning.value"
          :disabled="v.exportSelectedIds.value.length === 0 && !v.exportIncludeCurrent.value"
          @click="v.runVersionsExport"
        >Выгрузить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Экспорт редакций ФЭО — вынесен из SubsidiesView.vue. Состояние/логика — в
// usePlanGraphVersions.ts (singleton, общий с остальными диалогами версий).
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePlanGraphVersions } from '@/composables/subsidies/usePlanGraphVersions'

const v = usePlanGraphVersions(useSubsidyDetailCtx())
</script>
