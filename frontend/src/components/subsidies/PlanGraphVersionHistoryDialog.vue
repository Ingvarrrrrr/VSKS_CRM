<template>
  <!-- 12-04: Version History Dialog -->
  <v-dialog v-model="v.showVersionHistoryDialog.value" max-width="720" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-history" size="20" color="blue-grey" class="mr-2" />
        История плана закупок
        <v-spacer />
        <v-btn icon="mdi-close" size="x-small" variant="text" @click="v.showVersionHistoryDialog.value = false" />
      </v-card-title>
      <v-divider />
      <v-card-text style="min-height:200px">
        <div v-if="v.versionHistoryLoading.value" class="d-flex justify-center py-8">
          <v-progress-circular indeterminate color="blue-grey" />
        </div>
        <div v-else-if="v.versionHistoryList.value.length === 0" class="text-center text-medium-emphasis py-8">
          Нет сохранённых версий
        </div>
        <v-table v-else density="compact">
          <thead>
            <tr>
              <th>Версия</th>
              <th>Дата</th>
              <th>Дата редакции</th>
              <th>Автор</th>
              <th class="text-right">Всего план, ₽</th>
              <th class="text-right">Факт, ₽</th>
              <th>Примечание</th>
              <th>Сравнить</th>
              <th>Excel</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="ver in v.versionHistoryList.value" :key="ver.id">
              <td><v-chip size="x-small" color="blue-grey" variant="tonal">v{{ ver.version_number }}</v-chip></td>
              <td style="font-size:12px">{{ ver.created_at ? new Date(ver.created_at).toLocaleString('ru') : '—' }}</td>
              <td style="font-size:12px">{{ (ver as any).effective_date ? new Date((ver as any).effective_date).toLocaleDateString('ru-RU') : '—' }}</td>
              <td style="font-size:12px">{{ ver.created_by_name || '—' }}</td>
              <td class="text-right" style="font-size:12px">{{ formatCurrency(ver.total_planned) }}</td>
              <td class="text-right" style="font-size:12px">{{ formatCurrency(ver.total_used) }}</td>
              <td style="font-size:12px;max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ ver.note || '—' }}</td>
              <td>
                <v-checkbox
                  v-model="v.compareSelected.value"
                  :value="ver.id"
                  :disabled="v.compareSelected.value.length >= 2 && !v.compareSelected.value.includes(ver.id)"
                  density="compact"
                  hide-details
                />
              </td>
              <td>
                <v-btn icon="mdi-file-excel" size="x-small" variant="text" color="green" @click="v.downloadVersionExcel(ver.id)" />
              </td>
              <td>
                <v-btn size="x-small" variant="text" color="blue" icon="mdi-eye-outline"
                  title="Просмотр снимка"
                  @click="v.viewVersionSnapshot(ver.id)" />
              </td>
            </tr>
          </tbody>
        </v-table>
        <div class="d-flex align-center justify-end mt-3 ga-2">
          <span v-if="v.compareSelected.value.length > 0" class="text-caption text-medium-emphasis mr-auto">
            Выбрано: {{ v.compareSelected.value.length }}/2
          </span>
          <v-btn
            v-if="v.compareSelected.value.length > 0"
            size="small"
            variant="text"
            @click="v.compareSelected.value = []"
          >Очистить</v-btn>
          <v-btn
            :disabled="v.compareSelected.value.length !== 2"
            color="primary"
            variant="flat"
            size="small"
            prepend-icon="mdi-compare"
            :loading="v.compareLoading.value"
            @click="v.downloadCompareExcel"
          >Скачать сравнение (Excel)</v-btn>
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// История версий план-графика — вынесена из SubsidiesView.vue. Состояние и вся
// логика — в usePlanGraphVersions.ts (singleton, общий с остальными тремя
// диалогами версий), этот компонент — только разметка.
import { useDisplay } from 'vuetify'
import { formatCurrency } from '@/composables/subsidies/format'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePlanGraphVersions } from '@/composables/subsidies/usePlanGraphVersions'

const { mobile } = useDisplay()
const v = usePlanGraphVersions(useSubsidyDetailCtx())
</script>
