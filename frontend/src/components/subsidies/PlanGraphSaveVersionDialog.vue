<template>
  <!-- 12-05: Save version dialog -->
  <v-dialog v-model="v.showSaveVersionDialog.value" max-width="540" :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex justify-space-between align-center">
        Сохранить редакцию ФЭО
        <v-btn icon="mdi-close" size="x-small" variant="text" @click="v.showSaveVersionDialog.value = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <v-text-field
          v-model="v.saveVersionEffectiveDate.value"
          type="date"
          label="Дата редакции"
          density="comfortable"
          variant="outlined"
          hide-details="auto"
          class="mb-3"
        />
        <v-textarea
          v-model="v.saveVersionNote.value"
          label="Примечание (необязательно)"
          rows="2"
          density="comfortable"
          variant="outlined"
          hide-details="auto"
        />
      </v-card-text>
      <v-divider />
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="v.showSaveVersionDialog.value = false">Отмена</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="v.saveVersionLoading.value"
          :disabled="!v.saveVersionEffectiveDate.value"
          @click="v.saveVersion"
        >
          Сохранить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Сохранение редакции ФЭО — вынесено из SubsidiesView.vue. Состояние/логика —
// в usePlanGraphVersions.ts (singleton, общий с остальными диалогами версий).
import { useDisplay } from 'vuetify'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { usePlanGraphVersions } from '@/composables/subsidies/usePlanGraphVersions'

const { mobile } = useDisplay()
const v = usePlanGraphVersions(useSubsidyDetailCtx())
</script>
