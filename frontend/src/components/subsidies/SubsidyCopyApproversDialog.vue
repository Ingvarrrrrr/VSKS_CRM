<template>
  <!-- ── Copy Approvers Sub-dialog ── -->
  <v-dialog v-model="showCopyApproversDialog" max-width="520" :fullscreen="mobile">
    <v-card>
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon icon="mdi-content-copy" color="indigo" class="mr-2" />
        Скопировать согласующих из другой субсидии
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="showCopyApproversDialog = false" />
      </v-card-title>
      <v-card-text>
        <v-autocomplete
          v-model="copyApprovers.sourceId"
          :items="copySourceSubsidies"
          item-title="name"
          item-value="id"
          label="Источник (другая субсидия)"
          variant="outlined" density="compact"
        />
        <v-checkbox
          v-model="copyApprovers.replace"
          label="Заменить существующих (иначе добавить в конец)"
          hide-details density="compact"
        />
        <v-alert v-if="copyApprovers.error" type="error" variant="tonal" density="compact" class="mt-2">
          {{ copyApprovers.error }}
        </v-alert>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="showCopyApproversDialog = false">Отмена</v-btn>
        <v-btn color="indigo" :loading="copyApprovers.loading"
               :disabled="!copyApprovers.sourceId"
               @click="confirmCopyApprovers">
          Скопировать
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'
import { useSubsidyApprovers } from '@/composables/subsidies/useSubsidyApprovers'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'

const { mobile } = useDisplay()

// Этот компонент — настоящий потомок SubsidiesView.vue, поэтому (в отличие от
// самого SubsidiesView.vue) может корректно заинжектить его provide() — нужен
// для copySourceSubsidies (список субсидий-источников копирования).
const {
  showCopyApproversDialog, copyApprovers, copySourceSubsidies, confirmCopyApprovers,
} = useSubsidyApprovers(useSubsidyDetailCtx())
</script>
