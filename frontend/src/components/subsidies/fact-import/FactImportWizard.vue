<template>
  <!-- Жалоба владельца 07.10.2026: при max-width:1100 колонки «Превышение»/
       «Сопоставление» уезжали за правый край таблицы шага 3 без видимой
       горизонтальной прокрутки — диалог расширен. -->
  <v-dialog v-model="factImport.show" max-width="1400" persistent :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6">
        Импорт факта
        <div class="text-caption text-medium-emphasis font-weight-regular mt-1">
          Шаг {{ factImport.step }} из 6
        </div>
      </v-card-title>
      <v-card-text class="px-6 fiw-body">
        <v-progress-linear v-if="factImport.loading" indeterminate color="teal" class="mb-3" />

        <FactImportStepFile v-if="factImport.step === 1" />
        <FactImportStepColumns v-else-if="factImport.step === 2" />
        <FactImportStepRows v-else-if="factImport.step === 3" :subsidy-id="factImport.subsidyId" />
        <FactImportStepGroups v-else-if="factImport.step === 4" />
        <FactImportStepConfirm v-else-if="factImport.step === 5" />
        <FactImportStepReport v-else />
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-btn v-if="factImport.step > 1 && factImport.step < 6" variant="text" :disabled="factImport.loading"
          @click="factImport.step -= 1">Назад</v-btn>
        <v-spacer />
        <v-btn variant="text" @click="factImport.show = false">
          {{ factImport.step === 6 ? 'Закрыть' : 'Отмена' }}
        </v-btn>

        <v-btn v-if="factImport.step === 1" color="primary" :loading="factImport.loading"
          :disabled="!factImport.selectedSheet || !factImport.preview" @click="factImport.step = 2">
          Далее
        </v-btn>
        <v-btn v-else-if="factImport.step === 2" color="primary" :loading="factImport.loading"
          :disabled="!mappingValid" @click="goToRows">
          Далее
        </v-btn>
        <v-btn v-else-if="factImport.step === 3" color="primary" :loading="factImport.loading"
          @click="goToGroups">
          Далее
        </v-btn>
        <v-btn v-else-if="factImport.step === 4" color="primary" :loading="factImport.loading"
          @click="goToConfirm">
          Далее
        </v-btn>
        <v-btn v-else-if="factImport.step === 5" color="error" :loading="factImport.loading"
          @click="commitImport">
          Загрузить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// FactImportWizard.vue — оболочка мастера «Импорт факта» (план
// breezy-mixing-lovelace.md, Часть 2, «Фронт»). Каждый шаг — отдельный файл в
// components/subsidies/fact-import/ (ПРАВИЛО №5 — не сваливать 6 шагов в один
// монолит); состояние общее — module-level singleton useFactImport.ts, та же
// схема, что у FeoImportWizard.vue/useFeoImport.ts.
import { useDisplay } from 'vuetify'
import { useFactImport } from '@/composables/subsidies/useFactImport'
import FactImportStepFile from './FactImportStepFile.vue'
import FactImportStepColumns from './FactImportStepColumns.vue'
import FactImportStepRows from './FactImportStepRows.vue'
import FactImportStepGroups from './FactImportStepGroups.vue'
import FactImportStepConfirm from './FactImportStepConfirm.vue'
import FactImportStepReport from './FactImportStepReport.vue'

const { mobile } = useDisplay()
const { factImport, mappingValid, loadPreview, commitImport: doCommit } = useFactImport()

async function goToRows() {
  await loadPreview()
  factImport.step = 3
}
async function goToGroups() {
  await loadPreview()
  factImport.step = 4
}
async function goToConfirm() {
  await loadPreview()
  factImport.step = 5
}
async function commitImport() {
  await doCommit()
}
</script>

<style scoped>
.fiw-body {
  max-height: 70vh;
  overflow-y: auto;
}
</style>
