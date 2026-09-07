<template>
  <v-dialog v-model="importDialog.show" max-width="800" persistent :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4">
        Импорт договоров из файла
      </v-card-title>
      <v-card-text class="px-4">
        <!-- Step 1: File upload with drag-and-drop -->
        <div v-if="importDialog.step === 1">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-information-outline">
            <div class="text-body-2">
              <strong>Форматы:</strong> Excel (.xlsx, .xls), Word (.docx), PDF<br>
              <strong>Заголовки:</strong> определяются автоматически по ключевым словам — могут быть в любой строке<br>
              <strong>Лист:</strong> любое название — система прочитает первый или предложит выбрать
            </div>
          </v-alert>
          <FileDropZone v-model="importDialog.file" accept=".pdf,.xlsx,.xls,.docx,.doc"
            hint="PDF, Excel (.xlsx, .xls), Word (.docx) — таблица с договорами" class="mb-3" />
          <v-select v-model="importDialog.subsidyId" :items="subsidyOptions" item-title="name" item-value="id"
            label="Субсидия (для всех импортируемых)" variant="outlined" density="compact" clearable class="mt-2" />
        </div>

        <!-- Step 2: Column mapping -->
        <div v-if="importDialog.step === 2">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3" icon="mdi-file-table-outline">
            <strong>Лист:</strong> {{ importDialog.sheetName || 'Первый лист' }} ({{ importDialog.totalRows }} строк данных)
          </v-alert>
          <p class="text-body-2 mb-3">
            Сопоставьте столбцы файла с полями договора:
          </p>
          <v-row dense>
            <v-col v-for="field in importFields" :key="field.key" cols="12" md="6">
              <v-select v-model="importDialog.mapping[field.key]" :items="importDialog.headerOptions"
                :label="field.label + (field.required ? ' *' : '')" variant="outlined" density="compact" clearable />
            </v-col>
          </v-row>
          <!-- Sample data preview -->
          <div v-if="importDialog.sample.length" class="mt-3">
            <div class="text-body-2 font-weight-medium mb-1">Пример данных:</div>
            <v-table density="compact" class="text-caption">
              <thead>
                <tr><th v-for="h in importDialog.headers" :key="h">{{ h }}</th></tr>
              </thead>
              <tbody>
                <tr v-for="(row, ri) in importDialog.sample" :key="ri">
                  <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </div>

        <!-- Step 3: Result -->
        <div v-if="importDialog.step === 3">
          <v-alert type="success" variant="tonal" density="compact" class="mb-2">
            Создано: <strong>{{ importDialog.result?.created }}</strong>,
            пропущено (дубли): <strong>{{ importDialog.result?.skipped }}</strong>
          </v-alert>
        </div>

        <v-alert v-if="importDialog.error" type="error" variant="tonal" density="compact" class="mt-2">
          {{ importDialog.error }}
        </v-alert>
      </v-card-text>
      <v-card-actions class="px-4 pb-3">
        <v-spacer />
        <v-btn variant="text" @click="onClose">{{ importDialog.step === 3 ? 'Закрыть' : 'Отмена' }}</v-btn>
        <v-btn v-if="importDialog.step === 1" color="primary" variant="tonal" :loading="importDialog.loading"
          :disabled="!importDialog.file" @click="onPreview">
          Далее
        </v-btn>
        <v-btn v-if="importDialog.step === 2" color="primary" variant="tonal" :loading="importDialog.loading"
          :disabled="!importDialog.mapping.number" @click="onImport">
          Импортировать
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import FileDropZone from '@/components/FileDropZone.vue'
import { importFields } from '@/composables/contracts/useContractsImport'
import type { Subsidy } from '@/composables/contracts/contractsTypes'

defineProps<{
  importDialog: {
    show: boolean; step: number; loading: boolean; dragging: boolean
    file: File | null; subsidyId: number | null
    headers: string[]; headerOptions: { title: string; value: number }[]
    sample: string[][]; totalRows: number; headerRowOffset: number; sheetName: string
    mapping: Record<string, number | null>
    result: { created: number; skipped: number } | null
    error: string
  }
  subsidyOptions: Subsidy[]
  mobile: boolean
  onClose: () => void
  onPreview: () => void
  onImport: () => void
}>()
</script>
