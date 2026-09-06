<template>
  <!-- ── Copy Templates Sub-dialog ── -->
  <v-dialog v-model="showCopyTemplatesDialog" max-width="520" :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon icon="mdi-content-copy" color="indigo" class="mr-2" />
        Скопировать шаблоны из другой субсидии
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showCopyTemplatesDialog = false" />
      </v-card-title>
      <v-card-text>
        <v-autocomplete
          v-model="copyTemplates.sourceId"
          :items="copySourceSubsidiesForTemplates"
          item-title="name"
          item-value="id"
          label="Источник (другая субсидия)"
          variant="outlined" density="compact"
        />
        <v-checkbox
          v-model="copyTemplates.replace"
          label="Перезаписать существующие шаблоны"
          hide-details density="compact"
        />
        <v-alert v-if="copyTemplates.error" type="error" variant="tonal" density="compact" class="mt-2">
          {{ copyTemplates.error }}
        </v-alert>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="showCopyTemplatesDialog = false">Отмена</v-btn>
        <v-btn color="indigo" :loading="copyTemplates.loading"
               :disabled="!copyTemplates.sourceId"
               @click="confirmCopyTemplates">
          Скопировать
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'
import { useSubsidyTemplates } from '@/composables/subsidies/useSubsidyTemplates'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'

const { mobile } = useDisplay()

// Настоящий потомок SubsidiesView.vue — может корректно заинжектить его
// provide() (нужен для copySourceSubsidiesForTemplates), в отличие от самого
// SubsidiesView.vue.
const {
  showCopyTemplatesDialog, copyTemplates, copySourceSubsidiesForTemplates, confirmCopyTemplates,
} = useSubsidyTemplates(useSubsidyDetailCtx())
</script>
